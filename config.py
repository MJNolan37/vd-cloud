# =============================================================================
# V&D Cloud — Configuration
# =============================================================================
# Clean-room boundary: this project uses public market data only (via yfinance).
# It does not reference, rely on, or reproduce any proprietary employer systems,
# employer data, internal tools, or internal methodology of any kind.
# =============================================================================

# --- Date Range --------------------------------------------------------------
# Spans multiple distinct market regimes (2015 correction, 2018 Q4, 2020 COVID,
# 2022 rate-hike bear, later volatility episodes) while keeping the dataset
# manageable.

START_DATE = "2015-01-01"
# Pinned to match the documented research period (Phase 2 synthesis run 2026-06-07;
# Phase 2B holdout documented through 2026-05-29). This is a fixed historical study,
# not a live-updating monitor -- see Atlas Observatory for the live/current companion
# piece. yfinance's `end` is exclusive, so this captures through 2026-05-29 inclusive.
END_DATE = "2026-05-30"


# --- Universes -----------------------------------------------------------------

# Phase 1 (QQQ prototype)
BENCHMARK_TICKER = "QQQ"
OVERLAY_TICKER = "TQQQ"

# Phase 2 (developed-market country ETF surface)
DM_PRIMARY_BENCHMARK = "EFA"   # primary target
DM_CONTEXT_BENCHMARK = "URTH"  # broader context only, not a component-aligned target
DM_COUNTRY_ETF_UNIVERSE = [
    "EWJ", "EWU", "EWG", "EWQ", "EWI", "EWP", "EWN", "EWD",
    "EWL", "EWC", "EWA", "EWO", "EWK",
]


# --- Signal Parameters -------------------------------------------------------
# All windows are in trading days unless noted. These are the values used
# throughout the research, not re-optimized per universe.

Z_WINDOW = 126          # Rolling Z-score lookback (~6 months)
VOL_WINDOW = 21         # Realized volatility lookback (~1 month)
SMOOTH_WINDOW = 5       # Signal smoothing (5-day simple moving average)

# Ichimoku-style cloud windows, applied to the V&D signal rather than price
CONVERSION_WINDOW = 9   # Fast midpoint (Tenkan-sen analog)
BASE_WINDOW = 26        # Medium midpoint (Kijun-sen analog)
SPAN_B_WINDOW = 52      # Slow midpoint (Senkou Span B analog)

# Persistence-confirmation windows tested in Phase 2B
PERSISTENCE_WINDOWS = [3, 5]  # trading days a regime must hold to be "confirmed"


# --- Validation Parameters ---------------------------------------------------

FORWARD_HORIZONS = [5, 10, 21, 63]   # Forward return windows in trading days
MIN_BUCKET_N = 30                    # Minimum sample size for a regime bucket to be reported
HAC_TSTAT_THRESHOLD = 1.65           # Heuristic significance bar used throughout
PERMUTATION_TWO_SIDED_P = 0.10       # Random-label permutation interest threshold

# Chronological holdout split used in Phase 2B
IN_SAMPLE_END = "2020-12-31"
HOLDOUT_START = "2021-01-01"
