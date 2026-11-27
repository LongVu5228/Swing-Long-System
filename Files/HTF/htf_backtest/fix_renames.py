"""Rebuild still-listed rows' daily bars from the company's own symbol history (Massive ticker events).

Massive aggregates are per SYMBOL, so a renamed company's current symbol returns only post-rename bars, and a
reused symbol returns ANOTHER company's bars before the rename (ES: EnergySolutions 2007-13 under Eversource's
2008 scanner streak; Eversource was NU until 2015-02-19). For each row:
  1. /vX/reference/tickers/{sym}/events -> [(date, ticker)] symbol segments of THIS company (by FIGI)
  2. drop current-symbol bars dated before its own first segment (another company)
  3. fill earlier segments with the listed former symbols' bars
  4. if history before the first segment is still missing and a streak sits there, try candidate former symbols
     (list former_symbols / the repo resolver); accept one only if its bars end <= 3 sessions before the first
     segment and its 1-month return matches P123 (median |diff| <= 5%) around the streaks
  5. re-check every streak vs P123
Originals kept in list_daily/_orig/; manifest backtest_data/rename_fix_manifest.csv.

    ../../.venv/Scripts/python.exe -m htf_backtest.fix_renames [--tickers ES AACG] [--workers 8]
"""
import argparse
import glob
import os
import shutil
import sys

import numpy as np
import pandas as pd

from . import config, minute_bars as mb
from .delisted_bars import ACTIVE_DIR, LIST, RAW, START, fetch_daily, run_pool, safe

TOL = 0.05
P = {}


def load_p123(want):
    p = []
    for f in sorted(glob.glob(os.path.join(RAW, "*.parquet"))):
        r = pd.read_parquet(f, columns=["date", "ticker", "ret_1m"])
        p.append(r[r.ticker.isin(want)])
    p = pd.concat(p)
    p["date"] = pd.to_datetime(p.date)
    P.update({t: g.set_index("date").ret_1m.sort_index() for t, g in p.groupby("ticker")})


def events(sym):
    j = mb._api_get(f"{mb.BASE_URL}/vX/reference/tickers/{sym}/events", {"apiKey": mb.API_KEY}) or {}
    ev = [(pd.Timestamp(e["date"]), e["ticker_change"]["ticker"]) for e in (j.get("results") or {}).get("events", [])
          if e.get("type") == "ticker_change"]
    return sorted(ev)


def ret21(df):
    s = df.assign(date=pd.to_datetime(df.date)).set_index("date").close.sort_index()
    return s / s.shift(22) - 1   # P123 ret_1m = 22 sessions (21 fails fast movers: QUBT 11% vs 5%)


def streak_check(df, row):
    """[(span, median |diff| vs P123 ret_1m, n days)] from 3 months before to 1 month after each streak."""
    r = ret21(df) if len(df) else pd.Series(dtype=float)
    out = []
    for span in str(row.streak_spans).split(";"):
        if ".." not in span:
            continue
        a, e = (pd.Timestamp(x.strip()) for x in span.split(".."))
        pp = P.get(row.ticker, pd.Series(dtype=float))
        pp = pp[(pp.index >= a - pd.Timedelta(days=92)) & (pp.index <= e + pd.Timedelta(days=31))]
        j = pd.concat([pp.rename("p"), r.rename("b")], axis=1, join="inner").dropna()
        out.append((span.strip(), float((np.log1p(j.p) - np.log1p(j.b)).abs().median()) if len(j) >= 10 else np.nan, len(j)))
    return out


def status_of(chk):
    bad = [s for s, m, n in chk if not (m == m and m <= TOL)]
    return ("OK" if not bad else "ALL_BAD" if len(bad) == len(chk) else "SOME_BAD"), bad


def candidates(row, first_seg):
    c = []
    if isinstance(row.former_symbols, str):
        c += [s.strip() for s in str(row.former_symbols).replace(",", ";").split(";") if s.strip()]
    try:
        sys.path.insert(0, os.path.join(config.REPO, "Scripts"))
        from build_v2_features import resolve_historical_ticker
        a = resolve_historical_ticker(row.ticker, (first_seg - pd.Timedelta(days=30)).date())
        if a:
            c.append(a)
    except Exception:  # noqa: BLE001 -- resolver is best-effort
        pass
    return [x for i, x in enumerate(c) if x and x != row.ticker and x not in c[:i]]


