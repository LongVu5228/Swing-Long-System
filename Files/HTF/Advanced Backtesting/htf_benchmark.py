"""
Does hand-picking HTF flags beat the unfiltered scanner -- and does either beat noise?

Three arms on the SAME tickers (every ticker you've annotated), the SAME TradingView export
bars, and the SAME chosen-one exits and daily entry treatment (quick_backtest_chosen_one.py,
--entry-day mid). Only the selection of (level, live date) differs:

  hand-picked : your R1 and setup_confirmed.
  scanner     : every flagpole the pivot algorithm produced on those tickers (1M/3M/6M review
                files, deduped by hh_date). Level = that day's high from the export bars, so
                both arms read prices from one source. Live from hh_confirmed_date (pivot
                confirmation, 2 sessions after the high -- no lookahead).
  noise       : random dates on the same tickers (EP noise_benchmark.py rules: 5 draws per
                real trade, none within 15 sessions of a hand-picked flag, 30-session
                warmup, seed 42). Level = the random day's high. Measures what being long
                these names at an arbitrary time earns -- Aronson's position-bias check.

Every arm runs a fixed 8-session window (EP's D0..D+7; your own windows median 6), so the
window you chose can't confound the comparison. Hand-picked is also reported with its own
windows (through final_flag_end) for reference.

    python htf_benchmark.py
"""
import os
import random
from collections import namedtuple

import numpy as np
import pandas as pd

import quick_backtest_chosen_one as qb

HERE = os.path.dirname(os.path.abspath(__file__))
HTF = os.path.join(HERE, "..")
REVIEWS = ["htf_1m_flag_review_v2_flagpole_bucketed.csv",
           "htf_3m_flag_review_v2_flagpole_bucketed.csv",
           "htf_6m_flag_review_v2_flagpole_bucketed.csv"]
OUT = os.path.join(HERE, "htf_benchmark_trades.csv")

WINDOW = 8
NOISE_PER_TRADE, EXCLUSION_BUFFER, WARMUP_MIN, SEED = 5, 15, 30, 42
MODE = "mid"

Flag = namedtuple("Flag", "ticker flag_no setup_type setup_confirmed final_flag_end r1_price")


def window_end(bars, i_live_after: int) -> int:
    """Date WINDOW sessions after the live-after bar (or the last bar)."""
    j = min(i_live_after + WINDOW, len(bars) - 1)
    return int(bars.at[j, "d"])


def run(arm: str, flags: list, bars_of: dict) -> pd.DataFrame:
    rows = []
    for f in flags:
        r = qb.simulate(f, bars_of[f.ticker], MODE)
        r["arm"] = arm
        rows.append(r)
    return pd.DataFrame(rows)


def main():
    m = qb.read_master()
    picks = m[(m["flag_no"] > 0) & (~m["ticker"].isin(qb.EXCLUDE)) & m["r1_price"].notna()]
    tickers = sorted(picks["ticker"].unique())
    bars_of = {t: qb.load_bars(t) for t in tickers}
    bars_of = {t: b for t, b in bars_of.items() if b is not None}
    picks = picks[picks["ticker"].isin(bars_of)]
    print(f"{len(bars_of)} tickers, {len(picks)} hand-picked flags")

    # --- hand-picked, own windows and fixed window
    own = [Flag(r.ticker, r.flag_no, r.setup_type, r.setup_confirmed, r.final_flag_end, r.r1_price)
           for r in picks.itertuples()]
    fixed = []
    for r in picks.itertuples():
        b = bars_of[r.ticker]
        idx = b.index[b["d"] <= r.setup_confirmed]
        if len(idx):
            fixed.append(Flag(r.ticker, r.flag_no, r.setup_type, r.setup_confirmed,
                              window_end(b, int(idx[-1])), r.r1_price))

    # --- scanner flagpoles on the same tickers
    seen, scan = set(), []
    for name in REVIEWS:
        rv = pd.read_csv(os.path.join(HTF, name))
        rv = rv[(rv["status"] == "OK") & (rv["revised_ticker"].isin(bars_of))]
        for r in rv.itertuples():
            hh = str(r.hh_dates).split("; ")
            hc = str(r.hh_confirmed_dates).split("; ")
            for a, c in zip(hh, hc):
                key = (r.revised_ticker, a)
                if key in seen or a == "nan":
                    continue
                seen.add(key)
                b = bars_of[r.revised_ticker]
                ad, cd = int(a.replace("-", "")), int(c.replace("-", ""))
                hit, live = b.index[b["d"] == ad], b.index[b["d"] <= cd]
                if len(hit) == 0 or len(live) == 0:
                    continue
                scan.append(Flag(r.revised_ticker, len(scan), "SCANNER", cd,
                                 window_end(b, int(live[-1])), float(b.at[int(hit[0]), "high"])))

    # --- noise: random dates, EP rules
    rng = random.Random(SEED)
    noise = []
    for t, grp in picks.groupby("ticker"):
        b = bars_of[t]
        real = [int(b.index[b["d"] <= c][-1]) for c in grp["setup_confirmed"] if (b["d"] <= c).any()]
        pool = [i for i in range(WARMUP_MIN, len(b) - WINDOW - 2)
                if all(abs(i - x) > EXCLUSION_BUFFER for x in real)]
        for _ in range(NOISE_PER_TRADE * len(grp)):
            if not pool:
                break
            i = rng.choice(pool)
            noise.append(Flag(t, len(noise), "NOISE", int(b.at[i, "d"]), window_end(b, i),
                              float(b.at[i, "high"])))

    arms = {"hand-picked (own window)": own, "hand-picked (8-session)": fixed,
            "scanner (8-session)": scan, "noise (8-session)": noise}
    results = {name: run(name, fl, bars_of) for name, fl in arms.items()}
    pd.concat(results.values(), ignore_index=True).to_csv(OUT, index=False)

    rs = np.random.default_rng(SEED)
    def boot(x, n=20000):
        return np.array([rs.choice(x, len(x)).mean() for _ in range(n)])

    print(f"\n{'arm':26s} {'flags':>6s} {'trades':>6s} {'win':>6s} {'PF':>5s} {'EV':>8s}  95% CI")
    evs = {}
    for name, df in results.items():
        ok = df[df["status"] == "OK"]["realized_R"].to_numpy()
        w, lo = ok[ok > 0], ok[ok <= 0]
        pf = w.sum() / abs(lo.sum()) if lo.sum() else float("inf")
        bs = boot(ok)
        evs[name] = (ok, bs)
        print(f"{name:26s} {len(df):6d} {len(ok):6d} {len(w)/len(ok)*100:5.1f}% {pf:5.2f} "
              f"{ok.mean():+7.3f}R  [{np.percentile(bs,2.5):+.2f}, {np.percentile(bs,97.5):+.2f}]")

    print("\nhead-to-head (bootstrap difference in EV):")
    for a, b in [("hand-picked (8-session)", "scanner (8-session)"),
                 ("hand-picked (8-session)", "noise (8-session)"),
                 ("scanner (8-session)", "noise (8-session)")]:
        diff = evs[a][1] - evs[b][1]
        print(f"  {a:24s} - {b:20s}: {diff.mean():+.3f}R  "
              f"95% CI [{np.percentile(diff,2.5):+.2f}, {np.percentile(diff,97.5):+.2f}]  "
              f"P(<=0) {(diff <= 0).mean():.3f}")
    print(f"\ntrade log: {OUT}")


if __name__ == "__main__":
    main()
