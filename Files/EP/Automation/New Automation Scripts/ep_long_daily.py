"""
EP Swing-Long DAILY Engine -- DAS Trader Pro CMD API automation for the LONG side.

Sibling of ep_long_engine.py (kept as an unused backup/reference -- this file
is the one that actually runs going forward). Same Chosen One #4 strategy
shape (60m OR breakout, ADR stop, START20 ladder, 50% core riding a 20-day-
SMA trail), same 4-tab Google Sheet, but two real differences:

1. **Daily lifecycle, not a continuously-running process.** Launched fresh
   each morning by Task Scheduler (~9:20 ET), does its work, and exits
   cleanly around SESSION_SHUTDOWN_TIME -- Task Scheduler relaunches it the
   next morning. A multi-day-held position's protective stop/ladder orders
   rest at the broker (TIF=GTC+) independent of whether this process is
   connected, and the daily 20-SMA trail check only needs the process alive
   sometime around the close, which it always is under this schedule.
   State still persists to disk and reconciles against live DAS
   positions/orders on every reconnect, exactly like the continuous version.

2. **Sizing/stop are anchored to the PLANNED trigger price, not the actual
   fill price**, with a post-fill size-reconciliation loop -- ported from
   `Old Swing Short Scripts/Algo/algo/alextweak.py`'s `run_size_reconciliation`
   / `adjust_order_pending` single-flight pattern. Concretely: `fixed_stop_px`
   is computed once, at the moment the buy-stop is armed, off the OR-breakout
   trigger price -- never recalculated from the actual fill. If the entry
   fills worse than planned (slippage), the position is trimmed via a plain
   market sell (no borrow-gating needed on the long side, unlike the short
   version) until (avg_fill - fixed_stop_px) * shares == the original target
   dollar risk. If it fills better, shares get added the same way. Only one
   such adjust order is ever in flight per ticker at a time (the single-
   flight gate that fixes the "two orders at once" failure mode).

Daily sequence: idle after launch -> ONE sheet read at 09:29:30 ET -> at
09:30:00 confirm each candidate's gap % against its Yday Close (mirrors
alextweak.py's evaluate_morning_filter exactly, using the official-open T&S
print, condition bit 0x20) -> track the 60m opening range for confirmed
candidates -> arm a buy-stop at OR high + $0.01 -> on fill, reconcile size
to the fixed-stop-anchored target -> place the stop + 5 sell-STOP ladder
targets off the reconciled average fill -> manage breakeven/trail/exit same
as the continuous version -> exit for the day around SESSION_SHUTDOWN_TIME.

See "Files/EP/Backtesting/Swing_Long_EP_Backtest_Session_Dump_2026-09-01.md"
(section 10, strategy #4) and this folder's README.md for the strategy
background, Google Sheet columns, and route/AtClose caveats that still apply
here unchanged from ep_long_engine.py.

Credentials are NOT hardcoded here (unlike the old scripts) -- see .env.example.
"""

from __future__ import annotations

import atexit
import json
import msvcrt
import os
import re
import socket
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, date
from enum import Enum
from typing import Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import gspread
from google.oauth2.service_account import Credentials

from notify_discord import notify

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ET = ZoneInfo("America/New_York")


# =========================
# .env LOADING (no hardcoded secrets, no extra dependency)
# =========================
def _load_dotenv(path: str) -> None:
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip()
            if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                v = v[1:-1]
            os.environ.setdefault(k, v)


_load_dotenv(os.path.join(_SCRIPT_DIR, ".env"))


def _require_env(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env in this folder and fill it in."
        )
    return v


# ===== DAS CONNECTION (from .env) =====
DAS_HOST = os.environ.get("DAS_HOST", "127.0.0.1")
DAS_PORT = int(os.environ.get("DAS_PORT", "9910"))
DAS_USER = _require_env("DAS_USER")
DAS_PASS = _require_env("DAS_PASS")
DAS_ACCT = _require_env("DAS_ACCT")
READ_TIMEOUT_SEC = 0.5

# ===== RISK SIZING (from .env -- account-specific, no sane hardcoded default) =====
ACCOUNT_RESERVE = float(os.environ.get("DAS_ACCOUNT_RESERVE", "0") or 0)
RISK_PCT_PER_TRADE = float(os.environ.get("RISK_PCT_PER_TRADE", "0.05") or 0.05)
MAX_SHARES_CAP = 1_000_000

# ===== GOOGLE SHEETS =====
SHEET_CREDENTIALS_FILE = os.environ.get("SHEET_CREDENTIALS_FILE", "credentials.json")
SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "").strip()  # preferred: the id from the sheet's URL (.../d/<ID>/edit)
SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "Swing Algo Entry Sheet")  # fallback if GOOGLE_SHEET_ID is unset

# Four tabs: "Entry Sheet" is the only one you edit (input); the other three are
# fully bot-managed live views, rebuilt from in-memory state on every change.
ENTRY_SHEET_WORKSHEET = "Entry Sheet"
WATCH_LIST_WORKSHEET = "Current Watch List"
POSITIONS_WORKSHEET = "Current Positions"
HISTORY_WORKSHEET = "History"

_READONLY_SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
_READWRITE_SCOPES = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]


def _sheets_client(write: bool = False) -> gspread.Client:
    scopes = _READWRITE_SCOPES if write else _READONLY_SCOPES
    json_path = os.path.join(_SCRIPT_DIR, SHEET_CREDENTIALS_FILE)
    creds = Credentials.from_service_account_file(json_path, scopes=scopes)
    return gspread.authorize(creds)


def _open_sheet(client: gspread.Client):
    """Opens by GOOGLE_SHEET_ID (robust -- survives renames, no name-collision risk)
    if set, else falls back to matching by GOOGLE_SHEET_NAME."""
    if SHEET_ID:
        return client.open_by_key(SHEET_ID)
    return client.open(SHEET_NAME)


def _col_letter(n: int) -> str:
    letters = ""
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters

# =========================
# STRATEGY CONFIG -- Chosen One #4 (see module docstring)
# =========================
ENTRY_TF_MIN = 60                                     # opening-range window length, minutes from 9:30 ET
STOP_ADR_MULT = 0.50                                  # fixed stop = trigger_price * (1 - adr14 * STOP_ADR_MULT)
TRAIL_MA_WINDOW = 20                                  # close-below-20-day-SMA trailing exit
LADDER_PCTS = [0.20, 0.275, 0.35, 0.425, 0.50]         # START20 ladder, gain % measured off the RECONCILED avg fill
CORE_PCT = 0.50                                       # fraction of ORIGINAL shares that never sells on the ladder
PER_RUNG_FRACTION = (1.0 - CORE_PCT) / len(LADDER_PCTS)  # equal_depletion: 0.10 = 10% of original per rung
MAX_ENTRY_DAY_OFFSET = 7                              # entry watch expires after D0 + 7 trading sessions unfilled
DT_FAMILY_PATTERNS = {"DT", "DT SW", "DT U"}          # excluded chart_pattern values (backtest finding, session dump sec.3)

# ===== MORNING GAP FILTER (mirrors alextweak.py's evaluate_morning_filter) =====
MIN_GAP_PERCENT = 5.0   # min gap % vs Yday Close, confirmed live at the official 9:30 open print
MIN_PRICE = 2.00        # safety-net floor; the EP candidate criteria upstream already filter much higher

# ===== SIZE RECONCILIATION (ported from alextweak.py's run_size_reconciliation) =====
SIZE_TOLERANCE_SHARES = 5             # converge to within this many shares of target before finalizing
MAX_SIZE_ADJUST_ATTEMPTS = 5          # give up chasing the target and lock in current size after this many tries
ADJUST_ORDER_STUCK_TIMEOUT_SEC = 120.0  # release the single-flight slot if no terminal %ORDER status arrives

# ===== DAILY LIFECYCLE =====
SHEET_READ_TIME = "09:29:30"      # single one-shot Entry Sheet read each morning (not continuous, unlike ep_long_engine.py)
GAP_CONFIRM_GRACE_UNTIL = "09:35:00"  # if the official-open print never arrives by this time, reject the candidate
SESSION_SHUTDOWN_TIME = "16:15:00"    # exits cleanly here (a short buffer past the close for AtClose fills to settle); Task Scheduler relaunches tomorrow
DAS_PORT_WAIT_MIN = 10.0              # wait this long for the DAS CMD API port before giving up (Task Scheduler may fire slightly before DAS finishes logging in)

# When to run the once-a-day "close below Nday SMA?" check. Real close is
# 16:00:00 ET; this fires a few minutes early using the live last price as a
# stand-in for the closing print, then submits an AtClose order so the ACTUAL
# fill happens at the real close (see README "Trailing exit" for why this
# is an approximation of the backtest's same-day-close-fill assumption, not
# an exact reproduction).
CLOSE_CHECK_TIME = "15:55:00"
TRAIL_EXIT_TIF = "AtClose"   # fallback to "MKT"-style immediate exit if your broker rejects AtClose this close to the bell -- see README

# ===== DAS ORDER ROUTES =====
# NOTE: DAS route codes are broker/OM-specific and are NOT enumerated in the
# CMD API manual (confirmed -- it only gives examples like ARCA/INET/SMAT).
# These are CARRIED OVER GUESSES from the short-side scripts' conventions,
# not confirmed for long-side buy/sell orders on this account. CONFIRM with
# your broker / a small live test before trusting these for size.
ROUTE_ENTRY = "PRO20"     # buy-stop entry order route, and size-adjust ADD (buy more) route -- CONFIRM
ROUTE_STOP = "SMAT"       # protective sell-stop route (DAS smart route, supports STOPMKT) -- reused from short side, lower risk
ROUTE_ADJUST = "PRO20"    # size-adjust TRIM (sell some) route during reconciliation -- CONFIRM
ROUTE_LADDER = "PRO20"    # sell-STOP ladder target route -- CONFIRM
ROUTE_EXIT = "PRO20"      # market/AtClose sell route for the trailing-stop full-position exit -- CONFIRM

# =========================
# STATE PERSISTENCE
# =========================
STATE_DIR = os.path.join(_SCRIPT_DIR, "state")
STATE_PATH = os.path.join(STATE_DIR, "ep_long_daily_state.json")


