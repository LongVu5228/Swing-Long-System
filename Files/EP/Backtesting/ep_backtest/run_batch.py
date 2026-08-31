"""
Phase 4/5 batch runner: simulate one or more (entry_type, stop_type) strategies across
the full EP V5 event universe, write trade-level long-format results, and print a
strategy summary (Section 34/63 schema, minus the extras deferred to later analysis).

Usage:
    python -m ep_backtest.run_batch --entry 15m --stop 0.50adr
    python -m ep_backtest.run_batch --all-72
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed

import pandas as pd
from tqdm import tqdm

from . import calendar_utils, config, daily_bars, exits, minute_bars
from .entry import find_entry
from .load_events import load_ep_v5
from .simulate_trade import TradeResult, _strategy_id, simulate_trade_from_data, simulate_with_entry


def _prefetch(events: pd.DataFrame, workers: int):
    """Warm the daily+minute caches for every event before simulating (parallel I/O)."""
    tickers = sorted(events["ticker"].unique())
    earliest = events.groupby("ticker")["reaction_date"].min().to_dict()

    print(f"Prefetching daily bars for {len(tickers)} tickers...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(daily_bars.pull_ticker_daily_bars, t, earliest[t]): t for t in tickers}
        for _ in tqdm(as_completed(futs), total=len(futs), desc="daily bars"):
            pass

    print(f"Prefetching minute bars for {len(events)} events...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(minute_bars.get_event_window_minute_bars, row.ticker, row.reaction_date): (row.ticker, row.reaction_date)
            for row in events.itertuples()
        }
        for _ in tqdm(as_completed(futs), total=len(futs), desc="minute bars"):
            pass


# Per-event metadata worth carrying into every trade-level output row for post-hoc
# slicing (year-by-year is already done via event_date; this adds ADR and turnover --
# ADR was the #1 predictor and turnover the #2 predictor in this project's earlier EP
# research, see Swing_Long_EP_Master_Findings_CURRENT.md) WITHOUT needing to re-run the
# simulation later -- these are static properties of the event itself, untouched by
# which strategy is being simulated. Add a name here (and to the raw EP V5 read, if it
# isn't already a column there) rather than joining trades back to events after the fact
# every time a new slicing question comes up.
EVENT_META_COLUMNS = ["chart_pattern", "adr14", "adr_category", "trading_turnover_pct",
                       "trading_turnover_pct_category"]


def event_meta_from_row(row) -> dict:
    return {col: getattr(row, col) for col in EVENT_META_COLUMNS}


def _result_row(result, event_meta: dict, entry_type: str, stop_type: str) -> dict:
    return {
        "strategy_id": result.strategy_id,
        "ticker": result.ticker,
        "event_date": result.event_date,
        **event_meta,
        "entry_type": entry_type,
        "stop_type": stop_type,
        "status": result.status,
        "entry_status": result.entry_status,
        "entry_day_offset": result.entry_day_offset,
        "entry_fill": result.entry_fill,
        "initial_stop_price": result.initial_stop_price,
        "initial_risk_per_share": result.initial_risk_per_share,
        # exit_timestamp is a tz-aware datetime for a minute-bar exit but a plain date
        # for a daily-bar-approximation/SMA10 exit -- store as ISO text so Parquet
        # doesn't choke on the mixed type.
        "exit_timestamp": str(result.exit_timestamp) if result.exit_timestamp is not None else None,
        "exit_price": result.exit_price,
        "exit_reason": result.exit_reason,
        "realized_R": result.realized_R,
        "holding_days": result.holding_days,
        "max_favorable_R": result.max_favorable_R,
        "exit_efficiency": result.exit_efficiency,
    }


def run_strategy(events: pd.DataFrame, entry_type: str, stop_type: str) -> pd.DataFrame:
    rows = []
    for row in events.itertuples():
        minute_df = minute_bars.get_event_window_minute_bars(row.ticker, row.reaction_date)
        daily_df = daily_bars.pull_ticker_daily_bars(row.ticker, row.reaction_date)
        result = simulate_trade_from_data(
            row.ticker, row.reaction_date, row.adr14, entry_type, stop_type, minute_df, daily_df
        )
        rows.append(_result_row(result, event_meta_from_row(row), entry_type, stop_type))
    return pd.DataFrame(rows)


def _process_one_event(args) -> list:
    """
    Top-level (picklable) worker: runs the full 6x12 grid for ONE event, reading its
    minute/daily bars from the on-disk cache. Called either directly (sequential mode)
    or via ProcessPoolExecutor (parallel mode) -- must not depend on any state besides
    its arguments, since a process-pool worker gets a fresh interpreter with none of the
    parent's in-memory state.
    """
    ticker, reaction_date, adr14, event_meta = args
    rows = []

    minute_df = minute_bars.get_event_window_minute_bars(ticker, reaction_date)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, reaction_date)

    if minute_df is None or minute_df.empty:
        for entry_type in config.ENTRY_TYPES:
            for stop_type in config.STOP_TYPES:
                result = TradeResult(
                    ticker=ticker, event_date=reaction_date, entry_type=entry_type,
                    stop_type=stop_type, strategy_id=_strategy_id(entry_type, stop_type),
                    status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
                )
                rows.append(_result_row(result, event_meta, entry_type, stop_type))
        return rows

    daily_sma = exits.add_sma10(daily_df)
    sessions = calendar_utils.sessions_from(reaction_date, config.MAX_ENTRY_DAY_OFFSET + 1)
    for entry_type in config.ENTRY_TYPES:
        try:
            entry = find_entry(minute_df, reaction_date, sessions, entry_type)
        except ValueError:
            entry = None

        for stop_type in config.STOP_TYPES:
            if entry is None:
                result = TradeResult(
                    ticker=ticker, event_date=reaction_date, entry_type=entry_type,
                    stop_type=stop_type, strategy_id=_strategy_id(entry_type, stop_type),
                    status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
                )
            else:
                result = simulate_with_entry(
                    ticker, reaction_date, adr14, entry_type, stop_type,
                    entry, minute_df, daily_sma, sessions,
                )
            rows.append(_result_row(result, event_meta, entry_type, stop_type))

    return rows


def run_all_72(events: pd.DataFrame, workers: int = 1) -> pd.DataFrame:
    """
    Runs the full 6x12 grid for every event. Per-event work is completely independent
    (each reads its own cached Parquet files), so with workers > 1 this fans out across
    a ProcessPoolExecutor -- CPU-bound work (numpy/pandas per event), so processes, not
    threads, are needed to actually use multiple cores (threads stay serialized behind
    the GIL for this kind of work).

    Within one event, `_process_one_event` still hoists find_entry/add_sma10 out of the
    stop_type loop (computed once per entry_type, not once per (entry_type, stop_type))
    and the position-management stop/SMA10 scan is vectorized -- see simulate_trade.py.
    Those two fixes were what took a naive per-event time from ~5s down to ~0.03s;
    parallelizing across events on top of that is what this function adds.
    """
    arg_list = [
        (row.ticker, row.reaction_date, row.adr14, event_meta_from_row(row)) for row in events.itertuples()
    ]

    all_rows = []
    if workers <= 1:
        for args in tqdm(arg_list, desc="events (72 strategies each)"):
            all_rows.extend(_process_one_event(args))
    else:
        # chunksize=2, not the ProcessPoolExecutor default (~len/workers, effectively
        # huge here): per-event work time varies a lot -- a MISSING_MINUTE_DATA event
        # returns near-instantly while a fully-simulated one runs the whole strategy
        # grid -- so a small chunksize lets an idle worker grab new work sooner instead
        # of sitting on a slow chunk while other workers finish early. 2026-08-31,
        # user request: "what can we do to speed up the scripts" on a 4-core/8-thread
        # laptop -- this is the one safe, zero-risk lever available locally (see
        # config.py's screening pipeline for the bigger one: don't run more than needed).
        with ProcessPoolExecutor(max_workers=workers) as ex:
            for rows in tqdm(ex.map(_process_one_event, arg_list, chunksize=2), total=len(arg_list),
                              desc=f"events (72 strategies each, {workers} processes)"):
                all_rows.extend(rows)

    return pd.DataFrame(all_rows)


def summarize(trades: pd.DataFrame) -> dict:
    eligible = len(trades)
    no_entry = (trades["status"] == config.STATUS_NO_ENTRY).sum()
    triggered = trades[trades["status"] == "OK"]
    n = len(triggered)

    wins = triggered[triggered["realized_R"] > 1e-9]
    losses = triggered[triggered["realized_R"] < -1e-9]

    avg_winner = wins["realized_R"].mean() if len(wins) else float("nan")
    avg_loser = losses["realized_R"].mean() if len(losses) else float("nan")
    win_rate = len(wins) / n if n else float("nan")
    rr = avg_winner / abs(avg_loser) if avg_loser and avg_loser == avg_loser else float("nan")
    gross_win = wins["realized_R"].sum()
    gross_loss = abs(losses["realized_R"].sum())
    pf = gross_win / gross_loss if gross_loss else float("nan")
    ev = triggered["realized_R"].mean() if n else float("nan")
    total_r = triggered["realized_R"].sum()

    other_status = trades[~trades["status"].isin([config.STATUS_NO_ENTRY, "OK"])]["status"].value_counts().to_dict()

    # Exit efficiency (realized_R / MFE) is only meaningful for trades that had a real
    # move to give back -- a trade that ticks up 0.01R before a routine stop-out produces
    # an efficiency ratio like -76 (dividing a normal ~-1R loss by a near-zero MFE), a
    # division-by-near-zero artifact, not a real signal. Filtering to trades that reached
    # at least 1R of unrealized profit at some point is what makes the average
    # interpretable; the unfiltered version is kept too for transparency but should not
    # be read as "how good are our exits" on its own. See run_batch_v3b.summarize_all_v3b,
    # which this mirrors.
    has_mfe = "max_favorable_R" in triggered.columns
    real_movers = triggered[triggered["max_favorable_R"] >= 1.0] if has_mfe else triggered.iloc[0:0]

    # Split real movers by outcome: "avg_exit_efficiency" alone blends genuine winners
    # (positive efficiency -- kept most of what they ran up) with trades that touched 1R+
    # unrealized profit and then round-tripped all the way to a loss before breakeven
    # ever activated (necessarily negative efficiency, by construction, whenever they
    # exist). At a 15-35% win rate, that second group dominates the population and drags
    # the blended average deep negative on its own -- not informative about exit timing
    # on the trades that actually worked. Splitting them shows both stories separately.
    winning_real_movers = real_movers[real_movers["realized_R"] > 1e-9]
    losing_real_movers = real_movers[real_movers["realized_R"] <= 1e-9]

    return {
        "eligible_events": eligible,
        "no_entry": int(no_entry),
        "triggered_trades": n,
        "entry_rate": n / (eligible - other_status_count(other_status)) if eligible else float("nan"),
        "win_rate": win_rate,
        "avg_winner_R": avg_winner,
        "avg_loser_R": avg_loser,
        "RR": rr,
        "profit_factor": pf,
        "EV_R": ev,
        "total_R": total_r,
        "median_R": triggered["realized_R"].median() if n else float("nan"),
        "std_R": triggered["realized_R"].std() if n else float("nan"),
        "avg_hold_days": triggered["holding_days"].mean() if n else float("nan"),
        "pct_trades_with_real_move": len(real_movers) / n if n else float("nan"),
        "avg_exit_efficiency": real_movers["exit_efficiency"].mean() if len(real_movers) else float("nan"),
        "median_exit_efficiency": real_movers["exit_efficiency"].median() if len(real_movers) else float("nan"),
        "avg_exit_efficiency_unfiltered": triggered["exit_efficiency"].mean() if n else float("nan"),
        "avg_max_favorable_R": triggered["max_favorable_R"].mean() if n and has_mfe else float("nan"),
        # Real movers split by outcome -- see the comment above winning_real_movers.
        "pct_real_movers_still_won": len(winning_real_movers) / len(real_movers) if len(real_movers) else float("nan"),
        "avg_exit_efficiency_winners": winning_real_movers["exit_efficiency"].mean() if len(winning_real_movers) else float("nan"),
        "median_exit_efficiency_winners": winning_real_movers["exit_efficiency"].median() if len(winning_real_movers) else float("nan"),
        "avg_exit_efficiency_round_trip_losers": losing_real_movers["exit_efficiency"].mean() if len(losing_real_movers) else float("nan"),
        "other_status_counts": other_status,
    }


def other_status_count(d: dict) -> int:
    return sum(d.values())


def effective_outputs_dir(limit) -> str:
    """
    `--limit` truncates the INPUT events for a quick smoke test, but on its own does
    nothing to the OUTPUT path -- a smoke test and a real full-scale run write to the
    exact same file. Confirmed as a real, repeatable mistake (2026-08-31): three
    consecutive `--limit` smoke tests against run_batch_v3b.py silently overwrote real,
    already-completed full-scale results (two of the four output files were destroyed
    outright; a third only survived because it happened to be open in Excel at that
    exact moment, purely by luck). Every batch runner's main() must route through this
    instead of using config.OUTPUTS_DIR directly, so a `--limit` run is STRUCTURALLY
    unable to touch a real output file, not just conventionally expected not to.
    """
    if limit:
        return os.path.join(config.OUTPUTS_DIR, "smoketest")
    return config.OUTPUTS_DIR


def summarize_all(all_trades: pd.DataFrame) -> pd.DataFrame:
    summaries = []
    for (entry_type, stop_type), trades in all_trades.groupby(["entry_type", "stop_type"]):
        summary = summarize(trades)
        summary["entry_type"] = entry_type
        summary["stop_type"] = stop_type
        summary["strategy_id"] = f"E{entry_type.upper()}__S{stop_type.upper()}"
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
    parser.add_argument("--entry", default="15m")
    parser.add_argument("--stop", default="0.50adr")
    parser.add_argument("--all-72", action="store_true", help="run the full 6x12 V1 grid instead of one strategy")
    parser.add_argument("--limit", type=int, default=None, help="only the first N events (testing)")
    parser.add_argument("--workers", type=int, default=15, help="I/O-bound prefetch thread count")
    parser.add_argument("--sim-workers", type=int, default=os.cpu_count() or 4,
                         help="CPU-bound simulation process count for --all-72 (default: all cores)")
    parser.add_argument("--no-prefetch", action="store_true")
    args = parser.parse_args()

    events = load_ep_v5()
    if args.limit:
        events = events.head(args.limit)
    print(f"{len(events)} events loaded from EP V5")

    if not args.no_prefetch:
        _prefetch(events, args.workers)

    outputs_dir = effective_outputs_dir(args.limit)
    if args.limit:
        print(f"--limit set -- writing to {outputs_dir} instead of the real outputs/ dir")
    os.makedirs(outputs_dir, exist_ok=True)

    if not args.all_72:
        trades = run_strategy(events, args.entry, args.stop)
        out_path = os.path.join(outputs_dir, f"trades_E{args.entry.upper()}__S{args.stop.upper()}.parquet")
        trades.to_parquet(out_path, index=False)
        print(f"\nwrote {len(trades)} trade rows to {out_path}")

        summary = summarize(trades)
        print("\n--- Strategy summary ---")
        for k, v in summary.items():
            print(f"{k}: {v}")
        return

    combined_trades = run_all_72(events, workers=args.sim_workers)
    combined_trades.to_parquet(os.path.join(outputs_dir, "trades_all_72.parquet"), index=False)

    summary_df = summarize_all(combined_trades)
    summary_df.to_csv(os.path.join(outputs_dir, "strategy_summary_all_72.csv"), index=False)

    print(f"\nwrote {len(combined_trades)} trade rows across 72 strategies")
    print(f"strategy summary: {os.path.join(outputs_dir, 'strategy_summary_all_72.csv')}")
    print("\n--- Top 10 by G Score ---")
    cols = ["strategy_id", "triggered_trades", "win_rate", "RR", "profit_factor", "EV_R", "total_R",
            "pct_trades_with_real_move", "avg_exit_efficiency", "G_score"]
    print(summary_df[cols].head(10).to_string(index=False))
    print("\n--- Bottom 5 by G Score ---")
    print(summary_df[cols].tail(5).to_string(index=False))


if __name__ == "__main__":
    main()
