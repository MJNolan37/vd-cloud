# Atlas Observatory

A descriptive TQQQ / QQQ monitor, extending the [V&D Cloud](../README.md) research into rolling metrics and provisional threshold labels.

The committed [`index.html`](index.html) is a **verified snapshot, latest observation 2026-10-13**, from the revised implementation. Download and open locally. It embeds the plotting library and needs no server; it does not refresh automatically. GitHub's file view is not a rendered dashboard.

## Metrics and Interpretation

- Adjusted price normalized to the prior year's final available close, and current-year return from that close.
- 20-day annualized realized volatility.
- Pairwise correlation distance (`1 - rolling correlation` versus QQQ), distinct from cross-sectional dispersion.
- Volatility × correlation-distance state frequencies and a chronological state path.
- Rolling volume and descriptive high/lower-volatility, high/low-correlation-distance labels.

Public daily adjusted prices and volume come via `yfinance`. TQQQ's daily-reset leverage makes its return correlation with QQQ very close to one. Changes in this small proxy do not demonstrate market fragmentation or a trading opportunity. Zones have no predictive validation.

The revised calculation uses expanding quartiles from observations strictly **before each labeled date**, with at least 20 valid proxy observations in the displayed year. Ties can leave buckets empty. Initial states are uncalibrated; heatmap percentages cover calibrated observations only. Fixed volatility heatmap bands (Low up to and including 40%; Medium above 40% to 70%; High above 70% to 100%; Very High above 100%) differ from the state's 80% split; these are visualization choices, not learned thresholds. The header shows the full calculated state (for example, “Lower volatility · low correlation distance”) with its rule. Because distance cutoffs come from earlier days, the heatmap's distance columns need not hold 25% of days each.

## Reproducing the Revised Snapshot

On Windows/Python 3.12, install [`requirements-lock-windows-py312.txt`](../requirements-lock-windows-py312.txt) in an isolated environment. Other platforms may use [`requirements.txt`](../requirements.txt); their full environments are not validated by this run. From the repository root:

```powershell
python scripts/reproduce.py --atlas
```

Alternatively execute `atlas_observatory.ipynb` top-to-bottom. The year is calculated at execution time; pre-year data provides rolling-window warm-up. The output path is explicitly `atlas/index.html`, regardless of working directory. The research notebooks use fixed dates in [`config.py`](../config.py).

The downloader caches CSVs with hashes. Use `--refresh --atlas` for new responses or `--offline --atlas` to require matching cached data. A cache from another year cannot satisfy a current-year request. The metric table was verified in the October 13, 2026 run. This HTML was subsequently regenerated from that same table with the revised layout; repeated presentation renders are byte-identical. The original run manifest identifies the earlier HTML, while `results/atlas_layout_validation.json` identifies this presentation revision. Refreshing from Yahoo can change the data and should be followed by a new manifest and caption review.

## Reading the Dashboard

The initial layout is compact and responsive, with a separate header and short guides below each chart title. Volatility and correlation distance use independent time-series panels. The state chart shows faint earlier observations, a teal twenty-observation trail with exact dates on hover, and a white diamond for the latest observation. Its small correlation distances do not indicate leverage tracking error or broad market fragmentation.

The time-series and state charts keep zoom and pan controls; the heatmap is fixed. Year-to-date / 90-day / 30-day buttons change only the four time-series charts, setting their date range and rescaling their vertical axes to the visible window; the heatmap and state chart always cover the year to date. Reset all charts restores the default view. Smaller screens stack the panels.

To regenerate the presentation from the verified exported metrics without downloading data or rerunning research:

```powershell
python scripts/render_atlas.py
```

The footer states that the dashboard is a manually refreshed daily-data snapshot, not real-time quotes. It records the latest observation and generation time separately. Identical metrics and renderer versions reuse the original snapshot-generation time so offline replay remains deterministic. This timestamp is not the date of a fresh market-data download.

The subtitle identifies TQQQ as the monitored instrument and QQQ as the return-alignment benchmark; every caption names TQQQ, and the correlation-distance, heatmap and state captions also name QQQ. The state chart uses categorical styling (gray history, teal recent trail, white latest diamond), with no date-gradient axis.

Each chart guide explains its measurement and a concrete reading: price adjustment versus normalization, annualized variability versus investment return, correlation distance versus leverage tracking, heatmap percentages as shares of included days, the state trail as measured conditions rather than price direction, and volume in shares rather than dollars.