def load_state() -> dict:
    if not os.path.isfile(STATE_PATH):
        state = {}
    else:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    state.setdefault("watches", {})
    state.setdefault("positions", {})
    state.setdefault("closed_positions", [])
    state.setdefault("last_close_check_date", None)
    state.setdefault("last_sheet_read_date", None)
    state.setdefault("last_eod_sync_date", None)
    # Buffered writes -- everything below is only actually sent to Google Sheets
    # once per day, at EOD (run_eod_updates), not as each event happens. Queued
    # here rather than lost if an EOD pass is somehow skipped a given day.
    state.setdefault("pending_entry_sheet_clear_rows", [])
    state.setdefault("pending_history_opens", [])
    state.setdefault("pending_history_closes", [])
    return state


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_PATH)


class WatchStatus(str, Enum):
    PENDING_GAP_CONFIRM = "PENDING_GAP_CONFIRM"  # sheet-read done, waiting for the 9:30 official open print
    PENDING_OR = "PENDING_OR"   # gap confirmed, tracking the opening-range window
    ARMED = "ARMED"             # buy-stop resting at the broker


# =========================
# SINGLETON LOCK (same pattern as the short-side scripts)
# =========================
_SINGLETON_LOCK_HANDLE = None


def _release_singleton_lock() -> None:
    global _SINGLETON_LOCK_HANDLE
    if _SINGLETON_LOCK_HANDLE is None:
        return
    try:
        _SINGLETON_LOCK_HANDLE.seek(0)
        msvcrt.locking(_SINGLETON_LOCK_HANDLE.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass
    try:
        _SINGLETON_LOCK_HANDLE.close()
    except Exception:
        pass
    _SINGLETON_LOCK_HANDLE = None


def acquire_singleton_lock(lock_name: str = "ep_long_daily.lock") -> None:
    global _SINGLETON_LOCK_HANDLE
    lock_path = os.path.join(tempfile.gettempdir(), lock_name)
    try:
        handle = open(lock_path, "a+")
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        handle.seek(0)
        handle.truncate()
        handle.write(f"pid={os.getpid()} started={datetime.now(ET).isoformat()}\n")
        handle.flush()
        _SINGLETON_LOCK_HANDLE = handle
        atexit.register(_release_singleton_lock)
    except OSError:
        print("EP Long Daily engine appears to already be running. Exiting to prevent duplicate orders.")
        notify(
            "Startup blocked -- another instance appears active. Exiting to prevent duplicate orders.",
            title="EP Long Daily -- Singleton lock",
            color=0xE74C3C,
        )
        sys.exit(1)


# =========================
# TERMINAL LOGGING (tee stdout/stderr to a daily log file)
# =========================
class _TeeStream:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            try:
                s.write(data)
                s.flush()
            except Exception:
                pass

    def flush(self):
        for s in self.streams:
            try:
                s.flush()
            except Exception:
                pass


def setup_terminal_log() -> None:
    log_dir = os.path.join(_SCRIPT_DIR, "logs")
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, f"ep_long_daily_{datetime.now(ET).strftime('%Y%m%d')}.txt")
    f = open(path, "a", encoding="utf-8", buffering=1)
    sys.stdout = _TeeStream(sys.__stdout__, f)
    sys.stderr = _TeeStream(sys.__stderr__, f)


# =========================
# DAS SOCKET HELPERS
# =========================
def send_line(sock: socket.socket, line: str) -> None:
    sock.sendall((line + "\n").encode("ascii", errors="ignore"))


def recv_lines(sock: socket.socket, buffer: bytes) -> Tuple[List[str], bytes]:
    try:
        data = sock.recv(65536)
        if not data:
            return [], buffer
        buffer += data
        parts = buffer.split(b"\n")
        return [p.decode("utf-8", errors="ignore").strip() for p in parts[:-1]], parts[-1]
    except socket.timeout:
        return [], buffer
    except Exception:
        return [], b""


# =========================
# REGEX / LINE PARSERS
# =========================
# Day bar:    $Bar symbol date High Low Open Close Volume
DAY_BAR_RE = re.compile(
    r"^\$Bar\s+(\S+)\s+(\d{4}/\d{2}/\d{2})\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(\d+)\s*$",
    re.IGNORECASE,
)
# Minute bar: $Bar symbol date-time High Low Open Close Volume MinType
MIN_BAR_RE = re.compile(
    r"^\$Bar\s+(\S+)\s+(\d{4}/\d{2}/\d{2}-\d{2}:\d{2})\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(-?\d+\.?\d*)\s+(\d+)\s+(\d+)\s*$",
    re.IGNORECASE,
)
QUOTE_LAST_RE = re.compile(r"\bL:(\d+\.?\d*)")


def parse_das_position_long(line: str) -> Optional[Tuple[str, int]]:
    """%POS/#POS row -> (symbol, qty) for a LONG position (type 1=cash, 2=margin). None if not a long-position row."""
    if not line or ("%POS" not in line.upper() and "#POS" not in line.upper()):
        return None
    parts = [p for p in line.split() if p]
    if len(parts) < 4:
        return None
    if parts[1].lower() in ("symb", "symbol"):
        return None
    if parts[0].upper() not in ("%POS", "#POS"):
        return None
    try:
        sym = parts[1].upper()
        ptype = int(parts[2])
        qty = int(float(parts[3]))
    except (ValueError, IndexError):
        return None
    if ptype in (1, 2):
        return sym, max(0, qty)
    return None


def _self_test_parsers() -> None:
    """Validates our field-index assumptions against literal sample lines from the CMD API manual. Aborts startup on failure."""
    sample_order = "%ORDER 1 950543235 MSFT B L 100 100 0 333.3 SMAT Accepted 20:47:39 0 730001 BIAN"
    parts = sample_order.split()
    assert parts[1] == "1" and int(parts[2]) == 950543235, "%ORDER field-index assumption broke"

    sample_trade = "%TRADE 1 MSFT B 100 28.3 SMAT 18:00:31 3"
    parts = sample_trade.split()
    assert (
        parts[2] == "MSFT"
        and parts[3] == "B"
        and int(float(parts[4])) == 100
        and float(parts[5]) == 28.3
        and parts[8] == "3"
    ), "%TRADE field-index assumption broke"

    sample_bar_day = "$Bar DELL 2011/12/01 15.86 15.54 15.63 15.8 18000917"
    m = DAY_BAR_RE.match(sample_bar_day)
    assert m and m.group(1) == "DELL" and m.group(2) == "2011/12/01" and float(m.group(6)) == 15.8, "day $Bar regex broke"

    sample_bar_min = "$Bar C 2012/01/05-09:09 27.73 27.69 27.73 27.69 5000 1"
    m = MIN_BAR_RE.match(sample_bar_min)
    assert m is not None and float(m.group(3)) == 27.73, "minute $Bar regex broke"

    sample_pos_long = "%POS AAPL 2 100 117.34 0 0 0 2022/04/07-09:56:43 -245"
    assert parse_das_position_long(sample_pos_long) == ("AAPL", 100), "long %POS parser broke"

    sample_acct = "$AccountInfo 750000.00 750866.50 -29932.75 -18376.43 -32558.76 15.00 5.78 0.18 0.15 2604.90"
    parts = sample_acct.split()
    assert float(parts[2]) == 750866.50, "$AccountInfo field-index assumption broke"

    print("[self-test] all parser field-index assumptions verified against CMD API manual sample lines.")


# =========================
# RUNTIME (non-persisted) LOOKUP TABLES
# =========================
_token_counter = int(time.time())
pending_token_context: Dict[int, dict] = {}   # token -> {"kind": "entry"/"stop"/"rung"/"exit", "ticker": ..., "rung_idx": Optional[int]}
order_index: Dict[str, dict] = {}             # order_id -> same context dict
token_to_order_id: Dict[int, str] = {}
or_high_tracker: Dict[str, float] = {}        # ticker -> running max price during today's OR window
last_price_cache: Dict[str, float] = {}       # ticker -> most recent trade/quote price


def next_token() -> int:
    global _token_counter
    _token_counter += 1
    return _token_counter


def rebuild_runtime_index_from_state(state: dict) -> None:
    """Repopulate the in-memory token/order-id lookup tables from persisted state after a restart."""
    for ticker, w in state["watches"].items():
        tok = w.get("entry_order_token")
        if tok is not None:
            ctx = {"kind": "entry", "ticker": ticker}
            pending_token_context[tok] = ctx
            if w.get("entry_order_id"):
                order_index[w["entry_order_id"]] = ctx
                token_to_order_id[tok] = w["entry_order_id"]
    for ticker, p in state["positions"].items():
        # Entry order token can still be live on a position that's mid-reconciliation
        # (fills accumulated but not yet fully acked) -- carried over from the watch
        # when the position shell was created, so a restart mid-fill doesn't lose it.
        etok = p.get("entry_order_token")
        if etok is not None and p.get("entry_pending_ack"):
            ctx = {"kind": "entry", "ticker": ticker}
            pending_token_context[etok] = ctx
            if p.get("entry_order_id"):
                order_index[p["entry_order_id"]] = ctx
                token_to_order_id[etok] = p["entry_order_id"]
        atok = p.get("adjust_token")
        if atok is not None and p.get("adjust_order_pending"):
            ctx = {"kind": "adjust", "ticker": ticker, "side": p.get("adjust_side")}
            pending_token_context[atok] = ctx
            if p.get("adjust_order_id"):
                order_index[p["adjust_order_id"]] = ctx
                token_to_order_id[atok] = p["adjust_order_id"]
        tok = p.get("stop_order_token")
        if tok is not None:
            ctx = {"kind": "stop", "ticker": ticker}
            pending_token_context[tok] = ctx
            if p.get("stop_order_id"):
                order_index[p["stop_order_id"]] = ctx
                token_to_order_id[tok] = p["stop_order_id"]
        for idx, r in enumerate(p.get("ladder", [])):
            rtok = r.get("order_token")
            if rtok is not None:
                ctx = {"kind": "rung", "ticker": ticker, "rung_idx": idx}
                pending_token_context[rtok] = ctx
                if r.get("order_id"):
                    order_index[r["order_id"]] = ctx
                    token_to_order_id[rtok] = r["order_id"]


