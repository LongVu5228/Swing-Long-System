"""
V3b broadened batch runner: same multi-target staged-partials engine as run_batch_v3b.py,
but over the FULL V2 entry x stop x trail grid (config.V3B_BROAD_BASE_STRATEGIES, 60
combos) instead of the narrowed Top-5 V2 winners -- user request 2026-08-31, "test on the
other candle types, that big list of possible strategies."

Scoped down from the full sell-style x ladder x core cross product to keep runtime
bounded: late_start ladder only (config.V3B_BROAD_TARGET_LADDERS), since it beat
early_start on every one of the 5 original base strategies x 2 sell styles already
tested in run_batch_v3b.py -- not worth re-proving at 12x the base-strategy count. Full
sell-style x core_pct sweep is kept: 60 base x 2 sell styles x 1 ladder x 3 core_pcts =
360 combos.

run_batch_v3b.py itself is untouched (still the narrow Top-5 grid, kept for
comparability with earlier results); this is a separate script/output so neither run
overwrites the other.

Usage:
    python -m ep_backtest.run_batch_v3b_broad
    python -m ep_backtest.run_batch_v3b_broad --limit 100 --sim-workers 4
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor

import pandas as pd
from tqdm import tqdm

from . import calendar_utils, config, daily_bars, exits, minute_bars
from .entry import find_entry
from .load_events import load_ep_v5
from .multi_partial_taking import SELL_STYLES
from .run_batch import _prefetch
from .run_batch_v3b import _SELL_AMOUNTS, _missing_data_row, _result_row, summarize_all_v3b
from .simulate_trade import simulate_multi_v3_with_entry


def _process_one_event(args) -> list:
    """Top-level (picklable) worker: runs the full-60-base-strategies x 2-sell-styles x
    1-ladder x 3-core_pcts grid for ONE event."""
    ticker, reaction_date, adr14, chart_pattern = args
    rows = []

    minute_df = minute_bars.get_event_window_minute_bars(ticker, reaction_date)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, reaction_date)

    if minute_df is None or minute_df.empty:
        for entry_type, stop_type, trail_type in config.V3B_BROAD_BASE_STRATEGIES:
            for sell_style in SELL_STYLES:
                for ladder_name in config.V3B_BROAD_TARGET_LADDERS:
                    for core_pct in config.V3_CORE_PCTS:
                        rows.append(_missing_data_row(ticker, reaction_date, chart_pattern, entry_type, stop_type,
                                                       trail_type, sell_style, ladder_name, core_pct))
        return rows

    daily_sma = exits.add_sma10(daily_df)
    sessions = calendar_utils.sessions_from(reaction_date, config.MAX_ENTRY_DAY_OFFSET + 1)

    entries_needed = sorted({e for e, s, t in config.V3B_BROAD_BASE_STRATEGIES})
    entry_cache = {}
    for entry_type in entries_needed:
        try:
            entry_cache[entry_type] = find_entry(minute_df, reaction_date, sessions, entry_type)
        except ValueError:
            entry_cache[entry_type] = None

    for entry_type, stop_type, trail_type in config.V3B_BROAD_BASE_STRATEGIES:
        entry = entry_cache[entry_type]
        for sell_style in SELL_STYLES:
            for ladder_name, target_pcts in config.V3B_BROAD_TARGET_LADDERS.items():
                for core_pct in config.V3_CORE_PCTS:
                    if entry is None:
                        rows.append(_missing_data_row(ticker, reaction_date, chart_pattern, entry_type, stop_type,
                                                       trail_type, sell_style, ladder_name, core_pct))
                    else:
                        result = simulate_multi_v3_with_entry(
                            ticker, reaction_date, adr14, entry_type, stop_type, trail_type,
                            target_pcts, sell_style, _SELL_AMOUNTS[sell_style], ladder_name, core_pct,
                            entry, minute_df, daily_sma, sessions,
                        )
                        rows.append(_result_row(result, chart_pattern))

    return rows


def run_v3b_broad_grid(events: pd.DataFrame, workers: int = 1) -> pd.DataFrame:
    n_combos = (len(config.V3B_BROAD_BASE_STRATEGIES) * len(SELL_STYLES)
                * len(config.V3B_BROAD_TARGET_LADDERS) * len(config.V3_CORE_PCTS))
    arg_list = [(row.ticker, row.reaction_date, row.adr14, row.chart_pattern) for row in events.itertuples()]

    all_rows = []
    if workers <= 1:
        for args in tqdm(arg_list, desc=f"events ({n_combos} broad V3b strategies each)"):
            all_rows.extend(_process_one_event(args))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for rows in tqdm(ex.map(_process_one_event, arg_list, chunksize=8), total=len(arg_list),
                              desc=f"events ({n_combos} broad V3b strategies each, {workers} processes)"):
                all_rows.extend(rows)

    return pd.DataFrame(all_rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="only the first N events (testing)")
    parser.add_argument("--workers", type=int, default=15, help="I/O-bound prefetch thread count")
    parser.add_argument("--sim-workers", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--no-prefetch", action="store_true")
    args = parser.parse_args()

    events = load_ep_v5()
    if args.limit:
        events = events.head(args.limit)
    print(f"{len(events)} events loaded from EP V5")
    print(f"V3b broad base strategies: {len(config.V3B_BROAD_BASE_STRATEGIES)} combos")
    print(f"V3b sell styles: {SELL_STYLES}")
    print(f"V3b broad target ladders: {config.V3B_BROAD_TARGET_LADDERS}")
    print(f"V3b core_pcts: {config.V3_CORE_PCTS}")

    if not args.no_prefetch:
        _prefetch(events, args.workers)

    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)

    combined_trades = run_v3b_broad_grid(events, workers=args.sim_workers)
    combined_trades.to_parquet(os.path.join(config.OUTPUTS_DIR, "trades_v3b_broad.parquet"), index=False)

    summary_df = summarize_all_v3b(combined_trades)
    summary_df.to_csv(os.path.join(config.OUTPUTS_DIR, "strategy_summary_v3b_broad.csv"), index=False)

    print(f"\nwrote {len(combined_trades)} trade rows across {len(summary_df)} V3b strategies")
    print(f"strategy summary: {os.path.join(config.OUTPUTS_DIR, 'strategy_summary_v3b_broad.csv')}")
    cols = ["strategy_id", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R",
            "pct_trades_with_real_move", "avg_exit_efficiency", "G_score"]
    print("\n--- Top 20 by G Score ---")
    print(summary_df[cols].head(20).to_string(index=False))
    print("\n--- Bottom 5 by G Score ---")
    print(summary_df[cols].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
