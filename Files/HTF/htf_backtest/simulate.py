"""
Per-flag simulation of the HTF grid: HTF entry (entry.py) + HTF stop (stops.py), then EP's
tested multi-partial position management (ep_backtest.simulate_trade.simulate_multi_v3_with_entry)
for trailing stops, staged partials, breakeven, gap handling and MFE.

Reference partial setup for Stage 1 (§12): the HTF "chosen one" ladder -- 10% of the original
position at each of +20/27.5/35/42.5/50% (EP's "start20" ladder, equal depletion), 50% core,
breakeven after the first sale (built into EP's engine).

Work is hoisted like EP's run_batch: the entry search runs once per entry type and is reused
across all 13 stops x 8 trails; stops are computed once per (entry, stop).
"""

import os
from dataclasses import asdict
from datetime import datetime

import pandas as pd

from . import config, entry as htf_entry, minute_bars, stops
from ep_backtest import config as ep_config, exits  # noqa: E402
from ep_backtest.simulate_trade import simulate_multi_v3_with_entry  # noqa: E402

LADDER_NAME = "start20"
LADDER = ep_config.V3_MULTI_TARGET_LADDERS[LADDER_NAME]
SELL_STYLE, CORE_PCT = "equal_depletion", 0.5


def _d(x):
    return datetime.strptime(str(int(x)), "%Y%m%d").date()


def daily_frame(ticker: str) -> pd.DataFrame:
    """TradingView export -> EP daily schema (date as datetime.date) + sma5/10/20."""
    import quick_backtest_chosen_one as qb
    b = qb.load_bars(ticker)
    if b is None:
        return None
    df = pd.DataFrame({"date": [_d(x) for x in b.d], "open": b.open, "high": b.high, "low": b.low, "close": b.close})
    return exits.add_sma10(df)


_MANIFEST = {}


def _manifest() -> dict:
    """(ticker, start, end) -> (use, scale) from minute_bars --recheck."""
    if not _MANIFEST:
        m = pd.read_csv(config.MINUTE_MANIFEST)
        for r in m.itertuples():
            _MANIFEST[(r.ticker, pd.Timestamp(r.start).date(), pd.Timestamp(r.end).date())] = (
                getattr(r, "use", "OK"), getattr(r, "scale", 1.0))
    return _MANIFEST


def minute_frame(ticker: str, confirm, end, last_bar=None):
    """(minute bars for the cached window covering this flag, status). Windows the recheck
    classed RESCALE are multiplied onto the TradingView chart's price scale (R1, ADR and the
    MAs come from the chart); BAD / EMPTY windows return None with an explicit status."""
    s, e = minute_bars._window_bounds(confirm, end)
    if last_bar is not None and "^" in ticker:
        e = min(e, last_bar)          # delisted: the post-flag sessions stop at the last daily bar
    folder = os.path.join(config.MINUTE_BARS_DIR, ticker)
    if not os.path.isdir(folder) and "^" in ticker:
        # delisted rows charted in the local recorder: minute bars from htf_backtest.delisted_bars
        import re
        folder = os.path.join(config.DATA_DIR, "delisted_minute", re.sub(r"[^A-Za-z0-9._-]", "_", ticker))
    if not os.path.isdir(folder):
        return None, config.STATUS_MISSING_MINUTE_DATA
    for f in os.listdir(folder):
        a, b = (datetime.strptime(x, "%Y%m%d").date() for x in f.replace(".parquet", "").split("_"))
        if a <= s and b >= e:
            use, scale = _manifest().get((ticker, a, b), ("OK", 1.0))
            if use == "BAD":
                return None, config.STATUS_MINUTE_MISMATCH
            df = pd.read_parquet(os.path.join(folder, f))
            if use == "EMPTY" or not len(df):
                return None, config.STATUS_MISSING_MINUTE_DATA
            if use == "RESCALE" and pd.notna(scale):
                for c in ("open", "high", "low", "close", "vwap"):
                    df[c] = df[c] * float(scale)
            return df, "OK"
    return None, config.STATUS_MISSING_MINUTE_DATA


def strategy_id(entry_type, stop_type, trail_type) -> str:
    return f"E{entry_type.upper()}__S{stop_type.upper()}__T{trail_type.upper()}"


