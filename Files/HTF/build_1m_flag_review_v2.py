"""
V2 of the pivot-detection review builder -- same logic as build_1m_flag_review.py
(including every fix made to it: pandas 3.0's groupby().apply() column-drop bug, the
forward-only no-lookahead fix, pulling daily bars all the way to TODAY instead of a
narrow post-streak buffer, LH+HL matching, the rank/population lookup), just pointed at
the NEW v2 candidate set (Files/HTF/htf_universe_candidates_v2.csv: $50M mktcap, rising
10-day AND 20-day SMA required, flat top-16/day instead of a percentage cut -- see
scan_htf_universe_v2.py's own docstring for why each of those changed).

Deliberately a SEPARATE cache directory for daily bars (data_cache/daily_bars_v2/), not
reusing build_1m_flag_review.py's data_cache/daily_bars/ -- the underlying price data is
identical either way, but v2's earliest qualifying date for a given ticker can differ
from v1's, and pull_bars() trusts whatever's already cached without checking date
coverage (same risk class as the ABAT bug this project already hit once). Reusing the v1
cache blindly risks silently reintroducing exactly that bug for tickers where v2's
earliest date predates what v1 happened to cache. A little redundant Polygon traffic for
overlapping tickers is the safer trade.

The rank/population lookup's gate now ALSO requires both SMAs rising (v1's didn't have
this condition at all) -- imported directly from scan_htf_universe_v2 as the single
source of truth, same reasoning as v1 importing from scan_htf_universe.

Usage:
    python build_1m_flag_review_v2.py --smoke-test          # first 20 tickers only
    python build_1m_flag_review_v2.py                        # full run, all tickers
    python build_1m_flag_review_v2.py --limit 200             # first N tickers (testing)
"""
import argparse
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import pandas as pd
import pandas_market_calendars as mcal
from dotenv import load_dotenv
from tqdm import tqdm

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
BGU_DIR = os.path.join(os.path.dirname(__file__), "..", "Buyable Gap Up")
SCRIPTS_DIR = os.path.join(REPO_ROOT, "Scripts")
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, BGU_DIR)
sys.path.insert(0, SCRIPTS_DIR)

load_dotenv(os.path.join(BGU_DIR, ".env"))  # P123_API_ID/KEY live here, not repo root

from fill_episodic_pivots_v3 import get_daily_bars, PLAN_CUTOFF  # noqa: E402
from build_benzinga_candidate_list import resolve_historical_ticker  # noqa: E402
from build_v2_features import clean_ticker  # noqa: E402
from resistance_zigzag import compute_pivots  # noqa: E402
from scan_htf_universe_v2 import ADR_PCT_MIN, ADV_MIN, MKTCAP_MIN  # noqa: E402 -- v2's
                                                                     # gate, single source
                                                                     # of truth

CANDIDATES_CSV = os.path.join(os.path.dirname(__file__), "htf_universe_candidates_v2.csv")
RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "raw_data_htf_v2")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache", "daily_bars_v2")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "htf_1m_flag_review_v2.csv")

MAX_STREAK_GAP_TRADING_DAYS = 3
PULL_BUFFER_DAYS = 365
HH_QUALIFY_WINDOW_DAYS = 45
PLACEHOLDER_SUPPRESS_WINDOW_DAYS = 60
TODAY = date.today()


def build_streaks(candidates: pd.DataFrame) -> pd.DataFrame:
    df = candidates[candidates["qualifies_1m"] == True].copy()  # noqa: E712
    df["date"] = pd.to_datetime(df["date"]).dt.date

    cal = mcal.get_calendar("NYSE")
    schedule = cal.schedule(start_date=df["date"].min().isoformat(), end_date=TODAY.isoformat())
    trading_days = [ts.date() for ts in schedule.index]
    rank = {d: i for i, d in enumerate(trading_days)}
    df["rank"] = df["date"].map(rank)
    df = df.dropna(subset=["rank"]).sort_values(["ticker", "date"])

    df["gap"] = df.groupby("ticker")["rank"].diff()
    df["new_streak"] = df["gap"].isna() | (df["gap"] > MAX_STREAK_GAP_TRADING_DAYS)
    df["streak_id"] = df.groupby("ticker")["new_streak"].cumsum()

    streaks = (
        df.groupby(["ticker", "streak_id"])
        .agg(streak_start=("date", "min"), streak_end=("date", "max"))
        .reset_index()[["ticker", "streak_start", "streak_end"]]
    )
    return streaks


