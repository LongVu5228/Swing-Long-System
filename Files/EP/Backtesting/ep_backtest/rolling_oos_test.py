"""
Rolling OOS test: repeats the train/test-split comparison from oos_test.py across
MULTIPLE historical cutoffs instead of just one, to check whether the "consistency-based
selection beats naive best-G-score selection" finding holds up generally or was an
artifact of exactly where the 2023 split happened to fall. User request 2026-08-31:
"is it possible/makes sense to do consistent 18 for OOS testing" -> yes, and do it
rolling, not just once.

Two selection methods compared at each split, using ONLY that split's train-period data:
- naive: the single strategy with the highest POOLED train-period G_score.
- consistency (maximin): the single strategy with the highest WORST-YEAR G_score within
  the train period (only years with >= --min-year-trades trades count) -- a rolling-
  window-friendly generalization of the original "Consistent Across Eras" idea (which
  used fixed era buckets; a rolling train window can be too short to contain multiple
  eras, so this uses per-YEAR granularity instead, filtered to years with enough volume
  to trust).

Both picks are then evaluated on that split's TEST-period data (never used for
selection). Reports each split's two picks and their test-period G_score/EV_R side by
side, plus which method won more splits overall.

Usage:
    python -m ep_backtest.rolling_oos_test
    python -m ep_backtest.rolling_oos_test --trades outputs/trades_v3b_screen2.parquet
"""

import argparse
import os

import pandas as pd

from . import config
from .run_batch import summarize
from .year_breakdown import _copy_strategy_desc_columns

# (train_end_year_inclusive, test_start_year, test_end_year_inclusive) -- test_end=None
# means "through the end of the data". Chosen to give each test window a few calendar
# years of data without cutting so early that the train window is nearly empty (2012-2016
# only has 144 events total across the whole project, per Files/EP/EP V5.xlsx).
DEFAULT_SPLITS = [
    (2017, 2018, 2019),
    (2019, 2020, 2021),
    (2021, 2022, 2023),
    (2023, 2024, None),
]


def _pooled_summary(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for strategy_id, group in trades.groupby("strategy_id"):
        summary = summarize(group)
        summary["strategy_id"] = strategy_id
        _copy_strategy_desc_columns(summary, group)
        rows.append(summary)
    df = pd.DataFrame(rows)
    ev_cap, pf_cap = 0.30, 2.0
    df["ev_score"] = (df["EV_R"] / ev_cap * 10).clip(0, 10)
    df["pf_score"] = (df["profit_factor"] / pf_cap * 10).clip(0, 10)
    df["G_score"] = 0.5 * df["ev_score"] + 0.5 * df["pf_score"]
    return df.drop(columns=["other_status_counts"])


def _maximin_pick(train_trades: pd.DataFrame, min_year_trades: int) -> str:
    """The strategy whose WORST qualifying year (>= min_year_trades triggered trades)
    has the highest G_score -- a strategy with no qualifying year at all is excluded
    (can't judge its worst case)."""
    year = pd.to_datetime(train_trades["event_date"]).dt.year
    yearly = train_trades.assign(year=year)

    rows = []
    for (yr, strategy_id), group in yearly.groupby(["year", "strategy_id"]):
        summary = summarize(group)
        if summary["triggered_trades"] < min_year_trades:
            continue
        rows.append({"year": yr, "strategy_id": strategy_id, "G_score":
                      0.5 * min((summary["EV_R"] / 0.30) * 10, 10) + 0.5 * min((summary["profit_factor"] / 2.0) * 10, 10)})
    if not rows:
        return None
    yearly_g = pd.DataFrame(rows)

    worst_per_strategy = yearly_g.groupby("strategy_id").agg(
        worst_g=("G_score", "min"), n_years=("year", "nunique")
    ).reset_index()
    if worst_per_strategy.empty:
        return None
    return worst_per_strategy.sort_values("worst_g", ascending=False).iloc[0]["strategy_id"]


def run_split(trades: pd.DataFrame, train_end: int, test_start: int, test_end, min_year_trades: int) -> dict:
    year = pd.to_datetime(trades["event_date"]).dt.year
    train_trades = trades[year <= train_end]
    test_mask = year >= test_start
    if test_end is not None:
        test_mask &= year <= test_end
    test_trades = trades[test_mask]

    train_summary = _pooled_summary(train_trades)
    test_summary = _pooled_summary(test_trades)
    test_lookup = test_summary.set_index("strategy_id")

    naive_id = train_summary.sort_values("G_score", ascending=False).iloc[0]["strategy_id"]
    maximin_id = _maximin_pick(train_trades, min_year_trades)

    def _test_stats(strategy_id):
        if strategy_id is None or strategy_id not in test_lookup.index:
            return None, None
        row = test_lookup.loc[strategy_id]
        return row["G_score"], row["EV_R"]

    naive_test_g, naive_test_ev = _test_stats(naive_id)
    maximin_test_g, maximin_test_ev = _test_stats(maximin_id)

    return {
        "train_end": train_end, "test_start": test_start, "test_end": test_end or "end",
        "naive_strategy": naive_id, "naive_test_G": naive_test_g, "naive_test_EV_R": naive_test_ev,
        "maximin_strategy": maximin_id, "maximin_test_G": maximin_test_g, "maximin_test_EV_R": maximin_test_ev,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", default=os.path.join(config.OUTPUTS_DIR, "trades_v3b_screen2.parquet"))
    parser.add_argument("--min-year-trades", type=int, default=20,
                         help="minimum trades in a calendar year for that year to count toward the maximin pick")
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    trades = pd.read_parquet(args.trades)
    results = [run_split(trades, *split, args.min_year_trades) for split in DEFAULT_SPLITS]
    result_df = pd.DataFrame(results)

    out_path = args.out or (os.path.splitext(args.trades)[0] + "_rolling_oos.csv")
    result_df.to_csv(out_path, index=False)
    print(f"wrote {len(result_df)} split rows to {out_path}\n")

    cols = ["train_end", "test_start", "test_end", "naive_test_G", "naive_test_EV_R",
            "maximin_test_G", "maximin_test_EV_R"]
    print(result_df[cols].to_string(index=False))

    valid = result_df.dropna(subset=["naive_test_G", "maximin_test_G"])
    maximin_wins = (valid["maximin_test_G"] > valid["naive_test_G"]).sum()
    print(f"\nmaximin (consistency) beat naive (best-pooled-G-score) in {maximin_wins} of {len(valid)} splits")
    print(f"avg naive test EV_R: {valid['naive_test_EV_R'].mean():.4f}")
    print(f"avg maximin test EV_R: {valid['maximin_test_EV_R'].mean():.4f}")


if __name__ == "__main__":
    main()
