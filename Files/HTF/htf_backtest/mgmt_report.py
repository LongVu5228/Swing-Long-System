"""Step 13 report: re-entry variants + earnings hold rules on trades_mgmt_slip0.1.parquet (mgmt.py).

Re-entry: per flag R = sum of the attempts a variant accepts. Variant = time limit (W15: inside the original
15-session order window | X5 / X10: within 5 / 10 sessions after the previous exit) x trigger (loss: previous attempt
lost | any: any exit) x max attempts (2 / 3). A chain stops at the first attempt the variant rejects. Flags whose
accepted chain hits a DATA_SHORT attempt (minute cache ends before a possible re-entry) are UNKNOWN and dropped from
that variant AND its baseline, so each comparison is on the same flags.

Views: all flags | skip red + SPY > 200d (prior close; re-entries must pass it too, else the chain stops).

Earnings (2015+, Benzinga, base symbol): for every attempt-1 trade still open at the close before its next report
(BMO / intraday report on D -> sell at D-1 close; AMC on D -> D close; unknown time -> D-1), post-process its sales:
hold | sell all | sell half | sell all / half unless cushioned (a partial already taken or close >= entry + 1R).

    ../../.venv/Scripts/python.exe -m htf_backtest.mgmt_report
"""
import json
import os
import re

import numpy as np
import pandas as pd

from . import config
from .entry_test_report import RED, labels

OUT = config.OUTPUTS_DIR
SLIP = config.SLIPPAGE_PCT
PERIODS = {"05-15": (2005, 2015), "16-26": (2016, 2026), "WF16-19": (2016, 2019), "WF20-22": (2020, 2022),
           "WF23-26": (2023, 2026)}


def spy_ok():
    b = pd.read_parquet(os.path.join(config.DATA_DIR, "index_SPY.parquet"))
    b["date"] = pd.to_datetime(b.date)
    b = b.sort_values("date")
    ok = b.close > b.close.rolling(200).mean()
    nxt = b.date.shift(-1)                    # the session whose prior close this is
    return dict(zip(nxt.dt.strftime("%Y-%m-%d"), ok))


def seq_stats(r, dates):
    o = np.argsort(np.asarray(dates), kind="stable")
    r = np.asarray(r, float)[o]
    if not len(r):
        return dict(n=0)
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    return dict(n=len(r), EV=r.mean(), total=r.sum(), dd=dd, calmar=r.sum() / abs(dd) if dd else np.nan,
                win=(r > 0).mean())


def chains(m, window, trigger, max_k, spy=None):
    """-> per-flag frame: R_base (attempt 1 only), R_var (accepted chain), n_trades, unknown, first entry date, y."""
    out = []
    for (tk, fn), g in m.groupby(["ticker", "flag_no"], sort=False):
        g = g.sort_values("attempt")
        a1 = g.iloc[0]
        if a1.attempt != 1 or a1.status != "OK" or (spy is not None and not spy.get(a1.entry_date, False)):
            continue
        rs, unknown, prev = [a1.realized_R], False, a1
        for _, a in g.iloc[1:].iterrows():
            if a.attempt > max_k:
                break
            if trigger == "loss" and not (prev.realized_R < 0):
                break
            ok_time = (a.within_window if window == "W15" else
                       (a.sessions_after_prev_exit is not None and a.sessions_after_prev_exit <= int(window[1:])))
            if not ok_time or (spy is not None and not spy.get(a.entry_date, False)):
                break
            if a.status != "OK":
                unknown = a.status == "DATA_SHORT"
                break
            rs.append(a.realized_R)
            prev = a
        out.append(dict(ticker=tk, flag_no=fn, date=a1.entry_date, R_base=a1.realized_R, R_var=sum(rs),
                        n_trades=len(rs), re_R=sum(rs[1:]), unknown=unknown, trades=[(a1.entry_date, r) for r in rs]))
    return pd.DataFrame(out)


def reentry(m, view_name, spy):
    rows = []
    for window in ("W15", "X5", "X10"):
        for trigger in ("loss", "any"):
            for k in (2, 3):
                c = chains(m, window, trigger, k, spy)
                unk = c.unknown.sum()
                c = c[~c.unknown]
                c["y"] = c.date.str[:4].astype(int)
                base = seq_stats(c.R_base, c.date)
                tr = [(d, r) for lst in c.trades for d, r in lst]
                var = seq_stats([r for _, r in tr], [d for d, _ in tr])
                reent = c[c.n_trades > 1]
                row = dict(view=view_name, window=window, trigger=trigger, max_attempts=k, flags=len(c), unknown=int(unk),
                           reentries=int((c.n_trades - 1).sum()), R_per_flag_base=c.R_base.mean(),
                           R_per_flag_var=c.R_var.mean(), reentry_trade_EV=reent.re_R.sum() / max(1, (c.n_trades - 1).sum()),
                           total_base=base["total"], total_var=var["total"], DD_base=base["dd"], DD_var=var["dd"],
                           calmar_base=base["calmar"], calmar_var=var["calmar"])
                wins = 0
                for p, (a, b) in PERIODS.items():
                    s = c[c.y.between(a, b)]
                    d = (s.R_var - s.R_base).mean()
                    row[f"d_{p}"] = d
                    wins += d > 0
                row["periods_better"] = wins
                rows.append(row)
    return pd.DataFrame(rows)


