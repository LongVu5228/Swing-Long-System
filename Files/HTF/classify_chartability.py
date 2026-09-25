"""
Classifies each unique ticker in htf_1m_flag_review_by_date.csv as "likely chartable" on
a standard retail charting platform (TradingView) vs. "low confidence" -- NOT by deleting
rows (that would introduce real survivorship bias, e.g. dropping DRYS just because it's
delisted today would delete a completely real, huge 2007-2008 move) but by adding a
separate lookup table the user can filter/sort by in their own in-progress review copy,
without me touching that file directly (same reasoning as the project's existing
no-direct-writes-to-pivot-files rule -- don't risk a user's in-progress manual work).

The proxy: "was this a real common stock / ADR primary-listed on a major US exchange"
(NYSE/NASDAQ/NYSE American/NYSE Arca), via Polygon's reference/tickers endpoint with
active=false (so delisted names are still found, e.g. DRYS -> AIRTRAN-style real
history). This is a PROXY for "TradingView still has historical chart data," not a
direct verification -- no API here can check TradingView's own coverage -- so it's
reported as a confidence tier, not a guarantee, and nothing gets deleted from the
master file either way.

Usage:
    python classify_chartability.py --smoke-test   # first 10 tickers only
    python classify_chartability.py                 # full run, all OK-status tickers
"""
import argparse
import os
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import requests
from dotenv import load_dotenv
from tqdm import tqdm

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
load_dotenv(os.path.join(REPO_ROOT, ".env"))
POLYGON_API_KEY = os.environ["POLYGON_API_KEY"]

REVIEW_CSV = os.path.join(os.path.dirname(__file__), "htf_1m_flag_review_by_date.csv")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "chartability_lookup.csv")

MAJOR_EXCHANGES = {"XNYS", "XNAS", "XASE", "ARCX"}  # NYSE, NASDAQ, NYSE American, NYSE Arca


def _lookup(ticker: str, active_val: str) -> dict:
    resp = requests.get(
        "https://api.polygon.io/v3/reference/tickers",
        params={"apiKey": POLYGON_API_KEY, "ticker": ticker, "active": active_val, "limit": 5},
        timeout=30,
    )
    results = resp.json().get("results", []) if resp.status_code == 200 else []
    return results[0] if results else None


def classify(raw_ticker: str, revised_ticker: str) -> dict:
    ticker = revised_ticker if isinstance(revised_ticker, str) and revised_ticker else raw_ticker
    # "active" is an EXACT filter on Polygon's side (confirmed live 2026-09-14), not an
    # include/exclude toggle -- active=false returns [] for a currently-listed ticker like
    # ABT, and omitting the param defaults to active=true only. Must try both explicitly.
    r = _lookup(ticker, "true") or _lookup(ticker, "false")
    if r is None:
        return {"ticker": raw_ticker, "revised_ticker": ticker, "name": None,
                "primary_exchange": None, "type": None, "active": None,
                "chartability": "unknown_not_in_polygon"}

    exch = r.get("primary_exchange")
    typ = r.get("type")
    # type is sometimes missing/None even for a real major-exchange common stock (AMLN
    # confirmed live 2026-09-14) -- don't let a missing field alone downgrade an otherwise
    # clear major-exchange match. Only disqualify on a type that's POSITIVELY something
    # else (ETF, WARRANT, RIGHT, UNIT, PFD, etc.), not on type simply being unknown.
    type_ok = typ is None or typ in ("CS", "ADRC", "ADRR")
    tier = "likely_chartable" if (r.get("market") == "stocks" and exch in MAJOR_EXCHANGES
                                   and type_ok) else "low_confidence"
    return {
        "ticker": raw_ticker, "revised_ticker": ticker, "name": r.get("name"),
        "primary_exchange": exch, "type": typ, "active": r.get("active"),
        "chartability": tier,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--workers", type=int, default=15)
    args = parser.parse_args()

    df = pd.read_csv(REVIEW_CSV)
    ok = df[df["status"] == "OK"][["ticker", "revised_ticker"]].drop_duplicates()
    if args.smoke_test:
        ok = ok.head(10)
    print(f"classifying {len(ok):,} unique tickers")

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(classify, row.ticker, row.revised_ticker): row.ticker
            for row in ok.itertuples()
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="classifying"):
            results.append(fut.result())

    out = pd.DataFrame(results)
    out_path = OUTPUT_CSV.replace(".csv", "_SMOKETEST.csv") if args.smoke_test else OUTPUT_CSV
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out):,} rows to {out_path}")
    print(out["chartability"].value_counts())


if __name__ == "__main__":
    main()
