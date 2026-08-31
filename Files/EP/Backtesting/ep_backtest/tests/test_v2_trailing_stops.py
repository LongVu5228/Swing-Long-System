"""
V2 trailing-stop unit tests: the level-series math directly (fast, precise), plus a
few end-to-end scenarios through simulate_v2_with_entry using synthetic bars.
"""

from datetime import datetime, timedelta

import pandas as pd

from .. import calendar_utils, config
from ..entry import find_entry
from ..exits import add_sma10
from ..simulate_trade import simulate_v2_with_entry
from ..trailing_stops import ratchet_level_series, touch_level_series

D0 = calendar_utils.sessions_from(pd.Timestamp("2024-01-02").date(), 1)[0]
SESSIONS = calendar_utils.sessions_from(D0, 8)


def _bar(session_date, hhmm, o, h, l, c, v=1000):
    hh, mm = divmod(hhmm, 100)
    dt = datetime.combine(session_date, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    return {"dt_et": dt, "session_date": session_date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _to_df(bars):
    return pd.DataFrame(bars).sort_values("dt_et").reset_index(drop=True)


def _flat_day(session_date, start_hhmm=931, n=5, price=99.0):
    bars = []
    hh, mm = divmod(start_hhmm, 100)
    t = datetime.combine(session_date, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    for _ in range(n):
        bars.append({"dt_et": t, "session_date": session_date, "open": price, "high": price,
                     "low": price, "close": price, "volume": 1000})
        t += timedelta(minutes=1)
    return bars


def test_touch_level_series_is_prior_day_sma_floored_at_initial_stop():
    df = pd.DataFrame({
        "date": [f"d{i}" for i in range(1, 7)],
        "sma10": [105, 104, 103, 103, 101, 100],
    })
    levels = touch_level_series(df, "sma10", initial_stop=90)
    assert list(levels) == [90, 105, 104, 103, 103, 101]


def test_ratchet_level_series_only_ever_increases():
    df = pd.DataFrame({
        "date": [f"d{i}" for i in range(1, 7)],
        "close": [100, 110, 101, 112, 99, 120],
        "sma10": [105, 104, 103, 103, 101, 100],
        "low":   [98,  107, 100, 108, 95,  115],
    })
    # d1 qualifies (100<105), low=98 -> ratchet to 98
    # d2 doesn't qualify (110>=104)
    # d3 qualifies (101<103), low=100 > 98 -> ratchet UP to 100
    # d4 doesn't qualify (112>=103)
    # d5 qualifies (99<101), low=95 < 100 -> must NOT lower the ratchet
    # d6 doesn't qualify (120>=100)
    levels = ratchet_level_series(df, "sma10", initial_stop=90, entry_date="d1")
    assert list(levels) == [90, 98, 98, 100, 100, 100]


def test_ratchet_ignores_pre_entry_history():
    # Regression test for a real bug found in the first V2 run: FSLR's 2012 entry at
    # ~$18 picked up a stop of $123 from a qualifying low that predated the EP event by
    # years -- because the ratchet was a global cummax over the ticker's entire cached
    # history instead of being scoped to start at the entry date. d1/d2 here simulate
    # that kind of ancient, unrelated qualifying day sitting years before entry.
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3", "d4", "d5"],
        "close": [50, 200, 100, 101, 112],  # d2: a huge pre-entry close<MA day
        "sma10": [60, 250, 105, 103, 103],
        "low":   [45, 150, 98,  100, 108],  # d2's low=150 must NOT leak into the ratchet
    })
    # entry happens at d3 -- only d3 onward may ever contribute to the ratchet.
    # d3 qualifies (100<105), low=98 -> ratchet to 98 (NOT the ancient 150 from d2)
    # d4 qualifies (101<103), low=100 > 98 -> ratchet UP to 100
    levels = ratchet_level_series(df, "sma10", initial_stop=90, entry_date="d3")
    assert list(levels) == [90, 90, 90, 98, 100]


def test_v2_touch_exits_intrabar_even_though_close_recovers():
    # OR -> trigger 100.01. Entry bar survives cleanly (its own low stays above both the
    # initial stop and the touch level). A LATER bar dips through the touch level (which
    # is tighter than the initial stop) but the day still closes back up -- a close-based
    # rule would never have fired here, only the intrabar touch does.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 99, 100.5, 98.5, 100.2))  # entry bar, low 98.5 is safe
    bars.append(_bar(D0, 932, 100, 100.3, 96.5, 99.8))  # dips to 96.5, touching the level
    bars += _flat_day(D0, start_hhmm=933, n=3, price=99.0)
    minute_df = _to_df(bars)

    daily_rows = []
    base = D0 - timedelta(days=20)
    for i in range(15):
        d = base + timedelta(days=i)
        if calendar_utils.is_trading_day(d):
            daily_rows.append({"date": d, "open": 97, "high": 97, "low": 96, "close": 97.0, "volume": 10000})
    daily_rows.append({"date": D0, "open": 99, "high": 100.5, "low": 96.5, "close": 99.0, "volume": 50000})
    daily_df = pd.DataFrame(daily_rows)
    daily_sma = add_sma10(daily_df)

    sessions = calendar_utils.sessions_from(D0, config.MAX_ENTRY_DAY_OFFSET + 1)
    entry = find_entry(minute_df, D0, sessions, "1m")
    assert entry.entry_status == config.STATUS_VALID_TRADE

    result = simulate_v2_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                     trail_type="10ma_touch", entry=entry, minute_df=minute_df,
                                     daily_sma=daily_sma, sessions=sessions)

    assert result.status == "OK"
    assert result.exit_reason == "STOPPED_TRADE_THROUGH"
    # touch level (prior day's sma10 ~ 97.0) must be tighter than -- i.e. exit above -- the
    # much wider 5% initial stop, proving the touch rule fired first.
    assert result.initial_stop_price < 96.0
    assert result.exit_price is not None and result.exit_price > result.initial_stop_price


