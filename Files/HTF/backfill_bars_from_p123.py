"""
Backfills daily bars from P123 for the periods Polygon has no data for at all.

After repair_truncated_bars.py resolved every symbol rename it could, ~795 tickers still had
streaks with no price history -- not a naming problem, a coverage one. Polygon simply doesn't
carry pre-2022 OTC names (ABAT's January 2021 run is absent under ABAT, ABML and ORRP alike)
or many 2005-2009 delistings. P123's universe is point-in-time and does carry them.

PRICE BASIS WARNING. P123 returns the price AS TRADED on that date; Polygon back-adjusts for
later splits. ABAT closed at $1.02 on 2022-01-03 per P123 and $15.30 per Polygon -- a 1-for-15
reverse split at its Nasdaq uplisting. Splicing raw would put a 15x cliff mid-series and
manufacture a flagpole at the seam. Polygon's /v3/reference/splits doesn't list that split, so
the factor is derived empirically instead: pull OVERLAP_DAYS past the seam, take the median
Polygon/P123 ratio across days both cover, and scale the P123 segment by it.

That corrects the cumulative factor AT the seam. A split INSIDE the backfilled window is not
corrected and cannot be auto-detected here -- this dataset is full of genuine 100%+ daily
moves that look exactly like one. Such tickers are flagged in the report with their largest
day-over-day move so they can be eyeballed; the backfilled bars are also marked in a sidecar
file so the resistance prices they produce aren't mistaken for adjusted ones.

The goal is DISCOVERY: making the streak appear in the review file at the right dates. The
charting happens on TradingView, which has this history already.

Run from anywhere:
    python Files/HTF/backfill_bars_from_p123.py --dry-run     # plan + cost estimate only
    python Files/HTF/backfill_bars_from_p123.py --years 2005-2009
    python Files/HTF/backfill_bars_from_p123.py               # all years that need it
"""
import argparse
import os
import sys
from collections import defaultdict

import pandas as pd
import pandas_market_calendars as mcal

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..")
CACHE = os.path.join(HERE, "data_cache", "daily_bars_v2")
REPORT = os.path.join(HERE, "_p123_backfill_report.csv")
SIDECAR = os.path.join(HERE, "_p123_backfilled_ranges.csv")

sys.path.insert(0, os.path.join(REPO, "Files", "Buyable Gap Up"))
from p123_client import P123Client  # noqa: E402

REVIEWS = [
    "htf_1m_flag_review_v2_flagpole_bucketed.csv",
    "htf_3m_flag_review_v2_flagpole_bucketed.csv",
    "htf_6m_flag_review_v2_flagpole_bucketed.csv",
]

FORMULAS = ["Open(0)", "Hi(0)", "Low(0)", "Close(0)", "AvgDailyTot(1)"]
COLS = ["open", "high", "low", "close", "dollar_vol"]
OVERLAP_DAYS = 30          # trading days past the seam, for deriving the split factor
QUOTA_FLOOR = 60           # stop before the account runs dry
BATCH_DAYS = 60            # dates per API call


def clean(t: str) -> str:
    return t.split("^")[0].split(".")[0].strip().upper()


LEAD_IN_DAYS = 150    # context before a streak so the pivot detector can form a flagpole
TAIL_DAYS = 45        # after, so the pullback that confirms it is present


def missing_streaks() -> pd.DataFrame:
    """Individual streaks with no price data, not whole gaps.

    Pulling every day between need_from and have_from spans ~5,500 trading days -- as costly
    as a full re-pull. The detector only needs bars AROUND each streak, so this pulls
    LEAD_IN_DAYS before and TAIL_DAYS after instead, which is a fraction of the days.
    """
    first = {}
    for f in os.listdir(CACHE):
        if not f.endswith(".csv"):
            continue
        try:
            d = pd.read_csv(os.path.join(CACHE, f), usecols=["date"], nrows=1)
            first[f[:-4]] = str(d["date"].iloc[0])[:10]
        except Exception:
            pass
    frames = []
    for name in REVIEWS:
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            frames.append(pd.read_csv(p)[["ticker", "first_qualifying_date", "last_qualifying_date"]])
    r = pd.concat(frames, ignore_index=True).dropna()
    r["first_bar"] = r["ticker"].map(first)
    r = r.dropna(subset=["first_bar"])
    return r[r["first_qualifying_date"] < r["first_bar"]].copy()


