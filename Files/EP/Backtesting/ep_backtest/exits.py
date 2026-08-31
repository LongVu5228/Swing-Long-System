"""
V1 standardized exit: first finalized daily close below the 10-day SMA (Section 26-29).
V2 trailing-stop variants (Section 43-46) live in trailing_stops.py and build on the
sma10/sma20 columns added here.
"""

import pandas as pd

from . import config


def add_sma10(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Trailing 10-period AND 20-period SMA of daily closes (V2 needs both), computed over
    the WHOLE series (pre-event history included) so there's no artificial warm-up gap
    right at the event -- these are rolling windows, so sma10/sma20 on day t only ever
    use closes up to and including t (point-in-time safe). Kept the name `add_sma10` for
    backward compatibility with existing V1 call sites; it now also adds sma20.
    """
    df = daily_df.sort_values("date").reset_index(drop=True).copy()
    df["sma10"] = df["close"].rolling(config.SMA_WINDOW).mean()
    df["sma20"] = df["close"].rolling(config.SMA20_WINDOW).mean()
    return df


def has_sufficient_history(daily_df_with_sma: pd.DataFrame, as_of_date, window: int = None) -> bool:
    """Section 29: event is ineligible if the relevant SMA isn't defined by the given date."""
    col = "sma10" if window in (None, config.SMA_WINDOW) else "sma20"
    row = daily_df_with_sma[daily_df_with_sma["date"] == as_of_date]
    if row.empty:
        return False
    return bool(pd.notna(row[col].iloc[0]))
