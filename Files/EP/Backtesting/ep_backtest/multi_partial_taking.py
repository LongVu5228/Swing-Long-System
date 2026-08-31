"""
V3b: multi-target staged partial-taking (Section 50/52/53/54), as an alternative to
partial_taking.py's single-sale version. User's confirmed choices (2026-08-30):

- Targets spaced every 10% from entry: +10%, +20%, +30%, +40%, +50%.
- Both sell styles requested, run side by side:
  - EQUAL_DEPLETION (Section 52): sell a fixed 10 percentage points of the ORIGINAL
    position at each target crossed, until the 50% non-core is fully depleted (so all
    5 targets, hit in order, exactly exhaust it).
  - EXPONENTIAL_REMAINING (Section 53): sell 20% of whatever non-core REMAINS at each
    target crossed. The first sale is the same size as equal-depletion's (20% of the
    initial 50% non-core = 10pp), but every sale after that is smaller, leaving a
    shrinking tail that can still be partly unsold after all 5 targets -- that residual
    just keeps riding under the trailing stop indefinitely, same as a smaller "core."
- Breakeven activates once, after the FIRST sale (any target), exactly like the
  single-sale version -- never re-activated or re-tightened by later sales themselves
  (only the ongoing trailing stop can tighten it further from there).
- Core % floor: the 50% core is NEVER touched by target sales; both sell styles only
  ever draw down the 50% non-core bucket.

Architecture: a loop over "the next undepleted target," reusing the exact same
race-downside-vs-target primitives as the single-sale version (partial_taking.py) at
each step -- find_target_reached, the V2 downside scan, and the continuation helpers
(restrict_to_after / make_continuation_entry) that keep each step point-in-time safe
and non-overlapping with bars/days already consumed by earlier steps.

Section 54 (gap through multiple targets): if the achieved price on a single crossing
event is at or above MORE than one remaining target, all of those targets are
considered reached at once, filled at the SAME actual achieved price (not their
individual stale target levels) -- handled by the `crossed` computation below.
"""

from dataclasses import dataclass, field
from typing import Optional

from . import config, trailing_stops
from .entry import EntryResult
from .partial_taking import (
    _day_of,
    _stop_wins,
    find_target_reached,
    make_continuation_entry,
    restrict_to_after,
)
from .simulate_trade import _run_position_management, _slip_sub

SELL_STYLES = ["equal_depletion", "exponential_remaining"]


@dataclass
class Sale:
    timestamp: object
    price: float
    pct_of_original: float
    reason: str


@dataclass
class MultiPartialResult:
    status: str
    sales: list = field(default_factory=list)  # list[Sale]
    realized_R: Optional[float] = None
    audit_log: list = field(default_factory=list)


def _downside_scan(minute_df, daily_sma, scan_entry, floor, trail_type, sessions, log, is_continuation):
    """One downside stop/trailing check, reused at every step of the loop."""
    if trailing_stops.is_close_based(trail_type):
        return _run_position_management(
            minute_df, daily_sma, scan_entry, floor, sessions, log,
            ma_col=trailing_stops.ma_column_for(trail_type), is_continuation=is_continuation,
        )
    level_series = trailing_stops.level_series_for(trail_type, daily_sma, floor, scan_entry.entry_session_date)
    entry_day_level = level_series[daily_sma["date"] == scan_entry.entry_session_date]
    if not entry_day_level.empty and float(entry_day_level.iloc[0]) >= scan_entry.entry_fill:
        log.append(
            f"Trailing level on {scan_entry.entry_session_date} ({float(entry_day_level.iloc[0]):.4f}) >= "
            f"reference price ({scan_entry.entry_fill:.4f}) -- INVALID_STOP_GEOMETRY"
        )
        return "INVALID", None, None
    return trailing_stops.run_level_based_position_management(
        minute_df, daily_sma, scan_entry, level_series, sessions, log, is_continuation=is_continuation
    )


