"""
Stage 2a (§12): the shortlisted Stage 1 strategies x one-partial-dimension-at-a-time variants
(partials.stage2a_variants), same flags, same engine pieces. EP run_batch style.

    ../../.venv/Scripts/python.exe -m htf_backtest.run_stage2 --verify --limit 40   # ref == Stage 1 check
    ../../.venv/Scripts/python.exe -m htf_backtest.run_stage2 --workers 6            # full Stage 2a

Shortlist (25, hand-built for coverage rather than a single score, since Stage 1's composite
ranks would drop the whole 0.5 ADR "max monsters" family that Stage 2 is meant to test):
  entries 5m / 15m / r1_cross  x  stops 0.5 ADR / 0.75 ADR / 4% / 1.0 ADR / 5%  x  20ma_touch   (15)
  5m  x  the same 5 stops  x  close_below_20ma / close_below_10ma                                (10)
"""

import argparse
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

import numpy as np
import pandas as pd

from . import config

STOPS = ["0.50adr", "0.75adr", "4pct_entry", "1.00adr", "5pct_entry"]
SHORTLIST = ([(e, s, "20ma_touch") for e in ("5m", "15m", "r1_cross") for s in STOPS]
             + [("5m", s, t) for s in STOPS for t in ("close_below_20ma", "close_below_10ma")])
# Stage 2b + expiry test: the finalists
FINAL = [("5m", "0.75adr", "20ma_touch"), ("5m", "1.00adr", "20ma_touch"), ("15m", "0.75adr", "20ma_touch"),
         ("15m", "1.00adr", "20ma_touch"), ("5m", "0.50adr", "20ma_touch")]
EXPIRIES = [None, 3, 5, 10, 15, 20, 30]
# Stage 2c (profit-taking alternatives): 2 stops x 4 trails, 15-session expiry
STAGE2C = [("5m", s, t) for s in ("0.75adr", "1.00adr")
           for t in ("20ma_touch", "10ma_touch", "close_below_20ma", "close_below_10ma")]
# entry-rule test (2026-11-23): current hybrid OR entries (5m, 30m) vs the user's 30m ORB-above-R1 rule vs the
# original "N-min bar closes above R1" rule, on TV + delisted flags, 15-session expiry, ref ladder
ENTRY_TEST = [(e, s, t) for e in ("5m", "30m", "orb30", "c5m", "c10m", "c15m")
              for s in ("0.75adr", "1.00adr", "1.50adr", "4pct_entry", "last_higher_low")
              for t in ("20ma_touch", "close_below_adaptive_5_10")]     # None = the hand-drawn box end (Stage 1 behaviour)
# lock re-check (2026-11-24): entries head-to-head at the locked stop/trail + core-split / ladder variants
LOCK_ENTRIES = ["30m", "r1_cross", "1m", "5m", "15m", "60m", "xc5m"]
LOCK = [(e, "0.75adr", "20ma_touch") for e in LOCK_ENTRIES]


def _expiry_end(conf, n):
    """Last session a resting order is live: the n-th session after setup_confirmed."""
    from ep_backtest import calendar_utils
    return calendar_utils.sessions_from(conf, n)[-1]


