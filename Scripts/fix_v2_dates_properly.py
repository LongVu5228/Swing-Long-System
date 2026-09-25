"""
Correct redo of the weekend-date fix on EP Scan V2.xlsx.

The previous fix (walking back @d trading sessions from the batch's raw scan date)
was WRONG -- verified against real Polygon price data, it produced dates where the
actual gap doesn't match the recorded @GapPct at all. The real bug is much simpler:
the raw event date is off by 1-2 calendar days (a timezone/timestamp quirk), which
only shows up when the shift happens to cross into a weekend.

This script finds the TRUE date for each of the 60 originally-weekend rows by
searching real price data for the day whose actual gap (open/prevClose - 1) matches
the recorded @GapPct, then recomputes every downstream column for just those rows.
"""

import argparse
import datetime
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date

import openpyxl
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(__file__))
from build_v2_features import (
    INPUT_XLSX, SHEET_NAME, clean_ticker, resolve_historical_ticker,
    get_daily_bars, compute_row, na, WINDOWS_MONTHS,
)

BACKUP_PRE_WEEKEND_FIX = os.path.join("Files", "EP", "EP Scan V2.backup-20260810-175925-preweekendfix.xlsx")

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=15, pool_maxsize=15))


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


def get_bars_raw(ticker, from_date, to_date):
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if not data or not data.get("results"):
        return []
    out = []
    for b in data["results"]:
        d = datetime.datetime.fromtimestamp(b["t"] / 1000, tz=datetime.timezone.utc).date()
        out.append((d, b["o"], b["c"]))
    return out


def find_true_date(ticker_raw, raw_bad_date, recorded_gap_pct, tol=0.15, search_days=60):
    ticker = clean_ticker(ticker_raw)
    lo = (raw_bad_date - datetime.timedelta(days=search_days)).isoformat()
    hi = (raw_bad_date + datetime.timedelta(days=search_days)).isoformat()
    bars = get_bars_raw(ticker, lo, hi)
    used_ticker = ticker
    if not bars:
        resolved = resolve_historical_ticker(ticker, raw_bad_date)
        if resolved != ticker:
            bars = get_bars_raw(resolved, lo, hi)
            used_ticker = resolved
    if not bars or recorded_gap_pct is None:
        return None, used_ticker

    matches = []
    for i in range(1, len(bars)):
        d, o, c = bars[i]
        prev_c = bars[i - 1][2]
        if prev_c == 0:
            continue
        gap = (o / prev_c - 1) * 100
        if abs(gap - recorded_gap_pct) < tol:
            matches.append(d)
    if not matches:
        return None, used_ticker
    matches.sort(key=lambda d: abs((d - raw_bad_date).days))
    return matches[0], used_ticker


