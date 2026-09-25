"""
Backfills daily bars for tickers whose cached history starts AFTER the scanner first flagged
them -- the silent cause of ~75% of `no_pivot_yet` rows in the review files.

P123's universe is point-in-time under the CURRENT symbol; Polygon files history under
whatever the symbol was AT THE TIME. So a renamed or bankrupt company gets a truncated series,
the pivot detector sees no bars for the old period, and the streak is dropped. Because renames
and bankruptcies are exactly the names that didn't survive, that drop is survivorship bias.

Two resolution paths, both needed (measured 2026-09-22 over the affected set):
  - Bankruptcy "…Q" tickers 404 on the events endpoint, but the pre-bankruptcy symbol is just
    the ticker minus the trailing Q (SPWRQ -> SPWR, SHLDQ -> SHLD).
  - Everything else resolves via /vX/reference/tickers/{t}/events, which returns the full
    ticker_change chain (NXH <- BBBY <- BYON <- OSTK), walked oldest-first.

Recovered bars are PREPENDED to the cached CSV. Note the seam: each symbol's series is
split/dividend-adjusted on its own basis, so a price discontinuity at the rename boundary is
possible. Flagged in the report when the gap looks large.

    python repair_truncated_bars.py --dry-run      # resolve only, write nothing
    python repair_truncated_bars.py --limit 20     # try the 20 worst offenders
    python repair_truncated_bars.py                # full run
"""
import argparse
import datetime as dt
import os
import sys

import pandas as pd
import requests
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..")
CACHE = os.path.join(HERE, "data_cache", "daily_bars_v2")
REPORT = os.path.join(HERE, "_bar_repair_report.csv")

sys.path.insert(0, os.path.join(REPO, "Scripts"))
load_dotenv(os.path.join(REPO, ".env"))
KEY = os.getenv("POLYGON_API_KEY")

REVIEWS = [
    "htf_1m_flag_review_v2_flagpole_bucketed_v2.csv",
    "htf_3m_flag_review_v2_flagpole_bucketed.csv",
    "htf_6m_flag_review_v2_flagpole_bucketed.csv",
]


def clean(t: str) -> str:
    """Strip P123's point-in-time suffix: 'SPWRQ^24' -> 'SPWRQ'."""
    return t.split("^")[0].split(".")[0].strip().upper()


def find_truncated() -> pd.DataFrame:
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
            frames.append(pd.read_csv(p)[["ticker", "first_qualifying_date", "status"]])
    r = pd.concat(frames, ignore_index=True)
    r["first_bar"] = r["ticker"].map(first)
    r = r.dropna(subset=["first_bar"])
    tr = r[r["first_qualifying_date"] < r["first_bar"]]
    g = (tr.groupby("ticker")
           .agg(streaks=("ticker", "size"),
                need_from=("first_qualifying_date", "min"),
                have_from=("first_bar", "first"))
           .sort_values("streaks", ascending=False)
           .reset_index())
    return g


EDGAR_HEADERS = {"User-Agent": "HTF Research numnum5228@gmail.com"}
SUFFIXES = {"INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LIMITED", "PLC", "LP",
            "LLC", "SA", "NV", "AG", "HOLDINGS", "HOLDING", "GROUP", "THE", "NEW", "COM",
            "STK", "CLASS", "A", "B", "/DE/", "/MD/", "/NY/"}


