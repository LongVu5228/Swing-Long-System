"""Step 4 (findings doc §26): entry filters on the phase 2-3 finalists, TV + delisted flags, 15-session expiry, ref ladder.

Strategies: E30M__S1.50ADR__T20MA_TOUCH (finalist, trades_final2_slip*) and E30M__S0.75ADR__T20MA_TOUCH (high-RR #3,
trades_highrr_slip*), at slippage 0.1% and 0.3%, each on all flags and with red flags skipped (hand labels).

Every feature uses only what is known at the entry: market cap / ADV30 on the last P123 day <= setup_confirmed,
entry price, stop width, % above R1 at the fill, ADR14, SPY / IWM close vs their 200-day SMA on the PRIOR session,
Benzinga earnings in the next 10 sessions (judged 2015+ only, where the dates are dense). Cutoffs are pre-declared
(round numbers / earlier doc sections), never tuned on these trades.

A filter PASSES only if the kept trades beat the unfiltered strategy on EV in every one of 5 periods (2005-15,
2016-26 halves; 2016-19 / 2020-22 / 2023-26 walk-forward test windows), improve Calmar, and keep >= 70% of the
10R+ trades.

    ../../.venv/Scripts/python.exe -m htf_backtest.step4_filters      # -> backtest_outputs/step4_filters.csv
"""
import os
import re

import numpy as np
import pandas as pd

from . import config
from .delisted_bars import safe
from .entry_test_report import RED, labels

OUT = config.OUTPUTS_DIR
DATA = config.DATA_DIR
STRATS = {"1.5ADR": ("final2", "E30M__S1.50ADR__T20MA_TOUCH"), "0.75ADR": ("highrr", "E30M__S0.75ADR__T20MA_TOUCH")}
PERIODS = {"05-15": (2005, 2015), "16-26": (2016, 2026), "WF16-19": (2016, 2019), "WF20-22": (2020, 2022),
           "WF23-26": (2023, 2026)}


def load(tag, sid, slip):
    t = pd.read_parquet(os.path.join(OUT, f"trades_{tag}_slip{slip}.parquet"))
    t = t[(t.status == "OK") & (t.partial == "ref") & (t.strategy_id == sid)].copy()
    t["entry_date"] = pd.to_datetime(t.entry_date.astype(str))
    t["conf"] = pd.to_datetime(t.setup_confirmed.astype(int).astype(str))
    return t


def add_features(t):
    # market cap / ADV at confirmation
    caps = []
    for tk in t.ticker.unique():
        p = os.path.join(DATA, "p123_by_ticker", safe(tk) + ".parquet")
        if os.path.exists(p):
            caps.append(pd.read_parquet(p).assign(ticker=tk))
    cap = pd.concat(caps)
    cap["date"] = pd.to_datetime(cap.date).astype("datetime64[ns]")
    t = t.sort_values("conf")
    t["conf"] = t.conf.astype("datetime64[ns]")
    t = pd.merge_asof(t, cap.sort_values("date")[["date", "ticker", "mktcap", "adv30"]], left_on="conf",
                      right_on="date", by="ticker", direction="backward", tolerance=pd.Timedelta("10D")).drop(columns="date")
    t["ext_pct"] = (t.entry_fill / t.r1_price - 1) * 100
    t["adr_pct"] = t.adr14 * 100 if t.adr14.max() < 1 else t.adr14
    # regime on the prior session's close (known before the entry day's open)
    for ix in ("SPY", "IWM"):
        b = pd.read_parquet(os.path.join(DATA, f"index_{ix}.parquet"))
        b["date"] = pd.to_datetime(b.date).astype("datetime64[ns]")
        b = b.sort_values("date")
        b["sma200"] = b.close.rolling(200).mean()
        b[f"{ix}_above"] = b.close > b.sma200
        b[f"{ix}_rising"] = b.sma200 > b.sma200.shift(20)
        b["date"] = b.date + pd.Timedelta(days=1)            # as-of strictly before the entry date
        t = pd.merge_asof(t.sort_values("entry_date").assign(entry_date=lambda d: d.entry_date.astype("datetime64[ns]")),
                          b[["date", f"{ix}_above", f"{ix}_rising"]], left_on="entry_date", right_on="date",
                          direction="backward").drop(columns="date")
    # earnings within the next 10 sessions (entry day included), Benzinga, base symbol of delisted rows
    e = pd.read_parquet(os.path.join(DATA, "earnings_benzinga.parquet"), columns=["ticker", "date"])
    e["date"] = pd.to_datetime(e.date)
    ed = e.groupby("ticker").date.apply(lambda s: np.sort(s.unique()))
    base = t.ticker.map(lambda x: re.split(r"[.^]", x)[0])
    def soon(tk, d):
        arr = ed.get(tk)
        if arr is None:
            return False
        lo = np.searchsorted(arr, np.datetime64(d))
        return lo < len(arr) and np.busday_count(np.datetime64(d, "D"), np.datetime64(arr[lo], "D")) <= 10
    t["earn10"] = [soon(b_, d) for b_, d in zip(base, t.entry_date)]
    t["y"] = t.entry_date.dt.year
    return t


