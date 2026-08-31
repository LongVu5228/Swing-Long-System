"""
V3 unit tests: partial profit-taking + core + breakeven (Section 47-55, user's confirmed
choices -- single-sale Type-A target, 50/50 core split, breakeven enabled).
"""

from datetime import datetime, timedelta

import pandas as pd

from .. import calendar_utils, config
from ..entry import find_entry
from ..exits import add_sma10
from ..simulate_trade import simulate_v2_with_entry, simulate_v3_with_entry

D0 = calendar_utils.sessions_from(pd.Timestamp("2024-01-02").date(), 1)[0]
SESSIONS = calendar_utils.sessions_from(D0, 8)


def _bar(session_date, hhmm, o, h, l, c, v=1000):
    hh, mm = divmod(hhmm, 100)
    dt = datetime.combine(session_date, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    return {"dt_et": dt, "session_date": session_date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _to_df(bars):
    return pd.DataFrame(bars).sort_values("dt_et").reset_index(drop=True)


def _prior_days_daily_df(n_days, close, extra_row=None):
    rows = []
    base = D0 - timedelta(days=n_days + 30)
    d = base
    while len(rows) < n_days:
        if calendar_utils.is_trading_day(d):
            rows.append({"date": d, "open": close, "high": close, "low": close - 1, "close": float(close), "volume": 10000})
        d += timedelta(days=1)
    if extra_row is not None:
        rows.append(extra_row)
    return pd.DataFrame(rows)


def test_v3_target_never_reached_matches_v2():
    # Unreachable target (500%) -- the whole trade must resolve exactly as V2 would,
    # since no partial ever happens. Cross-checks V3's Phase-1-stop-wins path against
    # already-trusted V2 code rather than hand-deriving expected numbers.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))  # entry, no immediate threat
    bars.append(_bar(D0, 932, 100, 100.3, 94.0, 95.0))   # dips through a 5% stop (~95.1)
    minute_df = _to_df(bars)

    daily_df = _prior_days_daily_df(25, 90, extra_row={"date": D0, "open": 99, "high": 100.5, "low": 94.0, "close": 95.0, "volume": 50000})
    daily_sma = add_sma10(daily_df)

    entry = find_entry(minute_df, D0, SESSIONS, "1m")
    assert entry.entry_status == config.STATUS_VALID_TRADE

    v2 = simulate_v2_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                 trail_type="close_below_20ma", entry=entry, minute_df=minute_df,
                                 daily_sma=daily_sma, sessions=SESSIONS)
    v3 = simulate_v3_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                 trail_type="close_below_20ma", target_pct=5.0, core_pct=0.5,
                                 entry=entry, minute_df=minute_df, daily_sma=daily_sma, sessions=SESSIONS)

    assert v2.status == "OK" and v3.status == "OK"
    assert v3.partial_timestamp is None, "no partial should have happened"
    assert abs(v3.realized_R - v2.realized_R) < 1e-9


def test_v3_partial_then_core_exit_weighted_R():
    # Everything happens within D0 so the test doesn't need multi-day minute fixtures:
    # entry -> target hit intrabar (partial) -> core survives the rest of the day ->
    # D0's own close ends up below a deliberately inflated sma20 -> same-day core exit.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]        # OR -> trigger 100.01
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))   # entry fires here
    bars.append(_bar(D0, 932, 100.2, 103.0, 100.1, 102.5))  # target (2% ~102.11) hit here
    bars.append(_bar(D0, 933, 102, 102.5, 101.0, 102.3))    # phase 2: quiet, no stop threat
    minute_df = _to_df(bars)

    # 19 prior days at close=110 (well above D0's close) so sma20 pulls D0's own close
    # underneath it, producing a same-day close_below_20ma exit for the core.
    daily_df = _prior_days_daily_df(19, 110, extra_row={"date": D0, "open": 99, "high": 103.0, "low": 99.9, "close": 102.3, "volume": 50000})
    daily_sma = add_sma10(daily_df)

    entry = find_entry(minute_df, D0, SESSIONS, "1m")
    assert entry.entry_status == config.STATUS_VALID_TRADE

    result = simulate_v3_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                     trail_type="close_below_20ma", target_pct=0.02, core_pct=0.5,
                                     entry=entry, minute_df=minute_df, daily_sma=daily_sma, sessions=SESSIONS)

    assert result.status == "OK"
    assert result.partial_reason == "TARGET_TRADE_THROUGH"
    assert result.core_exit_reason == "SMA20_EXIT"

    entry_fill = result.entry_fill
    risk = entry_fill - result.initial_stop_price
    # partial_price/core_exit_price are already rounded to 4dp for storage, so
    # recomputing R from them re-introduces that rounding -- a slightly looser
    # tolerance than exact-precision comparisons here, not a sign of a real bug.
    partial_R = (result.partial_price - entry_fill) / risk
    core_R = (result.core_exit_price - entry_fill) / risk
    expected_R = 0.5 * partial_R + 0.5 * core_R
    assert abs(result.realized_R - expected_R) < 1e-3


def test_v3_phase2_first_bar_gap_uses_realistic_fill_not_breakeven():
    # Regression-style test for the is_continuation fix: Phase 2's first considered bar
    # GAPS below the breakeven floor. The fix must fill at the bar's own (worse) open
    # price, not silently use the breakeven floor as if this were an ambiguous
    # same-bar-as-entry situation (which it structurally isn't -- nothing "entered" on
    # this bar, the core position was already open).
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))     # entry
    bars.append(_bar(D0, 932, 100.2, 103.0, 100.1, 102.5))  # target hit
    # Phase 2's first bar opens well below the ~100.11 breakeven floor.
    bars.append(_bar(D0, 933, 99.0, 99.5, 98.0, 98.5))
    minute_df = _to_df(bars)

    daily_df = _prior_days_daily_df(25, 90, extra_row={"date": D0, "open": 99, "high": 103.0, "low": 98.0, "close": 98.5, "volume": 50000})
    daily_sma = add_sma10(daily_df)

    entry = find_entry(minute_df, D0, SESSIONS, "1m")
    result = simulate_v3_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                     trail_type="close_below_20ma", target_pct=0.02, core_pct=0.5,
                                     entry=entry, minute_df=minute_df, daily_sma=daily_sma, sessions=SESSIONS)

    assert result.status == "OK"
    assert result.core_exit_reason == "STOPPED_GAP_THROUGH", \
        "must not be mislabeled STOPPED_SAME_BAR_AS_ENTRY -- nothing 'entered' on this continuation bar"
    # The fill must reflect the bar's own (worse) open, not the breakeven floor (~100.11).
    assert result.core_exit_price < result.entry_fill * 0.995


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    if failures:
        raise SystemExit(1)
