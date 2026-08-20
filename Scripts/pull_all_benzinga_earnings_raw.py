"""
One-shot full-history dump of every confirmed Benzinga earnings event, all tickers,
all columns Benzinga returns -- no per-event Polygon calls, so it runs in well under
a minute regardless of range.

This is deliberately dumber than build_benzinga_candidate_list.py: it does NOT compute
gap%/ADR/liquidity/mktcap (those need daily bars per event). It just lists events and
flags which ones fall inside the plan's bars-covered window, so a later filtering pass
knows what it can and can't compute.
"""

import argparse
import os
import sys
import time
from datetime import date, timedelta

import pandas as pd
import requests
from dateutil.relativedelta import relativedelta
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

OUTPUT_DIR = os.path.join("Files", "EP", "Data Pulls")
BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
PAGE_LIMIT = 50000

# Polygon plan (upgraded 2026-08) serves daily bars for roughly the trailing 20 years --
# comfortably covers Benzinga's full earnings history (starts 2011-05-12), so this should
# stay informational rather than an actual constraint now. Kept as a flag column in case
# the plan ever changes again.
BARS_WINDOW_YEARS = 20

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=4, pool_maxsize=4))


def api_get(url, params=None):
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


def get_all_earnings(date_from=None, date_to=None, status="confirmed"):
    params = {"apiKey": POLYGON_API_KEY, "date_status": status, "limit": PAGE_LIMIT, "sort": "date.asc"}
    if date_from:
        params["date.gte"] = date_from
    if date_to:
        params["date.lte"] = date_to
    url = f"{BASE_URL}/benzinga/v1/earnings"
    out = []
    page = 0
    while url:
        data = api_get(url, params)
        params = None  # next_url already has query params baked in
        if not data:
            break
        out.extend(data.get("results", []))
        page += 1
        print(f"  page {page}: {len(out)} events so far", end="\r")
        url = data.get("next_url")
        if url and "apiKey" not in url:
            url = url + ("&" if "?" in url else "?") + f"apiKey={POLYGON_API_KEY}"
    print()
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", type=str, default=None, help="default: earliest available")
    parser.add_argument("--to-date", type=str, default=None, help="default: today")
    parser.add_argument("--status", type=str, default="confirmed")
    parser.add_argument("--label", type=str, default=None)
    args = parser.parse_args()

    print(f"Pulling ALL {args.status} Benzinga earnings events "
          f"({args.from_date or 'earliest'} -> {args.to_date or 'today'})...")
    events = get_all_earnings(args.from_date, args.to_date, args.status)
    print(f"{len(events)} events pulled")

    if not events:
        print("Nothing to write.")
        return

    df = pd.DataFrame(events)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    df = df.sort_values(["date", "ticker"]).reset_index(drop=True)

    bars_cutoff = date.today() - relativedelta(years=BARS_WINDOW_YEARS)
    df["within_bars_window"] = df["date"] >= bars_cutoff

    print(f"\nDate range: {df['date'].min()} -> {df['date'].max()}")
    print(f"Unique tickers: {df['ticker'].nunique()}")
    in_window = df["within_bars_window"].sum()
    print(f"Within current ~{BARS_WINDOW_YEARS}yr bars window (>= {bars_cutoff}, filterable now): {in_window}")
    print(f"Outside bars window (needs a plan upgrade to gap/ADR/liquidity/mktcap-filter): {len(df) - in_window}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tag = f" - {args.label}" if args.label else ""
    out_path = os.path.join(OUTPUT_DIR, f"Benzinga All Earnings Raw{tag}.xlsx")
    df["date"] = df["date"].astype(str)
    try:
        df.to_excel(out_path, index=False)
        print(f"\nWrote {out_path}")
    except PermissionError:
        print(f"Could not write {out_path} (likely open in Excel)")


if __name__ == "__main__":
    main()
