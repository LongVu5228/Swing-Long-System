"""
Massive (Polygon) 1-minute bars for every annotated flag's entry window -- pull, cache, check.

EP pattern (ep_backtest/minute_bars.py), adapted to HTF:
- one pooled requests.Session, exponential backoff on 429 / network errors, 404 -> None;
- regular session only (9:30 <= bar start < 16:00 ET; the 16:00 bar is after-hours), with
  dt_et (tz-aware) + session_date columns -- the exact schema ep_backtest's position-management
  code expects, so it can be reused unchanged;
- one parquet per (ticker, window) under backtest_data/minute_bars/<TICKER>/;
- historical-ticker fallback (Scripts/build_v2_features.resolve_historical_ticker) when the
  chart symbol returns nothing (renamed / delisted names).
HTF additions:
- windows come from the annotation master: setup_confirmed session .. session on/before
  final_flag_end + POST_SESSIONS, merged per ticker when flags sit close together;
- every window is CHECKED against the TradingView export the flag was drawn on (minute bars
  rolled up to daily closes vs the chart's closes). A reused ticker (CZR, CNR) or split
  mismatch shows up here instead of silently feeding the backtest wrong prices;
- a manifest (backtest_data/minute_manifest.csv) records every window's status/check.

Run from Files/HTF with the repo venv:
    ../../.venv/Scripts/python.exe -m htf_backtest.minute_bars --probe
    ../../.venv/Scripts/python.exe -m htf_backtest.minute_bars --test 3
    ../../.venv/Scripts/python.exe -m htf_backtest.minute_bars --workers 8
    ../../.venv/Scripts/python.exe -m htf_backtest.minute_bars --extra SPY,IWM
The key comes from the repo-root .env (MASSIVE_API_KEY, else POLYGON_API_KEY), never printed.
"""

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

import pandas as pd
import requests
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter

from . import config

from ep_backtest import calendar_utils  # noqa: E402  (path set up by config)

load_dotenv(os.path.join(config.REPO, ".env"))
API_KEY = os.environ.get("MASSIVE_API_KEY") or os.environ.get("POLYGON_API_KEY")
BASE_URL = os.environ.get("MASSIVE_BASE_URL", "https://api.polygon.io")
MAX_RETRIES = 6

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=32, pool_maxsize=32))
COLUMNS = ["dt_et", "session_date", "open", "high", "low", "close", "volume", "vwap"]
_FREE_TIER_GAP_S = 13.0
_throttle = {"free": False, "last": 0.0}


def _api_get(url, params=None):
    for attempt in range(1, MAX_RETRIES + 1):
        if _throttle["free"]:
            wait = _FREE_TIER_GAP_S - (time.time() - _throttle["last"])
            if wait > 0:
                time.sleep(wait)
            _throttle["last"] = time.time()
        try:
            resp = SESSION.get(url, params=params, timeout=60)
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 404:
            return None
        if resp.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        resp.raise_for_status()
        return resp.json()
    return None


