"""
NYSE trading-session calendar helpers.

Uses pandas_market_calendars rather than a hand-rolled calendar. A hand-rolled NYSE
calendar in this same project (Scripts/build_benzinga_candidate_list.py) previously had
a bug where any date before the calendar's start silently snapped to index 0 instead of
raising -- it corrupted 43% of a 245k-row dataset before being caught. The bounds checks
here exist specifically to fail loudly instead of repeating that failure mode.
"""

from datetime import date

import pandas as pd
import pandas_market_calendars as mcal

CALENDAR_START = "2000-01-01"  # comfortably before EP V5's earliest event (2012-05-15)
CALENDAR_END = "2035-12-31"    # comfortably past any realistic run date

_NYSE = mcal.get_calendar("NYSE")
_SCHEDULE = _NYSE.schedule(start_date=CALENDAR_START, end_date=CALENDAR_END)
TRADING_DAYS = pd.DatetimeIndex(_SCHEDULE.index.date)


def _check_bounds(d: date):
    if d < TRADING_DAYS[0].date() or d > TRADING_DAYS[-1].date():
        raise ValueError(
            f"{d} is outside the trading calendar bounds "
            f"[{TRADING_DAYS[0].date()}, {TRADING_DAYS[-1].date()}]. "
            "Widen CALENDAR_START/CALENDAR_END rather than letting this fail silently."
        )


def is_trading_day(d: date) -> bool:
    _check_bounds(d)
    return d in set(TRADING_DAYS.date)


def sessions_from(d: date, n: int) -> list[date]:
    """
    Return the n trading sessions starting at-or-after d, inclusive of d itself if d is
    a trading day. sessions_from(d, 8) gives D0..D+7 (8 sessions) when d == D0.
    """
    _check_bounds(d)
    pos = TRADING_DAYS.searchsorted(pd.Timestamp(d), side="left")
    if pos >= len(TRADING_DAYS):
        raise ValueError(f"No trading sessions on/after {d} within calendar bounds.")
    out = TRADING_DAYS[pos : pos + n]
    if len(out) < n:
        raise ValueError(
            f"Only {len(out)} trading sessions available on/after {d}, needed {n}. "
            "Widen CALENDAR_END."
        )
    return [ts.date() for ts in out]


def next_session_after(d: date) -> date:
    """First trading session strictly after d (used for gap-through fills on D+1, etc.)."""
    _check_bounds(d)
    pos = TRADING_DAYS.searchsorted(pd.Timestamp(d), side="right")
    if pos >= len(TRADING_DAYS):
        raise ValueError(f"No trading session after {d} within calendar bounds.")
    return TRADING_DAYS[pos].date()
