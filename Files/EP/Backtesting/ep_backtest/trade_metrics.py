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
    exit_date,
    entry_fill: float,
    risk: float,
) -> Optional[float]:
    """
    The best price reached at ANY point from entry through the trade's final exit,
    expressed as an R-multiple of the frozen initial risk -- independent of how much of
    the position was still open at that moment (a pure price statistic, not a
    size-weighted one; the standard MFE definition).

    Entry day uses minute-bar highs (only from entry_timestamp onward -- a trade can't
    have "run up" before it was entered). Every day after that through exit_date uses
    the daily high directly; daily resolution is sufficient there since the goal is just
    "what was the peak price," not an intrabar-precise fill.
    """
    entry_day_bars = minute_df[
        (minute_df["session_date"] == entry_session_date) & (minute_df["dt_et"] >= entry_timestamp)
    ]
    peak = float(entry_day_bars["high"].max()) if not entry_day_bars.empty else entry_fill

    later_days = daily_sma[(daily_sma["date"] > entry_session_date) & (daily_sma["date"] <= exit_date)]
    if not later_days.empty:
        peak = max(peak, float(later_days["high"].max()))

    if risk <= 0:
        return None
    return (peak - entry_fill) / risk


def compute_exit_efficiency(realized_R: Optional[float], max_favorable_R: Optional[float]) -> Optional[float]:
    """None when there's no meaningful peak to measure against (MFE <= 0 -- the trade
    never moved favorably at all, e.g. an immediate stop-out)."""
    if realized_R is None or max_favorable_R is None or max_favorable_R <= 1e-9:
        return None
    return realized_R / max_favorable_R
