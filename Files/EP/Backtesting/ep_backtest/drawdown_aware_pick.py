"""
Re-pick each walk-forward fold's winner using a drawdown-aware criterion instead of
G_score, reusing the already-cached screen2 TRAIN trade-level output (no new backtest
simulation needed for the train side). Then evaluates each alternate pick on that fold's
real, never-seen TEST set (a single-strategy run -- cheap, seconds not hours).

Motivated by a user observation, 2026-09-03: fold3's G-score winner used a 15-minute
entry (structurally lower win rate than 60-minute -- confirmed: 23.2% vs 24.6% average
across the whole ~35k-trade population) AND came in at an unusually low 9.2% test win
rate even for a 15m strategy. G_score (0.5*EV_R_score + 0.5*profit_factor_score) has no
concept of path risk -- it can pick a strategy with a great average return that is
nearly untradeable in practice. Result (see EBTA_Book_Robustness_Findings_2026-09-03.md
section 4): drawdown-aware picks converge on nearly the same recipe across all 3 folds
(ADR-based stop, 20MA-touch trail, early profit-taking, 30% core -- only entry timeframe
varies), unlike G_score which picks something different and unrelated every time. Mixed
on raw out-of-sample return (won big in fold3, lost in fold2, a wash in fold1), but the
fold3 case is stark: G-score's pick went -108R underwater to net only +38R; the Calmar
pick made +248R with a -32R drawdown.

Usage:
    python -m ep_backtest.drawdown_aware_pick
"""
import sys
sys.path.insert(0, '.')
import pandas as pd

from ep_backtest import config
from ep_backtest.load_events import load_ep_v5
from ep_backtest.run_batch_v3b import run_v3b_grid

DT_FAMILY = ["DT", "DT SW", "DT U"]
MIN_TRADES = 30  # ignore thin-sample strategies where "low drawdown" is just "barely traded"

FOLDS = [
    {
        "name": "fold1_train2019", "train_end": 2019, "test_start": 2020, "test_end": 2026,
        "screen2_path": "outputs/walkforward/trades_screen2_train2019.parquet",
    },
    {
        "name": "fold2_train2021", "train_end": 2021, "test_start": 2022, "test_end": 2023,
        "screen2_path": "outputs/walkforward/fold2_train2021/trades_screen2_train.parquet",
    },
    {
        "name": "fold3_train2023", "train_end": 2023, "test_start": 2024, "test_end": 2026,
        "screen2_path": "outputs/walkforward/fold3_train2023/trades_screen2_train.parquet",
    },
]


def max_drawdown_R(sub: pd.DataFrame) -> float:
    sub = sub.sort_values("event_date")
    cum = sub["realized_R"].cumsum()
    peak = cum.cummax()
    dd = cum - peak
    return float(dd.min())


def per_strategy_stats(trades: pd.DataFrame) -> pd.DataFrame:
    ok = trades[(trades["status"] == "OK") & (~trades["chart_pattern"].isin(DT_FAMILY))]
    rows = []
    for strategy_id, sub in ok.groupby("strategy_id"):
        n = len(sub)
        if n < MIN_TRADES:
            continue
        wins = sub[sub["realized_R"] > 0]["realized_R"]
        losses = sub[sub["realized_R"] <= 0]["realized_R"]
        ev = sub["realized_R"].mean()
        pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf")
        dd = max_drawdown_R(sub)
        row = sub.iloc[0]
        rows.append({
            "strategy_id": strategy_id, "n": n, "win_rate": (sub["realized_R"] > 0).mean(),
            "EV_R": ev, "PF": pf, "total_R": sub["realized_R"].sum(), "max_drawdown_R": dd,
            "calmar": (sub["realized_R"].sum() / abs(dd)) if dd < 0 else float("inf"),
            "entry_type": row["entry_type"], "stop_type": row["stop_type"], "trail_type": row["trail_type"],
            "sell_style": row["sell_style"], "target_ladder": row["target_ladder"], "core_pct": row["core_pct"],
        })
    return pd.DataFrame(rows)


def _year_slice(events, lo=None, hi=None):
    years = pd.to_datetime(events["reaction_date"]).dt.year
    mask = pd.Series(True, index=events.index)
    if lo is not None:
        mask &= years >= lo
    if hi is not None:
        mask &= years <= hi
    return events[mask].reset_index(drop=True)


