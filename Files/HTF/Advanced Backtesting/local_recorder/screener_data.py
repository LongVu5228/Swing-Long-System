"""
Data layer for the local HTF screener (screener.html / chart.html, served by server.py).

Lists: the exact backtest scan (scan_htf_universe_v2.filter_all_cached_years_bucketed): ADR14 >= 5%, ADV30 >= $10M,
MktCap >= $50M, SMA10 and SMA20 rising over their own periods, then the top 16 per market-cap bucket
(small 50M-2B / mid 2-10B / large 10B+) by 1M / 3M / 6M return. Replay mode rebuilds any past date from the cached
P123 pull (raw_data_htf_v2/<year>.parquet). Live mode (later): the VPS job drops live_scanner/lists/<date>.json in
the same shape and it takes precedence over the raw rebuild for that date.

Graduates: tickers on any list in the GRAD_SESSIONS sessions before the date but not on today's lists.

Bars: list_daily/ (still-listed rows) or delisted_daily/ (^ rows) from the backtest caches; tickers missing there,
or stale for the date asked, are pulled from Massive on demand into backtest_data/screener_daily/. Everything sent
to the browser is cut at the as-of date, so a replay date never shows the future.

Armed flags: armed_replay.json / armed_live.json next to this file (replay practice never mixes with live).
Window = the 15 sessions after the arm date (the arm day is the confirmation day, orders from the next session).
Trade state before DAS is wired in is a DAILY-BAR ESTIMATE: triggered if a later high >= R1 + 1c, then
stopped (low <= trigger * (1 - 0.75 ADR) before a +20% partial), exit on a 20-day SMA touch, else open.
"""

import json
import math
import os
import re
import sys
import threading
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ADV = os.path.dirname(HERE)
HTF = os.path.dirname(ADV)
if HTF not in sys.path:
    sys.path.insert(0, HTF)
import htf_backtest.config  # noqa: E402,F401  (puts ep_backtest on the path)
from ep_backtest import calendar_utils  # noqa: E402

DATA = os.path.join(HTF, "backtest_data")
RAW = os.path.join(HTF, "raw_data_htf_v2")
LIST_CACHE = os.path.join(DATA, "screener_lists")
SCR_DAILY = os.path.join(DATA, "screener_daily")
LIVE_DIR = os.path.join(HTF, "live_scanner", "lists")
MASTER = os.path.join(ADV, "htf_annotations_master.csv")
LOCAL_STORE = os.path.join(HERE, "annotations_local.json")
SETTINGS = os.path.join(HERE, "screener_settings.json")
ARMED = {"replay": os.path.join(HERE, "armed_replay.json"), "live": os.path.join(HERE, "armed_live.json")}

ADR_MIN, ADV_MIN, CAP_MIN, TOP_N = 5.0, 10_000_000, 50, 16
BUCKETS = [("small", 50, 2_000), ("mid", 2_000, 10_000), ("large", 10_000, float("inf"))]
WINDOWS = ["1m", "3m", "6m"]
GRAD_SESSIONS = 63                   # ~3 months (older -> backlog)
WINDOW_SESSIONS = 15
STOP_ADR = 0.75
PATTERNS = ["Green HTF", "Perfect HTF", "Big Green Flag", "Big Perfect Flag", "Red HTF", "Big Red Flag"]
RED = {"Red HTF", "Big Red Flag"}
LOCK = threading.Lock()
TD = calendar_utils.TRADING_DAYS


def safe(name):
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def d10(x):
    return str(x)[:10]


# ------------------------------------------------------------------ lists
_YEAR = {}


def _raw_sig():
    """Changes whenever p123_daily.py appends days -> every in-memory cache below is rebuilt."""
    return tuple((f, os.path.getmtime(os.path.join(RAW, f))) for f in sorted(os.listdir(RAW)) if f.endswith(".parquet"))


_SIG = [None]


def _fresh():
    sig = _raw_sig()
    if sig != _SIG[0]:
        global _DATES, _ALL
        _YEAR.clear(); _DATES = None; _ALL = None; _SIG[0] = sig


