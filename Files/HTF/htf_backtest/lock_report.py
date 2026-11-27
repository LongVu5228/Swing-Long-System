"""Lock re-check (2026-11-24): trades_lock_slip0.1.parquet (run_stage2 --stage lock).

A. Entries head-to-head at the locked stop / trail (0.75 ADR / 20ma_touch / e15 / ref ladder).
B. Core split + ladder variants on the locked entry (30m).
Views: all flags | FINAL = skip red (hand labels) + SPY prior close > 200d SMA. Losses get -0.3R extra (the -1.3R per
loss cost model, §39). No re-try here (same for every row, so comparisons are like-for-like).
Paired bootstrap by flag vs the locked row (flag R = 0 when a variant doesn't trade it), 2,000 resamples, 90% CI.

    ../../.venv/Scripts/python.exe -m htf_backtest.lock_report
"""
import os

import numpy as np
import pandas as pd

from . import config
from .entry_test_report import RED, labels
from .mgmt_report import spy_ok

OUT = config.OUTPUTS_DIR
LOCK_SID, LOCK_P = "E30M__S0.75ADR__T20MA_TOUCH", "ref"
LOSS_EXTRA = -0.3


def stats(t):
    r = t.R.to_numpy()
    n = len(r)
    if n == 0:
        return {}
    o = np.argsort(t.entry_date.to_numpy(), kind="stable")
    eq = np.cumsum(r[o])
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    w, l = r[r > 0], r[r <= 0]
    s = np.sort(r)
    yr = t.groupby(t.entry_date.str[:4]).R.sum()
    return dict(n=n, win=len(w) / n, avg_win=w.mean() if len(w) else np.nan, avg_loss=l.mean() if len(l) else np.nan,
                RR=w.mean() / -l.mean() if len(w) and len(l) else np.nan, EV=r.mean(),
                EV_ex5=s[:n - int(np.ceil(n * .05))].mean(), total=r.sum(), maxDD=dd, calmar=r.sum() / abs(dd) if dd else np.nan,
                neg_years=int((yr < 0).sum()), n10R=int((r >= 10).sum()))


def paired(t, sid, part, flags, rng):
    a = t[(t.strategy_id == LOCK_SID) & (t.partial == LOCK_P)].groupby("fk").R.sum().reindex(flags, fill_value=0).to_numpy()
    b = t[(t.strategy_id == sid) & (t.partial == part)].groupby("fk").R.sum().reindex(flags, fill_value=0).to_numpy()
    d = b - a
    idx = rng.integers(0, len(d), (2000, len(d)))
    bs = d[idx].sum(1)
    return d.sum(), np.percentile(bs, 5), np.percentile(bs, 95)


def main():
    t = pd.read_parquet(os.path.join(OUT, "trades_lock_slip0.1.parquet"))
    t = t[t.status == "OK"].copy()
    t["entry_date"] = t.entry_date.astype(str).str[:10]
    t["R"] = t.realized_R + np.where(t.realized_R <= 0, LOSS_EXTRA, 0)
    t = t.merge(labels(), on=["ticker", "flag_no"], how="left")
    spy = spy_ok()
    t["spy"] = t.entry_date.map(lambda d: spy.get(d, False))
    t["fk"] = t.ticker + "#" + t.flag_no.astype(str)
    rng = np.random.default_rng(7)
    pd.set_option("display.width", 260)
    rows = []
    for view, v in (("all flags", t), ("FINAL (skip red + SPY>200d)", t[t.hand.notna() & ~t.hand.isin(RED) & t.spy])):
        flags = v.fk.unique()
        for (sid, part), g in v.groupby(["strategy_id", "partial"]):
            if not (part == "ref" or sid == LOCK_SID):
                continue
            d, lo, hi = paired(v, sid, part, flags, rng)
            rows.append(dict(view=view, block="A entries" if part == "ref" else "B exits", entry=g.entry_type.iloc[0],
                             partial=part, **stats(g), dTotal_vs_lock=d, ci90_lo=lo, ci90_hi=hi))
    s = pd.DataFrame(rows)
    base = s[(s.entry == "30m") & (s.partial == "ref")].assign(block="B exits")   # locked row heads both blocks
    s = pd.concat([s, base], ignore_index=True)
    s.to_csv(os.path.join(OUT, "lock_recheck.csv"), index=False)
    cols = ["entry", "partial", "n", "win", "avg_win", "avg_loss", "RR", "EV", "EV_ex5", "total", "maxDD", "calmar",
            "neg_years", "n10R", "dTotal_vs_lock", "ci90_lo", "ci90_hi"]
    for (view, blk), g in s.groupby(["view", "block"], sort=False):
        print(f"\n=== {view} | {blk}  (R incl. -1.3R per loss; dTotal = total R vs 30m/ref, paired by flag)")
        print(g.sort_values("EV", ascending=False)[cols].round(3).to_string(index=False))
    print(f"\nsaved {os.path.join(OUT, 'lock_recheck.csv')}")


if __name__ == "__main__":
    main()