# =========================
# TIME-OF-DAY HELPERS (string-based HH:MM:SS, avoids datetime.time/time-module naming collisions)
# =========================
def add_minutes_to_time_str(hhmmss: str, minutes: int) -> str:
    h, m, s = (int(x) for x in hhmmss.split(":"))
    total = (h * 3600 + m * 60 + s + minutes * 60) % (24 * 3600)
    return f"{total // 3600:02d}:{(total % 3600) // 60:02d}:{total % 60:02d}"


def add_trading_days(d: date, n: int) -> date:
    """d + n trading sessions. Uses pandas_market_calendars (NYSE) if available for holiday accuracy; else weekday-only fallback."""
    try:
        import pandas_market_calendars as mcal

        cal = mcal.get_calendar("NYSE")
        sched = cal.schedule(start_date=d, end_date=d + timedelta(days=int(n * 2.5) + 15))
        sessions = [ts.date() for ts in sched.index]
        idx = sessions.index(d) if d in sessions else 0
        return sessions[idx + n]
    except Exception:
        cur = d
        added = 0
        while added < n:
            cur += timedelta(days=1)
            if cur.weekday() < 5:
                added += 1
        return cur


# =========================
# GOOGLE SHEETS -- "Entry Sheet" (input) + "Current Watch List" / "Current Positions" /
# "History" (bot-managed output views)
# =========================
def get_candidates_from_sheet() -> List[dict]:
    """Reads the 'Entry Sheet' tab. Columns (case-insensitive): Ticker, Gap %, ADR14 %,
    Chart Pattern, Enabled, Yday Close. No date column -- a row present here is always
    treated as TODAY's candidate (you add it the morning of the EP). The caller clears
    every row it processes -- armed, skipped, or rejected -- so nothing ever lingers to
    be wrongly treated as a fresh candidate tomorrow.

    Yday Close feeds the live 9:30 gap% confirmation (mirrors alextweak.py's
    evaluate_morning_filter) -- the sheet's own Gap % column is informational only,
    same as before; this is the number actually checked against the live open.
    """
    client = _sheets_client(write=False)
    ws = _open_sheet(client).worksheet(ENTRY_SHEET_WORKSHEET)
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def col(name: str) -> Optional[int]:
        return header.index(name) if name in header else None

    i_ticker = col("ticker")
    i_gap = col("gap %")
    i_adr = col("adr14 %")
    i_pattern = col("chart pattern")
    i_enabled = col("enabled")
    i_yday = col("yday close")
    required = [i_ticker, i_adr, i_pattern, i_enabled, i_yday]
    if None in required:
        print("ERROR: Entry Sheet missing a required column (Ticker / ADR14 % / Chart Pattern / Enabled / Yday Close).")
        return []

    out = []
    width = max(x for x in (required + [i_gap]) if x is not None) + 1
    for sheet_row, r in enumerate(rows[1:], start=2):
        r = r + [""] * (width - len(r))
        ticker = r[i_ticker].strip().upper()
        pattern = r[i_pattern].strip().upper()
        enabled = r[i_enabled].strip().lower()
        if not (ticker and enabled in ("true", "t", "1", "yes", "y")):
            continue  # blank / not-yet-enabled rows are left alone, not consumed
        try:
            adr14_pct = float(r[i_adr].replace("%", "").strip()) / 100.0
        except ValueError:
            adr14_pct = None
        try:
            yday_close = float(r[i_yday].replace("$", "").replace(",", "").strip())
        except ValueError:
            yday_close = None
        gap_pct = None
        if i_gap is not None:
            try:
                gap_pct = float(r[i_gap].replace("%", "").strip())
            except ValueError:
                gap_pct = None
        out.append(
            {
                "row": sheet_row, "ticker": ticker, "gap_pct": gap_pct, "adr14_pct": adr14_pct,
                "chart_pattern": pattern, "yday_close": yday_close,
            }
        )
    return out


def clear_entry_sheet_rows(row_indices: List[int]) -> None:
    if not row_indices:
        return
    try:
        client = _sheets_client(write=True)
        ws = _open_sheet(client).worksheet(ENTRY_SHEET_WORKSHEET)
        ws.batch_clear([f"A{r}:F{r}" for r in row_indices])
    except Exception as e:
        notify(f"Failed to clear processed Entry Sheet row(s): {e}", title="EP Long Daily -- Sheet Error", color=0xF39C12)


def _rebuild_worksheet_rows(worksheet_name: str, rows: List[list], num_cols: int) -> None:
    """Shared helper for the two 'live view' tabs (Watch List, Positions): clears all
    data rows (row 2+) then writes `rows` starting at A2 -- always a full snapshot of
    current in-memory state, never incrementally edited, so the sheet can't drift."""
    client = _sheets_client(write=True)
    ws = _open_sheet(client).worksheet(worksheet_name)
    existing = ws.get_all_values()
    existing_rows = max(0, len(existing) - 1)
    last_col = _col_letter(num_cols)
    if existing_rows:
        ws.batch_clear([f"A2:{last_col}{1 + existing_rows}"])
    if rows:
        # RAW, not USER_ENTERED: these rows mix native numbers with decorated display
        # strings like "+8.5%" / "$10,850.00" -- USER_ENTERED's auto-parsing mangles a
        # leading "+" on a percent string into a bare decimal (confirmed: "+8.5%" -> "0.085").
        # RAW guarantees exactly what we computed is exactly what's displayed.
        ws.update(rows, f"A2:{last_col}{1 + len(rows)}", value_input_option="RAW")


def sync_watch_list_sheet(state: dict) -> None:
    try:
        today = datetime.now(ET).date()
        rows = []
        for w in state["watches"].values():
            if w["status"] != WatchStatus.ARMED.value:
                continue
            expiry_str = w.get("expiry_date") or ""
            days_left = ""
            if expiry_str:
                try:
                    days_left = (datetime.strptime(expiry_str, "%Y-%m-%d").date() - today).days
                except ValueError:
                    days_left = ""
            rows.append(
                [
                    w["ticker"], w["day0"], w.get("or_high", ""), w.get("trigger_price", ""),
                    w.get("planned_shares", ""), "Buy Stop -> Market", ROUTE_ENTRY,
                    expiry_str, days_left, "Watching",
                ]
            )
        _rebuild_worksheet_rows(WATCH_LIST_WORKSHEET, rows, 10)
    except Exception as e:
        notify(f"Failed to sync 'Current Watch List' tab: {e}", title="EP Long Daily -- Sheet Sync Error", color=0xF39C12)


def sync_positions_sheet(state: dict) -> None:
    try:
        rows = []
        for p in state["positions"].values():
            if not p.get("reconciled"):
                continue  # still converging size to the target risk -- not shown until stop/ladder are live
            entry_fill = p["entry_fill"]
            shares_total = p["shares_total"]
            shares_rem = p["shares_remaining"]
            position_size = entry_fill * shares_total
            r_risk = p.get("r_risk_amount", 0.0)
            remaining_pct = (shares_rem / shares_total * 100) if shares_total else 0
            last_price = last_price_cache.get(p["ticker"])
            current_size = shares_rem * last_price if last_price is not None else ""
            unrealized_pct = ((last_price - entry_fill) / entry_fill * 100) if last_price is not None else ""
            core_shares = round(shares_total * CORE_PCT)
            targets = []
            for rung in p["ladder"]:
                tag = " ✓ Filled" if rung["filled"] else ""
                targets.append(f"${rung['price']:.2f}{tag}")
            while len(targets) < len(LADDER_PCTS):
                targets.append("")
            rows.append(
                [
                    p["ticker"], p["entry_date"], entry_fill, shares_total,
                    f"${position_size:,.2f}", f"${r_risk:,.2f}",
                    shares_rem, f"{remaining_pct:.0f}%",
                    f"${current_size:,.2f}" if current_size != "" else "",
                    core_shares, p["stop_price"],
                    "Breakeven" if p["breakeven_applied"] else "Initial ADR Stop",
                    *targets,
                    p.get("last_close", ""), p.get("last_sma", ""),
                    f"{p['last_dist_pct']:+.1f}%" if p.get("last_dist_pct") is not None else "",
                    f"{unrealized_pct:+.1f}%" if unrealized_pct != "" else "",
                ]
            )
        _rebuild_worksheet_rows(POSITIONS_WORKSHEET, rows, 21)
    except Exception as e:
        notify(f"Failed to sync 'Current Positions' tab: {e}", title="EP Long Daily -- Sheet Sync Error", color=0xF39C12)


def history_add_entry(
    ticker: str, entry_date: str, chart_pattern: str, gap_pct: Optional[float],
    adr14_pct: float, entry_price: float, shares: int, r_risk: float,
) -> None:
    try:
        client = _sheets_client(write=True)
        ws = _open_sheet(client).worksheet(HISTORY_WORKSHEET)
        ws.append_row(
            [
                entry_date, ticker, chart_pattern, gap_pct if gap_pct is not None else "",
                round(adr14_pct * 100, 2), entry_price, shares, round(r_risk, 2), "", "", "", "",
            ],
            table_range="A1",
            value_input_option="USER_ENTERED",
        )
    except Exception as e:
        notify(f"Failed to add '{ticker}' to History tab: {e}", title="EP Long Daily -- Sheet Error", color=0xF39C12)


def history_close_entry(
    ticker: str, entry_date: str, exit_date: str, exit_reason: str,
    realized_pl: float, realized_r: Optional[float],
) -> None:
    try:
        client = _sheets_client(write=True)
        ws = _open_sheet(client).worksheet(HISTORY_WORKSHEET)
        col_a = ws.col_values(1)  # Entry Date
        col_b = ws.col_values(2)  # Ticker
        target_row = None
        for i in range(len(col_b) - 1, 0, -1):  # search from the bottom -- most recent match wins
            if col_b[i] == ticker and col_a[i] == entry_date:
                target_row = i + 1
                break
        # Realized R/P&L stay real numbers here (not decorated strings like the two
        # dashboard tabs use) -- History's whole point is later filtering/summing/
        # averaging in Sheets, which needs actual numeric cells, not text.
        realized_r_val = round(realized_r, 4) if realized_r is not None else ""
        if target_row is None:
            # Shouldn't normally happen (history_add_entry runs at entry) -- append rather than lose the record.
            ws.append_row(
                [entry_date, ticker, "", "", "", "", "", "", exit_date, exit_reason, round(realized_pl, 2), realized_r_val],
                table_range="A1",
                value_input_option="USER_ENTERED",
            )
            return
        ws.update(
            f"I{target_row}:L{target_row}",
            [[exit_date, exit_reason, round(realized_pl, 2), realized_r_val]],
            value_input_option="USER_ENTERED",
        )
    except Exception as e:
        notify(f"Failed to update '{ticker}' History row at close: {e}", title="EP Long Daily -- Sheet Error", color=0xF39C12)