def _year_lists(y):
    """Gated + ranked rows (any rank <= TOP_N) for one year, cached to parquet (rebuilt if the raw file changes)."""
    _fresh()
    if y in _YEAR:
        return _YEAR[y]
    src = os.path.join(RAW, f"{y}.parquet")
    if not os.path.exists(src):
        _YEAR[y] = pd.DataFrame()
        return _YEAR[y]
    os.makedirs(LIST_CACHE, exist_ok=True)
    dst = os.path.join(LIST_CACHE, f"{y}.parquet")
    if os.path.exists(dst) and os.path.getmtime(dst) >= os.path.getmtime(src):
        _YEAR[y] = pd.read_parquet(dst)
        return _YEAR[y]
    r = pd.read_parquet(src).dropna(subset=["adr14", "adv30", "mktcap", "sma10_rising_diff", "sma20_rising_diff"])
    r = r[(r.adr14 >= ADR_MIN) & (r.adv30 >= ADV_MIN) & (r.mktcap >= CAP_MIN)
          & (r.sma10_rising_diff > 0) & (r.sma20_rising_diff > 0)].copy()
    r["bucket"] = None
    for name, lo, hi in BUCKETS:
        r.loc[(r.mktcap >= lo) & (r.mktcap < hi), "bucket"] = name
    keep = np.zeros(len(r), bool)
    for w in WINDOWS:
        col = f"ret_{w}"
        rk = r.groupby(["date", "bucket"])[col].rank(method="first", ascending=False)
        r[f"rank_{w}"] = rk.where((rk <= TOP_N) & r[col].notna())
        keep |= r[f"rank_{w}"].notna().to_numpy()
    r = r[keep].reset_index(drop=True)
    r["date"] = r.date.astype(str).str[:10]
    r.to_parquet(dst, index=False)
    _YEAR[y] = r
    return r


def _live_dates():
    if not os.path.isdir(LIVE_DIR):
        return []
    return sorted(f[:10] for f in os.listdir(LIVE_DIR) if re.match(r"\d{4}-\d{2}-\d{2}\.json$", f))


_DATES = None


def scan_dates():
    """All dates the screener can show: every raw P123 date plus live drops."""
    global _DATES
    _fresh()
    if _DATES is None:
        ds = set()
        for f in sorted(os.listdir(RAW)):
            if f.endswith(".parquet"):
                ds |= set(pd.read_parquet(os.path.join(RAW, f), columns=["date"]).date.astype(str).str[:10].unique())
        _DATES = sorted(ds)
    return sorted(set(_DATES) | set(_live_dates()))


def _rows_for(day):
    live = os.path.join(LIVE_DIR, f"{day}.json")
    if os.path.exists(live):
        with open(live, encoding="utf-8") as fh:
            return pd.DataFrame(json.load(fh)["rows"])
    y = _year_lists(int(day[:4]))
    return y[y.date == day] if len(y) else pd.DataFrame()


_LCACHE = {}


def lists_for(day):
    """Cached per day; rebuilt when P123 days are added or a ticker is moved to the backlog."""
    mv = os.path.getmtime(MOVED) if os.path.exists(MOVED) else 0
    key = (day, _raw_sig(), mv)
    if key not in _LCACHE:
        if len(_LCACHE) > 40:
            _LCACHE.clear()
        _LCACHE[key] = _lists_for(day)
    return dict(_LCACHE[key])


def _lists_for(day):
    """{"1m_small": [row...], ...} sorted by rank, plus graduates and badges (which lists each ticker is on)."""
    today = _rows_for(day)
    out, on = {}, {}
    for w in WINDOWS:
        for b, _, _ in BUCKETS:
            key = f"{w}_{b}"
            if today.empty:
                out[key] = []
                continue
            g = today[(today.bucket == b) & today[f"rank_{w}"].notna()].sort_values(f"rank_{w}")
            out[key] = [dict(ticker=r.ticker, rank=int(r[f"rank_{w}"]), ret=float(r[f"ret_{w}"]), mktcap=float(r.mktcap),
                             adr=float(r.adr14), adv=float(r.adv30), bucket=b) for _, r in g.iterrows()]
            for r in out[key]:
                on.setdefault(r["ticker"], []).append(w.upper())
    # graduates: on a list in the prior GRAD_SESSIONS sessions (~3 months), on no list today
    pos = TD.searchsorted(pd.Timestamp(day))
    first = d10(TD[max(0, pos - GRAD_SESSIONS)].date())
    hist = []
    for y in range(int(first[:4]), int(day[:4]) + 1):
        f = _year_lists(y)
        if len(f):
            hist.append(f[(f.date >= first) & (f.date < day)])
    h = pd.concat(hist) if hist else pd.DataFrame()
    if len(h):
        h = h[~h.ticker.isin(on)]
    moved = _moved_to_backlog(day, h)
    if len(h) and moved:
        h = h[~h.ticker.isin(moved)]
    grads, gbadges = _past_lists(h)
    return {"date": day, "lists": out, "moved": sorted(moved), "badges": {t: sorted(set(v)) for t, v in on.items()},
            "graduates": grads, "gbadges": gbadges, "grad_from": first,
            "live": is_live(day)}