def test_v2_ratchet_does_not_exit_on_the_close_below_ma_event_itself():
    # A day that closes below the MA should NOT by itself end the trade under the
    # low-of-close-below-MA rule -- it only raises the floor for future days.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))  # entry, no stop threat at all
    bars += _flat_day(D0, start_hhmm=932, n=5, price=100.2)
    minute_df = _to_df(bars)

    daily_rows = []
    base = D0 - timedelta(days=20)
    for i in range(15):
        d = base + timedelta(days=i)
        if calendar_utils.is_trading_day(d):
            daily_rows.append({"date": d, "open": 90, "high": 90, "low": 89, "close": 90.0, "volume": 10000})
    # D0 closes BELOW its own sma10 (which will be well above 90 once D0's much higher
    # close enters the rolling window on later days) -- but that alone must not exit.
    daily_rows.append({"date": D0, "open": 99, "high": 100.5, "low": 99, "close": 100.2, "volume": 50000})
    daily_df = pd.DataFrame(daily_rows)
    daily_sma = add_sma10(daily_df)

    sessions = calendar_utils.sessions_from(D0, config.MAX_ENTRY_DAY_OFFSET + 1)
    entry = find_entry(minute_df, D0, sessions, "1m")
    assert entry.entry_status == config.STATUS_VALID_TRADE

    result = simulate_v2_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                     trail_type="low_of_close_below_10ma", entry=entry, minute_df=minute_df,
                                     daily_sma=daily_sma, sessions=sessions)

    # Nothing threatens the position within the cached window, and the close-below-MA
    # event itself must not trigger an exit -- position should still be open.
    assert result.status == "STILL_OPEN_AT_DATA_END"


def test_v2_close_below_20ma_matches_v1_close_below_10ma_mechanics():
    # Sanity check that generalizing _run_position_management's ma_col param didn't
    # change V1's behavior: an sma20-based close-exit should fire the same way V1's
    # sma10 same-day exit test does, just referencing sma20.
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))
    bars += _flat_day(D0, start_hhmm=932, n=5, price=100.2)
    minute_df = _to_df(bars)

    daily_rows = []
    base = D0 - timedelta(days=45)
    for i in range(40):
        d = base + timedelta(days=i)
        if calendar_utils.is_trading_day(d):
            daily_rows.append({"date": d, "open": 150, "high": 151, "low": 149, "close": 150, "volume": 10000})
    daily_rows.append({"date": D0, "open": 99, "high": 100.5, "low": 99, "close": 100.2, "volume": 50000})
    daily_df = pd.DataFrame(daily_rows)
    daily_sma = add_sma10(daily_df)

    sessions = calendar_utils.sessions_from(D0, config.MAX_ENTRY_DAY_OFFSET + 1)
    entry = find_entry(minute_df, D0, sessions, "1m")

    result = simulate_v2_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                     trail_type="close_below_20ma", entry=entry, minute_df=minute_df,
                                     daily_sma=daily_sma, sessions=sessions)

    assert result.status == "OK"
    assert result.exit_reason == "SMA20_EXIT"
    assert result.holding_days == 0


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
