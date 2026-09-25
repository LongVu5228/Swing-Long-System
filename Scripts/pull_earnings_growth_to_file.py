"""
Pull EPS YoY Growth % and Revenue YoY Growth % for each event in Master Order of
Tickers.xlsx, from Polygon's /vX/reference/financials (actuals from SEC filings --
no consensus estimates needed for this, so no Benzinga add-on required).

For each event: find the fiscal quarter whose filing_date is closest to the event
date (this is the quarter that was just reported and triggered the gap), then find
the SAME fiscal quarter one year earlier for the same ticker, and compute YoY growth
on diluted EPS and revenue. Output goes to a standalone file in Data Pulls/, row-
aligned to Master Order of Tickers -- not written into any working file directly.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

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
MAX_REPORTING_LAG_DAYS = 100  # event date vs period end_date -- catches "not filed yet" cases

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


def get_financials(ticker, timeframe, limit):
    data = api_get("/vX/reference/financials", {
        "ticker": ticker, "timeframe": timeframe, "limit": limit, "sort": "filing_date", "order": "desc",
    })
    if not data or not data.get("results"):
        return []
    out = []
    for r in data["results"]:
        inc = r.get("financials", {}).get("income_statement", {})
        eps = inc.get("diluted_earnings_per_share", {}).get("value")
        if eps is None:
            eps = inc.get("basic_earnings_per_share", {}).get("value")
        rev = inc.get("revenues", {}).get("value")
        fy = r.get("fiscal_year")
        end_date = r.get("end_date")
        if end_date is None:
            continue
        out.append({
            "fiscal_period": r.get("fiscal_period"), "fiscal_year": int(fy) if fy is not None else None,
            "filing_date": r.get("filing_date"), "end_date": date.fromisoformat(end_date),
            "eps": eps, "revenue": rev,
        })
    return out


def get_reporting_periods(ticker):
    # Q4 is often absent from the "quarterly" bucket (folded into the annual 10-K),
    # so pull both and merge -- matching by period end_date, not filing_date, since
    # filing lag after the actual earnings release varies wildly by company.
    quarterly = get_financials(ticker, "quarterly", limit=32)  # ~8 years back -- covers the 2021-2026 event range plus prior-year lookups
    annual = get_financials(ticker, "annual", limit=10)
    return quarterly, annual


def find_growth(quarterly, annual, event_date):
    all_periods = [(q, "quarterly") for q in quarterly] + [(a, "annual") for a in annual]
    candidates = [(p, kind) for p, kind in all_periods if p["end_date"] <= event_date]
    if not candidates:
        return None
    current, kind = max(candidates, key=lambda pk: pk[0]["end_date"])
    if (event_date - current["end_date"]).days > MAX_REPORTING_LAG_DAYS:
        return None  # most recent completed period is too old -- this quarter likely not filed yet

    bucket = quarterly if kind == "quarterly" else annual
    prior = next((q for q in bucket
                  if q["fiscal_period"] == current["fiscal_period"]
                  and q["fiscal_year"] == current["fiscal_year"] - 1), None)

    label = f"{current['fiscal_period']} {current['fiscal_year']}" if kind == "quarterly" else f"FY {current['fiscal_year']}"
    result = {
        "fiscal_period": label,
        "filing_date": current["filing_date"], "period_end_date": current["end_date"].isoformat(),
        "eps_current": current["eps"], "revenue_current": current["revenue"],
        "eps_prior_year": prior["eps"] if prior else None,
        "revenue_prior_year": prior["revenue"] if prior else None,
    }
    if prior and current["eps"] is not None and prior["eps"] not in (None, 0):
        result["eps_yoy_growth_pct"] = (current["eps"] - prior["eps"]) / abs(prior["eps"]) * 100
    else:
        result["eps_yoy_growth_pct"] = None
    if prior and current["revenue"] is not None and prior["revenue"] not in (None, 0):
        result["revenue_yoy_growth_pct"] = (current["revenue"] - prior["revenue"]) / abs(prior["revenue"]) * 100
    else:
        result["revenue_yoy_growth_pct"] = None
    return result


def process_ticker(ticker, ticker_events):
    quarterly, annual = get_reporting_periods(ticker)
    resolved = ticker
    if not quarterly and not annual:
        alt = resolve_historical_ticker(ticker, min(e["event_date"] for e in ticker_events))
        if alt != ticker:
            quarterly, annual = get_reporting_periods(alt)
            resolved = alt

    results = {}
    for e in ticker_events:
        g = find_growth(quarterly, annual, e["event_date"])
        results[e["row"]] = {"resolved_ticker": resolved, **(g or {})}
    return results


def na(v):
    return v if v is not None else "N/A"


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
    import argparse
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
        with tqdm(total=len(futures), desc="Pulling earnings growth", unit="ticker") as pbar:
            for future in as_completed(futures):
                all_results.update(future.result())
                pbar.update(1)

    out_rows = []
    matched = 0
    for e in events:
        r = all_results.get(e["row"], {})
        if r.get("fiscal_period"):
            matched += 1
        out_rows.append({
            "Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
            "Fiscal Quarter": na(r.get("fiscal_period")),
            "Period End Date": na(r.get("period_end_date")),
            "Filing Date": na(r.get("filing_date")),
            "EPS (Current Q)": na(r.get("eps_current")),
            "EPS (Same Q Prior Year)": na(r.get("eps_prior_year")),
            "EPS YoY Growth %": na(r.get("eps_yoy_growth_pct")),
            "Revenue (Current Q)": na(r.get("revenue_current")),
            "Revenue (Same Q Prior Year)": na(r.get("revenue_prior_year")),
            "Revenue YoY Growth %": na(r.get("revenue_yoy_growth_pct")),
        })

    print(f"\nMatched a reporting quarter for {matched} / {len(events)} events")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"Earnings YoY Growth - {date.today().isoformat()}.xlsx")
    pd.DataFrame(out_rows).to_excel(out_path, index=False)
    print(f"Wrote {len(out_rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