# =========================
# BLOCKING DAS FETCH HELPERS
# (each briefly monopolizes the socket with its own local buffer; kept short
#  and infrequent -- same accepted tradeoff the short-side scripts make for
#  GET AccountInfo / GET POSITIONS / GET TRADES calls mid-session.)
# =========================
def fetch_equity_snapshot(sock: socket.socket, timeout_sec: float = 3.0) -> Optional[float]:
    send_line(sock, "GET AccountInfo")
    buf = b""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        lines, buf = recv_lines(sock, buf)
        for line in lines:
            if line.startswith("$AccountInfo"):
                parts = line.split()
                if len(parts) >= 3:
                    try:
                        return float(parts[2])
                    except ValueError:
                        return None
        time.sleep(0.05)
    return None


def fetch_daily_closes(sock: socket.socket, ticker: str, lookback_days: int = 60, timeout_sec: float = 3.0) -> List[Tuple[date, float]]:
    end = datetime.now(ET).date()
    start = end - timedelta(days=lookback_days)
    send_line(sock, f"SB {ticker} DAYCHART {start.strftime('%Y/%m/%d')} {end.strftime('%Y/%m/%d')}")
    out: Dict[date, float] = {}
    buf = b""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        lines, buf = recv_lines(sock, buf)
        for line in lines:
            m = DAY_BAR_RE.match(line)
            if m and m.group(1).upper() == ticker.upper():
                try:
                    d = datetime.strptime(m.group(2), "%Y/%m/%d").date()
                    out[d] = float(m.group(6))
                except ValueError:
                    continue
        time.sleep(0.05)
    send_line(sock, f"UNSB {ticker} DAYCHART")
    return sorted(out.items())


def backfill_or_from_minchart(sock: socket.socket, ticker: str, day0: date, up_to_hhmm: str, timeout_sec: float = 3.0) -> Optional[float]:
    """Recovery path if a candidate is added to the sheet (or the engine restarts) after 9:30 on D0 --
    pulls the missed minutes of the OR window from DAS's own minute-chart cache instead of losing them."""
    start = f"{day0.strftime('%Y/%m/%d')}-09:30"
    end = f"{day0.strftime('%Y/%m/%d')}-{up_to_hhmm}"
    send_line(sock, f"SB {ticker} MINCHART {start} {end}")
    highs: List[float] = []
    buf = b""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        lines, buf = recv_lines(sock, buf)
        for line in lines:
            m = MIN_BAR_RE.match(line)
            if m and m.group(1).upper() == ticker.upper():
                highs.append(float(m.group(3)))
        time.sleep(0.05)
    send_line(sock, f"UNSB {ticker} MINCHART")
    return max(highs) if highs else None


# =========================
# ORDER PLACEMENT HELPERS
# =========================
def place_entry_watch_order(sock: socket.socket, ticker: str, shares: int, trigger_price: float) -> int:
    token = next_token()
    pending_token_context[token] = {"kind": "entry", "ticker": ticker}
    send_line(sock, f"NEWORDER {token} B {ticker} {ROUTE_ENTRY} {shares} STOPMKT {trigger_price:.2f} TIF=GTC+")
    return token


def place_protective_stop(sock: socket.socket, ticker: str, shares: int, stop_price: float) -> int:
    token = next_token()
    pending_token_context[token] = {"kind": "stop", "ticker": ticker}
    send_line(sock, f"NEWORDER {token} S {ticker} {ROUTE_STOP} {shares} STOPMKT {stop_price:.2f} TIF=GTC+ Pref={ROUTE_STOP}")
    return token


def place_ladder_rung(sock: socket.socket, ticker: str, shares: int, price: float, rung_idx: int) -> int:
    """Sell-STOP (not a resting limit) -- converts to a market sell once triggered,
    guaranteeing the sale fires rather than risking a no-fill on a brief touch."""
    token = next_token()
    pending_token_context[token] = {"kind": "rung", "ticker": ticker, "rung_idx": rung_idx}
    send_line(sock, f"NEWORDER {token} S {ticker} {ROUTE_LADDER} {shares} STOPMKT {price:.2f} TIF=GTC+")
    return token


def place_trail_exit(sock: socket.socket, ticker: str, shares: int) -> int:
    token = next_token()
    pending_token_context[token] = {"kind": "exit", "ticker": ticker}
    send_line(sock, f"NEWORDER {token} S {ticker} {ROUTE_EXIT} {shares} MKT TIF={TRAIL_EXIT_TIF}")
    return token


# =========================
# SIZE RECONCILIATION (ported from alextweak.py: run_size_reconciliation /
# _arm_adjust_order / _clear_adjust_order -- single-flight per-ticker gate so a
# second adjust order can never go out before the first one's status resolves,
# which is the fix for the "two orders at once" failure mode).
# =========================
def _arm_adjust_order(pos: dict, token: int, side: str) -> None:
    pos["adjust_order_pending"] = True
    pos["adjust_token"] = token
    pos["adjust_order_id"] = None
    pos["adjust_side"] = side
    pos["adjust_sent_ts"] = time.time()


def _clear_adjust_order(pos: dict) -> None:
    pos["adjust_order_pending"] = False
    pos["adjust_token"] = None
    pos["adjust_order_id"] = None
    pos["adjust_side"] = None
    pos["adjust_sent_ts"] = None


def _finalize_position(sock: socket.socket, state: dict, ticker: str) -> None:
    """Size has converged (or we've given up chasing it) -- lock in the ladder/stop
    off the actual reconciled average fill and hand the ticker to normal management."""
    pos = state["positions"].get(ticker)
    if not pos or pos.get("reconciled"):
        return
    qty = pos["net_qty"]
    avg_fill = pos["total_cost"] / qty if qty else 0.0
    fixed_stop_px = pos["fixed_stop_px"]
    r_risk_amount = round((avg_fill - fixed_stop_px) * qty, 2)

    ladder = []
    for pct in LADDER_PCTS:
        rung_price = round(avg_fill * (1 + pct), 2)
        rung_shares = int(round(qty * PER_RUNG_FRACTION))
        ladder.append(
            {"pct": pct, "price": rung_price, "shares": rung_shares, "order_token": None, "order_id": None, "filled": False, "filled_shares": 0}
        )

    pos.update(
        {
            "entry_fill": round(avg_fill, 4),
            "shares_total": qty,
            "shares_remaining": qty,
            "stop_price": fixed_stop_px,
            "breakeven_applied": False,
            "ladder": ladder,
            "r_risk_amount": r_risk_amount,
            "reconciled": True,
        }
    )
    save_state(state)

    ladder_desc = ", ".join(f"+{p*100:.1f}%→${r['price']:.2f} ({r['shares']}sh)" for p, r in zip(LADDER_PCTS, ladder))
    notify(
        f"{ticker}: size reconciled -- {qty}sh @ avg ${avg_fill:.2f}. Fixed stop ${fixed_stop_px:.2f} (1R=${r_risk_amount:,.2f}). "
        f"Ladder (sell-STOP): {ladder_desc}. Core {CORE_PCT*100:.0f}% rides the {TRAIL_MA_WINDOW}-day SMA trail.",
        title="EP Long Daily -- Entered",
        color=0x2ECC71,
    )
    # Queued, not sent now -- History/Watch-List/Positions sheet writes all
    # happen once, at EOD (run_eod_updates), not as each event occurs.
    state["pending_history_opens"].append(
        {
            "ticker": ticker, "entry_date": pos["entry_date"], "chart_pattern": pos["chart_pattern"],
            "gap_pct": pos.get("gap_pct"), "adr14_pct": pos["adr14_pct"], "entry_price": avg_fill,
            "shares": qty, "r_risk": r_risk_amount,
        }
    )

    if pos.get("stop_order_id"):
        # A reconcile_on_startup interim stop is already resting (crash-recovery
        # case) -- REPLACE it to the final size/price instead of placing a
        # second, duplicate stop order.
        send_line(sock, f"REPLACE {pos['stop_order_id']} {qty} STOPMKT {fixed_stop_px:.2f}")
    else:
        pos["stop_order_token"] = place_protective_stop(sock, ticker, qty, fixed_stop_px)
    for idx, rung in enumerate(ladder):
        if rung["shares"] <= 0:
            continue
        rung["order_token"] = place_ladder_rung(sock, ticker, rung["shares"], rung["price"], idx)
    save_state(state)


