"""
Pull + cache split-adjusted daily OHLCV from Polygon, one Parquet file per ticker.

Unlike Scripts/pull_daily_bars.py (which caps the forward buffer at 60 calendar days
past the event, built for a fixed-horizon MFE study), V1 allows unbounded holding
periods (frozen spec Section 57) -- every ticker is pulled from well before its
earliest EP V5 event through "today", with no forward cap.
"""

import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

from . import config

sys.path.insert(0, os.path.join(os.path.dirname(config.EP_V5_XLSX), "..", "..", "Scripts"))
from build_v2_features import resolve_historical_ticker  # noqa: E402

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
BUFFER_BEFORE_DAYS = 400  # comfortably covers the 10SMA warm-up (needs >=10 sessions)

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=20))


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
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def _fetch(ticker: str, from_date: str, to_date: str):
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if data is None or not data.get("results"):
        return None
    df = pd.DataFrame(data["results"])
    df["date"] = df["t"].apply(lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date())
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap"})
    return df[["date", "open", "high", "low", "close", "volume", "vwap"]].sort_values("date").reset_index(drop=True)


def pull_ticker_daily_bars(ticker: str, earliest_event: date, refresh: bool = False) -> pd.DataFrame:
    """Fetch+cache one ticker's daily bar history. Returns the cached/fetched DataFrame."""
    out_path = os.path.join(config.DAILY_BARS_DIR, f"{ticker}.parquet")
    if not refresh and os.path.exists(out_path):
        return pd.read_parquet(out_path)

    from_date = (earliest_event - timedelta(days=BUFFER_BEFORE_DAYS)).isoformat()
    to_date = date.today().isoformat()

    df = _fetch(ticker, from_date, to_date)
    resolved_ticker = ticker
    if df is None or df.empty:
        resolved = resolve_historical_ticker(ticker, earliest_event)
        if resolved != ticker:
            df = _fetch(resolved, from_date, to_date)
            resolved_ticker = resolved

    if df is None:
        df = pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume", "vwap"])

    df.attrs["resolved_ticker"] = resolved_ticker
    os.makedirs(config.DAILY_BARS_DIR, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df


if __name__ == "__main__":
    import argparse

    from .load_events import load_ep_v5

    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--workers", type=int, default=15)
    args = parser.parse_args()

    from concurrent.futures import ThreadPoolExecutor, as_completed

    from tqdm import tqdm

    events = load_ep_v5()
    earliest_by_ticker = events.groupby("ticker")["reaction_date"].min().to_dict()
    tickers = sorted(earliest_by_ticker.items())
    if args.limit:
        tickers = tickers[: args.limit]

    print(f"{len(tickers)} unique tickers to pull daily bars for")
    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(pull_ticker_daily_bars, t, d, args.refresh): t for t, d in tickers
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="daily bars"):
            t = futures[fut]
            try:
                df = fut.result()
                results.append((t, len(df)))
            except Exception as exc:  # noqa: BLE001
                results.append((t, f"ERROR: {exc}"))

    empty = [t for t, n in results if n == 0]
    errored = [t for t, n in results if isinstance(n, str)]
    print(f"done. {len(results) - len(empty) - len(errored)} ok, {len(empty)} empty, {len(errored)} errored")
    if errored:
        print("errored tickers:", errored[:20])
