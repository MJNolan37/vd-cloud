"""Execute revised notebooks, export result tables and regenerate research figures."""
import argparse
import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Tables exported from each notebook's namespace. Loop temporaries are excluded on purpose.
EXPORTS = {
    "01_qqq_prototype_clean": ["validation_summary", "stability_summary", "hac_summary",
                               "permutation_summary"],
    "02_cross_market_validation_clean": ["corr_matrix", "regime_forward_return_summary",
                                         "baseline_forward_return_summary",
                                         "baseline_spread_by_classifier", "vd_spread_21d",
                                         "robustness_verdict"],
    "03_temporal_holdout_clean": ["churn_diagnostics", "persistence_forward_return_summary",
                                  "regime_period_forward_return_summary",
                                  "in_sample_vs_holdout_consistency", "preference_counts"],
    "atlas_observatory": ["metrics"],
}
COVERAGE = ("valid_counts", "available_count")
FIGURES = ["01_phase1_qqq_cloud_geometry.png", "02_phase1_regime_radar_2y.png",
           "03_phase2_evidence_ladder.png", "04_phase2_hac_robustness_check.png",
           "05_phase2b_temporal_holdout.png"]


def execute(path):
    import pandas as pd
    nb = json.loads(path.read_text(encoding="utf-8"))
    namespace = {"__name__": "__main__"}
    for i, cell in enumerate(nb["cells"]):
        if cell["cell_type"] == "code":
            print(f"{path.name}: cell {i}", flush=True)
            exec(compile("".join(cell["source"]), f"{path.name}:cell{i}", "exec"), namespace)
    output = ROOT / "results" / path.stem
    output.mkdir(parents=True, exist_ok=True)
    for name in EXPORTS.get(path.stem, []):
        value = namespace[name]
        if isinstance(value, dict):
            value = pd.Series(value, name="count")
        if isinstance(value, pd.Series):
            value.to_csv(output / f"{name}.csv", index_label=value.index.name or "key")
        elif name in ("corr_matrix", "metrics"):
            value.to_csv(output / f"{name}.csv", index_label="variant" if name == "corr_matrix" else "date")
        else:
            value.to_csv(output / f"{name}.csv", index=False)
    for name in COVERAGE:
        if name in namespace:
            namespace[name].rename("valid_component_return_count").to_csv(
                output / "daily_component_coverage.csv", index_label="date")
    return namespace


