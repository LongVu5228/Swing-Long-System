"""
Builds one master sheet of every HTF scanner streak across all three return windows, with the
ticker's former symbols attached so a delisted or renamed chart can actually be found.

Why streaks get merged across windows: 1M/3M/6M each produce their own review file, and the
same underlying run usually appears in two or three of them with slightly different date
edges. Listing them separately would mean reviewing the same chart three times. Overlapping
ranges on a ticker are clustered into one row, with a `windows` column recording which
scanners saw it -- so a 1M-only row (short burst, often noise) is distinguishable at a glance
from a 1M+3M+6M row (every lookback agreed).

The `former_symbols` column is the point of the exercise: P123 stores history under the
CURRENT symbol, so a 2006 streak on SPWRQ^24 is only chartable under SPWR. Resolved via
Polygon's ticker_change events plus SEC EDGAR former company names, same chain as
repair_truncated_bars.py.

    python build_scanner_master.py                # full build
    python build_scanner_master.py --no-lookup    # skip the API pass, leave symbols blank
"""
import argparse
import os
import sys

import pandas as pd
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_CSV = os.path.join(HERE, "htf_scanner_master.csv")
OUT_TICKER_CSV = os.path.join(HERE, "htf_scanner_master_by_ticker.csv")
OUT_XLSX = os.path.join(HERE, "htf_scanner_master.xlsx")

sys.path.insert(0, HERE)
import importlib.util
_spec = importlib.util.spec_from_file_location("_repair", os.path.join(HERE, "repair_truncated_bars.py"))
_repair = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_repair)

WINDOWS = {
    "1M": "htf_1m_flag_review_v2_flagpole_bucketed.csv",
    "3M": "htf_3m_flag_review_v2_flagpole_bucketed.csv",
    "6M": "htf_6m_flag_review_v2_flagpole_bucketed.csv",
}


def load_all() -> pd.DataFrame:
    frames = []
    for w, name in WINDOWS.items():
        p = os.path.join(HERE, name)
        if not os.path.exists(p):
            continue
        d = pd.read_csv(p)
        d = d[d["status"] == "OK"].copy()
        d["window"] = w
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)
    for c in ("first_qualifying_date", "last_qualifying_date"):
        df[c] = pd.to_datetime(df[c])
    return df


