"""
Stage 1 grid runner (§12): every development-sample flag x 9 entries x 13 stops x 8 trails, with
the reference partial ladder. EP run_batch style: ProcessPool over flags (one worker = one flag,
reads its own cached bars, no shared state), trade-level parquet + strategy summary.

    ../../.venv/Scripts/python.exe -m htf_backtest.run_grid --limit 20 --workers 4     # smoke
    ../../.venv/Scripts/python.exe -m htf_backtest.run_grid --workers 8                # full dev sample

Summary per strategy: trades, win rate, avg R (EV), PF, total R, G-score (re-based caps 1.0R /
PF 3.0), 10R+ and 5R+ rates, EV without 10R+ trades, max drawdown and longest losing streak in
chronological order (EP §4), median stop distance, and the status mix.
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

from . import config


def _flags(limit=None, tickers=None) -> pd.DataFrame:
    import quick_backtest_chosen_one as qb
    m = qb.read_master()
    # HTF_SAMPLE=dev (default): development sample only | holdout: rows after DEV_LAST_TICKER (run ONCE on the
    # frozen system, 2026-11-25) | all
    sample = os.environ.get("HTF_SAMPLE", "dev")
    m = m[m.flag_no > 0]
    if sample == "dev":
        m = m[m.ticker <= config.DEV_LAST_TICKER]
    elif sample == "holdout":
        m = m[m.ticker > config.DEV_LAST_TICKER]
    if tickers:
        m = m[m.ticker.isin(tickers)]
    m = m.sort_values(["ticker", "flag_no"])
    return m.head(limit) if limit else m


def _work(args):
    from . import simulate as S
    ticker, flag_rows = args
    daily = S.daily_frame(ticker)
    out = []
    for f in flag_rows.itertuples():
        mdf, mstat = None, config.STATUS_MISSING_MINUTE_DATA
        if daily is not None and pd.notna(f.setup_confirmed):
            mdf, mstat = S.minute_frame(ticker, S._d(f.setup_confirmed), S._d(max(f.final_flag_end, f.setup_confirmed)),
                                        last_bar=daily.date.max() if daily is not None else None)
        try:
            out += S.run_flag(f, daily, mdf, missing_status=mstat)
        except Exception as exc:  # noqa: BLE001 -- one bad flag must not kill the run
            out.append({"ticker": ticker, "flag_no": int(f.flag_no), "status": f"ERROR: {exc}"})
    return out


def max_dd_and_streak(r: pd.Series) -> tuple:
    eq = r.cumsum()
    dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
    streak = best = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        best = max(best, streak)
    return dd, best


def summarize(trades: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sid, g in trades.groupby("strategy_id"):
        ok = g[g.status == "OK"].sort_values(["entry_date", "ticker"])
        r = ok.realized_R.astype(float)
        n = len(r)
        win, loss = r[r > 0], r[r <= 0]
        pf = win.sum() / abs(loss.sum()) if len(loss) and loss.sum() != 0 else np.nan
        ev = r.mean() if n else np.nan
        dd, streak = max_dd_and_streak(r)
        rows.append({
            "strategy_id": sid, "entry_type": g.entry_type.iloc[0], "stop_type": g.stop_type.iloc[0],
            "trail_type": g.trail_type.iloc[0], "trades": n, "win_rate": len(win) / n if n else np.nan,
            "EV_R": ev, "profit_factor": pf, "total_R": r.sum(),
            "rate_10R": (r >= 10).mean() if n else np.nan, "rate_5R": (r >= 5).mean() if n else np.nan,
            "EV_ex_10R": r[r < 10].mean() if n else np.nan, "max_dd_R": dd, "max_losing_streak": streak,
            "median_stop_pct": ok.stop_pct.median() if n else np.nan,
            "entry_rate": (g.status != config.STATUS_NO_ENTRY).mean(),
            "invalid_stop": (g.status == config.STATUS_INVALID_STOP_GEOMETRY).sum(),
            "missing_minute": (g.status == config.STATUS_MISSING_MINUTE_DATA).sum(),
        })
    s = pd.DataFrame(rows)
    s["G_score"] = (0.5 * (s.EV_R / config.G_EV_CAP * 10).clip(0, 10)
                    + 0.5 * (s.profit_factor / config.G_PF_CAP * 10).clip(0, 10))
    s["calmar"] = s.total_R / s.max_dd_R.abs().replace(0, np.nan)
    return s.sort_values("G_score", ascending=False).reset_index(drop=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="first N flags (smoke test)")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tag", default="stage1")
    ap.add_argument("--delisted-only", action="store_true",
                    help="only the local-recorder (^) flags; stack the output onto trades_stage1 (§29)")
    args = ap.parse_args()

    flags = _flags()
    if args.delisted_only:
        flags = flags[flags.ticker.str.contains("^", regex=False)]
    flags = flags.head(args.limit) if args.limit else flags
    # One task per FLAG, not per ticker: per-ticker tasks left most workers idle while one
    # ground through AAOI's 14 long-window flags (smoke run 2026-11-13). Each task reloads its
    # ticker's daily bars, which is cheap next to the simulations.
    groups = [(r.ticker, flags.loc[[i]]) for i, r in zip(flags.index, flags.itertuples())]
    groups.sort(key=lambda g: -int(g[1].final_flag_end.iloc[0]))   # long recent windows first
    print(f"{len(flags)} flags on {len(groups)} tickers x {len(config.ENTRY_TYPES)}x{len(config.STOP_TYPES)}x"
          f"{len(config.TRAIL_TYPES)} = {len(flags) * 936:,} strategy-trades")
    from tqdm import tqdm
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_work, g) for g in groups]
        for f in tqdm(as_completed(futs), total=len(futs), desc="flags"):
            rows += f.result()
    trades = pd.DataFrame(rows)
    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
    tp = os.path.join(config.OUTPUTS_DIR, f"trades_{args.tag}.parquet")
    for c in ("entry_date", "exit_date"):
        if c in trades:
            trades[c] = trades[c].astype(str)
    trades.to_parquet(tp, index=False)
    summ = summarize(trades)
    sp = os.path.join(config.OUTPUTS_DIR, f"strategy_summary_{args.tag}.csv")
    summ.to_csv(sp, index=False)
    print(f"\nstatus: {trades.status.value_counts().to_dict()}")
    cols = ["strategy_id", "trades", "win_rate", "EV_R", "profit_factor", "total_R", "rate_10R", "EV_ex_10R",
            "max_dd_R", "G_score"]
    print(summ[cols].head(15).round(3).to_string(index=False))
    print(f"\ntrades: {tp}\nsummary: {sp}")


if __name__ == "__main__":
    main()