def fix_row(row):
    fp = os.path.join(ACTIVE_DIR, safe(row.ticker) + ".parquet")
    orig_dir = os.path.join(ACTIVE_DIR, "_orig")
    op = os.path.join(orig_dir, safe(row.ticker) + ".parquet")
    src = op if os.path.exists(op) else fp
    base = {"ticker": row.ticker, "list_row": row.list_row}
    if not os.path.exists(src):
        return {**base, "action": "NO_FILE"}
    cur = pd.read_parquet(src)
    before, _ = status_of(streak_check(cur, row))
    segs = events(row.ticker)
    action, note = "unchanged", ""
    if segs:
        first_seg = segs[0][0]
        parts = []
        for i, (d, t) in enumerate(segs):
            end = segs[i + 1][0] - pd.Timedelta(days=1) if i + 1 < len(segs) else pd.Timestamp.today()
            if t == row.ticker:
                b = cur.assign(_d=pd.to_datetime(cur.date))
                b = b[(b._d >= d) & (b._d <= end)].drop(columns="_d")
            else:
                b = fetch_daily(t, d.date().isoformat(), end.date().isoformat())
            if len(b):
                parts.append(b)
        dropped = int((pd.to_datetime(cur.date) < first_seg).sum())
        need = any(pd.Timestamp(s.split("..")[0].strip()) < first_seg + pd.Timedelta(days=30)
                   for s in str(row.streak_spans).split(";") if ".." in s)
        if need and first_seg > pd.Timestamp(START):
            for c in candidates(row, first_seg):
                b = fetch_daily(c, START, (first_seg - pd.Timedelta(days=1)).date().isoformat())
                if not len(b):
                    continue
                if np.busday_count(pd.Timestamp(b.date.max()).date(), first_seg.date()) > 3:
                    continue
                chk = [m for _, m, n in streak_check(b, row) if m == m]
                if chk and np.median(chk) <= TOL:
                    parts.insert(0, b)
                    note = f"prepended {c}"
                    break
        new = (pd.concat(parts).drop_duplicates("date").sort_values("date").reset_index(drop=True)
               if parts else cur.iloc[0:0])
        # Events are not always complete (AA: Massive starts it at the 2016 Alcoa split, P123 keeps the old history):
        # keep the rebuilt bars only if they match P123 on more streaks, or on as many while showing fewer
        # streaks with ANOTHER company's prices (ES 2008: EnergySolutions bars -> none).
        def score(df):
            chk = streak_check(df, row)
            ok = sum(m == m and m <= TOL for _, m, n in chk)
            wrong = sum(n >= 10 and not (m == m and m <= TOL) for _, m, n in chk)
            return ok, -wrong
        better = score(new) > score(cur) if len(new) else False
        if better and (len(new) != len(cur) or dropped or len(segs) > 1 or note):
            os.makedirs(orig_dir, exist_ok=True)
            if not os.path.exists(op):
                shutil.copy2(fp, op)
            new.to_parquet(fp, index=False)
            cur = new
            action = f"rebuilt: {len(segs)} segment(s), dropped {dropped} pre-segment bars" + (f", {note}" if note else "")
    after, bad = status_of(streak_check(cur, row))
    return {**base, "events": " > ".join(f"{t}@{d.date()}" for d, t in segs), "action": action,
            "status_before": before, "status_after": after, "bad_spans": "; ".join(bad),
            "bars": len(cur), "first_bar": cur.date.min() if len(cur) else None}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="*")
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    L = pd.read_csv(LIST)
    L["list_row"] = np.arange(2, len(L) + 2)
    L = L[~L.ticker.str.contains("^", regex=False)]
    if a.tickers:
        L = L[L.ticker.isin(a.tickers)]
    print(f"{len(L)} still-listed rows; loading P123 returns ...")
    load_p123(set(L.ticker))
    m = run_pool(fix_row, list(L.itertuples()), a.workers, "renames")
    p = os.path.join(config.DATA_DIR, "rename_fix_manifest.csv")
    if a.tickers and os.path.exists(p):
        old = pd.read_csv(p)
        m = pd.concat([old[~old.ticker.isin(m.ticker)], m])
    m.sort_values("list_row").to_csv(p, index=False)
    print(pd.crosstab(m.status_before, m.status_after).to_string())
    print(m.action.str.split(":").str[0].value_counts().to_string())
    print(f"manifest: {p}")


if __name__ == "__main__":
    main()
