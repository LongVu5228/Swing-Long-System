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
SMA20_WINDOW = 20

# Section 43-46 -- V2 trailing-stop grid (6 types)
TRAIL_TYPES = [
    "10ma_touch",
    "close_below_10ma",
    "low_of_close_below_10ma",
    "20ma_touch",
    "close_below_20ma",
    "low_of_close_below_20ma",
]

# Section 86 -- V2 carries forward the strong V1 region, not the full 72-combo grid.
# Chosen 2026-08-30: the entries/stops that were consistently positive across BOTH of
# the strongest V1 entry timeframes (30m, 60m) at 0.1% slippage.
V2_ENTRY_TYPES = ["30m", "60m"]
V2_STOP_TYPES = ["0.25adr", "0.333333adr", "0.50adr", "1.00adr", "3pct_entry"]

# V3 (Section 47-55) carries forward the Top-5 V2 strategies by G Score, not the full
# V2 grid -- (entry_type, stop_type, trail_type) tuples, chosen 2026-08-30.
V3_BASE_STRATEGIES = [
    ("60m", "3pct_entry", "20ma_touch"),
    ("60m", "3pct_entry", "low_of_close_below_20ma"),
    ("60m", "3pct_entry", "close_below_20ma"),
    ("60m", "0.50adr", "20ma_touch"),
    ("30m", "3pct_entry", "low_of_close_below_20ma"),
]
# User-confirmed choices (2026-08-30): Type-A single-sale profit target, 50/50 core.
V3_TARGET_PCTS = [0.10, 0.15, 0.20, 0.30, 0.50]
V3_CORE_PCT = 0.5

# Core/non-core split sweep (user idea, 2026-08-31): don't assume 50/50 is right --
# compare a core-heavy split (70% core, only 30% sold off via targets -- rides winners
# harder) against a non-core-heavy split (30% core, 70% sold off via targets -- banks
# profit earlier/more aggressively) against the original 50/50. Used by V3b's batch
# runner; V3 (single-sale) still uses the fixed V3_CORE_PCT above.
V3_CORE_PCTS = [0.3, 0.5, 0.7]

# V3b: multi-target staged partials (Section 50/52/53/54), user-confirmed 2026-08-30 --
# targets every 10% from entry up to 50%, both sell styles tested side by side. Same
# 50/50 core as V3.
V3_MULTI_TARGET_PCTS = [0.10, 0.20, 0.30, 0.40, 0.50]
# equal_depletion: this is the per-target sell size ONLY at the original 50/50 core
# split (10pp x 5 targets exactly exhausts a 50% non-core). At other core_pct values in
# the sweep below, multi_partial_taking.py recomputes the actual per-target size as
# (1 - core_pct) / n_targets so every split's ladder still exactly exhausts its own
# non-core bucket -- see that module's docstring (2026-08-31 fix).
V3_MULTI_SELL_AMOUNT_EQUAL = 0.10
# exponential_remaining: sell this fraction of whatever non-core REMAINS at each target
# crossed. Chosen so the FIRST sale matches equal_depletion's exactly (20% of the
# initial 50% non-core = 10pp), making the two styles directly comparable on their
# opening move -- every sale after that is smaller for exponential, tapering off.
V3_MULTI_SELL_AMOUNT_EXPONENTIAL = 0.20

# Alternate target ladder (user idea, 2026-08-31): don't take any profit until the move
# has proven itself -- no rungs below 30%, then 5% steps. Same rung COUNT (5) and the
# same per-rung sell_amount constants above, so this is an apples-to-apples comparison
# against V3_MULTI_TARGET_PCTS -- only WHEN profit-taking starts changes, not how much
# gets sold per rung.
V3_MULTI_TARGET_PCTS_LATE_START = [0.30, 0.35, 0.40, 0.45, 0.50]

V3_MULTI_TARGET_LADDERS = {
    "early_start": V3_MULTI_TARGET_PCTS,
    "late_start": V3_MULTI_TARGET_PCTS_LATE_START,
}

# Broadened strategy universe (user request, 2026-08-31): "test on the other candle
# types, that big list of possible strategies" -- the FULL V2 entry x stop x trail grid
# (60 combos) as V3b base strategies, instead of just the narrowed Top-5 V2 winners used
# above. Run via run_batch_v3b_broad.py, NOT run_batch_v3b.py (which keeps using the
# narrow Top-5 list, unchanged, for backward comparability with earlier results).
#
# Scoped down from the full sell-style x ladder x core cross product to keep runtime
# bounded (~1.5hr vs ~3hr for the full 60x2x2x3=720 cross product, user's explicit
# choice 2026-08-31): late_start only, since it beat early_start on EVERY one of the 5
# original base strategies x 2 sell styles already tested -- not worth re-proving at
# 12x the base-strategy count. Full sell-style x core_pct sweep is kept.
V3B_BROAD_BASE_STRATEGIES = [
    (entry_type, stop_type, trail_type)
    for entry_type in V2_ENTRY_TYPES
    for stop_type in V2_STOP_TYPES
    for trail_type in TRAIL_TYPES
]
assert len(V3B_BROAD_BASE_STRATEGIES) == 60, V3B_BROAD_BASE_STRATEGIES

V3B_BROAD_TARGET_LADDERS = {"late_start": V3_MULTI_TARGET_PCTS_LATE_START}

# Section 60.1 -- V1 slippage placeholder: 0.1% of the relevant reference price.
# Revised down from an initial 1% (2026-08-30) after the first full-universe V1 run
# showed 1% + 1% round-trip slippage exceeded the width of the 0.5%/1% static stops
# outright, mechanically forcing a 0% win rate on those rows regardless of the entries'
# actual quality. 0.1% keeps the round-trip cost (~0.2%) comfortably below even the
# tightest stop while still penalizing thin stops relative to wide ones.
SLIPPAGE_PCT = 0.001

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
