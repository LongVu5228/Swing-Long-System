"""
Partial out-of-sample test: re-ranks the ALREADY-SCREENED strategies in a trades file
using only a TRAIN period, then checks how the train-period winner (and the ranking as a
whole) performs on a TEST period it never influenced. User request 2026-08-31: "oos test
please."

This is deliberately a PARTIAL OOS test, not the full version -- it only re-validates the
FINAL "pick a winner by ranking" step among strategies that were already narrowed down
using the FULL 2012-2026 dataset at every earlier stage (Stage 0's V1 filter, screen1's
entry/stop/trail ranking -- see run_batch_v3b.py's module docstring). It does NOT test
whether that earlier narrowing itself overfits -- that would require re-running the whole
screen1->screen2 pipeline restricted to train-only data (several more hours of compute,
a separate, more expensive test). It still directly tests the single most common source
of curve-fitting in this kind of search: does "best in a large combo search" predict
"best going forward," or is picking the top G-score effectively noise?

Default split: train = 2012-2022 (eras 01-05), test = 2023-2026+ (eras 06-07) -- matches
the standard "hold out the most recent few years" OOS convention. The 2026+ portion of
the test period is a known-incomplete year (STILL_OPEN_AT_DATA_END right-censoring, see
trade_metrics.py / run_batch.summarize) -- worth remembering when reading test-period
results, same caveat as everywhere else this project uses 2026+.

Usage:
    python -m ep_backtest.oos_test
    python -m ep_backtest.oos_test --trades outputs/trades_v3b_screen2.parquet --split-year 2023
"""

import argparse
import os

import pandas as pd

from . import config
from .run_batch import summarize
from .year_breakdown import _copy_strategy_desc_columns


def _summarize_period(trades: pd.DataFrame, prefix: str) -> pd.DataFrame:
    rows = []
    for strategy_id, group in trades.groupby("strategy_id"):
        summary = summarize(group)
        summary["strategy_id"] = strategy_id
        _copy_strategy_desc_columns(summary, group)
        rows.append(summary)

    df = pd.DataFrame(rows)
    ev_cap, pf_cap = 0.30, 2.0  # Section 7 -- same G Score caps as every other summary
    df["ev_score"] = (df["EV_R"] / ev_cap * 10).clip(0, 10)
    df["pf_score"] = (df["profit_factor"] / pf_cap * 10).clip(0, 10)
    df["G_score"] = 0.5 * df["ev_score"] + 0.5 * df["pf_score"]
    df = df.drop(columns=["other_status_counts"])
    rename = {c: f"{prefix}_{c}" for c in df.columns if c not in
              ("strategy_id", "entry_type", "stop_type", "trail_type", "sell_style", "target_ladder", "core_pct")}
    return df.rename(columns=rename)


def run_oos_test(trades: pd.DataFrame, split_year: int) -> pd.DataFrame:
    year = pd.to_datetime(trades["event_date"]).dt.year
    train_trades = trades[year < split_year]
    test_trades = trades[year >= split_year]

    train_summary = _summarize_period(train_trades, "train")
    test_summary = _summarize_period(test_trades, "test")

    desc_cols = ["entry_type", "stop_type", "trail_type", "sell_style", "target_ladder", "core_pct"]
    merged = train_summary.merge(test_summary, on=["strategy_id"] + desc_cols, how="outer")

    lead = ["strategy_id"] + desc_cols + [
        "train_triggered_trades", "train_win_rate", "train_profit_factor", "train_EV_R", "train_total_R",
        "train_G_score",
        "test_triggered_trades", "test_win_rate", "test_profit_factor", "test_EV_R", "test_total_R", "test_G_score",
    ]
    other = [c for c in merged.columns if c not in lead]
    return merged[lead + other]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", default=os.path.join(config.OUTPUTS_DIR, "trades_v3b_screen2.parquet"))
    parser.add_argument("--split-year", type=int, default=2023,
                         help="train = event years before this, test = this year onward")
    parser.add_argument("--out", default=None, help="defaults to <trades>_oos.csv")
    parser.add_argument("--min-test-trades", type=int, default=15,
                         help="minimum test-period trades for a strategy to be shown in the top-N tables")
    args = parser.parse_args()

    trades = pd.read_parquet(args.trades)
    result = run_oos_test(trades, args.split_year)

    out_path = args.out or (os.path.splitext(args.trades)[0] + "_oos.csv")
    result.to_csv(out_path, index=False)
    print(f"wrote {len(result)} strategy rows to {out_path}")

    valid = result.dropna(subset=["train_G_score", "test_G_score"])
    valid = valid[valid["test_triggered_trades"] >= args.min_test_trades]
    # Spearman = Pearson correlation of the ranks -- computed by hand rather than
    # pandas' method="spearman" (which imports scipy, not installed in this venv).
    corr = valid["train_G_score"].rank().corr(valid["test_G_score"].rank())
    print(f"\nSpearman rank correlation (train G_score vs test G_score), n={len(valid)}: {corr:.3f}")
    print("(near 0 = train ranking has no OOS predictive power; near 1 = train winners stay test winners)")

    cols = ["strategy_id", "train_triggered_trades", "train_EV_R", "train_G_score",
            "test_triggered_trades", "test_EV_R", "test_G_score"]
    print(f"\n--- Top 10 by TRAIN G_score (min {args.min_test_trades} test trades) -- does the winner hold up OOS? ---")
    print(valid.sort_values("train_G_score", ascending=False).head(10)[cols].to_string(index=False))

    print(f"\n--- Top 10 by TEST G_score, for comparison -- were these even ranked highly in train? ---")
    print(valid.sort_values("test_G_score", ascending=False).head(10)[cols].to_string(index=False))


if __name__ == "__main__":
    main()