def run_size_reconciliation(sock: socket.socket, state: dict, ticker: str) -> None:
    """Converge net_qty to (risk_dollars / (avg_fill - fixed_stop_px)) via plain
    market add/trim orders. fixed_stop_px never moves from what was set when the
    buy-stop was armed -- only shares move, which is what keeps actual dollar risk
    pinned to the ORIGINAL plan regardless of how the entry itself filled."""
    pos = state["positions"].get(ticker)
    if not pos or pos.get("reconciled"):
        return
    if pos.get("entry_pending_ack"):
        return  # wait for the initial buy-stop to fully fill before judging size

    if pos["net_qty"] <= 0:
        notify(
            f"{ticker}: reconciliation left 0 shares -- dropping, nothing to protect.",
            title="EP Long Daily -- Reconcile Flat", color=0x95A5A6,
        )
        state["positions"].pop(ticker, None)
        save_state(state)
        return

    avg_fill = pos["total_cost"] / pos["net_qty"]
    risk_per_share = avg_fill - pos["fixed_stop_px"]
    if risk_per_share <= 0:
        notify(
            f"{ticker}: avg fill ${avg_fill:.2f} is at/below the fixed stop ${pos['fixed_stop_px']:.2f} "
            "(extreme slippage) -- locking in stop/ladder at current size instead of chasing a target.",
            title="EP Long Daily -- Reconcile Error", color=0xE74C3C,
        )
        _finalize_position(sock, state, ticker)
        return

    if pos.get("adjust_order_pending"):
        if time.time() - (pos.get("adjust_sent_ts") or 0) >= ADJUST_ORDER_STUCK_TIMEOUT_SEC:
            oid = pos.get("adjust_order_id")
            if oid:
                send_line(sock, f"CANCEL {oid}")
            notify(
                f"{ticker}: size-adjust stuck timeout ({ADJUST_ORDER_STUCK_TIMEOUT_SEC:.0f}s) -- "
                + (f"sent CANCEL for {oid}; " if oid else "no DAS order id to cancel; ")
                + "releasing slot, verify open orders in DAS.",
                title="EP Long Daily -- Reconcile Timeout", color=0xE67E22,
            )
            _clear_adjust_order(pos)
            save_state(state)
        else:
            return  # still waiting on the outstanding adjust order

    target_shares = max(1, min(MAX_SHARES_CAP, int(pos["risk_dollars"] / risk_per_share)))
    pos["target_shares"] = target_shares
    diff = target_shares - pos["net_qty"]

    if abs(diff) <= SIZE_TOLERANCE_SHARES:
        _finalize_position(sock, state, ticker)
        return

    if pos.get("adjust_attempts", 0) >= MAX_SIZE_ADJUST_ATTEMPTS:
        notify(
            f"{ticker}: hit max size-adjust attempts ({MAX_SIZE_ADJUST_ATTEMPTS}) -- locking in stop/ladder "
            f"at current size ({pos['net_qty']}sh) rather than continuing to chase the target.",
            title="EP Long Daily -- Reconcile Max Attempts", color=0xF39C12,
        )
        _finalize_position(sock, state, ticker)
        return

    adj_qty = min(abs(diff), MAX_SHARES_CAP)
    token = next_token()
    if diff > 0:
        pending_token_context[token] = {"kind": "adjust", "ticker": ticker, "side": "B"}
        send_line(sock, f"NEWORDER {token} B {ticker} {ROUTE_ENTRY} {adj_qty} MKT TIF=DAY+")
        _arm_adjust_order(pos, token, "B")
        notify(
            f"{ticker}: reconciling size -- avg ${avg_fill:.2f}, target {target_shares}sh vs held {pos['net_qty']}sh -- buying {adj_qty} more.",
            title="EP Long Daily -- Size Adjust", color=0x3498DB,
        )
    else:
        pending_token_context[token] = {"kind": "adjust", "ticker": ticker, "side": "S"}
        send_line(sock, f"NEWORDER {token} S {ticker} {ROUTE_ADJUST} {adj_qty} MKT TIF=DAY+")
        _arm_adjust_order(pos, token, "S")
        notify(
            f"{ticker}: reconciling size -- avg ${avg_fill:.2f}, target {target_shares}sh vs held {pos['net_qty']}sh -- trimming {adj_qty}.",
            title="EP Long Daily -- Size Adjust", color=0x3498DB,
        )
    pos["adjust_attempts"] = pos.get("adjust_attempts", 0) + 1
    save_state(state)


# =========================
# CANDIDATE / WATCH LIFECYCLE
# =========================
def refresh_candidates(sock: socket.socket, state: dict) -> None:
    """One-shot morning read (called once at SHEET_READ_TIME, not continuously --
    unlike ep_long_engine.py). New candidates enter PENDING_GAP_CONFIRM and wait for
    the 9:30 official open print to confirm/reject the gap %."""
    try:
        candidates = get_candidates_from_sheet()
    except Exception as e:
        notify(f"EP Long Daily sheet read failed: {e}", title="EP Long Daily -- Sheet Error", color=0xE74C3C)
        return
    if not candidates:
        notify("Entry Sheet read -- no enabled candidates today.", title="EP Long Daily -- Morning Read", color=0x95A5A6)
        return

    today = datetime.now(ET).date()
    armed_msgs: List[str] = []
    processed_rows: List[int] = []

    for c in candidates:
        ticker = c["ticker"]
        processed_rows.append(c["row"])

        if c["chart_pattern"] in DT_FAMILY_PATTERNS:
            notify(
                f"{ticker}: Chart Pattern '{c['chart_pattern']}' is in the excluded DT family -- not armed.",
                title="EP Long Daily -- Candidate Skipped", color=0x95A5A6,
            )
            continue
        if c["adr14_pct"] is None:
            notify(
                f"{ticker}: ADR14 % missing/invalid on Entry Sheet -- not armed.",
                title="EP Long Daily -- Candidate Skipped", color=0xE67E22,
            )
            continue
        if c["yday_close"] is None or c["yday_close"] <= 0:
            notify(
                f"{ticker}: Yday Close missing/invalid on Entry Sheet -- can't confirm gap % live, not armed.",
                title="EP Long Daily -- Candidate Skipped", color=0xE67E22,
            )
            continue
        if ticker in state["watches"] or ticker in state["positions"]:
            notify(
                f"{ticker}: already has an open watch or position -- duplicate Entry Sheet row ignored.",
                title="EP Long Daily -- Candidate Skipped", color=0x95A5A6,
            )
            continue

        watch = {
            "ticker": ticker,
            "day0": today.strftime("%Y-%m-%d"),
            "adr14_pct": c["adr14_pct"],
            "gap_pct": c["gap_pct"],
            "yday_close": c["yday_close"],
            "chart_pattern": c["chart_pattern"],
            "status": WatchStatus.PENDING_GAP_CONFIRM.value,
            "official_open_price": None,
            "confirmed_gap_pct": None,
            "or_high": None,
            "trigger_price": None,
            "planned_stop_price": None,
            "planned_shares": None,
            "risk_dollars": None,
            "entry_order_token": None,
            "entry_order_id": None,
            "expiry_date": None,
        }
        state["watches"][ticker] = watch
        send_line(sock, f"SB {ticker} Lv1")
        send_line(sock, f"SB {ticker} tms")
        armed_msgs.append(ticker)

    # Cleared at EOD (run_eod_updates), not immediately -- consolidates all
    # Entry Sheet writes into the single once-a-day batch, same as the other tabs.
    state["pending_entry_sheet_clear_rows"].extend(processed_rows)
    if armed_msgs:
        save_state(state)
        notify(
            f"Entry Sheet read -- watching for the 9:30 gap confirmation: {', '.join(armed_msgs)}.",
            title="EP Long Daily -- Morning Read", color=0x3498DB,
        )
    else:
        save_state(state)


def evaluate_gap_confirm(state: dict, ticker: str, open_px: float) -> None:
    """Mirrors alextweak.py's evaluate_morning_filter: gap % vs Yday Close, checked
    against the live official-open print (first T&S tick at/after 9:30:00 with
    condition bit 0x20 set)."""
    watch = state["watches"].get(ticker)
    if not watch or watch["status"] != WatchStatus.PENDING_GAP_CONFIRM.value:
        return
    yday_close = watch.get("yday_close")
    watch["official_open_price"] = open_px
    if not yday_close or yday_close <= 0:
        notify(f"{ticker}: rejected -- invalid Yday Close.", title="EP Long Daily -- Gap Filter", color=0xE74C3C)
        state["watches"].pop(ticker, None)
        save_state(state)
        return

    gap_pct = (open_px - yday_close) / yday_close * 100
    if open_px < MIN_PRICE or gap_pct < MIN_GAP_PERCENT:
        notify(
            f"{ticker}: rejected -- open ${open_px:.2f}, gap {gap_pct:.1f}% "
            f"(min gap {MIN_GAP_PERCENT}%, min price ${MIN_PRICE:.2f}).",
            title="EP Long Daily -- Gap Filter", color=0xE74C3C,
        )
        state["watches"].pop(ticker, None)
        save_state(state)
        return

    watch["confirmed_gap_pct"] = round(gap_pct, 2)
    watch["status"] = WatchStatus.PENDING_OR.value
    save_state(state)
    notify(
        f"{ticker}: gap confirmed -- open ${open_px:.2f}, gap {gap_pct:.1f}%. Tracking the {ENTRY_TF_MIN}m opening range.",
        title="EP Long Daily -- Gap Confirmed", color=0x2ECC71,
    )


def expire_unconfirmed_gap_watches(state: dict, now: datetime) -> None:
    """Safety net: if the official-open print (condition bit 0x20) never arrives
    -- e.g. the ticker is halted at the open -- don't hang in PENDING_GAP_CONFIRM
    forever; reject and move on."""
    if now.strftime("%H:%M:%S") < GAP_CONFIRM_GRACE_UNTIL:
        return
    today_str = now.strftime("%Y-%m-%d")
    for ticker, watch in list(state["watches"].items()):
        if watch["status"] != WatchStatus.PENDING_GAP_CONFIRM.value or watch["day0"] != today_str:
            continue
        notify(
            f"{ticker}: no official-open print seen by {GAP_CONFIRM_GRACE_UNTIL} ET (possibly halted at the open) -- rejected.",
            title="EP Long Daily -- Gap Filter Timeout", color=0xE67E22,
        )
        state["watches"].pop(ticker, None)
        save_state(state)


def on_tick_price(state: dict, ticker: str, price: float, ts_time: str, condition: int) -> None:
    watch = state["watches"].get(ticker)
    if not watch:
        return
    if datetime.now(ET).strftime("%Y-%m-%d") != watch["day0"]:
        return

    if watch["status"] == WatchStatus.PENDING_GAP_CONFIRM.value:
        # Bit 0x20 (per the CMD API manual: "valid for hi/lo") marks the official
        # opening print at 9:30:00 -- same mechanism alextweak.py's morning filter uses.
        if ts_time >= "09:30:00" and (condition & 0x20):
            evaluate_gap_confirm(state, ticker, price)
        return

    if watch["status"] != WatchStatus.PENDING_OR.value:
        return
    if ts_time < "09:30:00":
        return
    window_end = add_minutes_to_time_str("09:30:00", ENTRY_TF_MIN)
    if ts_time > window_end:
        return
    cur = or_high_tracker.get(ticker)
    if cur is None or price > cur:
        or_high_tracker[ticker] = price


