"""
Dry-run data puller: for each ticker in the IPO universe CSV, pull daily OHLCV
from Polygon and compute IPO (list) date, all-time high, and all-time low.
No expectancy/trade logic here -- just the raw data columns for a manual Excel pass.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm

load_dotenv()

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

INPUT_CSV = os.path.join("Downloads", "IPO as of 7-1-25.csv")
OUTPUT_CSV = os.path.join("Output", "polygon_ipo_dry_run.csv")

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
MAX_WORKERS = 20
GAIN_WINDOWS_TRADING_DAYS = {
    "1m": 21,
    "3m": 63,
    "6m": 126,
    "1y": 252,
}

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
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def clean_ticker(raw_ticker):
    return raw_ticker.split("^")[0].strip()


def get_ticker_details(ticker):
    data = api_get(f"/v3/reference/tickers/{ticker}")
    if data and "results" in data and data["results"].get("list_date"):
        return data["results"]

    # Ticker may be delisted; the plain lookup only covers currently-active
    # tickers, so find its delisted_utc and re-query as-of a date it was live.
    search = api_get("/v3/reference/tickers", {"ticker": ticker, "active": "false", "limit": 1})
    if not search or not search.get("results"):
        return None
    delisted_utc = search["results"][0].get("delisted_utc")
    if not delisted_utc:
        return None
    as_of = (datetime.fromisoformat(delisted_utc.replace("Z", "+00:00")).date()
             - pd.Timedelta(days=30)).isoformat()
    data = api_get(f"/v3/reference/tickers/{ticker}", {"date": as_of})
    if not data or "results" not in data:
        return None
    return data["results"]


def get_daily_bars(ticker, from_date, to_date):
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if not data or not data.get("results"):
        return []
    return data["results"]


def best_rolling_gain(closes, bar_dates, window):
    """Max close-to-close return over any `window`-trading-day span, plus when it happened."""
    if len(closes) <= window:
        return None, None, None
    rolling_gain = closes / closes.shift(window) - 1
    if not rolling_gain.notna().any():
        return None, None, None
    best_idx = int(rolling_gain.idxmax())
    return (round(rolling_gain.iloc[best_idx] * 100, 2),
            bar_dates[best_idx - window],
            bar_dates[best_idx])


def load_universe(path):
    df = pd.read_csv(path, skiprows=3)
    df = df.loc[:, ~df.columns.str.startswith("Unnamed")]
    return df[["Ticker", "Name", "Sector"]].dropna(subset=["Ticker"])


def process_ticker(raw_ticker, name, csv_sector, today):
    ticker = clean_ticker(raw_ticker)

    details = get_ticker_details(ticker)
    list_date = details.get("list_date") if details else None
    if not list_date:
        return {"ticker": raw_ticker, "clean_ticker": ticker, "name": name,
                "sector": csv_sector, "status": "ticker_not_found"}

    bars = get_daily_bars(ticker, list_date, today)
    if not bars:
        return {"ticker": raw_ticker, "clean_ticker": ticker, "name": name,
                "sector": csv_sector, "ipo_date": list_date, "status": "no_price_data"}

    ath_bar = max(bars, key=lambda b: b["h"])
    atl_bar = min(bars, key=lambda b: b["l"])
    last_bar = bars[-1]
    data_start_date = datetime.fromtimestamp(bars[0]["t"] / 1000, tz=timezone.utc).date().isoformat()
    # Plan's historical data floor can post-date list_date, which would
    # silently understate ATH/ATL for older IPOs -- flag rather than hide it.
    data_incomplete = data_start_date > list_date

    bar_dates = [datetime.fromtimestamp(b["t"] / 1000, tz=timezone.utc).date().isoformat() for b in bars]
    closes = pd.Series([b["c"] for b in bars])

    gain_columns = {}
    for label, window in GAIN_WINDOWS_TRADING_DAYS.items():
        pct, start_date, end_date = best_rolling_gain(closes, bar_dates, window)
        gain_columns[f"best_gain_{label}_pct"] = pct
        gain_columns[f"best_gain_{label}_start_date"] = start_date
        gain_columns[f"best_gain_{label}_end_date"] = end_date

    return {
        "ticker": raw_ticker,
        "clean_ticker": ticker,
        "name": name,
        "sector": csv_sector,
        "sic_code": details.get("sic_code"),
        "sic_description": details.get("sic_description"),
        "ipo_date": list_date,
        "data_start_date": data_start_date,
        "data_incomplete": data_incomplete,
        "ath_price": ath_bar["h"],
        "ath_date": datetime.fromtimestamp(ath_bar["t"] / 1000, tz=timezone.utc).date().isoformat(),
        "atl_price": atl_bar["l"],
        "atl_date": datetime.fromtimestamp(atl_bar["t"] / 1000, tz=timezone.utc).date().isoformat(),
        "last_close": last_bar["c"],
        "last_date": datetime.fromtimestamp(last_bar["t"] / 1000, tz=timezone.utc).date().isoformat(),
        "trading_days": len(bars),
        **gain_columns,
        "status": "ok",
    }


def main():
    universe = load_universe(INPUT_CSV)
    today = date.today().isoformat()
    records = list(universe.itertuples(index=False))
    rows = [None] * len(records)

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_ticker, r.Ticker, r.Name, r.Sector, today): i
            for i, r in enumerate(records)
        }
        with tqdm(total=len(futures), desc="Pulling Polygon data", unit="ticker") as pbar:
            for future in as_completed(futures):
                idx = futures[future]
                rows[idx] = future.result()
                pbar.update(1)

    os.makedirs("Output", exist_ok=True)
    pd.DataFrame(rows).to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {len(rows)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
