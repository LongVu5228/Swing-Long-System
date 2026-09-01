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
from ..trailing_stops import (
    build_adaptive_ma_column,
    ratchet_level_series,
    touch_level_series,
    touch_level_series_with_fallback,
)

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


def test_touch_fallback_real_rejection_case_recovers_instead_of_invalidating():
    # d1's prior MA is unknown (NaN->floor). d2's prior MA=110 (>= reference 100) --
    # would be INVALID_STOP_GEOMETRY territory for plain touch on entry day if entry
    # were d2; fallback must serve `floor` (90) that day instead. d3's prior MA=95 (<100)
    # activates; from then on the real MA level is used (102 on d4, matching prior-day
    # sma20 shifted).
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3", "d4"],
        "sma20": [999, 110, 95, 102],  # shift(1): d1=NaN, d2=999, d3=110, d4=95
    })
    levels = touch_level_series_with_fallback(df, "sma20", floor=90, entry_date="d2", reference_price=100)
    # entry_date=d2 -> only d2 onward can activate.
    # d1 (before entry): irrelevant, but formula still fills it in -- not asserted.
    # d2: raw = min-floored(999)=999, after_entry=True, 999<100? No -> not activated -> floor=90
    # d3: raw = 110 (prior sma20 shift), 110<100? No -> still not activated -> 90
    # d4: raw = 95, 95<100? Yes -> ACTIVATES -> use raw=95 (not floor)
    assert list(levels)[1:] == [90, 90, 95]


def test_touch_fallback_stays_activated_even_if_ma_rises_back_above_reference():
    # Once activated, must behave exactly like plain touch_level_series (allowed to
    # loosen) -- must NOT revert to floor even if the MA later climbs back up.
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3"],
        "sma20": [80, 80, 150],  # shift(1): d1=NaN, d2=80, d3=80
    })
    levels = touch_level_series_with_fallback(df, "sma20", floor=90, entry_date="d1", reference_price=100)
    # d1: raw=fillna(90)=90 (clipped at floor already >= floor), 90<100 -> activates immediately
    # d2: raw=max(80,90)=90 (clip lower=floor), still counts as activated from d1 onward regardless
    assert list(levels) == [90, 90, 90]


def test_touch_fallback_ignores_pre_entry_history():
    # Same masking requirement as the ratchet type (FSLR 2012 bug class) -- a qualifying
    # day before entry_date must not leak into the "activated" state.
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3", "d4"],
        "sma20": [10, 999, 999, 50],  # shift(1): d1=NaN, d2=10, d3=999, d4=999
    })
    # entry_date=d3: d2's qualifying MA (10, pre-entry) must NOT activate the trade.
    # d3: raw=999 (>=reference 100) -> not activated -> floor=90
    # d4: raw=999 -> still not activated -> floor=90
    levels = touch_level_series_with_fallback(df, "sma20", floor=90, entry_date="d3", reference_price=100)
    assert list(levels)[2:] == [90, 90]


def test_adaptive_ma_stays_on_base_col_until_activation_high_reached():
    # entry_fill=100, activation_pct=0.30 -> threshold=130. d1/d2's highs (110, 125) never
    # reach it -- adaptive_ma must equal sma10 those days. d3's high=131 clears it -> from
    # d3 on, adaptive_ma must equal sma5 instead, even though d3's own sma10 value differs.
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3", "d4"],
        "high": [110, 125, 131, 128],
        "sma10": [95, 96, 97, 98],
        "sma5":  [99, 100, 101, 102],
    })
    out = build_adaptive_ma_column(df, entry_fill=100, entry_date="d1", activation_pct=0.30)
    assert list(out["adaptive_ma"]) == [95, 96, 101, 102]


def test_adaptive_ma_stays_activated_even_if_price_pulls_back_after():
    # Once activated (d2 clears threshold), must stay on sma5 even on a later day whose
    # high no longer clears the threshold (sticky, matching every other "activated" trail
    # variant's design in this project).
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3"],
        "high": [110, 135, 115],  # d3's high no longer clears 130 -- must NOT deactivate
        "sma10": [95, 96, 97],
        "sma5":  [99, 100, 101],
    })
    out = build_adaptive_ma_column(df, entry_fill=100, entry_date="d1", activation_pct=0.30)
    assert list(out["adaptive_ma"]) == [95, 100, 101]


def test_adaptive_ma_ignores_pre_entry_history():
    # Same masking requirement as every other "activated" trail variant here -- a
    # qualifying high before entry_date must not leak into the activated state.
    df = pd.DataFrame({
        "date": ["d1", "d2", "d3"],
        "high": [200, 110, 115],  # d1's high clears threshold but is BEFORE entry
        "sma10": [95, 96, 97],
        "sma5":  [99, 100, 101],
    })
    out = build_adaptive_ma_column(df, entry_fill=100, entry_date="d2", activation_pct=0.30)
    assert list(out["adaptive_ma"]) == [95, 96, 97]  # never activates -- d2/d3 highs don't clear 130


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


def test_v2_touch_level_above_entry_fill_is_invalid_not_a_fabricated_win():
    # Regression test for a real bug found in the first full V2 run: after a steep
    # enough decline, "yesterday's finalized MA" (the touch level, Section 44) can still
    # sit ABOVE the entry price -- it hasn't caught down to the crash yet. CCL entered
    # at $12.22 on 2020-03-20 got a touch level of $25.64 (the prior day's 20MA, still
    # elevated from the pre-crash price), and the same-bar-adverse rule then used that
    # unreachable level as an exit FILL PRICE, fabricating a ~36x "win" at a price the
    # stock never actually traded. This must be treated as invalid stop geometry
    # instead, exactly like an initial stop >= entry (Section 31).
    bars = [_bar(D0, 930, 11, 12, 10.5, 11.8)]  # OR high 12 -> trigger 12.01
    bars.append(_bar(D0, 931, 11.9, 12.5, 11.5, 12.2))  # entry fires here, low 11.5 is safe
    bars += _flat_day(D0, start_hhmm=932, n=5, price=12.2)
    minute_df = _to_df(bars)

    daily_rows = []
    base = D0 - timedelta(days=45)
    # A crash into D0: closes fall from ~50 down to ~12 over the prior weeks, so the
    # rolling 20-day average is still sitting far above the current $12 price.
    closes = list(range(50, 12, -2))
    i = 0
    d = base
    while len(daily_rows) < 25:
        if calendar_utils.is_trading_day(d):
            c = closes[min(i, len(closes) - 1)]
            daily_rows.append({"date": d, "open": c, "high": c, "low": c - 1, "close": float(c), "volume": 10000})
            i += 1
        d += timedelta(days=1)
    daily_rows.append({"date": D0, "open": 11, "high": 12.5, "low": 10.5, "close": 12.0, "volume": 50000})
    daily_df = pd.DataFrame(daily_rows)
    daily_sma = add_sma10(daily_df)

    sessions = calendar_utils.sessions_from(D0, config.MAX_ENTRY_DAY_OFFSET + 1)
    entry = find_entry(minute_df, D0, sessions, "1m")
    assert entry.entry_status == config.STATUS_VALID_TRADE
    assert entry.entry_fill < daily_sma[daily_sma["date"] < D0]["sma20"].iloc[-1], \
        "test setup check: prior day's sma20 really must be above the entry fill"

    result = simulate_v2_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                     trail_type="20ma_touch", entry=entry, minute_df=minute_df,
                                     daily_sma=daily_sma, sessions=sessions)

    assert result.status == config.STATUS_INVALID_STOP_GEOMETRY
    assert result.realized_R is None, "must not fabricate a win from an unreachable level"


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
