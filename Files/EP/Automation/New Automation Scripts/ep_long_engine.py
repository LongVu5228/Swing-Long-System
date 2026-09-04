"""
EP Swing-Long Engine -- DAS Trader Pro CMD API automation for the LONG side.

Implements "Chosen One #4" from the EP backtest project:
  E60M__S0.50ADR__TCLOSE_BELOW_20MA__EQUAL_DEPLETION__LSTART20__C50

  - Entry:  60-minute opening-range breakout (D0 9:30-10:30 ET high + 1 tick),
            watched via a resting buy-stop for up to 8 sessions (D0..D0+7).
  - Stop:   entry_fill * (1 - adr14 * 0.50), hard stop-market, live from fill.
  - Ladder: 10% of the ORIGINAL position sold at each of +20/27.5/35/42.5/50%
            (off entry fill). First rung fill steps the stop to breakeven.
  - Core:   the remaining 50% never sells on the ladder -- it rides until either
            the stop is hit or a day's close finalizes below its own 20-day SMA
            of closes (checked once per day, near the close).

See "Files/EP/Backtesting/Swing_Long_EP_Backtest_Session_Dump_2026-09-01.md"
(section 10, strategy #4) for where these numbers came from, and this
folder's README.md for setup, required Google Sheet columns, and the
specific assumptions/gotchas that don't translate perfectly from a vectorized
backtest to live trading (same-day-close exits, DAYCHART date format, route
codes that need confirming with the broker, etc).

Unlike the short-side scripts (Old Swing Short Scripts/), this is a single
CONTINUOUSLY RUNNING process, not a fresh daily launch -- EP long trades can
sit in the D0..D0+7 entry watch for over a week and, once filled, can be held
for weeks. All state that must survive a crash or the weekend maintenance
reboot (see WeekendWindowsMaintenance.ps1) is persisted to state/ep_long_state.json
and reconciled against live DAS positions/orders on every startup.

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
SHEET_NAME = os.environ.get("GOOGLE_SHEET_NAME", "EP Long Entry Sheet")
SHEET_TAB_INDEX = 0
TRADE_LOG_WORKSHEET = os.environ.get("TRADE_LOG_WORKSHEET", "EP Long Trade Log")

# =========================
# STRATEGY CONFIG -- Chosen One #4 (see module docstring)
# =========================
ENTRY_TF_MIN = 60                                     # opening-range window length, minutes from 9:30 ET
STOP_ADR_MULT = 0.50                                  # initial stop = entry_fill * (1 - adr14 * STOP_ADR_MULT)
TRAIL_MA_WINDOW = 20                                  # close-below-20-day-SMA trailing exit
LADDER_PCTS = [0.20, 0.275, 0.35, 0.425, 0.50]         # START20 ladder, gain % measured off entry fill
CORE_PCT = 0.50                                       # fraction of ORIGINAL shares that never sells on the ladder
PER_RUNG_FRACTION = (1.0 - CORE_PCT) / len(LADDER_PCTS)  # equal_depletion: 0.10 = 10% of original per rung
MAX_ENTRY_DAY_OFFSET = 7                              # entry watch expires after D0 + 7 trading sessions unfilled
DT_FAMILY_PATTERNS = {"DT", "DT SW", "DT U"}          # excluded chart_pattern values (backtest finding, session dump sec.3)

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
ROUTE_ENTRY = "PRO20"     # buy-stop entry order route -- CONFIRM
ROUTE_STOP = "SMAT"       # protective sell-stop route (DAS smart route, supports STOPMKT) -- reused from short side, lower risk
ROUTE_LADDER = "PRO20"    # resting limit sell (ladder rungs) route -- CONFIRM
ROUTE_EXIT = "PRO20"      # market/AtClose sell route for the trailing-stop full-position exit -- CONFIRM

# =========================
# STATE PERSISTENCE
# =========================
STATE_DIR = os.path.join(_SCRIPT_DIR, "state")
STATE_PATH = os.path.join(STATE_DIR, "ep_long_state.json")


def load_state() -> dict:
    if not os.path.isfile(STATE_PATH):
        return {"watches": {}, "positions": {}, "closed_positions": [], "last_close_check_date": None}
    with open(STATE_PATH, "r", encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("watches", {})
    state.setdefault("positions", {})
    state.setdefault("closed_positions", [])
    state.setdefault("last_close_check_date", None)
    return state


def save_state(state: dict) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)
    os.replace(tmp, STATE_PATH)


class WatchStatus(str, Enum):
    PENDING_OR = "PENDING_OR"   # before the opening-range window has closed
    ARMED = "ARMED"             # buy-stop resting at the broker
    ERROR = "ERROR"             # invalid geometry / no OR data -- will not be retried automatically


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


def acquire_singleton_lock(lock_name: str = "ep_long_engine.lock") -> None:
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
        print("EP Long engine appears to already be running. Exiting to prevent duplicate orders.")
        notify(
            "Startup blocked -- another instance appears active. Exiting to prevent duplicate orders.",
            title="EP Long -- Singleton lock",
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
    path = os.path.join(log_dir, f"ep_long_{datetime.now(ET).strftime('%Y%m%d')}.txt")
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
# GOOGLE SHEETS -- candidate read + optional trade log write
# =========================
_trade_log_broken = False


def get_candidates_from_sheet() -> List[dict]:
    """Reads the 'EP Long Entry Sheet' (tab 0). Required columns (case-insensitive):
    Ticker, Reaction Date, ADR14 %, Chart Pattern, Enabled. 'Gap %' is optional/informational.
    """
    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly", "https://www.googleapis.com/auth/drive.readonly"]
    json_path = os.path.join(_SCRIPT_DIR, SHEET_CREDENTIALS_FILE)
    creds = Credentials.from_service_account_file(json_path, scopes=scopes)
    client = gspread.authorize(creds)
    ws = client.open(SHEET_NAME).get_worksheet(SHEET_TAB_INDEX)
    if ws is None:
        return []
    rows = ws.get_all_values()
    if len(rows) < 2:
        return []
    header = [h.strip().lower() for h in rows[0]]

    def col(name: str) -> Optional[int]:
        return header.index(name) if name in header else None

    i_ticker = col("ticker")
    i_date = col("reaction date")
    i_adr = col("adr14 %")
    i_pattern = col("chart pattern")
    i_enabled = col("enabled")
    required = [i_ticker, i_date, i_adr, i_pattern, i_enabled]
    if None in required:
        print("ERROR: EP Long sheet missing a required column (Ticker / Reaction Date / ADR14 % / Chart Pattern / Enabled).")
        return []

    out = []
    width = max(x for x in required if x is not None) + 1
    for r in rows[1:]:
        r = r + [""] * (width - len(r))
        ticker = r[i_ticker].strip().upper()
        date_str = r[i_date].strip()
        pattern = r[i_pattern].strip().upper()
        enabled = r[i_enabled].strip().lower()
        try:
            adr14_pct = float(r[i_adr].replace("%", "").strip()) / 100.0
        except ValueError:
            adr14_pct = None
        if not (ticker and date_str and adr14_pct and enabled in ("true", "t", "1", "yes", "y")):
            continue
        if pattern in DT_FAMILY_PATTERNS:
            continue  # backtest-confirmed exclusion (session dump sec. 3) -- applied here, not inside the sim engine
        day0 = None
        for fmt in ("%m/%d/%Y", "%Y-%m-%d"):
            try:
                day0 = datetime.strptime(date_str, fmt).date()
                break
            except ValueError:
                continue
        if day0 is None:
            continue
        out.append({"ticker": ticker, "day0": day0, "adr14_pct": adr14_pct, "chart_pattern": pattern})
    return out


def log_trade_event_to_sheet(event: str, ticker: str, shares: int, price: float, note: str = "") -> None:
    global _trade_log_broken
    if _trade_log_broken:
        return
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        json_path = os.path.join(_SCRIPT_DIR, SHEET_CREDENTIALS_FILE)
        creds = Credentials.from_service_account_file(json_path, scopes=scopes)
        client = gspread.authorize(creds)
        ws = client.open(SHEET_NAME).worksheet(TRADE_LOG_WORKSHEET)
        ws.append_row(
            [datetime.now(ET).strftime("%Y-%m-%d %H:%M:%S"), event, ticker, shares, price, note],
            table_range="A1",
            value_input_option="USER_ENTERED",
        )
    except Exception as e:
        _trade_log_broken = True
        notify(
            f"Trade-log sheet write failed ({e}) -- disabling further sheet logging this session. Discord remains the record.",
            title="EP Long -- Trade Log Sheet Error",
            color=0xF39C12,
        )


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
    token = next_token()
    pending_token_context[token] = {"kind": "rung", "ticker": ticker, "rung_idx": rung_idx}
    send_line(sock, f"NEWORDER {token} S {ticker} {ROUTE_LADDER} {shares} {price:.2f} TIF=GTC+")
    return token


def place_trail_exit(sock: socket.socket, ticker: str, shares: int) -> int:
    token = next_token()
    pending_token_context[token] = {"kind": "exit", "ticker": ticker}
    send_line(sock, f"NEWORDER {token} S {ticker} {ROUTE_EXIT} {shares} MKT TIF={TRAIL_EXIT_TIF}")
    return token


# =========================
# CANDIDATE / WATCH LIFECYCLE
# =========================
def refresh_candidates(sock: socket.socket, state: dict) -> None:
    try:
        candidates = get_candidates_from_sheet()
    except Exception as e:
        notify(f"EP Long sheet read failed: {e}", title="EP Long -- Sheet Error", color=0xE74C3C)
        return
    today = datetime.now(ET).date()
    added = []
    for c in candidates:
        ticker = c["ticker"]
        if c["day0"] != today:
            continue  # OR can only be computed live on D0 itself -- a stale sheet row is not retroactively armed
        if ticker in state["watches"] or ticker in state["positions"]:
            continue
        watch = {
            "ticker": ticker,
            "day0": today.strftime("%Y-%m-%d"),
            "adr14_pct": c["adr14_pct"],
            "chart_pattern": c["chart_pattern"],
            "status": WatchStatus.PENDING_OR.value,
            "or_high": None,
            "trigger_price": None,
            "planned_stop_price": None,
            "planned_shares": None,
            "entry_order_token": None,
            "entry_order_id": None,
            "expiry_date": None,
            "last_error": None,
        }
        state["watches"][ticker] = watch
        send_line(sock, f"SB {ticker} Lv1")
        send_line(sock, f"SB {ticker} tms")
        now = datetime.now(ET)
        if now.strftime("%H:%M:%S") > "09:30:05":
            backfilled = backfill_or_from_minchart(sock, ticker, today, now.strftime("%H:%M"))
            if backfilled:
                or_high_tracker[ticker] = backfilled
        added.append(ticker)
    if added:
        save_state(state)
        notify(f"New EP long candidate(s) armed for today's OR watch: {', '.join(added)}.", title="EP Long -- New Candidates", color=0x3498DB)


def on_tick_price(state: dict, ticker: str, price: float, ts_time: str) -> None:
    watch = state["watches"].get(ticker)
    if not watch or watch["status"] != WatchStatus.PENDING_OR.value:
        return
    if datetime.now(ET).strftime("%Y-%m-%d") != watch["day0"]:
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
                title="EP Long -- OR Failed",
                color=0xE67E22,
            )
            watch["status"] = WatchStatus.ERROR.value
            watch["last_error"] = "no_or_ticks"
            save_state(state)
            continue

        trigger = round(or_high + 0.01, 2)
        planned_stop = round(trigger * (1 - watch["adr14_pct"] * STOP_ADR_MULT), 2)
        risk_per_share = trigger - planned_stop
        if risk_per_share <= 0:
            notify(
                f"{ticker}: invalid stop geometry (trigger ${trigger:.2f} <= planned stop ${planned_stop:.2f}, adr14={watch['adr14_pct']*100:.2f}%). Skipping.",
                title="EP Long -- Invalid Stop Geometry",
                color=0xE74C3C,
            )
            watch["status"] = WatchStatus.ERROR.value
            watch["last_error"] = "invalid_stop_geometry"
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
            title="EP Long -- Entry Armed",
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
            title="EP Long -- Watch Expired",
            color=0x95A5A6,
        )
        state["watches"].pop(ticker, None)
        save_state(state)


# =========================
# FILL HANDLING
# =========================
def on_entry_filled(sock: socket.socket, state: dict, ticker: str, qty: int, price: float) -> None:
    watch = state["watches"].pop(ticker, None)
    adr14_pct = watch["adr14_pct"] if watch else 0.0
    stop_price = round(price * (1 - adr14_pct * STOP_ADR_MULT), 2)

    ladder = []
    for pct in LADDER_PCTS:
        rung_price = round(price * (1 + pct), 2)
        rung_shares = int(round(qty * PER_RUNG_FRACTION))
        ladder.append(
            {"pct": pct, "price": rung_price, "shares": rung_shares, "order_token": None, "order_id": None, "filled": False, "filled_shares": 0}
        )

    position = {
        "ticker": ticker,
        "entry_fill": price,
        "entry_date": datetime.now(ET).strftime("%Y-%m-%d"),
        "shares_total": qty,
        "shares_remaining": qty,
        "stop_price": stop_price,
        "stop_order_token": None,
        "stop_order_id": None,
        "breakeven_applied": False,
        "ladder": ladder,
        "adr14_pct": adr14_pct,
    }
    state["positions"][ticker] = position
    save_state(state)

    ladder_desc = ", ".join(f"+{p*100:.1f}%→${r['price']:.2f} ({r['shares']}sh)" for p, r in zip(LADDER_PCTS, ladder))
    notify(
        f"{ticker}: ENTRY FILLED {qty}sh @ ${price:.2f}. Stop ${stop_price:.2f}. Ladder: {ladder_desc}. Core {CORE_PCT*100:.0f}% rides the {TRAIL_MA_WINDOW}-day SMA trail.",
        title="EP Long -- Entered",
        color=0x2ECC71,
    )
    log_trade_event_to_sheet("ENTRY", ticker, qty, price)

    position["stop_order_token"] = place_protective_stop(sock, ticker, qty, stop_price)
    for idx, rung in enumerate(ladder):
        if rung["shares"] <= 0:
            continue
        rung["order_token"] = place_ladder_rung(sock, ticker, rung["shares"], rung["price"], idx)
    save_state(state)


def on_rung_filled(sock: socket.socket, state: dict, ticker: str, rung_idx: int, qty: int, price: float) -> None:
    pos = state["positions"].get(ticker)
    if not pos:
        return
    rung = pos["ladder"][rung_idx]
    rung["filled"] = True
    rung["filled_shares"] = rung.get("filled_shares", 0) + qty
    pos["shares_remaining"] = max(0, pos["shares_remaining"] - qty)

    notify(
        f"{ticker}: ladder rung {rung_idx+1}/5 (+{LADDER_PCTS[rung_idx]*100:.1f}%) filled {qty}sh @ ${price:.2f}. Remaining: {pos['shares_remaining']}sh.",
        title="EP Long -- Partial Sold",
        color=0x2ECC71,
    )
    log_trade_event_to_sheet("PARTIAL", ticker, qty, price, note=f"rung {rung_idx+1}")

    if not pos["breakeven_applied"]:
        pos["breakeven_applied"] = True
        pos["stop_price"] = pos["entry_fill"]
        notify(f"{ticker}: breakeven stop armed @ ${pos['stop_price']:.2f}.", title="EP Long -- Breakeven Stop", color=0x3498DB)

    stop_order_id = pos.get("stop_order_id") or token_to_order_id.get(pos.get("stop_order_token"))
    if stop_order_id and pos["shares_remaining"] > 0:
        send_line(sock, f"REPLACE {stop_order_id} {pos['shares_remaining']} STOPMKT {pos['stop_price']:.2f}")
    save_state(state)


def on_stop_filled(sock: socket.socket, state: dict, ticker: str, qty: int, price: float) -> None:
    pos = state["positions"].get(ticker)
    if not pos:
        return
    pos["shares_remaining"] = max(0, pos["shares_remaining"] - qty)
    notify(f"{ticker}: STOPPED OUT {qty}sh @ ${price:.2f}.", title="EP Long -- Stopped Out", color=0xE74C3C)
    log_trade_event_to_sheet("STOP", ticker, qty, price)
    _cancel_remaining_ladder(sock, pos)
    close_position(state, ticker, "stopped_out")


def on_trail_exit_filled(sock: socket.socket, state: dict, ticker: str, qty: int, price: float) -> None:
    pos = state["positions"].get(ticker)
    if not pos:
        return
    pos["shares_remaining"] = max(0, pos["shares_remaining"] - qty)
    notify(f"{ticker}: TRAIL EXIT filled {qty}sh @ ${price:.2f} (close below {TRAIL_MA_WINDOW}-day SMA).", title="EP Long -- Trail Exit Filled", color=0xE67E22)
    log_trade_event_to_sheet("TRAIL_EXIT", ticker, qty, price)
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
def check_daily_trail_exit(sock: socket.socket, ticker: str) -> Tuple[bool, Optional[float]]:
    bars = fetch_daily_closes(sock, ticker)
    today = datetime.now(ET).date()
    prior_closes = [c for d, c in bars if d < today]
    if len(prior_closes) < TRAIL_MA_WINDOW - 1:
        notify(f"{ticker}: not enough daily-close history ({len(prior_closes)}) to evaluate the {TRAIL_MA_WINDOW}-day SMA trail today.", title="EP Long -- Trail Check Skipped", color=0xF39C12)
        return False, None
    prior_closes = prior_closes[-(TRAIL_MA_WINDOW - 1):]
    est_close = last_price_cache.get(ticker)
    if est_close is None:
        return False, None
    sma = (sum(prior_closes) + est_close) / TRAIL_MA_WINDOW
    return est_close < sma, est_close


def run_daily_close_checks(sock: socket.socket, state: dict) -> None:
    for ticker, pos in list(state["positions"].items()):
        exit_needed, est_close = check_daily_trail_exit(sock, ticker)
        if exit_needed and est_close is not None:
            _cancel_remaining_ladder(sock, pos)
            stop_order_id = pos.get("stop_order_id") or token_to_order_id.get(pos.get("stop_order_token"))
            if stop_order_id:
                send_line(sock, f"CANCEL {stop_order_id}")
            shares = pos["shares_remaining"]
            place_trail_exit(sock, ticker, shares)
            notify(
                f"{ticker}: close (~${est_close:.2f}) below {TRAIL_MA_WINDOW}-day SMA -- exiting remaining {shares}sh via {TRAIL_EXIT_TIF} order.",
                title="EP Long -- Trail Exit Triggered",
                color=0xE67E22,
            )


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
        on_entry_filled(sock, state, ticker, qty, price)
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
    last_price_cache[ticker] = price
    on_tick_price(state, ticker, price, ts_time)


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
    notify("Startup: reconciling persisted state against live DAS positions/orders...", title="EP Long -- Reconciling", color=0x3498DB)

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
            title="EP Long -- Reconcile Mismatch",
            color=0xE74C3C,
        )
    if missing_on_broker:
        notify(
            f"RECONCILE WARNING: locally-tracked position(s) show flat on DAS: {', '.join(sorted(missing_on_broker))}. "
            "Likely filled/stopped while offline -- removing from local tracking.",
            title="EP Long -- Reconcile Mismatch",
            color=0xF39C12,
        )
        for s in missing_on_broker:
            close_position(state, s, "reconciled_flat_on_restart")

    order_lines_upper = [l.upper() for l in raw_lines if l.upper().startswith("%ORDER") or l.upper().startswith("#ORDER")]
    for ticker, pos in list(state["positions"].items()):
        if ticker in missing_on_broker:
            continue
        has_resting_stop = any(ticker.upper() in l and "STOP" in l for l in order_lines_upper)
        if not has_resting_stop:
            notify(
                f"SAFETY: {ticker} has a live long position with NO resting stop order found on restart! Re-arming protective stop @ ${pos['stop_price']:.2f} now.",
                title="EP Long -- RE-ARMING STOP",
                color=0xE74C3C,
            )
            pos["stop_order_token"] = place_protective_stop(sock, ticker, pos["shares_remaining"], pos["stop_price"])
            pos["stop_order_id"] = None

    save_state(state)
    notify(
        f"Reconcile complete. Tracking {len(state['positions'])} open position(s), {len(state['watches'])} pending watch(es).",
        title="EP Long -- Reconcile Done",
        color=0x2ECC71,
    )


# =========================
# MAIN LOOP
# =========================
def main() -> None:
    state = load_state()
    rebuild_runtime_index_from_state(state)

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(READ_TIMEOUT_SEC)
    sock.connect((DAS_HOST, DAS_PORT))
    send_line(sock, f"LOGIN {DAS_USER} {DAS_PASS} {DAS_ACCT}")
    time.sleep(1.0)
    send_line(sock, "ReturnFullLv1 YES")

    try:
        reconcile_on_startup(sock, state)

        for ticker in list(state["watches"].keys()) + list(state["positions"].keys()):
            send_line(sock, f"SB {ticker} Lv1")
            send_line(sock, f"SB {ticker} tms")

        notify(
            f"EP Long engine started/reconnected. Tracking {len(state['watches'])} watch(es), {len(state['positions'])} position(s).",
            title="EP Long -- Started",
            color=0x2ECC71,
        )

        buf = b""
        last_ping = time.time()
        last_sheet_refresh_ts = 0.0
        last_close_check_date = state.get("last_close_check_date")
        last_heartbeat_hour = -1

        while True:
            now = datetime.now(ET)
            hhmmss = now.strftime("%H:%M:%S")
            weekday_ok = now.weekday() < 5

            if time.time() - last_ping > 45:
                send_line(sock, "TEST")
                last_ping = time.time()

            lines, buf = recv_lines(sock, buf)
            for line in lines:
                dispatch_line(sock, state, line)

            if weekday_ok and "08:55:00" <= hhmmss <= "10:35:00" and (time.time() - last_sheet_refresh_ts) > 120:
                refresh_candidates(sock, state)
                last_sheet_refresh_ts = time.time()

            if weekday_ok:
                finalize_or_and_arm_entries(sock, state, now)
                expire_stale_watches(sock, state, now)

            today_key = now.strftime("%Y-%m-%d")
            if weekday_ok and hhmmss >= CLOSE_CHECK_TIME and last_close_check_date != today_key and state["positions"]:
                run_daily_close_checks(sock, state)
                last_close_check_date = today_key
                state["last_close_check_date"] = today_key
                save_state(state)

            if now.minute == 0 and now.second < 2 and last_heartbeat_hour != now.hour:
                notify(
                    f"Heartbeat -- {len(state['watches'])} watch(es), {len(state['positions'])} open position(s).",
                    title="EP Long -- Heartbeat",
                    color=0x3498DB,
                )
                last_heartbeat_hour = now.hour

            idle = not (weekday_ok and "08:30:00" <= hhmmss <= "16:10:00")
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
        notify(f"Startup self-test failed: {e}. Refusing to start.", title="EP Long -- SELF-TEST FAILED", color=0xE74C3C)
        sys.exit(1)

    acquire_singleton_lock()

    while True:
        try:
            main()
        except (KeyboardInterrupt, SystemExit):
            break
        except Exception as e:
            print(f"Unhandled error: {e}")
            notify(f"Unhandled error, reconnecting in 5s: {e}", title="EP Long -- Reconnect", color=0xE74C3C)
            time.sleep(5)