def needs() -> pd.DataFrame:
    """Tickers whose cached bars start after the scanner first flagged them."""
    first = {}
    for f in os.listdir(CACHE):
        if not f.endswith(".csv"):
            continue
        try:
            d = pd.read_csv(os.path.join(CACHE, f), usecols=["date"], nrows=1)
            first[f[:-4]] = str(d["date"].iloc[0])[:10]
        except Exception:
            pass

    frames = []
    for name in REVIEWS:
        p = os.path.join(HERE, name)
        if os.path.exists(p):
            frames.append(pd.read_csv(p)[["ticker", "first_qualifying_date"]])
    r = pd.concat(frames, ignore_index=True)
    r["first_bar"] = r["ticker"].map(first)
    r = r.dropna(subset=["first_bar"])
    tr = r[r["first_qualifying_date"] < r["first_bar"]]
    return (tr.groupby("ticker")
              .agg(need_from=("first_qualifying_date", "min"),
                   have_from=("first_bar", "first"),
                   streaks=("ticker", "size"))
              .reset_index())


_CAL = None


def all_trading_days() -> list:
    """Built once -- rebuilding the NYSE calendar per ticker takes minutes."""
    global _CAL
    if _CAL is None:
        sched = mcal.get_calendar("NYSE").schedule(start_date="2004-01-01", end_date="2026-12-31")
        _CAL = [ts.date().isoformat() for ts in sched.index]
    return _CAL


