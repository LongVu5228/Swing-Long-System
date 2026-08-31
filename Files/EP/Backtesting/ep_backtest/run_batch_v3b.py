"""
V3b batch runner: multi-target staged partials, both sell styles (equal_depletion,
exponential_remaining) x both target ladders (early_start: 10/20/30/40/50%, late_start:
30/35/40/45/50% -- config.V3_MULTI_TARGET_LADDERS) x the Top-5 V2 base strategies x the
core/non-core split sweep (config.V3_CORE_PCTS: 30/50/70% core). Same "carry forward the
strong region" philosophy as V2/V3.

Also reports max_favorable_R (MFE) and exit_efficiency (realized_R / MFE) per trade,
averaged into the strategy summary -- how much of each trade's best price did the exit
rule actually capture.

Usage:
    python -m ep_backtest.run_batch_v3b
    python -m ep_backtest.run_batch_v3b --limit 100 --sim-workers 4
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
from .run_batch import _prefetch, summarize
from .simulate_trade import TradeResultMultiV3, _strategy_id_multi_v3, simulate_multi_v3_with_entry

_SELL_AMOUNTS = {
    "equal_depletion": config.V3_MULTI_SELL_AMOUNT_EQUAL,
    "exponential_remaining": config.V3_MULTI_SELL_AMOUNT_EXPONENTIAL,
}


def _result_row(result: TradeResultMultiV3, chart_pattern) -> dict:
    return {
        "strategy_id": result.strategy_id,
        "ticker": result.ticker,
        "event_date": result.event_date,
        "chart_pattern": chart_pattern,
        "entry_type": result.entry_type,
        "stop_type": result.stop_type,
        "trail_type": result.trail_type,
        "sell_style": result.sell_style,
        "target_ladder": result.target_ladder,
        "core_pct": result.core_pct,
        "status": result.status,
        "entry_status": result.entry_status,
        "entry_day_offset": result.entry_day_offset,
        "entry_fill": result.entry_fill,
        "initial_stop_price": result.initial_stop_price,
        "n_sales": result.n_sales,
        "first_sale_timestamp": str(result.first_sale_timestamp) if result.first_sale_timestamp is not None else None,
        "first_sale_price": result.first_sale_price,
        "first_sale_reason": result.first_sale_reason,
        "last_sale_timestamp": str(result.last_sale_timestamp) if result.last_sale_timestamp is not None else None,
        "last_sale_price": result.last_sale_price,
        "last_sale_reason": result.last_sale_reason,
        "realized_R": result.realized_R,
        "holding_days": result.holding_days,
        "max_favorable_R": result.max_favorable_R,
        "exit_efficiency": result.exit_efficiency,
    }


def _missing_data_row(ticker, reaction_date, chart_pattern, entry_type, stop_type, trail_type, sell_style,
                       target_ladder, core_pct) -> dict:
    result = TradeResultMultiV3(
        ticker=ticker, event_date=reaction_date, entry_type=entry_type, stop_type=stop_type,
        trail_type=trail_type, sell_style=sell_style, target_ladder=target_ladder, core_pct=core_pct,
        strategy_id=_strategy_id_multi_v3(entry_type, stop_type, trail_type, sell_style, target_ladder, core_pct),
        status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
    )
    return _result_row(result, chart_pattern)


def _process_one_event(args) -> list:
    """Top-level (picklable) worker: runs the Top-5-strategies x 2-sell-styles x 2-ladders grid for ONE event."""
    ticker, reaction_date, adr14, chart_pattern = args
    rows = []

    minute_df = minute_bars.get_event_window_minute_bars(ticker, reaction_date)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, reaction_date)

    if minute_df is None or minute_df.empty:
        for entry_type, stop_type, trail_type in config.V3_BASE_STRATEGIES:
            for sell_style in SELL_STYLES:
                for ladder_name in config.V3_MULTI_TARGET_LADDERS:
                    for core_pct in config.V3_CORE_PCTS:
                        rows.append(_missing_data_row(ticker, reaction_date, chart_pattern, entry_type, stop_type,
                                                       trail_type, sell_style, ladder_name, core_pct))
        return rows

    daily_sma = exits.add_sma10(daily_df)
    sessions = calendar_utils.sessions_from(reaction_date, config.MAX_ENTRY_DAY_OFFSET + 1)

    entries_needed = sorted({e for e, s, t in config.V3_BASE_STRATEGIES})
    entry_cache = {}
    for entry_type in entries_needed:
        try:
            entry_cache[entry_type] = find_entry(minute_df, reaction_date, sessions, entry_type)
        except ValueError:
            entry_cache[entry_type] = None

    for entry_type, stop_type, trail_type in config.V3_BASE_STRATEGIES:
        entry = entry_cache[entry_type]
        for sell_style in SELL_STYLES:
            for ladder_name, target_pcts in config.V3_MULTI_TARGET_LADDERS.items():
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


def run_v3b_grid(events: pd.DataFrame, workers: int = 1) -> pd.DataFrame:
    n_combos = (len(config.V3_BASE_STRATEGIES) * len(SELL_STYLES) * len(config.V3_MULTI_TARGET_LADDERS)
                * len(config.V3_CORE_PCTS))
    arg_list = [(row.ticker, row.reaction_date, row.adr14, row.chart_pattern) for row in events.itertuples()]

    all_rows = []
    if workers <= 1:
        for args in tqdm(arg_list, desc=f"events ({n_combos} V3b strategies each)"):
            all_rows.extend(_process_one_event(args))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for rows in tqdm(ex.map(_process_one_event, arg_list, chunksize=8), total=len(arg_list),
                              desc=f"events ({n_combos} V3b strategies each, {workers} processes)"):
                all_rows.extend(rows)

    return pd.DataFrame(all_rows)


def summarize_all_v3b(all_trades: pd.DataFrame) -> pd.DataFrame:
    summaries = []
    for strategy_id, trades in all_trades.groupby("strategy_id"):
        summary = summarize(trades)
        row = trades.iloc[0]
        summary["entry_type"] = row["entry_type"]
        summary["stop_type"] = row["stop_type"]
        summary["trail_type"] = row["trail_type"]
        summary["sell_style"] = row["sell_style"]
        summary["target_ladder"] = row["target_ladder"]
        summary["core_pct"] = row["core_pct"]
        summary["strategy_id"] = strategy_id
        # pct_trades_with_real_move / avg_exit_efficiency / avg_max_favorable_R etc. are
        # already computed by summarize() (shared with V1/V2/V3) -- see run_batch.summarize.

        summaries.append(summary)

    summary_df = pd.DataFrame(summaries)
    ev_cap, pf_cap = 0.30, 2.0  # Section 7 -- old G Score caps
    summary_df["ev_score"] = (summary_df["EV_R"] / ev_cap * 10).clip(0, 10)
    summary_df["pf_score"] = (summary_df["profit_factor"] / pf_cap * 10).clip(0, 10)
    summary_df["G_score"] = 0.5 * summary_df["ev_score"] + 0.5 * summary_df["pf_score"]
    summary_df = summary_df.drop(columns=["other_status_counts"])
    return summary_df.sort_values("G_score", ascending=False).reset_index(drop=True)


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
    print(f"V3b base strategies: {config.V3_BASE_STRATEGIES}")
    print(f"V3b sell styles: {SELL_STYLES}")
    print(f"V3b target ladders: {config.V3_MULTI_TARGET_LADDERS}")
    print(f"V3b core_pcts: {config.V3_CORE_PCTS}")

    if not args.no_prefetch:
        _prefetch(events, args.workers)

    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)

    combined_trades = run_v3b_grid(events, workers=args.sim_workers)
    combined_trades.to_parquet(os.path.join(config.OUTPUTS_DIR, "trades_v3b.parquet"), index=False)

    summary_df = summarize_all_v3b(combined_trades)
    summary_df.to_csv(os.path.join(config.OUTPUTS_DIR, "strategy_summary_v3b.csv"), index=False)

    print(f"\nwrote {len(combined_trades)} trade rows across {len(summary_df)} V3b strategies")
    print(f"strategy summary: {os.path.join(config.OUTPUTS_DIR, 'strategy_summary_v3b.csv')}")
    cols = ["strategy_id", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R",
            "pct_trades_with_real_move", "avg_exit_efficiency", "G_score"]
    print("\n--- All strategies by G Score ---")
    print(summary_df[cols].to_string(index=False))


if __name__ == "__main__":
    main()
