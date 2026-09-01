"""
V3b: multi-target staged partial-taking (Section 50/52/53/54), as an alternative to
partial_taking.py's single-sale version. User's confirmed choices (2026-08-30):

- Targets spaced every 10% from entry: +10%, +20%, +30%, +40%, +50%.
- Both sell styles requested, run side by side:
  - EQUAL_DEPLETION (Section 52): sell an equal slice of the ORIGINAL position at each
    target crossed -- (1 - core_pct) / n_targets per rung -- so all targets, hit in
    order, exactly exhaust the non-core bucket regardless of the core/non-core split
    (10pp/target at the original 50/50; 14pp/target at 30/70; 6pp/target at 70/30).
  - EXPONENTIAL_REMAINING (Section 53): sell 20% of whatever non-core REMAINS at each
    target crossed. The first sale is the same size as equal-depletion's first rung,
    but every sale after that is smaller, leaving a shrinking tail that can still be
    partly unsold after all 5 targets -- that residual just keeps riding under the
    trailing stop indefinitely, same as a smaller "core."
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

Section 54 (crossing multiple targets in one bar/day): if the achieved price on a
single crossing event is at or above MORE than one remaining target, all of those
targets are considered reached at once -- handled by the `crossed` computation below.
A gap fills every crossed target at the SAME real gap price (no orderly price discovery
happened between the pre-gap and post-gap price). An ordinary trade-through fills each
crossed target at ITS OWN resting level (price passed through them in order, so each
would have filled individually) -- fixed 2026-08-31 after confirming the original
version only ever detected/filled the ONE target being searched for on a non-gap
multi-target crossing.
"""

from dataclasses import dataclass, field
from typing import Optional

from . import config, trailing_stops
from .entry import EntryResult
from .partial_taking import (
    _day_of,
    _stop_wins,
    find_target_reached,
    is_gap_reason,
    make_continuation_entry,
    restrict_to_after,
)
from .simulate_trade import _run_position_management, _slip_sub

SELL_STYLES = ["equal_depletion", "exponential_remaining"]


def _next_sell_pct(sell_style: str, sell_amount: float, non_core_remaining: float) -> float:
    """The fraction of the ORIGINAL position sold at ONE target crossing, given how much
    non-core remains right before it. Shared by the live simulation loop below and
    describe_sell_schedule() (a pure, trade-independent preview of the same math, used
    for reporting) so the two can never silently drift apart."""
    if sell_style == "equal_depletion":
        return min(sell_amount, non_core_remaining)
    return min(non_core_remaining * sell_amount, non_core_remaining)


def describe_sell_schedule(sell_style: str, core_pct: float, n_targets: int) -> list:
    """The sequence of per-rung sell sizes (as a fraction of the ORIGINAL position) this
    strategy's targets would produce if every rung were reached in order with nothing
    else intervening -- a pure function of the strategy's own parameters (no trade, no
    price action involved), for describing/reporting what a strategy_id actually does
    mechanically. Added 2026-08-31: the strategy_id string alone doesn't say how much
    gets sold at each rung, and that wasn't otherwise visible anywhere in the output."""
    if n_targets <= 0:
        return []
    non_core_remaining = 1.0 - core_pct
    sell_amount = (
        non_core_remaining / n_targets if sell_style == "equal_depletion"
        else config.V3_MULTI_SELL_AMOUNT_EXPONENTIAL
    )
    schedule = []
    for _ in range(n_targets):
        sell_pct = _next_sell_pct(sell_style, sell_amount, non_core_remaining)
        schedule.append(sell_pct)
        non_core_remaining -= sell_pct
    return schedule


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


