"""
V2 trailing-stop engine (Section 43-46 of the frozen spec).

All six trail types apply ON TOP OF the same fixed initial stop V1 already computes --
the initial stop never disappears, it's the floor every trail type is bounded below by
(a trailing rule should only ever tighten protection, never loosen it).

Two design decisions made here that the spec explicitly left open (Section 44):

1. "MA touch" needs an intraday reference level, but an SMA is a closing-price
   indicator -- today's SMA literally cannot be known until today's close happens. The
   only lookahead-safe choice is YESTERDAY's finalized SMA as today's live intraday
   floor (Section 44's option (a)). Recomputed fresh every day, so it moves with the MA
   -- unlike the ratchet type below, it CAN loosen if the MA pulls back.

2. "Low of close-below-MA" (Section 46) only ever tightens: a day whose close is below
   the MA makes that day's low a new floor, and the floor never lowers afterward. This
   turns out to be a simple cumulative maximum over a masked series (see
   _ratchet_level_series), computed once for the whole daily history rather than walked
   day-by-day -- the same vectorization trick used for V1's daily-approximation exit
   scan in simulate_trade.py.

Both level types are shifted by one day before use: the level applied to day T's
intraday trading is only known as of T's market open (i.e. it reflects data through
T-1's close), which is what keeps this point-in-time safe.
"""

import numpy as np
import pandas as pd

from . import config


def ma_column_for(trail_type: str) -> str:
    return "sma20" if "20ma" in trail_type else "sma10"


def ma_window_for(trail_type: str) -> int:
    return config.SMA20_WINDOW if "20ma" in trail_type else config.SMA_WINDOW


def is_close_based(trail_type: str) -> bool:
    return trail_type in ("close_below_10ma", "close_below_20ma")


def is_touch(trail_type: str) -> bool:
    return trail_type in ("10ma_touch", "20ma_touch")


def is_ratchet(trail_type: str) -> bool:
    return trail_type in ("low_of_close_below_10ma", "low_of_close_below_20ma")


def touch_level_series(daily_sma: pd.DataFrame, ma_col: str, initial_stop: float) -> pd.Series:
    """Section 44: yesterday's finalized MA, floored at the original initial stop."""
    prior_ma = daily_sma[ma_col].shift(1)
    return prior_ma.clip(lower=initial_stop).fillna(initial_stop)


def ratchet_level_series(daily_sma: pd.DataFrame, ma_col: str, initial_stop: float, entry_date) -> pd.Series:
    """
    Section 46: cumulative max of {that day's low : that day's close < that day's MA},
    known only as of the NEXT day's open (shift(1)) and floored at the initial stop.

    `entry_date` must ALWAYS be the trade's ORIGINAL entry date, never a later
    continuation date (e.g. when a partial-taking phase 2 resumes after a target fires).
    Passing a later date here forgets any ratchet floor that was already established
    between the real entry and that later date, which can make the floor DROP relative
    to what it legitimately was before the partial -- a direct violation of "trailing
    stops never loosen" (confirmed real bug, 2026-08-31: both partial_taking.py's Phase 2
    and multi_partial_taking.py's per-target loop were passing the continuation date here
    instead of preserving the original).

    `daily_sma` covers a ticker's ENTIRE multi-year cached history, not just the life of
    this one trade -- a plain global cummax would let a qualifying low from years before
    this specific EP event (a completely different price regime) leak forward and become
    "the stop" for a trade entered later at a totally different price. Confirmed as a
    real bug via a first V2 run: FSLR's 2012 entry at ~$18 got a stop of $123 from a
    qualifying day that predated the event by years. Masking out everything before
    entry_date is what scopes the ratchet to this trade's own post-entry price action.

    Plain `.cummax()` does NOT forward-fill through NaN in pandas (verified: a NaN input
    stays NaN in the output, it doesn't carry the running max forward) -- so NaN is
    replaced with -inf first, which lets cummax propagate the real running max through
    every non-qualifying day, then the floor/fillna at the end restores real values.
    """
    after_entry = daily_sma["date"] >= entry_date
    qualifying_low = daily_sma["low"].where(after_entry & (daily_sma["close"] < daily_sma[ma_col]))
    running_ratchet = qualifying_low.fillna(-np.inf).cummax()
    level_known_at_open = running_ratchet.shift(1)
    return level_known_at_open.clip(lower=initial_stop).fillna(initial_stop)