def finalize_or_and_arm_entries(sock: socket.socket, state: dict, now: datetime) -> None:
    window_close_str = add_minutes_to_time_str("09:30:00", ENTRY_TF_MIN)
    hhmmss = now.strftime("%H:%M:%S")
    if hhmmss < window_close_str:
        return
    today_str = now.strftime("%Y-%m-%d")
    for ticker, watch in list(state["watches"].items()):
        if watch["status"] != WatchStatus.PENDING_OR.value or watch["day0"] != today_str:
            continue
        or_high = or_high_tracker.get(ticker)
        if or_high is None:
            notify(
                f"{ticker}: no trade ticks observed during the {ENTRY_TF_MIN}m opening range -- cannot compute breakout level. Not armed today.",
                title="EP Long Daily -- OR Failed",
                color=0xE67E22,
            )
            state["watches"].pop(ticker, None)
            save_state(state)
            continue

        trigger = round(or_high + 0.01, 2)
        planned_stop = round(trigger * (1 - watch["adr14_pct"] * STOP_ADR_MULT), 2)
        risk_per_share = trigger - planned_stop
        if risk_per_share <= 0:
            notify(
                f"{ticker}: invalid stop geometry (trigger ${trigger:.2f} <= planned stop ${planned_stop:.2f}, adr14={watch['adr14_pct']*100:.2f}%). Skipping.",
                title="EP Long Daily -- Invalid Stop Geometry",
                color=0xE74C3C,
            )
            state["watches"].pop(ticker, None)
            save_state(state)
            continue

        equity = fetch_equity_snapshot(sock)
        if equity is None:
            continue  # retry next loop tick rather than guessing

        risk_dollars = max(0.0, equity - ACCOUNT_RESERVE) * RISK_PCT_PER_TRADE
        shares = max(1, min(MAX_SHARES_CAP, int(risk_dollars / risk_per_share)))
        expiry = add_trading_days(watch_day0(watch), MAX_ENTRY_DAY_OFFSET)

        watch.update(
            {
                "or_high": or_high,
                "trigger_price": trigger,
                "planned_stop_price": planned_stop,
                "planned_shares": shares,
                "risk_dollars": risk_dollars,
                "expiry_date": expiry.strftime("%Y-%m-%d"),
                "status": WatchStatus.ARMED.value,
            }
        )
        token = place_entry_watch_order(sock, ticker, shares, trigger)
        watch["entry_order_token"] = token
        save_state(state)
        notify(
            f"{ticker}: {ENTRY_TF_MIN}m OR high = ${or_high:.2f}. Buy-stop ARMED @ ${trigger:.2f} x {shares}sh "
            f"(risk ${risk_dollars:,.2f}, planned stop ${planned_stop:.2f}). Watching through {expiry.isoformat()}.",
            title="EP Long Daily -- Entry Armed",
            color=0x3498DB,
        )


def watch_day0(watch: dict) -> date:
    return datetime.strptime(watch["day0"], "%Y-%m-%d").date()


def expire_stale_watches(sock: socket.socket, state: dict, now: datetime) -> None:
    for ticker, watch in list(state["watches"].items()):
        if watch["status"] != WatchStatus.ARMED.value or not watch.get("expiry_date"):
            continue
        expiry_date = datetime.strptime(watch["expiry_date"], "%Y-%m-%d").date()
        past_expiry = now.date() > expiry_date or (now.date() == expiry_date and now.strftime("%H:%M:%S") >= "16:00:00")
        if not past_expiry:
            continue
        order_id = watch.get("entry_order_id") or token_to_order_id.get(watch.get("entry_order_token"))
        if order_id:
            send_line(sock, f"CANCEL {order_id}")
        notify(
            f"{ticker}: entry watch expired unfilled after {MAX_ENTRY_DAY_OFFSET} sessions (D0={watch['day0']}). Buy-stop canceled.",
            title="EP Long Daily -- Watch Expired",
            color=0x95A5A6,
        )
        state["watches"].pop(ticker, None)
        save_state(state)


# =========================
# FILL HANDLING
# =========================
def on_entry_fill_tick(sock: socket.socket, state: dict, ticker: str, qty: int, price: float) -> None:
    """Accumulates one entry fill (there can be more than one partial) into the
    position's running net_qty/total_cost, then hands off to size reconciliation
    once the originally-requested share count is fully filled. fixed_stop_px comes
    from the watch (the PLANNED trigger price) and is never touched here."""
    pos = state["positions"].get(ticker)
    if pos is None:
        watch = state["watches"].pop(ticker, None)
        if watch is None:
            return  # fill for a ticker we no longer have any record of -- nothing to do
        pos = {
            "ticker": ticker,
            "fixed_stop_px": watch["planned_stop_price"],
            "risk_dollars": watch["risk_dollars"],
            "entry_requested_shares": watch["planned_shares"],
            "entry_pending_ack": True,
            "entry_order_token": watch.get("entry_order_token"),
            "entry_order_id": watch.get("entry_order_id"),
            "net_qty": 0,
            "total_cost": 0.0,
            "target_shares": None,
            "adjust_order_pending": False,
            "adjust_token": None,
            "adjust_order_id": None,
            "adjust_side": None,
            "adjust_sent_ts": None,
            "adjust_attempts": 0,
            "reconciled": False,
            "entry_date": datetime.now(ET).strftime("%Y-%m-%d"),
            "chart_pattern": watch.get("chart_pattern", ""),
            "gap_pct": watch.get("confirmed_gap_pct", watch.get("gap_pct")),
            "adr14_pct": watch["adr14_pct"],
            # Filled in once reconciled (see _finalize_position):
            "entry_fill": None, "shares_total": None, "shares_remaining": None,
            "stop_price": None, "stop_order_token": None, "stop_order_id": None,
            "breakeven_applied": False, "ladder": [], "r_risk_amount": None,
            "realized_pl": 0.0, "last_close": None, "last_sma": None, "last_dist_pct": None,
        }
        state["positions"][ticker] = pos

    pos["net_qty"] += qty
    pos["total_cost"] += qty * price
    if pos["net_qty"] >= pos["entry_requested_shares"]:
        pos["entry_pending_ack"] = False
    save_state(state)

    if pos["entry_pending_ack"]:
        notify(
            f"{ticker}: entry partial fill {qty}sh @ ${price:.2f} (running {pos['net_qty']}/{pos['entry_requested_shares']}sh) -- waiting for the rest before sizing.",
            title="EP Long Daily -- Entry Partial", color=0x3498DB,
        )
        return

    notify(
        f"{ticker}: entry filled {pos['net_qty']}sh, avg ${pos['total_cost']/pos['net_qty']:.2f} -- reconciling size to the fixed stop ${pos['fixed_stop_px']:.2f}.",
        title="EP Long Daily -- Entry Filled", color=0x2ECC71,
    )
    run_size_reconciliation(sock, state, ticker)


def on_adjust_fill_tick(sock: socket.socket, state: dict, ticker: str, qty: int, price: float, side: Optional[str]) -> None:
    """Fill on a size-adjust order (add or trim during reconciliation, before the
    ladder/stop are placed). Releases the single-flight slot and re-runs reconciliation."""
    pos = state["positions"].get(ticker)
    if not pos:
        return
    if side == "B":
        pos["net_qty"] += qty
        pos["total_cost"] += qty * price
    else:
        # Trimming reduces total_cost proportionally so the average cost of the
        # REMAINING shares is unchanged -- selling shares off a position doesn't
        # change what you paid for the ones you kept.
        avg_before = pos["total_cost"] / pos["net_qty"] if pos["net_qty"] else 0.0
        pos["net_qty"] = max(0, pos["net_qty"] - qty)
        pos["total_cost"] = max(0.0, pos["total_cost"] - qty * avg_before)
    _clear_adjust_order(pos)
    save_state(state)
    run_size_reconciliation(sock, state, ticker)


def on_rung_filled(sock: socket.socket, state: dict, ticker: str, rung_idx: int, qty: int, price: float) -> None:
    pos = state["positions"].get(ticker)
    if not pos:
        return
    rung = pos["ladder"][rung_idx]
    rung["filled"] = True
    rung["filled_shares"] = rung.get("filled_shares", 0) + qty
    pos["shares_remaining"] = max(0, pos["shares_remaining"] - qty)
    pos["realized_pl"] = pos.get("realized_pl", 0.0) + (price - pos["entry_fill"]) * qty

    notify(
        f"{ticker}: ladder rung {rung_idx+1}/5 (+{LADDER_PCTS[rung_idx]*100:.1f}%) filled {qty}sh @ ${price:.2f}. Remaining: {pos['shares_remaining']}sh.",
        title="EP Long Daily -- Partial Sold",
        color=0x2ECC71,
    )

    if not pos["breakeven_applied"]:
        pos["breakeven_applied"] = True
        pos["stop_price"] = pos["entry_fill"]
        notify(f"{ticker}: breakeven stop armed @ ${pos['stop_price']:.2f}.", title="EP Long Daily -- Breakeven Stop", color=0x3498DB)

    stop_order_id = pos.get("stop_order_id") or token_to_order_id.get(pos.get("stop_order_token"))
    if stop_order_id and pos["shares_remaining"] > 0:
        send_line(sock, f"REPLACE {stop_order_id} {pos['shares_remaining']} STOPMKT {pos['stop_price']:.2f}")
    save_state(state)


def _finalize_history_close(state: dict, pos: dict, exit_reason: str) -> None:
    """Queued, not sent now -- flushed once at EOD by run_eod_updates."""
    r_risk = pos.get("r_risk_amount") or 0.0
    realized_pl = pos.get("realized_pl", 0.0)
    realized_r = (realized_pl / r_risk) if r_risk else None
    state["pending_history_closes"].append(
        {
            "ticker": pos["ticker"], "entry_date": pos["entry_date"],
            "exit_date": datetime.now(ET).strftime("%Y-%m-%d"), "exit_reason": exit_reason,
            "realized_pl": realized_pl, "realized_r": realized_r,
        }
    )


def on_stop_filled(sock: socket.socket, state: dict, ticker: str, qty: int, price: float) -> None:
    pos = state["positions"].get(ticker)
    if not pos:
        return
    pos["shares_remaining"] = max(0, pos["shares_remaining"] - qty)
    pos["realized_pl"] = pos.get("realized_pl", 0.0) + (price - pos["entry_fill"]) * qty
    notify(f"{ticker}: STOPPED OUT {qty}sh @ ${price:.2f}.", title="EP Long Daily -- Stopped Out", color=0xE74C3C)
    _cancel_remaining_ladder(sock, pos)
    _finalize_history_close(state, pos, "Stopped Out")
    close_position(state, ticker, "stopped_out")


