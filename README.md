# V&D Cloud
### Volatility & Dispersion Regime Research

A clean-room quantitative research project testing whether volatility and cross-sectional dispersion can support an Ichimoku-inspired market-regime framework.

**The framework produced coherent descriptive regimes but did not demonstrate sufficiently stable predictive performance across markets and temporal holdouts.**

That's the finding. This repository documents how it was reached, and why the negative result is trustworthy.

---

## Research Question

Traditional Ichimoku cloud analysis asks "what regime is *price* in?" This project asks a different question: can the same regime-mapping grammar — applied to a synthetic **volatility-and-dispersion state variable** instead of price — identify meaningfully different market environments, and do those environments say anything honest about forward returns?

## Motivation

Regime-detection frameworks are easy to build and easy to oversell — a visually coherent chart is not the same as a validated signal. This project was designed from the outset to separate those two things: build the framework, then spend at least as much effort trying to break it as building it.

## Data

Public daily price data only, via `yfinance`:
- **Phase 1:** QQQ (2015–present)
- **Phase 2:** EFA (primary developed-market benchmark), URTH (broader context), and 13 developed-market country ETFs (equal-weight component universe)

No proprietary, employer, vendor-licensed, or personal brokerage data is used anywhere in this repository. See [Clean-Room Boundary](#clean-room-boundary) below.

## Method

1. **Components** — rolling realized volatility and cross-sectional dispersion, each normalized to a rolling Z-score.
2. **Signal construction** — multiple lenses built on the same components: additive, penalty-weighted, and (Phase 2 only) dispersion-only and volatility-only variants, so the research compares related-but-distinct views rather than a single model.
3. **Cloud geometry** — Ichimoku-style conversion/base/span windows applied to the V&D signal (not price), producing same-date regime labels: *above_cloud*, *below_cloud*, *inside_cloud*.
4. **Forward-return analysis** — mean forward returns conditioned on regime, at 5/10/21/63-day horizons.

## Validation

The validation is the actual research contribution here, not the signal itself:

- **Baseline challenge** — do simple, non-V&D classifiers (drawdown bucket, realized-vol quartile) explain the same structure?
- **HAC / Newey-West inference** — autocorrelation-robust significance testing, since forward-return windows overlap heavily.
- **Random-label permutation testing** — is the observed regime separation unusual versus a distribution built from randomly shuffled labels?
- **Persistence filters** — does requiring a regime to hold for 3–5 days before counting it produce cleaner results than same-date raw labels?
- **Chronological holdout** — in-sample (2015–2020) vs. holdout (2021–2026): do in-sample relationships survive on data the framework never saw?

A finding only counts as "supported" here if it clears more than one of these bars. Most don't.

## Results

| Test | Outcome |
|---|---|
| Internal diagnostic coherence | Supported |
| Descriptive regime separation | Partially supported |
| Advantage over simple baselines | Inconclusive |
| HAC robustness | Not supported |
| Permutation robustness | Mixed |
| Temporal holdout stability | Weak |
| Trade readiness | Rejected |

**The headline number:** in Phase 2, of the 13 hand-picked, best-looking regime buckets, roughly 10 looked *permutation-interesting* — but only **1 of 13** also cleared the HAC robustness bar, and that one case sits right at the boundary (|t| = 1.73 against a 1.65 threshold). A single near-boundary hit out of 13 buckets tested is roughly what multiple-comparison risk alone would predict by chance, so this does not amount to a validated finding — the most carefully selected, best-looking candidates from the entire build did not meaningfully survive a stacked robustness check. Phase 2B's temporal holdout reinforced the overall conclusion while softening it slightly: across 56 tested variant/regime/horizon cells, 31 sign-flipped between the in-sample and holdout periods, with 21 descriptive survivors — a meaningful minority holds up, but the majority still doesn't.

*(All figures and numbers on this page are generated directly by the notebooks in this repository — see [Repository Structure](#repository-structure) to reproduce them.)*

![Phase 1 cloud geometry on QQQ](figures/01_phase1_qqq_cloud_geometry.png)
*Same-date V&D cloud geometry on QQQ (Phase 1) — the structure is coherent and non-degenerate, which is a necessary but not sufficient condition for the framework to be useful.*

![Phase 2 evidence ladder](figures/03_phase2_evidence_ladder.png)
*The Phase 2 evidence ladder: each rung graded independently, from "structural coherence" (supported) through "statistical validation" (not established).*

![HAC robustness check](figures/04_phase2_hac_robustness_check.png)
*HAC t-stats for the 13 documented key buckets, regenerated from this repository's own notebook — only one (red) crosses the 1.65 threshold, and only barely.*

![Temporal holdout results](figures/05_phase2b_temporal_holdout.png)
*Illustrative examples of the largest in-sample-to-holdout sign flips (Phase 2B) — most tested cells behaved like this; a minority didn't.*

## Repository Structure

```
vd-cloud/
├── README.md
├── config.py                          # signal windows, universes, validation thresholds
├── requirements.txt
├── LICENSE
├── notebooks/
│   ├── 01_qqq_prototype_clean.ipynb              # Phase 1 — QQQ, components → regimes → validation
│   ├── 02_cross_market_validation_clean.ipynb    # Phase 2 — DM country ETF surface, G1-G9
│   └── 03_temporal_holdout_clean.ipynb           # Phase 2B — persistence filters + chronological holdout
├── figures/                            # generated charts referenced above
├── atlas/                              # Atlas Observatory — live monitoring dashboard (see Future Work)
│   ├── atlas_observatory.ipynb
│   ├── index.html                     # self-contained interactive dashboard
│   └── README.md
└── src/                                 # (reserved — reusable components not yet extracted)
```

These notebooks are curated retellings of a larger private research archive (Phase 1 alone spans ~250 working notebook cells across multiple validation rounds). The full archive, including additional robustness checks and an earlier single-ticker prototype, is preserved privately as the research record; this repository is the public exhibit.

## Limitations

Stated plainly, because a research project that hides its limitations isn't trustworthy:

- **No predictive proof.** Descriptive forward-return differences exist across regimes, but nothing here demonstrates out-of-sample predictive power.
- **No causal claim.** Regime labels correlate with different forward-return distributions in-sample; no causal mechanism was tested.
- **No out-of-sample robustness beyond the one holdout split tested.** The 2021–2026 holdout is a single realized historical path (post-pandemic recovery, the 2022 hiking cycle) that may itself be regime-specific.
- **No transaction-cost, slippage, or execution analysis.** Even a statistically robust descriptive edge could be erased by real-world costs — not examined here.
- **No strategy backtest, position sizing, or entry/exit logic exists anywhere in this repository, by design.**
- **Multiple-comparison risk.** Roughly a dozen buckets and several baselines were tested without a formal multiple-comparison correction (e.g., Bonferroni, Benjamini–Hochberg).
- **Country ETFs embed currency and macro exposure** beyond pure equity dispersion — the Phase 2 dispersion signal may partly reflect FX or macro regime shifts rather than pure equity-market structure.

## Future Work

- Rolling/expanding baseline thresholds (Phase 2's baseline challenge used full-sample quartiles, which wouldn't have been knowable in real time).
- Block-bootstrap or alternative HAC lag conventions, to test whether the "HAC-weak" finding is sensitive to the specific lag choice.
- Sample-period sensitivity — are findings stable across sub-periods, or driven by a small number of unusual regimes (2020, 2022)?
- **[Atlas Observatory](atlas/README.md)** — a companion single-ticker interactive dashboard (TQQQ vs. QQQ) extending this research into day-to-day monitoring (volatility, dispersion, and provisional market-state zones), built as a later, lighter-weight branch of this same research line. [Open the live dashboard](atlas/index.html).

## Methodology Note on AI-Assisted Development

Development used an AI-assisted research workflow for code scaffolding, debugging, documentation, and iterative hypothesis testing. Model definitions, validation design, interpretation, and final research judgments remained human-directed and independently reviewed — including two rounds of adversarial review specifically aimed at finding reasons the framework's apparent findings shouldn't be trusted.

## Clean-Room Boundary

This is an independently built personal research project using public market data only. It does not reference, rely on, or reproduce any proprietary employer systems, employer data, internal tools, or internal methodology of any kind.

## License

MIT — see [LICENSE](LICENSE).
