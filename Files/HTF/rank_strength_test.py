"""
Test 1 of the "does top-16 matter" question (2026-11-12): do the strongest stocks keep running
more than slightly-less-strong ones? Qullamaggie's claim is that the biggest moves come from
stocks already leading on 1/3/6-month performance. No hand-marked flags -- this uses the raw
P123 universe pull (raw_data_htf_v2/*.parquet, every US stock every day since 2005).

Two rankings, both point-in-time (only data known at that day's close):
  A. Scanner replica: stocks passing the scanner's gates (ADR>=5%, ADV>=$10M, mktcap>=$50M,
     SMA10 and SMA20 rising), ranked within (date, mktcap bucket) on each of ret_1m/3m/6m;
     a stock's rank = its BEST rank across the three windows, exactly how the scanner unions
     them. Groups: 1-16 (on the scanner), 17-32, 33-64, 65+.
  B. Qullamaggie's broader version: every liquid stock (ADV>=$10M, mktcap>=$50M, no ADR/SMA
     gate), percentile of ret_3m within (date, bucket): top 1%, 1-2%, 2-5%, 5-10%, 10-25%,
     25-50%, bottom 50%.

Forward outcome, measured from the NEXT day's open (buyable), via the same return columns:
  fwd_1m = ret_1m at t+22  (= close(t+22) / open(t+1) - 1), fwd_3m = ret_3m at t+64,
  fwd_6m = ret_6m at t+127; new_run = max ret_1m over t+22..t+127 (a fresh +X% month that
  starts after t+1). Missing future rows (delisted / data gap) are counted, not imputed.

Signal days are sampled every 5th trading day so one stock's long run isn't counted 5x a week.
Returns are capped at +2000% before averaging (a few raw rows are corrupt, up to +5,689,900%).

    ../../.venv/Scripts/python.exe rank_strength_test.py
"""
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw_data_htf_v2")
OUT = os.path.join(HERE, "rank_strength_results.csv")

ADR_MIN, ADV_MIN, CAP_MIN, TOP_N = 5.0, 10_000_000, 50, 16
BUCKETS = [("small", 50, 2_000), ("mid", 2_000, 10_000), ("large_plus", 10_000, np.inf)]
WINDOWS = ["ret_1m", "ret_3m", "ret_6m"]
STEP = 5
CAP = 20.0
COLS = ["date", "ticker", "adr14", "adv30", "mktcap", "sma10_rising_diff", "sma20_rising_diff"] + WINDOWS


def bucket(mc: pd.Series) -> pd.Series:
    out = pd.Series(pd.NA, index=mc.index, dtype="object")
    for name, lo, hi in BUCKETS:
        out[(mc >= lo) & (mc < hi)] = name
    return out


def forward(sig: pd.DataFrame, full: pd.DataFrame, nxt: pd.DataFrame, dates: list) -> pd.DataFrame:
    """Attach forward outcomes to every signal row, looking ahead through the FULL daily data
    of this year and next (not just the sampled signal days -- that was a bug, 2026-11-12:
    91% of fwd_1m came back missing because t+22 landed on unsampled days)."""
    cur = sig
    both = pd.concat([full[["date", "ticker"] + WINDOWS], nxt[["date", "ticker"] + WINDOWS]], ignore_index=True)
    idx = {d: i for i, d in enumerate(dates)}
    both["di"] = both.date.map(idx)
    wide = {w: both.pivot_table(index="di", columns="ticker", values=w, aggfunc="last") for w in WINDOWS}
    for w in WINDOWS:
        wide[w] = wide[w].reindex(range(len(dates))).clip(upper=CAP)
    cur = cur.copy()
    cur["di"] = cur.date.map(idx)
    t = cur.ticker.values
    i = cur.di.values

    def at(w, k):
        tab = wide[w]
        col = tab.columns.get_indexer(t)
        row = i + k
        ok = (col >= 0) & (row < len(tab))
        out = np.full(len(cur), np.nan)
        arr = tab.values
        out[ok] = arr[row[ok], col[ok]]
        return out

    cur["fwd_1m"] = at("ret_1m", 22)
    cur["fwd_3m"] = at("ret_3m", 64)
    cur["fwd_6m"] = at("ret_6m", 127)
    # best fresh 1-month run starting after t+1, within ~6 months: max of ret_1m over
    # t+22..t+127, as a reversed rolling max of the series shifted 22 days ahead
    r1 = wide["ret_1m"]
    wide["fwdmax"] = r1.shift(-22).iloc[::-1].rolling(106, min_periods=1).max().iloc[::-1]
    cur["new_run"] = at("fwdmax", 0)
    return cur


def label(df: pd.DataFrame) -> pd.DataFrame:
    liquid = (df.adv30 >= ADV_MIN) & (df.mktcap >= CAP_MIN)
    df = df[liquid].copy()
    df["bucket"] = bucket(df.mktcap)
    gated = (df.adr14 >= ADR_MIN) & (df.sma10_rising_diff > 0) & (df.sma20_rising_diff > 0)
    ranks = []
    for w in WINDOWS:
        r = df[gated].groupby(["date", "bucket"])[w].rank(method="first", ascending=False)
        ranks.append(r)
    best = pd.concat(ranks, axis=1).min(axis=1)
    df["scan_rank"] = best.reindex(df.index)
    df["scan_group"] = pd.cut(df.scan_rank, [0, 16, 32, 64, np.inf], labels=["1-16", "17-32", "33-64", "65+"])
    df["scan_group"] = df.scan_group.cat.add_categories("not gated").fillna("not gated")
    pct = df.groupby(["date", "bucket"]).ret_3m.rank(pct=True, ascending=False)
    df["pct_group"] = pd.cut(pct, [0, .01, .02, .05, .10, .25, .50, 1.0],
                             labels=["top 1%", "1-2%", "2-5%", "5-10%", "10-25%", "25-50%", "bottom 50%"])
    return df


def main():
    files = sorted(f for f in os.listdir(RAW) if f.endswith(".parquet"))
    years = [int(f[:4]) for f in files]
    load = lambda y: pd.read_parquet(os.path.join(RAW, f"{y}.parquet"), columns=COLS) if y in years else pd.DataFrame(columns=COLS)
    rows = []
    prev = None
    for y in years:
        cur = prev if prev is not None else load(y)
        nxt = load(y + 1)
        for c in WINDOWS + ["adr14", "adv30", "mktcap", "sma10_rising_diff", "sma20_rising_diff"]:
            cur[c] = pd.to_numeric(cur[c], errors="coerce")
            nxt[c] = pd.to_numeric(nxt[c], errors="coerce")
        dates = sorted(set(cur.date) | set(nxt.date))
        ydates = sorted(set(cur.date))[::STEP]
        sig = label(cur[cur.date.isin(ydates)])
        sig = sig[sig.ret_3m.notna()]
        sig = forward(sig, cur, nxt, dates)
        sig["year"] = y
        rows.append(sig[["date", "year", "ticker", "bucket", "scan_rank", "scan_group", "pct_group",
                         "ret_3m", "fwd_1m", "fwd_3m", "fwd_6m", "new_run"]])
        print(f"{y}: {len(sig):,} signal rows")
        prev = nxt
    df = pd.concat(rows, ignore_index=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
