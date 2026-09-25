"""
Batch-ingests TradingView chart exports carrying HTF Manual Flag Recorder annotations.

Run it after annotating a batch of tickers. It scans Downloads for chart exports, keeps only
the NEWEST export per ticker (so re-exporting supersedes earlier attempts -- that's what makes
the "BATS_AA, 1D (1).csv / (2).csv" pileup harmless), files the raw CSV under chart_exports/,
parses the annotation record, and rewrites the master table.

Re-exporting a ticker REPLACES its annotations rather than adding to them: the newest export
is the truth, otherwise a redone chart leaves both the old and new reading in the table.

Resistance levels are resolved here, not in Pine: the export stores the source bar's DATE, and
the level is that bar's high, read from the same CSV's OHLC columns. Schema 1 exports stored a
price directly; both are handled.

    python ingest_exports.py                 # ingest, move raw files out of Downloads
    python ingest_exports.py --dry-run       # show what would happen, touch nothing
    python ingest_exports.py --keep          # parse but leave the CSVs in Downloads
"""
import argparse
import os
import re
import shutil
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
RAW_DIR = os.path.join(HERE, "chart_exports")
MASTER = os.path.join(HERE, "htf_annotations_master.csv")

# TradingView names exports "<EXCHANGE>_<TICKER>, <TIMEFRAME>.csv", with " (n)" on repeats.
EXPORT_RE = re.compile(r"^(?P<exch>[A-Z]+)_(?P<ticker>[A-Z0-9.\-]+), (?P<tf>\w+)(?: \((?P<dup>\d+)\))?\.csv$")

TYPE = {1: "HL_FLAG", 2: "LL_NO_RECLAIM", 3: "LL_RECLAIM"}
REVIEW = {0: "NOT_REVIEWED", 1: "REVIEWED_FLAGS_FOUND", 2: "REVIEWED_NO_FLAG"}


def find_exports(src: str) -> dict:
    """Newest export per ticker."""
    best = {}
    for name in os.listdir(src):
        m = EXPORT_RE.match(name)
        if not m:
            continue
        path = os.path.join(src, name)
        mtime = os.path.getmtime(path)
        t = m.group("ticker")
        if t not in best or mtime > best[t][1]:
            best[t] = (path, mtime, m.group("tf"))
    return best