def is_live(day):
    """The newest scan day, if it is recent (P123 feed current) -> LIVE mode with its own armed list."""
    ds = scan_dates()
    recent = (pd.Timestamp.now().normalize() - pd.Timestamp(day)).days <= 6
    return os.path.exists(os.path.join(LIVE_DIR, f"{day}.json")) or (day == ds[-1] and recent)


def _past_lists(h):
    """Rows of past list appearances -> per list (window x cap bucket) one entry per ticker: last day on THAT list,
    days on it, best rank, and its numbers on that last day; newest first. Plus badges: which lists it was on."""
    out = {f"{w}_{b}": [] for w in WINDOWS for b, _, _ in BUCKETS}
    badges = {}
    if h is None or not len(h):
        return out, badges
    h = h.sort_values("date")
    for w in WINDOWS:
        hw = h[h[f"rank_{w}"].notna()]
        if not len(hw):
            continue
        g = hw.groupby(["bucket", "ticker"], sort=False)
        agg = g.agg(last_seen=("date", "max"), days_on=("date", "nunique"), best_rank=(f"rank_{w}", "min"),
                    mktcap=("mktcap", "last"), adr=("adr14", "last"), ret=(f"ret_{w}", "last")).reset_index()
        for b, gb in agg.groupby("bucket"):
            gb = gb.sort_values(["last_seen", "best_rank"], ascending=[False, True])
            out[f"{w}_{b}"] = [dict(ticker=r.ticker, last_seen=r.last_seen, days_on=int(r.days_on), best_rank=int(r.best_rank),
                                    bucket=b, mktcap=float(r.mktcap), adr=float(r.adr),
                                    ret=None if pd.isna(r.ret) else float(r.ret)) for r in gb.itertuples()]
        for t in agg.ticker.unique():
            badges.setdefault(t, set()).add(w.upper())
    return out, {t: sorted(v) for t, v in badges.items()}


_ALL = None


def _all_lists():
    """Every list appearance 2005 -> now (built once per server run from the per-year caches)."""
    global _ALL
    _fresh()
    if _ALL is None:
        ys = sorted(int(f[:4]) for f in os.listdir(RAW) if f[:4].isdigit() and f.endswith(".parquet"))
        _ALL = pd.concat([_year_lists(y) for y in ys if len(_year_lists(y))], ignore_index=True)
    return _ALL


def _gone(ticker, day):
    """Delisted before this date? List rows of delisted names end in ^YY (the delisting year)."""
    m = re.search(r"\^(\d{2})$", ticker)
    if not m:
        return False
    y = 2000 + int(m.group(1))
    if y != int(day[:4]):
        return y < int(day[:4])
    return (_last_bar(ticker) or "9999") < day        # delisted this year: gone once its last bar is behind us


_LAST = {}


def _last_bar(ticker):
    if ticker not in _LAST:
        p = os.path.join(DATA, "delisted_daily", safe(ticker) + ".parquet")
        _LAST[ticker] = None
        if os.path.exists(p):
            d = pd.read_parquet(p, columns=["date"]).date
            if len(d):
                _LAST[ticker] = str(pd.to_datetime(d).max())[:10]
        else:                                          # no delisted-bar file: last bar of the base symbol in the store
            try:
                from htf_backtest import market_store as MS
                st = MS.read_ticker(re.split(r"[.^]", ticker)[0])
                if len(st):
                    _LAST[ticker] = st.date.iloc[-1]
            except Exception:  # noqa: BLE001
                pass
    return _LAST[ticker]


def backlog_for(day):
    """Backlog: tickers whose LAST appearance on any list was before the graduate window (> ~3 months ago), back to
    the start of the data, minus names already delisted by this date. Once a ticker hits a scan it never leaves the
    screener: today -> graduates -> backlog."""
    L = lists_for(day)
    first, moved = L["grad_from"], set(L["moved"])
    recent = set(L["badges"]) | set(L["gbadges"])
    a = _all_lists()
    h = a[a.date < first]
    h = h[~h.ticker.isin(recent)]
    if moved:                                   # graduates you sent to the backlog: all their past appearances
        h = pd.concat([h[~h.ticker.isin(moved)], a[(a.date < day) & a.ticker.isin(moved)]])
    h = h[~h.ticker.map(lambda t: _gone(t, day))]
    lists, badges = _past_lists(h)
    return {"date": day, "backlog": lists, "bbadges": badges, "before": first, "moved": sorted(moved)}


