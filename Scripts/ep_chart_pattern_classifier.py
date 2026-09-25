"""
EP Chart Pattern Classifier V1 -- see Files/EP/EP_Chart_Pattern_Classifier_Simple_V1.md
for the full spec. Rule-based, point-in-time-safe classification of the pre-EP chart
structure into: Deep Decline -> Sideways EP, Long Sideways EP, Already Strong /
Uptrending EP, Mixed / Other EP, or Unclear.

Point-in-time rule: all features use daily bars strictly BEFORE the EP date.
"""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta

import numpy as np
import openpyxl
import pandas as pd
import requests
from openpyxl.utils.datetime import from_excel
from dotenv import load_dotenv
from requests.adapters import HTTPAdapter
from tqdm import tqdm

sys.path.insert(0, os.path.dirname(__file__))
from build_v2_features import clean_ticker, resolve_historical_ticker, PLAN_CUTOFF

load_dotenv()
POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY")
if not POLYGON_API_KEY:
    sys.exit("POLYGON_API_KEY not found. Check your .env file.")

MASTER_ORDER_XLSX = os.path.join("Files", "EP", "Master Order of tickers", "Master Order of Tickers.xlsx")
OUTPUT_DIR = os.path.join("Files", "EP", "Data Pulls")

BASE_URL = "https://api.polygon.io"
MAX_RETRIES = 5
MAX_WORKERS = 10

# ---- centralized thresholds (V1, tune after reviewing sample output) ----
MIN_HISTORY_DAYS = 60          # below this many pre-EP trading days available -> Unclear
DECLINE_LOOKBACK_DAYS = 252    # window searched for the prior-peak -> trough (max drawdown)
DEEP_DECLINE_THRESH = -0.20    # max drawdown more negative than this -> a real "deep decline" happened
MIN_BASE_DAYS = 5              # trading days since the trough, minimum to call it a base (not just noise)
MAX_RECOVERY_FOR_DECLINE = 1.3 # if recovered beyond this much of the decline (i.e. well past the old peak
                                # into new highs), the decline is stale -- defer to the uptrend check instead

# "Long Sideways" (no real decline, just flat/choppy) still uses a backward flatness walk
LOOKBACK_WINDOWS = [20, 40, 60, 80, 100, 120, 140, 160, 180, 200, 220, 240, 252]
SIDEWAYS_TREND_THRESH = 0.15
SIDEWAYS_EFFICIENCY_THRESH = 0.35
SIDEWAYS_RANGE_THRESH = 1.00
MIN_SIDEWAYS_DAYS = 40

# "Already Strong / Uptrending" -- checked across multiple windows so a choppy final
# few weeks doesn't erase a longer real trend; larger window needs a bigger cumulative move.
UPTREND_WINDOWS = [
    # (n_days, min_return, min_efficiency) -- efficiency naturally runs lower over longer
    # windows even for genuine strong trends (daily noise keeps accumulating in the
    # denominator), so it's a low noise-filter here, not a strength requirement -- the
    # return threshold is what actually establishes "strong".
    (252, 0.50, 0.12),
    (120, 0.30, 0.12),
    (60, 0.20, 0.15),
]
NEAR_HIGH_THRESH = 0.20        # within this fraction of that window's own high

SESSION = requests.Session()
SESSION.mount("https://", HTTPAdapter(pool_connections=MAX_WORKERS, pool_maxsize=MAX_WORKERS))


def api_get(path, params=None):
    params = dict(params or {})
    params["apiKey"] = POLYGON_API_KEY
    url = f"{BASE_URL}{path}"
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = SESSION.get(url, params=params, timeout=30)
        except requests.exceptions.RequestException:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        if resp.status_code in (403, 404):
            return None
        resp.raise_for_status()
        return resp.json()
    return None


def get_daily_bars(ticker, from_date, to_date):
    path = f"/v2/aggs/ticker/{ticker}/range/1/day/{from_date}/{to_date}"
    data = api_get(path, {"adjusted": "true", "sort": "asc", "limit": 50000})
    if data is None or not data.get("results"):
        return None
    df = pd.DataFrame(data["results"])
    df["date"] = df["t"].apply(lambda ms: datetime.fromtimestamp(ms / 1000, tz=None).date())
    return df[["date", "o", "h", "l", "c"]].rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})


# ---------------------------------------------------------------------------
# Feature computation (all point-in-time: bars must already be strictly < EP date)
# ---------------------------------------------------------------------------

def trend_logret(closes, n):
    if len(closes) < n:
        return None
    y = np.log(closes[-n:].values)
    x = np.arange(n)
    slope, _ = np.polyfit(x, y, 1)
    return slope * n  # total trend-implied log return over the window


