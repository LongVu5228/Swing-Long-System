"""
Local chart viewer + flag recorder for the whole HTF list (replaces the TradingView recorder from row 1,217 on;
originally built for the delisted rows, which TradingView cannot chart).

Serves recorder.html on http://127.0.0.1:8765 (localhost only) with the Massive daily bars pulled
by htf_backtest/delisted_bars.py. Every save writes:
  - local_recorder/annotations_local.json   (the editing truth: reopen a ticker, flags come back)
  - ~/Downloads/DELISTED_<ticker>, 1D.csv   (^ rows) or LOCAL_<ticker>, 1D.csv (still-listed rows), both in the
    TradingView recorder export format (schema 5)
so `python ingest_exports.py` files it into htf_annotations_master.csv exactly like a TV chart --
pattern "Auto" is classified there by the same labeler.

    cd "Files/HTF/Advanced Backtesting/local_recorder"
    ../../../../.venv/Scripts/python.exe server.py          # then open http://127.0.0.1:8765
"""

import json
import os
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ADV = os.path.dirname(HERE)
HTF = os.path.dirname(ADV)
DATA = os.path.join(HTF, "backtest_data")
DAILY = os.path.join(DATA, "delisted_daily")
DAILY_ACTIVE = os.path.join(DATA, "list_daily")          # htf_backtest.delisted_bars --active
MASTER = os.path.join(ADV, "htf_annotations_master.csv")
STORE = os.path.join(HERE, "annotations_local.json")
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
LIST = os.path.join(HTF, "htf_scanner_master_by_ticker.csv")
REVIEWS = {"1m": "htf_1m_flag_review_v2_flagpole_bucketed.csv", "3m": "htf_3m_flag_review_v2_flagpole_bucketed.csv",
           "6m": "htf_6m_flag_review_v2_flagpole_bucketed.csv"}
PATTERN_CODE = {"Green HTF": 1, "Red HTF": 2, "Perfect HTF": 3, "Big Green Flag": 4, "Big Red Flag": 5,
                "Big Perfect Flag": 6}
RED = {"Red HTF", "Big Red Flag"}
PORT = 8765
LOCK = threading.Lock()


def safe(name):
    import re
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def is_delisted(t):
    return "^" in t


def export_name(t):
    return f"{'DELISTED' if is_delisted(t) else 'LOCAL'}_{t}, 1D.csv"


def tv_charted():
    """Tickers already charted with the TradingView recorder: in the master (non-^) or a TV export in Downloads."""
    import re
    out = {}
    if os.path.exists(MASTER):
        m = pd.read_csv(MASTER, usecols=["ticker", "flag_no"])
        m = m[~m.ticker.str.contains("^", regex=False)]
        out = m[m.flag_no > 0].groupby("ticker").size().to_dict()
        out.update({t: 0 for t in set(m.ticker) - set(out)})
    rx = re.compile(r"^(?P<exch>[A-Z_]+?)_(?P<ticker>[A-Z0-9.\-^]+), (?P<tf>\w+)(?: \((?P<dup>\d+)\))?\.csv$")
    for f in os.listdir(DOWNLOADS):
        g = rx.match(f)
        if g and g["exch"] not in ("DELISTED", "LOCAL"):
            out.setdefault(g["ticker"], -1)              # exported, not ingested yet
    return out


