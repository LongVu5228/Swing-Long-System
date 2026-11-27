"""
Pull the user's pattern reviews from the Google Sheet "HTF Ticker List" (tab "Individual HTF")
into htf_pattern_truth.csv, and line-of-least-resistance fixes into htf_r1_revisions.csv.

  python sync_sheet_reviews.py <downloaded .xlsx> [--through TICKER]

Sheet columns: "Revised Flag Pattern" (short code) and "Revised Line of Least Resistance"
(new R1 source bar as YY/M/D, e.g. 21/7/2 = 2021-07-02). N = not a flag: written to
htf_dropped_flags.csv, which every backtest skips. A blank pattern on a reviewed ticker
means the overlay's auto-label was right. Reviewed = every ticker alphabetically up to the last
one with any revision, or up to --through. Tickers past that keep whatever the truth file had.
"""

import os
import sys
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "htf_pattern_labels.csv")
TRUTH = os.path.join(HERE, "htf_pattern_truth.csv")
R1_OUT = os.path.join(HERE, "htf_r1_revisions.csv")
DROPPED = os.path.join(HERE, "htf_dropped_flags.csv")
MASTER = os.path.join(HERE, "htf_annotations_master.csv")
PAT, LLR = "Revised Flag Pattern", "Revised Line of Least Resistance"

CODES = {"GHTF": "Green HTF", "PHTF": "Perfect HTF", "RHTF": "Red HTF", "EHTF": "Expanding HTF",
         "SP": "Spiky Top HTF", "SPIKY": "Spiky Top HTF",
         "BGF": "Big Green Flag", "BFG": "Big Green Flag", "BPF": "Big Perfect Flag",
         "PF": "Big Perfect Flag", "PFLAG": "Big Perfect Flag", "BRF": "Big Red Flag",
         "N": None,  # N = null: not a flag after all -> dropped from the sample
         # plain names (2026-11-06 column): HTFs are just the color, Flags get "Big"
         "GREEN": "Green HTF", "PERFECT": "Perfect HTF", "RED": "Red HTF",
         "BIG GREEN": "Big Green Flag", "BIG PERFECT": "Big Perfect Flag", "BIG RED": "Big Red Flag",
         "SPIKY TOP": "Spiky Top HTF", "SPIKY": "Spiky Top HTF", "EXPANDING": "Expanding HTF",
         "NULL": None}


def yymd(s) -> int:
    y, m, d = (int(x) for x in str(s).strip().split("/"))
    return (2000 + y if y < 100 else y) * 10000 + m * 100 + d


def main():
    path = sys.argv[1]
    through = sys.argv[sys.argv.index("--through") + 1].upper() if "--through" in sys.argv else None
    d = pd.read_excel(path, sheet_name="Individual HTF")
    d["ticker"] = d.ticker.astype(str)
    # every "Revised Flag Pattern" column (codes, then plain names): the right-most filled one wins
    pcols = [c for c in d.columns if str(c).startswith(PAT)]
    d[PAT] = d[pcols[::-1]].bfill(axis=1).iloc[:, 0]
    d[PAT] = d[PAT].where(d[PAT].isna(), d[PAT].astype(str).str.strip().str.upper().str.replace(r"\s+", " ", regex=True))
    rev = d[d[PAT].notna() | d[LLR].notna()]
    through = through or max(rev.ticker)
    unknown = set(rev[PAT].dropna()) - set(CODES)
    if unknown:
        sys.exit(f"unknown pattern code(s) {sorted(unknown)} -- add them to CODES")

    auto = pd.read_csv(LABELS)[["ticker", "flag_no", "pattern"]]
    auto = auto[(auto.ticker <= through) & auto.pattern.isin({v for v in CODES.values() if v})]
    # Tickers re-recorded with the recorder's Pattern dropdown (schema 4): the recorder is the
    # truth. Their sheet rows predate the re-export and may point at renumbered flags.
    m = pd.read_csv(MASTER)
    m = m[m.pattern_recorded.notna()]
    recorded = dict(zip(zip(m.ticker, m.flag_no), m.pattern_recorded))
    rec_tickers = set(m.ticker)
    d = d[~d.ticker.isin(rec_tickers)]
    codes = d.set_index(["ticker", "flag_no"])[PAT].dropna().map(CODES.get)
    drop = codes[codes.isna()]
    pd.DataFrame(list(drop.index), columns=["ticker", "flag_no"]).assign(
        reviewed=date.today().isoformat()).to_csv(DROPPED, index=False)
    fix = codes.dropna()
    auto = auto[[k not in set(drop.index) for k in zip(auto.ticker, auto.flag_no)]]
    truth = [recorded.get((t, n), fix.get((t, n), p)) for t, n, p in zip(auto.ticker, auto.flag_no, auto.pattern)]
    new = auto.assign(truth=truth, reviewed=date.today().isoformat())[["ticker", "flag_no", "truth", "reviewed"]]
    old = pd.read_csv(TRUTH) if os.path.exists(TRUTH) else new.iloc[:0]
    out = pd.concat([old[old.ticker > through], new]).sort_values(["ticker", "flag_no"])
    out.to_csv(TRUTH, index=False)

    r1 = rev[rev[LLR].notna()][["ticker", "flag_no", "r1_source_bar", "r1_price", LLR]].copy()
    r1["r1_source_bar_revised"] = r1[LLR].map(yymd)
    r1.drop(columns=LLR).to_csv(R1_OUT, index=False)

    dropped = ", ".join(f"{t} {n}" for t, n in drop.index)
    print(f"reviewed through {through}: {len(new)} flags on {new.ticker.nunique()} tickers, "
          f"{int(fix.index.get_level_values(0).isin(new.ticker).sum())} pattern fixes, {len(r1)} R1 fixes, "
          f"{len(drop)} dropped (N): {dropped}")
    print(f"truth file: {len(out)} flags on {out.ticker.nunique()} tickers")


if __name__ == "__main__":
    main()