# ---- "move to backlog": graduates you don't expect to set up soon. Stored with the screener date you moved it on;
# it applies from that date on and lapses by itself once the ticker is back on a list after that date (it shows in
# Today, then in Graduates again when it drops off).
MOVED = os.path.join(HERE, "moved_to_backlog.json")


def _moved_all():
    if not os.path.exists(MOVED):
        return {}
    with open(MOVED, encoding="utf-8") as fh:
        return json.load(fh)


def _moved_to_backlog(day, hist):
    m = {t: v["asof"] for t, v in _moved_all().items() if v["asof"] <= day}
    if not m or hist is None or not len(hist):
        return set(m) if m else set()
    last = hist.groupby("ticker").date.max()
    return {t for t, asof in m.items() if t not in last.index or last[t] <= asof}


def move_to_backlog(ticker, asof, undo=False):
    with LOCK:
        d = _moved_all()
        if undo:
            d.pop(ticker, None)
        else:
            d[ticker] = {"asof": asof, "at": datetime.now().isoformat(timespec="seconds")}
        with open(MOVED + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
        os.replace(MOVED + ".tmp", MOVED)
    return {"ok": True}


# ------------------------------------------------------------------ bars
_FETCHED = set()          # tickers already refreshed from Massive this server run


def _massive(sym, start, end):
    from htf_backtest.delisted_bars import fetch_daily
    return fetch_daily(sym, start, end)


def _read(p):
    df = pd.read_parquet(p)
    if df.empty or not {"open", "high", "low", "close", "date"} <= set(df.columns):
        return None
    df = df.dropna(subset=["open", "high", "low", "close"]).copy()
    df["date"] = pd.to_datetime(df.date).dt.strftime("%Y-%m-%d")
    if "volume" not in df:
        df["volume"] = 0
    df["volume"] = df.volume.fillna(0)
    return df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)


def _from_store(ticker, asof):
    """Bars from the all-stock store (htf_backtest.market_store), with pre-store history prepended from the old
    per-ticker caches. None if the store doesn't cover asof for this ticker (then the old path runs)."""
    try:
        from htf_backtest import market_store as MS
        cov = MS.coverage()
    except Exception:  # noqa: BLE001
        return None
    if not cov or asof < cov[0]:
        return None
    st = MS.read_ticker(ticker, asof)
    if st.empty or st.date.iloc[-1] < min(asof, cov[1]):
        return None                                   # not traded through asof in the store: let the old path try
    st = st.drop(columns=["ticker"])
    for p in (os.path.join(SCR_DAILY, safe(ticker) + ".parquet"), os.path.join(DATA, "list_daily", safe(ticker) + ".parquet")):
        if os.path.exists(p):
            old = _read(p)
            if old is not None:
                st = pd.concat([old[old.date < st.date.iloc[0]][["date", "open", "high", "low", "close", "volume"]], st])
                break
    return st.reset_index(drop=True)


_BCACHE = {}


def _store_sig():
    """Changes when the all-stock store gets new days -> cached bars are re-read."""
    p = os.path.join(DATA, "market_daily", "_state.json")
    return os.path.getmtime(p) if os.path.exists(p) else 0


def bars_for(ticker, asof):
    """Cached wrapper (2026-11-26: re-reading the store for every armed ticker on every refresh took ~0.3 s each)."""
    key = (ticker, asof, _store_sig())
    if key not in _BCACHE:
        if len(_BCACHE) > 600:
            _BCACHE.clear()
        _BCACHE[key] = _bars_for(ticker, asof)
    return _BCACHE[key]


