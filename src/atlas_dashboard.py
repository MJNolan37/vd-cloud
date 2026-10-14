"""Compact, self-contained Atlas presentation from previously calculated metrics."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from html import escape
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

CAPTIONS = {
    "price": ("Normalized adjusted price", "Yahoo adjusts {target}’s prices for stock splits and distributions, so those events do not show up as price jumps or drops. The last adjusted close of {base_year} is then set to 100: a reading of 150 means the adjusted price is 50% above that starting value."),
    "volatility": ("Realized volatility", "Standard deviation of {target}’s daily returns over the 20 trading days ending on each date, scaled to an annual rate (×√252). Higher readings mean larger daily swings: 40% corresponds to a daily-return standard deviation of about 2.5%, not an average or predicted daily move. It measures variability, not a 40% gain or loss."),
    "distance": ("Correlation distance from {benchmark}", "One minus the correlation between {target}’s and {benchmark}’s daily returns over the 20 trading days ending on each date. Higher means weaker alignment: a distance of 0.0002 means a correlation of 0.9998, still extremely close. It does not measure whether {target} delivered three times {benchmark}’s return."),
    "heatmap": ("State-frequency heatmap", "Each cell pairs a {target} volatility band with a band of correlation distance from {benchmark} and shows the share of included days with that combination. A cell showing 25% means the combination occurred on 25 of every 100 included days. Brighter means more common, not better conditions or a stronger forecast."),
    "state": ("Current state vs. recent history", "Each point places one day’s {target} volatility against its correlation distance from {benchmark}. Right means larger daily swings; up means weaker alignment. The trail shows movement between measured states, not the direction of {target}’s price."),
    "volume": ("Rolling volume", "{target} shares traded per day, averaged over the 20 trading days ending on each date. A bar at 50M means an average of 50 million shares each day, not $50 million or the total over 20 days."),
}

# Heatmap volatility bands: pd.cut(bins=[0, .40, .70, 1., inf], include_lowest=True) is right-closed.
VOL_BAND_LABELS = {"Low": "Low ≤40%", "Medium": "Medium 40–70%", "High": "High 70–100%", "Very High": "Very High >100%"}

CONFIG = {"responsive": True, "displaylogo": False, "displayModeBar": True,
          "scrollZoom": False, "doubleClick": "reset",
          "modeBarButtons": [["zoom2d", "pan2d", "zoomIn2d", "zoomOut2d", "resetScale2d", "toImage"]],
          "toImageButtonOptions": {"height": None, "width": None, "scale": 2}}


def build_charts(metrics, target="TQQQ", benchmark="QQQ"):
    if metrics.empty or not metrics.index.is_monotonic_increasing or not metrics.index.is_unique:
        raise ValueError("Dashboard metrics need a nonempty, unique, increasing date index.")
    dates = metrics.index.strftime("%Y-%m-%d")
    charts = {}
    chart_specs = [("price", "Price_Index", "Price index", "#a6a4ff", None),
                   ("volatility", "Realized_Vol", "Annualized volatility", "#ffb17a", ".0%"),
                   ("distance", "Dispersion_Proxy", "1 − correlation", "#63d9c4", ".5f"),
                   ("volume", "Rolling_Volume", "Shares / day", "#65bad8", "~s")]
    for key, column, title, color, tickformat in chart_specs:
        trace = (go.Bar(x=dates, y=metrics[column], marker_color=color, opacity=.8,
                        hovertemplate="%{x|%d %b %Y}<br>20-day average: %{y:,.0f} shares<extra></extra>")
                 if key == "volume" else go.Scatter(x=dates, y=metrics[column], mode="lines",
                        line={"color": color, "width": 1.8},
                        hovertemplate=("%{x|%d %b %Y}<br>" + title + ": %{y:" +
                                       (".1%" if key == "volatility" else ".6f" if key == "distance" else ".1f") + "}<extra></extra>")))
        fig = go.Figure(trace)
        fig.update_xaxes(type="date", tickformat="%b", dtick="M1", nticks=8)
        fig.update_yaxes(title_text=title, tickformat=tickformat, rangemode="tozero" if key != "price" else "normal")
        if key == "price":
            fig.add_hline(y=100, line_dash="dot", line_color="#7a8798", line_width=1)
        charts[key] = fig

    heat = (metrics.groupby(["Vol_Bucket", "Disp_Bucket"], observed=False).size().unstack(fill_value=0)
            .reindex(index=["Low", "Medium", "High", "Very High"],
                     columns=["Very Low", "Low", "Medium", "High"], fill_value=0))
    calibrated = int(heat.to_numpy().sum())
    if not calibrated:
        raise ValueError("No calibrated observations are available for the state-frequency heatmap.")
    heat_pct = heat / calibrated * 100
    charts["heatmap"] = go.Figure(go.Heatmap(
        x=list(heat_pct.columns), y=[VOL_BAND_LABELS[label] for label in heat_pct.index], z=heat_pct.to_numpy(),
        text=np.round(heat_pct.to_numpy(), 1), texttemplate="%{text:.1f}%",
        colorscale=[[0,"#18233a"],[.35,"#285b83"],[.7,"#40a8a7"],[1,"#e3ce72"]],
        showscale=False, xgap=2, ygap=2,
        hovertemplate="Volatility: %{y}<br>Correlation-distance bucket: %{x}<br>%{z:.1f}% of included days<extra></extra>"))
    charts["heatmap"].update_xaxes(title_text=f"{target}–{benchmark} distance bucket", fixedrange=True)
    charts["heatmap"].update_yaxes(title_text=f"{target} volatility bucket", fixedrange=True)

    trail = metrics.tail(20)
    older = metrics.iloc[:-len(trail)]
    state = go.Figure()
    hover = "%{text}<br>Volatility: %{x:.1%}<br>Correlation distance: %{y:.6f}<extra></extra>"
    state.add_trace(go.Scatter(x=older.Realized_Vol, y=older.Dispersion_Proxy,
                    mode="markers", marker={"size": 5, "color": "#7c8799", "opacity": .32},
                    name="Earlier this year", text=older.index.strftime("%d %b %Y"), hovertemplate=hover))
    state.add_trace(go.Scatter(x=trail.Realized_Vol, y=trail.Dispersion_Proxy,
                    mode="lines+markers", name="Recent 20 observations", text=trail.index.strftime("%d %b %Y"),
                    line={"width": 1.7, "color": "#63d9c4"},
                    hovertemplate=hover, marker={"size": 6, "color": "#63d9c4"}))
    state.add_trace(go.Scatter(x=[metrics.Realized_Vol.iloc[-1]], y=[metrics.Dispersion_Proxy.iloc[-1]],
                    mode="markers", name="Latest: " + metrics.index[-1].strftime("%d %b"), text=[metrics.index[-1].strftime("%d %b %Y")],
                    marker={"symbol": "diamond", "size": 12, "color": "#f7faff",
                            "line": {"color": "#101825", "width": 1.5}}, hovertemplate=hover))
    state.update_xaxes(title_text=f"{target} annualized volatility", tickformat=".0%")
    state.update_yaxes(title_text=f"Distance from {benchmark}", tickformat=".4f")
    state.update_layout(showlegend=True, hovermode="closest",
                        legend={"orientation": "h", "y": 1.08, "x": 0,
                                "font": {"size": 10}, "yanchor": "bottom"})
    charts["state"] = state

    for key, fig in charts.items():
        fig.update_layout(template="plotly_dark", autosize=True,
                          paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                          font={"family": "Arial, sans-serif", "size": 11, "color": "#c5d1df"},
                          margin={"l": 58, "r": 14, "t": 28 if key == "state" else 16,
                                  "b": 40 if key in ("state", "heatmap") else 23},
                          showlegend=key == "state", hovermode="closest" if key in ("heatmap","state") else "x unified")
        fig.update_xaxes(gridcolor="#263141", zeroline=False, automargin=True)
        fig.update_yaxes(gridcolor="#263141", zeroline=False, automargin=True)
    return charts


CSS = """
:root{color-scheme:dark;--bg:#0b1019;--panel:#111a27;--text:#edf3fa;--muted:#9baec2;--edge:#263244}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:13px/1.4 Arial,sans-serif}
main{max-width:1480px;margin:0 auto;padding:18px 24px 14px}header{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}
h1{font-size:22px;line-height:1.2;margin:0 0 5px;font-weight:600;letter-spacing:-.4px}.sub{color:var(--muted);margin:0;font-size:12px}
.badge{border:1px solid #426d65;background:#15322e;color:#a8e0ca;padding:5px 9px;border-radius:18px;white-space:nowrap;font-size:11px}
.origin{margin:9px 0;color:var(--muted);font-size:12px}.origin summary{cursor:pointer;color:#b5d8ef}.origin p{max-width:100ch;margin:7px 0}.origin a{color:#a8d4f3;text-underline-offset:3px}
.readout{display:flex;flex-wrap:wrap;gap:12px 24px;padding:10px 0 8px}.readout span{color:var(--muted);font-size:11px}.readout strong{color:var(--text);margin-left:6px;font-size:13px;font-weight:500}
.controls{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:0 0 10px}.controls .hint{color:var(--muted);font-size:11px;margin-left:7px}
button{background:#1b293b;color:#dce7f4;border:1px solid #35475e;border-radius:5px;padding:4px 9px;font:11px Arial;cursor:pointer}
button:hover,button.active{background:#29435d;border-color:#6994b7}button:focus-visible{outline:2px solid #a6cde9;outline-offset:2px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.card{min-width:0;background:var(--panel);border:1px solid var(--edge);border-radius:9px;padding:9px 11px 2px}
.wide{grid-column:1/-1}h2{font-size:13px;font-weight:600;margin:0 0 2px}.caption{font-size:11px;color:var(--muted);line-height:1.35;margin:0;min-height:15px}
.chart{width:100%;height:clamp(110px,14vh,170px)}.state-chart,.heatmap-chart{height:clamp(205px,25vh,275px)}.volume-chart{height:clamp(90px,11vh,125px)}
.note{font-size:10px;color:#92a8bc;margin:3px 0 4px}.state-rule{margin:-4px 0 8px}footer{border-top:1px solid var(--edge);margin-top:12px;padding-top:9px;color:var(--muted);font-size:11px}
footer p{margin:0 0 4px}footer strong{color:#c9d7e5;font-weight:500}.js-plotly-plot .plotly .modebar{right:4px;top:1px}
.js-plotly-plot .plotly .modebar-btn{font-size:11px}.error{color:#ffc4a4;padding:10px}
@media(min-width:1700px){main{max-width:1600px}}@media(max-width:780px){main{padding:15px 12px}header{display:block}.badge{display:inline-block;margin-top:8px}.grid{grid-template-columns:1fr}.wide{grid-column:auto}.chart{height:165px}.state-chart,.heatmap-chart{height:250px}.volume-chart{height:135px}.readout{gap:8px 16px}.controls .hint{display:block;width:100%;margin-left:0}}
"""


def render_dashboard(metrics, target, benchmark, ytd_return, output_path, snapshot_path=None, generated_at=None):
    """Persist a generation timestamp per identical metrics + renderer + package version.

    Replaying the same snapshot reuses its generation time, so HTML remains byte-identical.
    It does not falsely label cached prices as a fresh download.
    """
    from plotly import __version__ as plotly_version
    charts = build_charts(metrics, target, benchmark)
    payload = metrics.to_csv(float_format="%.17g").encode()
    fingerprint = hashlib.sha256(payload + Path(__file__).read_bytes() +
                  json.dumps([target,benchmark,float(ytd_return),plotly_version]).encode()).hexdigest()
    output_path = Path(output_path)
    snapshot_path = Path(snapshot_path) if snapshot_path else output_path.with_suffix(".snapshot.json")
    previous = json.loads(snapshot_path.read_text(encoding="utf-8")) if snapshot_path.exists() else {}
    if previous.get("fingerprint") == fingerprint:
        stamp = previous["generated_at_utc"]
    else:
        stamp = (generated_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    local = datetime.fromisoformat(stamp).astimezone(ZoneInfo("America/Los_Angeles"))
    latest = metrics.iloc[-1]
    last_date = metrics.index[-1].strftime("%d %b %Y")
    first_date = metrics.index[0].strftime("%Y-%m-%d")
    last_iso = metrics.index[-1].strftime("%Y-%m-%d")
    # Plain copies of the time series let the date buttons rescale each vertical axis
    # without reading Plotly's internal (typed-array) trace storage.
    series = {"dates": list(metrics.index.strftime("%Y-%m-%d"))}
    for key, column in [("price", "Price_Index"), ("volatility", "Realized_Vol"),
                        ("distance", "Dispersion_Proxy"), ("volume", "Rolling_Volume")]:
        series[key] = [None if pd.isna(v) else float(v) for v in metrics[column]]
    panels = []
    words = {"target": target, "benchmark": benchmark, "base_year": metrics.index[0].year - 1}
    included = metrics["Disp_Bucket"].notna() & metrics["Vol_Bucket"].notna()
    column_counts = metrics.loc[included, "Disp_Bucket"].value_counts().reindex(["Very Low", "Low", "Medium", "High"], fill_value=0)
    column_shares = " · ".join(f"{name} {count / included.sum():.0%}" for name, count in column_counts.items())
    first_included = metrics.index[included.to_numpy()].min().strftime("%d %b %Y")
    trail_start = metrics.index[-20:][0].strftime("%d %b")
    heatmap_note = (f'<p class="note">Included: {included.sum()} of {len(metrics)} days ({first_included} to {last_date}); '
                    f'{(~included).sum()} days without 20 earlier observations this year are excluded. '
                    'Volatility bands: Low up to and including 40%; Medium above 40% to 70%; High above 70% to 100%; Very High above 100%.</p>'
                    '<p class="note">Distance bands use quartile cutoffs from earlier days this year, so columns need not hold 25% of days each '
                    f'(here {escape(column_shares)}). “High” means relatively weaker alignment for this pair.</p>')
    state_note = (f'<p class="note">Gray dots = earlier this year · Teal trail = recent 20 observations ({trail_start} to {metrics.index[-1].strftime("%d %b")}) · '
                  'White diamond = latest, drawn over the trail’s last point. Hover for dates.</p>'
                  '<p class="note">Small distances still mean very close correlation; this is not leverage tracking error.</p>')
    for key in ["price", "volatility", "distance", "heatmap", "state", "volume"]:
        title, caption = CAPTIONS[key]
        title, caption = title.format(**words), caption.format(**words)
        chart_config = {**CONFIG, "displayModeBar": False} if key == "heatmap" else CONFIG
        chart = charts[key].to_html(full_html=False, include_plotlyjs=False,
                                    div_id="atlas-"+key, config=chart_config)
        # Plotly's inline chart element takes the exact height of this enclosing card region.
        note = state_note if key == "state" else heatmap_note if key == "heatmap" else ''
        klass = "card wide" if key in ("price","volume") else "card"
        chartklass = "chart "+("state-chart" if key == "state" else "heatmap-chart" if key == "heatmap" else "volume-chart" if key == "volume" else "")
        panels.append(f'<section class="{klass}" aria-labelledby="heading-{key}"><h2 id="heading-{key}">{escape(title)}</h2>'
                      f'<p class="caption">{escape(caption)}</p><div class="{chartklass}">{chart}</div>{note}</section>')
    # Use the calculated zone so the header cannot drift from classify_zone.
    zone = str(latest.get("Zone", ""))
    state_text = ("Uncalibrated (needs 20 earlier observations this year)" if zone == "Uncalibrated"
                  else zone.replace(" / ", " · "))
    date_text = local.strftime("%d %b %Y, %I:%M %p %Z")
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Atlas Observatory | {escape(target)} / {escape(benchmark)}</title><style>{CSS}</style>
<script>{get_plotlyjs()}</script></head><body><main>
<header><div><h1>Atlas Observatory</h1><p class="sub">{escape(target)} monitoring · {escape(benchmark)} is the return-alignment benchmark</p></div>
<span class="badge">Daily-data snapshot · Updated manually</span></header>
<details class="origin"><summary>From self-study research to Atlas</summary>
<p>Atlas grew out of V&amp;D Cloud, a self-study project exploring whether volatility and cross-sectional dispersion could support an Ichimoku-inspired market-regime framework. The research produced descriptive structure but did not establish predictive validity.</p>
<p>Atlas carries that learning into a simpler monitoring dashboard: {escape(target)} is the instrument being observed, and {escape(benchmark)} is its return-alignment benchmark. Its pairwise correlation-distance measure differs from the country/stock cross-sectional dispersion used in the research.</p>
<p><a href="https://github.com/MJNolan37/vd-cloud#research-question-and-motivation">Read the research story and methodology</a> · <a href="https://github.com/MJNolan37/vd-cloud#verified-revised-results">Explore the research findings</a></p></details>
<div class="readout"><div><span>Latest observation</span><strong>{last_date}</strong></div>
<div><span>YTD adjusted return</span><strong>{ytd_return:.1%}</strong></div>
<div><span>20-day annualized volatility</span><strong>{latest.Realized_Vol:.1%}</strong></div>
<div><span>20-day correlation with {escape(benchmark)}</span><strong>{latest.Correlation_vs_QQQ:.5f}</strong></div>
<div><span>Descriptive state</span><strong>{escape(state_text)}</strong></div></div>
<p class="note state-rule">State rule: volatility of 80% or more is high; correlation distance at or above the 75th percentile of earlier days this year is high using the same percentile value as the heatmap. The heatmap’s volatility bands are separate; its distance bands put exact cutoff ties in the lower band.</p>
<nav class="controls" aria-label="Chart views"><button class="active" data-range="all">Year to date</button>
<button data-range="90">Last 90 days</button><button data-range="30">Last 30 days</button>
<button id="reset-view">Reset all charts</button><span class="hint">Use + / − within a chart to zoom. Date buttons set the range of the four time-series charts and rescale their vertical axes; the heatmap and state chart always cover the year to date.</span></nav>
<div class="grid">{''.join(panels)}</div>
<footer><p><strong>Data:</strong> Yahoo Finance via yfinance. Daily adjusted prices and trading volume; not real-time quotes. Updates only when regenerated.</p>
<p>Latest market observation: <strong>{last_date}</strong> · Dashboard generated: <strong>{escape(date_text)} · America/Los_Angeles</strong></p>
<p>Historical data may be revised. Metrics and state labels are descriptive research, not validated forecasts or trading recommendations.</p></footer>
</main><script>
const timeCharts = ['price','volatility','distance','volume'];
const allCharts = ['price','volatility','distance','heatmap','state','volume'];
const lastDate = {json.dumps(last_iso)}, firstDate = {json.dumps(first_date)};
const series = {json.dumps(series)};
document.querySelectorAll('[data-range]').forEach(button => button.addEventListener('click', () => {{
 document.querySelectorAll('[data-range]').forEach(b => b.classList.remove('active'));button.classList.add('active');
 const date = new Date(lastDate+'T12:00:00Z');date.setUTCDate(date.getUTCDate()-Number(button.dataset.range));
 const start = button.dataset.range==='all' ? firstDate : date.toISOString().slice(0,10);
 timeCharts.forEach(key => {{
  const gd = document.getElementById('atlas-'+key);
  const ys = series.dates.map((x,i)=>[x, series[key][i]]).filter(([x,y])=>x>=start && x<=lastDate && Number.isFinite(y)).map(([,y])=>y);
  const update = {{'xaxis.range':[start,lastDate],'xaxis.autorange':false}};
  if (ys.length) {{
   const lo = Math.min(...ys), hi = Math.max(...ys), pad = (hi-lo || Math.abs(hi) || 1)*0.08;
   update['yaxis.range'] = key==='price' ? [lo-pad, hi+pad] : [0, hi+pad];
   update['yaxis.autorange'] = false;
  }}
  Plotly.relayout(gd, update);
 }});
}}));
document.getElementById('reset-view').addEventListener('click', () => {{
 allCharts.forEach(key => Plotly.relayout('atlas-'+key, {{'xaxis.autorange':true,'yaxis.autorange':true}}));
 document.querySelectorAll('[data-range]').forEach(b=>b.classList.toggle('active',b.dataset.range==='all'));
}});
window.addEventListener('resize',()=>allCharts.forEach(key=>Plotly.Plots.resize('atlas-'+key)));
</script></body></html>'''
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(page, encoding="utf-8", newline="\n")
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(json.dumps({"fingerprint":fingerprint,"generated_at_utc":stamp,
        "latest_market_observation":last_iso,"timezone":"America/Los_Angeles",
        "data_mode":"daily_snapshot_manual_refresh"},indent=2)+"\n",encoding="utf-8",newline="\n")
    return charts