def _work(args):
    from . import entry as htf_entry, partials as P, simulate as S, stops
    from ep_backtest import config as ep_config
    ticker, f, variants, strategies, expiries = args
    base = {"ticker": ticker, "flag_no": int(f.flag_no), "setup_confirmed": int(f.setup_confirmed),
            "final_flag_end": int(f.final_flag_end), "r1_price": f.r1_price}

    def blank(e, s, t, v, x, status):
        return {**base, "strategy_id": S.strategy_id(e, s, t), "entry_type": e, "stop_type": s, "trail_type": t,
                "partial": v.label, "expiry": "box" if x is None else f"e{x}", "status": status}

    daily = S.daily_frame(ticker)
    mdf, mstat = None, config.STATUS_MISSING_MINUTE_DATA
    if daily is not None:
        mdf, mstat = S.minute_frame(ticker, S._d(f.setup_confirmed), S._d(max(f.final_flag_end, f.setup_confirmed)),
                                    last_bar=daily.date.max())
    if pd.isna(f.r1_price) or mdf is None or daily is None:
        st = config.STATUS_NO_LEVEL if pd.isna(f.r1_price) else mstat
        return [blank(e, s, t, v, x, st) for x in expiries for e, s, t in strategies for v in variants]

    rows, memo, ents = [], {}, {}
    sessions = sorted(mdf.session_date.unique())
    conf, box_end = S._d(f.setup_confirmed), S._d(max(f.final_flag_end, f.setup_confirmed))
    covered = sessions[-1]
    dhigh = daily.set_index("date").high
    for x in expiries:
        end = box_end if x is None else _expiry_end(conf, x)
        for e, s, t in strategies:
            if (e, end) not in ents:
                ent = htf_entry.find_entry(e, mdf, daily, float(f.r1_price), conf, end)
                # an order still live past the cached minute data: if the daily bars show R1 traded
                # through in the uncovered sessions, the outcome is unknown, not "no entry"
                if ent.entry_status != ep_config.STATUS_VALID_TRADE and end > covered:
                    gap = dhigh[(dhigh.index > covered) & (dhigh.index <= end)]
                    if (gap > float(f.r1_price)).any():
                        ent = "DATA_SHORT"
                ents[(e, end)] = ent
            ent = ents[(e, end)]
            if isinstance(ent, str):
                rows += [blank(e, s, t, v, x, ent) for v in variants]
                continue
            if ent.entry_status != ep_config.STATUS_VALID_TRADE:
                rows += [blank(e, s, t, v, x, config.STATUS_NO_ENTRY) for v in variants]
                continue
            price = stops.stop_price(s, ent, daily)
            if price is None or price >= ent.entry_fill:
                rows += [blank(e, s, t, v, x, config.STATUS_INVALID_STOP_GEOMETRY) for v in variants]
                continue
            mdf_e = mdf[mdf.session_date >= ent.entry_session_date]
            sess_e = [d for d in sessions if d >= ent.entry_session_date]
            ep_stop = stops.as_ep_stop_type(price, ent.entry_fill)
            for v in variants:
                key = (str(ent.entry_timestamp), ent.entry_fill, round(price, 6), t, v)
                if key not in memo:
                    try:
                        memo[key] = P.simulate(ticker, ent, ep_stop, t, v, mdf_e, daily, sess_e,
                                               force_exit="^" in ticker)
                    except Exception as exc:  # noqa: BLE001
                        memo[key] = P.Result(status=f"ERROR: {exc}")
                r = memo[key]
                ts = r.last_sale_timestamp
                rows.append({**blank(e, s, t, v, x, r.status), "entry_date": ent.entry_session_date,
                         "adr14": stops.adr14(daily, ent.entry_session_date),
                             "entry_fill": ent.entry_fill, "stop_pct": round((1 - price / ent.entry_fill) * 100, 3),
                             "realized_R": r.realized_R, "n_sales": r.n_sales, "last_sale_reason": r.last_sale_reason,
                             "exit_date": ts.date() if hasattr(ts, "date") else ts, "holding_days": r.holding_days,
                             "max_favorable_R": r.max_favorable_R, "exit_efficiency": r.exit_efficiency})
    return rows


