"""
Synthetic tests for the Stage 2 partial engine (partials.py) -- the new modes only; the
reference ladder is checked trade-for-trade against Stage 1 by run_stage2 --verify.
"""

from datetime import date, datetime, timedelta

import pandas as pd

from .. import config, partials as P
from ep_backtest import exits
from ep_backtest.entry import EntryResult

DAYS = list(pd.bdate_range("2024-01-02", periods=40).date)


def minute(days_prices):
    """days_prices: {day: [(o,h,l,c), ...]} one bar per minute from 9:30."""
    rows = []
    for d, bars in days_prices.items():
        for i, (o, h, l, c) in enumerate(bars):
            ts = pd.Timestamp(datetime(d.year, d.month, d.day, 9, 30) + timedelta(minutes=i)).tz_localize(config.ET)
            rows.append({"dt_et": ts, "session_date": d, "open": o, "high": h, "low": l, "close": c,
                         "volume": 1, "vwap": c})
    return pd.DataFrame(rows)


def daily(closes, lows=None):
    lows = lows or [c - 0.5 for c in closes]
    return exits.add_sma10(pd.DataFrame({"date": DAYS[:len(closes)], "open": closes, "high": [c + 0.5 for c in closes],
                                         "low": lows, "close": closes}))


def entry_on(day, fill=100.0):
    return EntryResult(entry_status="VALID_TRADE", or_high=99, trigger=100, entry_timestamp=pd.Timestamp(
        datetime(day.year, day.month, day.day, 9, 30)).tz_localize(config.ET), entry_day_offset=0,
        entry_session_date=day, entry_fill=fill, fill_reason="normal_trade_through", entry_bar_index=0,
        lod_known_at_entry=99, trigger_candle_low_known_at_entry=99)


def _setup(closes):
    # 25 sessions of history at 80 (MAs well below), entry on session 25, then `closes`.
    hist = [80.0] * 25
    d = daily(hist + closes)
    ed = DAYS[25]
    m = minute({DAYS[25 + i]: [(c, c + 0.2, c - 0.2, c)] for i, c in enumerate(closes)})
    return d, ed, m, [DAYS[25 + i] for i in range(len(closes))]


def test_none_rides_whole_position_to_trail():
    closes = [100, 105, 110, 115, 120]
    d, ed, m, sess = _setup(closes)
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(kind="none"), sess, [])
    assert r.status == "STILL_OPEN_AT_DATA_END" and not r.sales      # never stopped, nothing sold


def test_time_sales_every_2_sessions_at_close():
    closes = [100, 104, 108, 112, 116, 120, 124]
    d, ed, m, sess = _setup(closes)
    cfg = P.PartialCfg(kind="time", every_n=2, n_time_sales=2, amount_mode="fixed", amount=0.25, core_pct=0.5)
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", cfg, sess, [])
    sold = [(s.timestamp.date(), round(s.price / (1 - config.SLIPPAGE_PCT), 4), s.pct_of_original) for s in r.sales]
    assert sold == [(sess[2], 108.0, 0.25), (sess[4], 116.0, 0.25)]   # 2nd and 4th session after entry


def test_fixed_amount_leaves_noncore_riding():
    closes = [100, 121, 121, 121]       # crosses only the first +20% rung
    d, ed, m, sess = _setup(closes)
    cfg = P.PartialCfg(amount_mode="fixed", amount=0.025)
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", cfg, sess, [])
    assert abs(r.sales[0].pct_of_original - 0.025) < 1e-12


def test_breakeven_off_keeps_initial_floor():
    # +20% rung hit, then price falls back to 99 (below entry, above the 95 stop): with breakeven
    # the 100 floor stops it out; without, the position is still open.
    closes = [100, 121, 99, 99]
    d, ed, m, sess = _setup(closes)
    on = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(), sess, [])
    off = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(breakeven=False), sess, [])
    assert on.status == "OK" and on.sales[-1].reason.startswith("STOPPED")
    assert off.status == "STILL_OPEN_AT_DATA_END"


def test_time_sale_below_entry_does_not_arm_breakeven():
    closes = [100, 98, 98, 98]
    d, ed, m, sess = _setup(closes)
    cfg = P.PartialCfg(kind="time", every_n=1, n_time_sales=1)
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", cfg, sess, [])
    assert r.status != "INVALID_STOP_GEOMETRY"


def test_R_targets_scale_with_risk():
    closes = [100, 104, 104, 104]               # risk 5 (stop 95): +3R = 115 never hit, +0.5R = 102.5 hit
    d, ed, m, sess = _setup(closes)
    hit = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(targets=(0.5,), target_unit="R"), sess, [])
    miss = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(targets=(3,), target_unit="R"), sess, [])
    # the bar opens at 104, above the 102.5 target -> gap-through fill at the open (EP rule)
    assert hit.sales and hit.sales[0].reason.startswith("TARGET_GAP_THROUGH")
    assert abs(hit.sales[0].price / (1 - config.SLIPPAGE_PCT) - 104) < 1e-9
    assert not miss.sales


def test_adr_targets_use_entry_adr():
    closes = [100, 106, 106, 106]               # ADR 5%: +1 ADR = 105 hit, +2 ADR = 110 not
    d, ed, m, sess = _setup(closes)
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma",
                       P.PartialCfg(targets=(1, 2), target_unit="adr"), sess, [], adr=0.05)
    assert len(r.sales) == 1 and abs(r.sales[0].price / (1 - config.SLIPPAGE_PCT) - 106) < 1e-9   # gap over 105
    none = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(targets=(1,), target_unit="adr"), sess, [])
    assert none.status == "NO_ADR"


def test_extension_sells_at_close_when_far_above_sma10():
    closes = [100, 130, 160, 160]               # history at 80 -> SMA10 lags far below
    d, ed, m, sess = _setup(closes)
    cfg = P.PartialCfg(kind="extension", targets=(2,))
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", cfg, sess, [], adr=0.05)
    first = r.sales[0]
    assert first.reason.startswith("EXTENSION_SALE_CLOSE") and first.timestamp.date() == sess[1]


def test_bollinger_extension_uses_sigma_of_sma20():
    closes = [100, 130, 160, 160]
    d, ed, m, sess = _setup(closes)
    r = P.run_partials(m, d, entry_on(ed), 95.0, "close_below_20ma", P.PartialCfg(kind="extension", ext_basis="bb20", targets=(2,)),
                       sess, [], adr=0.05)
    assert r.sales[0].reason.startswith("EXTENSION_SALE_CLOSE")