def _bars_for(ticker, asof):
    """Daily bars through asof (cut there). All-stock store first; else the per-ticker caches, topped up from
    Massive one ticker at a time (slow on the free tier -- the store exists to avoid this)."""
    if "^" in ticker:
        p = os.path.join(DATA, "delisted_daily", safe(ticker) + ".parquet")
        return _read(p) if os.path.exists(p) else None
    s = _from_store(ticker, asof)
    if s is not None:
        return s
    srcs = [os.path.join(SCR_DAILY, safe(ticker) + ".parquet"), os.path.join(DATA, "list_daily", safe(ticker) + ".parquet")]
    df = None
    for p in srcs:
        if os.path.exists(p):
            df = _read(p)
            if df is not None and df.date.iloc[-1] >= asof:
                break
    stale = df is None or df.date.iloc[-1] < asof
    if stale and ticker not in _FETCHED and asof >= "2015-01-01":
        _FETCHED.add(ticker)
        today = date.today().isoformat()
        start = d10(pd.Timestamp(asof) - pd.Timedelta(days=6 * 366)) if df is None else df.date.iloc[0]
        try:
            new = _massive(ticker, start, today)
        except Exception:  # noqa: BLE001
            new = pd.DataFrame()
        if len(new):
            new["date"] = pd.to_datetime(new.date).dt.strftime("%Y-%m-%d")
            df = pd.concat([df, new]) if df is not None else new
            df = df.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
            os.makedirs(SCR_DAILY, exist_ok=True)
            df.to_parquet(srcs[0], index=False)
    if df is None:
        return None
    return df[df.date <= asof].reset_index(drop=True)


def adr14(df):
    """Backtest ADR14 for an entry the session after the last bar: (mean high - mean low, last 14) / last close."""
    if df is None or len(df) < 15:
        return None
    w = df.tail(14)
    return float((w.high.mean() - w.low.mean()) / df.close.iloc[-1])


def spy_status(asof):
    s = bars_for("SPY", asof)
    if s is None or len(s) < 200:
        p = os.path.join(DATA, "index_SPY.parquet")
        s = _read(p)
        s = s[s.date <= asof] if s is not None else None
    if s is None or len(s) < 200:
        return None
    sma = float(s.close.tail(200).mean())
    c = float(s.close.iloc[-1])
    return {"date": s.date.iloc[-1], "close": c, "sma200": sma, "above": c > sma, "pct": c / sma - 1}


# ------------------------------------------------------------------ earnings + past flags
_EARN = None


def earnings(sym):
    global _EARN
    if _EARN is None:
        e = pd.read_parquet(os.path.join(DATA, "earnings_benzinga.parquet"), columns=["ticker", "date"])
        e["date"] = pd.to_datetime(e.date).dt.strftime("%Y-%m-%d")
        _EARN = {t: sorted(set(g.date)) for t, g in e.groupby("ticker")}
    return _EARN.get(re.split(r"[.^]", sym)[0], [])


def _ymd(x):
    try:
        s = str(int(float(x)))
        return f"{s[:4]}-{s[4:6]}-{s[6:8]}"
    except (TypeError, ValueError):
        return None


_MASTER = None
_HAND = None


def _hand_labels():
    """(ticker, flag_no) -> your pattern call: hand truth file first, else the recorded pattern (backtest labels())."""
    global _HAND
    if _HAND is None:
        try:
            from htf_backtest.entry_test_report import labels
            lab = labels()
            _HAND = {(t, int(f)): h for t, f, h in zip(lab.ticker, lab.flag_no, lab.hand)}
        except Exception:  # noqa: BLE001
            _HAND = {}
    return _HAND


def past_flags(ticker, asof, df):
    """Flags recorded on this ticker before asof: TradingView master + local recorder store. R1 = the r1 bar's high."""
    global _MASTER
    if _MASTER is None:
        _MASTER = pd.read_csv(MASTER, usecols=["ticker", "flag_no", "flag_start", "setup_confirmed", "final_flag_end",
                                              "r1_source_bar", "r1_price", "pattern_recorded"]) if os.path.exists(MASTER) else pd.DataFrame()
    out = []
    hand = _hand_labels()
    if len(_MASTER):
        for r in _MASTER[(_MASTER.ticker == ticker) & (_MASTER.flag_no > 0)].itertuples():
            conf = _ymd(r.setup_confirmed)
            if conf and conf <= asof:
                pat = hand.get((ticker, int(r.flag_no)))
                if not isinstance(pat, str):
                    pat = r.pattern_recorded if isinstance(r.pattern_recorded, str) else None
                out.append(dict(start=_ymd(r.flag_start), conf=conf, end=min(_ymd(r.final_flag_end) or conf, asof),
                                r1_date=_ymd(r.r1_source_bar), r1=None if pd.isna(r.r1_price) else float(r.r1_price),
                                pattern=pat, src="TV"))
    if not out and os.path.exists(LOCAL_STORE):
        with open(LOCAL_STORE, encoding="utf-8") as fh:
            st = json.load(fh).get(ticker, {})
        hi = dict(zip(df.date, df.high)) if df is not None else {}
        for f in st.get("flags", []):
            if f.get("conf") and f["conf"] <= asof:
                out.append(dict(start=f.get("start"), conf=f["conf"], end=min(f.get("end") or f["conf"], asof),
                                r1_date=f.get("r1"), r1=hi.get(f.get("r1")), pattern=f.get("pattern"), src="local"))
    return out


