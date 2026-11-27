"""Entry-rule test report (2026-11-23): run_stage2 --stage entry -> per strategy, on TV + delisted dev flags,
  all flags | skip red (hand labels) | skip red (auto-labeler, TV flags only, apples-to-apples vs hand on TV)
with EV, EV ex top 5%, total R, max DD, Calmar, negative years, EV on TV / delisted halves.

Hand label = htf_pattern_truth.csv (all TV flags AA..CVI, reviewed 2026-11-09) else the recorder's
pattern_recorded (every delisted flag was reviewed in the local recorder; blind trainer 2026-11-23 showed the
green/red call holds without hindsight). Auto = htf_pattern_labels.csv (labeler, TV only).

    ../../.venv/Scripts/python.exe -m htf_backtest.entry_test_report [--tag entry_test_slip0.1]
"""
import argparse
import os

import numpy as np
import pandas as pd

from . import config

RED = {"Red HTF", "Big Red Flag"}
ENTRY_NAME = {"5m": "hybrid 5m OR (current)", "30m": "hybrid 30m OR", "orb30": "30m ORB above R1 (yours)",
              "c5m": "5m bar close > R1", "c10m": "10m bar close > R1", "c15m": "15m bar close > R1"}


def labels():
    adv = config.ADV
    m = pd.read_csv(os.path.join(adv, "htf_annotations_master.csv"), usecols=["ticker", "flag_no", "pattern_recorded"])
    tr = pd.read_csv(os.path.join(adv, "htf_pattern_truth.csv"), usecols=["ticker", "flag_no", "truth"])
    au = pd.read_csv(os.path.join(adv, "htf_pattern_labels.csv"), usecols=["ticker", "flag_no", "pattern"])
    m = m[m.flag_no > 0].merge(tr, on=["ticker", "flag_no"], how="left").merge(au, on=["ticker", "flag_no"], how="left")
    m["hand"] = m.truth.fillna(m.pattern_recorded)
    return m[["ticker", "flag_no", "hand", "pattern"]].rename(columns={"pattern": "auto"})


def stats(g):
    g = g.sort_values(["entry_date", "ticker"])
    r = g.realized_R.to_numpy(float)
    n = len(r)
    if n < 20:
        return pd.Series({"trades": n})
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    s = np.sort(r)
    yr = g.groupby(g.entry_date.str[:4]).realized_R.sum()
    return pd.Series({"trades": n, "win": (r > 0).mean(), "EV": r.mean(),
                      "EV_ex5": s[:n - int(np.ceil(n * 0.05))].mean(), "total_R": r.sum(), "max_dd": dd,
                      "calmar": r.sum() / abs(dd) if dd else np.nan, "neg_yrs": int((yr < 0).sum()),
                      "n_10R": int((r >= 10).sum()),
                      "EV_TV": g[~g.del_].realized_R.mean(), "EV_DEL": g[g.del_].realized_R.mean()})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", default="entry_test_slip0.1")
    a = ap.parse_args()
    t = pd.read_parquet(os.path.join(config.OUTPUTS_DIR, f"trades_{a.tag}.parquet"))
    print("status:", t.status.value_counts().to_dict())
    t = t[t.status == "OK"].merge(labels(), on=["ticker", "flag_no"], how="left")
    t["entry_date"] = t.entry_date.astype(str)
    t["del_"] = t.ticker.str.contains("^", regex=False)
    print(f"hand label coverage {t.hand.notna().mean():.1%} | auto coverage on TV {t[~t.del_].auto.notna().mean():.1%}")
    views = {"all": t, "skip_red_hand": t[t.hand.notna() & ~t.hand.isin(RED)],
             "TV_skip_red_auto": t[~t.del_ & t.auto.notna() & ~t.auto.isin(RED)],
             "TV_skip_red_hand": t[~t.del_ & t.hand.notna() & ~t.hand.isin(RED)]}
    out = []
    for v, d in views.items():
        s = d.groupby(["entry_type", "stop_type", "trail_type"]).apply(stats, include_groups=False).reset_index()
        out.append(s.assign(view=v))
    s = pd.concat(out)
    p = os.path.join(config.OUTPUTS_DIR, f"report_{a.tag}.csv")
    s.to_csv(p, index=False)
    pd.set_option("display.width", 250)
    cols = ["entry_type", "stop_type", "trail_type", "trades", "win", "EV", "EV_ex5", "total_R", "max_dd", "calmar",
            "neg_yrs", "n_10R", "EV_TV", "EV_DEL"]
    for v in ("all", "skip_red_hand"):
        x = s[s.view == v]
        print(f"\n=== {v}: by entry rule (median over 10 stop x trail combos)")
        print(x.groupby("entry_type")[["trades", "EV", "EV_ex5", "max_dd", "calmar", "EV_TV", "EV_DEL"]].median()
              .round(3).sort_values("calmar", ascending=False).to_string())
        print(f"\n=== {v}: top 15 by Calmar")
        print(x.sort_values("calmar", ascending=False)[cols].head(15).round(3).to_string(index=False))
    tv = s[s.view.isin(["TV_skip_red_auto", "TV_skip_red_hand"])]
    print("\n=== TV flags only: skip red by AUTO vs HAND labels (median over strategies)")
    print(tv.groupby("view")[["trades", "EV", "EV_ex5", "max_dd", "calmar"]].median().round(3).to_string())
    print(f"\nsaved {p}")


if __name__ == "__main__":
    main()
