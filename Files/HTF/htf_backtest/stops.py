"""
HTF initial-stop grid (13 types, §12). Returns a stop PRICE; simulate.py hands it to EP's engine
as an equivalent "<pct>pct_entry" stop so EP's compute_initial_stop / geometry guard (Section 31)
and everything downstream run unchanged.

  2/3/4/5pct_entry          entry_fill * (1 - pct)
  0.33/0.50/0.75/1.00/1.50adr  entry_fill * (1 - mult * ADR14), ADR14 = (mean high - mean low)
                            over the 14 sessions BEFORE the entry session / prior close (the HTF
                            daily backtest's formula; EP's adr14_pregap analogue)
  low_10d                   lowest low of the 10 sessions before the entry session
  last_higher_low           most recent swing low (low <= both neighbours) whose next session is
                            still before the entry session, within 30 sessions -- price-only, no
                            box clicks (user 2026-11-11: flag clicks are too inconsistent)
  lod_known_at_entry        session low up to the entry bar, capped at entry * (1 - 1%)
  trigger_candle_low...     low of the entry's own candle bucket up to the entry bar, same 1% cap
The 1% minimum risk on the two intraday stops exists because a breakout that opens just under R1
gives a LOD a few cents below entry and an absurd R (+394R artifact on daily bars, §2).
Every function only reads data strictly before the entry session or up to the entry bar.
"""

from typing import Optional

import numpy as np
import pandas as pd

from . import config


def adr14(daily_sma: pd.DataFrame, entry_date) -> Optional[float]:
    prior = daily_sma[daily_sma.date < entry_date].tail(15)
    if len(prior) < 15:
        return None
    w = prior.tail(14)
    return float((w.high.mean() - w.low.mean()) / prior.close.iloc[-1])


def stop_price(stop_type: str, entry, daily_sma: pd.DataFrame) -> Optional[float]:
    fill, d = entry.entry_fill, entry.entry_session_date
    if stop_type.endswith("pct_entry"):
        return fill * (1 - float(stop_type.replace("pct_entry", "")) / 100)
    if stop_type in config.ADR_MULTIPLIERS:
        a = adr14(daily_sma, d)
        return None if a is None else fill * (1 - config.ADR_MULTIPLIERS[stop_type] * a)
    before = daily_sma[daily_sma.date < d]
    if stop_type == "low_10d":
        return float(before.tail(10).low.min()) if len(before) >= 10 else None
    if stop_type == "last_higher_low":
        lows = before.tail(31).low.to_numpy()
        for j in range(len(lows) - 2, 0, -1):          # j+1 must exist and be before entry
            if lows[j] <= lows[j - 1] and lows[j] <= lows[j + 1] and lows[j] < fill:
                return float(lows[j])
        return None
    cap = fill * (1 - config.LOD_MIN_RISK_PCT)
    if stop_type == "lod_known_at_entry":
        return min(entry.lod_known_at_entry, cap)
    if stop_type == "trigger_candle_low_known_at_entry":
        return min(entry.trigger_candle_low_known_at_entry, cap)
    raise ValueError(f"unknown stop_type {stop_type}")


def as_ep_stop_type(price: float, fill: float) -> str:
    """Express any stop price as EP's generic percent stop (exact to float precision)."""
    return f"{(1 - price / fill) * 100:.10f}pct_entry"