def directional_efficiency(closes, n):
    if len(closes) < n + 1:
        return None
    window = closes[-n:].values
    net = abs(window[-1] - window[0])
    total = np.abs(np.diff(window)).sum()
    if total == 0:
        return 0.0
    return net / total


def range_width(highs, lows, closes, n):
    if len(closes) < n:
        return None
    hi = highs[-n:].max()
    lo = lows[-n:].min()
    typical = closes[-n:].mean()
    if typical == 0:
        return None
    return (hi - lo) / typical


def trailing_return(closes, n):
    if len(closes) < n + 1:
        return None
    return closes.iloc[-1] / closes.iloc[-1 - n] - 1


def find_sideways_days(closes, highs, lows):
    sideways_days = 0
    for n in LOOKBACK_WINDOWS:
        if len(closes) < n:
            break
        tl = trend_logret(closes, n)
        eff = directional_efficiency(closes, n)
        rw = range_width(highs, lows, closes, n)
        if tl is None or eff is None or rw is None:
            break
        is_sideways = abs(tl) < SIDEWAYS_TREND_THRESH and eff < SIDEWAYS_EFFICIENCY_THRESH and rw < SIDEWAYS_RANGE_THRESH
        if is_sideways:
            sideways_days = n
        else:
            break
    return sideways_days


def find_max_drawdown(bars):
    """Find the single deepest peak-to-trough decline within DECLINE_LOOKBACK_DAYS.
    Returns None if there isn't enough data. The trough may be anywhere up to and
    including the last bar (i.e. still at/near the trough going into the EP)."""
    n = min(len(bars), DECLINE_LOOKBACK_DAYS)
    window = bars.iloc[-n:].reset_index(drop=True)
    highs, lows = window["high"], window["low"]

    running_peak = highs.iloc[0]
    running_peak_idx = 0
    best_dd = 0.0
    best_peak_idx, best_trough_idx = 0, 0
    for i in range(len(window)):
        if highs.iloc[i] > running_peak:
            running_peak = highs.iloc[i]
            running_peak_idx = i
        dd = lows.iloc[i] / running_peak - 1
        if dd < best_dd:
            best_dd = dd
            best_peak_idx, best_trough_idx = running_peak_idx, i

    if best_dd == 0.0:
        return None

    return {
        "decline_pct": best_dd,
        "peak_price": highs.iloc[best_peak_idx], "peak_date": window["date"].iloc[best_peak_idx],
        "trough_price": lows.iloc[best_trough_idx], "trough_date": window["date"].iloc[best_trough_idx],
        "base_days": len(window) - 1 - best_trough_idx,  # trading days from the trough to the day before the EP
    }


def recovery_from_trough(bars, drawdown):
    """How much of the peak-to-trough decline has been recovered by the last bar (day before EP).
    ~0 = still sitting at the trough. ~1 = fully back to the old peak. Can exceed 1 (new highs)."""
    span = drawdown["peak_price"] - drawdown["trough_price"]
    if span <= 0:
        return None
    last_close = bars["close"].iloc[-1]
    return (last_close - drawdown["trough_price"]) / span


