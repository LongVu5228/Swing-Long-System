"""
V1 frozen constants -- see Swing_Long_EP_Backtest_Master_Context_FROZEN_V1_2026-08-30.md
for the source spec. Every number here traces back to a numbered section of that doc;
do not change a value here without updating the doc (or vice versa).
"""

import zoneinfo

ET = zoneinfo.ZoneInfo("America/New_York")

# Section 76
SESSION_OPEN = "09:30:00"
SESSION_CLOSE = "16:00:00"

# Section 9 -- opening-range durations in minutes
ENTRY_TYPES = ["1m", "5m", "10m", "15m", "30m", "60m"]
ENTRY_MINUTES = {"1m": 1, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60}

# Section 12 -- pending entry window, D0 through D+7 inclusive (8 sessions)
MAX_ENTRY_DAY_OFFSET = 7

# Section 18 -- V1 initial-stop grid (12 types)
STATIC_PCT_STOPS = [0.005, 0.01, 0.02, 0.03, 0.05]
ADR_MULTIPLIERS = {
    "0.25adr": 0.25,
    "0.333333adr": 1 / 3,
    "0.50adr": 0.50,
    "1.00adr": 1.00,
    "2.00adr": 2.00,
}
STRUCTURAL_STOPS = ["lod_known_at_entry", "trigger_candle_low_known_at_entry"]

STOP_TYPES = (
    [f"{p * 100:g}pct_entry" for p in STATIC_PCT_STOPS]
    + STRUCTURAL_STOPS
    + list(ADR_MULTIPLIERS.keys())
)

assert len(ENTRY_TYPES) == 6
assert len(STOP_TYPES) == 12, STOP_TYPES

# Section 26-27 -- V1 standardized exit
SMA_WINDOW = 10

# Section 60.1 -- V1 slippage placeholder: 1% of the relevant reference price
SLIPPAGE_PCT = 0.01

# Section 80 -- tick size
TICK_SIZE = 0.01

# Trade / event status codes (Section 74)
STATUS_VALID_TRADE = "VALID_TRADE"
STATUS_NO_ENTRY = "NO_ENTRY"
STATUS_INELIGIBLE_NO_10SMA = "INELIGIBLE_NO_10SMA_HISTORY"
STATUS_MISSING_MINUTE_DATA = "MISSING_MINUTE_DATA"
STATUS_MISSING_DAILY_DATA = "MISSING_DAILY_DATA"
STATUS_INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
STATUS_CORRUPT_EVENT = "CORRUPT_EVENT"
STATUS_EXIT_DATA_GAP = "EXIT_DATA_GAP"  # daily bars stop before a 10SMA exit fires (delisting/halt)

# Paths
import os

_THIS_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # Files/EP/Backtesting
EP_V5_XLSX = os.path.normpath(os.path.join(_THIS_DIR, "..", "EP V5.xlsx"))
EP_V5_SHEET = "Data"

CACHE_DIR = os.path.join(_THIS_DIR, "data_cache")
DAILY_BARS_DIR = os.path.join(CACHE_DIR, "daily_bars")
MINUTE_BARS_DIR = os.path.join(CACHE_DIR, "minute_bars")
EVENTS_PARQUET = os.path.join(CACHE_DIR, "ep_v5_events.parquet")

OUTPUTS_DIR = os.path.join(_THIS_DIR, "outputs")