def build_rank_lookup() -> tuple:
    """Same idea as v1's build_rank_lookup(), but the gate ALSO requires both SMAs
    rising -- v2's actual gate, not just ADR/ADV/mktcap."""
    files = sorted(f for f in os.listdir(RAW_DATA_DIR) if f.endswith(".parquet"))
    frames = [pd.read_parquet(os.path.join(RAW_DATA_DIR, f)) for f in files]
    all_data = pd.concat(frames, ignore_index=True)
    all_data = all_data.dropna(subset=["adr14", "adv30", "mktcap", "ret_1m", "sma10_rising_diff", "sma20_rising_diff"])

    pop = all_data[
        (all_data["adr14"] >= ADR_PCT_MIN)
        & (all_data["adv30"] >= ADV_MIN)
        & (all_data["mktcap"] >= MKTCAP_MIN)
        & (all_data["sma10_rising_diff"] > 0)
        & (all_data["sma20_rising_diff"] > 0)
    ].copy()
    pop["date"] = pd.to_datetime(pop["date"]).dt.date
    pop["rank"] = pop.groupby("date")["ret_1m"].rank(method="first", ascending=False).astype(int)

    rank_lookup = {(row.date, row.ticker): row.rank for row in pop.itertuples()}
    count_lookup = pop.groupby("date").size().to_dict()
    return rank_lookup, count_lookup


def pull_bars(raw_ticker: str, pull_start: date, pull_end: date) -> pd.DataFrame:
    ticker = clean_ticker(raw_ticker)
    lo = max(pull_start, PLAN_CUTOFF)
    hi = min(pull_end, TODAY)
    if lo > hi:
        return None

    cache_path = os.path.join(CACHE_DIR, f"{raw_ticker}.csv")
    if os.path.exists(cache_path):
        return pd.read_csv(cache_path, parse_dates=["date"]).assign(
            date=lambda d: d["date"].dt.date
        )

    bars = get_daily_bars(ticker, lo.isoformat(), hi.isoformat())
    if bars is None:
        alt = resolve_historical_ticker(ticker, pull_end)
        if alt != ticker:
            bars = get_daily_bars(alt, lo.isoformat(), hi.isoformat())
    if bars is None or bars.empty:
        return None

    os.makedirs(CACHE_DIR, exist_ok=True)
    bars.to_csv(cache_path, index=False)
    return bars


