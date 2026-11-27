"""
Synthetic-bar tests for the HTF-specific pieces (EP Section 68 style). Position management itself
is EP's, covered by ep_backtest/tests.

    ../../.venv/Scripts/python.exe -m pytest htf_backtest/tests -q      (from Files/HTF)
"""

from datetime import date, datetime, timedelta

import pandas as pd

from .. import config, entry as E, stops as S
from ep_backtest import exits

D1, D2, D3 = date(2024, 1, 3), date(2024, 1, 4), date(2024, 1, 5)
CONF = date(2024, 1, 2)
R1 = 100.0


def bars(day, rows):
    """rows: list of (hhmm, o, h, l, c)."""
    out = []
    for hhmm, o, h, l, c in rows:
        hh, mm = divmod(hhmm, 100)
        dt = pd.Timestamp(datetime(day.year, day.month, day.day, hh, mm)).tz_localize(config.ET)
        out.append({"dt_et": dt, "session_date": day, "open": o, "high": h, "low": l, "close": c, "volume": 1, "vwap": c})
    return out


def flat(day, start=931, n=60, px=98.0):
    t = datetime(day.year, day.month, day.day, *divmod(start, 100))
    return [{"dt_et": pd.Timestamp(t + timedelta(minutes=i)).tz_localize(config.ET), "session_date": day,
             "open": px, "high": px, "low": px, "close": px, "volume": 1, "vwap": px} for i in range(n)]


def frame(rows):
    return pd.DataFrame(rows).sort_values("dt_et").reset_index(drop=True)


def daily(closes_by_day):
    d = pd.DataFrame([{"date": k, "open": v, "high": v + 1, "low": v - 1, "close": v} for k, v in closes_by_day.items()])
    return exits.add_sma10(d)


def test_or_trigger_is_r1_when_range_is_below_it():
    # 5m range high 99 (< R1) -> trigger = R1 + tick; first fill after the range closes.
    rows = bars(D1, [(930, 98, 99, 97.5, 98)]) + flat(D1, 935, 10)
    rows += bars(D1, [(1000, 99.5, 100.2, 99.4, 100.1)])
    r = E.find_entry("5m", frame(rows), daily({D1: 100}), R1, CONF, D3)
    assert r.trigger == 100.01
    assert r.entry_timestamp.hour == 10 and r.entry_timestamp.minute == 0
    assert abs(r.entry_fill - 100.01 * (1 + config.SLIPPAGE_PCT)) < 1e-4


def test_no_fill_inside_the_opening_range():
    # A 9:33 spike through R1 sits INSIDE the 5m range: it raises the range high (trigger
    # 101.01) and can't fill itself (EP Section 16); the 10:00 bar through 101.01 fills.
    rows = bars(D1, [(930, 98, 99, 97.5, 98), (933, 98, 101, 98, 98.5)]) + flat(D1, 935, 10)
    rows += bars(D1, [(1000, 100.5, 101.5, 100.4, 101.2)])
    r = E.find_entry("5m", frame(rows), daily({D1: 101}), R1, CONF, D3)
    assert r.or_high == 101 and r.trigger == 101.01
    assert r.entry_timestamp.hour == 10 and r.entry_timestamp.minute == 0


def test_or_high_above_r1_sets_trigger():
    rows = bars(D1, [(930, 100, 103, 99.8, 102)]) + bars(D1, [(931, 102, 103.5, 101.9, 103.2)])
    r = E.find_entry("1m", frame(rows), daily({D1: 103}), R1, CONF, D3)
    assert r.trigger == 103.01 and r.entry_timestamp.minute == 31


def test_gap_through_fills_at_open_and_lod_known_only_to_entry_bar():
    rows = bars(D1, [(930, 98, 98.5, 97, 98)]) + bars(D2, [(930, 104, 104.5, 103, 104), (931, 104, 104.2, 90, 95)])
    r = E.find_entry("r1_cross", frame(rows), daily({D1: 98, D2: 95}), R1, CONF, D3)
    assert r.fill_reason == "gap_through" and r.entry_session_date == D2
    assert r.lod_known_at_entry == 103          # the later 90 low is not known at entry


def test_confirm_day_itself_is_not_an_entry_session():
    rows = bars(CONF, [(930, 101, 102, 100.5, 101.5)]) + flat(D1)
    r = E.find_entry("r1_cross", frame(rows), daily({CONF: 101.5, D1: 98}), R1, CONF, D3)
    assert r.entry_status == "NO_ENTRY"


def test_daily_entries_close_and_next_open():
    rows = flat(D1) + bars(D2, [(930, 99, 101, 98.5, 100.5)]) + bars(D3, [(930, 101, 102, 100.8, 101.5)])
    d = daily({D1: 98, D2: 100.5, D3: 101.5})
    c = E.find_entry("close_above_r1", frame(rows), d, R1, CONF, D3)
    assert c.entry_session_date == D2 and abs(c.entry_fill - 100.5 * (1 + config.SLIPPAGE_PCT)) < 1e-4
    assert c.lod_known_at_entry == 98.5
    n = E.find_entry("next_open_after_close", frame(rows), d, R1, CONF, D3)
    assert n.entry_session_date == D3 and n.lod_known_at_entry == 98.5   # signal day's low, not the open


def test_lod_stop_has_1pct_minimum_risk():
    class Ent:
        entry_fill, entry_session_date = 100.0, D2
        lod_known_at_entry = 99.95
        trigger_candle_low_known_at_entry = 99.99
    assert S.stop_price("lod_known_at_entry", Ent, daily({D1: 98})) == 99.0
    assert S.stop_price("trigger_candle_low_known_at_entry", Ent, daily({D1: 98})) == 99.0


def test_structure_stops_use_only_sessions_before_entry():
    days = pd.bdate_range("2023-12-01", periods=25).date
    lows = [95, 94, 96, 97, 93, 96, 98, 97, 99, 100, 99, 98, 99.5, 100, 101, 100.5, 101, 102, 101.5, 102,
            103, 102.5, 103, 104, 50]           # last day = entry day with a crash low (must be ignored)
    d = exits.add_sma10(pd.DataFrame({"date": days, "open": lows, "high": [x + 2 for x in lows], "low": lows,
                                      "close": [x + 1 for x in lows]}))

    class Ent:
        entry_fill, entry_session_date = 105.0, days[-1]
    assert S.stop_price("low_10d", Ent, d) == min(lows[-11:-1])
    assert S.stop_price("last_higher_low", Ent, d) == 102.5   # most recent swing low before entry


def test_stop_type_roundtrip_to_ep_percent():
    assert abs(float(S.as_ep_stop_type(95.0, 100.0).replace("pct_entry", "")) - 5.0) < 1e-9