def figures(phase1, phase2, phase3):
    import matplotlib.pyplot as plt
    import numpy as np
    import pandas as pd
    directory = ROOT / "figures"
    directory.mkdir(exist_ok=True)
    frame = phase1["additive_cloud"]
    for filename, recent in [(FIGURES[0], False), (FIGURES[1], True)]:
        plot = frame.loc[frame.index >= frame.index.max() - pd.DateOffset(years=2)] if recent else frame
        fig, ax = plt.subplots(figsize=(12, 5))
        ax.fill_between(plot.index, plot.cloud_bottom, plot.cloud_top, alpha=.25,
                        label="Cloud band (Span A to Span B)")
        ax.plot(plot.index, plot.signal, linewidth=1, label="Additive V&D signal")
        ax.axhline(0, color="gray", linewidth=.6, linestyle=":")
        ax.set_ylabel("Signal (weighted rolling Z-scores)")
        ax.set_title("QQQ additive V&D signal and same-date cloud"
                     + (" — last two years" if recent else f" — {plot.index.min():%Y-%m} to {plot.index.max():%Y-%m}"))
        ax.legend(loc="upper left"); fig.tight_layout(); fig.savefig(directory / filename, dpi=160); plt.close(fig)

    table = phase2["robustness_verdict"]
    t_threshold = phase2["HAC_T_STAT_THRESHOLD"]
    fig, ax = plt.subplots(figsize=(12, 5))
    labels = table.variant + " / " + table.regime + " / " + table.horizon.astype(str) + "d"
    crosses = table.hac_t_stat.abs() >= t_threshold
    ax.bar(np.arange(len(table)), table.hac_t_stat.abs(),
           color=np.where(crosses, "tab:red", "tab:blue"))
    ax.axhline(t_threshold, color="red", linestyle="--", label=f"Heuristic threshold |t| = {t_threshold}")
    ax.set_xticks(np.arange(len(table)), labels, rotation=70, ha="right")
    ax.set_ylabel("Absolute HAC t-statistic")
    ax.set_title("Phase 2: HAC t-statistics for the 13 previously selected buckets (red = crosses threshold)")
    ax.legend(); fig.tight_layout()
    fig.savefig(directory / FIGURES[3], dpi=160); plt.close(fig)

    summary_counts = headline_counts(table, phase2["PERMUTATION_P_THRESHOLD"], t_threshold,
                                     phase2["MIN_BUCKET_N"])
    p = phase2["PERMUTATION_P_THRESHOLD"]
    fig, ax = plt.subplots(figsize=(9, 4))
    names = [f"Shuffled-label p ≤ {p}", f"HAC |t| ≥ {t_threshold}", f"Circular-shift p ≤ {p}",
             "Shuffled-label and HAC"]
    counts = [summary_counts[k] for k in ("shuffle_interesting", "hac_interesting",
                                          "circular_shift_interesting", "shuffle_and_hac")]
    ax.barh(names, counts)
    for y, value in enumerate(counts):
        ax.text(value + .1, y, str(value), va="center")
    ax.set_xlim(0, len(table)); ax.invert_yaxis()
    ax.set_xlabel(f"Buckets crossing each threshold (of {len(table)} selected)")
    ax.set_title("Phase 2 exploratory checks; selection and multiplicity uncorrected")
    fig.tight_layout(); fig.savefig(directory / FIGURES[2], dpi=160); plt.close(fig)

    consistency = phase3["in_sample_vs_holdout_consistency"]
    named = consistency.loc[consistency.regime != "unconfirmed"]
    order = ["consistent", "directionally_consistent_but_weaker", "sign_flipped", "inconclusive", "low_n"]
    plot = (named.groupby(["consistency_flag", "regime_source"]).size().unstack(fill_value=0)
            .reindex(order, fill_value=0))
    fig, ax = plt.subplots(figsize=(10, 4))
    plot.plot.bar(ax=ax, rot=20)
    ax.set_title(f"Phase 2B chronological comparison — {len(named)} named-regime cells (21d and 63d)")
    ax.set_ylabel("Cells (not independent tests)"); ax.set_xlabel("")
    ax.legend(title="Labels"); fig.tight_layout()
    fig.savefig(directory / FIGURES[4], dpi=160); plt.close(fig)

    def records(frame):
        return json.loads(frame.to_json(orient="records"))

    summary = {"selected_buckets": len(table), **summary_counts,
               "phase2_buckets": records(table),
               "holdout_named_regimes": {k: int(v) for k, v in named.consistency_flag.value_counts().items()},
               "holdout_named_regimes_by_source": {src: {k: int(v) for k, v in grp.consistency_flag.value_counts().items()}
                                                   for src, grp in named.groupby("regime_source")},
               "holdout_unconfirmed": {k: int(v) for k, v in consistency.loc[consistency.regime == "unconfirmed"].consistency_flag.value_counts().items()},
               "persistence_preference_counts": {k: int(v) for k, v in phase3["preference_counts"].items()},
               "baseline_spread_21d": {k: float(v) for k, v in phase2["baseline_spread_by_classifier"].items()},
               "vd_spread_21d": {k: float(v) for k, v in phase2["vd_spread_21d"].items()}}
    (ROOT / "results" / "headline_summary.json").write_text(json.dumps(summary, indent=2)+"\n", encoding="utf-8")


def headline_counts(table, p_threshold, t_threshold, min_bucket_n):
    enough = table.bucket_n >= min_bucket_n
    shuffle = enough & (table.empirical_p <= p_threshold)
    hac = enough & (table.hac_t_stat.abs() >= t_threshold)
    circular = enough & (table.circular_shift_p <= p_threshold)
    return {"shuffle_interesting": int(shuffle.sum()), "hac_interesting": int(hac.sum()),
            "circular_shift_interesting": int(circular.sum()), "shuffle_and_hac": int((shuffle & hac).sum())}