def classify(bars):
    closes, highs, lows = bars["close"], bars["high"], bars["low"]
    n_bars = len(bars)

    diag = {"n_bars_available": n_bars}
    for n in [20, 60, 120, 252]:
        diag[f"return_{n}d"] = trailing_return(closes, n)
        diag[f"trend_logret_{n}d"] = trend_logret(closes, n)
        diag[f"efficiency_{n}d"] = directional_efficiency(closes, n)
        diag[f"range_width_{n}d"] = range_width(highs, lows, closes, n)

    if n_bars < MIN_HISTORY_DAYS:
        diag["sideways_days"] = None
        diag["prior_decline_pct"] = None
        return {
            "pattern": "Unclear",
            "reasoning": f"Only {n_bars} trading days of pre-EP history available (need at least {MIN_HISTORY_DAYS}) -- not enough data to classify the chart.",
            "sideways_days": None, "prior_decline_pct": None, "confidence": "Low",
        }, diag

    # --- Priority 1: was there a real decline into a trough, with time spent near it since? ---
    dd = find_max_drawdown(bars)
    diag["max_drawdown_pct"] = dd["decline_pct"] if dd else None
    diag["drawdown_base_days"] = dd["base_days"] if dd else None

    dd_recovery = recovery_from_trough(bars, dd) if dd else None
    dd_qualifies = (
        dd is not None and dd["decline_pct"] <= DEEP_DECLINE_THRESH and dd["base_days"] >= MIN_BASE_DAYS
        and (dd_recovery is None or dd_recovery <= MAX_RECOVERY_FOR_DECLINE)
    )

    if dd_qualifies:
        recovery = dd_recovery
        diag["recovery_from_trough_pct"] = recovery
        decline_pct, base_days = dd["decline_pct"], dd["base_days"]

        if recovery is not None and recovery >= 0.85:
            shape = "recovering most of the way back toward the prior high, completing a U"
        elif recovery is not None and recovery >= 0.4:
            shape = "perking up off the bottom, but still well below the prior high"
        else:
            shape = "still sitting near the bottom of that decline"

        pattern = "Deep Decline → Sideways EP"
        recovery_txt = f"{recovery * 100:.0f}%" if recovery is not None else "an undetermined amount"
        reasoning = (f"Declined about {abs(decline_pct) * 100:.0f}% from a prior peak ({dd['peak_date'].isoformat()}) "
                     f"to a trough on {dd['trough_date'].isoformat()}, then spent about {base_days} trading days "
                     f"since -- {shape} (recovered ~{recovery_txt} of the decline by the EP).")
        confidence = "High" if decline_pct <= DEEP_DECLINE_THRESH * 1.5 and base_days >= MIN_BASE_DAYS * 2 else "Medium"
        return {"pattern": pattern, "reasoning": reasoning, "sideways_days": base_days,
                "prior_decline_pct": decline_pct, "confidence": confidence}, diag

    diag["recovery_from_trough_pct"] = None

    # --- Priority 2: already strong / uptrending, checked across multiple windows ---
    best_uptrend = None
    for n, min_ret, min_eff in UPTREND_WINDOWS:
        if n_bars < n:
            continue
        ret = diag.get(f"return_{n}d") if n in (20, 60, 120, 252) else trailing_return(closes, n)
        eff = diag.get(f"efficiency_{n}d") if n in (20, 60, 120, 252) else directional_efficiency(closes, n)
        hi = highs[-n:].max()
        near_high = closes.iloc[-1] / hi - 1
        if ret is not None and ret >= min_ret and eff is not None and eff >= min_eff and near_high >= -NEAR_HIGH_THRESH:
            best_uptrend = {"n": n, "ret": ret, "eff": eff, "near_high": near_high}
            break  # UPTREND_WINDOWS is ordered longest-first -- prefer the longer-horizon signal

    if best_uptrend:
        n, ret, eff, near_high = best_uptrend["n"], best_uptrend["ret"], best_uptrend["eff"], best_uptrend["near_high"]
        pattern = "Already Strong / Uptrending EP"
        dd_txt = f"{abs(dd['decline_pct']) * 100:.0f}%" if dd else "N/A"
        reasoning = (f"Stock was already up about {ret * 100:.0f}% over the prior {n} trading days, with "
                     f"efficiency {eff:.2f}, and within {abs(near_high) * 100:.0f}% of its {n}-day high going into "
                     f"the EP -- no meaningful decline/base along the way (max drawdown {dd_txt}).")
        confidence = "High" if ret >= UPTREND_WINDOWS[0][1] * 1.3 else "Medium"
        return {"pattern": pattern, "reasoning": reasoning, "sideways_days": 0,
                "prior_decline_pct": None, "confidence": confidence}, diag

    # --- Priority 3: no real decline, no real uptrend -- is it just long and flat? ---
    sideways_days = find_sideways_days(closes, highs, lows)
    diag["sideways_days"] = sideways_days
    if sideways_days >= MIN_SIDEWAYS_DAYS:
        pattern = "Long Sideways EP"
        reasoning = (f"Traded in a non-directional range for approximately {sideways_days} trading days "
                     f"before the EP, without a major preceding decline or uptrend.")
        confidence = "Medium" if sideways_days >= MIN_SIDEWAYS_DAYS * 1.5 else "Low"
        return {"pattern": pattern, "reasoning": reasoning, "sideways_days": sideways_days,
                "prior_decline_pct": None, "confidence": confidence}, diag

    # --- Priority 4: doesn't fit cleanly ---
    ret60 = diag["return_60d"]
    eff60 = diag["efficiency_60d"]
    ret_txt = f"{ret60 * 100:.0f}%" if ret60 is not None else "N/A"
    eff_txt = f"{eff60:.2f}" if eff60 is not None else "N/A"
    pattern = "Mixed / Other EP"
    reasoning = (f"No clean decline/base, no clean long uptrend, and no long sideways period "
                 f"(60d return {ret_txt}, efficiency {eff_txt}) -- doesn't fit the main patterns cleanly.")
    return {"pattern": pattern, "reasoning": reasoning, "sideways_days": sideways_days,
            "prior_decline_pct": None, "confidence": "Low"}, diag


