"""
Pull + cache 1-minute OHLCV for the D0..D+7 entry-search window of a single EP event.

Per the frozen V1 spec (Section 78), the simulator only ever needs minute bars for the
entry-search window -- the standardized exit (Section 26) runs entirely on daily bars.
So minute data is fetched per-event (ticker, D0), not as an open-ended per-ticker store.

One event's window is <= 8 trading sessions; this pulls them in a single ranged Polygon
call (with next_url pagination, just in case) rather than 8 separate day calls.
"""

import os
import sys
import time
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

from . import calendar_utils, config

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=20, pool_maxsize=20))


def _api_get(url, params=None):
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


def _fetch_minute_range(ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
    path = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/minute/{from_date}/{to_date}"
    params = {"apiKey": POLYGON_API_KEY, "adjusted": "true", "sort": "asc", "limit": 50000}
    all_results = []
    url, use_params = path, params
    while url:
        data = _api_get(url, use_params)
        if data is None:
            break
        all_results.extend(data.get("results") or [])
        next_url = data.get("next_url")
        if not next_url:
            break
        url, use_params = next_url, {"apiKey": POLYGON_API_KEY}

    if not all_results:
        return pd.DataFrame(columns=["dt_et", "session_date", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_results)
    df["dt_et"] = df["t"].apply(
        lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(config.ET)
    )
    df["session_date"] = df["dt_et"].apply(lambda d: d.date())
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    return df[["dt_et", "session_date", "open", "high", "low", "close", "volume"]].sort_values("dt_et").reset_index(drop=True)


def get_event_window_minute_bars(ticker: str, d0: date, refresh: bool = False) -> pd.DataFrame:
    """
    Return regular-session (9:30-16:00 ET) 1-minute bars for the 8 trading sessions
    D0..D+7 anchored on d0. Cached per (ticker, d0).
    """
    out_path = os.path.join(config.MINUTE_BARS_DIR, f"{ticker}_{d0.isoformat()}.parquet")
    if not refresh and os.path.exists(out_path):
        return pd.read_parquet(out_path)

    sessions = calendar_utils.sessions_from(d0, config.MAX_ENTRY_DAY_OFFSET + 1)  # D0..D+7
    df = _fetch_minute_range(ticker, sessions[0].isoformat(), sessions[-1].isoformat())

    if not df.empty:
        # Regular session only (Section 76): 9:30:00-16:00:00 ET. Polygon's minute
        # aggs bucket by bar start, so the 16:00 bar itself (16:00:00-16:00:59) is
        # after-hours and excluded; the last regular bar starts at 15:59.
        session_open = df["dt_et"].apply(lambda d: d.replace(hour=9, minute=30, second=0, microsecond=0))
        session_close = df["dt_et"].apply(lambda d: d.replace(hour=16, minute=0, second=0, microsecond=0))
        df = df[(df["dt_et"] >= session_open) & (df["dt_et"] < session_close)].reset_index(drop=True)

    os.makedirs(config.MINUTE_BARS_DIR, exist_ok=True)
    df.to_parquet(out_path, index=False)
    return df


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("event_date", help="YYYY-MM-DD")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    d0 = date.fromisoformat(args.event_date)
    df = get_event_window_minute_bars(args.ticker, d0, refresh=args.refresh)
    print(f"{len(df)} regular-session 1-minute bars across D0..D+7 for {args.ticker} @ {d0}")
    if not df.empty:
        print(df.groupby("session_date").size())
        print(df.head())