def load_bad_rows():
    wb = openpyxl.load_workbook(BACKUP_PRE_WEEKEND_FIX, data_only=True)
    ws = wb[SHEET_NAME]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    rows = []
    for row_num, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        fd = row[idx["Full Date"]]
        if fd is None:
            continue
        bad_date = fd.date() if isinstance(fd, datetime.datetime) else date.fromisoformat(str(fd))
        if bad_date.weekday() < 5:
            continue
        rows.append({
            "row": row_num, "ticker_raw": row[idx["Ticker"]],
            "bad_date": bad_date, "gap_pct": row[idx["@GapPct"]],
        })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    bad_rows = load_bad_rows()
    print(f"{len(bad_rows)} originally-weekend rows to re-derive")

    resolved = {}
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            executor.submit(find_true_date, r["ticker_raw"], r["bad_date"], r["gap_pct"]): r
            for r in bad_rows
        }
        with tqdm(total=len(futures), desc="Finding true dates", unit="row") as pbar:
            for future in as_completed(futures):
                r = futures[future]
                true_date, used_ticker = future.result()
                resolved[r["row"]] = {**r, "true_date": true_date, "used_ticker": used_ticker}
                pbar.update(1)

    found = [r for r in resolved.values() if r["true_date"]]
    unresolved = [r for r in resolved.values() if not r["true_date"]]
    print(f"\nResolved: {len(found)} / {len(bad_rows)}")
    for r in sorted(found, key=lambda x: x["row"]):
        print(f"  {r['ticker_raw']:10s} {r['bad_date']} ({r['bad_date'].strftime('%a')}) -> {r['true_date']} ({r['true_date'].strftime('%a')})  gap={r['gap_pct']}")
    if unresolved:
        print(f"\nCould not resolve {len(unresolved)}:")
        for r in unresolved:
            print(f"  {r['ticker_raw']} {r['bad_date']} gap={r['gap_pct']}")

    if args.dry_run:
        return

    print("\nRecomputing downstream columns for resolved rows...")
    wb_vals = openpyxl.load_workbook(INPUT_XLSX, data_only=True)
    ws_vals = wb_vals[SHEET_NAME]
    header = [c.value for c in ws_vals[1]]
    idx = {h: i for i, h in enumerate(header)}

    from dateutil.relativedelta import relativedelta
    features = {}
    for r in tqdm(found, desc="Rebuilding features", unit="row"):
        event_date = r["true_date"]
        lo = event_date - relativedelta(years=1)  # plenty for ATH/prior-high context; compute_row also handles PLAN_CUTOFF internally via truncation flag logic elsewhere
        hi = min(date.today(), event_date + relativedelta(months=max(WINDOWS_MONTHS)))
        from build_v2_features import PLAN_CUTOFF
        lo = max(lo, PLAN_CUTOFF)
        bars = get_daily_bars(r["used_ticker"], lo.isoformat(), hi.isoformat())
        if bars is None:
            continue
        feat = compute_row(bars, event_date)
        features[r["row"]] = (r, feat)

    wb = openpyxl.load_workbook(INPUT_XLSX, data_only=False)
    ws = wb[SHEET_NAME]
    col_map = {name: i + 1 for i, name in enumerate(header)}

    for row_num, (r, feat) in features.items():
        ws.cell(row=row_num, column=col_map["Full Date"], value=datetime.datetime(
            r["true_date"].year, r["true_date"].month, r["true_date"].day))
        if "@EventDate" in col_map:
            ws.cell(row=row_num, column=col_map["@EventDate"], value=int(r["true_date"].strftime("%Y%m%d")))

        ws.cell(row=row_num, column=col_map["Gap Day Open"], value=na(feat["gap_open"]))
        ws.cell(row=row_num, column=col_map["Gap Day Close"], value=na(feat["gap_close"]))
        ws.cell(row=row_num, column=col_map["Prior ATH Price"], value=na(feat["ath_price"]))
        ws.cell(row=row_num, column=col_map["Prior ATH Date"], value=na(feat["ath_date"]))
        ws.cell(row=row_num, column=col_map["Prior ATH Data Truncated"], value=feat["ath_truncated"])
        for m in WINDOWS_MONTHS:
            ws.cell(row=row_num, column=col_map[f"{m}M High"], value=na(feat.get(f"high_{m}m")))
            ws.cell(row=row_num, column=col_map[f"{m}M High Date"], value=na(feat.get(f"high_{m}m_date")))
            ws.cell(row=row_num, column=col_map[f"{m}M Window Complete"], value=feat.get(f"{m}m_complete"))
            ws.cell(row=row_num, column=col_map[f"{m}M Plan Data Truncated"], value=feat.get(f"{m}m_truncated"))
            ws.cell(row=row_num, column=col_map[f"{m}M Close"], value=na(feat.get(f"close_{m}m")))
            ws.cell(row=row_num, column=col_map[f"{m}M Close Date"], value=na(feat.get(f"close_{m}m_date")))

    wb.save(INPUT_XLSX)
    print(f"\nWrote corrected dates + recomputed features for {len(features)} rows to {INPUT_XLSX}")


if __name__ == "__main__":
    main()
