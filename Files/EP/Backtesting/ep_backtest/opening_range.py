"""Opening-range high computation (Section 9-11)."""

from datetime import datetime, timedelta

import pandas as pd

from . import config


def session_open_ts(session_date, tz=config.ET):
    return datetime.combine(session_date, datetime.min.time(), tzinfo=tz).replace(hour=9, minute=30)


def opening_range_high(minute_df: pd.DataFrame, d0, entry_type: str) -> tuple[float, "datetime"]:
    """
    Section 9-10: OR high from D0's first `entry_type`-duration candle, bucketed by
    wall-clock time from the session open (matches Scripts/build_v2_intraday.py's
    convention -- sparse/no-trade minutes don't shift the window).

    Returns (or_high, window_end_ts). Raises ValueError if D0 has no regular-session
    bars in that window (can't define a trigger -> event ineligible for this entry type).
    """
    minutes = config.ENTRY_MINUTES[entry_type]
    open_ts = session_open_ts(d0)
    window_end = open_ts + timedelta(minutes=minutes)

    d0_bars = minute_df[minute_df["session_date"] == d0]
    window = d0_bars[(d0_bars["dt_et"] >= open_ts) & (d0_bars["dt_et"] < window_end)]
    if window.empty:
        raise ValueError(f"No D0 bars in the {entry_type} opening-range window ({open_ts}..{window_end})")

    return float(window["high"].max()), window_end
