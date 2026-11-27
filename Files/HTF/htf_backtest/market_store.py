"""
Local daily-bar store for EVERY US stock (Massive grouped daily: one API call = all ~12,700 stocks for one session).

Why: the free Massive tier allows ~5 calls/minute and ~2 years of history, so the screener can't fetch bars per
ticker. Backfill once on the paid plan (2018 -> today, ~2,250 calls), then one call per new session keeps it current.

Layout: backtest_data/market_daily/<year>.parquet, columns date (YYYY-MM-DD), ticker, open, high, low, close, volume,
sorted by (ticker, date) in small row groups, so reading one ticker touches only a few row groups per year.
_state.json: dates stored, last split check, split ids already applied.

Splits: grouped bars are split-adjusted as of the day they were fetched. A split executed LATER would leave older stored
bars unadjusted, so every update pulls /v3/reference/splits executed since the last check and rescales the stored
bars before each split's execution date (prices x from/to, volume x to/from). Ids are recorded so none applies twice.

    ../../.venv/Scripts/python.exe -m htf_backtest.market_store --backfill 2018-01-01      # once, on the paid plan
    ../../.venv/Scripts/python.exe -m htf_backtest.market_store --update                   # daily (1 call + splits)
    ../../.venv/Scripts/python.exe -m htf_backtest.market_store --show AA
"""
import argparse
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime

import pandas as pd
import pyarrow as pa
import pyarrow.dataset as ds
import pyarrow.parquet as pq

from . import config
from . import minute_bars as mb
from ep_backtest import calendar_utils  # noqa: E402  (path set by config)

STORE = os.path.join(config.DATA_DIR, "market_daily")
STATE = os.path.join(STORE, "_state.json")
COLS = ["date", "ticker", "open", "high", "low", "close", "volume"]
LOCK = threading.Lock()


def _state():
    if os.path.exists(STATE):
        with open(STATE, encoding="utf-8") as fh:
            return json.load(fh)
    return {"dates": [], "split_check": None, "splits_applied": []}


