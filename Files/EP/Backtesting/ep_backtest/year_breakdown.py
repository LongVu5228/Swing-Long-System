"""
Year-by-year breakdown: slice any engine's trade-level parquet output by event_date's
year and report top strategies per year (era/robustness view), not just the aggregate
across all 2012-2026 years -- user request 2026-08-30, "have those strategies done by
year, to see the top strats by year."

Works against any of the four engines' trade-level output (trades_all_72.parquet,
trades_v2.parquet, trades_v3.parquet, trades_v3b.parquet, trades_v3b_broad.parquet) --
they all share event_date, strategy_id, status, realized_R, holding_days, and (as of
2026-08-31) max_favorable_R/exit_efficiency, which is all summarize() needs.

Usage:
    python -m ep_backtest.year_breakdown outputs/trades_v3b.parquet --top 5
    python -m ep_backtest.year_breakdown outputs/trades_v3b_broad.parquet --top 10 --min-trades 15
"""

import argparse
import os

import pandas as pd

from . import config
from .run_batch import summarize


def add_year(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    trades["year"] = pd.to_datetime(trades["event_date"]).dt.year
    return trades


def summarize_by_year(trades: pd.DataFrame) -> pd.DataFrame:
    trades = add_year(trades)
    summaries = []
    for (year, strategy_id), group in trades.groupby(["year", "strategy_id"]):
        summary = summarize(group)
        summary["year"] = int(year)
        summary["strategy_id"] = strategy_id
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)
    ev_cap, pf_cap = 0.30, 2.0  # Section 7 -- old G Score caps, same as every other summary
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    return summary_df


def top_n_per_year(summary_df: pd.DataFrame, n: int = 5, min_trades: int = 10,
                    sort_by: str = "G_score") -> pd.DataFrame:
    """min_trades filters out (year, strategy) cells too thin to trust -- with ~2,358
    events split across a strategy grid and ~14 calendar years, a single-year cell can
    easily have single-digit N; a "best strategy of the year" built on 3 trades is noise,
    not signal (see [[feedback_verify_against_real_data]])."""
    df = summary_df[summary_df["triggered_trades"] >= min_trades]
    return (df.sort_values(["year", sort_by], ascending=[True, False])
              .groupby("year", group_keys=False).head(n).reset_index(drop=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trades_path", help="path to a trades_*.parquet file, e.g. outputs/trades_v3b.parquet")
    parser.add_argument("--top", type=int, default=5, help="strategies to show per year")
    parser.add_argument("--min-trades", type=int, default=10,
                         help="minimum triggered trades in a (year, strategy) cell to be ranked")
    args = parser.parse_args()

    trades = pd.read_parquet(args.trades_path)
    summary_df = summarize_by_year(trades)

    out_path = os.path.splitext(args.trades_path)[0] + "_by_year.csv"
    summary_df.to_csv(out_path, index=False)
    print(f"wrote {len(summary_df)} (year, strategy) rows to {out_path}")

    top = top_n_per_year(summary_df, n=args.top, min_trades=args.min_trades)
    cols = ["year", "strategy_id", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R", "G_score"]
    print(f"\n--- Top {args.top} strategies per year (min {args.min_trades} triggered trades) ---")
    print(top[cols].to_string(index=False))


if __name__ == "__main__":
    main()
