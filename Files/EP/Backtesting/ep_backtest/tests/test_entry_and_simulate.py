"""
Section 68 toy-case unit tests, run against synthetic bars (no API calls). Labels
below match the frozen spec's lettering (A, B, C, D, E, G, H, I).

Run with:
    python -m pytest ep_backtest/tests -q
from the Files/EP/Backtesting directory (with the project venv active), or:
    python -m ep_backtest.tests.test_entry_and_simulate
to run standalone without pytest.
"""

from datetime import datetime, timedelta

import pandas as pd

from .. import calendar_utils, config
from ..entry import find_entry
from ..exits import add_sma10
from ..simulate_trade import simulate_trade_from_data

D0 = calendar_utils.sessions_from(pd.Timestamp("2024-01-02").date(), 1)[0]
SESSIONS = calendar_utils.sessions_from(D0, 8)


def _bar(session_date, hhmm, o, h, l, c, v=1000):
    hh, mm = divmod(hhmm, 100)
    dt = datetime.combine(session_date, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    return {"dt_et": dt, "session_date": session_date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _flat_day(session_date, start_hhmm=931, n=389, price=99.0):
    """A day of quiet bars that never approach the trigger, one per minute from start_hhmm."""
    bars = []
    hh, mm = divmod(start_hhmm, 100)
    t = datetime.combine(session_date, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    for _ in range(n):
        bars.append({"dt_et": t, "session_date": session_date, "open": price, "high": price,
                     "low": price, "close": price, "volume": 1000})
        t += timedelta(minutes=1)
    return bars


def _to_df(bars):
    return pd.DataFrame(bars).sort_values("dt_et").reset_index(drop=True)


def test_a_earliest_1m_entry_and_no_early_fill():
    # OR bucket (9:30-9:31) high = 100 -> trigger = 100.01.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    # 9:31 bar stays below trigger -> must not fire.
    bars.append(_bar(D0, 931, 99, 99, 98, 99))
    # 9:32 bar finally crosses -> earliest possible entry.
    bars.append(_bar(D0, 932, 99, 100.02, 98.5, 100))
    bars += _flat_day(D0, start_hhmm=933, n=5)
    df = _to_df(bars)

    result = find_entry(df, D0, SESSIONS, "1m")
    assert result.entry_status == config.STATUS_VALID_TRADE
    assert result.entry_timestamp.hour == 9 and result.entry_timestamp.minute == 32
    assert abs(result.trigger - 100.01) < 1e-9


def test_b_gap_through_defining_candle_close_at_high():
    # OR bucket (9:30-9:35, 5m) high = 100 exactly at the last bar's close -> trigger 100.01.
    bars = [_bar(D0, 930, 99, 99.5, 98, 99), _bar(D0, 931, 99, 99.5, 98, 99),
            _bar(D0, 932, 99, 99.5, 98, 99), _bar(D0, 933, 99, 99.5, 98, 99),
            _bar(D0, 934, 99.5, 100, 99, 100)]
    # Next bar (9:35) opens well above the trigger -> gap-through fill at that open.
    bars.append(_bar(D0, 935, 105, 106, 104, 105))
    df = _to_df(bars)

    result = find_entry(df, D0, SESSIONS, "5m")
    assert result.fill_reason == "gap_through"
    assert result.entry_fill == round(105 * (1 + config.SLIPPAGE_PCT), 4)


def test_c_delayed_entry_on_dplus3():
    bars = [_bar(D0, 930, 99, 100, 98, 100)]  # OR high 100 -> trigger 100.01
    bars += _flat_day(D0, start_hhmm=931, n=5)
    d1, d2, d3 = SESSIONS[1], SESSIONS[2], SESSIONS[3]
    bars += _flat_day(d1, n=5)
    bars += _flat_day(d2, n=5)
    bars += _flat_day(d3, start_hhmm=930, n=3)
    bars.append(_bar(d3, 933, 99, 100.05, 98, 100))  # finally fires on D+3
    df = _to_df(bars)

    result = find_entry(df, D0, SESSIONS, "1m")
    assert result.entry_status == config.STATUS_VALID_TRADE
    assert result.entry_day_offset == 3
    assert result.entry_session_date == d3


def test_d_no_entry_through_dplus7():
    bars = [_bar(D0, 930, 99, 100, 98, 100)]  # OR high 100 -> trigger 100.01
    for s in SESSIONS:
        bars += _flat_day(s, n=10)
    df = _to_df(bars)

    result = find_entry(df, D0, SESSIONS, "1m")
    assert result.entry_status == config.STATUS_NO_ENTRY


def test_e_lod_known_at_entry_ignores_future_low():
    # Trigger fires at 9:33; price dips to 95 known-so-far, then LATER (9:35) makes a
    # much lower low of 80 -- the stop must use 95, not 80.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]  # OR -> trigger 100.01
    bars.append(_bar(D0, 931, 98, 99, 95, 96))     # known low so far = 95
    bars.append(_bar(D0, 932, 96, 99, 96, 98))
    bars.append(_bar(D0, 933, 98, 100.05, 97, 100))  # entry fires here
    bars.append(_bar(D0, 934, 100, 101, 80, 100))    # future low of 80 -- must be ignored

    df = _to_df(bars)
    result = find_entry(df, D0, SESSIONS, "1m")
    assert result.entry_status == config.STATUS_VALID_TRADE
    assert result.lod_known_at_entry == 95, "must not see the 80 low that comes after entry"


def test_g_same_minute_entry_and_stop_uses_adverse_assumption():
    # Entry bar's own low is far enough below a 1%-from-entry stop that the same bar
    # both triggers the entry AND would trigger the stop -- must assume adverse (stopped).
    bars = [_bar(D0, 930, 99, 100, 98, 100)]  # OR -> trigger 100.01
    # Entry bar: crosses 100.01 on the high, but its low (90) is also below where a
    # tight 1% stop will land (~ just under 101 -- entry fill w/ 1% slippage ~101.01,
    # stop = entry_fill*0.99 ~ 100.0, still above 90).
    bars.append(_bar(D0, 931, 95, 100.5, 90, 95))
    df = _to_df(bars)

    daily_rows = []
    base = D0 - timedelta(days=20)
    for i in range(15):
        d = base + timedelta(days=i)
        if calendar_utils.is_trading_day(d):
            daily_rows.append({"date": d, "open": 99, "high": 101, "low": 98, "close": 99.5, "volume": 10000})
    daily_rows.append({"date": D0, "open": 99, "high": 100.6, "low": 90, "close": 95, "volume": 50000})
    daily_df = pd.DataFrame(daily_rows)

    result = simulate_trade_from_data("TEST", D0, adr14=0.06, entry_type="1m", stop_type="1pct_entry",
                                       minute_df=df, daily_df=daily_df)
    assert result.status == "OK"
    assert result.exit_reason == "STOPPED_SAME_BAR_AS_ENTRY"
    assert result.entry_timestamp == result.exit_timestamp


def test_i_same_day_10sma_exit_allowed():
    bars = [_bar(D0, 930, 99, 100, 98, 100)]  # OR -> trigger 100.01
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))  # entry fires, no stop touch
    bars += _flat_day(D0, start_hhmm=932, n=5, price=100.2)
    df = _to_df(bars)

    daily_rows = []
    base = D0 - timedelta(days=20)
    for i in range(15):
        d = base + timedelta(days=i)
        if calendar_utils.is_trading_day(d):
            daily_rows.append({"date": d, "open": 150, "high": 151, "low": 149, "close": 150, "volume": 10000})
    # D0 closes far below the inflated 10SMA -- should exit same day at that close.
    daily_rows.append({"date": D0, "open": 99, "high": 100.5, "low": 99, "close": 100.2, "volume": 50000})
    daily_df = pd.DataFrame(daily_rows)

    result = simulate_trade_from_data("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                       minute_df=df, daily_df=daily_df)
    assert result.status == "OK"
    assert result.exit_reason == "SMA10_EXIT"
    assert result.holding_days == 0


def test_j_insufficient_10sma_history_is_ineligible():
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))
    df = _to_df(bars)

    daily_df = pd.DataFrame([
        {"date": D0 - timedelta(days=2), "open": 99, "high": 101, "low": 98, "close": 99.5, "volume": 10000},
        {"date": D0, "open": 99, "high": 100.5, "low": 99, "close": 100.2, "volume": 50000},
    ])

    result = simulate_trade_from_data("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                       minute_df=df, daily_df=daily_df)
    assert result.status == config.STATUS_INELIGIBLE_NO_10SMA


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