def load_list():
    b = pd.read_csv(LIST)
    b["list_row"] = np.arange(2, len(b) + 2)
    d = b.copy()
    cols = ["ticker", "status", "symbol_used", "bars", "p123_ret1m_median_diff"]
    mans = [pd.read_csv(os.path.join(DATA, f))[cols] for f in ("delisted_daily_manifest.csv", "list_daily_manifest.csv")
            if os.path.exists(os.path.join(DATA, f))]
    d = d.merge(pd.concat(mans), on="ticker", how="left")
    tv = tv_charted()
    d["tv_flags"] = d.ticker.map(tv)
    # per-streak check vs P123 (htf_backtest.recheck_streaks) supersedes the whole-history manifest status:
    # a reused / renamed symbol can pass on its good years and still show another company under a streak (ES 2008)
    sc = os.path.join(DATA, "streak_check.csv")
    if os.path.exists(sc):
        c = pd.read_csv(sc)[["ticker", "streak_status", "bad_spans"]]
        d = d.merge(c, on="ticker", how="left")
        bad = d.streak_status.isin(["ALL_BAD", "SOME_BAD"])
        d.loc[bad, "status"] = d.loc[bad, "streak_status"].map({"ALL_BAD": "BAD_DATA", "SOME_BAD": "SOME_STREAKS_BAD"})
        d.loc[d.streak_status.eq("OK"), "status"] = "OK"
    d["next"] = d.ticker.shift(-1).fillna("")
    d["prev"] = d.ticker.shift(1).fillna("")
    return d


def load_windows():
    out = {}
    for w, f in REVIEWS.items():
        p = os.path.join(HTF, f)
        if not os.path.exists(p):
            continue
        r = pd.read_csv(p, usecols=["ticker", "first_qualifying_date", "last_qualifying_date", "status", "hh_dates"])
        for x in r.itertuples():
            e = out.setdefault(x.ticker, {"1m": [], "3m": [], "6m": [], "hh": set()})
            if x.status == "OK":
                e[w].append([x.first_qualifying_date, x.last_qualifying_date])
            if isinstance(x.hh_dates, str):
                e["hh"] |= {h.strip() for h in x.hh_dates.split(";") if h.strip()}
    for e in out.values():
        e["hh"] = sorted(e["hh"])
    return out


def load_p123():
    """Unused: P123 market cap / adv30 now read per ticker from backtest_data/p123_by_ticker/ (one 11M-row frame
    took ~4 min to load)."""
    return None


P123_DIR = os.path.join(DATA, "p123_by_ticker")


def p123_for(t):
    """[[date, mktcap $M, adv30], ...] for one list row (built from the delisted + still-listed P123 caches)."""
    p = os.path.join(P123_DIR, safe(t) + ".parquet")
    if not os.path.exists(p):
        return []
    g = pd.read_parquet(p)
    return list(zip(g.date, g.mktcap, g.adv30))


def load_earnings():
    p = os.path.join(DATA, "earnings_benzinga.parquet")
    if not os.path.exists(p):
        return {}
    e = pd.read_parquet(p)
    e["date"] = pd.to_datetime(e["date"]).dt.strftime("%Y-%m-%d")
    return {t: sorted(set(g.date)) for t, g in e.groupby("ticker")}


def read_store():
    if not os.path.exists(STORE):
        return {}
    with open(STORE, encoding="utf-8") as fh:
        return json.load(fh)


def write_store(s):
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(s, fh, indent=1)
    os.replace(tmp, STORE)


def bars(ticker):
    p = os.path.join(DAILY if is_delisted(ticker) else DAILY_ACTIVE, safe(ticker) + ".parquet")
    if not os.path.exists(p):
        return None
    df = pd.read_parquet(p)
    if df.empty or not {"open", "high", "low", "close", "date"} <= set(df.columns):
        return None                        # e.g. FCE.A^18: Massive had nothing for it
    df = df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)
    if "volume" in df:
        df["volume"] = df["volume"].fillna(0)
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df


def classify(ticker, f):
    """Same call ingest_exports.py makes for a slot left on Auto -> the pattern ingest will record."""
    from types import SimpleNamespace
    if ADV not in sys.path:
        sys.path.insert(0, ADV)
    import htf_pattern_labeler as hpl
    df = bars(ticker)
    if df is None or not (f.get("start") and f.get("conf") and f.get("end")):
        return None
    b = pd.DataFrame({"d": df.date.str.replace("-", "").astype(int), "open": df.open, "high": df.high,
                      "low": df.low, "close": df.close}).reset_index(drop=True)
    start, conf, end = ymd(f["start"]), ymd(f["conf"]), ymd(f["end"])
    cross = None
    if f.get("r1") and end != conf:
        lvl = b.high[b.d == ymd(f["r1"])]
        if len(lvl):
            fwd = b[(b.d >= conf) & (b.high >= float(lvl.iloc[0]))]
            cross = int(fwd.d.iloc[0]) if len(fwd) else None
    fl = SimpleNamespace(flag_start=start, setup_confirmed=conf, final_flag_end=end, r1_first_cross=cross)
    try:
        return hpl.label_flag(b, fl)["pattern"]
    except Exception as exc:  # noqa: BLE001
        return f"ERROR: {exc}"


