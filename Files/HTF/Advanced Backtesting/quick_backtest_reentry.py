"""
Re-entry test on top of quick_backtest_chosen_one.py: after a trade is stopped out, buy again
if price trades back through the ORIGINAL R1 within REENTRY_WINDOW sessions.

Re-entry uses the exact same daily-proxy mechanics as the first entry (qb.simulate): sessions
strictly after the stop-out day, first one whose high >= R1, filled at max(R1, open) + slippage,
fresh 0.5 ADR stop off the new entry, same ladder / breakeven / 20-day SMA core exit. The real
plan buys over the 60-minute high, which needs intraday bars -- this is the daily proxy, same
caveat as the base backtest.

One re-entry per original trade by default; --max-reentries N chains further re-entries off
re-entries that also stop out.

    python quick_backtest_reentry.py
    python quick_backtest_reentry.py --window 7 --max-reentries 2
"""
import argparse
import os
from collections import namedtuple

import numpy as np
import pandas as pd

import quick_backtest_chosen_one as qb

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "quick_backtest_reentry_trades.csv")
STOP_EXITS = {"STOP", "STOP_GAP"}

Flag = namedtuple("Flag", "ticker flag_no setup_type setup_confirmed final_flag_end r1_price")


def boot_ci(x, n=20000, seed=42):
    rs = np.random.default_rng(seed)
    bs = np.array([rs.choice(x, len(x)).mean() for _ in range(n)])
    return np.percentile(bs, 2.5), np.percentile(bs, 97.5)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=int, default=7, help="sessions after the stop-out to allow a re-entry")
    ap.add_argument("--max-reentries", type=int, default=1)
    args = ap.parse_args()

    m = qb.read_master()
    flags = m[(m["flag_no"] > 0) & (~m["ticker"].isin(qb.EXCLUDE))]
    bars_of, rows = {}, []
    for f in flags.itertuples():
        if f.ticker not in bars_of:
            bars_of[f.ticker] = qb.load_bars(f.ticker)
        bars = bars_of[f.ticker]
        if bars is None:
            continue
        r = qb.simulate(f, bars, "mid")
        r["leg"] = 0
        rows.append(r)
        prev = r
        for leg in range(1, args.max_reentries + 1):
            if prev.get("status") != "OK" or prev.get("exit_reason") not in STOP_EXITS:
                break
            i_exit = int(bars.index[bars["d"] == prev["exit_date"]][0])
            j_end = min(i_exit + args.window, len(bars) - 1)
            synth = Flag(f.ticker, f.flag_no, f.setup_type, int(prev["exit_date"]),
                         int(bars.at[j_end, "d"]), f.r1_price)
            re = qb.simulate(synth, bars, "mid")
            re["leg"] = leg
            re["prior_R"] = prev["realized_R"]
            re["days_after_stop"] = (int(bars.index[bars["d"] == re["entry_date"]][0]) - i_exit
                                     if re.get("status") in ("OK", "STILL_OPEN") else None)
            rows.append(re)
            prev = re

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    first = df[(df["leg"] == 0) & (df["status"] == "OK")]
    stopped = first[first["exit_reason"].isin(STOP_EXITS)]
    re = df[df["leg"] >= 1]
    re_ok = re[re["status"] == "OK"]

    print(f"window {args.window} sessions after stop-out, max {args.max_reentries} re-entr(y/ies), daily proxy (mid)\n")
    print(f"first entries: {len(first)}  stopped out: {len(stopped)} "
          f"({(stopped['realized_R'] < 0).sum()} full-loss stops, {(stopped['realized_R'] >= 0).sum()} breakeven/after-partial stops)")
    trig = re[re["status"].isin(["OK", "STILL_OPEN"])]
    print(f"re-entries triggered: {len(trig)} of {len(re)} stop-outs checked "
          f"({len(trig)/max(len(re),1)*100:.0f}%), median {trig['days_after_stop'].median():.0f} sessions after the stop\n")

    print("re-entry trades:")
    qb.summarize(re_ok, "ALL")
    for t in ("HL_FLAG", "LL_RECLAIM"):
        qb.summarize(re_ok[re_ok["setup_type"] == t], t)
    if len(re_ok):
        lo, hi = boot_ci(re_ok["realized_R"].to_numpy())
        print(f"  EV 95% CI [{lo:+.2f}, {hi:+.2f}]")
        print(f"  after a FULL-loss stop:      ", end=""); qb.summarize(re_ok[re_ok["prior_R"] < 0], "")
        print(f"  after a breakeven-type stop: ", end=""); qb.summarize(re_ok[re_ok["prior_R"] >= 0], "")
        for leg in sorted(re_ok["leg"].unique()):
            if leg > 1:
                qb.summarize(re_ok[re_ok["leg"] == leg], f"leg {leg}")
        re_ok = re_ok.assign(yr=re_ok["entry_date"] // 10000)
        g = re_ok.groupby("yr")["realized_R"].agg(n="size", ev="mean").round(2)
        print("\n  by year (re-entries):\n" + g[g.index >= 2016].T.to_string())

    base = first["realized_R"].sum()
    combo = base + re_ok["realized_R"].sum()
    print(f"\nsystem total: base {base:+.1f}R over {len(first)} trades (EV {first['realized_R'].mean():+.3f}R)  ->  "
          f"with re-entries {combo:+.1f}R over {len(first)+len(re_ok)} trades "
          f"(EV {combo/(len(first)+len(re_ok)):+.3f}R per trade, {combo/len(first):+.3f}R per original flag)")
    print(f"\ntrade log: {OUT}")


if __name__ == "__main__":
    main()
