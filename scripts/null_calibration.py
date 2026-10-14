"""Calibrate the label-null checks when regime labels carry no information.

Persistent three-state labels (mean run length ~25 days) are drawn independently of
i.i.d. daily returns, so every rejection is a false positive. Overlapping 21- and
63-day forward returns match the research design. Prints the share of replications
with p <= 0.10 for the shuffled-label and circular-shift nulls.

    python scripts/null_calibration.py [--reps 200] [--draws 200]
"""
import argparse
from pathlib import Path
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.vdcloud import forward_return, label_null_test  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reps", type=int, default=200)
    parser.add_argument("--draws", type=int, default=200)
    parser.add_argument("--days", type=int, default=2800)
    parser.add_argument("--seed", type=int, default=2026)
    args = parser.parse_args()
    rng = np.random.default_rng(args.seed)
    rows = []
    for rep in range(args.reps):
        states, state = [], rng.integers(3)
        while len(states) < args.days:
            states += [state] * int(rng.geometric(1 / 25))
            state = rng.integers(3)
        labels = np.array(["above", "inside", "below"])[np.array(states[:args.days])]
        returns = pd.Series(rng.normal(0, .01, args.days))
        for h in (21, 63):
            frame = pd.DataFrame({"regime": labels, "ret": forward_return(returns, h)}).iloc[:args.days - h]
            shuffle = label_null_test(frame, "regime", "ret", "above", args.draws, rep, "shuffle")
            circular = label_null_test(frame, "regime", "ret", "above", args.draws, rep, "circular_shift", h)
            rows.append((h, shuffle["empirical_two_sided_p_value"], circular["empirical_two_sided_p_value"]))
    result = pd.DataFrame(rows, columns=["horizon", "shuffle_p", "circular_p"])
    rates = result.groupby("horizon").agg(
        shuffle_false_positive_rate=("shuffle_p", lambda p: (p <= .10).mean()),
        circular_shift_false_positive_rate=("circular_p", lambda p: (p <= .10).mean()))
    print(f"Share of {args.reps} no-information replications with p <= 0.10 (nominal 0.10):")
    print(rates.to_string())


if __name__ == "__main__":
    main()
