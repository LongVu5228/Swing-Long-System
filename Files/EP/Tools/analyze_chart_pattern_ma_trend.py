"""
One-off research script: for every human-labeled EP V5 event (Chart Pattern column,
2,358 rows), pull daily bars and check whether pre-event 200D/50D moving-average
position/slope cleanly separates the labeled downtrend patterns (DT, DT SW, DT U) from
the uptrend/basing ones (UT, UTU, U, SW, UDS, CPH).

Goal: find a purely mechanical rule (e.g. "200MA slope negative") that could stand in
for manual chart-pattern review when screening the 45K-row BGU/BP_V1 universe, which has
no Chart Pattern column and is too large to eyeball like EP's 2,358 was.

All moving-average stats are computed using only bars strictly BEFORE the event date
(no lookahead) -- consistent with pre_gap_close usage elsewhere in this project.

Usage:
    python analyze_chart_pattern_ma_trend.py               # full run
    python analyze_chart_pattern_ma_trend.py --smoke-test   # first 20 events, prints only
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import openpyxl
import pandas as pd
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env"))

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Scripts")
sys.path.insert(0, SCRIPTS_DIR)

from fill_episodic_pivots_v3 import get_daily_bars, PLAN_CUTOFF  # noqa: E402
from build_benzinga_candidate_list import resolve_historical_ticker  # noqa: E402
from build_v2_features import clean_ticker  # noqa: E402

EP_XLSX = os.path.join(os.path.dirname(__file__), "..", "EP V5.xlsx")
SHEET_NAME = "Data"
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "chart_pattern_ma_trend.csv")
SLOPE_LOOKBACK_DAYS = 20  # trading days back to measure MA slope over
TODAY = date.today()


def load_events():
    wb = openpyxl.load_workbook(EP_XLSX, data_only=True)
    ws = wb[SHEET_NAME]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    events = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        ticker = row[idx["ticker"]]
        rdate = row[idx["reaction_date"]]
        pattern = row[idx["Chart Pattern"]]
        if not ticker or not rdate or not pattern or pattern == "DELISTED":
            continue
        event_date = rdate.date() if hasattr(rdate, "date") else date.fromisoformat(str(rdate))
        events.append({"ticker": ticker, "event_date": event_date, "pattern": pattern})
    return events


def analyze_event(raw_ticker: str, event_date: date, pattern: str) -> dict:
    ticker = clean_ticker(raw_ticker)
    lo = max(event_date - relativedelta(months=15), PLAN_CUTOFF)
    hi = event_date
    if lo > hi:
        return {"ticker": raw_ticker, "date": event_date.isoformat(), "pattern": pattern,
                "status": "before_polygon_plan_cutoff"}

    bars = get_daily_bars(ticker, lo.isoformat(), hi.isoformat())
    if bars is None:
        alt = resolve_historical_ticker(ticker, event_date)
        if alt != ticker:
            bars = get_daily_bars(alt, lo.isoformat(), hi.isoformat())
    if bars is None:
        return {"ticker": raw_ticker, "date": event_date.isoformat(), "pattern": pattern, "status": "no_daily_bars"}

    prior = bars[bars["date"] < event_date].reset_index(drop=True)
    if len(prior) < 200 + SLOPE_LOOKBACK_DAYS:
        return {"ticker": raw_ticker, "date": event_date.isoformat(), "pattern": pattern,
                "status": "insufficient_history"}

    closes = prior["close"]
    pre_gap_close = closes.iloc[-1]

    sma200_now = closes.iloc[-200:].mean()
    sma200_prior = closes.iloc[-200 - SLOPE_LOOKBACK_DAYS:-SLOPE_LOOKBACK_DAYS].mean()
    sma200_slope_pct = (sma200_now / sma200_prior - 1) * 100

    sma50_now = closes.iloc[-50:].mean()
    sma50_prior = closes.iloc[-50 - SLOPE_LOOKBACK_DAYS:-SLOPE_LOOKBACK_DAYS].mean()
    sma50_slope_pct = (sma50_now / sma50_prior - 1) * 100

    return {
        "ticker": raw_ticker, "date": event_date.isoformat(), "pattern": pattern, "status": "OK",
        "price_vs_sma200_pct": (pre_gap_close / sma200_now - 1) * 100,
        "sma200_slope_pct": sma200_slope_pct,
        "sma200_slope_negative": sma200_slope_pct < 0,
        "price_vs_sma50_pct": (pre_gap_close / sma50_now - 1) * 100,
        "sma50_slope_pct": sma50_slope_pct,
        "sma50_slope_negative": sma50_slope_pct < 0,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    events = load_events()
    if args.smoke_test:
        events = events[:20]
    print(f"{len(events)} labeled events loaded from EP V5.xlsx")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(analyze_event, e["ticker"], e["event_date"], e["pattern"]): e
            for e in events
        }
        exception_count = 0
        with tqdm(total=len(futures), desc="MA trend analysis", unit="event") as pbar:
            for fut in as_completed(futures):
                e = futures[fut]
                try:
                    r = fut.result()
                except Exception as ex:
                    exception_count += 1
                    r = {"ticker": e["ticker"], "date": e["event_date"].isoformat(), "pattern": e["pattern"],
                         "status": f"exception: {type(ex).__name__}: {ex}"}
                results.append(r)
                pbar.update(1)
        if exception_count:
            print(f"\n{exception_count} events hit an unexpected exception (recorded in 'status').")

    df = pd.DataFrame(results)
    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {len(df)} rows to {OUTPUT_CSV}")
    print(f"status counts: {df['status'].value_counts().to_dict()}")

    ok = df[df["status"] == "OK"].copy()
    print(f"\n{len(ok)} events with complete 200D+slope history\n")

    # NOTE: aggregate the *_negative boolean columns directly, not via the raw numeric
    # columns' own (s < 0) comparison recomputed here -- those booleans go missing (NaN)
    # for non-OK rows when the results list (mixed-key dicts) becomes a DataFrame, which
    # upcasts the whole column to object dtype; .mean() on that object column silently
    # returns garbage instead of erroring. Recomputing from the numeric column each time
    # sidesteps the bad dtype entirely. Confirmed live 2026-09 -- don't reintroduce the
    # precomputed boolean columns into this aggregation.
    summary = ok.groupby("pattern").agg(
        n=("pattern", "size"),
        pct_below_sma200=("price_vs_sma200_pct", lambda s: (s < 0).mean() * 100),
        pct_sma200_slope_neg=("sma200_slope_pct", lambda s: (s < 0).mean() * 100),
        median_sma200_slope_pct=("sma200_slope_pct", "median"),
        pct_below_sma50=("price_vs_sma50_pct", lambda s: (s < 0).mean() * 100),
        pct_sma50_slope_neg=("sma50_slope_pct", lambda s: (s < 0).mean() * 100),
        median_sma50_slope_pct=("sma50_slope_pct", "median"),
    ).sort_values("pct_sma200_slope_neg", ascending=False)

    pd.set_option("display.width", 140)
    print(summary.round(1).to_string())


if __name__ == "__main__":
    main()
