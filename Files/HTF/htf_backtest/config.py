"""
HTF strategy-matrix constants (2026-11-13). Source spec: Files/HTF/HTF_Backtest_Findings_CURRENT.md
§12 (grid), §13 (validation), §16 (game plan). Every grid value here traces back to that doc;
change both together.

Built in the style of Files/EP/Backtesting/ep_backtest/ (the engine that worked): one package,
one config, dataclass results with an audit log, status codes instead of silent drops,
parquet caches under one data dir, run with the repo .venv (pyarrow 25 / pandas 3), never the
stray global python (it can't read this project's parquet). Generic position-management
pieces (trailing stops, staged partials, MFE / exit efficiency) are IMPORTED from ep_backtest
rather than re-written -- they carry fixes for ~8 real bugs found during EP validation.
"""

import os
import sys
import zoneinfo

HERE = os.path.dirname(os.path.abspath(__file__))
HTF_DIR = os.path.dirname(HERE)
REPO = os.path.abspath(os.path.join(HTF_DIR, "..", ".."))
ADV = os.path.join(HTF_DIR, "Advanced Backtesting")          # annotation pipeline (master, exports)
EP_BACKTESTING = os.path.join(REPO, "Files", "EP", "Backtesting")

# make ep_backtest and the annotation helpers importable
for p in (EP_BACKTESTING, ADV):
    if p not in sys.path:
        sys.path.insert(0, p)

DATA_DIR = os.path.join(HTF_DIR, "backtest_data")
MINUTE_BARS_DIR = os.path.join(DATA_DIR, "minute_bars")
MINUTE_MANIFEST = os.path.join(DATA_DIR, "minute_manifest.csv")
OUTPUTS_DIR = os.path.join(HTF_DIR, "backtest_outputs")

ET = zoneinfo.ZoneInfo("America/New_York")
SESSION_OPEN = "09:30:00"
SESSION_CLOSE = "16:00:00"
TICK_SIZE = 0.01
SLIPPAGE_PCT = float(os.environ.get("HTF_SLIPPAGE", "0.001"))  # per fill; env override for the gauntlet. EP's revised placeholder (0.1%/fill); 1% made tight stops 0% WR artifacts

# Minute-data window per flag: setup_confirmed session through the session on/before
# final_flag_end, plus POST_SESSIONS more (entry day + ~2 weeks after it at 1-min resolution,
# daily bars after that -- EP's D0..D+7 minute / daily-after split, widened for HTF).
POST_SESSIONS = 10
MERGE_GAP_SESSIONS = 5        # flags on one ticker closer than this share one pull
CHECK_TOL = 0.02              # minute->daily rollup vs TradingView close: >2% = suspect window

# Development sample (§16): flags charted through list row 1,051 (DKNG). Rows charted later
# are the held-out test set -- never tune on them.
DEV_LAST_TICKER = "DKNG"

# --- Grid (§12) ---
OR_ENTRY_TYPES = ["1m", "5m", "10m", "15m", "30m", "60m"]
OR_MINUTES = {"1m": 1, "5m": 5, "10m": 10, "15m": 15, "30m": 30, "60m": 60}
DAILY_ENTRY_TYPES = ["r1_cross", "close_above_r1", "next_open_after_close"]
ENTRY_TYPES = OR_ENTRY_TYPES + DAILY_ENTRY_TYPES
# entry-rule test (2026-11-23, run_stage2 --stage entry), kept out of the 936 grid:
ORB_ABOVE_MINUTES = {"orb30": 30}                        # OR high must be > R1, buy-stop at OR high + tick
BARCLOSE_MINUTES = {"c5m": 5, "c10m": 10, "c15m": 15}    # first N-min bar closing above R1, filled at its close
# user idea 2026-11-24: each day the first N-min candle that trades above R1; once it closes, buy-stop at its high + tick
XCROSS_MINUTES = {"xc5m": 5, "xc15m": 15, "xc30m": 30}

STATIC_PCT_STOPS = [0.02, 0.03, 0.04, 0.05]
ADR_MULTIPLIERS = {"0.33adr": 1 / 3, "0.50adr": 0.50, "0.75adr": 0.75, "1.00adr": 1.00, "1.50adr": 1.50}
STRUCTURE_STOPS = ["low_10d", "last_higher_low"]               # price-only; no flag-low (box clicks vary)
INTRADAY_STOPS = ["lod_known_at_entry", "trigger_candle_low_known_at_entry"]
LOD_MIN_RISK_PCT = 0.01      # raw LOD made a +394R artifact on daily bars
STOP_TYPES = ([f"{p * 100:g}pct_entry" for p in STATIC_PCT_STOPS] + list(ADR_MULTIPLIERS)
              + STRUCTURE_STOPS + INTRADAY_STOPS)

TRAIL_TYPES = ["close_below_10ma", "close_below_20ma", "10ma_touch", "20ma_touch",
               "low_of_close_below_10ma", "low_of_close_below_20ma",
               "close_below_adaptive_5_10", "20ma_touch_adr_fallback"]

assert len(ENTRY_TYPES) == 9 and len(STOP_TYPES) == 13 and len(TRAIL_TYPES) == 8

# G-score re-based for HTF (EP's 0.30R / PF 2.0 caps saturate on HTF)
G_EV_CAP, G_PF_CAP = 1.0, 3.0

# Status codes (EP style: every non-trade is labeled, never silently dropped)
STATUS_OK = "OK"
STATUS_NO_ENTRY = "NO_ENTRY"
STATUS_NO_LEVEL = "NO_LEVEL"                       # flag has no R1
STATUS_MISSING_MINUTE_DATA = "MISSING_MINUTE_DATA"
STATUS_MINUTE_MISMATCH = "MINUTE_DATA_MISMATCH"    # Massive bars don't match the charted company
STATUS_INVALID_STOP_GEOMETRY = "INVALID_STOP_GEOMETRY"
STATUS_INELIGIBLE_NO_MA = "INELIGIBLE_NO_MA_HISTORY"
STATUS_STILL_OPEN = "STILL_OPEN_AT_DATA_END"

# one slippage for both engines: EP's _slip_sub (partial / stop fills) reads ep_backtest.config
from ep_backtest import config as _ep_config  # noqa: E402
_ep_config.SLIPPAGE_PCT = SLIPPAGE_PCT
