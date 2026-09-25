"""
Compute the Chillax Moving Average trend color (chillax_moving_averages.pine) for
SPY, as of each event's gap-up day, and write it to a standalone file in Data Pulls/
matched to Master Order of Tickers.xlsx row order.

Rules (from the .pine file, MA1=10d SMA, MA2=20d SMA, trendlen=5 bars, all of
close, all computed using only bars up to and including the event date -- no
lookahead):
  Green       : MA1 > MA2, and both MA1 and MA2 trending up (> value 5 bars ago)
  Light Green : MA1 > MA2, MA1 trending up but MA2 not
  Yellow      : MA1 > MA2, neither trending up
  Downtrend   : MA1 <= MA2 (everything the original indicator leaves uncolored)

Only one Polygon call needed -- SPY is a single continuous series covering the
whole date range, unlike the per-ticker pulls we've done elsewhere.
"""

import os
import sys
import time
from datetime import date, datetime, timezone

import openpyxl
import pandas as pd
import requests
from openpyxl.utils.datetime import from_excel
from dotenv import load_dotenv

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

MASTER_ORDER_XLSX = os.path.join("Files", "EP", "Master Order of tickers", "Master Order of Tickers.xlsx")
OUTPUT_DIR = os.path.join("Files", "EP", "Data Pulls")

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
MA1_LEN = 10
MA2_LEN = 20
TREND_LEN = 5


def api_get(path, params=None):
    params = dict(params or {})
    params["apiKey"] = POLYGON_API_KEY
    url = f"{BASE_URL}{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        resp = requests.get(url, params=params, timeout=30)
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def get_spy_daily():
    today = date.today().isoformat()
    data = api_get("/v2/aggs/ticker/SPY/range/1/day/2000-01-01/" + today,
                    {"adjusted": "true", "sort": "asc", "limit": 50000})
    if not data or not data.get("results"):
        sys.exit("Could not pull SPY daily bars.")
    df = pd.DataFrame(data["results"])
    df["date"] = df["t"].apply(lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date())
    df = df[["date", "c"]].rename(columns={"c": "close"}).sort_values("date").reset_index(drop=True)

    df["ma1"] = df["close"].rolling(MA1_LEN).mean()
    df["ma2"] = df["close"].rolling(MA2_LEN).mean()
    df["ma1_up"] = df["ma1"] > df["ma1"].shift(TREND_LEN)
    df["ma2_up"] = df["ma2"] > df["ma2"].shift(TREND_LEN)

    def classify(row):
        if pd.isna(row["ma1"]) or pd.isna(row["ma2"]) or pd.isna(row["ma1_up"]) or pd.isna(row["ma2_up"]):
            return None
        if row["ma1"] > row["ma2"] and row["ma1_up"] and row["ma2_up"]:
            return "Green"
        if row["ma1"] > row["ma2"] and row["ma1_up"] and not row["ma2_up"]:
            return "Light Green"
        if row["ma1"] > row["ma2"] and not row["ma1_up"] and not row["ma2_up"]:
            return "Yellow"
        return "Downtrend"  # everything else, incl. ma1 <= ma2 -- matches the .pine's uncolored case

    df["color"] = df.apply(classify, axis=1)
    return df


def load_master_order():
    wb = openpyxl.load_workbook(MASTER_ORDER_XLSX, data_only=True)
    ws = wb["Sheet1"]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    events = []
    for row in ws.iter_rows(min_row=2, values_only=True):
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
        events.append({"ticker_raw": ticker_raw, "event_date": event_date})
    return events


def main():
    print("Pulling SPY daily history...")
    spy = get_spy_daily()
    print(f"{len(spy)} SPY daily bars, {spy['color'].notna().sum()} with a valid trend color")

    events = load_master_order()
    print(f"{len(events)} event rows to classify")

    spy_indexed = spy.set_index("date")
    dates_sorted = spy["date"].values

    import numpy as np
    out_rows = []
    for e in events:
        pos = np.searchsorted(dates_sorted, e["event_date"], side="right") - 1
        if pos < 0:
            row = {"Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
                   "SPY MA1 (10d)": "N/A", "SPY MA2 (20d)": "N/A",
                   "SPY MA1 Trending Up": "N/A", "SPY MA2 Trending Up": "N/A",
                   "SPY Trend Color": "N/A"}
        else:
            r = spy.iloc[pos]
            color = r["color"]
            row = {"Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
                   "SPY MA1 (10d)": r["ma1"] if pd.notna(r["ma1"]) else "N/A",
                   "SPY MA2 (20d)": r["ma2"] if pd.notna(r["ma2"]) else "N/A",
                   "SPY MA1 Trending Up": bool(r["ma1_up"]) if pd.notna(r["ma1_up"]) else "N/A",
                   "SPY MA2 Trending Up": bool(r["ma2_up"]) if pd.notna(r["ma2_up"]) else "N/A",
                   "SPY Trend Color": color if color is not None else "N/A"}
        out_rows.append(row)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    out_path = os.path.join(OUTPUT_DIR, f"SPY Trend Color - {date.today().isoformat()}.xlsx")
    cols = ["Full Date", "Ticker", "SPY MA1 (10d)", "SPY MA2 (20d)",
            "SPY MA1 Trending Up", "SPY MA2 Trending Up", "SPY Trend Color"]
    pd.DataFrame(out_rows, columns=cols).to_excel(out_path, index=False)
    print(f"\nWrote {len(out_rows)} rows to {out_path}")

    counts = pd.Series([r["SPY Trend Color"] for r in out_rows]).value_counts()
    print("\nColor breakdown:")
    print(counts.to_string())


if __name__ == "__main__":
    main()
