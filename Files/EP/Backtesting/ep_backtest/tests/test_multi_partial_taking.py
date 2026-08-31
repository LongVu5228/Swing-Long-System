"""
V3b (multi-target staged partials) unit tests -- equal_depletion, exponential_remaining,
and Section 54's gap-through-multiple-targets-at-once case.
"""

from datetime import datetime, timedelta

import pandas as pd

from .. import calendar_utils, config
from ..entry import EntryResult
from ..entry import find_entry
from ..exits import add_sma10
from ..multi_partial_taking import _downside_scan, run_multi_partial_position_management
from ..simulate_trade import simulate_multi_v3_with_entry, simulate_v2_with_entry

D0 = calendar_utils.sessions_from(pd.Timestamp("2024-01-02").date(), 1)[0]
SESSIONS = calendar_utils.sessions_from(D0, 8)


def _bar(session_date, hhmm, o, h, l, c, v=1000):
    hh, mm = divmod(hhmm, 100)
    dt = datetime.combine(session_date, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    return {"dt_et": dt, "session_date": session_date, "open": o, "high": h, "low": l, "close": c, "volume": v}


def _to_df(bars):
    return pd.DataFrame(bars).sort_values("dt_et").reset_index(drop=True)


def _entry_and_prior_daily():
    bars = [_bar(D0, 930, 99, 100, 98, 100)]
    bars.append(_bar(D0, 931, 100, 100.5, 99.9, 100.2))  # entry fires, clean
    bars += [_bar(D0, 930 + m, 100.2, 100.4, 100.0, 100.2) for m in range(1, 5)]
    minute_df = _to_df(bars)

    prior_rows = []
    base = D0 - timedelta(days=45)
    d = base
    while len(prior_rows) < 25:
        if calendar_utils.is_trading_day(d):
            prior_rows.append({"date": d, "open": 90, "high": 90, "low": 89, "close": 90.0, "volume": 10000})
        d += timedelta(days=1)
    prior_rows.append({"date": D0, "open": 99, "high": 100.5, "low": 99.9, "close": 100.2, "volume": 50000})

    entry = find_entry(minute_df, D0, SESSIONS, "1m")
    assert entry.entry_status == config.STATUS_VALID_TRADE
    return minute_df, prior_rows, entry


def _daily_row(day, o, h, l, c):
    return {"date": day, "open": o, "high": h, "low": l, "close": c, "volume": 50000}


def _future_days(n):
    days = []
    d = SESSIONS[-1] + timedelta(days=1)
    while len(days) < n:
        if calendar_utils.is_trading_day(d):
            days.append(d)
        d += timedelta(days=1)
    return days


def _prior_days(n):
    days = []
    d = D0 - timedelta(days=1)
    while len(days) < n:
        if calendar_utils.is_trading_day(d):
            days.append(d)
        d -= timedelta(days=1)
    return sorted(days)


def test_equal_depletion_five_targets_with_a_double_gap_then_core_exit():
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    ef = entry.entry_fill
    targets = [round(ef * (1 + p), 4) for p in config.V3_MULTI_TARGET_PCTS]  # +10/20/30/40/50%

    days = _future_days(5)
    rows = list(prior_rows)
    # Day A: crosses target[0] only.
    rows.append(_daily_row(days[0], targets[0] - 1, targets[0] + 0.5, targets[0] - 2, targets[0]))
    # Day B: crosses target[1] only.
    rows.append(_daily_row(days[1], targets[1] - 1, targets[1] + 0.5, targets[1] - 2, targets[1]))
    # Day C: GAPS straight through target[2] AND target[3] at once (opens above both).
    gap_price = targets[3] + 2.0
    rows.append(_daily_row(days[2], gap_price, gap_price + 1, gap_price - 1, gap_price))
    # Day D: crosses target[4] (the last one) -> non-core should now be fully depleted.
    rows.append(_daily_row(days[3], targets[4] - 1, targets[4] + 0.5, targets[4] - 2, targets[4]))
    # Day E: a hard pullback well below breakeven closes out the remaining core.
    rows.append(_daily_row(days[4], ef - 5, ef - 4, ef - 6, ef - 5))

    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="equal_depletion",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EQUAL, target_ladder="early_start", core_pct=0.5, entry=entry, minute_df=minute_df,
        daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "OK"
    # 4 target-crossing EVENTS (one of them a simultaneous double-gap, recorded as 2
    # separate Sale entries sharing a timestamp/price) + 1 final core sale = 6 records.
    assert result.n_sales == 6
    assert result.last_sale_pct is not None and abs(result.last_sale_pct - 0.5) < 1e-6, \
        "the core (50%) must be exactly what's left for the final sale"
    # A clearly positive winner overall: 40% of the position sold at big gains (110-150),
    # even though the final 50% core sale landed below breakeven (a modest loss on that
    # slice) and pulls the weighted average down substantially.
    assert result.realized_R > 2.0


def test_exit_efficiency_reflects_giveback_after_the_final_sale():
    # Entry -> target hit -> price pushes to a HIGHER peak than any sale actually
    # captured -> pulls back and closes the core out below that peak. max_favorable_R
    # must reflect the true peak (not any individual sale price), and exit_efficiency
    # must be meaningfully below 1.0 since real profit was given back before the exit.
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    ef = entry.entry_fill
    targets = [round(ef * (1 + p), 4) for p in config.V3_MULTI_TARGET_PCTS]

    days = _future_days(2)
    rows = list(prior_rows)
    # Day A: crosses target[0], but ALSO prints a much higher high intraday (the peak)
    # that nothing ever sells at.
    peak_price = targets[0] + 20.0
    rows.append(_daily_row(days[0], targets[0] - 1, peak_price, targets[0] - 2, targets[0]))
    # Day B: hard pullback closes out everything else well below that peak.
    rows.append(_daily_row(days[1], ef - 5, ef - 4, ef - 6, ef - 5))

    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="equal_depletion",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EQUAL, target_ladder="early_start", core_pct=0.5, entry=entry,
        minute_df=minute_df, daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "OK"
    risk = result.entry_fill - result.initial_stop_price
    expected_mfe = (peak_price - result.entry_fill) / risk
    assert abs(result.max_favorable_R - expected_mfe) < 1e-6
    assert result.exit_efficiency is not None and result.exit_efficiency < 0.5, \
        "most of the peak gain was given back -- efficiency should be low"


def test_double_gap_sells_two_targets_worth_in_one_event_at_actual_price():
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    ef = entry.entry_fill
    targets = [round(ef * (1 + p), 4) for p in config.V3_MULTI_TARGET_PCTS]

    days = _future_days(2)
    rows = list(prior_rows)
    # Immediately gap straight past target[0] and target[1] on the very first future day.
    gap_price = targets[1] + 3.0
    rows.append(_daily_row(days[0], gap_price, gap_price + 1, gap_price - 1, gap_price))
    # Then a hard pullback resolves the remaining 80% (30pp non-core left + 50pp core).
    rows.append(_daily_row(days[1], ef - 5, ef - 4, ef - 6, ef - 5))

    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="equal_depletion",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EQUAL, target_ladder="early_start", core_pct=0.5, entry=entry, minute_df=minute_df,
        daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "OK"
    # The double-gap crosses 2 targets at once, recorded as 2 Sale entries sharing the
    # SAME timestamp and the SAME actual achieved fill price (not target[0]/[1]'s stale
    # levels) -- Section 54's "all crossed targets fill at the real gap price."
    assert result.first_sale_price is not None
    assert abs(result.first_sale_price - gap_price) < gap_price * 0.01
    assert result.first_sale_reason.endswith("_1of2")
    assert result.n_sales >= 2


def test_ordinary_trade_through_crosses_multiple_targets_each_at_its_own_price():
    # Regression test for a real bug: find_target_reached used to return target_price
    # (the single level being searched for) even for an ORDINARY (non-gap) trade-through,
    # so `crossed = [tp for tp in target_prices if tp <= target_ref]` could only ever
    # match the ONE target being searched for -- a single day's high blowing through
    # several targets without gapping at the open only ever registered one sale. Fixed by
    # returning the day's actual achieved price (its high) for crossing detection, while
    # filling each crossed target at ITS OWN resting level (not a shared price, unlike a
    # genuine gap) since ordinary price action passes through each level in turn.
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    ef = entry.entry_fill
    targets = [round(ef * (1 + p), 4) for p in config.V3_MULTI_TARGET_PCTS]  # +10/20/30/40/50%

    days = _future_days(2)
    rows = list(prior_rows)
    # Day A: opens BELOW target[0] (not a gap), but its HIGH trades through target[0],
    # target[1], AND target[2] in one ordinary intraday move.
    rows.append(_daily_row(days[0], targets[0] - 1, targets[2] + 2, targets[0] - 2, targets[1]))
    # Day B: hard pullback resolves the remaining core.
    rows.append(_daily_row(days[1], ef - 5, ef - 4, ef - 6, ef - 5))

    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    initial_stop_price = ef * 0.95  # matches "5pct_entry"
    result = run_multi_partial_position_management(
        minute_df, daily_sma, entry, initial_stop_price, ef, "close_below_20ma",
        config.V3_MULTI_TARGET_PCTS, "equal_depletion", config.V3_MULTI_SELL_AMOUNT_EQUAL,
        core_pct=0.5, sessions=SESSIONS, log=[],
    )

    assert result.status == "OK"
    target_sales = [s for s in result.sales if s.reason.startswith("TARGET_TRADE_THROUGH")]
    # All 3 targets crossed in this single day must be registered as separate sales, not
    # just the one being searched for.
    assert len(target_sales) == 3
    # Each must fill at its OWN target level (not the day's high, and not a shared price).
    for sale, target_price in zip(target_sales, targets[:3]):
        assert abs(sale.price - target_price) < target_price * 0.01
    assert len({round(s.price, 2) for s in target_sales}) == 3, \
        "each crossed target should fill at a DIFFERENT price, unlike a genuine gap"


def test_ratchet_floor_survives_a_partial_instead_of_resetting_to_breakeven():
    # Regression test for a real bug: the ratchet's cumulative-max was being scoped to
    # the CONTINUATION date (when a target fired) instead of the trade's real entry date,
    # so any ratchet floor established BEFORE the partial was silently forgotten once
    # Phase 2 began -- a direct violation of "trailing stops never loosen" (Section 46).
    entry = EntryResult(
        entry_status=config.STATUS_VALID_TRADE, or_high=99.0, trigger=100.0,
        entry_timestamp=pd.Timestamp(D0).tz_localize(config.ET), entry_day_offset=0,
        entry_session_date=D0, entry_fill=100.0, fill_reason="normal_trade_through",
        entry_bar_index=None, lod_known_at_entry=99.0, trigger_candle_low_known_at_entry=99.0,
    )
    minute_df = pd.DataFrame(columns=["dt_et", "session_date", "open", "high", "low", "close"])

    d1, d2, d3, d4 = _future_days(4)
    rows = []
    for day in _prior_days(25):
        rows.append({"date": day, "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0, "sma20": 91.0})
    rows.append({"date": D0, "open": 99.0, "high": 100.5, "low": 98.5, "close": 100.2, "sma20": 91.5})
    # D0+1: a qualifying ratchet day (close < sma20) whose LOW (103) sits well ABOVE both
    # the initial stop and breakeven -- this is the floor that must survive the partial.
    rows.append({"date": d1, "open": 105.0, "high": 107.0, "low": 103.0, "close": 104.0, "sma20": 106.0})
    # D0+2: an ordinary (non-gap) move through the first target (+10% = 110), staying well
    # above the D0+1 ratchet floor so the downside scan doesn't fire first.
    rows.append({"date": d2, "open": 109.0, "high": 111.0, "low": 108.0, "close": 110.5, "sma20": 100.0})
    # D0+3: OPENS above the ratchet floor (103, no gap-through) then trades down through
    # it intraday to a low BETWEEN breakeven (100) and the floor -- must stop out HERE,
    # at the floor itself, if it correctly survived the partial.
    rows.append({"date": d3, "open": 103.5, "high": 104.0, "low": 101.0, "close": 101.5, "sma20": 100.0})
    # D0+4: a hard pullback that resolves the trade regardless, so a still-buggy version
    # (which would have missed D0+3's 101 low against a wrongly-reset 100 floor) doesn't
    # just report STILL_OPEN and dodge the assertion.
    rows.append({"date": d4, "open": 90.0, "high": 91.0, "low": 89.0, "close": 90.0, "sma20": 100.0})

    daily_sma = pd.DataFrame(rows)

    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="low_of_close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="equal_depletion",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EQUAL, target_ladder="early_start", core_pct=0.5, entry=entry,
        minute_df=minute_df, daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "OK"
    # The core must exit on D0+3 at the preserved ratchet floor (~103), not ride through
    # to D0+4's much lower breakeven-only fill (~100) -- slippage keeps it just under 103.
    assert result.last_sale_price is not None
    assert result.last_sale_price > 102.0, (
        f"core exit at {result.last_sale_price} -- the pre-partial ratchet floor (~103) "
        f"was lost, position rode down to breakeven (~100) instead"
    )


def test_exponential_remaining_sales_shrink_and_first_sale_matches_equal_depletion():
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    ef = entry.entry_fill
    targets = [round(ef * (1 + p), 4) for p in config.V3_MULTI_TARGET_PCTS]

    days = _future_days(3)
    rows = list(prior_rows)
    rows.append(_daily_row(days[0], targets[0] - 1, targets[0] + 0.5, targets[0] - 2, targets[0]))
    rows.append(_daily_row(days[1], targets[1] - 1, targets[1] + 0.5, targets[1] - 2, targets[1]))
    rows.append(_daily_row(days[2], ef - 5, ef - 4, ef - 6, ef - 5))  # pulls back, resolves the rest

    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="exponential_remaining",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EXPONENTIAL, target_ladder="early_start", core_pct=0.5, entry=entry, minute_df=minute_df,
        daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "OK"
    assert result.n_sales == 3  # 2 target sales + 1 final stop-out of whatever remains
    # First sale: 20% of the initial 50% non-core = 10pp, same opening move as equal_depletion.
    # Second sale: 20% of the NEW remaining (40pp) = 8pp, strictly smaller than the first.
    # The final stop-out then sells the leftover non-core AND the 50% core TOGETHER in
    # one event (they aren't separate sales): 100 - 10 - 8 = 82pp of the original.
    assert abs(result.last_sale_pct - 0.82) < 1e-6


def test_downside_scan_reference_price_is_not_conflated_with_floor():
    # Regression test for a real bug found on the first full-universe V3b run: passing
    # the SAME value for both `floor` (used to compute the level series via
    # clip(lower=floor)) and `reference_price` (used to validate the level) made the
    # invalid-geometry check TAUTOLOGICALLY true the moment floor==entry_fill
    # (breakeven, active from the second target onward) -- level = max(prior_MA, floor)
    # is ALWAYS >= floor by construction, so comparing it against floor again flagged
    # every such continuation invalid regardless of whether the setup was actually
    # nonsensical. Confirmed on real data: WYNN 2016-02-12 resolved to +9.76R under
    # close_below_20ma but was wrongly discarded entirely (INVALID_STOP_GEOMETRY) under
    # 20ma_touch on the identical setup, purely because of this.
    daily_sma = pd.DataFrame({
        "date": [D0 - timedelta(days=1), D0, D0 + timedelta(days=1)],
        "close": [105.0, 106.0, 107.0],
        "sma20": [105.0, 106.0, 107.0],  # an ordinary, rising trailing MA
        "low": [104.0, 105.0, 106.0],
        "open": [104.5, 105.5, 106.5],
        "high": [105.5, 106.5, 107.5],
    })
    minute_df = pd.DataFrame(columns=["dt_et", "session_date", "open", "high", "low", "close"])
    continuation_entry = EntryResult(
        entry_status=config.STATUS_VALID_TRADE, or_high=100.0, trigger=100.01,
        entry_timestamp=pd.Timestamp(D0).tz_localize(config.ET), entry_day_offset=None,
        entry_session_date=D0, entry_fill=100.0, fill_reason="normal_trade_through",
        entry_bar_index=None, lod_known_at_entry=99.0, trigger_candle_low_known_at_entry=99.0,
    )

    # floor = 100 (breakeven); level on D0 = max(prior day's sma20=105, floor=100) = 105.
    # The buggy version compared 105 against floor (100) -- 105 >= 100 -> falsely
    # INVALID. The fix compares against reference_price (108, the actual price this
    # continuation resumed from, e.g. a target fill) -- 105 < 108, must NOT be invalid.
    status, _, _ = _downside_scan(
        minute_df, daily_sma, continuation_entry, floor=100.0, reference_price=108.0,
        trail_type="20ma_touch", sessions=[D0], log=[], is_continuation=True,
        original_entry_date=D0,
    )
    assert status != "INVALID"


def test_multi_neither_stop_nor_target_resolves_reports_still_open_without_crashing():
    # Regression test for a real bug found on the full-universe run: when data just
    # runs out with neither the downside scan NOR the target scan ever resolving,
    # _stop_wins() alone can't tell "genuinely nothing resolved" apart from "stop_ts is
    # None but a target WAS found" (its first check fires the same way for both) --
    # without an explicit guard, the code fell through to the "target won" branch with
    # target_ref=None and crashed on `target_ref + 1e-9`.
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    ef = entry.entry_fill
    days = _future_days(1)
    rows = list(prior_rows)
    # A perfectly quiet day: no target threatened, no stop threatened, then data ends.
    rows.append(_daily_row(days[0], ef, ef + 0.1, ef - 0.1, ef))
    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="equal_depletion",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EQUAL, target_ladder="early_start", core_pct=0.5, entry=entry, minute_df=minute_df,
        daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "STILL_OPEN_AT_DATA_END"
    assert result.realized_R is None


def test_multi_target_never_reached_matches_v2():
    # Sanity cross-check: if price never gets anywhere near even the first target, the
    # whole trade must resolve exactly like V2 (single downside exit, no partial sales).
    minute_df, prior_rows, entry = _entry_and_prior_daily()
    rows = list(prior_rows)
    days = _future_days(1)
    rows.append(_daily_row(days[0], entry.entry_fill - 5, entry.entry_fill - 4, entry.entry_fill - 6, entry.entry_fill - 5))
    daily_df = pd.DataFrame(rows)
    daily_sma = add_sma10(daily_df)

    v2 = simulate_v2_with_entry("TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry",
                                 trail_type="close_below_20ma", entry=entry, minute_df=minute_df,
                                 daily_sma=daily_sma, sessions=SESSIONS)
    result = simulate_multi_v3_with_entry(
        "TEST", D0, adr14=0.06, entry_type="1m", stop_type="5pct_entry", trail_type="close_below_20ma",
        target_pcts=config.V3_MULTI_TARGET_PCTS, sell_style="equal_depletion",
        sell_amount=config.V3_MULTI_SELL_AMOUNT_EQUAL, target_ladder="early_start", core_pct=0.5, entry=entry, minute_df=minute_df,
        daily_sma=daily_sma, sessions=SESSIONS,
    )

    assert result.status == "OK" and v2.status == "OK"
    assert result.n_sales == 1
    assert abs(result.realized_R - v2.realized_R) < 1e-9


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
