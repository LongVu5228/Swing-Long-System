"""
Massive (Polygon) bars for the DELISTED rows of the HTF ticker list (P123 names with "^YY", e.g.
"AAWW^23" = Atlas Air, delisted 2023). TradingView has no chart for most of them, so they were
skipped while charting -- ~32% of the list. Pull them while the subscription is live.

  --daily   full daily history per row: Massive start (2003) -> end of the delisting year.
  --minute  1-minute bars for each scanner streak, from the streak start to SCAN_AFTER sessions after
            it ends (flags/entries happen up to ~6 months after a name leaves the scanner).
  --estimate  size of the minute pull, no API calls.

Symbol: the row's chart_symbol (the base ticker it traded under). A ticker string can belong to
different companies over time, so every pull is CHECKED against P123's own data for that row
(raw_data_htf_v2: 1-month return on the row's scanner days vs the same return from the bars).
If the base symbol is empty or fails, the historical-ticker resolver is tried (renames).

Output: backtest_data/delisted_daily/<row_ticker>.parquet, backtest_data/delisted_minute/<row_ticker>/,
manifests backtest_data/delisted_daily_manifest.csv / delisted_minute_manifest.csv.

    ../../.venv/Scripts/python.exe -m htf_backtest.delisted_bars --daily --workers 8
    ../../.venv/Scripts/python.exe -m htf_backtest.delisted_bars --estimate
    ../../.venv/Scripts/python.exe -m htf_backtest.delisted_bars --minute --workers 8
The key comes from the repo-root .env via minute_bars, never printed.
"""

import argparse
import glob
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd

from . import config
from . import minute_bars as mb

LIST = os.path.join(config.HTF_DIR, "htf_scanner_master_by_ticker.csv")
RAW = os.path.join(config.HTF_DIR, "raw_data_htf_v2")
DAILY_DIR = os.path.join(config.DATA_DIR, "delisted_daily")
MINUTE_DIR = os.path.join(config.DATA_DIR, "delisted_minute")
ACTIVE_DIR = os.path.join(config.DATA_DIR, "list_daily")      # --active: still-listed rows, for the local recorder
START = "2003-09-01"
SCAN_AFTER = 126            # sessions after a streak ends (~6 months; 195/207 off-scanner entries were within 6)
CHECK_TOL = 0.05            # median |ret_1m(bars) - ret_1m(P123)| above this = wrong company / bad data


def safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def delisted_rows(active=False) -> pd.DataFrame:
    """active=True: the still-listed rows instead (no ^), delist_year NaN -> bars through today."""
    b = pd.read_csv(LIST)
    b["list_row"] = np.arange(2, len(b) + 2)          # sheet row (header = 1)
    is_d = b.ticker.str.contains("^", regex=False)
    d = b[~is_d if active else is_d].copy()
    d["yy"] = d.ticker.str.extract(r"\^(\d{2})$")[0].astype(float)
    d["delist_year"] = 2000 + d.yy
    d["first_seen"] = pd.to_datetime(d.first_seen)
    d["last_seen"] = pd.to_datetime(d.last_seen)
    return d.reset_index(drop=True)


def fetch_daily(sym: str, start: str, end: str) -> pd.DataFrame:
    url = f"{mb.BASE_URL}/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}"
    params = {"apiKey": mb.API_KEY, "adjusted": "true", "sort": "asc", "limit": 50000}
    rows = []
    while url:
        data = mb._api_get(url, params)
        if not data:
            break
        rows += data.get("results") or []
        url, params = data.get("next_url"), {"apiKey": mb.API_KEY}
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["date"] = [datetime.fromtimestamp(t / 1000, tz=timezone.utc).date() for t in df.t]
    df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume", "vw": "vwap", "n": "trades"})
    return df[[c for c in ["date", "open", "high", "low", "close", "volume", "vwap", "trades"] if c in df]]


_P123 = {}
_WANT = set()      # tickers whose P123 returns to load (empty = every ^ row)


def p123_returns(row_ticker: str) -> pd.Series:
    """P123's 1-month return (fraction) on the row's scanner days, indexed by date."""
    if not _P123:
        for f in sorted(glob.glob(os.path.join(RAW, "*.parquet"))):
            r = pd.read_parquet(f, columns=["date", "ticker", "ret_1m"])
            r = r[r.ticker.isin(_WANT)] if _WANT else r[r.ticker.str.contains("^", regex=False)]
            for t, g in r.groupby("ticker"):
                _P123.setdefault(t, []).append(g)
        for t in list(_P123):
            g = pd.concat(_P123[t])
            _P123[t] = pd.Series(g.ret_1m.to_numpy(), index=pd.to_datetime(g.date).dt.date)
    return _P123.get(row_ticker, pd.Series(dtype=float))


