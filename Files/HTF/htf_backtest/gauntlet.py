"""
Validation gauntlet (findings doc §13) on everything already simulated -- no new backtests except
the finalist slippage runs (run_stage2 --stage gauntlet, HTF_SLIPPAGE=0.001/0.003/0.01).

    ../../.venv/Scripts/python.exe -m htf_backtest.gauntlet            # all sections
    ../../.venv/Scripts/python.exe -m htf_backtest.gauntlet --only rc  # rc | wf | grid | final | slip

Sections
  rc    White's Reality Check + Hansen SPA (l/c/u) over EVERY variant tried (Stage 1 936 + 2a + 2b +
        expiry, ~1,690), H0: no variant has positive mean R. Flags are the resampling unit, ordered
        by setup_confirmed, moving-block bootstrap at block 1/10/25/50 flags (keeps date clustering
        and the cross-strategy correlation, since every variant trades the same flags).
  wf    Walk-forward re-search on the Stage 1 grid (the only stage not chosen with full-sample
        hindsight): 3 expanding folds (train <=2015/2019/2022), pre-declared pick rules, test after.
  grid  Parameter neighbourhood: entry x stop heatmaps for 20ma_touch (EV, EV ex top 5%, DD) +
        G-score vs Calmar vs min-DD pick comparison.
  final Finalists at the 15-session expiry: era table + consistency score, max DD / streak, tail
        dependence, moving-block CIs on EV.
  slip  Slippage 0.1/0.3/1% per fill: EV, break-even, split by price and stop width.
"""

import argparse
import os

import numpy as np
import pandas as pd

from . import config

OUT = config.OUTPUTS_DIR
FINAL_ID = "E5M__S0.75ADR__T20MA_TOUCH"
COMBINED = False      # --combined (2026-11-23): TV + delisted flags, final2 shortlist, entry-test variants in RC
BLOCKS = [1, 10, 25, 50]
N_BOOT = 2000
SEED = 42
FOLDS = [(2015, 2016, 2019), (2019, 2020, 2022), (2022, 2023, 2026)]
LINES = []