def ymd(s):
    return int(str(s).replace("-", ""))


def export_csv(ticker, flags, df):
    """TradingView-recorder-format export (schema 5) -> Downloads, for ingest_exports.py."""
    rec = {1: 5}
    slot = 0
    for f in flags:
        if not (f.get("start") and f.get("conf") and f.get("end")):
            continue
        if not (f["start"] <= f["conf"] <= f["end"]) or (f.get("r1") and f["r1"] > f["conf"]):
            continue                      # out-of-order clicks never reach the master
        slot += 1
        b = slot * 100
        pat = f.get("pattern") or "Auto"
        end_eq_conf = f["end"] == f["conf"]
        if pat in PATTERN_CODE:
            setup = (2 if end_eq_conf else 3) if pat in RED else 1
        else:
            setup = 0
        rec.update({b + 1: 1, b + 2: setup, b + 3: ymd(f["start"]), b + 4: ymd(f["conf"]), b + 5: ymd(f["end"]),
                    b + 6: ymd(f["conf"]), b + 7: ymd(f["r1"]) if f.get("r1") else np.nan,
                    b + 8: np.nan, b + 9: np.nan, b + 10: PATTERN_CODE.get(pat, np.nan)})
    if slot == 0:
        return None
    out = pd.DataFrame({
        "time": [int(datetime.strptime(d, "%Y-%m-%d").replace(hour=14, minute=30, tzinfo=timezone.utc).timestamp())
                 for d in df.date],
        "open": df.open, "high": df.high, "low": df.low, "close": df.close, "Volume": df.get("volume")})
    keys = list(rec.keys())
    out["ANNO_KEY"] = pd.Series(keys + [np.nan] * (len(out) - len(keys)))[:len(out)].to_numpy()
    out["ANNO_VAL"] = pd.Series(list(rec.values()) + [np.nan] * (len(out) - len(keys)))[:len(out)].to_numpy()
    path = os.path.join(DOWNLOADS, export_name(ticker))
    out.to_csv(path, index=False)
    return path


