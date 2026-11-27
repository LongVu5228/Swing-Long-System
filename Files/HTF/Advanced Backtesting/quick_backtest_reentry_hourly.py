"""
Re-entry test with the REAL 60-minute ORH entry (5-minute bars), on flags inside the free
Massive tier's intraday history -- the check on quick_backtest_reentry.py's daily proxy.

First entry and re-entry both use quick_backtest_hourly.simulate: per session, trigger =
max(60m ORH + 1 tick, R1), fills only after 10:30 ET, entry day walked in 5-minute bars,
later days on the TradingView daily bars. After a STOP / STOP_GAP exit, the re-entry window is
the REENTRY_WINDOW sessions after the stop-out day, same original R1. The daily proxy is run
on the same flags for an apples-to-apples comparison.

The free tier keeps a rolling ~2 years of intraday history, so COVERAGE_START is set a little
inside that floor. Intraday bars are pulled once per ticker over all its flags (cached).

    python quick_backtest_reentry_hourly.py
"""
import os
from collections import namedtuple
from datetime import timedelta

import numpy as np
import pandas as pd

import quick_backtest_chosen_one as qb
import quick_backtest_hourly as hb

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "quick_backtest_reentry_hourly_trades.csv")
COVERAGE_START = 20241101
REENTRY_WINDOW = 7
STOP_EXITS = {"STOP", "STOP_GAP"}

Flag = namedtuple("Flag", "ticker flag_no setup_type setup_confirmed final_flag_end r1_price")


def exit_info(r, bars):
    """(exit bar index, exit date) for a finished trade from either simulator."""
    if r.get("status") != "OK" or r.get("exit_reason") not in STOP_EXITS:
        return None
    i_entry = int(bars.index[bars["d"] == r["entry_date"]][0])
    i_exit = i_entry + int(r["holding_days"])
    return i_exit, int(bars.at[i_exit, "d"])


def reentry_flag(f, bars, i_exit):
    j_end = min(i_exit + REENTRY_WINDOW, len(bars) - 1)
    return Flag(f.ticker, f.flag_no, f.setup_type, int(bars.at[i_exit, "d"]),
                int(bars.at[j_end, "d"]), f.r1_price)


def intraday_for(ticker, flag, intra_all):
    """Slice the per-ticker pull; fetch the window separately if it runs past it."""
    lo, hi = flag.setup_confirmed, flag.final_flag_end
    have = intra_all[ticker]
    if not have.empty and have["d"].max() >= hi:
        return have[(have["d"] > lo) & (have["d"] <= hi)]
    start = hb.ymd_to_date(lo) + timedelta(days=1)
    end = hb.ymd_to_date(hi)
    return hb.fetch_5min(ticker, start, end) if end >= start else pd.DataFrame()


def main():
    m = qb.read_master()
    flags = m[(m["flag_no"] > 0) & (~m["ticker"].isin(qb.EXCLUDE)) & m["r1_price"].notna()
              & (m["setup_confirmed"] >= COVERAGE_START)]
    print(f"{len(flags)} flags, {flags['ticker'].nunique()} tickers in intraday coverage", flush=True)

    bars_of, intra_all = {}, {}
    for n, (t, g) in enumerate(flags.groupby("ticker"), 1):
        bars_of[t] = qb.load_bars(t)
        start = hb.ymd_to_date(g["setup_confirmed"].min()) + timedelta(days=1)
        end = min(hb.ymd_to_date(g["final_flag_end"].max()) + timedelta(days=45),
                  hb.ymd_to_date(int(bars_of[t]["d"].iloc[-1])))
        intra_all[t] = hb.fetch_5min(t, start, end)
        print(f"  intraday {n}/{flags['ticker'].nunique()} {t}: {len(intra_all[t])} bars", flush=True)

    rows = []
    for f in flags.itertuples():
        bars = bars_of[f.ticker]
        if bars is None:
            continue
        def hourly(fl):
            intra = intraday_for(f.ticker, fl, intra_all)
            if intra.empty:
                return {"ticker": fl.ticker, "flag_no": fl.flag_no, "setup_type": fl.setup_type,
                        "status": "NO_INTRADAY"}
            return hb.simulate(fl, bars, intra)

        for mode, sim in (("hourly", hourly),
                          ("daily", lambda fl: qb.simulate(fl, bars, "mid"))):
            r = sim(f)
            rows.append({**r, "mode": mode, "leg": 0})
            ex = exit_info(r, bars)
            if ex is None:
                continue
            re = sim(reentry_flag(f, bars, ex[0]))
            re.update(mode=mode, leg=1, prior_R=r["realized_R"])
            if re.get("status") in ("OK", "STILL_OPEN"):
                re["days_after_stop"] = int(bars.index[bars["d"] == re["entry_date"]][0]) - ex[0]
            rows.append(re)

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    rs = np.random.default_rng(42)
    for mode in ("hourly", "daily"):
        d = df[df["mode"] == mode]
        first = d[(d["leg"] == 0) & (d["status"] == "OK")]
        stopped = first[first["exit_reason"].isin(STOP_EXITS)]
        re = d[d["leg"] == 1]
        trig = re[re["status"].isin(["OK", "STILL_OPEN"])]
        re_ok = re[re["status"] == "OK"]
        print(f"\n=== {mode.upper()} entry ===")
        qb.summarize(first, "first entry")
        print(f"  stopped out {len(stopped)}; re-entry triggered {len(trig)} "
              f"({len(trig)/max(len(stopped),1)*100:.0f}%), median {trig['days_after_stop'].median():.0f} sessions after stop")
        qb.summarize(re_ok, "re-entry")
        if len(re_ok) > 1:
            x = re_ok["realized_R"].to_numpy()
            bs = np.array([rs.choice(x, len(x)).mean() for _ in range(20000)])
            print(f"  re-entry EV 95% CI [{np.percentile(bs,2.5):+.2f}, {np.percentile(bs,97.5):+.2f}]")
        tot = first["realized_R"].sum() + re_ok["realized_R"].sum()
        print(f"  system: {first['realized_R'].sum():+.1f}R -> {tot:+.1f}R with re-entries "
              f"({tot/max(len(first),1):+.3f}R per original flag)")
    h = df[(df["mode"] == "hourly") & (df["leg"] == 1)]
    print(f"\nhourly re-entry status: {h['status'].value_counts().to_dict()}")
    print(f"trade log: {OUT}")


if __name__ == "__main__":
    main()
