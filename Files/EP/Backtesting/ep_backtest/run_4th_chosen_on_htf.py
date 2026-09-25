"""
Runs the exact 4th-chosen-one strategy (E60M / 0.50ADR / close_below_20ma /
equal_depletion / start20 / C50 -- same config as build_4th_chosen_excel.py) against the
6,669-row "high tight flag" BGU candidate list (HTF_50pct_move_15pct_pullback.xlsx in
Files/Buyable Gap Up/), instead of its original EP V5 event set.

This list has no hand-labeled Chart Pattern column (it's BGU/BP_V1 events, not EP), so no
DT-family exclusion is applied here -- the HTF filter (50%+ move in some 14-day window
over the trailing 6mo, tight <=15% pullback since) is itself the candidate substitute for
that exclusion, which is exactly the hypothesis being tested.

adr14 (needed for the 0.50ADR initial stop) isn't in the HTF file -- joined in from
Files/Buyable Gap Up/adr14_pregap.csv (already computed earlier this project with the
identical EP-matching adr14 formula: 14-day mean-high-minus-mean-low over the prior close),
keyed on the RAW ticker + date (both files derive from buyable_gap_ups_20y.csv).

Usage (run from Files/EP/Backtesting/, per run_batch_v3b.py's own convention):
    python -m ep_backtest.run_4th_chosen_on_htf                 # full run
    python -m ep_backtest.run_4th_chosen_on_htf --limit 100     # first 100 rows (testing)
"""
import argparse
import os
import sys
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from datetime import date

import numpy as np
import pandas as pd
from tqdm import tqdm

from . import calendar_utils, config, daily_bars, exits, minute_bars
from .entry import find_entry
from .initial_stop import compute_initial_stop  # noqa: F401  (used indirectly via simulate_multi_v3_with_entry)
from .run_batch import summarize
from .simulate_trade import TradeResultMultiV3, _strategy_id_multi_v3, simulate_multi_v3_with_entry

HTF_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Buyable Gap Up")
HTF_XLSX = os.path.join(HTF_DIR, "HTF_1122_true_tight.xlsx")
ADR14_CSV = os.path.join(HTF_DIR, "adr14_pregap.csv")
OUTPUT_XLSX = os.path.join(os.path.dirname(__file__), "..", "outputs", "4th_chosen_on_HTF_1122.xlsx")

ENTRY_TYPE = "60m"
STOP_TYPE = "0.50adr"
TRAIL_TYPE = "close_below_20ma"
SELL_STYLE = "equal_depletion"
TARGET_LADDER = "start20"
CORE_PCT = 0.5
TARGET_PCTS = config.V3_MULTI_TARGET_LADDERS[TARGET_LADDER]
SELL_AMOUNT = config.V3_MULTI_SELL_AMOUNT_EQUAL
STRATEGY_ID = _strategy_id_multi_v3(ENTRY_TYPE, STOP_TYPE, TRAIL_TYPE, SELL_STYLE, TARGET_LADDER, CORE_PCT)


def load_events(limit=None) -> pd.DataFrame:
    htf = pd.read_excel(HTF_XLSX, sheet_name="HTF Candidates")
    htf["date"] = pd.to_datetime(htf["date"]).dt.date

    adr = pd.read_csv(ADR14_CSV)
    adr["date"] = pd.to_datetime(adr["date"]).dt.date
    adr = adr[["ticker", "date", "adr14_pregap"]].rename(columns={"adr14_pregap": "adr14"})
    # adr14_pregap.csv stores adr14 as a whole-number percentage (e.g. 6.19 meaning
    # 6.19%), matching EP V5's own convention -- but the simulator's compute_initial_stop
    # expects a decimal (0.0619), same normalization load_ep_v5() applies for EP events.
    adr["adr14"] = adr["adr14"] / 100.0

    events = htf.merge(adr, on=["ticker", "date"], how="left")
    print(f"adr14 join coverage: {events['adr14'].notna().mean() * 100:.1f}%")
    if limit:
        events = events.head(limit)
    return events


def _missing_data_result(ticker: str, event_date: date) -> TradeResultMultiV3:
    return TradeResultMultiV3(
        ticker=ticker, event_date=event_date, entry_type=ENTRY_TYPE, stop_type=STOP_TYPE,
        trail_type=TRAIL_TYPE, sell_style=SELL_STYLE, target_ladder=TARGET_LADDER, core_pct=CORE_PCT,
        strategy_id=STRATEGY_ID, status=config.STATUS_MISSING_MINUTE_DATA,
        entry_status=config.STATUS_MISSING_MINUTE_DATA,
    )


