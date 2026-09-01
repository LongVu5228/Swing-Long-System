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


# Era boundaries (user request 2026-08-31: "by era instead of just 15 year tabs").
# Starts from EP V5's own `era` column (Section: event metadata) -- 01|2012-2016,
# 02|2017-2019, 03|2020, 04|2021-2022, 05|2023-2025, 06|2026+ -- but SPLITS the
# provider's merged "2021-2022" bucket into 2021 and 2022 separately. That merge would
# blur exactly the question era analysis exists to answer: does a strategy survive the
# 2022 bear/chop market on its own, or does its edge come entirely from the 2020-2021
# COVID-momentum rally. Keeping 2020 and 2021 as their own eras (rather than combining
# them into one "COVID era") is deliberate for the same reason -- 2020 (crash + V-shaped
# recovery) and 2021 (already-elevated momentum/meme mania) are different enough regimes
# to want separated, not because the provider's boundary was wrong, just coarser than
# what this specific robustness question needs.
_ERA_BIN_EDGES = [2012, 2017, 2020, 2021, 2022, 2023, 2026, 9999]
_ERA_LABELS = ["01 | 2012-2016", "02 | 2017-2019", "03 | 2020", "04 | 2021",
               "05 | 2022", "06 | 2023-2025", "07 | 2026+"]


def add_era(trades: pd.DataFrame) -> pd.DataFrame:
    trades = trades.copy()
    year = pd.to_datetime(trades["event_date"]).dt.year
    trades["era"] = pd.cut(year, bins=_ERA_BIN_EDGES, labels=_ERA_LABELS, right=False,
                            include_lowest=True).astype(str)
    return trades


# Strategy-defining columns to carry through into every (year/era, strategy) row --
# summarize() itself only computes performance stats, it never copies these over, so
# without this the year/era tables ended up with entry_type/stop_type/etc. blank while
# the plain aggregate summaries (run_batch.summarize_all_v3b and friends, which DO copy
# these) had them filled in -- confirmed as a real bug 2026-08-31 once the two were
# unioned into one table and the gap became visible. Different engines expose different
# subsets of these (V1 only has entry_type/stop_type, V3b has all of them) -- checked
# for presence rather than assumed, so this one function works for every engine's output
# per this module's own "works against any of the four engines" contract.
_STRATEGY_DESC_COLUMNS = ["entry_type", "stop_type", "trail_type", "sell_style", "target_ladder", "core_pct",
                          "target_pct"]


def _copy_strategy_desc_columns(summary: dict, group: pd.DataFrame) -> None:
    for col in _STRATEGY_DESC_COLUMNS:
        if col in group.columns:
            summary[col] = group[col].iloc[0]


def summarize_by_year(trades: pd.DataFrame) -> pd.DataFrame:
    trades = add_year(trades)
    summaries = []
    for (year, strategy_id), group in trades.groupby(["year", "strategy_id"]):
        summary = summarize(group)
        summary["year"] = int(year)
        summary["strategy_id"] = strategy_id
        _copy_strategy_desc_columns(summary, group)
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)
    ev_cap, pf_cap = 0.30, 2.0  # Section 7 -- old G Score caps, same as every other summary
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    return summary_df


def summarize_by_era(trades: pd.DataFrame) -> pd.DataFrame:
    trades = add_era(trades)
    summaries = []
    for (era, strategy_id), group in trades.groupby(["era", "strategy_id"]):
        summary = summarize(group)
        summary["era"] = era
        summary["strategy_id"] = strategy_id
        _copy_strategy_desc_columns(summary, group)
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)
    ev_cap, pf_cap = 0.30, 2.0
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    return summary_df.sort_values(["era", "G_score"], ascending=[True, False]).reset_index(drop=True)


def summarize_by_chart_pattern(trades: pd.DataFrame) -> pd.DataFrame:
    """chart_pattern is already a column on every trade row (run_batch.event_meta_from_row)
    -- no bucketing/binning needed here, unlike year/era. User request 2026-08-31: "how
    about by chart pattern."""
    summaries = []
    for (pattern, strategy_id), group in trades.groupby(["chart_pattern", "strategy_id"]):
        summary = summarize(group)
        summary["chart_pattern"] = pattern
        summary["strategy_id"] = strategy_id
        _copy_strategy_desc_columns(summary, group)
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)
    ev_cap, pf_cap = 0.30, 2.0
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    return summary_df.sort_values(["chart_pattern", "G_score"], ascending=[True, False]).reset_index(drop=True)


