"""
Replace P123 as the EP candidate-discovery engine. Pulls EVERY confirmed Benzinga
earnings event in a date range directly (no ticker filter, no LatestNewsDate
ambiguity), resolves the true reaction date from the actual release timestamp, then
computes point-in-time gap/ADR/liquidity/market-cap features from Polygon on that
resolved date and applies the original qualifying filters.

release_timing resolution (from Benzinga's `time` field, ET):
  time <  09:30:00           -> BEFORE_OPEN   -> reaction_date = release date
  09:30:00 <= time < 16:00:00 -> DURING_MARKET -> reaction_date = release date
  time >= 16:00:00           -> AFTER_CLOSE   -> reaction_date = next trading session
  time missing               -> UNKNOWN       -> reaction_date unresolved (audited, excluded)

This never picks a reaction date based on which day's gap is bigger -- only real
release timing decides it (see Files/EP/EP_Chart_Pattern_Classifier_Simple_V1.md-style
point-in-time discipline the rest of this project follows).

Two output layers, per the user's spec:
  Layer 1 (raw): every confirmed earnings event + resolved timing/reaction date
  Layer 2 (resolved): point-in-time gap/ADR/liquidity/mktcap + qualify flags
"""

import argparse
import os
import sys
import threading
import time as time_module
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pandas_market_calendars as mcal
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(__file__))
from build_v2_features import PLAN_CUTOFF, resolve_historical_ticker

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

OUTPUT_DIR = os.path.join("Files", "EP", "Data Pulls")
BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
MAX_WORKERS = 15

GAP_MIN = 5.0
ADR_MIN = 2.0
MKTCAP_MIN = 100_000_000
DOLLARVOL_MIN = 10_000_000
ADR_WINDOW = 14
DOLLARVOL_WINDOW = 30

MARKET_OPEN = "09:30:00"
MARKET_CLOSE = "16:00:00"

NYSE = mcal.get_calendar("NYSE")
_SCHEDULE = NYSE.schedule(start_date="2020-01-01", end_date=(date.today() + timedelta(days=30)).isoformat())
TRADING_DAYS = pd.DatetimeIndex(_SCHEDULE.index.date)

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS))


def api_get(url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException:
            time_module.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            time_module.sleep(2 ** attempt)
            continue
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def get_earnings_range(date_from, date_to):
    """All confirmed Benzinga earnings events in [date_from, date_to], following pagination.
    date_from=None means earliest available."""
    params = {"apiKey": POLYGON_API_KEY, "date.lte": date_to,
              "date_status": "confirmed", "limit": 50000, "sort": "date.asc"}
    if date_from:
        params["date.gte"] = date_from
    url = f"{BASE_URL}/benzinga/v1/earnings"
    out = []
    while url:
        data = api_get(url, params)
        params = None  # next_url already has query params baked in
        if not data:
            break
        out.extend(data.get("results", []))
        url = data.get("next_url")
        if url and "apiKey" not in url:
            url = url + ("&" if "?" in url else "?") + f"apiKey={POLYGON_API_KEY}"
    return out


def classify_timing(time_str):
    if not time_str:
        return "UNKNOWN"
    if time_str < MARKET_OPEN:
        return "BEFORE_OPEN"
    if time_str < MARKET_CLOSE:
        return "DURING_MARKET"
    return "AFTER_CLOSE"


def resolve_reaction_date(release_date, timing):
    if timing == "UNKNOWN":
        return None
    pos = TRADING_DAYS.searchsorted(pd.Timestamp(release_date), side="left")
    if timing in ("BEFORE_OPEN", "DURING_MARKET"):
        # snap forward to the release date itself if it's a trading day, else the next one
        if pos < len(TRADING_DAYS) and TRADING_DAYS[pos].date() == release_date:
            return release_date
        if pos < len(TRADING_DAYS):
            return TRADING_DAYS[pos].date()
        return None
    # AFTER_CLOSE: next trading session strictly after release_date
    if pos < len(TRADING_DAYS) and TRADING_DAYS[pos].date() == release_date:
        pos += 1
    if pos < len(TRADING_DAYS):
        return TRADING_DAYS[pos].date()
    return None


def get_daily_bars(ticker, from_date, to_date):
    path = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"apiKey": POLYGON_API_KEY, "adjusted": "true", "sort": "asc", "limit": 50000})
    if data is None or not data.get("results"):
        return None
    df = pd.DataFrame(data["results"])
    df["date"] = df["t"].apply(lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).date())
    return df[["date", "o", "h", "l", "c", "v"]].rename(
        columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"}
    ).sort_values("date").reset_index(drop=True)