def parse_export(path: str, ticker: str, timeframe: str) -> tuple:
    df = pd.read_csv(path)
    if "ANNO_KEY" not in df.columns:
        return None, "no ANNO_KEY column -- was the recorder on the chart when you exported?"

    anno = df[df["ANNO_KEY"].notna()]
    if anno.empty:
        return None, "ANNO_KEY column present but empty"

    rec = dict(zip(anno["ANNO_KEY"].astype(int), anno["ANNO_VAL"]))
    df["d"] = pd.to_datetime(df["time"], unit="s").dt.strftime("%Y%m%d").astype(int)
    highs = dict(zip(df["d"], df["high"]))

    schema = int(rec.get(1, 1))
    review = REVIEW.get(int(rec.get(2, 0)), "NOT_REVIEWED")

    def g(k):
        v = rec.get(k)
        return None if pd.isna(v) else int(v)

    def level(bar_or_price_key):
        """Schema 2 stores the source bar's date; schema 1 stored the price outright."""
        v = rec.get(bar_or_price_key)
        if pd.isna(v):
            return None, None
        if schema >= 2:
            bar = int(v)
            return bar, highs.get(bar)
        return None, float(v)

    rows, warns = [], []
    for slot in range(1, 21):
        b = slot * 100
        if not rec.get(b + 1):
            continue
        start, conf, end = g(b + 3), g(b + 4), g(b + 5)
        r1_eff, (r1_bar, r1_px) = g(b + 6), level(b + 7)
        r2_eff, (r2_bar, r2_px) = g(b + 8), level(b + 9)

        if r1_bar is not None and r1_px is None:
            warns.append(f"slot {slot}: R1 source bar {r1_bar} not found in this CSV's bars")

        # A level with no gap before it breaks has no watch window to test an entry against.
        cross = None
        if r1_px is not None and r1_eff is not None:
            fwd = df[(df["d"] >= r1_eff) & (df["high"] >= r1_px)]
            cross = int(fwd.iloc[0]["d"]) if len(fwd) else None
            if cross == r1_eff:
                warns.append(f"slot {slot}: R1 breaks the same day it goes live -- no watch window")

        rows.append({
            "ticker": ticker,
            "timeframe": timeframe,
            "flag_no": slot,
            "setup_type": TYPE.get(g(b + 2)),
            "flag_start": start,
            "setup_confirmed": conf,
            "final_flag_end": end,
            "r1_effective": r1_eff,
            "r1_source_bar": r1_bar,
            "r1_price": round(r1_px, 4) if r1_px is not None else None,
            "r1_first_cross": cross,
            "r2_effective": r2_eff,
            "r2_source_bar": r2_bar,
            "r2_price": round(r2_px, 4) if r2_px is not None else None,
            "review_status": review,
            "schema": schema,
            "source_file": os.path.basename(path),
        })

    if not rows and review == "REVIEWED_NO_FLAG":
        rows.append({
            "ticker": ticker, "timeframe": timeframe, "flag_no": 0, "setup_type": None,
            "review_status": review, "schema": schema, "source_file": os.path.basename(path),
        })
    return (rows, warns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=DOWNLOADS)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--keep", action="store_true", help="leave CSVs in Downloads")
    args = ap.parse_args()

    found = find_exports(args.src)
    if not found:
        print(f"No TradingView chart exports found in {args.src}")
        return

    os.makedirs(RAW_DIR, exist_ok=True)
    all_rows, all_warns, moved = [], [], 0

    for ticker in sorted(found):
        path, mtime, tf = found[ticker]
        stamp = pd.Timestamp(mtime, unit="s").strftime("%Y%m%d")
        result = parse_export(path, ticker, tf)
        if result[0] is None:
            print(f"  {ticker:8s} SKIPPED -- {result[1]}")
            continue
        rows, warns = result
        flags = len([r for r in rows if r.get("flag_no")])
        note = f"{flags} flag(s), {rows[0]['review_status']}"
        print(f"  {ticker:8s} {note}")
        for w in warns:
            print(f"           ! {w}")
        all_rows += rows
        all_warns += warns

        if not args.dry_run and not args.keep:
            dest = os.path.join(RAW_DIR, f"{ticker}_{stamp}.csv")
            shutil.move(path, dest)
            moved += 1
            # Drop superseded duplicates of the same ticker
            for name in os.listdir(args.src):
                m = EXPORT_RE.match(name)
                if m and m.group("ticker") == ticker:
                    os.remove(os.path.join(args.src, name))

    if not all_rows:
        print("\nNothing parsed.")
        return

    new = pd.DataFrame(all_rows)
    if os.path.exists(MASTER) and not args.dry_run:
        old = pd.read_csv(MASTER)
        # Newest export wins: drop every prior row for the tickers in this batch.
        old = old[~old["ticker"].isin(new["ticker"])]
        out = pd.concat([old, new], ignore_index=True)
    else:
        out = new
    out = out.sort_values(["ticker", "flag_no"]).reset_index(drop=True)

    print(f"\n{len(found)} ticker(s), {len(new)} annotation row(s)"
          + (f", {moved} file(s) filed to chart_exports/" if moved else ""))
    if all_warns:
        print(f"{len(all_warns)} warning(s) above")
    if args.dry_run:
        print("DRY RUN -- nothing written or moved")
        return
    out.to_csv(MASTER, index=False)
    print(f"master table: {MASTER} ({len(out)} rows, {out['ticker'].nunique()} tickers)")


if __name__ == "__main__":
    sys.exit(main())