def _save_state(s):
    os.makedirs(STORE, exist_ok=True)
    with open(STATE + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(s, fh)
    os.replace(STATE + ".tmp", STATE)


def fetch_day(d: str) -> pd.DataFrame:
    """All US stocks' adjusted bars for one session (empty frame if Massive has none yet)."""
    data = mb._api_get(f"{mb.BASE_URL}/v2/aggs/grouped/locale/us/market/stocks/{d}",
                       {"apiKey": mb.API_KEY, "adjusted": "true"})
    rows = (data or {}).get("results") or []
    if not rows:
        return pd.DataFrame(columns=COLS)
    df = pd.DataFrame(rows).rename(columns={"T": "ticker", "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
    df["date"] = d
    return df[COLS].dropna(subset=["open", "high", "low", "close"])


def _year_path(y):
    return os.path.join(STORE, f"{y}.parquet")


def _write_year(y, df):
    df = df.drop_duplicates(["ticker", "date"], keep="last").sort_values(["ticker", "date"]).reset_index(drop=True)
    tbl = pa.Table.from_pandas(df[COLS], preserve_index=False)
    os.makedirs(STORE, exist_ok=True)
    tmp = _year_path(y) + ".tmp"
    pq.write_table(tbl, tmp, row_group_size=20_000, compression="zstd")
    os.replace(tmp, _year_path(y))


def _merge(new: pd.DataFrame):
    """Merge freshly fetched days into their year files."""
    for y, g in new.groupby(new.date.str[:4]):
        p = _year_path(y)
        old = pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame(columns=COLS)
        _write_year(y, pd.concat([old, g]))


def _sessions(start: str, end: str):
    td = calendar_utils.TRADING_DAYS
    return [d.strftime("%Y-%m-%d") for d in td[(td >= pd.Timestamp(start)) & (td <= pd.Timestamp(end))]]


def _last_complete_session():
    """Today counts only after ~16:30 ET (bars settle after the close)."""
    now = pd.Timestamp.now(tz=config.ET)
    end = now.normalize() if now.hour * 60 + now.minute >= 16 * 60 + 30 else now.normalize() - pd.Timedelta(days=1)
    return end.strftime("%Y-%m-%d")


def fill(start: str, end: str = None, workers: int = 8, verbose=True):
    """Fetch every missing session in [start, end]; writes once per year in batches. Returns sessions added."""
    end = end or _last_complete_session()
    st = _state()
    have = set(st["dates"])
    todo = [d for d in _sessions(start, end) if d not in have]
    if not todo:
        if verbose:
            print("store already complete for", start, "->", end)
        return 0
    if verbose:
        print(f"fetching {len(todo)} sessions ({todo[0]} -> {todo[-1]}) with {workers} threads")
    added, buf, done = 0, [], 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_day, d): d for d in todo}
        for fu in as_completed(futs):
            d = futs[fu]
            df = fu.result()
            done += 1
            if len(df):
                buf.append(df)
                have.add(d)
                added += 1
            if len(buf) >= 120 or done == len(todo):
                if buf:
                    _merge(pd.concat(buf))
                    buf = []
                st["dates"] = sorted(have)
                _save_state(st)
                if verbose:
                    print(f"  {done}/{len(todo)} sessions done, {added} stored")
    if st.get("split_check") is None:
        st["split_check"] = date.today().isoformat()   # backfilled bars are adjusted as of today
        _save_state(st)
    return added


def apply_splits(verbose=True):
    """Rescale stored bars for splits executed since the last check (and not applied yet)."""
    st = _state()
    since = st.get("split_check") or date.today().isoformat()
    today = date.today().isoformat()
    url, params, splits = f"{mb.BASE_URL}/v3/reference/splits", {"apiKey": mb.API_KEY, "execution_date.gte": since,
                                                                 "execution_date.lte": today, "limit": 1000}, []
    while url:
        data = mb._api_get(url, params) or {}
        splits += data.get("results") or []
        url, params = data.get("next_url"), {"apiKey": mb.API_KEY}
    applied = set(st.get("splits_applied", []))
    todo = [s for s in splits if s["id"] not in applied and s.get("split_from") and s.get("split_to")]
    # Measure instead of assuming: whether bars fetched around the execution day already carry the split depends on
    # when they were fetched. Compare stored closes before the split with a fresh adjusted pull (1 call per split);
    # rescale only if they differ by roughly the split ratio.
    factors = {}
    for s in todo:
        ex = s["execution_date"]
        old = read_ticker(s["ticker"])
        old = old[old.date < ex].tail(5)
        if old.empty:
            continue
        a = (pd.Timestamp(old.date.iloc[0]) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
        fresh = mb._api_get(f"{mb.BASE_URL}/v2/aggs/ticker/{s['ticker']}/range/1/day/{a}/{old.date.iloc[-1]}",
                            {"apiKey": mb.API_KEY, "adjusted": "true"}) or {}
        fr = {datetime.utcfromtimestamp(r["t"] / 1000).strftime("%Y-%m-%d"): r["c"] for r in fresh.get("results") or []}
        both = [(c, fr[d]) for d, c in zip(old.date, old.close) if d in fr and fr[d]]
        if not both:
            continue
        f = sorted(fresh_c / c for c, fresh_c in both)[len(both) // 2]        # fresh / stored (median)
        if abs(f - 1) > 0.02:
            factors[(s["ticker"], ex)] = f
    by_year = {}
    for (tk, ex), f in factors.items():
        for y in sorted({d[:4] for d in st["dates"] if d < ex}):
            by_year.setdefault(y, []).append((tk, ex, f))
    for y, ss in by_year.items():
        p = _year_path(y)
        if not os.path.exists(p):
            continue
        df = pd.read_parquet(p)
        for tk, ex, f in ss:
            m = (df.ticker == tk) & (df.date < ex)
            df.loc[m, ["open", "high", "low", "close"]] *= f
            df.loc[m, "volume"] /= f
        _write_year(y, df)
    if verbose and factors:
        print("  rescaled:", {k[0]: round(v, 4) for k, v in factors.items()})
    st["splits_applied"] = sorted(applied | {s["id"] for s in todo})
    st["split_check"] = today
    _save_state(st)
    if verbose:
        print(f"splits since {since}: {len(splits)} found, {len(todo)} checked, {len(factors)} needed rescaling")
    return len(factors)


def update(verbose=True):
    """Daily: add missing sessions since the store's last date, then apply new splits. Safe to run any time."""
    st = _state()
    if not st["dates"]:
        raise SystemExit("store is empty: run --backfill first")
    with LOCK:
        n = fill(st["dates"][-1], workers=2, verbose=verbose)
        apply_splits(verbose=verbose)
    return n


def coverage():
    st = _state()
    return (st["dates"][0], st["dates"][-1], len(st["dates"])) if st["dates"] else None


def read_ticker(ticker: str, end: str = None) -> pd.DataFrame:
    """Daily bars for one ticker from the store (all stored years), cut at end."""
    files = sorted(f for f in os.listdir(STORE) if f[:4].isdigit() and f.endswith(".parquet")) if os.path.isdir(STORE) else []
    if not files:
        return pd.DataFrame(columns=COLS)
    dset = ds.dataset([os.path.join(STORE, f) for f in files], format="parquet")
    flt = ds.field("ticker") == ticker
    if end:
        flt = flt & (ds.field("date") <= end)
    return dset.to_table(filter=flt).to_pandas().sort_values("date").reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backfill", metavar="START", help="fetch every missing session from START to the last close")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--show", metavar="TICKER")
    a = ap.parse_args()
    t0 = datetime.now()
    if a.backfill:
        fill(a.backfill, workers=a.workers)
        apply_splits()
    if a.update:
        update()
    if a.show:
        print(read_ticker(a.show).tail(5).to_string(index=False))
    print("coverage:", coverage(), f"({(datetime.now() - t0).total_seconds():.0f}s)")


if __name__ == "__main__":
    main()
