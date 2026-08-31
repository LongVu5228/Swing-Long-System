"""
Post-hoc trade metrics that don't affect any exit decision -- computed once a trade has
fully resolved, purely for analysis. Max favorable excursion (MFE) and exit efficiency
were both already anticipated in the frozen spec (Section 33/89: max_favorable_R,
MFE_R) but never implemented.

Exit efficiency = realized_R / max_favorable_R answers "how much of the best price this
trade ever reached did we actually capture by the time we were fully out?" A value near
1.0 means the exit was well-timed; a value near 0 (or negative) means most or all of the
peak gain was given back before the final exit.
"""

from typing import Optional

import pandas as pd


def compute_max_favorable_r(
    minute_df: pd.DataFrame,
    daily_sma: pd.DataFrame,
    entry_timestamp,
    entry_session_date,
    exit_timestamp,
    entry_fill: float,
    risk: float,
) -> Optional[float]:
    """
    The best price reached at ANY point from entry through the trade's final exit,
    expressed as an R-multiple of the frozen initial risk -- independent of how much of
    the position was still open at that moment (a pure price statistic, not a
    size-weighted one; the standard MFE definition).

    `exit_timestamp` is the RAW exit event (whatever the caller's own result stores) --
    either a tz-aware intraday Timestamp (a real minute-precision fill) or a plain date
    (a close-based exit, inherently end-of-day, or a daily-bar-approximation fallback
    beyond the D0-D+7 minute-cached window -- Section 78). Passing a bare date here and
    letting every day through it use the FULL day's high (including price action AFTER
    an intraday exit that same day) was a real bug, confirmed 2026-08-31: a trade that
    stopped out at 10am on some later day but the stock spiked at 2pm that same day had
    that afternoon spike counted toward its own MFE, silently understating
    exit_efficiency on every intraday exit.

    Entry day: minute-bar highs from entry_timestamp onward, capped at exit_timestamp too
    if the trade both entered AND exited the same day. Days strictly between entry and
    exit: the full daily high (the position was open the whole day, no cap needed). The
    exit day itself (when after the entry day): capped at exit_timestamp using minute
    bars IF they're cached for that day (D0-D+7) -- otherwise (a close-based end-of-day
    exit, which genuinely was exposed to the whole day, or a daily-approximation exit
    beyond the minute-cached window, where no finer data exists at all) the full day's
    high is used, same as before.
    """
    has_exit_time = hasattr(exit_timestamp, "date")  # tz-aware Timestamp => a real intraday moment is known
    exit_date = exit_timestamp.date() if has_exit_time else exit_timestamp

    entry_day_mask = (minute_df["session_date"] == entry_session_date) & (minute_df["dt_et"] >= entry_timestamp)
    if has_exit_time and exit_date == entry_session_date:
        entry_day_mask &= minute_df["dt_et"] <= exit_timestamp
    entry_day_bars = minute_df[entry_day_mask]
    peak = float(entry_day_bars["high"].max()) if not entry_day_bars.empty else entry_fill

    between_days = daily_sma[(daily_sma["date"] > entry_session_date) & (daily_sma["date"] < exit_date)]
    if not between_days.empty:
        peak = max(peak, float(between_days["high"].max()))

    if exit_date > entry_session_date:
        exit_day_minute_bars = (
            minute_df[(minute_df["session_date"] == exit_date) & (minute_df["dt_et"] <= exit_timestamp)]
            if has_exit_time else minute_df.iloc[0:0]
        )
        if not exit_day_minute_bars.empty:
            peak = max(peak, float(exit_day_minute_bars["high"].max()))
        else:
            exit_day_row = daily_sma[daily_sma["date"] == exit_date]
            if not exit_day_row.empty:
                peak = max(peak, float(exit_day_row["high"].iloc[0]))

    if risk <= 0:
        return None
    return (peak - entry_fill) / risk


def compute_exit_efficiency(realized_R: Optional[float], max_favorable_R: Optional[float]) -> Optional[float]:
    """None when there's no meaningful peak to measure against (MFE <= 0 -- the trade
    never moved favorably at all, e.g. an immediate stop-out)."""
    if realized_R is None or max_favorable_R is None or max_favorable_R <= 1e-9:
        return None
    return realized_R / max_favorable_R
