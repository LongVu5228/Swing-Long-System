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
from types import SimpleNamespace

import pandas as pd

import htf_pattern_labeler as hpl

HERE = os.path.dirname(os.path.abspath(__file__))
DOWNLOADS = os.path.join(os.path.expanduser("~"), "Downloads")
RAW_DIR = os.path.join(HERE, "chart_exports")
MASTER = os.path.join(HERE, "htf_annotations_master.csv")

# TradingView names exports "<EXCHANGE>_<TICKER>, <TIMEFRAME>.csv", with " (n)" on repeats.
# The exchange prefix can itself contain underscores (OTC_DLY_ABBNY, EURONEXT_DLY_AGN), so it's
# matched lazily and the ticker is whatever follows the LAST underscore.
EXPORT_RE = re.compile(r"^(?P<exch>[A-Z_]+?)_(?P<ticker>[A-Z0-9.\-^]+), (?P<tf>\w+)(?: \((?P<dup>\d+)\))?\.csv$")

TYPE = {1: "HL_FLAG", 2: "LL_NO_RECLAIM", 3: "LL_RECLAIM"}
# Schema 4: field 10 = pattern picked in the recorder (same names as the labeler uses).
PATTERN = {1: "Green HTF", 2: "Red HTF", 3: "Perfect HTF",
           4: "Big Green Flag", 5: "Big Red Flag", 6: "Big Perfect Flag"}
# Schema 5: field 10 = na and field 2 = 0 means the slot was left on "Auto". The recorder's Pine
# port of the labeler showed you its pick; the same classifier runs here on the exported bars,
# so a flag you left on Auto is recorded with the pattern you saw (pattern_source = auto).
RED = {"Red HTF", "Big Red Flag"}


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

    # Two recorders on one chart (e.g. a 7-slot added after a 20-slot ran out) export as
    # ANNO_KEY/ANNO_VAL, ANNO_KEY.1/ANNO_VAL.1, ... Each is its own record, numbered from
    # slot 1, so parse them separately and number the later ones after the earlier ones.
    # Inputs survive a symbol change, so a recorder left on the chart can still hold the
    # PREVIOUS ticker's flags: extra recorders are tagged so main() can reject those.
    key_cols = [c for c in df.columns if c.split(".")[0] == "ANNO_KEY"]
    val_cols = [c for c in df.columns if c.split(".")[0] == "ANNO_VAL"]
    df["d"] = pd.to_datetime(df["time"], unit="s").dt.strftime("%Y%m%d").astype(int)
    highs = dict(zip(df["d"], df["high"]))
    first_bar = int(df["d"].min())

    rows, warns, seen = [], [], set()
    for n, (kc, vc) in enumerate(zip(key_cols, val_cols), start=1):
        anno = df[df[kc].notna()]
        if anno.empty:
            continue
        rec = dict(zip(anno[kc].astype(int), anno[vc]))
        label = "" if n == 1 else f"recorder {n} "
        r, w = parse_record(rec, df, highs, ticker, timeframe, path, label)
        # The same recorder added twice exports the same flags twice -- keep one copy.
        r = [x for x in r if (x["flag_start"], x["setup_confirmed"], x["final_flag_end"]) not in seen]
        if n > 1:
            stale = [x for x in r if x["flag_start"] < first_bar]
            if stale:
                warns.append(f"recorder {n}: dropped {len(stale)} flag(s) dated before this chart's "
                             f"first bar -- leftovers from another ticker")
            r = [x for x in r if x["flag_start"] >= first_bar]
            for x in r:
                x["_extra_recorder"] = n
        seen |= {(x["flag_start"], x["setup_confirmed"], x["final_flag_end"]) for x in r}
        for i, x in enumerate(r, start=len(rows) + 1):
            x["flag_no"] = i
        rows += r
        warns += w
    if not rows and not warns:
        return None, "ANNO_KEY column present but empty"
    return (rows, warns)