_shares_cache = {}
_shares_lock = threading.Lock()


def get_shares_outstanding(ticker):
    # Same ticker can report ~20 times over 5 years -- cache instead of refetching every event.
    with _shares_lock:
        if ticker in _shares_cache:
            return _shares_cache[ticker]
    data = api_get(f"{BASE_URL}/v3/reference/tickers/{ticker}", {"apiKey": POLYGON_API_KEY})
    shares = data["results"].get("weighted_shares_outstanding") if data and data.get("results") else None
    with _shares_lock:
        _shares_cache[ticker] = shares
    return shares


def compute_features(ticker, reaction_date):
    lo = (reaction_date - timedelta(days=70)).isoformat()
    hi = reaction_date.isoformat()
    bars = get_daily_bars(ticker, lo, hi)
    resolved_ticker = ticker
    if bars is None:
        alt = resolve_historical_ticker(ticker, reaction_date)
        if alt != ticker:
            bars = get_daily_bars(alt, lo, hi)
            resolved_ticker = alt
    if bars is None:
        return None

    idx = bars.index[bars["date"] == reaction_date]
    if len(idx) == 0 or idx[0] == 0:
        return None
    i = idx[0]
    prior = bars.iloc[:i]  # strictly before reaction_date

    gap_open = bars["open"].iloc[i]
    pre_gap_close = prior["close"].iloc[-1]
    gap_pct = (gap_open / pre_gap_close - 1) * 100 if pre_gap_close else None

    prior14 = prior.tail(ADR_WINDOW)
    adr14 = ((prior14["high"].mean() - prior14["low"].mean()) / pre_gap_close * 100) if len(prior14) == ADR_WINDOW and pre_gap_close else None

    prior30 = prior.tail(DOLLARVOL_WINDOW)
    avg_vol30 = prior30["volume"].mean() if len(prior30) == DOLLARVOL_WINDOW else None
    dollarvol30 = pre_gap_close * avg_vol30 if avg_vol30 is not None and pre_gap_close else None

    shares = get_shares_outstanding(resolved_ticker)
    pre_gap_mktcap = shares * pre_gap_close if shares and pre_gap_close else None

    return {
        "resolved_ticker": resolved_ticker, "gap_open": gap_open, "pre_gap_close": pre_gap_close,
        "gap_pct": gap_pct, "adr14": adr14, "avg_share_volume_30d": avg_vol30,
        "dollar_volume_proxy_30d": dollarvol30, "pre_gap_market_cap": pre_gap_mktcap,
    }