FILTERS = {   # name -> keep mask (pre-declared cutoffs)
    "cap < 2B": lambda d: d.mktcap < 2000,
    "cap < 10B": lambda d: d.mktcap < 10000,
    "cap 300M-10B": lambda d: d.mktcap.between(300, 10000),
    "price >= 5": lambda d: d.entry_fill >= 5,
    "price >= 10": lambda d: d.entry_fill >= 10,
    "ADV30 >= $5M": lambda d: d.adv30 >= 5e6,
    "ADV30 >= $20M": lambda d: d.adv30 >= 20e6,
    "stop >= 3%": lambda d: d.stop_pct >= 3,
    "stop >= 5%": lambda d: d.stop_pct >= 5,
    "ADR >= 4%": lambda d: d.adr_pct >= 4,
    "ADR >= 6%": lambda d: d.adr_pct >= 6,
    "fill <= 2% over R1": lambda d: d.ext_pct <= 2,
    "fill <= 4% over R1": lambda d: d.ext_pct <= 4,
    "SPY > 200d": lambda d: d.SPY_above,
    "SPY 200d rising": lambda d: d.SPY_rising,
    "IWM > 200d": lambda d: d.IWM_above,
    "SPY or IWM > 200d": lambda d: d.SPY_above | d.IWM_above,
    "no earnings in 10 sessions (2015+)": lambda d: ~d.earn10,
}


def st(r, dates):
    o = np.argsort(dates, kind="stable")
    r = np.asarray(r, float)[o]
    n = len(r)
    if n < 20:
        return dict(n=n)
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    s = np.sort(r)
    return dict(n=n, win=(r > 0).mean(), EV=r.mean(), ex5=s[:n - int(np.ceil(n * .05))].mean(), total=r.sum(), dd=dd,
                calmar=r.sum() / abs(dd) if dd else np.nan, n10=int((r >= 10).sum()))


def evaluate(d, keep):
    base, k = st(d.realized_R, d.entry_date), st(d[keep].realized_R, d[keep].entry_date)
    row = {"n_all": base["n"], "n_kept": k["n"], "kept_pct": k["n"] / base["n"], "EV_all": base["EV"], "EV_kept": k.get("EV"),
           "EV_dropped": d[~keep].realized_R.mean(), "ex5_all": base["ex5"], "ex5_kept": k.get("ex5"),
           "DD_all": base["dd"], "DD_kept": k.get("dd"), "calmar_all": base["calmar"], "calmar_kept": k.get("calmar"),
           "10R_kept": f"{k.get('n10', 0)}/{base['n10']}"}
    wins = 0
    for p, (a, b) in PERIODS.items():
        m = d.y.between(a, b)
        diff = d[m & keep].realized_R.mean() - d[m].realized_R.mean()
        row[f"dEV_{p}"] = diff
        wins += diff > 0
    row["periods_better"] = wins
    mon_ok = base["n10"] == 0 or k.get("n10", 0) / base["n10"] >= 0.7
    row["PASS"] = bool(wins == len(PERIODS) and (k.get("calmar") or 0) > base["calmar"] and mon_ok)
    return row


def main():
    rows = []
    lab = labels()
    for sname, (tag, sid) in STRATS.items():
        for slip in ("0.1", "0.3"):
            t = add_features(load(tag, sid, slip)).merge(lab, on=["ticker", "flag_no"], how="left")
            if slip == "0.1":
                print(f"{sname}: {len(t)} trades | mktcap known {t.mktcap.notna().mean():.0%} | adv {t.adv30.notna().mean():.0%}"
                      f" | earnings-in-10 {t.earn10.mean():.1%} (2015+: {t[t.y >= 2015].earn10.mean():.1%})")
            for view, d in (("all", t), ("skip red", t[t.hand.notna() & ~t.hand.isin(RED)])):
                d = d.reset_index(drop=True)
                for fname, fn in FILTERS.items():
                    dd = d[d.y >= 2015].reset_index(drop=True) if "2015+" in fname else d
                    keep = fn(dd).fillna(True).astype(bool).to_numpy() if hasattr(fn(dd), "fillna") else fn(dd)
                    rows.append({"strategy": sname, "slip": slip, "view": view, "filter": fname, **evaluate(dd, keep)})
    s = pd.DataFrame(rows)
    p = os.path.join(OUT, "step4_filters.csv")
    s.to_csv(p, index=False)
    pd.set_option("display.width", 260)
    cols = ["filter", "kept_pct", "EV_all", "EV_kept", "EV_dropped", "ex5_kept", "DD_all", "DD_kept", "calmar_all",
            "calmar_kept", "10R_kept", "periods_better", "PASS"]
    for (sn, sl, v), g in s.groupby(["strategy", "slip", "view"], sort=False):
        print(f"\n=== {sn} | slip {sl}% | {v}")
        print(g[cols].round(3).to_string(index=False))
    print("\nfilters passing in every strategy x slip x view:")
    allp = s.groupby("filter").PASS.agg(["sum", "size"])
    print(allp.sort_values("sum", ascending=False).to_string())
    print(f"\nsaved {p}")


if __name__ == "__main__":
    main()