def parse_record(rec: dict, df, highs: dict, ticker: str, timeframe: str, path: str, label: str) -> tuple:

    # Schema 3 dropped key 2 (review status): an export existing at all means flags were
    # found, and a ticker never exported means none were. Schema 2 files still carry key 2;
    # it is simply ignored, so old and new exports parse the same way.
    schema = int(rec.get(1, 1))

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
    # Slot count varies by recorder (7/20/40), so read every slot the record carries.
    n_slots = max(k // 100 for k in rec if k % 100)
    bars = df[["d", "open", "high", "low", "close"]].dropna().sort_values("d").reset_index(drop=True)
    for slot in range(1, n_slots + 1):
        b = slot * 100
        if not rec.get(b + 1):
            continue
        start, conf, end = g(b + 3), g(b + 4), g(b + 5)
        r1_eff, (r1_bar, r1_px) = g(b + 6), level(b + 7)
        r2_eff, (r2_bar, r2_px) = g(b + 8), level(b + 9)

        slot_label = f"{label}slot {slot}"
        if r1_bar is not None and r1_px is None:
            warns.append(f"{slot_label}: R1 source bar {r1_bar} not found in this CSV's bars")

        # A level with no gap before it breaks has no watch window to test an entry against.
        cross = None
        if r1_px is not None and r1_eff is not None:
            fwd = df[(df["d"] >= r1_eff) & (df["high"] >= r1_px)]
            cross = int(fwd.iloc[0]["d"]) if len(fwd) else None
            if cross == r1_eff:
                warns.append(f"{slot_label}: R1 breaks the same day it goes live -- no watch window")

        pattern, source, setup = PATTERN.get(g(b + 10)), None, TYPE.get(g(b + 2))
        if pattern:
            source = "manual"
        elif schema >= 5 and g(b + 2) == 0:
            # End on the confirmed bar = a failed lower-low; classified without the R1 break,
            # exactly as the recorder does (dNoRecl).
            no_reclaim = end == conf
            f = SimpleNamespace(flag_start=start, setup_confirmed=conf, final_flag_end=end,
                                r1_first_cross=None if no_reclaim else cross)
            auto = hpl.label_flag(bars, f)["pattern"]
            if auto in PATTERN.values():
                pattern, source = auto, "auto"
                setup = ("LL_NO_RECLAIM" if no_reclaim else "LL_RECLAIM") if auto in RED else "HL_FLAG"
                if setup == "LL_NO_RECLAIM":   # no reclaim = no level to trade, as in manual slots
                    r1_eff = r1_bar = r1_px = cross = r2_eff = r2_bar = r2_px = None
            else:
                warns.append(f"{slot_label}: Auto found no pattern ({auto}) -- pick one in the recorder and re-export")
        rows.append({
            "ticker": ticker,
            "timeframe": timeframe,
            "flag_no": slot,
            "setup_type": setup,
            "pattern_recorded": pattern,
            "pattern_source": source,
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
            "schema": schema,
            "source_file": os.path.basename(path),
        })

    return (rows, warns)


def screen_extra_recorders(rows: list, ticker: str, old: pd.DataFrame) -> tuple:
    """Drop a second recorder whose flags mostly duplicate another ticker's saved flags (a
    recorder left on the chart across a symbol change), renumber, and flag what remains.
    Judged per recorder, not per flag: two tickers can share one flag's dates by coincidence
    (CRDO and CAN both flagged Dec 2024), but a stale recorder copies nearly all of them."""
    key = ("flag_start", "setup_confirmed", "final_flag_end")
    elsewhere = set()
    if len(old):
        o = old[old["ticker"] != ticker]
        elsewhere = set(zip(*(o[k] for k in key)))
    warns, kept, extra = [], [], 0
    for n in sorted({x.get("_extra_recorder") or 1 for x in rows}):
        mine = [x for x in rows if (x.get("_extra_recorder") or 1) == n]
        if n > 1:
            copied = sum(tuple(x[k] for k in key) in elsewhere for x in mine)
            if copied * 2 >= len(mine):
                warns.append(f"recorder {n}: dropped {len(mine)} flag(s), {copied} copied from another ticker")
                continue
            extra += len(mine)
        kept += mine
    for x in kept:
        x.pop("_extra_recorder", None)
    if extra:
        warns.append(f"{extra} flag(s) came from a 2nd recorder -- check they belong to {ticker}")
    for i, x in enumerate(kept, start=1):
        x["flag_no"] = i
    return kept, warns


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
    old = pd.read_csv(MASTER) if os.path.exists(MASTER) else pd.DataFrame()

    for ticker in sorted(found):
        path, mtime, tf = found[ticker]
        stamp = pd.Timestamp(mtime, unit="s").strftime("%Y%m%d")
        result = parse_export(path, ticker, tf)
        if result[0] is None:
            print(f"  {ticker:8s} SKIPPED -- {result[1]}")
            continue
        rows, warns = result
        rows, extra_warns = screen_extra_recorders(rows, ticker, old)
        warns += extra_warns
        flags = len([r for r in rows if r.get("flag_no")])
        # An export with no flags is now a contradiction -- you only download a chart once
        # you've found something on it -- so say so rather than recording an empty row.
        note = f"{flags} flag(s)" if flags else "NO FLAGS -- nothing to record, re-check the chart"
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
    if len(old) and not args.dry_run:
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
