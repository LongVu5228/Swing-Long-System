"""V1 standardized exit: first finalized daily close below the 10-day SMA (Section 26-29)."""

import pandas as pd

from . import config


def add_sma10(daily_df: pd.DataFrame) -> pd.DataFrame:
    """
    Trailing 10-period SMA of daily closes, computed over the WHOLE series (pre-event
    history included) so there's no artificial warm-up gap right at the event -- this
    is a rolling window, so sma10 on day t only ever uses closes up to and including t
    (point-in-time safe).
    """
    df = daily_df.sort_values("date").reset_index(drop=True).copy()
    df["sma10"] = df["close"].rolling(config.SMA_WINDOW).mean()
    return df


def has_sufficient_history(daily_df_with_sma: pd.DataFrame, as_of_date) -> bool:
    """Section 29: event is ineligible if sma10 isn't defined by the given date."""
    row = daily_df_with_sma[daily_df_with_sma["date"] == as_of_date]
    if row.empty:
        return False
    return bool(pd.notna(row["sma10"].iloc[0]))