def summarize(trades: pd.DataFrame, monsters: set) -> pd.DataFrame:
    from .run_grid import max_dd_and_streak
    out = []
    if "expiry" not in trades:
        trades = trades.assign(expiry="box")
    for (sid, part, xp), g in trades.groupby(["strategy_id", "partial", "expiry"]):
        ok = g[g.status == "OK"].sort_values(["entry_date", "ticker"])
        r = ok.realized_R.astype(float)
        n = len(r)
        win, loss = r[r > 0], r[r <= 0]
        dd, streak = max_dd_and_streak(r)
        keys = set(zip(ok.ticker, ok.flag_no))
        mon = ok[[k in monsters for k in zip(ok.ticker, ok.flag_no)]]
        yr = ok.assign(y=ok.entry_date.astype(str).str[:4]).groupby("y").realized_R.sum()
        srt = np.sort(r.to_numpy())
        out.append({
            "strategy_id": sid, "partial": part, "expiry": xp, "trades": n,
            "no_entry": int((g.status == config.STATUS_NO_ENTRY).sum()), "data_short": int((g.status == "DATA_SHORT").sum()), "win_rate": len(win) / n if n else np.nan,
            "EV_R": r.mean() if n else np.nan,
            "profit_factor": win.sum() / abs(loss.sum()) if len(loss) and loss.sum() else np.nan,
            "total_R": r.sum(), "rate_10R": (r >= 10).mean() if n else np.nan,
            "EV_ex_10R": r[r < 10].mean() if n else np.nan,
            "EV_ex_top5pct": srt[:n - int(np.ceil(n * 0.05))].mean() if n > 20 else np.nan,
            "mon_cap5": (mon.realized_R >= 5).sum() / len(monsters) if monsters else np.nan,
            "max_dd_R": dd, "max_losing_streak": streak, "neg_years": int((yr < 0).sum()),
            "worst_year_R": yr.min() if len(yr) else np.nan,
            "median_hold": ok.holding_days.median() if n else np.nan,
            "exit_eff": ok.exit_efficiency.median() if n else np.nan,
            "n_flags": len(keys),
        })
    s = pd.DataFrame(out)
    s["calmar"] = s.total_R / s.max_dd_R.abs().replace(0, np.nan)
    return s


