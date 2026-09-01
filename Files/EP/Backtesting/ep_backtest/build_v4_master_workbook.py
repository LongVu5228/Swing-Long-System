"""
Builds "V4 Master Strategies.xlsx" -- the human-facing rollup of screen2's results,
combining everything that used to be separate ad-hoc queries into one workbook (user
request 2026-08-31). Tabs:

- Screen2 All Days / Screen2 Day 0 / Screen2 Day 1+: the full 600-strategy summaries,
  unfiltered, restricted to D0-only entries, and restricted to D+1..D+7-only entries
  respectively (mirrors run_batch_v3b.py's own three output CSVs for the same run --
  Day 1+ added alongside Day 0 for symmetry, user request 2026-08-31: "not fair to have
  day 0 and all days, but not day 1+").
- Era Breakdown - All Days / Era Breakdown - Day 0 / Era Breakdown - Day 1+: every
  (era, strategy) cell, all three entry scopes.
- All Data (Filterable): every row from all six tabs above, unioned into one long table
  with `era` (including a synthetic "00 | ALL ERAS" row for the full-history aggregate)
  and `entry_scope` ("All Days" / "Day 0 Only" / "Day 1+ Only") as explicit columns,
  with an Excel AutoFilter applied to the header row -- lets you filter by era and/or
  entry scope directly in Excel instead of switching tabs.
- Consistent Across Eras: the strategies that hold up across every COMPLETE era (i.e.
  excluding 2022 -- a known-bad regime for this whole strategy class -- and 2026+ -- a
  known-incomplete year subject to STILL_OPEN_AT_DATA_END right-censoring, see
  trade_metrics.py / run_batch.summarize). "Consistent" = G_score > MIN_G_SCORE in every
  one of those 5 eras -- a different, arguably more important cut than "best on average,"
  since a strategy can win on aggregate by having a few outsized eras rather than being
  reliably solid throughout. Built from the All Days scope.

Usage:
    python -m ep_backtest.build_v4_master_workbook
    python -m ep_backtest.build_v4_master_workbook --trades outputs/trades_v3b_screen2.parquet --min-g-score 5
"""

import argparse
import os

import pandas as pd
from openpyxl.utils import get_column_letter

from . import config
from .run_batch_v3b import day0_only_summary, day1plus_only_summary, summarize_all_v3b
from .year_breakdown import summarize_by_era

EXCLUDED_ERAS_FOR_CONSISTENCY = ["05 | 2022", "07 | 2026+"]

_LEAD_COLS = ["era", "entry_scope", "strategy_id", "entry_type", "stop_type", "trail_type", "sell_style",
              "target_ladder", "core_pct", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R",
              "total_R", "G_score"]


def _combined_filterable_table(scopes: dict) -> pd.DataFrame:
    """scopes: {entry_scope_label: (aggregate_summary_df, era_summary_df)}."""
    pieces = []
    for label, (aggregate_df, era_df) in scopes.items():
        agg = aggregate_df.copy()
        agg["era"] = "00 | ALL ERAS (2012-2026)"
        agg["entry_scope"] = label
        pieces.append(agg)

        era = era_df.copy()
        era["entry_scope"] = label
        pieces.append(era)

    combined = pd.concat(pieces, ignore_index=True)
    other_cols = [c for c in combined.columns if c not in _LEAD_COLS]
    combined = combined[_LEAD_COLS + other_cols]
    return combined.sort_values(["era", "entry_scope", "G_score"], ascending=[True, True, False]).reset_index(drop=True)


def _consistent_across_eras(era_all: pd.DataFrame, min_g_score: float) -> pd.DataFrame:
    """Strategies whose G_score exceeds min_g_score in EVERY era not in
    EXCLUDED_ERAS_FOR_CONSISTENCY -- must have data in all of them, not just the ones it
    happens to clear."""
    complete = era_all[~era_all["era"].isin(EXCLUDED_ERAS_FOR_CONSISTENCY)]
    n_complete_eras = complete["era"].nunique()

    per_strategy = complete.groupby("strategy_id").agg(
        min_g_score=("G_score", "min"), eras_covered=("era", "nunique")
    ).reset_index()
    qualifying_ids = per_strategy[
        (per_strategy["eras_covered"] == n_complete_eras) & (per_strategy["min_g_score"] > min_g_score)
    ].sort_values("min_g_score", ascending=False)["strategy_id"]

    rows = complete[complete["strategy_id"].isin(qualifying_ids)].copy()
    order = {sid: i for i, sid in enumerate(qualifying_ids)}
    rows["_order"] = rows["strategy_id"].map(order)
    return rows.sort_values(["_order", "era"]).drop(columns=["_order"]).reset_index(drop=True)


def _autofilter(writer, sheet_name: str, df: pd.DataFrame):
    ws = writer.sheets[sheet_name]
    last_col = get_column_letter(len(df.columns))
    ws.auto_filter.ref = f"A1:{last_col}{len(df) + 1}"
    ws.freeze_panes = "A2"


def build(trades_path: str, min_g_score: float, out_path: str):
    trades = pd.read_parquet(trades_path)
    day0_trades = trades[(trades["status"] != "OK") | (trades["entry_day_offset"] == 0)]
    day1plus_trades = trades[(trades["status"] != "OK") | (trades["entry_day_offset"] >= 1)]

    all_days_summary = summarize_all_v3b(trades)
    day0_summary = day0_only_summary(trades)
    day1plus_summary = day1plus_only_summary(trades)
    era_all = summarize_by_era(trades)
    era_day0 = summarize_by_era(day0_trades)
    era_day1plus = summarize_by_era(day1plus_trades)

    combined = _combined_filterable_table({
        "All Days": (all_days_summary, era_all),
        "Day 0 Only": (day0_summary, era_day0),
        "Day 1+ Only": (day1plus_summary, era_day1plus),
    })
    consistent = _consistent_across_eras(era_all, min_g_score)

    sheets = {
        "Screen2 All Days": all_days_summary,
        "Screen2 Day 0": day0_summary,
        "Screen2 Day 1+": day1plus_summary,
        "Era Breakdown - All Days": era_all,
        "Era Breakdown - Day 0": era_day0,
        "Era Breakdown - Day 1+": era_day1plus,
        "All Data (Filterable)": combined,
        f"Consistent Across Eras (G>{min_g_score:g})": consistent,
    }

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with pd.ExcelWriter(out_path, engine="openpyxl") as writer:
        for sheet_name, df in sheets.items():
            df.to_excel(writer, sheet_name=sheet_name, index=False)
            _autofilter(writer, sheet_name, df)

    print(f"wrote {out_path}")
    for sheet_name, df in sheets.items():
        print(f"  {sheet_name}: {len(df)} rows")
    print(f"\n'Consistent Across Eras' strategies found: {len(consistent['strategy_id'].unique())}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--trades", default=os.path.join(config.OUTPUTS_DIR, "trades_v3b_screen2.parquet"))
    parser.add_argument("--min-g-score", type=float, default=5.0,
                         help="threshold for the 'Consistent Across Eras' tab")
    parser.add_argument("--out", default=os.path.join(config.OUTPUTS_DIR, "V4 Master Strategies.xlsx"))
    args = parser.parse_args()
    build(args.trades, args.min_g_score, args.out)


if __name__ == "__main__":
    main()