def fetch_minute_range(ticker: str, from_date: str, to_date: str) -> pd.DataFrame:
    """All 1-minute aggs for the range (next_url paginated), regular session only."""
    url = f"{BASE_URL}/v2/aggs/ticker/{ticker}/range/1/minute/{from_date}/{to_date}"
    params = {"apiKey": API_KEY, "adjusted": "true", "sort": "asc", "limit": 50000}
    results = []
    while url:
        data = _api_get(url, params)
        if data is None:
            break
        results.extend(data.get("results") or [])
        url, params = data.get("next_url"), {"apiKey": API_KEY}
    if not results:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.DataFrame(results)
    df["dt_et"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(config.ET)
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap"})
    if "vwap" not in df:
        df["vwap"] = float("nan")
    t = df["dt_et"].dt.strftime("%H:%M:%S")
    df = df[(t >= config.SESSION_OPEN) & (t < config.SESSION_CLOSE)].copy()   # Section 76
    df["session_date"] = df["dt_et"].dt.date
    return df[COLUMNS].sort_values("dt_et").reset_index(drop=True)


def _ymd(x) -> date:
    return datetime.strptime(str(int(x)), "%Y%m%d").date()


def _window_bounds(confirm: date, end: date) -> tuple:
    start = calendar_utils.sessions_from(confirm, 1)[0]
    last = end if calendar_utils.is_trading_day(end) else calendar_utils.TRADING_DAYS[
        calendar_utils.TRADING_DAYS.searchsorted(pd.Timestamp(end), side="right") - 1].date()
    pos = calendar_utils.TRADING_DAYS.searchsorted(pd.Timestamp(last))
    stop = calendar_utils.TRADING_DAYS[min(pos + config.POST_SESSIONS, len(calendar_utils.TRADING_DAYS) - 1)].date()
    return start, min(stop, date.today())


def flag_windows(master: pd.DataFrame = None) -> pd.DataFrame:
    """One row per merged (ticker, start, end) pull window."""
    if master is None:
        import quick_backtest_chosen_one as qb
        master = qb.read_master()
    m = master[(master.flag_no > 0) & master.setup_confirmed.notna() & master.final_flag_end.notna()]
    # delisted (^) rows get their minute bars from htf_backtest.delisted_bars (backtest_data/delisted_minute/).
    # Pulling them here (2026-11-25) created EMPTY folders under minute_bars/ that simulate.minute_frame finds first,
    # hiding the real delisted bars -- so never pull them here.
    m = m[~m.ticker.astype(str).str.contains("^", regex=False)]
    rows = []
    for r in m.itertuples():
        s, e = _window_bounds(_ymd(r.setup_confirmed), _ymd(max(r.final_flag_end, r.setup_confirmed)))
        rows.append((r.ticker, s, e))
    w = pd.DataFrame(rows, columns=["ticker", "start", "end"]).sort_values(["ticker", "start"])
    merged = []
    for tk, g in w.groupby("ticker"):
        cur = None
        for r in g.itertuples():
            gap = len(calendar_utils.TRADING_DAYS[(calendar_utils.TRADING_DAYS.date > (cur[2] if cur else r.start))
                                                  & (calendar_utils.TRADING_DAYS.date < r.start)]) if cur else 0
            if cur and gap <= config.MERGE_GAP_SESSIONS:
                cur[2] = max(cur[2], r.end)
                cur[3] += 1
            else:
                if cur:
                    merged.append(cur)
                cur = [tk, r.start, r.end, 1]
        merged.append(cur)
    return pd.DataFrame(merged, columns=["ticker", "start", "end", "n_flags"])


def cache_path(ticker: str, start: date, end: date) -> str:
    return os.path.join(config.MINUTE_BARS_DIR, ticker, f"{start:%Y%m%d}_{end:%Y%m%d}.parquet")


def load_window(ticker: str, start: date, end: date) -> pd.DataFrame:
    p = cache_path(ticker, start, end)
    return pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame(columns=COLUMNS)


def _tv_check(ticker: str, df: pd.DataFrame, tv_cache: dict) -> tuple:
    import quick_backtest_chosen_one as qb
    if ticker not in tv_cache:
        tv_cache[ticker] = qb.load_bars(ticker)
    tv = tv_cache[ticker]
    if tv is None or df.empty:
        return float("nan"), 0
    daily = df.groupby("session_date")["close"].last()
    daily.index = [int(d.strftime("%Y%m%d")) for d in daily.index]
    j = pd.DataFrame({"mb": daily}).join(tv.set_index("d")["close"].rename("tv"), how="inner")
    if j.empty:
        return float("nan"), 0
    diff = (j.mb / j.tv - 1).abs()
    return round(float(diff.median()), 4), int((diff > config.CHECK_TOL).sum())


def pull_window(ticker: str, start: date, end: date, n_flags: int, tv_cache: dict, refresh=False) -> dict:
    p = cache_path(ticker, start, end)
    resolved = ticker
    if os.path.exists(p) and not refresh:
        df, status = pd.read_parquet(p), "cached"
    else:
        df = fetch_minute_range(ticker, start.isoformat(), end.isoformat())
        if df.empty:
            try:   # renamed / delisted symbol -> what it traded as on the window's start date
                sys.path.insert(0, os.path.join(config.REPO, "Scripts"))
                from build_v2_features import resolve_historical_ticker
                resolved = resolve_historical_ticker(ticker, start)
                if resolved != ticker:
                    df = fetch_minute_range(resolved, start.isoformat(), end.isoformat())
            except Exception:  # noqa: BLE001 -- fallback is best-effort
                pass
        status = "ok" if not df.empty else "empty"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        df.to_parquet(p, index=False)       # empty windows cached too, so reruns skip them
    med, days_off = _tv_check(ticker, df, tv_cache) if n_flags else (float("nan"), 0)
    flag = ""
    if med == med and med > config.CHECK_TOL:
        flag = "MISMATCH"
    elif days_off:
        flag = "SOME_DAYS_OFF"
    return {"ticker": ticker, "resolved_ticker": resolved, "start": start, "end": end, "n_flags": n_flags,
            "status": status, "bars": len(df), "sessions": df.session_date.nunique() if len(df) else 0,
            "tv_close_median_diff": med, "tv_days_off": days_off, "check": flag}


def probe():
    print("earliest 1-minute history on this key (AAPL, first week of each year):")
    for y in [2003, 2004, 2005, 2008, 2012, 2016, 2020, 2024]:
        df = fetch_minute_range("AAPL", f"{y}-01-02", f"{y}-01-09")
        print(f"  {y}: {len(df):6d} regular-session bars")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--test", type=int, default=0, help="only the N most recent windows")
    ap.add_argument("--free", action="store_true", help="free tier: 13 s between calls, 1 worker")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--extra", default="", help="e.g. SPY,IWM over the full flag span, yearly chunks")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--recheck", action="store_true", help="classify windows OK/MINOR_OK/RESCALE/BAD/EMPTY")
    args = ap.parse_args()
    if args.recheck:
        recheck()
        return
    if not API_KEY:
        sys.exit("MASSIVE_API_KEY / POLYGON_API_KEY not found in the repo-root .env")
    _throttle["free"] = args.free
    if args.probe:
        probe()
        return

    w = flag_windows()
    if args.extra:
        lo, hi = w.start.min(), w.end.max()
        extra = [{"ticker": tk.strip(), "start": max(lo, date(y, 1, 1)), "end": min(hi, date(y, 12, 31)), "n_flags": 0}
                 for tk in args.extra.split(",") for y in range(lo.year, hi.year + 1)]
        w = pd.DataFrame(extra)
    if args.test:
        w = w.sort_values("start").tail(args.test)
    print(f"{len(w)} windows, {w.ticker.nunique()} tickers, {int(w.n_flags.sum())} flags")

    from tqdm import tqdm
    tv_cache, out = {}, []
    with ThreadPoolExecutor(max_workers=1 if args.free else args.workers) as ex:
        futs = {ex.submit(pull_window, r.ticker, r.start, r.end, r.n_flags, tv_cache, args.refresh): r.ticker
                for r in w.itertuples()}
        for f in tqdm(as_completed(futs), total=len(futs), desc="minute windows"):
            try:
                out.append(f.result())
            except Exception as exc:  # noqa: BLE001
                out.append({"ticker": futs[f], "status": f"ERROR: {exc}"})
    res = pd.DataFrame(out)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    if os.path.exists(config.MINUTE_MANIFEST):
        res = pd.concat([pd.read_csv(config.MINUTE_MANIFEST), res]).drop_duplicates(
            ["ticker", "start", "end"], keep="last")
    res.to_csv(config.MINUTE_MANIFEST, index=False)
    print(f"status: {res.status.value_counts().to_dict()}")
    print(f"check:  {res.check.fillna('').value_counts().to_dict()}")
    bad = res[res.check.fillna("") != ""]
    if len(bad):
        print(bad[["ticker", "resolved_ticker", "start", "end", "bars", "tv_close_median_diff", "tv_days_off", "check"]]
              .head(40).to_string(index=False))
    print(f"manifest: {config.MINUTE_MANIFEST}")



