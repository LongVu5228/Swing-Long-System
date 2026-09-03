"""
Reusable walk-forward fold runner (EBTA Ch.6 "Walk-Forward Testing" -- Aronson,
Evidence-Based Technical Analysis, 2007): the book's walk-forward diagram (Fig 6.57)
explicitly calls for MULTIPLE non-overlapping folds, each producing an independent
out-of-sample estimate, so the walk-forward result's own variance can be assessed rather
than treated as a single conclusive pilot. The 2026-09-01 session ran exactly one fold
(train<=2019, test>=2020); this script reruns the identical screen1->screen2->winner-eval
pipeline for arbitrary train/test year boundaries so additional folds can be added without
re-deriving the pipeline.

Given EP event volume is heavily back-loaded (311 of 2355 events, 13.2%, fall in
2012-2019; the rest -- 2020-2026 -- is 86.8%), fixed-size sliding windows aren't viable
this early in the dataset. This uses an EXPANDING training window (train = everything up
to train_end_year) with a bounded, non-overlapping test window per fold, matching what the
sparse early history actually supports.

DT-family (DT/DT SW/DT U) chart-pattern exclusion is applied as a POST-HOC trade-level
filter, right before each summarize_all_v3b() call -- verified against the original fold1
pilot's own raw output (trades_screen1_train2019.parquet still contains DT-family rows,
61,560 of 100,764), so this matches its actual methodology, not a pre-filter on which
events enter screen1/screen2.

Usage:
    python -m ep_backtest.walkforward_fold --train-end 2021 --test-start 2022 --test-end 2023 --fold-name fold2_train2021
    python -m ep_backtest.walkforward_fold --train-end 2023 --test-start 2024 --test-end 2026 --fold-name fold3_train2023
"""

import argparse
import os
import time

import pandas as pd

from . import config
from .load_events import load_ep_v5
from .multi_partial_taking import SELL_STYLES
from .run_batch import _prefetch
from .run_batch_v3b import run_v3b_grid, summarize_all_v3b, stage2_base_strategies

DT_FAMILY = ["DT", "DT SW", "DT U"]


