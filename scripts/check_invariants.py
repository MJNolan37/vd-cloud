"""Check data-handling invariants on the cached market data (offline only).

Run after `python scripts/reproduce.py` has downloaded the data:
    python scripts/check_invariants.py
Writes results/invariant_checks.json and exits nonzero if any check fails.
"""
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def run_notebook(name):
    nb = json.loads((ROOT / "notebooks" / f"{name}.ipynb").read_text(encoding="utf-8"))
    namespace = {"__name__": "__main__"}
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            exec(compile("".join(cell["source"]), f"{name}:cell{i}", "exec"), namespace)
    return namespace


def main():
    os.environ.update(VD_CLOUD_OFFLINE="1", VD_CLOUD_REFRESH="0", VD_CLOUD_BATCH="1")
    os.chdir(ROOT)
    import matplotlib
    matplotlib.use("Agg")
    import pandas as pd
    import config
    checks = {}

    for name in ("01_qqq_prototype_clean", "03_temporal_holdout_clean"):
        ns = run_notebook(name)
        prices, returns = ns["prices"], ns["returns"]
        # 1. Missing prices never produce a return on that date or the next observed date.
        should_be_missing = prices.isna() | prices.shift(1).isna()
        filled = int((should_be_missing & returns.notna()).sum().sum())
        checks[f"{name}: missing price cells"] = int(prices.isna().sum().sum())
        checks[f"{name}: returns filled across missing prices (must be 0)"] = filled
        # 3. Every labeled date has both spans (and the signal) available.
        clouds = ({"additive": ns["additive_cloud"], "penalty": ns["penalty_cloud"]} if "additive_cloud" in ns
                  else {k: ns["build_cloud"](s, config.CONVERSION_WINDOW, config.BASE_WINDOW, config.SPAN_B_WINDOW)
                        for k, s in ns["signal_variants"].items()})
        for variant, cloud in clouds.items():
            labeled = cloud["regime_state"].notna()
            incomplete = labeled & cloud[["signal", "span_a", "span_b"]].isna().any(axis=1)
            checks[f"{name}: {variant} labels lacking a span (must be 0)"] = int(incomplete.sum())
            checks[f"{name}: {variant} first labeled date"] = str(cloud.index[labeled.to_numpy()].min().date())

    # 2. No earlier-period outcome ends after the split; later-period outcomes are untouched.
    ns = run_notebook("03_temporal_holdout_clean")
    purged, end = ns["efa_fwd"], pd.Timestamp(config.IN_SAMPLE_END)
    unpurged = pd.DataFrame({f"fwd_{h}d": ns["forward_return"](ns["efa_returns"], h) for h in config.FORWARD_HORIZONS})
    positions = pd.Series(range(len(purged)), index=purged.index)
    for h in config.FORWARD_HORIZONS:
        col = f"fwd_{h}d"
        endpoint_pos = positions + h
        crossing = (purged.index <= end) & (endpoint_pos.to_numpy() < len(purged))
        crossing &= purged.index[endpoint_pos.clip(upper=len(purged) - 1)] > end
        checks[f"purge {col}: crossing outcomes still present (must be 0)"] = int(purged.loc[crossing, col].notna().sum())
        checks[f"purge {col}: outcomes removed"] = int((unpurged[col].notna() & purged[col].isna()).sum())
        later = purged.index > end
        checks[f"purge {col}: later-period outcomes altered (must be 0)"] = int(
            (~purged.loc[later, col].fillna(-9e9).eq(unpurged.loc[later, col].fillna(-9e9))).sum())

    failures = [k for k, v in checks.items() if "(must be 0)" in k and v != 0]
    out = {"status": "pass" if not failures else "fail", "failures": failures, "checks": checks}
    (ROOT / "results" / "invariant_checks.json").write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2))
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