def prefetch(events: pd.DataFrame, workers: int):
    """Same purpose as run_batch._prefetch (module docstring there: 'warm the daily+
    minute caches for every event before simulating, in parallel'), adapted for this
    file's own column names (resolved_ticker/date instead of ticker/reaction_date) --
    daily_bars.pull_ticker_daily_bars caches per TICKER, so two ProcessPoolExecutor
    workers racing to write/read the same not-yet-cached ticker's parquet file at the
    same time corrupts it (confirmed live: 'Could not open Parquet input source...
    Couldn't deserialize thrift'). Warming the cache single-threaded-per-ticker first,
    via ThreadPoolExecutor (I/O-bound, not CPU-bound, so threads are fine here), avoids
    the race entirely before the ProcessPoolExecutor simulation stage ever starts."""
    events = events.copy()
    events["resolved_or_raw"] = events["resolved_ticker"].where(
        events["resolved_ticker"].notna() & (events["resolved_ticker"] != ""), events["ticker"])
    tickers = sorted(events["resolved_or_raw"].unique())
    earliest = events.groupby("resolved_or_raw")["date"].min().to_dict()

    print(f"Prefetching daily bars for {len(tickers)} unique tickers...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(daily_bars.pull_ticker_daily_bars, t, earliest[t]): t for t in tickers}
        for _ in tqdm(as_completed(futs), total=len(futs), desc="daily bars"):
            pass

    print(f"Prefetching minute bars for {len(events)} events...")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {
            ex.submit(minute_bars.get_event_window_minute_bars, row.resolved_or_raw, row.date): (row.resolved_or_raw, row.date)
            for row in events.itertuples()
        }
        for _ in tqdm(as_completed(futs), total=len(futs), desc="minute bars"):
            pass


def process_one_event(args) -> TradeResultMultiV3:
    raw_ticker, resolved_ticker, event_date, adr14 = args
    ticker = resolved_ticker if isinstance(resolved_ticker, str) and resolved_ticker else raw_ticker

    minute_df = minute_bars.get_event_window_minute_bars(ticker, event_date)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, event_date)

    if minute_df is None or minute_df.empty:
        return _missing_data_result(raw_ticker, event_date)

    daily_sma = exits.add_sma10(daily_df)
    sessions = calendar_utils.sessions_from(event_date, config.MAX_ENTRY_DAY_OFFSET + 1)

    try:
        entry = find_entry(minute_df, event_date, sessions, ENTRY_TYPE)
    except ValueError:
        return _missing_data_result(raw_ticker, event_date)

    if entry.entry_status == config.STATUS_NO_ENTRY:
        result = TradeResultMultiV3(
            ticker=raw_ticker, event_date=event_date, entry_type=ENTRY_TYPE, stop_type=STOP_TYPE,
            trail_type=TRAIL_TYPE, sell_style=SELL_STYLE, target_ladder=TARGET_LADDER, core_pct=CORE_PCT,
            strategy_id=STRATEGY_ID, status=config.STATUS_NO_ENTRY, entry_status=config.STATUS_NO_ENTRY,
        )
        return result

    result = simulate_multi_v3_with_entry(
        ticker, event_date, adr14 if pd.notna(adr14) else None, ENTRY_TYPE, STOP_TYPE, TRAIL_TYPE,
        TARGET_PCTS, SELL_STYLE, SELL_AMOUNT, TARGET_LADDER, CORE_PCT,
        entry, minute_df, daily_sma, sessions,
    )
    result.ticker = raw_ticker  # keep the ORIGINAL (possibly P123-decorated) ticker in the output
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--sim-workers", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--prefetch-workers", type=int, default=15)
    parser.add_argument("--no-prefetch", action="store_true")
    args = parser.parse_args()

    events = load_events(limit=args.limit)
    print(f"{len(events)} HTF-candidate events loaded")
    print(f"Strategy: {STRATEGY_ID}")

    if not args.no_prefetch:
        prefetch(events, args.prefetch_workers)

    arg_list = [
        (row.ticker, row.resolved_ticker, row.date, row.adr14)
        for row in events.itertuples()
    ]

    results = []
    with ProcessPoolExecutor(max_workers=args.sim_workers) as ex:
        for r in tqdm(ex.map(process_one_event, arg_list, chunksize=4), total=len(arg_list),
                      desc=f"4th chosen one on HTF ({args.sim_workers} processes)"):
            results.append(r)

    rows = []
    for r in results:
        rows.append({
            "ticker": r.ticker, "event_date": r.event_date, "status": r.status,
            "entry_status": r.entry_status, "entry_day_offset": r.entry_day_offset,
            "entry_fill": r.entry_fill, "initial_stop_price": r.initial_stop_price,
            "n_sales": r.n_sales, "realized_R": r.realized_R, "holding_days": r.holding_days,
            "max_favorable_R": r.max_favorable_R, "exit_efficiency": r.exit_efficiency,
        })
    df = pd.DataFrame(rows)
    df.to_excel(OUTPUT_XLSX, index=False, sheet_name="Trade Log")
    print(f"\nWrote {len(df)} rows to {OUTPUT_XLSX}")
    print(f"status counts: {df['status'].value_counts().to_dict()}")

    ok = df[df["status"] == "OK"].copy()
    n = len(ok)
    if n == 0:
        print("No OK trades -- nothing to summarize.")
        return
    wins = ok[ok["realized_R"] > 0]["realized_R"]
    losses = ok[ok["realized_R"] <= 0]["realized_R"]
    print(f"\n--- Summary ({n} triggered trades) ---")
    print(f"Win rate: {len(wins) / n * 100:.1f}%")
    print(f"Avg winner (R): {wins.mean():.3f}")
    print(f"Avg loser (R): {losses.mean():.3f}")
    print(f"RR: {wins.mean() / abs(losses.mean()):.3f}")
    print(f"Profit factor: {wins.sum() / abs(losses.sum()):.3f}")
    print(f"EV_R (expectancy per trade): {ok['realized_R'].mean():.4f}")
    print(f"Total R: {ok['realized_R'].sum():.2f}")
    print(f"Median R: {ok['realized_R'].median():.3f}")
    print(f"Std dev R: {ok['realized_R'].std():.3f}")


if __name__ == "__main__":
    main()