def check(df: pd.DataFrame, row) -> tuple:
    """(median abs diff of 22-session return vs P123 on the row's streak days, n days compared,
    share of streak days that have a bar)."""
    if df.empty:
        return np.nan, 0, 0.0
    s = df.set_index("date").close
    ret = s / s.shift(22) - 1   # P123 ret_1m = 22 sessions (21 fails fast movers: QUBT 11% vs 5%)
    p = p123_returns(row.ticker)
    if p.empty:
        return np.nan, 0, np.nan
    j = pd.concat([ret.rename("bars"), p.rename("p123")], axis=1, join="inner").dropna()
    days = [d for d in p.index if row.first_seen.date() <= d <= row.last_seen.date()]
    cov = np.mean([d in s.index for d in days]) if days else np.nan
    if j.empty:
        return np.nan, 0, cov
    return float((j.bars - j.p123).abs().median()), len(j), cov


def pull_daily_row(row, refresh=False, out_dir=None) -> dict:
    out = os.path.join(out_dir or DAILY_DIR, safe(row.ticker) + ".parquet")
    end = f"{int(row.delist_year)}-12-31" if row.delist_year == row.delist_year else date.today().isoformat()
    base = str(row.chart_symbol) if pd.notna(row.chart_symbol) else row.ticker.split("^")[0].split(".")[0]
    tried = []
    if os.path.exists(out) and not refresh:
        df, sym = pd.read_parquet(out), base          # cached: the base symbol (renamed rows: see manifest)
    else:
        df, sym = pd.DataFrame(), base
        cands = [base]
        try:
            sys.path.insert(0, os.path.join(config.REPO, "Scripts"))
            from build_v2_features import resolve_historical_ticker
            alt = resolve_historical_ticker(base, row.first_seen.date())
            if alt and alt not in cands:
                cands.append(alt)
        except Exception:  # noqa: BLE001 -- resolver is best-effort
            pass
        if isinstance(row.former_symbols, str):
            cands += [s.strip() for s in re.split(r"[;,| ]+", row.former_symbols) if s.strip() and s.strip() not in cands]
        best = None
        for c in cands:
            d = fetch_daily(c, START, end)
            med, n, cov = check(d, row)
            tried.append(f"{c}:{len(d)}:{med if med == med else 'na'}")
            # a P123 match beats coverage: a renamed symbol may cover only part of the history
            score = (bool(med == med and med <= CHECK_TOL), cov if cov == cov else 0, -(med if med == med else 1))
            if not d.empty and (best is None or score > best[0]):
                best = (score, c, d)
            if not d.empty and med == med and med <= CHECK_TOL and cov == cov and cov >= 0.9:
                break
        if best:
            _, sym, df = best
        os.makedirs(os.path.dirname(out), exist_ok=True)
        df.to_parquet(out, index=False)
    med, n, cov = check(df, row)
    status = ("EMPTY" if df.empty else "OK" if med == med and med <= CHECK_TOL and cov >= 0.9
              else "NO_P123_CHECK" if med != med else "SUSPECT")
    return {"list_row": row.list_row, "ticker": row.ticker, "symbol_used": sym, "tried": " ".join(tried),
            "bars": len(df), "first_bar": df.date.min() if len(df) else None, "last_bar": df.date.max() if len(df) else None,
            "first_seen": row.first_seen.date(), "last_seen": row.last_seen.date(),
            "p123_ret1m_median_diff": round(med, 4) if med == med else None, "days_checked": n,
            "streak_day_coverage": round(cov, 3) if cov == cov else None, "status": status}


def minute_windows(rows: pd.DataFrame, daily_manifest: pd.DataFrame) -> pd.DataFrame:
    """One window per scanner streak: streak start -> SCAN_AFTER sessions after it ends, clipped to
    the last daily bar; overlapping windows on a row merged."""
    from ep_backtest import calendar_utils
    good = daily_manifest[daily_manifest.status.isin(["OK", "NO_P123_CHECK"])].set_index("ticker")
    out = []
    for r in rows.itertuples():
        if r.ticker not in good.index or not isinstance(r.streak_spans, str):
            continue
        sym = good.at[r.ticker, "symbol_used"]
        last = pd.Timestamp(good.at[r.ticker, "last_bar"]).date()
        spans = []
        for s in r.streak_spans.split(";"):
            a, b = (pd.Timestamp(x.strip()).date() for x in s.split(".."))
            pos = calendar_utils.TRADING_DAYS.searchsorted(pd.Timestamp(b))
            e = calendar_utils.TRADING_DAYS[min(pos + SCAN_AFTER, len(calendar_utils.TRADING_DAYS) - 1)].date()
            spans.append([max(a, date(2004, 1, 1)), min(e, last)])
        spans.sort()
        merged = []
        for a, b in spans:
            if merged and a <= merged[-1][1]:
                merged[-1][1] = max(merged[-1][1], b)
            else:
                merged.append([a, b])
        for a, b in merged:
            if a <= b:
                out.append({"ticker": r.ticker, "symbol": sym, "start": a, "end": b,
                            "sessions": int(((calendar_utils.TRADING_DAYS >= pd.Timestamp(a)) &
                                             (calendar_utils.TRADING_DAYS <= pd.Timestamp(b))).sum())})
    return pd.DataFrame(out)