def process_ticker(ticker: str, ticker_streaks: pd.DataFrame, qualifying_dates: list,
                    rank_lookup: dict, count_lookup: dict) -> list:
    pull_start = ticker_streaks["streak_start"].min() - timedelta(days=PULL_BUFFER_DAYS)

    revised_ticker = clean_ticker(ticker)

    bars = pull_bars(ticker, pull_start, TODAY)
    if bars is None or len(bars) < 10:
        return [{
            "ticker": ticker, "revised_ticker": revised_ticker,
            "streak_still_active": s.streak_end >= TODAY - timedelta(days=3),
            "hh_date": None, "hh_price": None, "pivot_kind": None, "pullback_date": None, "resistance_confirmed_date": None,
            "suggested_resistance": None, "first_qualifying_date": None,
            "rank_that_day": None, "population_that_day": None,
            "is_valid_flag": None, "resistance_override": None, "status": "no_daily_bars",
        } for s in ticker_streaks.itertuples()]

    bars = bars.sort_values("date").reset_index(drop=True)
    all_events = compute_pivots(bars, lb=2, rb=2)

    matched = []
    last_hh = None
    for ev in all_events:
        if ev.kind == "HH":
            last_hh = ev
        elif ev.kind in ("LH", "HL") and last_hh is not None and ev.resistance_after is not None:
            valid_q = [
                qd for qd in qualifying_dates
                if qd <= ev.confirmed_date and (ev.confirmed_date - qd).days <= HH_QUALIFY_WINDOW_DAYS
            ]
            if valid_q:
                first_q = min(valid_q)
                matched.append((ev, last_hh, first_q))

    rows = []
    for ev, hh, first_q in matched:
        rows.append({
            "ticker": ticker, "revised_ticker": revised_ticker, "streak_still_active": None,
            "hh_date": hh.date, "hh_price": hh.price, "pivot_kind": ev.kind,
            "pullback_date": ev.date, "resistance_confirmed_date": ev.confirmed_date,
            "suggested_resistance": ev.resistance_after,
            "first_qualifying_date": first_q,
            "rank_that_day": rank_lookup.get((first_q, ticker)),
            "population_that_day": count_lookup.get(first_q),
            "is_valid_flag": None, "resistance_override": None, "status": "OK",
        })

    for s in ticker_streaks.itertuples():
        covered = any(
            abs((hh.date - s.streak_start).days) <= PLACEHOLDER_SUPPRESS_WINDOW_DAYS
            or abs((hh.date - s.streak_end).days) <= PLACEHOLDER_SUPPRESS_WINDOW_DAYS
            for _, hh, _ in matched
        )
        if not covered:
            rows.append({
                "ticker": ticker, "revised_ticker": revised_ticker,
                "streak_still_active": s.streak_end >= TODAY - timedelta(days=3),
                "hh_date": None, "hh_price": None, "pivot_kind": None, "pullback_date": None, "resistance_confirmed_date": None,
                "suggested_resistance": None, "first_qualifying_date": None,
                "rank_that_day": None, "population_that_day": None,
                "is_valid_flag": None, "resistance_override": None, "status": "no_pivot_yet",
            })
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--workers", type=int, default=10)
    args = parser.parse_args()

    candidates = pd.read_csv(CANDIDATES_CSV)
    streaks = build_streaks(candidates)
    print(f"{len(streaks):,} streaks across {streaks['ticker'].nunique():,} tickers")

    qual = candidates[candidates["qualifies_1m"] == True].copy()  # noqa: E712
    qual["date"] = pd.to_datetime(qual["date"]).dt.date
    qual_by_ticker = qual.groupby("ticker")["date"].apply(list).to_dict()

    print("building rank/population lookup from raw_data_htf_v2 (0 API calls, local only)...")
    rank_lookup, count_lookup = build_rank_lookup()
    print(f"  {len(rank_lookup):,} (date, ticker) ranks, {len(count_lookup):,} distinct days")

    tickers = sorted(streaks["ticker"].unique())
    if args.smoke_test:
        tickers = tickers[:20]
    elif args.limit:
        tickers = tickers[: args.limit]
    print(f"processing {len(tickers):,} tickers")

    all_rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_ticker, t, streaks[streaks["ticker"] == t], qual_by_ticker[t],
                rank_lookup, count_lookup,
            ): t
            for t in tickers
        }
        for fut in tqdm(as_completed(futures), total=len(futures), desc="tickers"):
            t = futures[fut]
            try:
                all_rows.extend(fut.result())
            except Exception as e:  # noqa: BLE001
                all_rows.append({"ticker": t, "status": f"exception: {type(e).__name__}: {e}"})

    out = pd.DataFrame(all_rows)
    column_order = [
        "ticker", "revised_ticker", "first_qualifying_date",
        "rank_that_day", "population_that_day",
        "hh_date", "hh_price", "pivot_kind", "pullback_date", "resistance_confirmed_date",
        "suggested_resistance",
        "is_valid_flag", "resistance_override", "status",
        "streak_still_active",
    ]
    out = out[[c for c in column_order if c in out.columns] + [c for c in out.columns if c not in column_order]]
    out = out.sort_values(["ticker", "hh_date", "pullback_date"], na_position="first")
    out_path = OUTPUT_CSV.replace(".csv", "_SMOKETEST.csv") if args.smoke_test else OUTPUT_CSV
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out):,} rows to {out_path}")
    print(out["status"].value_counts())


if __name__ == "__main__":
    main()