def summarize_by_spy_trend(trades: pd.DataFrame) -> pd.DataFrame:
    """spy_trend_color is already a column on every trade row (run_batch.event_meta_from_row)
    -- the Chillax Moving Average SPY trend classification (Green/Light Green/Yellow/
    Downtrend), computed once for SPY and joined to every event by date regardless of
    ticker. User request 2026-08-31: "do the strats perform better on days where SPY is
    uptrending... testing chillaxmax's script accuracy." """
    summaries = []
    for (trend, strategy_id), group in trades.groupby(["spy_trend_color", "strategy_id"]):
        summary = summarize(group)
        summary["spy_trend_color"] = trend
        summary["strategy_id"] = strategy_id
        _copy_strategy_desc_columns(summary, group)
        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)
    ev_cap, pf_cap = 0.30, 2.0
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    return summary_df.sort_values(["spy_trend_color", "G_score"], ascending=[True, False]).reset_index(drop=True)


def summarize_by_pattern_and_era(trades: pd.DataFrame) -> pd.DataFrame:
    """
    chart_pattern x era, POOLED across every strategy variant in `trades` (not broken
    out per strategy_id like the other summarize_by_* functions) -- user request
    2026-08-31: "look at the chart patterns, do anything emerge when paired with year?"
    A per-strategy x pattern x era breakdown would mostly be too thin to trust (with 600
    strategies x 10 patterns x 7 eras, a typical cell would only have single-digit
    trades); pooling across strategies keeps sample sizes meaningful (thousands of trades
    per cell) at the cost of not being able to say WHICH exact strategy benefits, only
    whether the (pattern, era) combination itself looks structurally strong or weak
    across the whole grid.

    Found via this exact query, 2026-08-31: CPH (Cup with Handle) was the only pattern
    positive in every era including 2022, when literally 0 of 600 strategies were
    profitable in the era-only breakdown -- suggesting chart_pattern could be a real
    signal-quality filter, not just noise.
    """
    trades = add_era(trades)
    rows = []
    for (pattern, era), group in trades.groupby(["chart_pattern", "era"]):
        summary = summarize(group)
        summary["chart_pattern"] = pattern
        summary["era"] = era
        rows.append(summary)

    summary_df = pd.DataFrame(rows)
    ev_cap, pf_cap = 0.30, 2.0
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    lead_cols = ["chart_pattern", "era", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R",
                 "G_score"]
    other_cols = [c for c in summary_df.columns if c not in lead_cols]
    summary_df = summary_df[lead_cols + other_cols]
    return summary_df.sort_values(["chart_pattern", "era"]).reset_index(drop=True)


def top_n_per_year(summary_df: pd.DataFrame, n: int = 5, min_trades: int = 10,
                    sort_by: str = "G_score") -> pd.DataFrame:
    """min_trades filters out (year, strategy) cells too thin to trust -- with ~2,358
    events split across a strategy grid and ~14 calendar years, a single-year cell can
    easily have single-digit N; a "best strategy of the year" built on 3 trades is noise,
    not signal (see [[feedback_verify_against_real_data]])."""
    df = summary_df[summary_df["triggered_trades"] >= min_trades]
    return (df.sort_values(["year", sort_by], ascending=[True, False])
              .groupby("year", group_keys=False).head(n).reset_index(drop=True))


def top_n_per_era(summary_df: pd.DataFrame, n: int = 10, min_trades: int = 10,
                   sort_by: str = "G_score") -> pd.DataFrame:
    """Same min_trades reasoning as top_n_per_year -- an era spans multiple years so
    cells are less thin on average, but still worth guarding."""
    df = summary_df[summary_df["triggered_trades"] >= min_trades]
    return (df.sort_values(["era", sort_by], ascending=[True, False])
              .groupby("era", group_keys=False).head(n).reset_index(drop=True))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("trades_path", help="path to a trades_*.parquet file, e.g. outputs/trades_v3b.parquet")
    parser.add_argument("--by", choices=["year", "era"], default="year", help="group by calendar year or by era")
    parser.add_argument("--top", type=int, default=5, help="strategies to show per year/era")
    parser.add_argument("--min-trades", type=int, default=10,
                         help="minimum triggered trades in a (year/era, strategy) cell to be ranked")
    args = parser.parse_args()

    trades = pd.read_parquet(args.trades_path)
    group_col = args.by
    summary_df = summarize_by_year(trades) if args.by == "year" else summarize_by_era(trades)

    out_path = os.path.splitext(args.trades_path)[0] + f"_by_{args.by}.csv"
    summary_df.to_csv(out_path, index=False)
    print(f"wrote {len(summary_df)} ({args.by}, strategy) rows to {out_path}")

    top = top_n_per_year(summary_df, n=args.top, min_trades=args.min_trades) if args.by == "year" \
        else top_n_per_era(summary_df, n=args.top, min_trades=args.min_trades)
    cols = [group_col, "strategy_id", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R", "G_score"]
    print(f"\n--- Top {args.top} strategies per {args.by} (min {args.min_trades} triggered trades) ---")
    print(top[cols].to_string(index=False))


if __name__ == "__main__":
    main()