def process_event(ev):
    release_date = date.fromisoformat(ev["date"])
    timing = classify_timing(ev.get("time"))
    reaction_date = resolve_reaction_date(release_date, timing)

    row = {
        "ticker": ev.get("ticker"), "company_name": ev.get("company_name"),
        "release_date": release_date.isoformat(), "release_time": ev.get("time"),
        "release_timing": timing,
        "reaction_date": reaction_date.isoformat() if reaction_date else "UNRESOLVED",
        "fiscal_period": ev.get("fiscal_period"), "fiscal_year": ev.get("fiscal_year"),
        "actual_eps": ev.get("actual_eps"), "estimated_eps": ev.get("estimated_eps"),
        "eps_surprise_percent": ev.get("eps_surprise_percent"),
        "actual_revenue": ev.get("actual_revenue"), "estimated_revenue": ev.get("estimated_revenue"),
        "revenue_surprise_percent": ev.get("revenue_surprise_percent"),
    }

    if reaction_date is None:
        row.update({"gap_pct": None, "adr14": None, "avg_share_volume_30d": None,
                    "dollar_volume_proxy_30d": None, "pre_gap_market_cap": None,
                    "qualifies_gap": None, "qualifies_adr": None, "qualifies_liquidity": None,
                    "qualifies_mktcap": None, "final_ep_candidate": False})
        return row

    feat = compute_features(ev.get("ticker"), reaction_date)
    if feat is None:
        row.update({"gap_pct": "N/A", "adr14": "N/A", "avg_share_volume_30d": "N/A",
                    "dollar_volume_proxy_30d": "N/A", "pre_gap_market_cap": "N/A",
                    "qualifies_gap": None, "qualifies_adr": None, "qualifies_liquidity": None,
                    "qualifies_mktcap": None, "final_ep_candidate": False})
        return row

    q_gap = feat["gap_pct"] is not None and feat["gap_pct"] >= GAP_MIN
    q_adr = feat["adr14"] is not None and feat["adr14"] >= ADR_MIN
    q_liq = feat["dollar_volume_proxy_30d"] is not None and feat["dollar_volume_proxy_30d"] >= DOLLARVOL_MIN
    q_cap = feat["pre_gap_market_cap"] is not None and feat["pre_gap_market_cap"] >= MKTCAP_MIN

    row.update({
        "gap_pct": feat["gap_pct"], "adr14": feat["adr14"],
        "avg_share_volume_30d": feat["avg_share_volume_30d"],
        "dollar_volume_proxy_30d": feat["dollar_volume_proxy_30d"],
        "pre_gap_market_cap": feat["pre_gap_market_cap"],
        "qualifies_gap": q_gap, "qualifies_adr": q_adr,
        "qualifies_liquidity": q_liq, "qualifies_mktcap": q_cap,
        "final_ep_candidate": bool(q_gap and q_adr and q_liq and q_cap),
    })
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--from-date", type=str, default=None, help="default: earliest available (~2011-05-12)")
    parser.add_argument("--to-date", type=str, default=None, help="default: today")
    parser.add_argument("--label", type=str, default=None)
    args = parser.parse_args()
    to_date = args.to_date or date.today().isoformat()

    print(f"Pulling confirmed Benzinga earnings {args.from_date or 'earliest'} -> {to_date}...")
    events = get_earnings_range(args.from_date, to_date)
    print(f"{len(events)} confirmed earnings events")

    rows = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_event, ev): ev for ev in events}
        with tqdm(total=len(futures), desc="Resolving + computing features", unit="event") as pbar:
            for future in as_completed(futures):
                rows.append(future.result())
                pbar.update(1)

    df = pd.DataFrame(rows)
    timing_counts = df["release_timing"].value_counts()
    print("\nRelease timing breakdown:")
    print(timing_counts.to_string())

    candidates = df[df["final_ep_candidate"] == True]
    print(f"\nFinal EP candidates (all 4 filters pass): {len(candidates)} / {len(df)}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    tag = f" - {args.label}" if args.label else f" - {args.from_date or 'earliest'}_to_{to_date}"
    out_path = os.path.join(OUTPUT_DIR, f"Benzinga EP Candidates{tag}.xlsx")
    try:
        df.to_excel(out_path, index=False)
        print(f"\nWrote {out_path}")
    except PermissionError:
        print(f"Could not write {out_path} (likely open in Excel)")

    passing_path = os.path.join(OUTPUT_DIR, f"Benzinga EP Candidates - PASSING ONLY{tag}.xlsx")
    try:
        candidates.to_excel(passing_path, index=False)
        print(f"Wrote {passing_path}")
    except PermissionError:
        print(f"Could not write {passing_path} (likely open in Excel)")


if __name__ == "__main__":
    main()