def recheck() -> pd.DataFrame:
    """Classify every window against its TradingView export (2026-11-13, first full pull: 87
    MISMATCH + 32 SOME_DAYS_OFF of 2,013). Most "mismatches" were a CONSTANT price ratio --
    Massive and TradingView applying different split/dividend adjustments (AIG 1.358 every
    day, ALTO 15.0, AEO 0.93) -- not a different company. Those are rescaled to the chart's
    scale (R1, ADR and the moving averages all come from the chart, so the minute bars must
    match it). A ratio that wanders (reused ticker, foreign listing in another currency, ADR
    ratio change) is BAD and kept out of the minute grid.
      use = OK        no issue, scale 1
            MINOR_OK  ratio ~1, <=10% of days off by >2%
            RESCALE   constant ratio != 1 (<=10% of days off after rescaling) -> scale
            BAD       ratio not constant -> excluded (STATUS_MINUTE_MISMATCH)
            EMPTY     Massive returned nothing (renamed / OTC) -> excluded
    """
    import numpy as np
    import quick_backtest_chosen_one as qb
    man = pd.read_csv(config.MINUTE_MANIFEST)
    use, scale = [], []
    tv_cache = {}
    for r in man.itertuples():
        if r.status == "empty" or r.bars == 0:
            use.append("EMPTY"); scale.append(np.nan); continue
        if not isinstance(r.check, str) or r.check == "":
            use.append("OK"); scale.append(1.0); continue
        df = load_window(r.ticker, pd.Timestamp(r.start).date(), pd.Timestamp(r.end).date())
        if r.ticker not in tv_cache:
            tv_cache[r.ticker] = qb.load_bars(r.ticker)
        tv = tv_cache[r.ticker]
        d = df.groupby("session_date").close.last()
        d.index = [int(x.strftime("%Y%m%d")) for x in d.index]
        j = pd.DataFrame({"mb": d}).join(tv.set_index("d").close.rename("tv"), how="inner")
        ratio = j.tv / j.mb
        med = float(ratio.median())
        off = float((abs(ratio / med - 1) > 0.02).mean())
        if off > 0.10:
            use.append("BAD"); scale.append(np.nan)
        elif abs(med - 1) < 0.01:
            use.append("MINOR_OK"); scale.append(1.0)
        else:
            use.append("RESCALE"); scale.append(med)
    man["use"], man["scale"] = use, scale
    man.to_csv(config.MINUTE_MANIFEST, index=False)
    print(man.groupby("use").agg(windows=("ticker", "size"), flags=("n_flags", "sum")).to_string())
    return man


if __name__ == "__main__":
    main()