def run_flag(flag, daily_sma, minute_df, entry_types=None, stop_types=None, trail_types=None,
             keep_audit=False, missing_status=None) -> list:
    entry_types = entry_types or config.ENTRY_TYPES
    stop_types = stop_types or config.STOP_TYPES
    trail_types = trail_types or config.TRAIL_TYPES
    base = {"ticker": flag.ticker, "flag_no": int(flag.flag_no), "setup_confirmed": int(flag.setup_confirmed),
            "final_flag_end": int(flag.final_flag_end), "r1_price": flag.r1_price}
    rows = []

    def blank(et, st, tt, status):
        return {**base, "strategy_id": strategy_id(et, st, tt), "entry_type": et, "stop_type": st,
                "trail_type": tt, "status": status}

    if pd.isna(flag.r1_price):
        return [blank(e, s, t, config.STATUS_NO_LEVEL) for e in entry_types for s in stop_types for t in trail_types]
    if minute_df is None or daily_sma is None:
        st_ = missing_status or config.STATUS_MISSING_MINUTE_DATA
        return [blank(e, s, t, st_) for e in entry_types for s in stop_types for t in trail_types]

    sessions = sorted(minute_df.session_date.unique())
    conf, end, r1 = _d(flag.setup_confirmed), _d(max(flag.final_flag_end, flag.setup_confirmed)), float(flag.r1_price)
    # Position management depends only on (entry bar/fill, stop price, trail). When R1 sits above
    # the opening ranges, most entry types fill on the same bar at the same price, and several
    # stops land on the same price (e.g. low_10d == last_higher_low) -- simulate each distinct
    # case once (AA flag 1: 936 combos -> a few dozen distinct simulations).
    memo = {}
    for et in entry_types:
        ent = htf_entry.find_entry(et, minute_df, daily_sma, r1, conf, end)
        if ent.entry_status != ep_config.STATUS_VALID_TRADE:
            rows += [blank(et, s, t, config.STATUS_NO_ENTRY) for s in stop_types for t in trail_types]
            continue
        # EP's position management re-filters minute_df on every call and only ever reads bars
        # from the entry session on (entry_bar_index is never used downstream) -- hand it just
        # that slice so each simulation scans a fraction of the window.
        mdf_e = minute_df[minute_df.session_date >= ent.entry_session_date]
        sess_e = [s for s in sessions if s >= ent.entry_session_date]
        for st in stop_types:
            price = stops.stop_price(st, ent, daily_sma)
            if price is None or price >= ent.entry_fill:
                rows += [{**blank(et, st, t, config.STATUS_INVALID_STOP_GEOMETRY), "entry_fill": ent.entry_fill}
                         for t in trail_types]
                continue
            ep_stop = stops.as_ep_stop_type(price, ent.entry_fill)
            for tt in trail_types:
                key = (str(ent.entry_timestamp), ent.entry_fill, round(price, 6), tt)
                if key not in memo:
                    memo[key] = simulate_multi_v3_with_entry(
                        flag.ticker, conf, None, et, ep_stop, tt, LADDER, SELL_STYLE,
                        ep_config.V3_MULTI_SELL_AMOUNT_EQUAL, LADDER_NAME, CORE_PCT, ent, mdf_e, daily_sma, sess_e)
                r = memo[key]
                row = {**blank(et, st, tt, r.status), "entry_date": ent.entry_session_date,
                       "entry_time": str(ent.entry_timestamp.time()), "entry_day_offset": ent.entry_day_offset,
                       "fill_reason": ent.fill_reason, "entry_fill": ent.entry_fill, "stop_price": round(price, 4),
                       "stop_pct": round((1 - price / ent.entry_fill) * 100, 3), "realized_R": r.realized_R,
                       "n_sales": r.n_sales, "last_sale_reason": r.last_sale_reason,
                       "exit_date": (r.last_sale_timestamp.date() if hasattr(r.last_sale_timestamp, "date")
                                     else r.last_sale_timestamp),
                       "holding_days": r.holding_days, "max_favorable_R": r.max_favorable_R,
                       "exit_efficiency": r.exit_efficiency}
                if keep_audit:
                    row["audit_log"] = "\n".join(r.audit_log)
                rows.append(row)
    return rows
