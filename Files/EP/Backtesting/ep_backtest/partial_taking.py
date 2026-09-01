"""
V3 partial profit-taking (Section 47-55). User's confirmed choices (2026-08-30):

- Profit target Type A (Section 48): a single fixed price target, X% above entry.
- Sell style: ONE sale, sells the entire non-core portion (not staged partials) --
  the simplest version of V3, closest to Qullamaggie's actual "sell a third to half
  after 3-5 days" rule.
- Breakeven-after-first-sell: enabled (Section 55). BEStop = EntryPrice (the
  recommended simple V1 definition, reused here since nothing more specific was asked
  for).
- Core %: 50/50 (confirmed by the user ahead of V3 being built).

Mechanics, in two phases:

Phase 1 (100% of the position open): race the SAME V2 downside stop/trailing scan
against a NEW upside target scan (mirror-image logic, checking highs against a fixed
target price instead of lows against a stop). Whichever resolves first wins. If the
stop wins, this is exactly a V2 outcome -- no partial ever happens. If the target wins,
sell the non-core fraction at the target price and hand the remaining core off to
Phase 2.

Phase 2 (core_pct of the position remaining): re-run the SAME V2 trailing-stop scan
used in Phase 1, just with the floor raised from the original initial stop to
breakeven (entry_fill) instead -- Section 55's "later trailing stops can only replace
breakeven if they tighten the stop further" falls out for free from reusing the exact
same max(floor, trailing_level) mechanism V2 already implements, just with a higher
floor plugged in.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from . import calendar_utils, config, trailing_stops
from .entry import EntryResult
from .simulate_trade import _run_position_management


def is_gap_reason(reason) -> bool:
    return reason is not None and "GAP_THROUGH" in reason


def find_target_reached(minute_df, daily_sma, entry: EntryResult, target_price: float, sessions, log,
                         is_continuation: bool = False):
    """
    Mirror image of trailing_stops.run_level_based_position_management's downside scan,
    but upside and against a FIXED level (the target never moves): gap-through if a bar
    opens at/above target, trade-through if a bar's high reaches it otherwise. Same
    minute-precision-then-daily-approximation-fallback structure as every other scan in
    this project, for the same reason (Section 78 only caches minute bars D0..D+7).

    Returns (target_timestamp, achieved_price, "TARGET_GAP_THROUGH" | "TARGET_TRADE_THROUGH"
    | "TARGET_SAME_BAR_AS_ENTRY" | ..._DAILY_APPROX) or (None, None, None).

    `achieved_price` is the actual best price reached in the crossing bar/day -- the
    bar's open for a gap-through, or its HIGH for an ordinary trade-through (NOT
    target_price itself, as an earlier version returned). A caller checking only ONE
    target should still fill at target_price for a trade-through (a resting limit order
    fills AT its own level when touched, not at whatever high the bar goes on to reach)
    and at achieved_price for a gap-through (see is_gap_reason). A caller checking
    MULTIPLE resting targets at once (multi_partial_taking's ladder) needs achieved_price
    to detect every target crossed within this single bar/day -- confirmed real bug,
    2026-08-31: returning target_price unconditionally meant an ordinary (non-gap)
    trade-through that blew past several targets in one bar only ever registered ONE of
    them, since `[tp for tp in targets if tp <= target_price]` can only ever match the
    one target being searched for.

    is_continuation=True: the caller is resuming an already-open position (a later
    target search in multi_partial_taking's ladder, not a genuine entry), so the Section
    23 same-bar-adverse "ambiguous ordering" exemption -- which only makes sense for a
    real entry bar -- must NOT apply to this scan's first bar. Mirrors
    trailing_stops.run_level_based_position_management's is_continuation flag; without
    it, a later target reached on the very first bar of a continuation's scan window was
    wrongly treated as ambiguous "same bar as entry" and collapsed to a single fill at
    target_price, skipping the multi-crossing check entirely.
    """
    remaining_days = [d for d in sessions if d >= entry.entry_session_date]
    bars = minute_df[
        minute_df["session_date"].isin(remaining_days) & (minute_df["dt_et"] >= entry.entry_timestamp)
    ].sort_values("dt_et").reset_index(drop=True)

    if not bars.empty:
        is_entry_bar = np.zeros(len(bars), dtype=bool)
        if not is_continuation:
            is_entry_bar[0] = True
        high = bars["high"].to_numpy()
        open_ = bars["open"].to_numpy()
        gap_cond = (~is_entry_bar) & (open_ >= target_price)
        trade_cond = high >= target_price  # for the entry bar this is a same-bar target-and-stop-adjacent case
        target_hit = gap_cond | trade_cond
        if target_hit.any():
            idx = int(target_hit.argmax())
            ts = bars["dt_et"].iloc[idx]
            if is_entry_bar[idx]:
                return ts, target_price, "TARGET_SAME_BAR_AS_ENTRY"
            if gap_cond[idx]:
                return ts, float(open_[idx]), "TARGET_GAP_THROUGH"
            return ts, float(high[idx]), "TARGET_TRADE_THROUGH"

    after = daily_sma[daily_sma["date"] > sessions[-1]].sort_values("date").reset_index(drop=True)
    if after.empty:
        return None, None, None
    gap_through = after["open"] >= target_price
    trade_through = after["high"] >= target_price
    any_hit = gap_through | trade_through
    if not any_hit.any():
        return None, None, None
    pos = int(any_hit.to_numpy().argmax())
    row = after.iloc[pos]
    if gap_through.iloc[pos]:
        return row["date"], row["open"], "TARGET_GAP_THROUGH_DAILY_APPROX"
    return row["date"], float(row["high"]), "TARGET_TRADE_THROUGH_DAILY_APPROX"


def _day_of(ts):
    return ts.date() if hasattr(ts, "date") else ts


def restrict_to_after(minute_df, sessions, after_day, after_ts):
    """
    Bars/sessions still usable for a scan continuing from right after `after_ts` (on
    `after_day`) -- shared by V3's Phase 2 and multi_partial_taking's per-target loop,
    both of which need to avoid re-scanning bars/days already consumed by an earlier
    stage of the same trade.

    Real bug this guards against: `sessions` is always the ORIGINAL fixed D0..D+7 list
    (Section 78's cached minute-bar window), so filtering it to `>= after_day` goes
    EMPTY whenever the triggering event itself only resolved beyond D+7 -- i.e. whenever
    the event was already found via the daily-bar-approximation fallback, which is
    common for any target/level that takes more than 8 sessions to reach. The scanning
    functions use `sessions[-1]` purely as "where does the minute-precision window end,
    and daily approximation take over" -- an empty list must NOT be read as "nothing
    left to check," it must be read as "we're already past the minute window, so the
    daily-approximation phase should start immediately from `after_day`." Returning an
    empty list here made every downstream caller (both V3's Phase 2 and V3b's per-target
    loop) give up and report STILL_OPEN_AT_DATA_END the moment any triggering event fired
    beyond D+7, even when plenty more daily history was available to keep scanning.
    """
    sessions_after = [d for d in sessions if d >= after_day]
    if not sessions_after:
        sessions_after = [after_day]  # sentinel: daily-approximation resumes strictly after this
    if hasattr(after_ts, "date"):
        minute_after = minute_df[
            (minute_df["session_date"] > after_day)
            | ((minute_df["session_date"] == after_day) & (minute_df["dt_et"] > after_ts))
        ]
    else:
        minute_after = minute_df[minute_df["session_date"] > after_day]
    return minute_after, sessions_after


def make_continuation_entry(entry: EntryResult, ts, day, entry_fill: float) -> EntryResult:
    """
    A fabricated EntryResult so a later stage of the same trade can reuse the exact same
    V2 scanning functions unchanged -- they only need entry_timestamp/entry_session_date
    to know where to start looking, which for a continuation is "right after the
    previous stage's event." entry_fill is preserved as the ORIGINAL entry price (never
    the event that triggered this continuation) since it's still what defines 1R.
    """
    # ts is either already a tz-aware datetime (an intraday minute-window event) or a
    # plain date (a daily-approximation event) -- the latter must be localized to ET,
    # not left tz-naive, or every downstream comparison against minute_df["dt_et"]
    # (always tz-aware) raises TypeError: Cannot compare tz-naive and tz-aware.
    entry_timestamp = ts if hasattr(ts, "date") else pd.Timestamp(ts).tz_localize(config.ET)
    return EntryResult(
        entry_status=config.STATUS_VALID_TRADE, or_high=entry.or_high, trigger=entry.trigger,
        entry_timestamp=entry_timestamp,
        entry_day_offset=None, entry_session_date=day, entry_fill=entry_fill,
        fill_reason=entry.fill_reason, entry_bar_index=None,
        lod_known_at_entry=entry.lod_known_at_entry,
        trigger_candle_low_known_at_entry=entry.trigger_candle_low_known_at_entry,
    )


_END_OF_DAY_REASONS = ("SMA10_EXIT", "SMA20_EXIT")


def _has_intraday_precision(ts) -> bool:
    return hasattr(ts, "date")  # a real datetime/Timestamp, not a plain date


def _stop_wins(stop_ts, stop_reason, target_ts) -> bool:
    """
    True if the downside stop/trailing event resolves before (or, on a genuine tie,
    takes priority over) the upside target event.

    A same-CALENDAR-DAY collision needs real domain knowledge to order correctly, not
    just a raw timestamp/date comparison -- a first version of this fell back to "can't
    compare a date to a datetime -> assume adverse (stop wins)" for every same-day case,
    which silently mis-ordered a real, common scenario: an SMA-close exit is inherently
    an END-OF-DAY event (a close-below-MA check can't resolve until the day is over),
    so if the target fired at an actual intraday timestamp that same day, the target
    genuinely happened first regardless of the coarser date-only representation of the
    close exit. Caught by test_v3_partial_then_core_exit_weighted_R initially failing
    with the target silently disappearing (a close-based stop was wrongly declared the
    winner on the exact day the target had already fired hours earlier).
    """
    if stop_ts is None:
        return False
    if target_ts is None:
        return True

    stop_day, target_day = _day_of(stop_ts), _day_of(target_ts)
    if stop_day != target_day:
        return stop_day < target_day

    if stop_reason in _END_OF_DAY_REASONS and _has_intraday_precision(target_ts):
        return False  # the intraday target necessarily preceded the end-of-day check
    if _has_intraday_precision(stop_ts) and _has_intraday_precision(target_ts):
        return stop_ts <= target_ts  # real same-day tie between two intrabar events -> adverse
    return True  # both coarse/ambiguous (e.g. both daily-approximation) -> adverse priority


@dataclass
class V3Result:
    status: str
    partial_timestamp: Optional[object] = None
    partial_price: Optional[float] = None
    partial_reason: Optional[str] = None
    core_exit_timestamp: Optional[object] = None
    core_exit_price: Optional[float] = None
    core_exit_reason: Optional[str] = None
    realized_R: Optional[float] = None
    audit_log: list = field(default_factory=list)


def run_v3_position_management(
    minute_df, daily_sma, entry: EntryResult, initial_stop_price: float, entry_fill: float,
    trail_type: str, target_pct: float, core_pct: float, sessions, log,
) -> V3Result:
    from .simulate_trade import _slip_sub  # local import to avoid a module import cycle

    risk = entry_fill - initial_stop_price
    target_price = entry_fill * (1 + target_pct)
    log.append(f"Profit target ({target_pct*100:g}% from entry) = {target_price:.4f}")

    # Phase 1: race the downside (stop/trailing) scan against the new upside (target) scan.
    if trailing_stops.is_close_based(trail_type):
        stop_ts, stop_ref, stop_reason = _run_position_management(
            minute_df, daily_sma, entry, initial_stop_price, sessions, log,
            ma_col=trailing_stops.ma_column_for(trail_type),
        )
    else:
        level_series = trailing_stops.level_series_for(
            trail_type, daily_sma, initial_stop_price, entry.entry_session_date, reference_price=entry_fill
        )
        # Same invalid-geometry guard as V2 (see simulate_trade.simulate_v2_with_entry):
        # a touch level can legitimately sit above the entry price after a steep enough
        # decline, which must not be treated as a reachable fill price.
        entry_day_level = level_series[daily_sma["date"] == entry.entry_session_date]
        if not entry_day_level.empty and float(entry_day_level.iloc[0]) >= entry_fill:
            log.append(
                f"Trailing level on entry day ({float(entry_day_level.iloc[0]):.4f}) >= "
                f"entry fill ({entry_fill:.4f}) -- INVALID_STOP_GEOMETRY"
            )
            return V3Result(status=config.STATUS_INVALID_STOP_GEOMETRY, audit_log=log)

        stop_ts, stop_ref, stop_reason = trailing_stops.run_level_based_position_management(
            minute_df, daily_sma, entry, level_series, sessions, log
        )

    target_ts, target_ref, target_reason = find_target_reached(minute_df, daily_sma, entry, target_price, sessions, log)

    if stop_ts is None and target_ts is None:
        log.append("Neither stop/trailing nor profit target resolved before the end of available data -- STILL_OPEN_AT_DATA_END")
        return V3Result(status="STILL_OPEN_AT_DATA_END", audit_log=log)

    stop_wins = _stop_wins(stop_ts, stop_reason, target_ts)

    if stop_wins:
        # No partial ever happened -- this IS the V2 outcome, unweighted.
        exit_fill = _slip_sub(stop_ref)
        net_pnl_per_share = exit_fill - entry_fill
        realized_R = net_pnl_per_share / risk
        log.append(f"Stop/trailing resolved before target ({stop_reason} at {stop_ts}) -- no partial taken")
        return V3Result(
            status="OK", core_exit_timestamp=stop_ts, core_exit_price=round(exit_fill, 4),
            core_exit_reason=stop_reason, realized_R=realized_R, audit_log=log,
        )

    # Target won: sell the non-core fraction at the target, move remaining core's floor
    # to breakeven, and continue with Phase 2 -- the exact same scan, higher floor.
    # Fill at target_price for an ordinary trade-through (a resting limit order fills at
    # its own level, not wherever the bar's high goes on to reach -- target_ref is now
    # that bar's high, only useful for multi-target detection, see find_target_reached)
    # or at the real gap price for a gap-through.
    fill_level = target_ref if is_gap_reason(target_reason) else target_price
    partial_fill = _slip_sub(fill_level)
    partial_R = (partial_fill - entry_fill) / risk
    log.append(f"Target reached ({target_reason} at {target_ts}), fill = {partial_fill:.4f} -- "
               f"selling {(1-core_pct)*100:g}% non-core, moving core stop to breakeven ({entry_fill:.4f})")

    # Phase 2 must not re-scan bars/days already consumed by Phase 1.
    target_day = _day_of(target_ts)
    phase2_minute_df, phase2_sessions = restrict_to_after(minute_df, sessions, target_day, target_ts)
    phase2_entry = make_continuation_entry(entry, target_ts, target_day, entry_fill)

    if trailing_stops.is_close_based(trail_type):
        core_ts, core_ref, core_reason = _run_position_management(
            phase2_minute_df, daily_sma, phase2_entry, entry_fill, phase2_sessions, log,
            ma_col=trailing_stops.ma_column_for(trail_type), is_continuation=True,
        )
    else:
        # entry.entry_session_date (the ORIGINAL entry date), not target_day -- see
        # trailing_stops.ratchet_level_series's docstring. Passing target_day here was a
        # real bug: it forgot any ratchet floor already established between entry and
        # the partial, letting Phase 2's floor drop below what it legitimately was.
        core_level_series = trailing_stops.level_series_for(
            trail_type, daily_sma, entry_fill, entry.entry_session_date, reference_price=fill_level
        )
        # Same invalid-geometry guard as Phase 1, checked against the actual traded
        # price at the moment Phase 2 begins (fill_level -- the real partial fill price,
        # NOT target_ref, which for an ordinary trade-through is now the bar's HIGH, not
        # a price the position was actually transacted at) rather than entry_fill -- the
        # same "MA hasn't caught up to a violent move" scenario could in principle recur
        # here too, just relative to where the position is when the partial fires rather
        # than relative to the original entry.
        target_day_level = core_level_series[daily_sma["date"] == target_day]
        if not target_day_level.empty and float(target_day_level.iloc[0]) >= fill_level:
            log.append(
                f"Core trailing level on target day ({float(target_day_level.iloc[0]):.4f}) >= "
                f"target fill ({fill_level:.4f}) -- INVALID_STOP_GEOMETRY"
            )
            return V3Result(status=config.STATUS_INVALID_STOP_GEOMETRY, audit_log=log)

        core_ts, core_ref, core_reason = trailing_stops.run_level_based_position_management(
            phase2_minute_df, daily_sma, phase2_entry, core_level_series, phase2_sessions, log,
            is_continuation=True,
        )

    if core_ts is None:
        log.append("Core position still open at the end of available data after the partial -- STILL_OPEN_AT_DATA_END")
        return V3Result(
            status="STILL_OPEN_AT_DATA_END", partial_timestamp=target_ts, partial_price=round(partial_fill, 4),
            partial_reason=target_reason, audit_log=log,
        )

    core_fill = _slip_sub(core_ref)
    core_R = (core_fill - entry_fill) / risk
    realized_R = (1 - core_pct) * partial_R + core_pct * core_R
    log.append(f"Core exit: {core_reason} at {core_ts}, fill = {core_fill:.4f}")
    log.append(f"Partial R = {partial_R:.4f}, Core R = {core_R:.4f}, weighted Final R = {realized_R:.4f}")

    return V3Result(
        status="OK", partial_timestamp=target_ts, partial_price=round(partial_fill, 4), partial_reason=target_reason,
        core_exit_timestamp=core_ts, core_exit_price=round(core_fill, 4), core_exit_reason=core_reason,
        realized_R=realized_R, audit_log=log,
    )