def earnings_rules(m, view_name, spy):
    from . import simulate as S
    e = pd.read_parquet(os.path.join(config.DATA_DIR, "earnings_benzinga.parquet"), columns=["ticker", "date", "time"])
    e["date"] = pd.to_datetime(e.date)
    hh = pd.to_numeric(e.time.astype(str).str[:2], errors="coerce")
    e["amc"] = hh >= 16
    e = e.sort_values("date")
    t = m[(m.attempt == 1) & (m.status == "OK") & (m.entry_date >= "2015-01-01")].copy()
    if spy is not None:
        t = t[t.entry_date.map(lambda d: spy.get(d, False))]
    rows = []
    for tk, g in t.groupby("ticker"):
        base = re.split(r"[.^]", tk)[0]
        ev = e[e.ticker == base]
        daily = S.daily_frame(tk)
        if daily is None:
            continue
        closes = pd.Series(daily.close.to_numpy(), index=pd.to_datetime(daily.date))
        days = closes.index
        for a in g.itertuples():
            ed, xd = pd.Timestamp(a.entry_date), pd.Timestamp(a.exit_date)
            risk = a.entry_fill - a.stop_price
            sales = [(pd.Timestamp(s[0][:10]), s[1], s[2], s[3]) for s in json.loads(a.sales)]
            rec = dict(view=view_name, ticker=tk, flag_no=a.flag_no, strategy_id=a.strategy_id, entry_date=a.entry_date,
                       R_hold=a.realized_R, exposed=False)
            nxt = ev[ev.date >= ed]
            if len(nxt):
                d0 = nxt.iloc[0]
                pos = days.searchsorted(d0.date)
                sell = d0.date if d0.amc else (days[pos - 1] if pos > 0 else None)
                if sell is not None and sell in closes.index and ed <= sell < xd:
                    before = [s for s in sales if s[0] <= sell]
                    after = [s for s in sales if s[0] > sell]
                    rem = 1 - sum(s[2] for s in before)
                    if rem > 1e-9:
                        px = closes[sell] * (1 - SLIP)
                        rb = sum(s[2] * (s[1] - a.entry_fill) for s in before) / risk
                        ra = sum(s[2] * (s[1] - a.entry_fill) for s in after) / risk
                        r_all = rb + rem * (px - a.entry_fill) / risk
                        r_half = rb + 0.5 * rem * (px - a.entry_fill) / risk + 0.5 * ra
                        cushion = any("TARGET" in str(s[3]).upper() or "PARTIAL" in str(s[3]).upper() for s in before) \
                            or closes[sell] >= a.entry_fill + risk
                        rec.update(exposed=True, cushion=cushion, R_sell_all=r_all, R_sell_half=r_half,
                                   R_all_unless_cushion=a.realized_R if cushion else r_all,
                                   R_half_unless_cushion=a.realized_R if cushion else r_half)
            for k in ("R_sell_all", "R_sell_half", "R_all_unless_cushion", "R_half_unless_cushion"):
                rec.setdefault(k, a.realized_R)
            rows.append(rec)
    return pd.DataFrame(rows)


def main():
    m = pd.read_parquet(os.path.join(OUT, "trades_mgmt_slip0.1.parquet"))
    m["entry_date"] = m.entry_date.astype(str).str[:10]
    m.loc[m.entry_date.isin(["None", "nan", "NaT"]), "entry_date"] = None
    lab = labels()
    m = m.merge(lab, on=["ticker", "flag_no"], how="left")
    spy = spy_ok()
    pd.set_option("display.width", 260)
    re_all, earn_all = [], []
    for sid, ms in m.groupby("strategy_id"):
        for view, mv, sp in (("all", ms, None), ("skip red + SPY>200d", ms[ms.hand.notna() & ~ms.hand.isin(RED)], spy)):
            r = reentry(mv, view, sp).assign(strategy=sid)
            re_all.append(r)
            print(f"\n=== RE-ENTRY | {sid} | {view}")
            print(r.drop(columns=["view", "strategy"]).round(3).to_string(index=False))
            ea = earnings_rules(mv, view, sp)
            earn_all.append(ea)
            x = ea.sort_values("entry_date")
            print(f"\n=== EARNINGS (2015+) | {sid} | {view}: {len(x)} trades, {x.exposed.sum()} open into a report "
                  f"({x[x.exposed].cushion.astype(bool).mean():.0%} of those cushioned)")
            out = []
            for k in ("R_hold", "R_sell_all", "R_sell_half", "R_all_unless_cushion", "R_half_unless_cushion"):
                s = seq_stats(x[k], x.entry_date)
                ex = x[x.exposed][k]
                out.append(dict(rule=k, EV=s["EV"], total=s["total"], DD=s["dd"], calmar=s["calmar"],
                                exposed_EV=ex.mean(), exposed_worst=ex.min(), exposed_10R=int((ex >= 10).sum())))
            print(pd.DataFrame(out).round(3).to_string(index=False))
    pd.concat(re_all).to_csv(os.path.join(OUT, "step13_reentry.csv"), index=False)
    pd.concat(earn_all).to_csv(os.path.join(OUT, "step13_earnings.csv"), index=False)
    print("\nsaved step13_reentry.csv, step13_earnings.csv")


if __name__ == "__main__":
    main()