def trading_days(start: str, end: str) -> list:
    import bisect
    days = all_trading_days()
    lo = bisect.bisect_left(days, start)
    hi = bisect.bisect_right(days, end)
    return days[lo:hi]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--years", default=None,
                    help="range '2005-2009' or list '2005,2006,2021'; default = all needed. "
                         "Cost is flat per year (~132) but value is not -- 2006 alone returns "
                         "719 streaks, 2026 returns 4. Pull by value, not chronology.")
    args = ap.parse_args()

    g = needs()
    if g.empty:
        print("Nothing to backfill.")
        return

    # P123 charges per DATE, not per ticker, so one call covers every ticker needing that day.
    # Collect the union of days any ticker is missing, plus overlap for the split factor.
    want = defaultdict(set)
    ms = missing_streaks()
    for r in ms.itertuples():
        lo = (pd.Timestamp(r.first_qualifying_date) - pd.Timedelta(days=LEAD_IN_DAYS)).date().isoformat()
        hi = min((pd.Timestamp(r.last_qualifying_date) + pd.Timedelta(days=TAIL_DAYS)).date().isoformat(),
                 r.first_bar)
        for d in trading_days(lo, hi):
            want[d].add(r.ticker)
    # Overlap past each ticker's seam, for deriving the split factor.
    for r in g.itertuples():
        seam_end = (pd.Timestamp(r.have_from) + pd.Timedelta(days=OVERLAP_DAYS * 2)).date().isoformat()
        for d in trading_days(r.have_from, seam_end)[:OVERLAP_DAYS]:
            want[d].add(r.ticker)

    all_days = sorted(want)
    if args.years:
        if "-" in args.years:
            lo, hi = args.years.split("-")
            all_days = [d for d in all_days if lo <= d[:4] <= hi]
        else:
            yrs = {y.strip() for y in args.years.split(",")}
            all_days = [d for d in all_days if d[:4] in yrs]

    tickers = sorted({t for d in all_days for t in want[d]})
    est = max(1, round(len(all_days) / 21 * 11))   # smoke test: ~11 quota per month of dates
    print(f"{len(g):,} tickers need backfill, {int(g['streaks'].sum()):,} streaks")
    print(f"covering {len(all_days):,} trading days "
          f"({all_days[0]} -> {all_days[-1]}), {len(tickers):,} tickers in scope")
    print(f"estimated cost ~{est:,} quota units\n")
    if args.dry_run:
        print("DRY RUN -- nothing pulled")
        return

    client = P123Client()
    keep = {clean(t): t for t in tickers}        # P123 reports the clean symbol
    got = defaultdict(list)
    spent = 0

    for i in range(0, len(all_days), BATCH_DAYS):
        batch = all_days[i:i + BATCH_DAYS]
        res = client.post("/data/universe", {
            "type": "Stock", "universe": "ApiUniverse",
            "formulas": FORMULAS, "asOfDts": batch,
        })
        spent += res.get("cost") or 0
        quota = res.get("quotaRemaining")
        for e in res.get("dates", []):
            tk, data = e["tickers"], e["data"]
            for idx, sym in enumerate(tk):
                raw = keep.get(sym)
                if not raw:
                    continue
                row = {"date": e["dt"]}
                for name, col in zip(COLS, data):
                    row[name] = col[idx]
                got[raw].append(row)
        print(f"  {batch[0]}..{batch[-1]}  cost={res.get('cost')} quota={quota}")
        if quota is not None and quota < QUOTA_FLOOR:
            print(f"\nstopping: quota {quota} below floor {QUOTA_FLOOR}. Re-run to resume.")
            break

    rows, sidecar = [], []
    for raw, recs in got.items():
        p = pd.DataFrame(recs).dropna(subset=["close"])
        if len(p) < 20:
            continue
        p["date"] = pd.to_datetime(p["date"]).dt.date
        p = p.sort_values("date").drop_duplicates("date")

        path = os.path.join(CACHE, f"{raw}.csv")
        old = pd.read_csv(path, parse_dates=["date"])
        old["date"] = old["date"].dt.date

        # Derive the split factor from days both sources cover.
        both = p.merge(old[["date", "close"]], on="date", suffixes=("_p", "_o"))
        both = both[(both["close_p"] > 0) & (both["close_o"] > 0)]
        factor = float((both["close_o"] / both["close_p"]).median()) if len(both) >= 5 else 1.0
        note = "" if 0.98 <= factor <= 1.02 else f"scaled x{factor:.3f}"

        new = p[p["date"] < old["date"].min()].copy()
        if new.empty:
            continue
        for c in ("open", "high", "low", "close"):
            new[c] = new[c] * factor
        new["volume"] = (new["dollar_vol"] / new["close"].replace(0, pd.NA)).fillna(0)

        # A split inside the backfilled window isn't corrected by the seam factor.
        cl = new["close"].tolist()
        jump = max((max(a, b) / min(a, b) for a, b in zip(cl, cl[1:]) if a > 0 and b > 0),
                   default=1.0)
        if jump > 1.6:
            note = (note + " | " if note else "") + f"max 1d move {jump:.1f}x -- possible split inside window"

        merged = (pd.concat([new[["date"] + ["open", "high", "low", "close", "volume"]], old],
                            ignore_index=True)
                    .drop_duplicates(subset=["date"], keep="last")
                    .sort_values("date").reset_index(drop=True))
        merged.to_csv(path, index=False)

        rows.append({"ticker": raw, "bars_added": len(new),
                     "new_first_bar": new["date"].min().isoformat(),
                     "overlap_days": len(both), "split_factor": round(factor, 4),
                     "max_1d_move": round(jump, 2), "note": note})
        sidecar.append({"ticker": raw, "from": new["date"].min().isoformat(),
                        "to": new["date"].max().isoformat(), "source": "P123",
                        "price_basis": "as-traded, scaled to Polygon at seam"})

    rep = pd.DataFrame(rows)
    rep.to_csv(REPORT, index=False)
    pd.DataFrame(sidecar).to_csv(SIDECAR, index=False)
    print(f"\nquota spent: {spent:,}")
    print(f"backfilled {len(rep):,} tickers, {int(rep['bars_added'].sum()):,} bars" if len(rep) else "\nno tickers backfilled")
    if len(rep):
        scaled = rep[rep["split_factor"].round(2) != 1.00]
        flagged = rep[rep["note"].str.contains("possible split", na=False)]
        print(f"  {len(scaled):,} needed split-factor scaling")
        print(f"  {len(flagged):,} flagged for a possible split inside the window -- see report")
    print(f"report:  {REPORT}")
    print(f"sidecar: {SIDECAR}  (which ranges came from P123)")
    print("\nNext: rebuild the review files --")
    print("  for w in 1m 3m 6m; do python build_1m_flag_review_v2_flagpole_bucketed.py --window $w; done")


if __name__ == "__main__":
    main()