def cluster(df: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker per overlapping date cluster, across windows."""
    rows = []
    for ticker, g in df.groupby("ticker", sort=True):
        g = g.sort_values("first_qualifying_date")
        cur = None
        for r in g.itertuples():
            if cur and r.first_qualifying_date <= cur["end"]:
                cur["end"] = max(cur["end"], r.last_qualifying_date)
                cur["rows"].append(r)
            else:
                if cur:
                    rows.append(cur)
                cur = {"ticker": ticker, "start": r.first_qualifying_date,
                       "end": r.last_qualifying_date, "rows": [r]}
        if cur:
            rows.append(cur)

    out = []
    for c in rows:
        rs = c["rows"]
        wins = sorted({r.window for r in rs}, key=lambda w: ["1M", "3M", "6M"].index(w))
        # Prefer the window that found the most flagpoles for the pattern detail.
        best = max(rs, key=lambda r: (r.num_hh_flagpoles or 0))
        ranks = [r.best_rank_in_bucket for r in rs if pd.notna(r.best_rank_in_bucket)]
        out.append({
            "ticker": c["ticker"],
            "chart_symbol": _repair.clean(c["ticker"]),
            "former_symbols": None,
            "windows": "+".join(wins),
            "n_windows": len(wins),
            "start": c["start"].date(),
            "end": c["end"].date(),
            "days": (c["end"] - c["start"]).days,
            "mktcap_bucket": best.mktcap_bucket,
            "best_rank": min(ranks) if ranks else None,
            "num_flagpoles": best.num_hh_flagpoles,
            "hh_dates": best.hh_dates,
            "resistances": best.suggested_resistances,
            "latest_resistance": best.latest_suggested_resistance,
            "is_valid_flag": None,
            "notes": None,
        })
    return pd.DataFrame(out)


def collapse_to_ticker(m: pd.DataFrame) -> pd.DataFrame:
    """One row per ticker: every streak folded into semicolon-separated span lists.

    Matches how the review actually happens -- you open a chart once and judge all of that
    ticker's periods together, rather than reopening it per streak.
    """
    def spans(g):
        return "; ".join(f"{a}..{b}" for a, b in zip(g["start"], g["end"]))

    rows = []
    for t, g in m.groupby("ticker", sort=True):
        g = g.sort_values("start")
        ranks = g["best_rank"].dropna()
        rows.append({
            "ticker": t,
            "chart_symbol": g["chart_symbol"].iloc[0],
            "former_symbols": g["former_symbols"].dropna().iloc[0] if g["former_symbols"].notna().any() else None,
            "n_streaks": len(g),
            "first_seen": g["start"].min(),
            "last_seen": g["end"].max(),
            "streak_spans": spans(g),
            "windows_per_streak": "; ".join(g["windows"]),
            "any_triple": bool((g["n_windows"] == 3).any()),
            "mktcap_bucket": g["mktcap_bucket"].mode().iloc[0] if g["mktcap_bucket"].notna().any() else None,
            "best_rank": int(ranks.min()) if len(ranks) else None,
            "total_flagpoles": int(g["num_flagpoles"].fillna(0).sum()),
            "data_warning": None,
            "reviewed": None,
            "notes": None,
        })
    return pd.DataFrame(rows)


def attach_data_warnings(df: pd.DataFrame) -> pd.DataFrame:
    """Mark rows whose bars came from the P123 backfill with a suspect price jump.

    P123 reports prices as traded while the rest of the cache is split-adjusted; the backfill
    rescales at the seam, but a split INSIDE the backfilled window isn't corrected and can't
    be auto-detected -- in a dataset of explosive movers a 2x day is ordinary, so there's no
    threshold that separates a split from a real move. Rather than drop the data (losing real
    streaks) or include it silently (injecting artifacts), the suspicion is surfaced here.
    """
    p = os.path.join(HERE, "_p123_backfill_report.csv")
    if not os.path.exists(p):
        return df
    rep = pd.read_csv(p)
    warn = {}
    for r in rep.itertuples():
        if r.max_1d_move >= 10:
            warn[r.ticker] = f"P123 backfill: {r.max_1d_move:.0f}x 1-day move -- almost certainly an uncorrected split"
        elif r.max_1d_move >= 3:
            warn[r.ticker] = f"P123 backfill: {r.max_1d_move:.1f}x 1-day move -- verify against chart"
    df["data_warning"] = df["ticker"].map(warn)
    return df


def resolve_symbols(tickers: list, workers: int = 8) -> dict:
    """Former symbols for the rename-prone subset (suffixed or bankruptcy tickers)."""
    def one(t):
        sym = _repair.clean(t)
        cands = [c for c, conf in _repair.prior_tickers(sym) if conf == "high"]
        if not cands:
            cands = _repair.edgar_prior_tickers(sym, "2005-01-01")
        return t, ", ".join(dict.fromkeys(cands)) or None

    out = {}
    with ThreadPoolExecutor(max_workers=workers) as ex:
        for i, (t, val) in enumerate(ex.map(one, tickers), 1):
            out[t] = val
            if i % 100 == 0:
                print(f"  resolved {i:,}/{len(tickers):,}")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-lookup", action="store_true")
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    df = load_all()
    print(f"{len(df):,} OK rows across {df['window'].nunique()} windows")
    m = cluster(df)
    print(f"-> {len(m):,} merged streaks across {m['ticker'].nunique():,} tickers")
    print(m["windows"].value_counts().to_string())

    if not args.no_lookup:
        # Only the rename-prone ones: a point-in-time suffix or a bankruptcy Q. Querying
        # every ticker would cost thousands of calls to learn nothing for most of them.
        prone = sorted(t for t in m["ticker"].unique()
                       if "^" in t or _repair.clean(t).endswith("Q"))
        print(f"\nresolving former symbols for {len(prone):,} rename-prone tickers...")
        mapping = resolve_symbols(prone, args.workers)
        m["former_symbols"] = m["ticker"].map(mapping)
        found = m["former_symbols"].notna().sum()
        print(f"  {found:,} rows carry a former symbol")

    m = m.sort_values(["ticker", "start"]).reset_index(drop=True)
    m.to_csv(OUT_CSV, index=False)

    by_ticker = attach_data_warnings(collapse_to_ticker(m))
    n_warn = by_ticker["data_warning"].notna().sum()
    if n_warn:
        print(f"  {n_warn:,} tickers flagged with a data warning (P123 backfill split risk)")
    by_ticker.to_csv(OUT_TICKER_CSV, index=False)
    print(f"\n-> {len(by_ticker):,} tickers (one row each)")
    try:
        with pd.ExcelWriter(OUT_XLSX) as xl:
            by_ticker.to_excel(xl, index=False, sheet_name="by_ticker")
            m.to_excel(xl, index=False, sheet_name="by_streak")
        print(f"wrote {OUT_TICKER_CSV}\n      {OUT_CSV}\n      {OUT_XLSX} (both sheets)")
    except Exception as e:
        print(f"wrote {OUT_TICKER_CSV}\n      {OUT_CSV} (xlsx failed: {e})")


if __name__ == "__main__":
    main()