def eval_on_test(pick_row, test_events, sim_workers=6):
    base = [(pick_row["entry_type"], pick_row["stop_type"], pick_row["trail_type"])]
    ladder = {pick_row["target_ladder"]: config.V3_MULTI_TARGET_LADDERS[pick_row["target_ladder"]]}
    trades_test = run_v3b_grid(test_events, base, ladder, [pick_row["sell_style"]], [pick_row["core_pct"]],
                                workers=sim_workers)
    ok = trades_test[(trades_test["status"] == "OK") & (~trades_test["chart_pattern"].isin(DT_FAMILY))]
    if len(ok) == 0:
        return {"n": 0}
    wins = ok[ok["realized_R"] > 0]["realized_R"]
    losses = ok[ok["realized_R"] <= 0]["realized_R"]
    dd = max_drawdown_R(ok)
    return {
        "n": len(ok), "win_rate": (ok["realized_R"] > 0).mean(),
        "EV_R": ok["realized_R"].mean(), "PF": wins.sum() / abs(losses.sum()) if losses.sum() != 0 else float("inf"),
        "total_R": ok["realized_R"].sum(), "max_drawdown_R": dd,
    }


def main():
    events_all = load_ep_v5()
    for fold in FOLDS:
        print(f"\n{'='*90}\n{fold['name']}\n{'='*90}", flush=True)
        trades = pd.read_parquet(fold["screen2_path"])
        stats = per_strategy_stats(trades)
        print(f"{len(stats)} candidate strategies with >= {MIN_TRADES} trades", flush=True)

        by_gscore = stats.copy()
        by_gscore["ev_score"] = (by_gscore["EV_R"] / 0.30 * 10).clip(0, 10)
        by_gscore["pf_score"] = (by_gscore["PF"] / 2.0 * 10).clip(0, 10)
        by_gscore["G"] = 0.5 * by_gscore["ev_score"] + 0.5 * by_gscore["pf_score"]
        g_pick = by_gscore.sort_values("G", ascending=False).iloc[0]

        dd_pick = stats.sort_values("max_drawdown_R", ascending=False).iloc[0]  # least negative = smallest drawdown
        calmar_pick = stats.sort_values("calmar", ascending=False).iloc[0]

        print(f"\n[G-score pick]     {g_pick['strategy_id']}", flush=True)
        print(f"  TRAIN: n={g_pick['n']}, win_rate={g_pick['win_rate']*100:.1f}%, PF={g_pick['PF']:.3f}, "
              f"EV_R={g_pick['EV_R']:.4f}, max_DD={g_pick['max_drawdown_R']:.2f}R, total_R={g_pick['total_R']:.2f}",
              flush=True)

        print(f"\n[Min-drawdown pick] {dd_pick['strategy_id']}", flush=True)
        print(f"  TRAIN: n={dd_pick['n']}, win_rate={dd_pick['win_rate']*100:.1f}%, PF={dd_pick['PF']:.3f}, "
              f"EV_R={dd_pick['EV_R']:.4f}, max_DD={dd_pick['max_drawdown_R']:.2f}R, total_R={dd_pick['total_R']:.2f}",
              flush=True)

        print(f"\n[Calmar pick (total_R / max_DD)] {calmar_pick['strategy_id']}", flush=True)
        print(f"  TRAIN: n={calmar_pick['n']}, win_rate={calmar_pick['win_rate']*100:.1f}%, PF={calmar_pick['PF']:.3f}, "
              f"EV_R={calmar_pick['EV_R']:.4f}, max_DD={calmar_pick['max_drawdown_R']:.2f}R, "
              f"total_R={calmar_pick['total_R']:.2f}, calmar={calmar_pick['calmar']:.2f}", flush=True)

        test_events = _year_slice(events_all, lo=fold["test_start"], hi=fold["test_end"])

        for label, pick in [("G-score", g_pick), ("Min-drawdown", dd_pick), ("Calmar", calmar_pick)]:
            test_stats = eval_on_test(pick, test_events)
            if test_stats["n"] == 0:
                print(f"\n  TEST ({label}): no OK trades", flush=True)
                continue
            print(f"\n  TEST ({label}, {fold['test_start']}-{fold['test_end']}): n={test_stats['n']}, "
                  f"win_rate={test_stats['win_rate']*100:.1f}%, PF={test_stats['PF']:.3f}, "
                  f"EV_R={test_stats['EV_R']:.4f}, max_DD={test_stats['max_drawdown_R']:.2f}R, "
                  f"total_R={test_stats['total_R']:.2f}", flush=True)


if __name__ == "__main__":
    main()