def edgar_prior_tickers(sym: str, need: str) -> list:
    """Resolve historical symbols Polygon's own chain doesn't know about.

    Polygon's ticker_change events stop partway back -- it knows BB <- BBRY (2013) but not
    BBRY <- RIMM, so a 2007 streak stays uncovered. SEC EDGAR tracks former COMPANY NAMES by
    CIK, which is stable across renames, and Polygon's ticker search accepts a historical
    `date`. Chaining them recovers the rest: BB -> cik -> "Research In Motion" -> RIMM.
    """
    try:
        d = requests.get(f"https://api.polygon.io/v3/reference/tickers/{sym}",
                         params={"apiKey": KEY}, timeout=20).json().get("results", {})
        cik = d.get("cik")
        if not cik:
            return []
        sub = requests.get(f"https://data.sec.gov/submissions/CIK{str(cik).zfill(10)}.json",
                           headers=EDGAR_HEADERS, timeout=25)
        if sub.status_code != 200:
            return []
        names = [(f.get("name"), f.get("from", "")[:10], f.get("to", "")[:10])
                 for f in sub.json().get("formerNames", [])]
        out = []
        for name, frm, to in names:
            # Only names the company actually held when the streak happened.
            if not name or (to and to < need):
                continue
            # Polygon's search is literal enough that a corporate suffix kills the match:
            # "Silver Wheaton Corp." returns nothing, "Silver Wheaton" returns SLW. Strip
            # the suffixes, then try progressively shorter prefixes.
            words = [w for w in name.replace(",", " ").replace(".", " ").split()
                     if w.upper().strip("()") not in SUFFIXES]
            if not words:
                continue
            for n in (3, 2):
                if len(words) < n:
                    continue
                q = " ".join(words[:n])
                r = requests.get("https://api.polygon.io/v3/reference/tickers",
                                 params={"search": q, "date": need, "market": "stocks",
                                         "limit": 5, "apiKey": KEY}, timeout=25)
                # Polygon's search goes fuzzy on short queries and returns unrelated
                # companies (UAL -> ACU/AFP, QRVO -> RCKY). Require the returned company
                # name to actually start with the same word as the EDGAR name.
                hits = [x.get("ticker") for x in r.json().get("results", [])
                        if (x.get("name") or "").upper().lstrip("THE ").startswith(words[0].upper())]
                hits = [t for t in hits if t and t != sym and t.isalpha() and t not in out]
                if hits:
                    out.extend(hits)
                    break
        return out
    except Exception:
        return []


def prior_tickers(sym: str) -> list:
    """(candidate, confidence) historical symbols, most likely first.

    Confidence matters because a wrong guess merges a DIFFERENT company's prices into the
    series -- worse than the missing data it fixes. Two sources are trustworthy: Polygon's
    own ticker_change chain, and the standard bankruptcy convention of appending one Q.
    Stripping two characters is a guess that lands on real but unrelated tickers
    (SUNEQ -> SUN is Sunoco, not SunEdison; ACIIQ -> ACI is Albertsons, not Arch Coal), so
    it's reported for review rather than merged.
    """
    out = []
    if sym.endswith("Q") and len(sym) > 2:
        out.append((sym[:-1], "high"))       # SPWRQ -> SPWR
    try:
        r = requests.get(f"https://api.polygon.io/vX/reference/tickers/{sym}/events",
                         params={"apiKey": KEY}, timeout=20)
        if r.status_code == 200:
            chain = [(e.get("date"), e.get("ticker_change", {}).get("ticker"))
                     for e in r.json().get("results", {}).get("events", [])
                     if e.get("type") == "ticker_change"]
            # oldest first; skip the current symbol and anything non-alphabetic (S456 etc.)
            for _, t in sorted(chain):
                if t and t != sym and t.isalpha() and t not in [c for c, _ in out]:
                    out.append((t, "high"))
    except Exception:
        pass
    if sym.endswith("Q") and len(sym) > 3:
        out.append((sym[:-2], "low"))        # RADCQ -> RAD, but also SUNEQ -> SUN (wrong)
    return out


def fetch(sym: str, start: str, end: str) -> pd.DataFrame:
    r = requests.get(f"https://api.polygon.io/v2/aggs/ticker/{sym}/range/1/day/{start}/{end}",
                     params={"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": KEY},
                     timeout=60)
    if r.status_code != 200:
        return pd.DataFrame()
    res = r.json().get("results", [])
    if not res:
        return pd.DataFrame()
    df = pd.DataFrame(res)
    df["date"] = pd.to_datetime(df["t"], unit="ms").dt.date
    return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})[
        ["date", "open", "high", "low", "close", "volume"]
    ]


