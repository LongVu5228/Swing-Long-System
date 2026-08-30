"""V1 initial-stop grid: 12 stop types (Section 18-22, 31)."""

from dataclasses import dataclass
from typing import Optional

from . import config
from .entry import EntryResult


@dataclass
class StopResult:
    stop_type: str
    stop_price: Optional[float]
    valid: bool
    reason: Optional[str] = None  # set when invalid


def compute_initial_stop(stop_type: str, entry: EntryResult, adr14: Optional[float]) -> StopResult:
    entry_fill = entry.entry_fill

    if stop_type.endswith("pct_entry"):
        pct = float(stop_type.replace("pct_entry", "")) / 100.0
        stop_price = entry_fill * (1 - pct)  # Section 19
    elif stop_type == "lod_known_at_entry":
        stop_price = entry.lod_known_at_entry
    elif stop_type == "trigger_candle_low_known_at_entry":
        stop_price = entry.trigger_candle_low_known_at_entry
    elif stop_type in config.ADR_MULTIPLIERS:
        if adr14 is None or pd_isna(adr14):
            return StopResult(stop_type, None, False, "missing_adr14")
        multiplier = config.ADR_MULTIPLIERS[stop_type]
        stop_price = entry_fill * (1 - adr14 * multiplier)  # Section 20
    else:
        raise ValueError(f"Unknown stop_type: {stop_type}")

    if stop_price is None:
        return StopResult(stop_type, None, False, "missing_structural_reference")

    # Section 31: guard against nonsensical geometry.
    risk = entry_fill - stop_price
    if stop_price >= entry_fill or risk <= 0:
        return StopResult(stop_type, stop_price, False, config.STATUS_INVALID_STOP_GEOMETRY)

    return StopResult(stop_type, round(stop_price, 4), True)


def pd_isna(x) -> bool:
    try:
        import math
        return x is None or math.isnan(x)
    except TypeError:
        return x is None