def pull_minute_window(w, refresh=False) -> dict:
    p = os.path.join(MINUTE_DIR, safe(w.ticker), f"{w.start:%Y%m%d}_{w.end:%Y%m%d}.parquet")
    if os.path.exists(p) and not refresh:
        df, status = pd.read_parquet(p), "cached"
    else:
        df = mb.fetch_minute_range(w.symbol, w.start.isoformat(), w.end.isoformat())
        status = "ok" if not df.empty else "empty"
        os.makedirs(os.path.dirname(p), exist_ok=True)
        df.to_parquet(p, index=False)
    return {"ticker": w.ticker, "symbol": w.symbol, "start": w.start, "end": w.end, "status": status,
            "bars": len(df), "sessions": df.session_date.nunique() if len(df) else 0,
            "mb": round(os.path.getsize(p) / 1e6, 2)}


def run_pool(fn, items, workers, desc):
    from tqdm import tqdm
    res = []
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fn, it) for it in items]
        for f in tqdm(as_completed(futs), total=len(futs), desc=desc):
            try:
                res.append(f.result())
            except Exception as exc:  # noqa: BLE001 -- one bad row must not stop the pull
                res.append({"status": f"ERROR: {exc}"})
    return pd.DataFrame(res)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--minute", action="store_true")
    ap.add_argument("--estimate", action="store_true")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--redo-suspect", action="store_true", help="re-pull rows not OK in the daily manifest")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--active", action="store_true", help="daily bars for the still-listed rows -> list_daily/")
    a = ap.parse_args()
    if not mb.API_KEY and (a.daily or a.minute):
        sys.exit("MASSIVE_API_KEY / POLYGON_API_KEY not found in the repo-root .env")
    rows = delisted_rows(active=a.active)
    if a.limit:
        rows = rows.head(a.limit)
    if a.active:
        _WANT.update(rows.ticker)
        print(f"{len(rows)} still-listed rows; loading P123 check data ...")
        p123_returns(rows.ticker.iloc[0])          # load once, before the threads race to fill the cache
        m = run_pool(lambda r: pull_daily_row(r, out_dir=ACTIVE_DIR), list(rows.itertuples()), a.workers, "daily")
        p = os.path.join(config.DATA_DIR, "list_daily_manifest.csv")
        m.sort_values("list_row").to_csv(p, index=False)
        print(m.status.value_counts().to_dict())
        print(f"manifest: {p}")
        return
    dman = os.path.join(config.DATA_DIR, "delisted_daily_manifest.csv")
    if a.daily:
        redo = None
        if a.redo_suspect and os.path.exists(dman):
            old = pd.read_csv(dman)
            redo = set(old[old.status != "OK"].ticker)
            rows_run = rows[rows.ticker.isin(redo)]
        else:
            rows_run = rows
        print(f"{len(rows_run)} delisted rows; loading P123 check data ...")
        p123_returns(rows.ticker.iloc[0])
        m = run_pool(lambda r: pull_daily_row(r, refresh=redo is not None), list(rows_run.itertuples()), a.workers, "daily")
        if redo is not None:
            m = pd.concat([old[~old.ticker.isin(redo)], m])
        m.sort_values("list_row").to_csv(dman, index=False)
        print(m.status.value_counts().to_dict())
        print(f"manifest: {dman}")
    if a.estimate or a.minute:
        w = minute_windows(rows, pd.read_csv(dman))
        sizes = []
        for f in glob.glob(os.path.join(config.MINUTE_BARS_DIR, "*", "*.parquet"))[:400]:
            n = pd.read_parquet(f, columns=["session_date"]).session_date.nunique()
            if n:
                sizes.append(os.path.getsize(f) / n)
        per = float(np.median(sizes)) if sizes else 10_000
        print(f"{len(w)} minute windows on {w.ticker.nunique()} rows, {w.sessions.sum():,} sessions, "
              f"~{w.sessions.sum() * per / 1e9:.1f} GB at {per / 1e3:.0f} KB/session")
        if a.minute:
            mm = run_pool(pull_minute_window, list(w.itertuples()), a.workers, "minute")
            p = os.path.join(config.DATA_DIR, "delisted_minute_manifest.csv")
            mm.to_csv(p, index=False)
            print(mm.status.value_counts().to_dict(), f"{mm.mb.sum() / 1e3:.2f} GB")
            print(f"manifest: {p}")


if __name__ == "__main__":
    main()