def on_trail_exit_filled(sock: socket.socket, state: dict, ticker: str, qty: int, price: float) -> None:
    pos = state["positions"].get(ticker)
    if not pos:
        return
    pos["shares_remaining"] = max(0, pos["shares_remaining"] - qty)
    pos["realized_pl"] = pos.get("realized_pl", 0.0) + (price - pos["entry_fill"]) * qty
    notify(f"{ticker}: TRAIL EXIT filled {qty}sh @ ${price:.2f} (close below {TRAIL_MA_WINDOW}-day SMA).", title="EP Long Daily -- Trail Exit Filled", color=0xE67E22)
    _finalize_history_close(state, pos, "Trail Exit (20MA)")
    close_position(state, ticker, "trail_exit")


def _cancel_remaining_ladder(sock: socket.socket, pos: dict) -> None:
    for rung in pos["ladder"]:
        if not rung["filled"]:
            oid = rung.get("order_id") or token_to_order_id.get(rung.get("order_token"))
            if oid:
                send_line(sock, f"CANCEL {oid}")


def close_position(state: dict, ticker: str, reason: str) -> None:
    pos = state["positions"].pop(ticker, None)
    if pos is not None:
        pos["closed_reason"] = reason
        pos["closed_at"] = datetime.now(ET).isoformat()
        state["closed_positions"].append(pos)
        state["closed_positions"] = state["closed_positions"][-500:]  # cap history growth
    save_state(state)


# =========================
# DAILY TRAILING-STOP (close-below-SMA) CHECK
# =========================
def check_daily_trail_exit(sock: socket.socket, pos: dict) -> Tuple[bool, Optional[float]]:
    ticker = pos["ticker"]
    bars = fetch_daily_closes(sock, ticker)
    today = datetime.now(ET).date()
    prior_closes = [c for d, c in bars if d < today]
    if len(prior_closes) < TRAIL_MA_WINDOW - 1:
        notify(f"{ticker}: not enough daily-close history ({len(prior_closes)}) to evaluate the {TRAIL_MA_WINDOW}-day SMA trail today.", title="EP Long Daily -- Trail Check Skipped", color=0xF39C12)
        return False, None
    prior_closes = prior_closes[-(TRAIL_MA_WINDOW - 1):]
    est_close = last_price_cache.get(ticker)
    if est_close is None:
        return False, None
    sma = (sum(prior_closes) + est_close) / TRAIL_MA_WINDOW
    pos["last_close"] = est_close
    pos["last_sma"] = round(sma, 4)
    pos["last_dist_pct"] = ((est_close - sma) / sma * 100) if sma else None
    return est_close < sma, est_close


def run_daily_close_checks(sock: socket.socket, state: dict) -> None:
    for ticker, pos in list(state["positions"].items()):
        if not pos.get("reconciled"):
            continue  # still converging size -- shouldn't normally still be true by the close, but don't act on a half-built position
        exit_needed, est_close = check_daily_trail_exit(sock, pos)
        if exit_needed and est_close is not None:
            _cancel_remaining_ladder(sock, pos)
            stop_order_id = pos.get("stop_order_id") or token_to_order_id.get(pos.get("stop_order_token"))
            if stop_order_id:
                send_line(sock, f"CANCEL {stop_order_id}")
            shares = pos["shares_remaining"]
            place_trail_exit(sock, ticker, shares)
            notify(
                f"{ticker}: close (~${est_close:.2f}) below {TRAIL_MA_WINDOW}-day SMA -- exiting remaining {shares}sh via {TRAIL_EXIT_TIF} order.",
                title="EP Long Daily -- Trail Exit Triggered",
                color=0xE67E22,
            )
    save_state(state)


def run_eod_updates(state: dict) -> None:
    """The ONLY place the two dashboard tabs get written and Entry Sheet rows
    get cleared -- once per day, called right before the daily shutdown. No
    per-event or periodic writes elsewhere; this trades away intraday sheet
    visibility for far fewer Sheets API calls, per explicit instruction."""
    sync_watch_list_sheet(state)
    if state["positions"]:
        sync_positions_sheet(state)

    for item in state["pending_history_opens"]:
        history_add_entry(
            item["ticker"], item["entry_date"], item["chart_pattern"], item.get("gap_pct"),
            item["adr14_pct"], item["entry_price"], item["shares"], item["r_risk"],
        )
    state["pending_history_opens"] = []

    for item in state["pending_history_closes"]:
        history_close_entry(
            item["ticker"], item["entry_date"], item["exit_date"],
            item["exit_reason"], item["realized_pl"], item["realized_r"],
        )
    state["pending_history_closes"] = []

    clear_entry_sheet_rows(state["pending_entry_sheet_clear_rows"])
    state["pending_entry_sheet_clear_rows"] = []

    save_state(state)


# =========================
# LINE DISPATCH
# =========================
def handle_order_line(state: dict, line: str) -> None:
    parts = line.split()
    if len(parts) < 3:
        return
    try:
        order_id = parts[1]
        token = int(parts[2])
    except (ValueError, IndexError):
        return
    ctx = pending_token_context.get(token)
    if not ctx:
        return
    order_index[order_id] = ctx
    token_to_order_id[token] = order_id
    ticker, kind = ctx["ticker"], ctx["kind"]

    if kind == "entry":
        w = state["watches"].get(ticker)
        if w and w.get("entry_order_token") == token and not w.get("entry_order_id"):
            w["entry_order_id"] = order_id
            save_state(state)
        p = state["positions"].get(ticker)
        if p and p.get("entry_order_token") == token and not p.get("entry_order_id"):
            p["entry_order_id"] = order_id
            save_state(state)
    elif kind == "adjust":
        p = state["positions"].get(ticker)
        if p and p.get("adjust_token") == token and not p.get("adjust_order_id"):
            p["adjust_order_id"] = order_id
            save_state(state)
    elif kind == "stop":
        p = state["positions"].get(ticker)
        if p and p.get("stop_order_token") == token and not p.get("stop_order_id"):
            p["stop_order_id"] = order_id
            save_state(state)
    elif kind == "rung":
        p = state["positions"].get(ticker)
        if p:
            idx = ctx["rung_idx"]
            if 0 <= idx < len(p["ladder"]) and p["ladder"][idx].get("order_token") == token and not p["ladder"][idx].get("order_id"):
                p["ladder"][idx]["order_id"] = order_id
                save_state(state)


def handle_trade_line(sock: socket.socket, state: dict, line: str) -> None:
    parts = line.split()
    if len(parts) < 9:
        return
    try:
        qty = int(float(parts[4]))
        price = float(parts[5])
        order_id = parts[8]
    except (ValueError, IndexError):
        return
    ctx = order_index.get(order_id)
    if not ctx:
        return  # fill on an order we don't recognize (e.g. a manual trade) -- ignore
    ticker, kind = ctx["ticker"], ctx["kind"]
    if kind == "entry":
        on_entry_fill_tick(sock, state, ticker, qty, price)
    elif kind == "adjust":
        on_adjust_fill_tick(sock, state, ticker, qty, price, ctx.get("side"))
    elif kind == "stop":
        on_stop_filled(sock, state, ticker, qty, price)
    elif kind == "rung":
        on_rung_filled(sock, state, ticker, ctx["rung_idx"], qty, price)
    elif kind == "exit":
        on_trail_exit_filled(sock, state, ticker, qty, price)


def handle_quote_line(line: str) -> None:
    parts = line.split()
    if len(parts) < 2:
        return
    ticker = parts[1].upper()
    m = QUOTE_LAST_RE.search(line)
    if m:
        try:
            last_price_cache[ticker] = float(m.group(1))
        except ValueError:
            pass


def handle_ts_line(state: dict, line: str) -> None:
    parts = line.split()
    if len(parts) < 6 or parts[0].upper() != "$T&S":
        return
    ticker = parts[1].upper()
    try:
        price = float(parts[2])
        ts_time = parts[5]
    except (ValueError, IndexError):
        return
    condition = 0
    try:
        condition = int(parts[-1])
    except (ValueError, IndexError):
        pass  # gap-confirm just won't fire on this particular tick; later ticks still get a chance
    last_price_cache[ticker] = price
    on_tick_price(state, ticker, price, ts_time, condition)


def dispatch_line(sock: socket.socket, state: dict, line: str) -> None:
    if not line:
        return
    if line.startswith("%ORDER") or line.startswith("#Order"):
        handle_order_line(state, line)
    elif line.startswith("%TRADE") or line.startswith("#Trade"):
        handle_trade_line(sock, state, line)
    elif line.startswith("$Quote"):
        handle_quote_line(line)
    elif line.startswith("$T&S"):
        handle_ts_line(state, line)
    # $Bar / $AccountInfo lines are consumed synchronously by the blocking
    # fetch helpers above; nothing to do with them here.


