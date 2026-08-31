"""
V2 batch runner: 6 trailing-stop types x the strong V1 region (config.V2_ENTRY_TYPES x
config.V2_STOP_TYPES), not the full V1 72-combo grid -- Section 86 explicitly says to
carry forward the strong region from V1, not re-explode the whole grid.

Usage:
    python -m ep_backtest.run_batch_v2
    python -m ep_backtest.run_batch_v2 --limit 100 --sim-workers 4
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor

import pandas as pd
from tqdm import tqdm

from . import calendar_utils, config, daily_bars, exits, minute_bars
from .entry import find_entry
from .load_events import load_ep_v5
from .run_batch import _prefetch, other_status_count, summarize
from .simulate_trade import TradeResult, simulate_v2_with_entry


def _strategy_id_v2(entry_type: str, stop_type: str, trail_type: str) -> str:
    return f"E{entry_type.upper()}__S{stop_type.upper()}__T{trail_type.upper()}"


def _result_row(result, chart_pattern) -> dict:
    return {
        "strategy_id": result.strategy_id,
        "ticker": result.ticker,
        "event_date": result.event_date,
        "chart_pattern": chart_pattern,
        "entry_type": result.entry_type,
        "stop_type": result.stop_type,
        "trail_type": result.trail_type,
        "status": result.status,
        "entry_status": result.entry_status,
        "entry_day_offset": result.entry_day_offset,
        "entry_fill": result.entry_fill,
        "initial_stop_price": result.initial_stop_price,
        "initial_risk_per_share": result.initial_risk_per_share,
        "exit_timestamp": str(result.exit_timestamp) if result.exit_timestamp is not None else None,
        "exit_price": result.exit_price,
        "exit_reason": result.exit_reason,
        "realized_R": result.realized_R,
        "holding_days": result.holding_days,
    }


def _process_one_event(args) -> list:
    """Top-level (picklable) worker: runs the V2 region's full grid for ONE event."""
    ticker, reaction_date, adr14, chart_pattern = args
    rows = []

    minute_df = minute_bars.get_event_window_minute_bars(ticker, reaction_date)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, reaction_date)

    if minute_df is None or minute_df.empty:
        for entry_type in config.V2_ENTRY_TYPES:
            for stop_type in config.V2_STOP_TYPES:
                for trail_type in config.TRAIL_TYPES:
                    result = TradeResult(
                        ticker=ticker, event_date=reaction_date, entry_type=entry_type,
                        stop_type=stop_type, trail_type=trail_type,
                        strategy_id=_strategy_id_v2(entry_type, stop_type, trail_type),
                        status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
                    )
                    rows.append(_result_row(result, chart_pattern))
        return rows

    daily_sma = exits.add_sma10(daily_df)  # adds both sma10 and sma20
    sessions = calendar_utils.sessions_from(reaction_date, config.MAX_ENTRY_DAY_OFFSET + 1)

    for entry_type in config.V2_ENTRY_TYPES:
        try:
            entry = find_entry(minute_df, reaction_date, sessions, entry_type)
        except ValueError:
            entry = None

        for stop_type in config.V2_STOP_TYPES:
            for trail_type in config.TRAIL_TYPES:
                if entry is None:
                    result = TradeResult(
                        ticker=ticker, event_date=reaction_date, entry_type=entry_type,
                        stop_type=stop_type, trail_type=trail_type,
                        strategy_id=_strategy_id_v2(entry_type, stop_type, trail_type),
                        status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
                    )
                else:
                    result = simulate_v2_with_entry(
                        ticker, reaction_date, adr14, entry_type, stop_type, trail_type,
                        entry, minute_df, daily_sma, sessions,
                    )
                rows.append(_result_row(result, chart_pattern))

    return rows


def run_v2_grid(events: pd.DataFrame, workers: int = 1) -> pd.DataFrame:
    n_combos = len(config.V2_ENTRY_TYPES) * len(config.V2_STOP_TYPES) * len(config.TRAIL_TYPES)
    arg_list = [(row.ticker, row.reaction_date, row.adr14, row.chart_pattern) for row in events.itertuples()]

    all_rows = []
    if workers <= 1:
        for args in tqdm(arg_list, desc=f"events ({n_combos} V2 strategies each)"):
            all_rows.extend(_process_one_event(args))
    else:
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for rows in tqdm(ex.map(_process_one_event, arg_list, chunksize=8), total=len(arg_list),
                              desc=f"events ({n_combos} V2 strategies each, {workers} processes)"):
                all_rows.extend(rows)

    return pd.DataFrame(all_rows)


def summarize_all_v2(all_trades: pd.DataFrame) -> pd.DataFrame:
    summaries = []
    for (entry_type, stop_type, trail_type), trades in all_trades.groupby(["entry_type", "stop_type", "trail_type"]):
        summary = summarize(trades)
        summary["entry_type"] = entry_type
        summary["stop_type"] = stop_type
        summary["trail_type"] = trail_type
        summary["strategy_id"] = _strategy_id_v2(entry_type, stop_type, trail_type)
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
    print(f"V2 region: entries={config.V2_ENTRY_TYPES}, stops={config.V2_STOP_TYPES}, trails={config.TRAIL_TYPES}")

    if not args.no_prefetch:
        _prefetch(events, args.workers)

    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)

    combined_trades = run_v2_grid(events, workers=args.sim_workers)
    combined_trades.to_parquet(os.path.join(config.OUTPUTS_DIR, "trades_v2.parquet"), index=False)

    summary_df = summarize_all_v2(combined_trades)
    summary_df.to_csv(os.path.join(config.OUTPUTS_DIR, "strategy_summary_v2.csv"), index=False)

    print(f"\nwrote {len(combined_trades)} trade rows across {len(summary_df)} V2 strategies")
    print(f"strategy summary: {os.path.join(config.OUTPUTS_DIR, 'strategy_summary_v2.csv')}")
    cols = ["strategy_id", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R", "G_score"]
    print("\n--- Top 15 by G Score ---")
    print(summary_df[cols].head(15).to_string(index=False))
    print("\n--- Bottom 5 by G Score ---")
    print(summary_df[cols].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
