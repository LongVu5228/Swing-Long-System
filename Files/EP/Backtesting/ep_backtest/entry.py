"""
Entry search: fixed D0 opening-range-high trigger, valid through D+7, searched at
1-minute resolution (Section 9-17, 79).
"""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional

import pandas as pd

from . import config
from .opening_range import opening_range_high, session_open_ts


@dataclass
class EntryResult:
    entry_status: str  # "VALID_TRADE" or "NO_ENTRY"
    or_high: float
    trigger: float
    entry_timestamp: Optional[datetime] = None
    entry_day_offset: Optional[int] = None
    entry_session_date: Optional[date] = None
    entry_fill: Optional[float] = None
    fill_reason: Optional[str] = None  # "normal_trade_through" | "gap_through"
    entry_bar_index: Optional[int] = None  # position of the entry bar within minute_df
    lod_known_at_entry: Optional[float] = None
    trigger_candle_low_known_at_entry: Optional[float] = None


def _round_tick(price: float) -> float:
    return round(round(price / config.TICK_SIZE) * config.TICK_SIZE, 2)


def find_entry(minute_df: pd.DataFrame, d0: date, sessions: list, entry_type: str) -> EntryResult:
    """
    sessions: the 8 trading-session dates D0..D+7 (from calendar_utils.sessions_from).
    minute_df: regular-session 1-minute bars covering exactly those 8 sessions.
    """
    or_high, window_end = opening_range_high(minute_df, d0, entry_type)
    trigger = _round_tick(or_high + config.TICK_SIZE)

    # Section 16: no fill can occur inside the defining OR candle itself -- search starts
    # strictly at the first bar after the OR window completes.
    candidates = minute_df[minute_df["dt_et"] >= window_end].reset_index(drop=True)

    session_offset = {s: i for i, s in enumerate(sessions)}
    minutes = config.ENTRY_MINUTES[entry_type]

    for i, bar in candidates.iterrows():
        session_date = bar["session_date"]
        if session_date not in session_offset:
            continue  # shouldn't happen given how minute_df is scoped, but stay safe

        if bar["open"] > trigger:
            fill_reason = "gap_through"
            ref_price = float(bar["open"])
        elif bar["high"] >= trigger:
            fill_reason = "normal_trade_through"
            ref_price = trigger
        else:
            continue

        slip = config.SLIPPAGE_PCT * ref_price
        entry_fill = round(ref_price + slip, 4)

        # Section 21: LOD known at entry = this session's low, from that session's open
        # through and including the entry bar.
        day_bars = minute_df[minute_df["session_date"] == session_date]
        so_far = day_bars[day_bars["dt_et"] <= bar["dt_et"]]
        lod_known = float(so_far["low"].min())

        # Section 22/79: trigger-candle low = low of the same-duration bucket (anchored
        # at that session's own 9:30 open) containing the entry bar, through the entry
        # bar only.
        day_open = session_open_ts(session_date)
        elapsed_min = (bar["dt_et"] - day_open).total_seconds() / 60.0
        bucket_idx = int(elapsed_min // minutes)
        bucket_start = day_open + pd.Timedelta(minutes=bucket_idx * minutes)
        bucket_so_far = day_bars[(day_bars["dt_et"] >= bucket_start) & (day_bars["dt_et"] <= bar["dt_et"])]
        trigger_candle_low = float(bucket_so_far["low"].min())

        return EntryResult(
            entry_status=config.STATUS_VALID_TRADE,
            or_high=or_high,
            trigger=trigger,
            entry_timestamp=bar["dt_et"],
            entry_day_offset=session_offset[session_date],
            entry_session_date=session_date,
            entry_fill=entry_fill,
            fill_reason=fill_reason,
            entry_bar_index=i,
            lod_known_at_entry=lod_known,
            trigger_candle_low_known_at_entry=trigger_candle_low,
        )

    return EntryResult(entry_status=config.STATUS_NO_ENTRY, or_high=or_high, trigger=trigger)