# =========================
# STARTUP RECONCILIATION
# =========================
def reconcile_on_startup(sock: socket.socket, state: dict) -> None:
    notify("Startup: reconciling persisted state against live DAS positions/orders...", title="EP Long Daily -- Reconciling", color=0x3498DB)

    send_line(sock, "GET POSITIONS")
    time.sleep(0.5)
    send_line(sock, "GET ORDERS")

    raw_lines: List[str] = []
    buf = b""
    deadline = time.time() + 3.0
    while time.time() < deadline:
        lines, buf = recv_lines(sock, buf)
        raw_lines.extend(lines)
        time.sleep(0.05)

    live_long: Dict[str, int] = {}
    for line in raw_lines:
        parsed = parse_das_position_long(line)
        if parsed:
            sym, qty = parsed
            live_long[sym] = qty

    tracked = set(state["positions"].keys())
    live_syms = {s for s, q in live_long.items() if q > 0}

    missing_locally = live_syms - tracked
    missing_on_broker = {s for s in tracked if live_long.get(s, 0) <= 0}

    if missing_locally:
        notify(
            f"RECONCILE WARNING: DAS shows live long position(s) with no local tracking: {', '.join(sorted(missing_locally))}. "
            "NOT auto-managed by this engine -- verify manually in DAS.",
            title="EP Long Daily -- Reconcile Mismatch",
            color=0xE74C3C,
        )
    if missing_on_broker:
        notify(
            f"RECONCILE WARNING: locally-tracked position(s) show flat on DAS: {', '.join(sorted(missing_on_broker))}. "
            "Likely filled/stopped while offline -- removing from local tracking.",
            title="EP Long Daily -- Reconcile Mismatch",
            color=0xF39C12,
        )
        for s in missing_on_broker:
            close_position(state, s, "reconciled_flat_on_restart")

    order_lines_upper = [l.upper() for l in raw_lines if l.upper().startswith("%ORDER") or l.upper().startswith("#ORDER")]
    for ticker, pos in list(state["positions"].items()):
        if ticker in missing_on_broker:
            continue
        has_resting_stop = any(ticker.upper() in l and "STOP" in l for l in order_lines_upper)

        if not pos.get("reconciled"):
            # Crashed between the entry fill and the ladder/stop being placed --
            # net_qty shares are sitting completely unprotected. Place an interim
            # stop for the CURRENT size now; _finalize_position will REPLACE it
            # (not duplicate it) once reconciliation converges and hands off to
            # normal management.
            if pos.get("net_qty", 0) > 0 and not has_resting_stop and not pos.get("stop_order_id"):
                notify(
                    f"SAFETY: {ticker} has {pos['net_qty']}sh filled but NOT YET size-reconciled, with no resting stop found on restart! "
                    f"Placing an interim stop @ ${pos['fixed_stop_px']:.2f} for the current size now -- reconciliation resumes this session.",
                    title="EP Long Daily -- RE-ARMING STOP",
                    color=0xE74C3C,
                )
                pos["stop_order_token"] = place_protective_stop(sock, ticker, pos["net_qty"], pos["fixed_stop_px"])
                pos["stop_order_id"] = None
            continue

        if not has_resting_stop:
            notify(
                f"SAFETY: {ticker} has a live long position with NO resting stop order found on restart! Re-arming protective stop @ ${pos['stop_price']:.2f} now.",
                title="EP Long Daily -- RE-ARMING STOP",
                color=0xE74C3C,
            )
            pos["stop_order_token"] = place_protective_stop(sock, ticker, pos["shares_remaining"], pos["stop_price"])
            pos["stop_order_id"] = None

    save_state(state)
    notify(
        f"Reconcile complete. Tracking {len(state['positions'])} open position(s), {len(state['watches'])} pending watch(es).",
        title="EP Long Daily -- Reconcile Done",
        color=0x2ECC71,
    )


# =========================
# MAIN LOOP
# =========================
def wait_for_das_port(host: str, port: int, timeout_min: float) -> None:
    """Task Scheduler may fire a few minutes before DAS finishes its own login --
    poll for the CMD API port instead of failing outright. Raises (not sys.exit)
    so the outer reconnect loop decides whether to retry or call it done for the day."""
    deadline = time.time() + timeout_min * 60
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=3):
                return
        except OSError:
            time.sleep(5)
    raise RuntimeError(f"DAS CMD API port {host}:{port} did not come up within {timeout_min:.0f} min")


def backfill_or_in_progress_after_reconnect(sock: socket.socket, state: dict, now: datetime) -> None:
    """or_high_tracker is runtime-only (never persisted) -- if we reconnect mid-OR-
    window (a crash mid-morning), recover the OR-so-far from DAS's own minute-chart
    cache instead of silently losing tracking progress."""
    window_close_hhmm = add_minutes_to_time_str("09:30:00", ENTRY_TF_MIN)[:5]
    now_hhmm = now.strftime("%H:%M")
    today_str = now.strftime("%Y-%m-%d")
    for ticker, watch in state["watches"].items():
        if watch["status"] != WatchStatus.PENDING_OR.value or watch["day0"] != today_str:
            continue
        if ticker in or_high_tracker or now_hhmm <= "09:30":
            continue
        backfill_end = min(now_hhmm, window_close_hhmm)
        backfilled = backfill_or_from_minchart(sock, ticker, watch_day0(watch), backfill_end)
        if backfilled:
            or_high_tracker[ticker] = backfilled


def main() -> Optional[str]:
    """Returns 'DONE_FOR_DAY' on a clean scheduled shutdown; otherwise raises
    (the __main__ wrapper decides whether an exception means reconnect-and-retry
    or, if it's past shutdown time, give up until tomorrow)."""
    wait_for_das_port(DAS_HOST, DAS_PORT, DAS_PORT_WAIT_MIN)
    state = load_state()
    rebuild_runtime_index_from_state(state)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(READ_TIMEOUT_SEC)
    sock.connect((DAS_HOST, DAS_PORT))
    send_line(sock, f"LOGIN {DAS_USER} {DAS_PASS} {DAS_ACCT}")
    time.sleep(1.0)
    send_line(sock, "ReturnFullLv1 YES")

    try:
        # Immediate, impossible-to-miss confirmation of WHICH account this
        # connection is actually talking to -- check this before anything else
        # happens, especially on a first-ever live connection to this account.
        equity = fetch_equity_snapshot(sock, timeout_sec=5.0)
        equity_str = f"${equity:,.2f}" if equity is not None else "UNKNOWN (fetch failed/timed out)"
        print(f"\n{'='*60}\nCONNECTED -- DAS_HOST={DAS_HOST} DAS_PORT={DAS_PORT} ACCT={DAS_ACCT}\nCurrent equity: {equity_str}\n{'='*60}\n")

        reconcile_on_startup(sock, state)

        for ticker in list(state["watches"].keys()) + list(state["positions"].keys()):
            send_line(sock, f"SB {ticker} Lv1")
            send_line(sock, f"SB {ticker} tms")

        backfill_or_in_progress_after_reconnect(sock, state, datetime.now(ET))

        notify(
            f"EP Long Daily engine started/reconnected -- **account {DAS_ACCT}**, equity **{equity_str}**. "
            f"Tracking {len(state['watches'])} watch(es), {len(state['positions'])} position(s). "
            "**Verify this is the correct account before trusting today's run.**",
            title="EP Long Daily -- Started",
            color=0x2ECC71,
        )

        buf = b""
        last_ping = time.time()
        last_sheet_read_date = state.get("last_sheet_read_date")
        last_close_check_date = state.get("last_close_check_date")
        last_reconcile_retry_ts = 0.0
        last_heartbeat_hour = -1

        while True:
            now = datetime.now(ET)
            hhmmss = now.strftime("%H:%M:%S")
            today_key = now.strftime("%Y-%m-%d")
            weekday_ok = now.weekday() < 5

            if weekday_ok and hhmmss >= SESSION_SHUTDOWN_TIME:
                # The ONE daily sheet-write pass: Watch List, Positions, History,
                # and clearing today's processed Entry Sheet rows.
                run_eod_updates(state)
                notify(
                    "Session shutdown time reached -- disconnecting for the day; Task Scheduler will relaunch tomorrow morning.",
                    title="EP Long Daily -- Daily Shutdown",
                    color=0x95A5A6,
                )
                return "DONE_FOR_DAY"

            if time.time() - last_ping > 45:
                send_line(sock, "TEST")
                last_ping = time.time()

            lines, buf = recv_lines(sock, buf)
            for line in lines:
                dispatch_line(sock, state, line)

            # One-shot morning read (not continuous, unlike ep_long_engine.py) --
            # this script is built around the exact 09:29:30 -> 09:30:00 sequence.
            if weekday_ok and hhmmss >= SHEET_READ_TIME and last_sheet_read_date != today_key:
                refresh_candidates(sock, state)
                last_sheet_read_date = today_key
                state["last_sheet_read_date"] = today_key
                save_state(state)

            if weekday_ok:
                expire_unconfirmed_gap_watches(state, now)
                finalize_or_and_arm_entries(sock, state, now)
                expire_stale_watches(sock, state, now)

            # Periodic retry for any position still mid-reconciliation -- covers a
            # stuck-timeout needing re-evaluation even without a fresh fill event.
            if weekday_ok and (time.time() - last_reconcile_retry_ts) > 2.0:
                for ticker, pos in list(state["positions"].items()):
                    if not pos.get("reconciled"):
                        run_size_reconciliation(sock, state, ticker)
                last_reconcile_retry_ts = time.time()

            if weekday_ok and hhmmss >= CLOSE_CHECK_TIME and last_close_check_date != today_key and state["positions"]:
                run_daily_close_checks(sock, state)
                last_close_check_date = today_key
                state["last_close_check_date"] = today_key
                save_state(state)

            if now.minute == 0 and now.second < 2 and last_heartbeat_hour != now.hour:
                notify(
                    f"Heartbeat -- {len(state['watches'])} watch(es), {len(state['positions'])} open position(s).",
                    title="EP Long Daily -- Heartbeat",
                    color=0x3498DB,
                )
                last_heartbeat_hour = now.hour

            idle = not (weekday_ok and "08:30:00" <= hhmmss <= SESSION_SHUTDOWN_TIME)
            time.sleep(2.0 if idle else 0.25)
    finally:
        try:
            send_line(sock, "QUIT")
        except Exception:
            pass
        try:
            sock.close()
        except Exception:
            pass


if __name__ == "__main__":
    setup_terminal_log()
    try:
        _self_test_parsers()
    except AssertionError as e:
        print(f"SELF-TEST FAILED: {e}")
        notify(f"Startup self-test failed: {e}. Refusing to start.", title="EP Long Daily -- SELF-TEST FAILED", color=0xE74C3C)
        sys.exit(1)

    acquire_singleton_lock()

    while True:
        try:
            result = main()
            if result == "DONE_FOR_DAY":
                break
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            if datetime.now(ET).strftime("%H:%M:%S") >= SESSION_SHUTDOWN_TIME:
                notify(f"Error after session shutdown time ({e}) -- exiting for the day.", title="EP Long Daily -- Exit On Error", color=0xE74C3C)
                break
            print(f"Unhandled error: {e}")
            notify(f"Unhandled error, reconnecting in 5s: {e}", title="EP Long Daily -- Reconnect", color=0xE74C3C)
            time.sleep(5)