def process_event(ticker, event_date):
    lo = (event_date - timedelta(days=600))
    lo = max(lo, PLAN_CUTOFF)
    hi = event_date - timedelta(days=1)
    if lo > hi:
        return None, {"n_bars_available": 0}, ticker

    bars = get_daily_bars(ticker, lo.isoformat(), hi.isoformat())
    used_ticker = ticker
    if bars is None:
        resolved = resolve_historical_ticker(ticker, event_date)
        if resolved != ticker:
            bars = get_daily_bars(resolved, lo.isoformat(), hi.isoformat())
            used_ticker = resolved
    if bars is None or bars.empty:
        return {"pattern": "Unclear", "reasoning": "No pre-EP price data available.",
                "sideways_days": None, "prior_decline_pct": None, "confidence": "Low"}, {"n_bars_available": 0}, used_ticker

    bars = bars.sort_values("date").reset_index(drop=True)
    result, diag = classify(bars)
    return result, diag, used_ticker


def load_master_order(limit=None):
    wb = openpyxl.load_workbook(MASTER_ORDER_XLSX, data_only=True)
    ws = wb["Sheet1"]
    header = [c.value for c in ws[1]]
    idx = {h: i for i, h in enumerate(header)}
    events = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        ticker_raw = row[idx["Ticker"]]
        fd = row[idx["Full Date"]]
        if not ticker_raw or fd is None:
            continue
        if isinstance(fd, datetime):
            event_date = fd.date()
        elif isinstance(fd, (int, float)):
            event_date = from_excel(fd).date()
        else:
            event_date = date.fromisoformat(str(fd))
        events.append({"ticker_raw": ticker_raw, "ticker": clean_ticker(ticker_raw), "event_date": event_date})
    if limit:
        events = events[:limit]
    return events


def main():
    import argparse
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--label", type=str, default=None, help="Short unique name for this test run's output files")
    args = parser.parse_args()

    all_events = load_master_order()
    events = all_events[args.offset: args.offset + args.limit]
    print(f"Classifying {len(events)} events")

    main_rows, diag_rows = [], []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_event, e["ticker"], e["event_date"]): e for e in events}
        for future in tqdm(as_completed(futures), total=len(futures), desc="Classifying"):
            e = futures[future]
            result, diag, used_ticker = future.result()
            main_rows.append({
                "Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
                "Machine_Chart_Pattern": result["pattern"], "Machine_Chart_Reasoning": result["reasoning"],
                "Machine_Sideways_Days": result["sideways_days"], "Machine_Prior_Decline_Pct": result["prior_decline_pct"],
                "Machine_Confidence": result["confidence"],
                "Human_Chart_Pattern": "", "Human_Notes": "", "Human_Sideways_Start": "",
            })
            diag_rows.append({"Full Date": e["event_date"].isoformat(), "Ticker": e["ticker_raw"],
                              "Resolved Ticker": used_ticker, **diag})

    df_main = pd.DataFrame(main_rows)
    df_main = df_main.set_index("Ticker").loc[[e["ticker_raw"] for e in events]].reset_index()
    df_main = df_main[["Full Date", "Ticker", "Machine_Chart_Pattern", "Machine_Chart_Reasoning",
                        "Machine_Sideways_Days", "Machine_Prior_Decline_Pct", "Machine_Confidence",
                        "Human_Chart_Pattern", "Human_Notes", "Human_Sideways_Start"]]

    print(df_main.drop(columns=["Machine_Chart_Reasoning"]).to_string(index=False))
    print()
    for _, r in df_main.iterrows():
        print(f"{r['Ticker']} {r['Full Date']}: {r['Machine_Chart_Reasoning']}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    if args.limit >= 1000:
        tag = ""
    elif args.label:
        tag = f" - {args.label}"
    else:
        tag = f" - TEST offset{args.offset}-limit{args.limit}"
    out_path = os.path.join(OUTPUT_DIR, f"EP Chart Pattern{tag}.xlsx")
    diag_path = os.path.join(OUTPUT_DIR, f"EP Chart Pattern Diagnostics{tag}.xlsx")
    try:
        df_main.to_excel(out_path, index=False)
        pd.DataFrame(diag_rows).to_excel(diag_path, index=False)
        print(f"\nWrote {out_path}\nWrote {diag_path}")
    except PermissionError:
        print(f"\nCould not write (file likely open in Excel) -- results printed above only.")


if __name__ == "__main__":
    main()