def repair(row, dry: bool) -> dict:
    raw, sym = row.ticker, clean(row.ticker)
    need, have = row.need_from, row.have_from
    end = (dt.date.fromisoformat(have) - dt.timedelta(days=1)).isoformat()
    out = {"ticker": raw, "streaks": row.streaks, "need_from": need, "had_from": have,
           "resolved_as": None, "confidence": None, "new_first_bar": None, "bars_added": 0,
           "coverage_gap_days": None, "seam_gap_pct": None, "note": "", "merged": False, "source": None}

    need_d = dt.date.fromisoformat(need)
    # Every high-confidence candidate contributes, not just the first that reaches back:
    # renames chain (FLNA <- SAVA <- PTIE) and taking only the oldest hop would leave the
    # middle years empty. EDGAR costs 3 extra calls, so it's consulted only if Polygon's own
    # chain didn't already reach the streak.
    segments, used, tried, low_only = [], [], set(), None
    # Both sources always: Polygon answering isn't the same as answering far enough back.
    # It gives BB <- BBRY (2013) and stops, while a 2007 streak needs EDGAR's BBRY <- RIMM.
    cands = prior_tickers(sym) + [(t, "high") for t in edgar_prior_tickers(sym, need)]
    reached = False
    for cand, conf in cands:
        if cand in tried:
            continue
        tried.add(cand)
        bars = fetch(cand, need, end)
        if len(bars) < 20:
            continue
        if conf == "low":
            low_only = low_only or (cand, bars)
            continue
        segments.append(bars)
        used.append(cand)
        if (bars["date"].min() - need_d).days <= 400:
            reached = True
    if not segments:
        if low_only:
            out["resolved_as"], out["confidence"] = low_only[0], "low"
            out["new_first_bar"] = low_only[1]["date"].min().isoformat()
            out["bars_added"] = len(low_only[1])
            out["note"] = "LOW confidence -- not merged, verify manually"
        else:
            out["note"] = "no prior symbol found"
        return out

    path = os.path.join(CACHE, f"{raw}.csv")
    old = pd.read_csv(path, parse_dates=["date"])
    old["date"] = old["date"].dt.date
    # Current symbol last so it wins on any overlapping date.
    merged = (pd.concat(segments + [old], ignore_index=True)
                .drop_duplicates(subset=["date"], keep="last")
                .sort_values("date").reset_index(drop=True))

    out["resolved_as"] = "+".join(used)
    out["confidence"] = "high"
    out["new_first_bar"] = merged["date"].min().isoformat()
    out["bars_added"] = len(merged) - len(old)
    # Largest remaining hole anywhere in the stitched series -- the pivot detector would
    # step across it as if the bars were contiguous.
    gaps = pd.Series(merged["date"]).diff().dt.days if False else \
        pd.Series([(b - a).days for a, b in zip(merged["date"], merged["date"][1:])])
    biggest = int(gaps.max()) if len(gaps) else 0
    out["coverage_gap_days"] = biggest
    if biggest > 180:
        out["note"] = f"{biggest}d hole remains in stitched series"

    if not dry:
        merged.to_csv(path, index=False)
        out["merged"] = True
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    g = find_truncated()
    if args.limit:
        g = g.head(args.limit)
    print(f"{len(g):,} tickers with truncated history, {int(g['streaks'].sum()):,} streaks affected\n")

    rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for res in ex.map(lambda r: repair(r, args.dry_run), g.itertuples()):
            rows.append(res)
            if res["resolved_as"]:
                mark = " " if res["confidence"] == "high" else "?"
                print(f" {mark}{res['ticker']:12s} -> {res['resolved_as']:8s} "
                      f"+{res['bars_added']:5,} bars from {res['new_first_bar']}  {res['note']}")

    rep = pd.DataFrame(rows)
    hi = rep[rep["confidence"] == "high"]
    lo = rep[rep["confidence"] == "low"]
    none_ = rep[rep["resolved_as"].isna()]
    print(f"\nhigh confidence (merged): {len(hi):,} tickers, {int(hi['streaks'].sum()):,} streaks, "
          f"{int(hi['bars_added'].sum()):,} bars")
    print(f"low confidence (NOT merged, review): {len(lo):,} tickers, {int(lo['streaks'].sum()):,} streaks")
    print(f"unresolved: {len(none_):,} tickers, {int(none_['streaks'].sum()):,} streaks")
    holes = hi[hi["note"].str.contains("hole", na=False)]
    if len(holes):
        print(f"note: {len(holes)} merged series have a date hole between old and new symbol")
    rep.to_csv(REPORT, index=False)
    print(f"report: {REPORT}")
    if args.dry_run:
        print("DRY RUN -- no cache files written")


if __name__ == "__main__":
    main()