def clean(o):
    """NaN / inf -> null: browsers reject the bare NaN that json.dumps writes, and the ticker never opens."""
    if isinstance(o, float):
        return None if (o != o or o in (float("inf"), float("-inf"))) else o
    if isinstance(o, dict):
        return {k: clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [clean(v) for v in o]
    if isinstance(o, np.floating):
        return clean(float(o))
    if isinstance(o, np.integer):
        return int(o)
    return o


# ---- blind trainer (trainer.html): grade a flag with everything after its confirmation day withheld ----
TQUEUE = os.path.join(ADV, "htf_trainer_queue.csv")
TKEY = os.path.join(ADV, "htf_trainer_key.csv")
TFIELDS = ["pattern", "r1_date", "clean", "notes"]


def trainer_queue():
    q = pd.read_csv(TQUEUE, dtype=str).fillna("")
    k = pd.read_csv(TKEY, usecols=["train_id", "setup_confirmed"], dtype=str)
    return q.merge(k, on="train_id", how="left")


_SPAN = {}


def bar_span(t):
    """(first, last) bar date of a ticker's daily file, cached: a renamed symbol may start after the flag."""
    if t not in _SPAN:
        p = os.path.join(DAILY if is_delisted(t) else DAILY_ACTIVE, safe(t) + ".parquet")
        _SPAN[t] = None
        if os.path.exists(p):
            d = pd.read_parquet(p, columns=["date"]).date
            if len(d):
                d = pd.to_datetime(d).dt.strftime("%Y-%m-%d")
                _SPAN[t] = (d.min(), d.max())
    return _SPAN[t]


def trainer_list():
    q = trainer_queue()
    n_on = q.groupby("ticker").train_id.transform("size")
    out = []
    for r, n in zip(q.itertuples(), n_on):
        c, sp = f"{r.setup_confirmed[:4]}-{r.setup_confirmed[4:6]}-{r.setup_confirmed[6:8]}", bar_span(r.ticker)
        out.append({"id": int(r.train_id), "half": r.half, "done": bool(r.pattern), "k": int(r.flag_on_ticker),
                    "n": int(n), "ticker": r.ticker, "has_bars": bool(sp and sp[0] < c <= sp[1])})
    return out


def trainer_item(tid):
    """Bars, scanner windows, earnings and P123 data CUT AT the confirmation day, server-side: nothing after it
    ever reaches the browser."""
    q = trainer_queue()
    r = q[q.train_id == str(tid)]
    if r.empty:
        return None
    r = r.iloc[0]
    conf = f"{r.setup_confirmed[:4]}-{r.setup_confirmed[4:6]}-{r.setup_confirmed[6:8]}"
    df = bars(r.ticker)
    out = {"id": int(tid), "half": r.half, "k": int(r.flag_on_ticker), "ticker": r.ticker, "conf": conf,
           "answer": {f: r[f] for f in TFIELDS}, "bars": [], "windows": {"1m": [], "3m": [], "6m": []},
           "earnings": [], "p123": []}
    if df is None:
        return out
    df = df[df.date <= conf]
    out["bars"] = [[d, o, h, l, c, v] for d, o, h, l, c, v in
                   zip(df.date, df.open, df.high, df.low, df.close, df.get("volume", df.close * 0))]
    w = WINDOWS.get(r.ticker, {})
    for key in ("1m", "3m", "6m"):
        out["windows"][key] = [[a, min(b, conf)] for a, b in w.get(key, []) if a <= conf]
    row = LISTDF[LISTDF.ticker == r.ticker]
    sym = (row.symbol_used.iloc[0] if len(row) and isinstance(row.symbol_used.iloc[0], str) else r.ticker.split("^")[0])
    out["earnings"] = [d for d in EARN.get(sym, []) if d <= conf]
    out["p123"] = [x for x in p123_for(r.ticker) if x[0] <= conf]
    out["bad_spans"] = (row.bad_spans.iloc[0] if len(row) and "bad_spans" in row and isinstance(row.bad_spans.iloc[0], str)
                        else None)
    return out


def trainer_save(body):
    tid = str(int(body["id"]))
    with LOCK:
        q = pd.read_csv(TQUEUE, dtype=str).fillna("")
        i = q.index[q.train_id == tid]
        if not len(i):
            return False
        for f in TFIELDS:
            q.loc[i, f] = " ".join(str(body.get(f) or "").split())     # one line per CSV cell
        tmp = TQUEUE + ".tmp"
        q.to_csv(tmp, index=False)
        os.replace(tmp, TQUEUE)
    return True


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(clean(body), default=str, allow_nan=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)
        return True     # "handled": the screener router sends its own 404 only when a handler returned None

    def _screener_get(self, u, q):
        """Live / replay screener (screener.html, chart.html; data in screener_data.py)."""
        import screener_data as SD
        if u.path in ("/screener", "/chart"):
            with open(os.path.join(HERE, u.path[1:] + ".html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if u.path == "/scr_common.js":
            with open(os.path.join(HERE, "scr_common.js"), "rb") as fh:
                return self._send(200, fh.read(), "text/javascript; charset=utf-8")
        if u.path == "/api/scr/dates":
            ds = SD.scan_dates()
            return self._send(200, {"dates": ds, "latest": ds[-1], "patterns": SD.PATTERNS, "red": sorted(SD.RED)})
        if u.path == "/api/scr/lists":
            d = q.get("date") or SD.scan_dates()[-1]
            out = SD.lists_for(d)
            out["spy"] = SD.spy_status(d)
            return self._send(200, SD.clean(out))
        if u.path == "/api/scr/bars":
            p = SD.chart_payload(q.get("t", ""), q.get("asof") or SD.scan_dates()[-1])
            return self._send(200, SD.clean(p)) if p else self._send(404, {"error": "no bars"})
        if u.path == "/api/scr/backlog":
            return self._send(200, SD.clean(SD.backlog_for(q.get("date") or SD.scan_dates()[-1])))
        if u.path == "/api/scr/tags":
            return self._send(200, SD.tags_get())
        if u.path == "/api/scr/drawings_recent":
            return self._send(200, SD.drawings_recent(int(q.get("days", 30))))
        if u.path == "/api/scr/drawings":
            ts = [t for t in q.get("t", "").split(",") if t][:200]
            return self._send(200, SD.drawings_get(ts))
        if u.path == "/api/scr/armed":
            return self._send(200, SD.clean(SD.armed_view(q.get("mode", "replay"), q.get("asof") or SD.scan_dates()[-1])))
        return None

    def _screener_post(self, u, body):
        import screener_data as SD
        if u.path == "/api/scr/drawings":
            t = str(body.get("ticker", ""))
            if not t:
                return self._send(400, {"error": "ticker missing"})
            return self._send(200, {"ok": True, "drawings": SD.drawings_set(t, body.get("drawings"))})
        if u.path == "/api/scr/tags":
            return self._send(200, SD.tags_set(body.get("ticker"), body.get("tags"), body.get("vocab")))
        if u.path == "/api/scr/backlog_move":
            if not body.get("ticker") or not body.get("asof"):
                return self._send(400, {"error": "ticker / asof missing"})
            return self._send(200, SD.move_to_backlog(str(body["ticker"]), str(body["asof"])[:10], bool(body.get("undo"))))
        mode = body.get("mode", "replay")
        if mode not in SD.ARMED:
            return self._send(400, {"error": "bad mode"})
        try:
            if u.path == "/api/scr/arm":
                return self._send(200, SD.clean(SD.arm(mode, body)))
            if u.path == "/api/scr/disarm":
                SD.disarm(mode, body["id"])
                return self._send(200, {"ok": True})
            if u.path == "/api/scr/settings":
                return self._send(200, SD.settings(body))
        except (KeyError, ValueError) as exc:
            return self._send(400, {"error": str(exc)})
        return None

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.path in ("/screener", "/chart", "/scr_common.js") or u.path.startswith("/api/scr/"):
            if self._screener_get(u, q) is None:
                self._send(404, {"error": "not found"})
            return
        if u.path == "/trainer":
            with open(os.path.join(HERE, "trainer.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if u.path == "/api/trainer/list":
            return self._send(200, trainer_list())
        if u.path == "/api/trainer/item":
            it = trainer_item(q.get("id", ""))
            return self._send(200, it) if it else self._send(404, {"error": "unknown id"})
        if u.path in ("/", "/index.html"):
            with open(os.path.join(HERE, "recorder.html"), "rb") as fh:
                return self._send(200, fh.read(), "text/html; charset=utf-8")
        if u.path == "/api/list":
            st = read_store()
            rows = []
            for r in LISTDF.itertuples():
                s = st.get(r.ticker, {})
                rows.append({"ticker": r.ticker, "row": int(r.list_row), "status": r.status if isinstance(r.status, str) else "MISSING",
                             "n_flags": len(s.get("flags", [])), "reviewed": bool(s.get("reviewed")),
                             "tv": None if pd.isna(r.tv_flags) else int(r.tv_flags), "delisted": is_delisted(r.ticker)})
            return self._send(200, rows)
        if u.path == "/api/ticker":
            t = q.get("t", "")
            row = LISTDF[LISTDF.ticker == t]
            if row.empty:
                return self._send(404, {"error": "unknown ticker"})
            r = row.iloc[0]
            df = bars(t)
            st = read_store().get(t, {})
            info = {k: (None if (isinstance(v, float) and np.isnan(v)) else v) for k, v in r.to_dict().items()}
            sym = info.get("symbol_used") or info.get("chart_symbol")
            lo, hi = (df.date.iloc[0], df.date.iloc[-1]) if df is not None and len(df) else ("", "")
            earn = [d for d in EARN.get(sym, []) if lo <= d <= hi]
            return self._send(200, {
                "info": info,
                "bars": [] if df is None else [[d, o, h, l, c, v] for d, o, h, l, c, v in
                                              zip(df.date, df.open, df.high, df.low, df.close, df.get("volume", df.close * 0))],
                "windows": WINDOWS.get(t, {"1m": [], "3m": [], "6m": [], "hh": []}),
                "flags": st.get("flags", []), "reviewed": st.get("reviewed"),
                "p123": p123_for(t), "earnings": earn})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/scr/"):
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if self._screener_post(u, body) is None:
                self._send(404, {"error": "not found"})
            return
        if u.path == "/api/classify":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            return self._send(200, {"pattern": classify(body.get("ticker"), body.get("flag", {}))})
        if u.path == "/api/trainer/save":
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            return self._send(200 if trainer_save(body) else 400, {"ok": True})
        if u.path != "/api/save":
            return self._send(404, {"error": "not found"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        t, flags, no_flags = body.get("ticker"), body.get("flags", []), bool(body.get("no_flags"))
        if t not in set(LISTDF.ticker):
            return self._send(400, {"error": "unknown ticker"})
        with LOCK:
            s = read_store()
            s[t] = {"flags": flags, "reviewed": datetime.now().isoformat(timespec="seconds") if (flags or no_flags) else None,
                    "no_flags": no_flags and not flags}
            write_store(s)
        path, removed = None, False
        df = bars(t)
        if flags and df is not None:
            path = export_csv(t, flags, df)
        if path is None:
            # no complete flags left: drop the stale export so ingest can't pick up deleted flags
            old = os.path.join(DOWNLOADS, export_name(t))
            if os.path.exists(old):
                os.remove(old)
                removed = True
        return self._send(200, {"ok": True, "export": path, "removed": removed})


LISTDF = load_list()
WINDOWS = load_windows()
P123 = load_p123()
EARN = load_earnings()

if __name__ == "__main__":
    nb = sum(1 for t in LISTDF.ticker if os.path.exists(os.path.join(DAILY if is_delisted(t) else DAILY_ACTIVE, safe(t) + ".parquet")))
    print(f"{len(LISTDF)} list rows, {nb} with daily bars")
    print(f"open http://127.0.0.1:{PORT}   (Ctrl+C to stop)   blind trainer: http://127.0.0.1:{PORT}/trainer"
          f"   screener: http://127.0.0.1:{PORT}/screener")
    def _store_update():
        """1) P123: append the newest scan days (exact backtest formulas) -> the screener's lists go live.
        2) Bring the all-stock daily store up to the last close (1 Massive call per missing session + split checks)."""
        try:
            if HTF not in sys.path:
                sys.path.insert(0, HTF)
            import p123_daily
            n = p123_daily.pull(verbose=False)
            print(f"P123 scan feed: +{n} day(s)" if n else "P123 scan feed: up to date")
        except Exception as exc:  # noqa: BLE001
            print("P123 scan feed skipped:", exc)
        try:
            if HTF not in sys.path:
                sys.path.insert(0, HTF)
            from htf_backtest import market_store as MS
            if MS.coverage():
                n = MS.update(verbose=False)
                print(f"market store up to date: {MS.coverage()[1]} (+{n} sessions)")
        except Exception as exc:  # noqa: BLE001
            print("market store update skipped:", exc)
    threading.Thread(target=_store_update, daemon=True).start()
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
    except KeyboardInterrupt:
        sys.exit(0)