def run_multi_partial_position_management(
    minute_df, daily_sma, entry: EntryResult, initial_stop_price: float, entry_fill: float,
    trail_type: str, target_pcts: list, sell_style: str, sell_amount: float, core_pct: float, sessions, log,
) -> MultiPartialResult:
    risk = entry_fill - initial_stop_price
    target_prices = sorted(entry_fill * (1 + p) for p in target_pcts)
    log.append(f"Targets ({sell_style}): {[round(t, 4) for t in target_prices]}")

    non_core_remaining = 1.0 - core_pct
    total_sold_pct = 0.0
    sales = []

    scan_minute_df, scan_sessions = minute_df, sessions
    scan_entry = entry
    floor = initial_stop_price
    breakeven_activated = False
    is_continuation = False

    while True:
        stop_ts, stop_ref, stop_reason = _downside_scan(
            scan_minute_df, daily_sma, scan_entry, floor, trail_type, scan_sessions, log, is_continuation
        )
        if stop_ts == "INVALID":
            return MultiPartialResult(status=config.STATUS_INVALID_STOP_GEOMETRY, audit_log=log)

        if not target_prices or non_core_remaining <= 1e-9:
            # Nothing left to sell on the way up -- only the downside scan can resolve
            # the remainder now (whatever fraction of the original position remains).
            if stop_ts is None:
                return MultiPartialResult(status="STILL_OPEN_AT_DATA_END", sales=sales, audit_log=log)
            leftover = round(1.0 - total_sold_pct, 6)
            fill = _slip_sub(stop_ref)
            sales.append(Sale(stop_ts, fill, leftover, stop_reason))
            log.append(f"{stop_ts}: {stop_reason} at {fill:.4f} -- final sale of remaining {leftover*100:g}%")
            break

        next_target = target_prices[0]
        target_ts, target_ref, target_reason = find_target_reached(
            scan_minute_df, daily_sma, scan_entry, next_target, scan_sessions, log
        )

        if _stop_wins(stop_ts, stop_reason, target_ts):
            if stop_ts is None:
                return MultiPartialResult(status="STILL_OPEN_AT_DATA_END", sales=sales, audit_log=log)
            leftover = round(1.0 - total_sold_pct, 6)
            fill = _slip_sub(stop_ref)
            sales.append(Sale(stop_ts, fill, leftover, stop_reason))
            log.append(f"{stop_ts}: {stop_reason} at {fill:.4f} -- final sale of remaining {leftover*100:g}% "
                       f"(no further targets reached)")
            break

        # Target(s) reached -- Section 54: a gap can cross more than one remaining
        # target at once, all filled at the SAME actual achieved price.
        crossed = [tp for tp in target_prices if tp <= target_ref + 1e-9]
        fill = _slip_sub(target_ref)
        for i, _ in enumerate(crossed, start=1):
            if non_core_remaining <= 1e-9:
                break
            if sell_style == "equal_depletion":
                sell_pct = min(sell_amount, non_core_remaining)
            else:
                sell_pct = min(non_core_remaining * sell_amount, non_core_remaining)
            sales.append(Sale(target_ts, fill, sell_pct, f"{target_reason}_{i}of{len(crossed)}"))
            total_sold_pct += sell_pct
            non_core_remaining -= sell_pct

        log.append(f"{target_ts}: {len(crossed)} target(s) crossed at once, fill = {fill:.4f}, "
                   f"non-core remaining = {non_core_remaining*100:g}%")

        target_prices = target_prices[len(crossed):]
        if not breakeven_activated:
            floor = entry_fill
            breakeven_activated = True
            log.append(f"Breakeven activated: floor = {entry_fill:.4f}")

        target_day = _day_of(target_ts)
        scan_minute_df, scan_sessions = restrict_to_after(minute_df, sessions, target_day, target_ts)
        scan_entry = make_continuation_entry(entry, target_ts, target_day, entry_fill)
        is_continuation = True

    realized_R = sum(s.pct_of_original * (s.price - entry_fill) for s in sales) / risk
    log.append(f"Weighted final R = {realized_R:.4f} across {len(sales)} sale(s)")
    return MultiPartialResult(status="OK", sales=sales, realized_R=realized_R, audit_log=log)
