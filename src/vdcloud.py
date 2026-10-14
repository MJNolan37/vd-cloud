"""Daily-data research helpers; all signal calculations use present/past data only."""
from __future__ import annotations

import numpy as np
import pandas as pd

REGIMES = ("above_cloud", "inside_cloud", "below_cloud")


def validate_prices(prices, required_tickers):
    if prices.empty or not prices.index.is_monotonic_increasing or not prices.index.is_unique:
        raise ValueError("Prices must have a nonempty, unique, increasing date index.")
    missing = [t for t in required_tickers if t not in prices or prices[t].notna().sum() == 0]
    if missing:
        raise ValueError(f"Missing or empty ticker downloads: {missing}")
    values = prices[list(required_tickers)].to_numpy(dtype=float)
    if np.isinf(values).any() or (values[np.isfinite(values)] <= 0).any():
        raise ValueError("Observed adjusted prices must be finite and positive.")


def select_field(raw, fields, required_tickers):
    """Return one price field per ticker from either yfinance column ordering.

    ``fields`` is in order of preference; the first field present is used.
    """
    if isinstance(raw.columns, pd.MultiIndex):
        for field in fields:
            for level in range(raw.columns.nlevels):
                if field in raw.columns.get_level_values(level):
                    frame = raw.xs(field, axis=1, level=level).copy()
                    missing = [t for t in required_tickers if t not in frame]
                    if missing:
                        raise ValueError(f"Missing or empty ticker downloads: {missing}")
                    return frame[list(required_tickers)]
        raise ValueError(f"None of the fields {fields} is in the download.")
    if len(required_tickers) != 1:
        raise ValueError("Flat-column download cannot represent multiple requested tickers.")
    for field in fields:
        if field in raw:
            return raw[[field]].rename(columns={field: required_tickers[0]})
    raise ValueError(f"None of the fields {fields} is in the download.")


def adjusted_close(raw, required_tickers):
    """Adjusted closes from either yfinance MultiIndex ordering or a single-ticker frame.

    "Adj Close" is preferred when present: with ``auto_adjust=False`` yfinance also
    returns an unadjusted "Close". With ``auto_adjust=True`` (used throughout),
    "Close" is already adjusted and is the only close field.
    """
    prices = select_field(raw, ("Adj Close", "Close"), required_tickers)
    validate_prices(prices, required_tickers)
    return prices


def price_returns(prices):
    # Retain dates with missing returns: dropping them can bridge gaps in later windows.
    return prices.pct_change(fill_method=None)


def rolling_zscore(series, window):
    mean = series.rolling(window, min_periods=window).mean()
    std = series.rolling(window, min_periods=window).std(ddof=1)
    return ((series - mean) / std.where(std > 0)).replace([np.inf, -np.inf], np.nan)


def rolling_midpoint(series, window):
    return (series.rolling(window, min_periods=window).max()
            + series.rolling(window, min_periods=window).min()) / 2


def build_cloud(signal, fast=9, medium=26, slow=52):
    conversion, base = rolling_midpoint(signal, fast), rolling_midpoint(signal, medium)
    a, b = (conversion + base) / 2, rolling_midpoint(signal, slow)
    spans = pd.concat([a, b], axis=1)
    top, bottom = spans.max(axis=1, skipna=False), spans.min(axis=1, skipna=False)
    valid = signal.notna() & top.notna() & bottom.notna()
    regime = pd.Series(np.where(signal > top, "above_cloud",
                       np.where(signal < bottom, "below_cloud", "inside_cloud")),
                       index=signal.index, dtype=object).where(valid)
    return pd.DataFrame({"signal": signal, "conversion_line": conversion, "base_line": base,
                         "span_a": a, "span_b": b, "cloud_top": top,
                         "cloud_bottom": bottom, "regime_state": regime})


def forward_return(returns, horizon):
    if horizon < 1:
        raise ValueError("Forward horizon must be positive.")
    gross = 1 + returns.shift(-1)
    return (gross.rolling(horizon, min_periods=horizon).apply(np.prod, raw=True)
            .shift(-(horizon - 1)) - 1).replace([np.inf, -np.inf], np.nan)


def purge_cross_boundary(forward, in_sample_end):
    """Mask outcomes originating in-sample but ending outside that period."""
    result = forward.copy()
    dates = pd.Series(result.index, index=result.index)
    end = pd.Timestamp(in_sample_end)
    for col in result:
        horizon = int(col.removeprefix("fwd_").removesuffix("d"))
        endpoint = dates.shift(-horizon)
        crosses = (dates <= end) & ((endpoint > end) | endpoint.isna())
        result.loc[crosses, col] = np.nan
    return result


