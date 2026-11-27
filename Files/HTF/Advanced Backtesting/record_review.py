"""
Record a finished pattern review for one ticker into htf_pattern_truth.csv: the slots you
corrected get your label, every other flag on the ticker is confirmed as the auto-label.
Re-reviewing a ticker replaces its earlier rows.

  python record_review.py AMD 27=brf 28=brf 3=rh 1=ph
  python record_review.py CSIQ               (nothing to fix -- all confirmed)

Short names: gh/ph/rh = Green/Perfect/Red HTF, bgf/bpf/brf = Big Green/Perfect/Red Flag,
sp = Spiky Top HTF, eh = Expanding HTF (full names work too, quoted).
"""

import os
import sys
from datetime import date

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LABELS = os.path.join(HERE, "htf_pattern_labels.csv")
TRUTH = os.path.join(HERE, "htf_pattern_truth.csv")

SHORT = {"gh": "Green HTF", "ph": "Perfect HTF", "rh": "Red HTF", "bgf": "Big Green Flag",
         "bpf": "Big Perfect Flag", "brf": "Big Red Flag", "sp": "Spiky Top HTF", "eh": "Expanding HTF"}
VALID = set(SHORT.values())


def main():
    tk, fixes = sys.argv[1].upper(), {}
    for a in sys.argv[2:]:
        n, lab = a.split("=", 1)
        lab = SHORT.get(lab.strip().lower(), lab.strip())
        if lab not in VALID:
            sys.exit(f"unknown label {lab!r} -- use one of {sorted(SHORT)} or {sorted(VALID)}")
        fixes[int(n)] = lab
    auto = pd.read_csv(LABELS)
    auto = auto[auto.ticker == tk][["ticker", "flag_no", "pattern"]]
    if auto.empty:
        sys.exit(f"{tk}: no flags in {os.path.basename(LABELS)}")
    bad = set(fixes) - set(auto.flag_no)
    if bad:
        sys.exit(f"{tk}: no flag number(s) {sorted(bad)} -- it has {auto.flag_no.min()}..{auto.flag_no.max()}")
    new = auto.assign(truth=[fixes.get(n, p) for n, p in zip(auto.flag_no, auto.pattern)],
                      reviewed=date.today().isoformat())[["ticker", "flag_no", "truth", "reviewed"]]
    old = pd.read_csv(TRUTH) if os.path.exists(TRUTH) else new.iloc[:0]
    out = pd.concat([old[old.ticker != tk], new]).sort_values(["ticker", "flag_no"])
    out.to_csv(TRUTH, index=False)
    print(f"{tk}: {len(new)} flags reviewed, {len(fixes)} corrected, {len(new) - len(fixes)} confirmed "
          f"| truth file: {len(out)} flags on {out.ticker.nunique()} tickers")


if __name__ == "__main__":
    main()
