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
SMA5_WINDOW = 5  # only used by the experimental adaptive-tighten trail type below

# Section 43-46 -- V2 trailing-stop grid (6 types)
TRAIL_TYPES = [
    "10ma_touch",
    "close_below_10ma",
    "low_of_close_below_10ma",
    "20ma_touch",
    "close_below_20ma",
    "low_of_close_below_20ma",
]

# Experimental variant (user idea 2026-09-01), NOT part of the frozen TRAIL_TYPES grid
# above -- deliberately kept separate so it can be compared head-to-head against plain
# 20ma_touch without touching any already-run V1/V2/V3/V3b grid. See
# trailing_stops.touch_level_series_with_fallback: falls back to the ADR/pct initial stop
# on any day the raw touch level is still above the position's reference price (the exact
# scenario plain 20ma_touch discards the trade for entirely -- ~16% of setups, confirmed
# on trades_v3b_screen2.parquet), switching over to the real touch level once it catches
# down below the reference price.
TRAIL_TYPE_20MA_TOUCH_ADR_FALLBACK = "20ma_touch_adr_fallback"

# Experimental (user idea 2026-09-01): "once a trade proves itself, tighten the trail
# instead of chasing a distant fixed target." The MFE distribution check on
# trades_v3b_screen2_corrected.parquet showed only 1.5% of setups ever reach +70% and
# 0.5% reach +100% -- a scheduled target rung out there would affect too few trades to
# matter, but the SAME population's winners only capture ~47% of their own peak move on
# average (avg_exit_efficiency_winners), meaning the 10MA trail is giving back a lot of
# gain on the winners that DO run. This trail type stays close_below_10ma until the
# trade closes an intraday high at or above ACTIVATION_PCT above entry, then permanently
# switches to the much tighter close_below_5ma from that point on -- only wired into the
# V3b multi-target engine (multi_partial_taking.py), which is what every strategy
# comparison in this project actually uses; not added to V1/V2/V3's single-target paths.
TRAIL_TYPE_CLOSE_BELOW_ADAPTIVE_5_10 = "close_below_adaptive_5_10"
ADAPTIVE_TIGHTEN_ACTIVATION_PCT = 0.30

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


def _evenly_spaced_ladder(start_pct: float, end_pct: float = 0.50, n_rungs: int = 5) -> list:
    """5 rungs evenly spaced from start_pct to end_pct (inclusive), e.g. start_pct=0.20 ->
    20/27.5/35/42.5/50%. Used to build the starting-point sweep below -- every ladder ends
    at the same +50% and has the same rung COUNT, varying only WHERE profit-taking starts,
    so the sweep isolates that one variable instead of confounding it with step size too."""
    step = (end_pct - start_pct) / (n_rungs - 1)
    return [round(start_pct + i * step, 6) for i in range(n_rungs)]


# Starting-point sweep (user idea, 2026-08-31): "early_start" (begins at 10%) vs
# "late_start" (begins at 30%) only tested two points -- this fills in the gaps so WHERE
# profit-taking starts is tested as its own explicit dimension, not just two anecdotal
# choices. early_start/late_start keep their original names (and exact original values)
# for continuity with earlier results; start20/start40 are the new in-between points.
V3_MULTI_TARGET_LADDERS = {
    "early_start": V3_MULTI_TARGET_PCTS,               # 10/20/30/40/50
    "start20": _evenly_spaced_ladder(0.20),             # 20/27.5/35/42.5/50
    "late_start": V3_MULTI_TARGET_PCTS_LATE_START,      # 30/35/40/45/50
    "start40": _evenly_spaced_ladder(0.40),             # 40/42.5/45/47.5/50
}

# Experimental (user idea 2026-09-01): "we're stuck with no partials past 50%... stocks
# can go up 70%" -- every ladder above stops selling non-core shares by +50%, after which
# ONLY the core_pct rider (already uncapped, exits via the trailing stop whenever that
# fires) captures further upside. This spreads the SAME rung count across a wider range
# instead, so the non-core sales themselves extend out to +100% rather than bunching up by
# +50%. NOT added to V3_MULTI_TARGET_LADDERS above (that dict is the frozen 4-ladder
# sweep) -- kept separate so it can be tested head-to-head against start40 without
# touching any already-run grid.
V3_MULTI_TARGET_LADDERS_EXTENDED_TO_100 = {
    "start40_to_100": _evenly_spaced_ladder(0.40, end_pct=1.00),  # 40/55/70/85/100
}