# ------------------------------------------------------------------ armed store
def _load(mode):
    p = ARMED[mode]
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


def _save(mode, items):
    p = ARMED[mode]
    with open(p + ".tmp", "w", encoding="utf-8") as fh:
        json.dump(items, fh, indent=1)
    os.replace(p + ".tmp", p)


DRAWINGS = os.path.join(HERE, "drawings.json")


def drawings_get(tickers):
    if not os.path.exists(DRAWINGS):
        return {t: [] for t in tickers}
    with open(DRAWINGS, encoding="utf-8") as fh:
        d = json.load(fh)
    return {t: d.get(t, []) for t in tickers}


def drawings_set(ticker, items):
    """Replace one ticker's drawings (validated: trendlines and horizontal lines only). Each keeps "at" = when it
    was drawn or last edited (the browser stamps it; a missing stamp gets now) -> the "Recently drawn" tab."""
    def date_ok(x):
        return isinstance(x, str) and re.match(r"^\d{4}-\d{2}-\d{2}$", x)
    now = datetime.now().isoformat(timespec="seconds")
    clean_items = []
    for it in (items or [])[:500]:
        at = it.get("at") if isinstance(it.get("at"), str) and re.match(r"^\d{4}-\d{2}-\d{2}T", it.get("at", "")) else now
        if it.get("type") == "hline" and isinstance(it.get("price"), (int, float)):
            clean_items.append({"type": "hline", "price": float(it["price"]), "at": at[:19]})
        elif it.get("type") == "trend":
            a, b = it.get("a"), it.get("b")
            if all(isinstance(p, list) and len(p) == 2 and date_ok(p[0]) and isinstance(p[1], (int, float)) for p in (a, b)):
                clean_items.append({"type": "trend", "a": [a[0], float(a[1])], "b": [b[0], float(b[1])], "at": at[:19]})
    with LOCK:
        d = {}
        if os.path.exists(DRAWINGS):
            with open(DRAWINGS, encoding="utf-8") as fh:
                d = json.load(fh)
        if clean_items:
            d[ticker] = clean_items
        else:
            d.pop(ticker, None)
        with open(DRAWINGS + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
        os.replace(DRAWINGS + ".tmp", DRAWINGS)
    return clean_items


# ---- tags: your own labels per ticker (UT uptrending, DT downtrending, plus any you add)
TAGS = os.path.join(HERE, "tags.json")
DEFAULT_TAGS = ["UT", "DT", "N/A"]
PATTERN_TAG = {"Green HTF": "SG", "Big Green Flag": "BG", "Perfect HTF": "PF", "Big Perfect Flag": "BPF"}
# arming a flag adds its pattern as a tag; red patterns (watch only, not traded) add none


def tags_get():
    d = {"vocab": list(DEFAULT_TAGS), "tickers": {}}
    if os.path.exists(TAGS):
        with open(TAGS, encoding="utf-8") as fh:
            d.update(json.load(fh))
    return d


def tags_set(ticker=None, tags=None, vocab=None):
    """Set one ticker's tags (and/or the tag vocabulary). Tags are short words: letters, digits, - and _ (max 12)."""
    ok = lambda t: isinstance(t, str) and re.match(r"^[A-Za-z0-9_/\-]{1,12}$", t)     # "/" allowed: N/A
    with LOCK:
        d = tags_get()
        if vocab is not None:
            d["vocab"] = [t for t in dict.fromkeys(vocab) if ok(t)][:30]
        if ticker:
            clean_t = [t for t in dict.fromkeys(tags or []) if ok(t)][:10]
            for t in clean_t:                       # a new tag typed on a ticker joins the vocabulary
                if t not in d["vocab"]:
                    d["vocab"].append(t)
            if clean_t:
                d["tickers"][ticker] = clean_t
            else:
                d["tickers"].pop(ticker, None)
        with open(TAGS + ".tmp", "w", encoding="utf-8") as fh:
            json.dump(d, fh, indent=1)
        os.replace(TAGS + ".tmp", TAGS)
    return d


def drawings_recent(days=30):
    """Tickers whose latest drawing (made or edited) is within `days` of now, newest first."""
    if not os.path.exists(DRAWINGS):
        return []
    with open(DRAWINGS, encoding="utf-8") as fh:
        d = json.load(fh)
    mtime = datetime.fromtimestamp(os.path.getmtime(DRAWINGS)).isoformat(timespec="seconds")
    cut = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    out = []
    for t, items in d.items():
        if not items:
            continue
        last = max(it.get("at") or mtime for it in items)      # drawings from before the stamp existed: file time
        if last >= cut:
            out.append({"ticker": t, "last_drawn": last, "n": len(items)})
    return sorted(out, key=lambda x: x["last_drawn"], reverse=True)


def settings(new=None):
    s = {"account": 35000.0, "risk_pct": 0.25}
    if os.path.exists(SETTINGS):
        with open(SETTINGS, encoding="utf-8") as fh:
            s.update(json.load(fh))
    if new:
        for k in ("account", "risk_pct"):
            if k in new:
                s[k] = float(new[k])
        with open(SETTINGS, "w", encoding="utf-8") as fh:
            json.dump(s, fh, indent=1)
    return s


def arm(mode, body):
    """Create or update an armed / watch item. Red patterns can only be saved as watch."""
    pat = body.get("pattern")
    if pat not in PATTERNS:
        raise ValueError("pick a flag type")
    status = "watch" if pat in RED else body.get("status", "armed")
    with LOCK:
        items = _load(mode)
        it = next((x for x in items if x["id"] == body.get("id")), None) if body.get("id") else None
        if it is None:
            it = {"id": f"{body['ticker']}-{body['asof']}-{datetime.now():%H%M%S}", "ticker": body["ticker"],
                  "armed_on": body["asof"], "created": datetime.now().isoformat(timespec="seconds")}
            items.append(it)
        it.update(r1=round(float(body["r1"]), 4), r1_date=body["r1_date"], pattern=pat, status=status,
                  updated=datetime.now().isoformat(timespec="seconds"))
        _save(mode, items)
    # the pattern also becomes a tag (re-arming with another pattern swaps it; other tags stay)
    cur = tags_get()["tickers"].get(it["ticker"], [])
    tags_set(it["ticker"], [t for t in cur if t not in PATTERN_TAG.values()] + ([PATTERN_TAG[pat]] if pat in PATTERN_TAG else []))
    return it


def disarm(mode, item_id):
    with LOCK:
        items = _load(mode)
        for x in items:
            if x["id"] == item_id:
                x["was"] = x.get("status")            # a removed watch item is not shown in History
                x["status"] = "disarmed"
                x["updated"] = datetime.now().isoformat(timespec="seconds")
        _save(mode, items)


def _soon(asof, n=10):
    """The session n trading days after asof (earnings this close get flagged)."""
    return d10(calendar_utils.sessions_from(pd.Timestamp(asof).date() + timedelta(days=1), n)[-1])


def _window_end(armed_on):
    return d10(calendar_utils.sessions_from(pd.Timestamp(armed_on).date() + timedelta(days=1), WINDOW_SESSIONS)[-1])


def _sessions_between(a, b):
    """Sessions strictly after a, up to and including b."""
    return int(((TD > pd.Timestamp(a)) & (TD <= pd.Timestamp(b))).sum())


def _trade_state(df, it, adr, asof, win_end):
    """Daily-bar estimate of what the system would have done since the arm date (no minute data, no DAS)."""
    trig = round(it["r1"] + 0.01, 2)
    # no automatic expiry (user disarms by hand, 2026-11-25): a trigger can come any session after the arm date
    after = df[(df.date > it["armed_on"]) & (df.date <= asof)]
    hit = after[after.high >= trig]
    if hit.empty:
        return {"state": "WAITING"}
    d0 = hit.date.iloc[0]
    fill = max(trig, float(hit.open.iloc[0]))
    stop = fill * (1 - STOP_ADR * adr) if adr else None
    risk = fill - stop if stop else None
    sma20 = df.close.rolling(20).mean()
    post = df[df.date >= d0]
    partial = False
    for i, r in post.iterrows():
        floor = fill if partial else stop          # breakeven after the first partial (+20%)
        if floor is not None and r.low <= floor:
            if not partial:
                return {"state": "STOPPED", "entry_date": d0, "fill": fill, "closed_on": r.date, "R": -1.0}
            return {"state": "EXITED", "entry_date": d0, "fill": fill, "closed_on": r.date, "R": 0.0, "note": "breakeven"}
        if r.high >= fill * 1.20:
            partial = True
        if r.date > d0 and pd.notna(sma20[i]) and r.low <= sma20[i]:
            px = min(float(r.open), float(sma20[i]))
            return {"state": "EXITED", "entry_date": d0, "fill": fill, "closed_on": r.date,
                    "R": round((px - fill) / risk, 2) if risk else None}
    last = float(df.close.iloc[-1])
    return {"state": "IN TRADE", "entry_date": d0, "fill": fill, "open_R": round((last - fill) / risk, 2) if risk else None}


def armed_view(mode, asof):
    """Active / watch / history items as of asof, with order preview, context and estimated trade state."""
    s = settings()
    risk_usd = s["account"] * s["risk_pct"] / 100
    lists = lists_for(asof) if asof in set(scan_dates()) else {"badges": {}, "lists": {}}
    caps = {r["ticker"]: r for v in lists["lists"].values() for r in v}
    active, watch, hist = [], [], []
    for it in _load(mode):
        if it["armed_on"] > asof:
            continue                                     # armed after the replay date: hide
        df = bars_for(it["ticker"], asof)
        if df is None or df.empty:
            continue
        a = adr14(df)
        win_end = _window_end(it["armed_on"])
        left = max(0, WINDOW_SESSIONS - _sessions_between(it["armed_on"], asof))
        last = float(df.close.iloc[-1])
        trig = round(it["r1"] + 0.01, 2)
        stop = trig * (1 - STOP_ADR * a) if a else None
        rps = trig - stop if stop else None
        shares = int(risk_usd // rps) if rps and rps > 0 else None
        nxt = next((d for d in earnings(it["ticker"]) if d > asof), None)
        row = dict(it, last=last, last_date=df.date.iloc[-1], pct_to_r1=trig / last - 1, sessions_left=left,
                   r1_days=_sessions_between(it["r1_date"], asof),   # trading days since the R1 candle
                   window_end=win_end, adr=a, trigger=trig, stop=stop, stop_pct=(1 - stop / trig) if stop else None,
                   shares=shares, position=shares * trig if shares else None, risk_usd=risk_usd,
                   earnings_next=nxt, earnings_in_window=bool(nxt and nxt <= _soon(asof)),
                   badges=lists["badges"].get(it["ticker"], []),
                   mktcap=caps.get(it["ticker"], {}).get("mktcap"), bucket=caps.get(it["ticker"], {}).get("bucket"))
        if it["status"] == "disarmed":
            if it.get("was") == "watch":
                continue
            if it.get("updated", "")[:10] >= d10(pd.Timestamp(asof) - pd.Timedelta(days=30)) or mode == "replay":
                hist.append(dict(row, state="DISARMED"))
            continue
        if it["status"] == "watch":
            watch.append(row)
            continue
        st = _trade_state(df, it, a, asof, win_end)
        row.update(st)
        closed = st.get("closed_on")
        if closed and closed <= asof:
            if closed >= d10(pd.Timestamp(asof) - pd.Timedelta(days=30)):
                hist.append(row)
        else:
            active.append(row)
    active.sort(key=lambda x: (x["state"] != "IN TRADE", x["armed_on"]), reverse=False)
    hist.sort(key=lambda x: x.get("closed_on") or "", reverse=True)
    return {"active": active, "watch": watch, "history": hist, "settings": s, "asof": asof, "mode": mode}


def chart_payload(ticker, asof):
    df = bars_for(ticker, asof)
    if df is None:
        return None
    a = adr14(df)
    return {"ticker": ticker, "asof": asof,
            "bars": [[d, o, h, l, c, v] for d, o, h, l, c, v in zip(df.date, df.open, df.high, df.low, df.close, df.volume)],
            "earnings": [d for d in earnings(ticker) if df.date.iloc[0] <= d <= asof],
            "earnings_next": next((d for d in earnings(ticker) if d > asof), None),
            "flags": past_flags(ticker, asof, df), "adr": a}


def clean(o):
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.floating):
        return clean(float(o))
    if isinstance(o, (np.integer, np.bool_)):
        return o.item()
    return o
