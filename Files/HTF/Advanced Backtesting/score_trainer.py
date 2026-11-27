"""
Scores the filled-in htf_trainer_queue.csv against the original labels and the Stage 1 backtest.

  pattern : full name or code  G=Green HTF  P=Perfect HTF  R=Red HTF
                               BG=Big Green Flag  BP=Big Perfect Flag  BR=Big Red Flag
  r1_date : YYYYMMDD of the bar whose high you'd use as R1 (compared with r1_source_bar)
  clean   : optional 1 clean / 2 borderline / 3 messy

    python score_trainer.py               # everything answered so far
    python score_trainer.py --half A
"""
import argparse
import os

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "..", "backtest_outputs")
STRATEGY = "E5M__S0.75ADR__T20MA_TOUCH"
CODES = {"G": "Green HTF", "P": "Perfect HTF", "R": "Red HTF",
         "BG": "Big Green Flag", "BP": "Big Perfect Flag", "BR": "Big Red Flag"}
RED = {"Red HTF", "Big Red Flag"}


def norm(p):
    if pd.isna(p) or str(p).strip() == "":
        return np.nan
    s = str(p).strip()
    return CODES.get(s.upper(), next((v for v in CODES.values() if v.lower() == s.lower()), s))


def stats(r: pd.Series) -> dict:
    r = r.dropna().sort_values()
    n = len(r)
    if not n:
        return {"n": 0}
    cut = n - int(np.ceil(n * 0.05))
    return {"n": n, "win": round((r > 0).mean(), 3), "EV": round(r.mean(), 3),
            "EV_ex_top5": round(r.iloc[:cut].mean(), 3) if n >= 20 else np.nan,
            "n_10R": int((r >= 10).sum()), "total_R": round(r.sum(), 1)}


def table(df, by):
    return pd.DataFrame({k: stats(g.R) for k, g in df.groupby(by)}).T


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--queue", default=os.path.join(HERE, "htf_trainer_queue.csv"))
    ap.add_argument("--half", choices=["A", "B"])
    a = ap.parse_args()

    q = pd.read_csv(a.queue, dtype={"r1_date": str})
    key = pd.read_csv(os.path.join(HERE, "htf_trainer_key.csv"))
    df = q.merge(key[["train_id", "flag_no", "truth", "r1_source_bar"]], on="train_id")
    df["mine"] = df.pattern.map(norm)
    df = df[df.mine.notna() | df.r1_date.notna() | df.clean.notna()]
    if a.half:
        df = df[df.half == a.half]
    if df.empty:
        print("nothing answered yet")
        return
    t = pd.read_parquet(os.path.join(OUT, "trades_stage1.parquet"),
                        columns=["ticker", "flag_no", "strategy_id", "status", "realized_R"])
    t = t[(t.strategy_id == STRATEGY) & (t.status == "OK")][["ticker", "flag_no", "realized_R"]]
    df = df.merge(t.rename(columns={"realized_R": "R"}), on=["ticker", "flag_no"], how="left")
    print(f"{len(df)} flags answered ({df.R.notna().sum()} traded under {STRATEGY})\n")

    p = df[df.mine.notna()]
    if len(p):
        bad = sorted(set(p.mine) - set(CODES.values()))
        if bad:
            print("unrecognised pattern answers:", bad)
        print(f"PATTERN  exact agreement {(p.mine == p.truth).mean():.1%}   "
              f"red/non-red agreement {((p.mine.isin(RED)) == (p.truth.isin(RED))).mean():.1%}")
        print(pd.crosstab(p.truth, p.mine, margins=True).to_string(), "\n")
        print("backtest R by YOUR label");     print(table(p, "mine").to_string(), "\n")
        print("backtest R by ORIGINAL label"); print(table(p, "truth").to_string(), "\n")
        flip = p[p.truth.isin(RED) != p.mine.isin(RED)]
        if len(flip):
            print("red <-> non-red flips (original -> yours)")
            print(table(flip.assign(f=flip.truth.isin(RED).map({True: "red->non", False: "non->red"})), "f")
                  .to_string(), "\n")

    r = df[df.r1_date.notna() & df.r1_source_bar.notna()]
    if len(r):
        mine = pd.to_datetime(r.r1_date.str.strip(), format="%Y%m%d", errors="coerce")
        orig = pd.to_datetime(r.r1_source_bar.astype(int).astype(str), format="%Y%m%d")
        ok = mine.notna()
        gap = pd.Series(np.abs(np.busday_count(mine[ok].values.astype("datetime64[D]"),
                                               orig[ok].values.astype("datetime64[D]"))), index=r.index[ok])
        print(f"R1 DATE  {ok.sum()} parsed ({(~ok).sum()} bad)   exact {(gap == 0).mean():.1%}   "
              f"within 1 day {(gap <= 1).mean():.1%}   within 3 {(gap <= 3).mean():.1%}   "
              f"median gap {gap.median():.0f} days\n")

    c = df[df.clean.notna()]
    if len(c):
        print("backtest R by CLEAN grade (all patterns)"); print(table(c, "clean").to_string(), "\n")
        cr = c[c.truth.isin(RED)]
        if len(cr):
            print("backtest R by CLEAN grade (original red flags)"); print(table(cr, "clean").to_string())


if __name__ == "__main__":
    main()
