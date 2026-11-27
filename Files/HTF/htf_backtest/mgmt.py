"""Step 13 (findings doc §26 C): trade management on the finalists -- re-entry after an exit + data for the earnings
hold rule. One simulation pass; every variant is scored afterwards by mgmt_report.py.

Per flag x strategy (30m hybrid OR / 1.5 ADR or 0.75 ADR / 20ma_touch / ref ladder), up to MAX_ATTEMPTS attempts:
  attempt 1 = the normal trade (orders live for 15 sessions after setup_confirmed).
  attempt k+1 = the same entry rule (fresh 30m OR each session, buy-stop at max(OR high, R1) + tick, fresh stop)
     searched from the session AFTER attempt k's final exit, through max(15-session window end, exit + 10 sessions).
     No same-day re-entry. Every attempt is recorded with sessions_after_exit and within_window, so the variants
     (re-enter only inside the original 15-session window / within 5 / within 10 sessions of the exit; after a loss
     only vs after any exit; max 2 or 3 attempts) are chosen in the report without re-simulating.
Each attempt also stores its sales [(timestamp, price, pct_of_original, reason)], stop price and entry fill, so the
earnings rules (sell all / half the close before the report, unless cushioned) are post-processed exactly.

    ../../.venv/Scripts/python.exe -m htf_backtest.mgmt [--limit N] [--workers 8]   # -> trades_mgmt_slip0.1.parquet
"""
import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed

import pandas as pd

from . import config

STRATS = [("30m", "1.50adr", "20ma_touch"), ("30m", "0.75adr", "20ma_touch")]
MAX_ATTEMPTS = 3
WINDOW = 15
REENTRY_MAX_SESSIONS = 10


def _nth_session_after(d, n):
    from ep_backtest import calendar_utils
    return calendar_utils.sessions_from(d, n + 1)[-1]


def _sessions_between(a, b):
    from ep_backtest import calendar_utils
    td = calendar_utils.TRADING_DAYS
    return int(((td.date > a) & (td.date <= b)).sum())


def _work(args):
    from . import entry as htf_entry, partials as P, simulate as S, stops
    from ep_backtest import config as ep_config
    ticker, f = args
    base = {"ticker": ticker, "flag_no": int(f.flag_no), "setup_confirmed": int(f.setup_confirmed), "r1_price": f.r1_price}
    daily = S.daily_frame(ticker)
    mdf = None
    if daily is not None and pd.notna(f.r1_price):
        mdf, _ = S.minute_frame(ticker, S._d(f.setup_confirmed), S._d(max(f.final_flag_end, f.setup_confirmed)),
                                last_bar=daily.date.max())
    if mdf is None:
        return []
    conf = S._d(f.setup_confirmed)
    win_end = _nth_session_after(conf, WINDOW - 1)        # same as run_stage2._expiry_end(conf, 15)
    sessions = sorted(mdf.session_date.unique())
    covered = sessions[-1]
    dhigh = daily.set_index("date").high
    r1 = float(f.r1_price)
    cfg = P.PartialCfg()
    rows = []
    for e, s, t in STRATS:
        sid = S.strategy_id(e, s, t)
        start, prev_exit = conf, None
        for k in range(1, MAX_ATTEMPTS + 1):
            end = win_end if k == 1 else max(win_end, _nth_session_after(prev_exit, REENTRY_MAX_SESSIONS))
            row = {**base, "strategy_id": sid, "attempt": k}
            ent = htf_entry.find_entry(e, mdf, daily, r1, start, end)
            if ent.entry_status != ep_config.STATUS_VALID_TRADE:
                gap = dhigh[(dhigh.index > covered) & (dhigh.index <= end) & (dhigh.index > start)]
                if end > covered and (gap > r1).any():
                    # minute data ends before the window: R1 traded through later on daily bars -> unknown outcome.
                    # Record the earliest possible trigger day so the report can tell which variants it touches.
                    d0 = gap[gap > r1].index[0]
                    rows.append({**row, "status": "DATA_SHORT", "entry_date": d0, "within_window": d0 <= win_end,
                                 "sessions_after_prev_exit": None if prev_exit is None else _sessions_between(prev_exit, d0)})
                break
            price = stops.stop_price(s, ent, daily)
            if price is None or price >= ent.entry_fill:
                rows.append({**row, "status": config.STATUS_INVALID_STOP_GEOMETRY})
                break
            mdf_e = mdf[mdf.session_date >= ent.entry_session_date]
            sess_e = [d for d in sessions if d >= ent.entry_session_date]
            try:
                r = P.simulate(ticker, ent, stops.as_ep_stop_type(price, ent.entry_fill), t, cfg, mdf_e, daily, sess_e,
                               force_exit="^" in ticker)
            except Exception as exc:  # noqa: BLE001
                rows.append({**row, "status": f"ERROR: {exc}"})
                break
            ts = r.last_sale_timestamp
            exit_d = ts.date() if hasattr(ts, "date") else ts
            rows.append({**row, "status": r.status, "entry_date": ent.entry_session_date, "entry_fill": ent.entry_fill,
                         "stop_price": price, "realized_R": r.realized_R, "last_sale_reason": r.last_sale_reason,
                         "exit_date": exit_d, "max_favorable_R": r.max_favorable_R,
                         "sessions_after_prev_exit": None if prev_exit is None else _sessions_between(prev_exit, ent.entry_session_date),
                         "within_window": ent.entry_session_date <= win_end,
                         "sales": json.dumps([[str(x.timestamp), x.price, x.pct_of_original, x.reason] for x in r.sales])})
            if r.status != "OK" or exit_d is None:
                break
            start = prev_exit = exit_d if not hasattr(exit_d, "date") else exit_d
    return rows


def main():
    from .run_grid import _flags
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=8)
    a = ap.parse_args()
    flags = _flags(a.limit)
    from types import SimpleNamespace
    tasks = [(r.ticker, SimpleNamespace(**r._asdict())) for r in flags.itertuples()]
    tasks.sort(key=lambda x: -int(x[1].final_flag_end))
    print(f"{len(tasks)} flags x {len(STRATS)} strategies x up to {MAX_ATTEMPTS} attempts")
    from tqdm import tqdm
    rows = []
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        futs = [ex.submit(_work, t) for t in tasks]
        for fu in tqdm(as_completed(futs), total=len(futs), desc="flags"):
            rows += fu.result()
    d = pd.DataFrame(rows)
    for c in ("entry_date", "exit_date"):
        d[c] = d[c].astype(str)
    sample = os.environ.get("HTF_SAMPLE", "dev")
    tag = f"mgmt{'' if sample == 'dev' else '_' + sample}_slip{config.SLIPPAGE_PCT * 100:g}"
    p = os.path.join(config.OUTPUTS_DIR, f"trades_{tag}.parquet")
    d.to_parquet(p, index=False)
    print(d.groupby(["strategy_id", "attempt"]).status.value_counts().unstack(fill_value=0).to_string())
    print(f"saved {p}")


if __name__ == "__main__":
    main()