def level_series_for(trail_type: str, daily_sma: pd.DataFrame, initial_stop: float, entry_date) -> pd.Series:
    ma_col = ma_column_for(trail_type)
    if is_touch(trail_type):
        return touch_level_series(daily_sma, ma_col, initial_stop)
    if is_ratchet(trail_type):
        return ratchet_level_series(daily_sma, ma_col, initial_stop, entry_date)
    raise ValueError(f"level_series_for() doesn't apply to close-based trail type: {trail_type}")


def run_level_based_position_management(minute_df, daily_sma, entry, level_series, sessions, log,
                                          is_continuation=False):
    """
    Shared engine for BOTH touch and ratchet trail types -- they differ only in how
    level_series was built (see level_series_for above); once it exists, "find the
    first day/bar where price crosses that day's specific level" is identical logic
    for either type. Mirrors simulate_trade._run_position_management's structure and
    vectorization approach, generalized from a single fixed stop_price to a per-day
    level.

    is_continuation=True: see simulate_trade._run_position_management's docstring --
    used by V3's Phase 2 (partial_taking.py), where the position was already open
    before this scan starts, so the Section 23 same-bar-adverse exemption on the gap
    check must not apply to the first bar considered here.

    Returns (exit_timestamp, exit_reference_price, exit_reason) or (None, None, None).
    """
    remaining_days = [d for d in sessions if d >= entry.entry_session_date]
    level_by_date = dict(zip(daily_sma["date"], level_series))

    bars = minute_df[
        minute_df["session_date"].isin(remaining_days) & (minute_df["dt_et"] >= entry.entry_timestamp)
    ].sort_values("dt_et").reset_index(drop=True)

    if not bars.empty:
        bar_levels = bars["session_date"].map(level_by_date).to_numpy(dtype=float)
        is_entry_bar = np.zeros(len(bars), dtype=bool)
        if not is_continuation:
            is_entry_bar[0] = True
        low = bars["low"].to_numpy()
        open_ = bars["open"].to_numpy()
        gap_cond = (~is_entry_bar) & (open_ <= bar_levels)
        trade_cond = low <= bar_levels
        stop_hit = gap_cond | trade_cond
        if stop_hit.any():
            idx = int(stop_hit.argmax())
            ts = bars["dt_et"].iloc[idx]
            level_here = float(bar_levels[idx])
            if is_entry_bar[idx]:
                log.append(
                    f"{ts}: entry bar's own low ({low[idx]:.4f}) <= trailing level "
                    f"({level_here:.4f}) -- same-bar ambiguity, adverse assumption applied"
                )
                return ts, level_here, "STOPPED_SAME_BAR_AS_ENTRY"
            if gap_cond[idx]:
                log.append(f"{ts}: session open ({float(open_[idx]):.4f}) already through trailing level ({level_here:.4f}) -- gap-through")
                return ts, float(open_[idx]), "STOPPED_GAP_THROUGH"
            log.append(f"{ts}: traded through trailing level ({level_here:.4f})")
            return ts, level_here, "STOPPED_TRADE_THROUGH"

    log.append(f"Position survived through {sessions[-1]} (end of cached minute window) -- switching to daily-bar approximation")
    after = daily_sma[daily_sma["date"] > sessions[-1]].sort_values("date").reset_index(drop=True)
    if after.empty:
        return None, None, None

    after_levels = after["date"].map(level_by_date).astype(float)
    gap_through = after["open"] <= after_levels
    trade_through = after["low"] <= after_levels
    any_exit = gap_through | trade_through
    if not any_exit.any():
        return None, None, None

    pos = int(any_exit.to_numpy().argmax())
    row = after.iloc[pos]
    if gap_through.iloc[pos]:
        return row["date"], row["open"], "STOPPED_GAP_THROUGH_DAILY_APPROX"
    return row["date"], float(after_levels.iloc[pos]), "STOPPED_TRADE_THROUGH_DAILY_APPROX"