def _downside_scan(minute_df, daily_sma, scan_entry, floor, reference_price, trail_type, sessions, log,
                    is_continuation, original_entry_date, original_entry_fill=None):
    """
    One downside stop/trailing check, reused at every step of the loop.

    `floor` and `reference_price` must NOT be the same value once breakeven has
    activated -- `floor` is the price used to compute the level series (clip(lower=
    floor)), while `reference_price` is what the invalid-geometry guard checks that
    level against. Confirmed as a real bug on the first full-universe V3b run: the
    original code passed scan_entry.entry_fill for both, and once floor==entry_fill
    (breakeven, active from the second target onward), the check `level >= entry_fill`
    became TAUTOLOGICALLY true by construction (the level series is clipped to be >=
    floor==entry_fill no matter what), so every touch/ratchet trade that ever reached a
    single target got marked INVALID_STOP_GEOMETRY from that point on -- including real
    winners (WYNN 2016-02-12 resolved correctly to +9.76R under close_below_20ma but was
    wrongly discarded entirely under 20ma_touch on the identical setup). reference_price
    must be the actual traded price at the START of this scan phase (the original entry
    fill for the very first call, the most recent target's fill price afterward) --
    exactly mirroring how partial_taking.run_v3_position_management's Phase 2 correctly
    checks against target_ref, not entry_fill.

    `original_entry_date` (the trade's REAL entry date, never a continuation date) is
    separate from `scan_entry.entry_session_date` (which IS a continuation date after the
    first target) for the same reason: trailing_stops.ratchet_level_series's cumulative
    max must be scoped to the whole trade's post-entry history, not reset at each
    continuation -- passing scan_entry.entry_session_date here was a real bug that forgot
    any ratchet floor already established before the most recent target fired.
    """
    if trailing_stops.is_close_based(trail_type):
        return _run_position_management(
            minute_df, daily_sma, scan_entry, floor, sessions, log,
            ma_col=trailing_stops.ma_column_for(trail_type), is_continuation=is_continuation,
        )
    if trailing_stops.is_adaptive_close_based(trail_type):
        adaptive_daily_sma = trailing_stops.build_adaptive_ma_column(
            daily_sma, original_entry_fill, original_entry_date, config.ADAPTIVE_TIGHTEN_ACTIVATION_PCT,
        )
        return _run_position_management(
            minute_df, adaptive_daily_sma, scan_entry, floor, sessions, log,
            ma_col="adaptive_ma", is_continuation=is_continuation,
        )
    level_series = trailing_stops.level_series_for(
        trail_type, daily_sma, floor, original_entry_date, reference_price=reference_price
    )
    entry_day_level = level_series[daily_sma["date"] == scan_entry.entry_session_date]
    if not entry_day_level.empty and float(entry_day_level.iloc[0]) >= reference_price:
        log.append(
            f"Trailing level on {scan_entry.entry_session_date} ({float(entry_day_level.iloc[0]):.4f}) >= "
            f"reference price ({reference_price:.4f}) -- INVALID_STOP_GEOMETRY"
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

    if sell_style == "equal_depletion" and target_prices:
        # Scale the per-target sell size to core_pct so the ladder always fully
        # exhausts non-core across all rungs, regardless of split. Previously this was
        # a FIXED 10pp/target (config.V3_MULTI_SELL_AMOUNT_EQUAL) calibrated only for
        # the 50/50 split -- it silently capped out early for a large core_pct (e.g.
        # C70's 30% non-core hit the cap after 3 targets) and, worse, made C30 and C50
        # produce byte-for-byte identical trades (5 x 10pp = 50pp always exhausts BOTH
        # a 70% and a 50% non-core bucket the same way, with the leftover just rolling
        # into the same final sale either way). Confirmed on the 2026-08-31 core-pct
        # sweep run: every equal_depletion strategy showed C30 == C50 exactly.
        sell_amount = non_core_remaining / len(target_prices)

    scan_minute_df, scan_sessions = minute_df, sessions
    scan_entry = entry
    floor = initial_stop_price
    reference_price = entry_fill  # see _downside_scan's docstring: NOT the same as floor once breakeven activates
    breakeven_activated = False
    is_continuation = False

    while True:
        stop_ts, stop_ref, stop_reason = _downside_scan(
            scan_minute_df, daily_sma, scan_entry, floor, reference_price, trail_type, scan_sessions, log,
            is_continuation, entry.entry_session_date, original_entry_fill=entry_fill,
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
            scan_minute_df, daily_sma, scan_entry, next_target, scan_sessions, log,
            is_continuation=is_continuation,
        )

        if stop_ts is None and target_ts is None:
            # _stop_wins() alone can't distinguish this from "stop_ts is None but
            # target_ts is set" (its first check fires either way) -- must be checked
            # explicitly here, or the code falls through to the "target won" branch
            # with target_ref=None and crashes. Matches the equivalent guard in
            # partial_taking.run_v3_position_management.
            return MultiPartialResult(status="STILL_OPEN_AT_DATA_END", sales=sales, audit_log=log)

        if _stop_wins(stop_ts, stop_reason, target_ts):
            if stop_ts is None:
                return MultiPartialResult(status="STILL_OPEN_AT_DATA_END", sales=sales, audit_log=log)
            leftover = round(1.0 - total_sold_pct, 6)
            fill = _slip_sub(stop_ref)
            sales.append(Sale(stop_ts, fill, leftover, stop_reason))
            log.append(f"{stop_ts}: {stop_reason} at {fill:.4f} -- final sale of remaining {leftover*100:g}% "
                       f"(no further targets reached)")
            break

        # Target(s) reached. target_ref is the ACTUAL achieved price in this bar/day (the
        # bar's open for a gap, its high for an ordinary trade-through -- see
        # find_target_reached), used here to detect every target crossed at once, not
        # just the one being searched for.
        #
        # Section 54 (gap): no orderly price discovery happened between the pre-gap and
        # post-gap price, so every crossed target fills at the SAME real gap price.
        #
        # An ordinary (non-gap) trade-through can ALSO cross more than one target within
        # a single bar/day -- confirmed real bug, 2026-08-31: the previous version filled
        # every crossed target at target_ref regardless of gap vs trade-through, which
        # for a trade-through either missed extra crossed targets entirely (target_ref
        # used to be hardcoded to the searched-for level) or, after fixing that, would
        # have overpaid every crossed target at the bar's HIGH instead of each target's
        # own resting level. A resting limit sell order at each level fills AT that level
        # as price passes through it in order -- not at a shared price.
        is_gap = is_gap_reason(target_reason)
        crossed = [tp for tp in target_prices if tp <= target_ref + 1e-9]
        last_fill = None
        for i, tp in enumerate(crossed, start=1):
            if non_core_remaining <= 1e-9:
                break
            fill_level = target_ref if is_gap else tp
            fill = _slip_sub(fill_level)
            last_fill = fill
            sell_pct = _next_sell_pct(sell_style, sell_amount, non_core_remaining)
            sales.append(Sale(target_ts, fill, sell_pct, f"{target_reason}_{i}of{len(crossed)}"))
            total_sold_pct += sell_pct
            non_core_remaining -= sell_pct

        log.append(f"{target_ts}: {len(crossed)} target(s) crossed at once "
                   f"({'gap, shared fill' if is_gap else 'trade-through, each at its own level'}), "
                   f"non-core remaining = {non_core_remaining*100:g}%")

        target_prices = target_prices[len(crossed):]
        if not breakeven_activated:
            floor = entry_fill
            breakeven_activated = True
            log.append(f"Breakeven activated: floor = {entry_fill:.4f}")
        reference_price = last_fill  # the actual traded price this phase is resuming from

        target_day = _day_of(target_ts)
        scan_minute_df, scan_sessions = restrict_to_after(minute_df, sessions, target_day, target_ts)
        scan_entry = make_continuation_entry(entry, target_ts, target_day, entry_fill)
        is_continuation = True

    realized_R = sum(s.pct_of_original * (s.price - entry_fill) for s in sales) / risk
    log.append(f"Weighted final R = {realized_R:.4f} across {len(sales)} sale(s)")
    return MultiPartialResult(status="OK", sales=sales, realized_R=realized_R, audit_log=log)
