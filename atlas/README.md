# Atlas Observatory v0.1

An interactive, single-ticker volatility & dispersion monitoring dashboard (TQQQ vs. QQQ) — a lighter-weight, later branch of the [V&D Cloud](../README.md) research, extending it from a fixed research question into day-to-day instrumentation.

**[Open the live dashboard](index.html)** — a self-contained HTML file, no install or server required.

## What it shows

- Normalized price, 20-day realized volatility, and a simple dispersion proxy (`1 - rolling correlation vs. QQQ`)
- A volatility × dispersion heatmap of how often TQQQ has spent time in each combined state
- A "state path" scatter tracing volatility/dispersion through time
- Rolling volume
- A provisional rule-based zone label (`Turbulent / Fragmented`, `Reactive`, `Unstable Transition`, `Balanced / Risk-On`)

**These zone labels are explicitly provisional and rule-based — not a validated regime model, and not a trading signal.** They exist to demonstrate the jump from "research finding" to "usable monitoring instrument," not to make a forecasting claim.

**Calibration note.** Dispersion is bucketed by **quartile of the observed pair's own distribution**, not a fixed absolute threshold — applied consistently to the heatmap buckets and the zone classifier. TQQQ tracks QQQ so tightly via daily-reset leverage that its raw dispersion sits orders of magnitude below what a fixed universal cutoff would assume, which would otherwise make three of the four dispersion buckets — and two of the four zones — permanently unreachable. "High dispersion" here means high relative to how this specific pair has behaved recently, not a fixed absolute level.

## Reproducing it

Unlike the main V&D Cloud notebooks (which are pinned to a fixed historical analysis window on purpose — see the [main README](../README.md#clean-room-boundary)), this notebook is meant to be **re-run for a current read**: `start_date` is year-to-date and `end_date` defaults to latest available. Run `atlas_observatory.ipynb` top-to-bottom to regenerate `index.html` with today's data.

## Clean-Room Boundary

Public market data only, via `yfinance`. No proprietary employer systems, employer data, internal tools, or internal methodology are referenced or reproduced anywhere in this notebook.
