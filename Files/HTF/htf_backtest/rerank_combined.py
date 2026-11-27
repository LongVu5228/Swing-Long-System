"""Re-rank the 936 Stage 1 strategies on survivors + delisted flags (§29: the finalist was picked on
TradingView survivors only; delisted flags earn ~0.3R less and push the finalist's drawdown to -81R).

Stacks trades_stage1.parquet (TV flags) with trades_stage1_delisted.parquet (run_grid --delisted-only),
then scores every strategy in true entry-date order on the combined set:
  EV, EV ex top 5%, total R, max drawdown, Calmar (total R / |max DD|), negative years, worst year,
  plus EV on each half (TV vs delisted) so a strategy that only works on survivors is visible.

    ../../.venv/Scripts/python.exe -m htf_backtest.rerank_combined     # -> backtest_outputs/rerank_combined.csv
"""
import os

import numpy as np
import pandas as pd

from . import config

FINALIST = "E5M__S0.75ADR__T20MA_TOUCH"


def stats(g):
    g = g.sort_values(["entry_date", "ticker"])
    r = g.realized_R.to_numpy(float)
    n = len(r)
    if not n:
        return pd.Series(dtype=float)
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    s = np.sort(r)
    yr = g.groupby(g.entry_date.str[:4]).realized_R.sum()
    tv, de = g[g.src == "TV"].realized_R, g[g.src == "DEL"].realized_R
    return pd.Series({
        "trades": n, "win_rate": (r > 0).mean(), "EV_R": r.mean(),
        "EV_ex_top5pct": s[:n - int(np.ceil(n * 0.05))].mean() if n > 20 else np.nan,
        "total_R": r.sum(), "rate_10R": (r >= 10).mean(), "max_dd_R": dd,
        "calmar": r.sum() / abs(dd) if dd else np.nan,
        "neg_years": int((yr < 0).sum()), "worst_year_R": yr.min(),
        "EV_TV": tv.mean(), "EV_DEL": de.mean(), "n_DEL": len(de),
        "median_stop_pct": g.stop_pct.median(),
    })


def main():
    cols = ["ticker", "flag_no", "strategy_id", "entry_type", "stop_type", "trail_type", "status", "realized_R",
            "entry_date", "stop_pct"]
    tv = pd.read_parquet(os.path.join(config.OUTPUTS_DIR, "trades_stage1.parquet"), columns=cols)
    tv = tv[~tv.ticker.str.contains("^", regex=False)].assign(src="TV")
    de = pd.read_parquet(os.path.join(config.OUTPUTS_DIR, "trades_stage1_delisted.parquet"), columns=cols).assign(src="DEL")
    print("status TV:", tv.status.value_counts().head(4).to_dict())
    print("status DEL:", de.status.value_counts().head(4).to_dict())
    t = pd.concat([tv, de])
    t = t[t.status == "OK"].copy()
    t["entry_date"] = t.entry_date.astype(str)
    s = t.groupby("strategy_id").apply(stats, include_groups=False).reset_index()
    meta = t.drop_duplicates("strategy_id").set_index("strategy_id")[["entry_type", "stop_type", "trail_type"]]
    s = s.join(meta, on="strategy_id")
    # rank: Calmar and EV ex top 5% (the two that survivorship hurt most), each as a percentile, equally weighted
    s["rank_score"] = 0.5 * s.calmar.rank(pct=True) + 0.5 * s.EV_ex_top5pct.rank(pct=True)
    s = s.sort_values("rank_score", ascending=False).reset_index(drop=True)
    s.index += 1
    out = os.path.join(config.OUTPUTS_DIR, "rerank_combined.csv")
    s.to_csv(out, index_label="rank")
    pd.set_option("display.width", 250)
    show = ["strategy_id", "trades", "win_rate", "EV_R", "EV_ex_top5pct", "total_R", "max_dd_R", "calmar",
            "neg_years", "worst_year_R", "EV_TV", "EV_DEL", "median_stop_pct"]
    print("\nTOP 25 by rank_score (Calmar + EV ex top 5%):")
    print(s[show].head(25).round(3).to_string())
    print("\nTOP 15 by EV (EV ex top 5% > -0.2):")
    print(s[s.EV_ex_top5pct > -0.2].sort_values("EV_R", ascending=False)[show].head(15).round(3).to_string())
    f = s[s.strategy_id == FINALIST]
    print(f"\nold finalist {FINALIST}: rank {f.index[0]} of {len(s)}")
    print(f[show].round(3).to_string())
    print("\nby dimension (median over strategies):")
    for d in ("entry_type", "stop_type", "trail_type"):
        print(s.groupby(d)[["EV_R", "EV_ex_top5pct", "max_dd_R", "calmar", "EV_DEL"]].median().round(3)
              .sort_values("calmar", ascending=False).to_string(), "\n")
    print(f"saved {out}")


if __name__ == "__main__":
    main()