def main():
    from . import partials as P
    from .run_grid import _flags
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--stage", choices=["2a", "2b", "2c", "expiry", "gauntlet", "delisted", "entry", "final2", "lock"], default="2a")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--strategies", default=None,
                    help="final2: comma list entry:stop:trail, e.g. c5m:1.00adr:20ma_touch,30m:4pct_entry:20ma_touch")
    ap.add_argument("--verify", action="store_true", help="reference partials only; compare with Stage 1 trades")
    args = ap.parse_args()
    args.tag = args.tag or {"2a": "stage2a", "2b": "stage2b", "expiry": "expiry",
                            "gauntlet": f"gauntlet_slip{config.SLIPPAGE_PCT * 100:g}", "2c": "stage2c",
                            "delisted": f"delisted_slip{config.SLIPPAGE_PCT * 100:g}",
                            "entry": f"entry_test_slip{config.SLIPPAGE_PCT * 100:g}",
                            "final2": f"final2_slip{config.SLIPPAGE_PCT * 100:g}",
                            "lock": f"lock_slip{config.SLIPPAGE_PCT * 100:g}"}[args.stage]

    if args.verify:
        variants, strategies, expiries = [P.PartialCfg()], SHORTLIST, [None]
    elif args.stage == "2a":
        variants, strategies, expiries = P.stage2a_variants(), SHORTLIST, [None]
    elif args.stage == "2b":
        variants, strategies, expiries = P.stage2b_variants(), FINAL, [None]
    elif args.stage == "2c":
        variants, strategies, expiries = P.stage2c_variants(), STAGE2C, [15]
    elif args.stage == "expiry":
        variants, strategies, expiries = [P.PartialCfg()], FINAL, EXPIRIES
    elif args.stage == "final2":    # phase 2/3 redo (2026-11-23): shortlist on TV + delisted, e15, ref + s30 ladders
        s30 = next(v for v in P.stage2b_variants() if v.label == "s30_sp7.5")
        strategies = [tuple(x.split(":")) for x in args.strategies.split(",")]
        variants, expiries = [P.PartialCfg(), s30], [15]
    elif args.stage == "lock":
        b2, a2 = P.stage2b_variants(), P.stage2a_variants()
        pick = lambda vs, lab: next(v for v in vs if v.label == lab)
        variants = [P.PartialCfg(), pick(a2, "core0"), pick(a2, "core30"), pick(a2, "core70"),
                    P.PartialCfg(kind="none", label="none_core100"), pick(b2, "s30_sp7.5"), pick(a2, "start40"),
                    pick(a2, "spacing20")]
        strategies, expiries = LOCK, [15]
    elif args.stage == "entry":     # all dev flags, TV + delisted (^ get the forced-exit rule in _work)
        variants, strategies, expiries = [P.PartialCfg()], ENTRY_TEST, [15]
    else:   # finalists at the chosen 15-session expiry, ref + s30_sp7.5 ladders; slippage via HTF_SLIPPAGE
        s30 = next(v for v in P.stage2b_variants() if v.label == "s30_sp7.5")
        variants, strategies, expiries = [P.PartialCfg(), s30], FINAL, [15]
    flags = _flags(args.limit)
    if args.stage == "2c":     # same flag set as every earlier stage: delisted rows need the forced-exit rule first
        flags = flags[~flags.ticker.str.contains("^", regex=False)]
    if args.stage == "delisted":   # gauntlet config on the local-recorder (^) flags only; stack onto trades_gauntlet_slip*
        flags = flags[flags.ticker.str.contains("^", regex=False)]
    from types import SimpleNamespace
    tasks = [(r.ticker, SimpleNamespace(**r._asdict()), variants, strategies, expiries) for r in flags.itertuples()]
    tasks.sort(key=lambda x: -int(x[1].final_flag_end))
    print(f"{len(flags)} flags x {len(strategies)} strategies x {len(variants)} partials x {len(expiries)} expiries = "
          f"{len(flags) * len(strategies) * len(variants) * len(expiries):,} strategy-trades")
    from tqdm import tqdm
    rows = []
    with ProcessPoolExecutor(max_workers=args.workers) as ex:
        futs = [ex.submit(_work, t) for t in tasks]
        for fu in tqdm(as_completed(futs), total=len(futs), desc="flags"):
            rows += fu.result()
    trades = pd.DataFrame(rows)
    for c in ("entry_date", "exit_date"):
        trades[c] = trades[c].astype(str)
    print("status:", trades.status.value_counts().to_dict())

    s1 = pd.read_parquet(os.path.join(config.OUTPUTS_DIR, "trades_stage1.parquet"),
                         columns=["ticker", "flag_no", "strategy_id", "status", "realized_R"])
    if args.verify or args.stage == "expiry":   # noqa: E501
        chk = trades[trades.expiry == "box"] if args.stage == "expiry" else trades
        m = chk.merge(s1, on=["ticker", "flag_no", "strategy_id"], suffixes=("", "_s1"))
        same_status = (m.status == m.status_s1).mean()
        both = m[(m.status == "OK") & (m.status_s1 == "OK")]
        diff = (both.realized_R - both.realized_R_s1).abs()
        print(f"verify: {len(m)} rows, status match {same_status:.4%}, OK rows {len(both)}, "
              f"max |dR| {diff.max():.2e}, rows off by >1e-9: {(diff > 1e-9).sum()}")
        if (diff > 1e-9).any() or same_status < 1:
            print(m[(m.status != m.status_s1) | ((m.realized_R - m.realized_R_s1).abs() > 1e-9)].head(20).to_string())
        if args.verify:
            return

    ok1 = s1[s1.status == "OK"]
    best = ok1.groupby(["ticker", "flag_no"]).realized_R.max()
    monsters = set(best[best >= 10].index)                 # same strategy-independent set as Stage 1
    os.makedirs(config.OUTPUTS_DIR, exist_ok=True)
    tp = os.path.join(config.OUTPUTS_DIR, f"trades_{args.tag}.parquet")
    trades.to_parquet(tp, index=False)
    summ = summarize(trades, monsters)
    sp = os.path.join(config.OUTPUTS_DIR, f"strategy_summary_{args.tag}.csv")
    summ.to_csv(sp, index=False)
    print(summ.sort_values("EV_R", ascending=False).head(20).round(3).to_string(index=False))
    print(f"\ntrades: {tp}\nsummary: {sp}")


if __name__ == "__main__":
    main()
