"""
For every ticker/event-date row in All EP Scan.xlsx, pull that day's actual
Open and Close from Polygon and write them as two new columns.
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

import openpyxl
import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm

load_dotenv()

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

INPUT_XLSX = os.path.join("Files", "EP", "All EP Scan.xlsx")
SHEET_NAME = "OG No Dupes"

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
MAX_WORKERS = 20

SESSION = requests.Session()
_adapter = HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS)
SESSION.mount("https://", _adapter)


def api_get(path, params=None):
    params = dict(params or {})
    params["apiKey"] = POLYGON_API_KEY
    url = f"{BASE_URL}{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        resp = SESSION.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def clean_ticker(raw_ticker):
    t = raw_ticker.split("^")[0].strip()
    if "." in t:
        base, suffix = t.rsplit(".", 1)
        if suffix.isdigit():
            t = base
    return t


def get_daily_bars(ticker, from_date, to_date):
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if data is None or not data.get("results"):
        return None
    df = pd.DataFrame(data["results"])
    df["date"] = df["t"].apply(lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date())
    return df[["date", "o", "c"]].rename(columns={"o": "open", "c": "close"})


def load_events(limit=None):
    wb = openpyxl.load_workbook(INPUT_XLSX, data_only=True)
    ws = wb[SHEET_NAME]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    events = []
    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        ticker_raw = row[idx["Ticker"]]
        event_date = row[idx["Full Date"]]
        if not ticker_raw or not event_date:
            continue
        events.append({
            "row": row_num,
            "ticker": clean_ticker(ticker_raw),
            "event_date": date.fromisoformat(str(event_date)),
        })
    if limit:
        events = events[:limit]
    return events


def process_ticker_events(ticker, ticker_events):
    lo = min(e["event_date"] for e in ticker_events)
    hi = max(e["event_date"] for e in ticker_events)
    bars = get_daily_bars(ticker, lo.isoformat(), hi.isoformat())

    results = {}
    for e in ticker_events:
        if bars is None:
            results[e["row"]] = (None, None)
            continue
        match = bars[bars["date"] == e["event_date"]]
        if match.empty:
            results[e["row"]] = (None, None)
            continue
        results[e["row"]] = (match["open"].iloc[0], match["close"].iloc[0])
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only process first N event rows (testing)")
    parser.add_argument("--dry-run", action="store_true", help="Print results, don't write to the Excel file")
    args = parser.parse_args()

    events = load_events(limit=args.limit)
    by_ticker = {}
    for e in events:
        by_ticker.setdefault(e["ticker"], []).append(e)

    print(f"{len(events)} event rows across {len(by_ticker)} unique tickers")

    all_results = {}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_ticker_events, ticker, ticker_events): ticker
            for ticker, ticker_events in by_ticker.items()
        }
        with tqdm(total=len(futures), desc="Pulling gap-day OHLC", unit="ticker") as pbar:
            for future in as_completed(futures):
                all_results.update(future.result())
                pbar.update(1)

    if args.dry_run:
        preview_rows = []
        for e in events:
            o, c = all_results.get(e["row"], (None, None))
            preview_rows.append({
                "ticker": e["ticker"], "event_date": e["event_date"].isoformat(),
                "open": o, "close": c,
            })
        print(pd.DataFrame(preview_rows).to_string(index=False))
        return

    wb = openpyxl.load_workbook(INPUT_XLSX, data_only=False)
    ws = wb[SHEET_NAME]
    header = [c.value for c in ws[1]]
    open_col = len(header) + 1
    close_col = len(header) + 2
    ws.cell(row=1, column=open_col, value="Gap Day Open")
    ws.cell(row=1, column=close_col, value="Gap Day Close")

    missing = 0
    for e in events:
        o, c = all_results.get(e["row"], (None, None))
        if o is None:
            missing += 1
        ws.cell(row=e["row"], column=open_col, value=o if o is not None else "N/A")
        ws.cell(row=e["row"], column=close_col, value=c if c is not None else "N/A")

    wb.save(INPUT_XLSX)
    print(f"\nWrote {len(events)} rows to {INPUT_XLSX} ({missing} rows N/A)")


if __name__ == "__main__":
    main()