# Broadened strategy universe (user request, 2026-08-31): "test on the other candle
# types, that big list of possible strategies" -- the FULL V2 entry x stop x trail grid
# (60 combos) as V3b base strategies, instead of just the narrowed Top-5 V2 winners used
# above. Run via `run_batch_v3b.py --universe broad` (merged into run_batch_v3b.py
# 2026-08-31 -- was briefly its own run_batch_v3b_broad.py script).
#
# base_strategies x sell_style(2) x ladder x core_pct(3) = 360 combos per ladder. User's
# explicit choice 2026-08-31: run the FULL 4-ladder starting-point sweep here too (1,440
# combos, ~6hr), not just late_start -- see V3_MULTI_TARGET_LADDERS above for what the 4
# ladders are and why.
V3B_BROAD_BASE_STRATEGIES = [
    (entry_type, stop_type, trail_type)
    for entry_type in V2_ENTRY_TYPES
    for stop_type in V2_STOP_TYPES
    for trail_type in TRAIL_TYPES
]
assert len(V3B_BROAD_BASE_STRATEGIES) == 60, V3B_BROAD_BASE_STRATEGIES

V3B_BROAD_TARGET_LADDERS = V3_MULTI_TARGET_LADDERS

# Coarse-to-fine screening (user idea, 2026-08-31): the TRUE full grid (6 entries x 12
# stops x 6 trails x 2 sell styles x 4 ladders x 3 core_pcts = 10,368 combos) is ~40hrs,
# impractical in one sitting. Two-stage alternative that covers more ground than the
# broad universe above at LESS total cost (~3.5hr vs ~6hr):
#
# Stage 0 (free -- reuses V1's already-completed 72-combo grid, zero new compute):
# exclude only the stop types that are structurally too tight to survive to an exit
# decision at ALL, regardless of exit sophistication -- the initial stop never widens
# under V2/V3/V3b, a trailing stop or partial-taking layer can only tighten it further,
# so a stop that's already getting hit almost immediately (1-16% win rates, EV as low as
# -1.14R in the V1 grid) can't be rescued by a better exit. Confirmed via
# strategy_summary_all_72.csv: 0.5%/1%/trigger-candle-low static/structural stops are a
# clearly separate, much-worse cluster (EV -0.14 to -1.14) than everything else (EV
# -0.005 to -0.14) -- the latter group (0.25 ADR, 2% static, LOD) is close enough to
# breakeven under V1's dumb exit that a real exit could plausibly flip it positive, so
# those stay IN despite not clearing V1's profitability bar on their own.
STAGE0_EXCLUDED_STOP_TYPES = ["0.5pct_entry", "1pct_entry", "trigger_candle_low_known_at_entry"]

# Stage 1 (cheap, full breadth): the ~54 surviving entry x stop pairs x all 6 trail
# types = 324 combos, but FIXED to a single reference profit-taking config (not swept)
# -- just enough to rank which entry/stop/trail combos have real edge before committing
# full sell-style x ladder x core_pct depth to only the winners in Stage 2.
V3B_SCREEN_STAGE1_BASE_STRATEGIES = [
    (entry_type, stop_type, trail_type)
    for entry_type in ENTRY_TYPES
    for stop_type in STOP_TYPES
    if stop_type not in STAGE0_EXCLUDED_STOP_TYPES
    for trail_type in TRAIL_TYPES
]
assert len(V3B_SCREEN_STAGE1_BASE_STRATEGIES) == 54 * 6, len(V3B_SCREEN_STAGE1_BASE_STRATEGIES)

V3B_SCREEN_STAGE1_SELL_STYLES = ["equal_depletion"]
V3B_SCREEN_STAGE1_TARGET_LADDERS = {"late_start": V3_MULTI_TARGET_PCTS_LATE_START}
V3B_SCREEN_STAGE1_CORE_PCTS = [0.5]

# Stage 2 (full depth on the winners): top N strategies from Stage 1 by G_score, re-run
# with the FULL sell_style x ladder x core_pct sweep (24 combos each). N is a runtime
# --top-n flag on run_batch_v3b.py, not fixed here -- Stage 2's base_strategies are only
# known once Stage 1's actual results exist.
V3B_SCREEN_STAGE2_DEFAULT_TOP_N = 25

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