def persistence_confirmed(regimes, window, unconfirmed="unconfirmed"):
    if window < 1:
        raise ValueError("Persistence window must be positive.")
    result = pd.Series(unconfirmed, index=regimes.index, dtype=object)
    for i in range(window - 1, len(regimes)):
        values = regimes.iloc[i - window + 1:i + 1]
        if values.notna().all() and values.iloc[0] in REGIMES and values.eq(values.iloc[0]).all():
            result.iloc[i] = values.iloc[0]
    return result.where(regimes.isin(REGIMES))


def prior_quantile_buckets(series, labels, min_periods=126):
    """Quartile edges use observations strictly before the labeled date."""
    if len(labels) != 4:
        raise ValueError("Four labels are required.")
    past = series.shift(1).expanding(min_periods=min_periods)
    edges = pd.concat([past.quantile(q) for q in (.25, .5, .75)], axis=1)
    valid = series.notna() & edges.notna().all(axis=1)
    # Ties go to the lower bucket; a constant history may populate fewer than four bins.
    codes = edges.lt(series, axis=0).sum(axis=1)
    out = pd.Series(np.asarray(labels, dtype=object)[codes], index=series.index)
    return out.where(valid)


def classify_zone(vol, disp, disp_high, vol_high=.80):
    if not np.isfinite([vol, disp, disp_high]).all():
        return "Uncalibrated"
    if vol >= vol_high:
        return "High volatility / high correlation distance" if disp >= disp_high else "High volatility / low correlation distance"
    return "Lower volatility / high correlation distance" if disp >= disp_high else "Lower volatility / low correlation distance"


def monte_carlo_p(null_statistics, observed):
    null = np.asarray(null_statistics, dtype=float)
    null = null[np.isfinite(null)]
    if not len(null) or not np.isfinite(observed):
        return np.nan
    return (1 + np.count_nonzero(np.abs(null) >= abs(observed))) / (len(null) + 1)


def _complete_time_sample(frame, columns):
    valid = frame[columns].notna().all(axis=1)
    positions = np.flatnonzero(valid.to_numpy())
    if len(positions) and np.any(np.diff(positions) != 1):
        raise ValueError("Internal missing dates would compress time in inference; resolve data coverage first.")
    return frame.loc[valid, columns]


def bucket_inference(frame, regime_col, return_col, target_regime, maxlags):
    """Chronological OLS contrast: bucket mean minus complement mean, with HAC."""
    import statsmodels.api as sm
    sample = _complete_time_sample(frame, [regime_col, return_col])
    indicator = sample[regime_col].eq(target_regime).astype(float)
    if indicator.nunique() < 2 or len(sample) < maxlags + 5:
        return {"hac_t_stat": np.nan, "coefficient": np.nan, "hac_available": False}
    X = sm.add_constant(indicator.rename("bucket_indicator"))
    fit = sm.OLS(sample[return_col].astype(float), X).fit(
        cov_type="HAC", cov_kwds={"maxlags": maxlags})
    return {"hac_t_stat": float(fit.tvalues["bucket_indicator"]),
            "coefficient": float(fit.params["bucket_indicator"]), "hac_available": True}


def label_null_test(frame, regime_col, return_col, target_regime, n_perm=1000,
                    random_seed=42, method="shuffle", min_shift=1):
    """Exploratory shuffle or circular-shift null; neither corrects model selection.

    Circular shifts preserve label run structure except at the wrap boundary and
    assume approximate stationarity. They are a sensitivity check, not a proof.
    """
    if n_perm < 1:
        raise ValueError("At least one resample is required.")
    sample = _complete_time_sample(frame, [regime_col, return_col])
    labels = sample[regime_col].eq(target_regime).to_numpy()
    values = sample[return_col].to_numpy(dtype=float)
    n, bucket_n = len(values), int(labels.sum())
    if bucket_n == 0 or bucket_n == n:
        return {"bucket_n": bucket_n, "observed_excess": np.nan, "empirical_two_sided_p_value": np.nan}
    mean = values.mean()
    observed = float(values[labels].mean() - mean)
    rng = np.random.default_rng(random_seed)
    if method == "circular_shift":
        choices = np.arange(max(1, min_shift), n - max(1, min_shift) + 1)
        if not len(choices):
            raise ValueError("Too few dates for requested circular-shift separation.")
        shifts = rng.choice(choices, size=n_perm, replace=True)
        masks = (np.roll(labels, shift) for shift in shifts)
    elif method == "shuffle":
        masks = (rng.permutation(labels) for _ in range(n_perm))
    else:
        raise ValueError(f"Unknown label-null method: {method}")
    null = [float(values[mask].mean() - mean) for mask in masks]
    return {"bucket_n": bucket_n, "observed_excess": observed,
            "empirical_two_sided_p_value": monte_carlo_p(null, observed)}
