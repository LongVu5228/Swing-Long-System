"""
Audit the master EP dataset for the SMCI-style AMC (after-market-close reporter) bug:
LatestNewsDate records the actual news RELEASE day, but if the company reported after
that day's close, the market doesn't react until the NEXT trading session's open. If
P123's @d/@GapPct formula anchors on the release day instead of the reaction day, the
recorded gap can be a small, non-representative move while the REAL (larger) gap
happens on the following trading day -- exactly what happened with SMCI.

For every event in Master Order of Tickers.xlsx, compute:
  this_day_gap_pct  = Open(Full Date) / Close(prior trading day) - 1   (what's "recorded")
  next_day_gap_pct  = Open(Full Date + 1 trading day) / Close(Full Date) - 1

Flags a row as suspicious if next_day_gap_pct is itself >= 5% (a real qualifying gap
sitting one day later that the current row doesn't capture) -- especially when it's
larger than this_day_gap_pct, which is the SMCI pattern (small move on the release
day, real move the day after).

This only audits what's ALREADY in the dataset -- it cannot recover true false
negatives (AMC reporters whose release-day move never exceeded 5%, so they were never
captured by the P123 screen at all). That would require re-running candidate discovery
with a corrected methodology, which is a separate, bigger task.
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import openpyxl
import pandas as pd
import requests
from openpyxl.utils.datetime import from_excel
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(__file__))
from build_v2_features import clean_ticker, resolve_historical_ticker

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

MASTER_ORDER_XLSX = os.path.join("Files", "EP", "Master Order of tickers", "Master Order of Tickers.xlsx")
OUTPUT_DIR = os.path.join("Files", "EP", "Data Pulls")

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
MAX_WORKERS = 10
GAP_THRESHOLD = 5.0  # matches the user's own >=5% qualifying gap rule

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS))


def api_get(path, params=None):
    params = dict(params or {})
    params["apiKey"] = POLYGON_API_KEY
    url = f"{BASE_URL}{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def get_daily_bars(ticker, from_date, to_date):
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if data is None or not data.get("results"):
        return None
    df = pd.DataFrame(data["results"])
    df["date"] = df["t"].apply(lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date())
    return df[["date", "o", "c"]].rename(columns={"o": "open", "c": "close"}).sort_values("date").reset_index(drop=True)


def process_ticker(ticker, ticker_events):
    lo = min(e["event_date"] for e in ticker_events) - timedelta(days=15)
    hi = min(date.today(), max(e["event_date"] for e in ticker_events) + timedelta(days=15))
    if lo > hi:
        return {e["row"]: None for e in ticker_events}

    bars = get_daily_bars(ticker, lo.isoformat(), hi.isoformat())
    if bars is None:
        resolved = resolve_historical_ticker(ticker, min(e["event_date"] for e in ticker_events))
        if resolved != ticker:
            bars = get_daily_bars(resolved, lo.isoformat(), hi.isoformat())

    results = {}
    for e in ticker_events:
        if bars is None:
            results[e["row"]] = None
            continue
        idx = bars.index[bars["date"] == e["event_date"]]
        if len(idx) == 0 or idx[0] == 0 or idx[0] + 1 >= len(bars):
            results[e["row"]] = None
            continue
        i = idx[0]
        prior_close = bars["close"].iloc[i - 1]
        this_open = bars["open"].iloc[i]
        this_close = bars["close"].iloc[i]
        next_open = bars["open"].iloc[i + 1]
        this_gap = (this_open / prior_close - 1) * 100 if prior_close else None
        next_gap = (next_open / this_close - 1) * 100 if this_close else None
        results[e["row"]] = {"this_day_gap_pct": this_gap, "next_day_gap_pct": next_gap,
                              "next_day": bars["date"].iloc[i + 1]}
    return results


def load_master_order(limit=None):
    wb = openpyxl.load_workbook(MASTER_ORDER_XLSX, data_only=True)
    ws = wb["Sheet1"]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    events = []
    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        ticker_raw = row[idx["Ticker"]]
        fd = row[idx["Full Date"]]
        if not ticker_raw or fd is None:
            continue
        if isinstance(fd, datetime):
            event_date = fd.date()
        elif isinstance(fd, (int, float)):
            event_date = from_excel(fd).date()
        else:
            event_date = date.fromisoformat(str(fd))
        events.append({"row": row_num, "ticker_raw": ticker_raw, "ticker": clean_ticker(ticker_raw),
                        "event_date": event_date})
    if limit:
        events = events[:limit]
    return events


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    events = load_master_order(limit=args.limit)
    by_ticker = {}
    for e in events:
        by_ticker.setdefault(e["ticker"], []).append(e)
    print(f"{len(events)} event rows across {len(by_ticker)} unique tickers")

    all_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_ticker, t, evs): t for t, evs in by_ticker.items()}
        with tqdm(total=len(futures), desc="Auditing AMC gap offset", unit="ticker") as pbar:
            for future in as_completed(futures):
                all_results.update(future.result())
                pbar.update(1)

    out_rows = []
    flagged = 0
    no_data = 0
    for e in events:
        r = all_results.get(e["row"])
        if r is None:
            no_data += 1
            out_rows.append({"Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
                             "This Day Gap %": "N/A", "Next Day Gap %": "N/A", "Next Trading Day": "N/A",
                             "Suspicious (AMC offset)?": "N/A"})
            continue
        this_gap, next_gap = r["this_day_gap_pct"], r["next_day_gap_pct"]
        # SMCI signature: the *recorded* gap is small/unremarkable but a bigger real gap is
        # hiding one trading day later -- not just any continuation move (e.g. STX: 15% then
        # a normal 6% follow-through day isn't a mislabeling bug, it's just momentum).
        suspicious = (
            next_gap is not None and next_gap >= GAP_THRESHOLD
            and (this_gap is None or this_gap < GAP_THRESHOLD or next_gap > this_gap * 1.5)
        )
        if suspicious:
            flagged += 1
        out_rows.append({
            "Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
            "This Day Gap %": round(this_gap, 2) if this_gap is not None else "N/A",
            "Next Day Gap %": round(next_gap, 2) if next_gap is not None else "N/A",
            "Next Trading Day": r["next_day"].isoformat(),
            "Suspicious (AMC offset)?": "Y" if suspicious else "N",
        })

    print(f"\nNo data: {no_data} / {len(events)}")
    print(f"Flagged as suspicious (next-day gap >= {GAP_THRESHOLD}%): {flagged} / {len(events)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, "AMC Gap Offset Audit.xlsx")
    try:
        pd.DataFrame(out_rows).to_excel(out_path, index=False)
        print(f"Wrote {out_path}")
    except PermissionError:
        print(f"Could not write {out_path} (likely open in Excel)")


if __name__ == "__main__":
    main()