def _year_slice(events: pd.DataFrame, lo: int = None, hi: int = None) -> pd.DataFrame:
    years = pd.to_datetime(events["reaction_date"]).dt.year
    mask = pd.Series(True, index=events.index)
    if lo is not None:
        mask &= years >= lo
    if hi is not None:
        mask &= years <= hi
    return events[mask].reset_index(drop=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--train-end", type=int, required=True, help="train = all events with reaction_date year <= this")
    parser.add_argument("--test-start", type=int, required=True)
    parser.add_argument("--test-end", type=int, required=True)
    parser.add_argument("--fold-name", required=True, help="output subfolder under outputs/walkforward/")
    parser.add_argument("--top-n", type=int, default=config.V3B_SCREEN_STAGE2_DEFAULT_TOP_N)
    parser.add_argument("--sim-workers", type=int, default=os.cpu_count() or 4)
    parser.add_argument("--workers", type=int, default=15)
    args = parser.parse_args()

    t0 = time.time()
    out_dir = os.path.join(config.OUTPUTS_DIR, "walkforward", args.fold_name)
    os.makedirs(out_dir, exist_ok=True)

    events_all = load_ep_v5()

    train_events = _year_slice(events_all, hi=args.train_end)
    test_events = _year_slice(events_all, lo=args.test_start, hi=args.test_end)
    print(f"[{args.fold_name}] train: {len(train_events)} events (<= {args.train_end}), "
          f"test: {len(test_events)} events ({args.test_start}-{args.test_end}), "
          f"DT-family excluded post-hoc at summary time", flush=True)

    _prefetch(train_events, args.workers)
    _prefetch(test_events, args.workers)

    # ---------- Screen1 on TRAIN only ----------
    print(f"[{args.fold_name}] screen1: {len(config.V3B_SCREEN_STAGE1_BASE_STRATEGIES)} base strategies "
          f"x {len(train_events)} train events...", flush=True)
    t1 = time.time()
    trades1 = run_v3b_grid(
        train_events, config.V3B_SCREEN_STAGE1_BASE_STRATEGIES, config.V3B_SCREEN_STAGE1_TARGET_LADDERS,
        config.V3B_SCREEN_STAGE1_SELL_STYLES, config.V3B_SCREEN_STAGE1_CORE_PCTS, workers=args.sim_workers,
    )
    trades1.to_parquet(os.path.join(out_dir, "trades_screen1_train.parquet"), index=False)
    summary1 = summarize_all_v3b(trades1[~trades1["chart_pattern"].isin(DT_FAMILY)])
    summary1_path = os.path.join(out_dir, "strategy_summary_screen1_train.csv")
    summary1.to_csv(summary1_path, index=False)
    print(f"[{args.fold_name}] screen1 done in {time.time()-t1:.0f}s. Top G_score: {summary1['G_score'].iloc[0]:.2f} "
          f"({summary1['strategy_id'].iloc[0]})", flush=True)

    # ---------- Screen2 on TRAIN only ----------
    base2 = stage2_base_strategies(summary1_path, args.top_n)
    print(f"[{args.fold_name}] screen2: {len(base2)} base strategies (top {args.top_n} of screen1) "
          f"x full sell/ladder/core sweep x {len(train_events)} train events...", flush=True)
    t2 = time.time()
    trades2 = run_v3b_grid(
        train_events, base2, config.V3_MULTI_TARGET_LADDERS, SELL_STYLES, config.V3_CORE_PCTS,
        workers=args.sim_workers,
    )
    trades2.to_parquet(os.path.join(out_dir, "trades_screen2_train.parquet"), index=False)
    summary2 = summarize_all_v3b(trades2[~trades2["chart_pattern"].isin(DT_FAMILY)])
    summary2.to_csv(os.path.join(out_dir, "strategy_summary_screen2_train.csv"), index=False)
    print(f"[{args.fold_name}] screen2 done in {time.time()-t2:.0f}s.", flush=True)

    winner = summary2.iloc[0]
    winner_id = winner["strategy_id"]
    print(f"[{args.fold_name}] WINNER (picked on TRAIN only): {winner_id}", flush=True)
    print(f"  TRAIN: trades={winner['triggered_trades']}, win_rate={winner['win_rate']*100:.1f}%, "
          f"PF={winner['profit_factor']:.3f}, EV_R={winner['EV_R']:.4f}, total_R={winner['total_R']:.2f}, "
          f"G={winner['G_score']:.2f}", flush=True)

    # ---------- Evaluate winner on TEST (never seen by screen1 or screen2) ----------
    winner_base = [(winner["entry_type"], winner["stop_type"], winner["trail_type"])]
    winner_ladder = {winner["target_ladder"]: config.V3_MULTI_TARGET_LADDERS[winner["target_ladder"]]}
    t3 = time.time()
    trades_test = run_v3b_grid(
        test_events, winner_base, winner_ladder, [winner["sell_style"]], [winner["core_pct"]],
        workers=args.sim_workers,
    )
    trades_test.to_parquet(os.path.join(out_dir, "trades_winner_test.parquet"), index=False)
    summary_test = summarize_all_v3b(trades_test[~trades_test["chart_pattern"].isin(DT_FAMILY)])
    summary_test.to_csv(os.path.join(out_dir, "strategy_summary_winner_test.csv"), index=False)
    test_row = summary_test.iloc[0]
    print(f"[{args.fold_name}] TEST ({args.test_start}-{args.test_end}, never seen by selection) "
          f"in {time.time()-t3:.0f}s:", flush=True)
    print(f"  TEST: trades={test_row['triggered_trades']}, win_rate={test_row['win_rate']*100:.1f}%, "
          f"PF={test_row['profit_factor']:.3f}, EV_R={test_row['EV_R']:.4f}, total_R={test_row['total_R']:.2f}, "
          f"G={test_row['G_score']:.2f}", flush=True)

    ev_decay_pct = (test_row["EV_R"] - winner["EV_R"]) / winner["EV_R"] * 100 if winner["EV_R"] else float("nan")
    print(f"[{args.fold_name}] EV_R change train->test: {ev_decay_pct:+.1f}%", flush=True)
    print(f"[{args.fold_name}] TOTAL elapsed: {time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