def say(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LINES.append(s)


# --------------------------------------------------------------------------------------- helpers
def max_dd_streak(r):
    r = np.asarray(r, float)
    if not len(r):
        return 0.0, 0
    eq = np.cumsum(r)
    dd = float((eq - np.maximum.accumulate(np.maximum(eq, 0))).min())
    best = cur = 0
    for x in r:
        cur = cur + 1 if x <= 0 else 0
        best = max(best, cur)
    return dd, best


def ev_ex_top(r, frac=0.05):
    s = np.sort(np.asarray(r, float))
    n = len(s)
    return s[:n - int(np.ceil(n * frac))].mean() if n > 20 else np.nan


def block_idx(n, L, rng):
    """Moving (circular) block bootstrap index of length n."""
    starts = rng.integers(0, n, size=int(np.ceil(n / L)))
    return (starts[:, None] + np.arange(L)[None, :]).ravel()[:n] % n


def block_ci(r, L, rng, n_boot=N_BOOT):
    r = np.asarray(r, float)
    m = np.array([r[block_idx(len(r), L, rng)].mean() for _ in range(n_boot)])
    return np.percentile(m, 5), np.percentile(m, 95), (m <= 0).mean()


def flag_order():
    import sys
    sys.path.insert(0, os.path.join(config.HTF_DIR, "Advanced Backtesting"))
    from .run_grid import _flags
    f = _flags()[["ticker", "flag_no", "setup_confirmed"]].drop_duplicates(["ticker", "flag_no"])
    return f.sort_values(["setup_confirmed", "ticker", "flag_no"]).reset_index(drop=True)


def load_variants():
    """Long frame: ticker, flag_no, variant, realized_R, entry_date (status OK only)."""
    cols = ["ticker", "flag_no", "strategy_id", "status", "realized_R", "entry_date"]
    parts = []
    s1 = _stage1(cols)
    parts.append(s1.assign(variant="S1|" + s1.strategy_id))
    if COMBINED:
        for tag in ("entry_test_slip0.1", "final2_slip0.1"):
            p = os.path.join(OUT, f"trades_{tag}.parquet")
            if os.path.exists(p):
                d = pd.read_parquet(p, columns=cols + ["partial"])
                if tag.startswith("final2"):
                    d = d[d.partial != "ref"]      # ref ladder rows duplicate the entry test
                parts.append(d.assign(variant=f"{tag}|" + d.strategy_id + "|" + d.partial))
    for tag, extra in [("stage2a", ["partial"]), ("stage2b", ["partial"]), ("expiry", ["partial", "expiry"])]:
        p = os.path.join(OUT, f"trades_{tag}.parquet")
        if not os.path.exists(p):
            continue
        d = pd.read_parquet(p, columns=cols + extra)
        if tag == "expiry":
            d = d[d.expiry != "box"]                       # box rows duplicate Stage 1
            d = d.assign(variant=f"{tag}|" + d.strategy_id + "|" + d.expiry)
        else:
            d = d[d.partial != "ref"] if tag == "stage2a" else d[d.partial != "s20_sp7.5"]
            d = d.assign(variant=f"{tag}|" + d.strategy_id + "|" + d.partial)
        parts.append(d)
    v = pd.concat([p[p.status == "OK"][["ticker", "flag_no", "variant", "realized_R", "entry_date"]] for p in parts])
    return v


def _stage1(cols):
    """Stage 1 grid trades; combined mode stacks the delisted (^) grid run onto the TV flags."""
    s1 = pd.read_parquet(os.path.join(OUT, "trades_stage1.parquet"), columns=cols)
    if not COMBINED:
        return s1
    s1 = s1[~s1.ticker.str.contains("^", regex=False)]
    de = pd.read_parquet(os.path.join(OUT, "trades_stage1_delisted.parquet"), columns=cols)
    return pd.concat([s1, de], ignore_index=True)


# --------------------------------------------------------------------------------------- RC / SPA
def rc_spa():
    say("\n=== 1. WHITE'S REALITY CHECK + HANSEN SPA (H0: best variant's mean R <= 0) ===")
    order = flag_order()
    v = load_variants()
    fidx = {k: i for i, k in enumerate(zip(order.ticker, order.flag_no))}
    v["row"] = [fidx.get(k, -1) for k in zip(v.ticker, v.flag_no)]
    v = v[v.row >= 0]
    names = sorted(v.variant.unique())
    col = {n: j for j, n in enumerate(names)}
    n, K = len(order), len(names)
    X = np.zeros((n, K))
    M = np.zeros((n, K), dtype=np.float32)
    X[v.row.to_numpy(), v.variant.map(col).to_numpy()] = v.realized_R.to_numpy()
    M[v.row.to_numpy(), v.variant.map(col).to_numpy()] = 1
    cnt = M.sum(0)
    mu = X.sum(0) / cnt
    sd = np.sqrt(((X - mu) ** 2 * M).sum(0) / (cnt - 1))
    se = sd / np.sqrt(cnt)
    t = mu / se
    say(f"{K} variants x {n} flags (date-ordered); trades per variant median {np.median(cnt):.0f}")
    best_t, best_m = int(np.argmax(t)), int(np.argmax(mu))
    say(f"best t-stat : {names[best_t]}  mean {mu[best_t]:+.3f}R  t {t[best_t]:.2f}  n {cnt[best_t]:.0f}")
    say(f"best mean   : {names[best_m]}  mean {mu[best_m]:+.3f}R  t {t[best_m]:.2f}  n {cnt[best_m]:.0f}")
    say(f"variants with mean > 0: {(mu > 0).mean():.1%}   t > 2: {(t > 2).mean():.1%}")

    thr = -np.sqrt(2 * np.log(np.log(np.median(cnt))))
    mu_l, mu_c, mu_u = np.minimum(mu, 0), np.where(t <= thr, mu, 0.0), np.zeros(K)
    T_obs, R_obs = max(t.max(), 0), max(mu.max(), 0)
    rng = np.random.default_rng(SEED)
    rows = []
    for L in BLOCKS:
        stats = {"RC": [], "SPA_l": [], "SPA_c": [], "SPA_u": []}
        for _ in range(N_BOOT):
            idx = block_idx(n, L, rng)
            c = M[idx].sum(0)
            mb = np.where(c > 0, X[idx].sum(0) / np.maximum(c, 1), mu)
            d = mb - mu                                      # centred bootstrap mean
            stats["RC"].append(max((d + mu_u).max(), 0))
            for k, adj in (("SPA_l", mu_l), ("SPA_c", mu_c), ("SPA_u", mu_u)):
                stats[k].append(max(((d + adj) / se).max(), 0))
        p = {"RC": np.mean(np.array(stats["RC"]) >= R_obs)}
        p.update({k: np.mean(np.array(stats[k]) >= T_obs) for k in ("SPA_l", "SPA_c", "SPA_u")})
        q95 = np.percentile(stats["SPA_c"], 95)
        rows.append({"block": L, **{f"p_{k}": round(v, 4) for k, v in p.items()}, "SPA_c_null95_t": round(q95, 2),
                     "n_variants_t_above_null95": int((t > q95).sum())})
    r = pd.DataFrame(rows)
    say(r.to_string(index=False))
    fin = [j for j, nm in enumerate(names) if FINAL_ID in nm]
    for j in fin:
        say(f"  finalist {names[j]}: mean {mu[j]:+.3f}R t {t[j]:.2f} (null 95% max-t at block 50: {rows[-1]['SPA_c_null95_t']})")
    pd.DataFrame({"variant": names, "n": cnt, "mean_R": mu, "t": t}).sort_values("t", ascending=False) \
        .to_csv(os.path.join(OUT, "gauntlet_variant_tstats.csv"), index=False)
    r.to_csv(os.path.join(OUT, "gauntlet_rc_spa.csv"), index=False)


# --------------------------------------------------------------------------------------- walk-forward
def _summ(g):
    r = g.sort_values(["entry_date", "ticker"]).realized_R.to_numpy()
    dd, _ = max_dd_streak(r)
    return pd.Series({"n": len(r), "EV": r.mean() if len(r) else np.nan, "total": r.sum(), "dd": dd,
                      "ex5": ev_ex_top(r), "calmar": r.sum() / abs(dd) if dd < 0 else np.nan})


def walk_forward():
    say("\n=== 2. WALK-FORWARD RE-SEARCH ON THE STAGE 1 GRID (936 strategies) ===")
    s1 = _stage1(["ticker", "strategy_id", "status", "realized_R", "entry_date"])
    s1 = s1[s1.status == "OK"].copy()
    s1["y"] = s1.entry_date.astype(str).str[:4].astype(int)
    rules = {"max EV": lambda s: s.EV, "max Calmar": lambda s: s.calmar, "max EV ex top5%": lambda s: s.ex5}
    rows = []
    for tr_end, te_lo, te_hi in FOLDS:
        tr = s1[s1.y <= tr_end].groupby("strategy_id").apply(_summ, include_groups=False)
        te = s1[(s1.y >= te_lo) & (s1.y <= te_hi)].groupby("strategy_id").apply(_summ, include_groups=False)
        tr = tr[tr.n >= 100]
        say(f"\nfold train <= {tr_end} ({int(tr.n.max())} max train trades)  test {te_lo}-{te_hi}: "
            f"{(te.EV > 0).mean():.0%} of strategies positive in test, median test EV {te.EV.median():+.3f}R")
        for name, f in rules.items():
            sid = f(tr).idxmax()
            rank = int((te.EV > te.at[sid, "EV"]).sum()) + 1
            rows.append({"fold": f"<= {tr_end}", "rule": name, "pick": sid, "train_EV": tr.at[sid, "EV"],
                         "test_n": te.at[sid, "n"], "test_EV": te.at[sid, "EV"], "test_total": te.at[sid, "total"],
                         "test_dd": te.at[sid, "dd"], "test_rank_of_936": rank})
        if FINAL_ID not in tr.index or FINAL_ID not in te.index:
            both = tr.join(te, lsuffix="_tr", rsuffix="_te", how="inner")
            say(f"  Spearman(train EV, test EV) across strategies: {both.EV_tr.rank().corr(both.EV_te.rank()):+.2f}")
            continue
        rows.append({"fold": f"<= {tr_end}", "rule": "fixed finalist", "pick": FINAL_ID,
                     "train_EV": tr.at[FINAL_ID, "EV"], "test_n": te.at[FINAL_ID, "n"], "test_EV": te.at[FINAL_ID, "EV"],
                     "test_total": te.at[FINAL_ID, "total"], "test_dd": te.at[FINAL_ID, "dd"],
                     "test_rank_of_936": int((te.EV > te.at[FINAL_ID, "EV"]).sum()) + 1})
        # rank correlation train vs test: does the in-sample ordering carry over?
        both = tr.join(te, lsuffix="_tr", rsuffix="_te", how="inner")
        say(f"  Spearman(train EV, test EV) across strategies: {both.EV_tr.rank().corr(both.EV_te.rank()):+.2f}")
    w = pd.DataFrame(rows)
    say(w.round(3).to_string(index=False))
    w.to_csv(os.path.join(OUT, "gauntlet_walkforward.csv"), index=False)


# --------------------------------------------------------------------------------------- grid / selection
def grid():
    say("\n=== 3. PARAMETER NEIGHBOURHOOD (Stage 1, trail 20ma_touch) + PICK COMPARISON ===")
    if COMBINED:
        say("combined mode: see backtest_outputs/rerank_combined.csv (rerank_combined.py) instead")
        return
    s = pd.read_csv(os.path.join(OUT, "strategy_summary_stage1_plus.csv"))
    g = s[s.trail_type == "20ma_touch"]
    order_e = list(config.ENTRY_TYPES)
    order_s = list(config.STOP_TYPES)
    for col, label in (("EV_R", "EV"), ("EV_ex_10R", "EV ex 10R+"), ("max_dd_R", "max DD")):
        h = g.pivot(index="stop_type", columns="entry_type", values=col).reindex(index=order_s, columns=order_e)
        say(f"\n{label} (rows stop, cols entry)")
        say(h.round(2).to_string())
    ok = s[(s.trades >= 1000) & (s.EV_R > 0)]
    picks = {"G-score": ok.G_score.idxmax(), "max EV": ok.EV_R.idxmax(), "Calmar": ok.calmar.idxmax(),
             "min DD (EV>=0.3)": ok[ok.EV_R >= 0.3].max_dd_R.idxmax(), "mon_cap5": ok.mon_cap5.idxmax()}
    t = s.loc[list(picks.values()), ["strategy_id", "trades", "EV_R", "EV_ex_10R", "total_R", "max_dd_R",
                                       "calmar", "mon_cap5", "neg_years"]]
    t.insert(0, "pick", list(picks.keys()))
    say("\nselection-rule comparison (Stage 1, >=1000 trades):")
    say(t.round(3).to_string(index=False))


# --------------------------------------------------------------------------------------- finalists
def _gauntlet_trades(slip="0.1"):
    p = os.path.join(OUT, f"trades_{'final2' if COMBINED else 'gauntlet'}_slip{slip}.parquet")
    return pd.read_parquet(p) if os.path.exists(p) else None


def finalists():
    say("\n=== 4. FINALISTS @ 15-SESSION EXPIRY (slippage 0.1%) ===")
    t = _gauntlet_trades("0.1")
    if t is None:
        say("finalist trades missing -- run run_stage2 --stage gauntlet (or final2 for --combined) first")
        return
    t = t[t.status == "OK"].copy()
    t["y"] = t.entry_date.astype(str).str[:4]
    rng = np.random.default_rng(SEED)
    summ = []
    for (sid, part), g in t.groupby(["strategy_id", "partial"]):
        g = g.sort_values(["entry_date", "ticker"])
        r = g.realized_R.to_numpy()
        dd, streak = max_dd_streak(r)
        yr = g.groupby("y").realized_R.agg(["mean", "size", "sum"])
        y8 = yr[yr["size"] >= 8]["mean"]
        srt = np.sort(r)[::-1]
        tot = r.sum()
        row = {"strategy": sid, "partial": part, "n": len(r), "EV": r.mean(), "total": tot, "max_dd": dd,
               "streak": streak, "neg_years": int((yr["sum"] < 0).sum()), "worst_year_EV": y8.min(),
               "consistency": y8.min() - y8.std(),
               "top1_share": srt[0] / tot, "top5_share": srt[:5].sum() / tot,
               "top1pct_share": srt[:max(1, len(r) // 100)].sum() / tot,
               "top5pct_share": srt[:int(np.ceil(len(r) * .05))].sum() / tot,
               "top10pct_share": srt[:int(np.ceil(len(r) * .10))].sum() / tot,
               "EV_ex_top10_trades": srt[10:].mean(), "EV_ex_top5pct": ev_ex_top(r)}
        for L in BLOCKS:
            lo, hi, p0 = block_ci(r, L, rng, 1000)
            row[f"ci90_b{L}"] = f"[{lo:+.2f},{hi:+.2f}] p0={p0:.3f}"
        summ.append(row)
    s = pd.DataFrame(summ).sort_values("EV", ascending=False)
    with pd.option_context("display.width", 250, "display.max_columns", 40):
        say(s.round(3).to_string(index=False))
    s.to_csv(os.path.join(OUT, "gauntlet_finalists.csv"), index=False)
    f = t[(t.strategy_id == FINAL_ID) & (t.partial == "ref")]
    yr = f.groupby("y").realized_R.agg(n="size", EV="mean", total="sum").round(2)
    say(f"\nera table {FINAL_ID} / ref ladder / e15:")
    say(yr.T.to_string())


def slippage():
    say("\n=== 5. SLIPPAGE 0.1% / 0.3% / 1% PER FILL (15-session expiry) ===")
    rows, base = [], None
    for slip in ("0.1", "0.3", "1"):
        t = _gauntlet_trades(slip)
        if t is None:
            say(f"  slip {slip}% missing")
            continue
        t = t[t.status == "OK"]
        for (sid, part), g in t.groupby(["strategy_id", "partial"]):
            r = g.sort_values("entry_date").realized_R.to_numpy()
            rows.append({"strategy": sid, "partial": part, "slip_pct": float(slip), "n": len(r), "EV": r.mean(),
                         "ex5": ev_ex_top(r), "dd": max_dd_streak(r)[0]})
        if slip == "1":
            base = t
    s = pd.DataFrame(rows)
    if s.empty:
        return
    p = s.pivot_table(index=["strategy", "partial"], columns="slip_pct", values="EV")
    if p.shape[1] >= 2:
        x = np.array(p.columns, float)
        p["breakeven_slip_pct"] = [np.interp(0, *zip(*sorted(zip(row[::-1], x[::-1]))))
                                   if row.min() < 0 else
                                   x[-1] + row.iloc[-1] / ((row.iloc[0] - row.iloc[-1]) / (x[-1] - x[0]))
                                   for _, row in p[list(x)].iterrows()]
    say(p.round(3).to_string())
    # liquidity proxies at 1%: entry price and stop width
    if base is not None:
        f = base[(base.strategy_id == FINAL_ID) & (base.partial == "ref")].copy()
        t1 = _gauntlet_trades("0.1")
        t1 = t1[(t1.strategy_id == FINAL_ID) & (t1.partial == "ref") & (t1.status == "OK")]
        for name, d in (("0.1%", t1), ("1%", f)):
            d = d.assign(price=pd.cut(d.entry_fill, [0, 5, 10, 20, 50, 1e9], labels=["<5", "5-10", "10-20", "20-50", "50+"]),
                         stopw=pd.cut(d.stop_pct, [0, 3, 5, 8, 100], labels=["<3%", "3-5%", "5-8%", "8%+"]))
            say(f"\n{FINAL_ID} ref @ slip {name}: EV by entry price / stop width")
            say(d.groupby("price", observed=True).realized_R.agg(["size", "mean"]).round(3).T.to_string())
            say(d.groupby("stopw", observed=True).realized_R.agg(["size", "mean"]).round(3).T.to_string())
    s.to_csv(os.path.join(OUT, "gauntlet_slippage.csv"), index=False)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["rc", "wf", "grid", "final", "slip"])
    ap.add_argument("--combined", action="store_true", help="TV + delisted flags, final2 shortlist")
    ap.add_argument("--final-id", default=None, help="strategy_id for the era / slippage detail tables")
    a = ap.parse_args()
    global COMBINED, FINAL_ID
    COMBINED = a.combined
    FINAL_ID = a.final_id or FINAL_ID
    steps = {"rc": rc_spa, "wf": walk_forward, "grid": grid, "final": finalists, "slip": slippage}
    for k, fn in steps.items():
        if a.only in (None, k):
            fn()
    name = f"gauntlet_report{'_combined' if COMBINED else ''}{'_' + a.only if a.only else ''}.txt"
    with open(os.path.join(OUT, name), "w", encoding="utf-8") as fh:
        fh.write("\n".join(LINES))
    print(f"\nreport: {os.path.join(OUT, name)}")


if __name__ == "__main__":
    main()