def git_provenance():
    # A downloaded source ZIP may have no Git metadata; source hashes still identify it.
    try:
        command = ["git", "-C", str(ROOT)]
        top = subprocess.check_output(command + ["rev-parse", "--show-toplevel"], text=True, stderr=subprocess.DEVNULL).strip()
        if Path(top).resolve() != ROOT:
            return {"git_commit": None, "git_dirty": None}
        return {"git_commit": subprocess.check_output(command + ["rev-parse", "HEAD"], text=True).strip(),
                "git_dirty": bool(subprocess.check_output(command + ["status", "--porcelain"], text=True).strip())}
    except (OSError, subprocess.CalledProcessError):
        return {"git_commit": None, "git_dirty": None}


def installed_distributions():
    """Name==version for every installed distribution; works without pip (e.g. uv venvs)."""
    found = {}
    for dist in importlib.metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            found[name.lower()] = f"{name}=={dist.version}"
    return [found[k] for k in sorted(found)]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--offline", action="store_true", help="Require hash-verified local cached downloads")
    modes.add_argument("--refresh", action="store_true", help="Replace local downloads with new Yahoo responses")
    parser.add_argument("--atlas", action="store_true", help="Also regenerate the current-year Atlas HTML")
    args = parser.parse_args()
    os.environ["VD_CLOUD_OFFLINE"] = "1" if args.offline else "0"
    os.environ["VD_CLOUD_REFRESH"] = "1" if args.refresh else "0"
    os.environ["VD_CLOUD_BATCH"] = "1"
    os.chdir(ROOT)
    import matplotlib
    matplotlib.use("Agg")
    from src.repro import DATA_RECORDS
    results = ROOT / "results"
    results.mkdir(exist_ok=True)
    manifest_path = results / "run_manifest.json"
    manifest = {"status": "running", "mode": "offline" if args.offline else "refresh" if args.refresh else "cache-or-download",
                "atlas": args.atlas, "python": sys.version, "platform": platform.platform(),
                "started_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                **git_provenance(),
                "packages": {name: importlib.metadata.version(name) for name in
                             ["numpy", "pandas", "scipy", "matplotlib", "statsmodels", "yfinance", "plotly"]}}
    sources = [ROOT / "config.py", *ROOT.glob("src/*.py"), *ROOT.glob("scripts/*.py"),
               *ROOT.glob("notebooks/*.ipynb"), *ROOT.glob("atlas/*.ipynb")]
    manifest["source_sha256"] = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(sources)}
    manifest_path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")
    try:
        names = ["01_qqq_prototype_clean", "02_cross_market_validation_clean", "03_temporal_holdout_clean"]
        runs = [execute(ROOT/"notebooks"/f"{name}.ipynb") for name in names]
        figures(*runs)
        if args.atlas:
            execute(ROOT/"atlas"/"atlas_observatory.ipynb")
        # Record the exact environment only after it has completed the whole run.
        (results/"requirements-run.txt").write_text("\n".join(installed_distributions())+"\n", encoding="utf-8")
        outputs = [*sorted(results.rglob("*.csv")), results/"headline_summary.json", results/"requirements-run.txt",
                   *[ROOT/"figures"/f for f in FIGURES]]
        if args.atlas:
            outputs.append(ROOT/"atlas"/"index.html")
        manifest["output_sha256"] = {p.relative_to(ROOT).as_posix(): sha256(p) for p in outputs}
        manifest["status"] = "complete"
    except Exception as exc:
        manifest["status"] = "failed"; manifest["error"] = repr(exc)
        raise
    finally:
        manifest["finished_at_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        manifest["datasets"] = DATA_RECORDS
        manifest_path.write_text(json.dumps(manifest, indent=2)+"\n", encoding="utf-8")


if __name__ == "__main__":
    main()
