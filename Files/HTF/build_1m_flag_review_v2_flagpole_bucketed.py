"""
Bucketed variant of build_1m_flag_review_v2_flagpole.py, per user's ARM investigation
(2026-09-15): a single combined ret_1m ranking structurally excludes mega-caps, since
explosive small/micro-caps dominate every top-16 cut even on a day a mega-cap puts up a
textbook +58% move. scan_htf_universe_v2.py's filter_all_cached_years_bucketed() already
produces htf_universe_candidates_v2_bucketed.csv: top-16 per day WITHIN each of 3
market-cap tiers (small $50M-2B, mid $2B-10B, large_plus $10B+) instead of one global
top-16. This script is the exact same flagpole/pivot logic as the unbucketed version
(same HH-confirmed-by-LH/HL rule, same no-lookahead qualifying-date check), just pointed
at that bucketed candidate list, with mktcap_bucket carried through as its own column.

rank_that_day/population_that_day here mean rank/population WITHIN the ticker's bucket
that day, not the whole gated universe -- rank_in_bucket and bucket_population are already
computed in the candidates CSV itself (same groupby-rank-before-cut the unbucketed
script's build_rank_lookup() does, just done once during bucketed filtering instead of
being recomputed here), so no separate raw-parquet rebuild is needed.

Reuses the same daily-bars cache (data_cache/daily_bars_v2/) as the unbucketed version --
same tickers largely overlap, new bucket-only entrants (e.g. ARM, previously excluded by
the combined ranking) just trigger a fresh Polygon pull into the same cache.

Usage:
    python build_1m_flag_review_v2_flagpole_bucketed.py --smoke-test
    python build_1m_flag_review_v2_flagpole_bucketed.py
    python build_1m_flag_review_v2_flagpole_bucketed.py --limit 200
    python build_1m_flag_review_v2_flagpole_bucketed.py --tickers ARM,AAOI
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

load_dotenv(os.path.join(BGU_DIR, ".env"))

from fill_episodic_pivots_v3 import get_daily_bars, PLAN_CUTOFF  # noqa: E402
from build_benzinga_candidate_list import resolve_historical_ticker  # noqa: E402
from build_v2_features import clean_ticker  # noqa: E402
from resistance_zigzag import compute_pivots  # noqa: E402

CANDIDATES_CSV = os.path.join(os.path.dirname(__file__), "htf_universe_candidates_v2_bucketed.csv")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache", "daily_bars_v2")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "htf_1m_flag_review_v2_flagpole_bucketed.csv")

MAX_STREAK_GAP_TRADING_DAYS = 25  # widened from 3 (2026-09-15, W 4/16-10/16/2020 case): 3
                          # trading days only bridges literal continuous presence, not "same
                          # underlying multi-month campaign" -- W's real gaps off the top-16
                          # during that run were 6-28 trading days (rank cooled, never really
                          # died). ~25 trading days (~1 month) chosen as close to the existing
                          # 45-CALENDAR-day HH_QUALIFY_WINDOW_DAYS elsewhere in this file, not
                          # yet validated beyond the W case -- risk is merging two genuinely
                          # UNRELATED runs on the same ticker a month-ish apart into one row;
                          # revisit if that shows up in review.
MIN_STREAK_DAYS = 2  # drop one-off single-day scanner appearances, see build_streaks()
PULL_BUFFER_DAYS = 365
HH_QUALIFY_WINDOW_DAYS = 45
PLACEHOLDER_SUPPRESS_WINDOW_DAYS = 60
TODAY = date.today()


def build_streaks(candidates: pd.DataFrame, qual_col: str) -> tuple:
    df = candidates[candidates[qual_col] == True].copy()  # noqa: E712
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
        .agg(streak_start=("date", "min"), streak_end=("date", "max"), n_days=("date", "nunique"))
        .reset_index()[["ticker", "streak_id", "streak_start", "streak_end", "n_days"]]
    )

    # Drop one-off single-day streaks entirely (e.g. ARM 2026-02-25: on the scanner one
    # random day, gone the next -- not a real sustained relative-strength run, just noise
    # a flat top-16-per-bucket cut lets through). MIN_STREAK_DAYS requires the ticker to
    # have stayed on the scanner across at least 2 distinct days before it counts.
    keep_ids = streaks[streaks["n_days"] >= MIN_STREAK_DAYS][["ticker", "streak_id"]]
    streaks = streaks.merge(keep_ids, on=["ticker", "streak_id"])[
        ["ticker", "streak_start", "streak_end"]
    ].reset_index(drop=True)
    df = df.merge(keep_ids, on=["ticker", "streak_id"])

    return streaks, df


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


def _streak_for_date(qd: date, ticker_streaks: pd.DataFrame):
    for s in ticker_streaks.itertuples():
        if s.streak_start <= qd <= s.streak_end:
            return s
    return None


def process_ticker(ticker: str, ticker_streaks: pd.DataFrame, qualifying_dates: list,
                    meta_lookup: dict) -> list:
    pull_start = ticker_streaks["streak_start"].min() - timedelta(days=PULL_BUFFER_DAYS)
    revised_ticker = clean_ticker(ticker)

    empty_row = lambda s, status: {  # noqa: E731
        "ticker": ticker, "revised_ticker": revised_ticker,
        "streak_still_active": s.streak_end >= TODAY - timedelta(days=3),
        "first_qualifying_date": s.streak_start, "last_qualifying_date": s.streak_end,
        "mktcap_bucket": None, "bucket_population": None, "rank_on_first_qualifying_date": None,
        "best_rank_in_bucket": None, "worst_rank_in_bucket": None,
        "num_hh_flagpoles": 0, "hh_dates": None, "hh_confirmed_dates": None,
        "suggested_resistances": None, "latest_suggested_resistance": None,
        "is_valid_flag": None, "resistance_override": None, "status": status,
    }

    bars = pull_bars(ticker, pull_start, TODAY)
    if bars is None or len(bars) < 10:
        return [empty_row(s, "no_daily_bars") for s in ticker_streaks.itertuples()]

    bars = bars.sort_values("date").reset_index(drop=True)
    all_events = compute_pivots(bars, lb=2, rb=2)

    # Same ONE-flagpole-per-confirmed-HH rule as the unbucketed version -- but now grouped
    # by which continuous scanner STREAK the flagpole's qualifying date falls into, so a
    # ticker that stays on the scanner for weeks (rank fluctuating but never dropping off
    # for >3 trading days -- e.g. ARM 3/30-4/16/2026) gets ONE row listing every confirmed
    # HH during that stretch, instead of a separate row per HH. A gap >3 trading days off
    # the scanner (e.g. ARM's 2/25 -> 3/30 gap) still starts a new streak/row, same as the
    # existing no_pivot_yet placeholder logic already did.
    matched = []
    pending_hh = None
    pending_emitted = False
    for ev in all_events:
        if ev.kind == "HH":
            pending_hh = ev
            pending_emitted = False
        elif ev.kind in ("LH", "HL") and pending_hh is not None and not pending_emitted:
            valid_q = [
                qd for qd in qualifying_dates
                if qd <= pending_hh.confirmed_date and (pending_hh.confirmed_date - qd).days <= HH_QUALIFY_WINDOW_DAYS
            ]
            if valid_q:
                first_q = min(valid_q)
                matched.append((pending_hh, first_q))
            pending_emitted = True

    by_streak = {}  # streak_start -> {"streak": row, "hhs": [(hh, first_q), ...]}
    for hh, first_q in matched:
        s = _streak_for_date(first_q, ticker_streaks)
        if s is None:
            continue  # shouldn't happen -- first_q always comes from a qualifying date
        by_streak.setdefault(s.streak_start, {"streak": s, "hhs": []})["hhs"].append((hh, first_q))

    rows = []
    for streak_start, group in by_streak.items():
        s = group["streak"]
        hhs = sorted(group["hhs"], key=lambda pair: pair[0].date)
        dates_in_streak = sorted(qd for qd in qualifying_dates if s.streak_start <= qd <= s.streak_end)
        ranks = [
            meta_lookup[(qd, ticker)]["rank_in_bucket"]
            for qd in dates_in_streak if (qd, ticker) in meta_lookup
        ]
        bucket = next(
            (meta_lookup[(qd, ticker)]["mktcap_bucket"] for qd in dates_in_streak if (qd, ticker) in meta_lookup),
            None,
        )
        population_at_start = meta_lookup.get((s.streak_start, ticker), {}).get("bucket_population")
        rank_at_start = meta_lookup.get((s.streak_start, ticker), {}).get("rank_in_bucket")
        rows.append({
            "ticker": ticker, "revised_ticker": revised_ticker, "streak_still_active": None,
            "first_qualifying_date": s.streak_start, "last_qualifying_date": s.streak_end,
            "mktcap_bucket": bucket, "bucket_population": population_at_start,
            "rank_on_first_qualifying_date": rank_at_start,
            "best_rank_in_bucket": min(ranks) if ranks else None,
            "worst_rank_in_bucket": max(ranks) if ranks else None,
            "num_hh_flagpoles": len(hhs),
            "hh_dates": "; ".join(str(hh.date) for hh, _ in hhs),
            "hh_confirmed_dates": "; ".join(str(hh.confirmed_date) for hh, _ in hhs),
            "suggested_resistances": "; ".join(str(hh.price) for hh, _ in hhs),
            "latest_suggested_resistance": hhs[-1][0].price,
            "is_valid_flag": None, "resistance_override": None, "status": "OK",
        })

    covered_starts = set(by_streak.keys())
    for s in ticker_streaks.itertuples():
        if s.streak_start not in covered_starts:
            rows.append(empty_row(s, "no_pivot_yet"))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke-test", action="store_true")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--tickers", type=str, default=None, help="comma-separated ticker subset")
    parser.add_argument("--workers", type=int, default=10)
    parser.add_argument("--window", default="1m", choices=["1m", "3m", "6m"],
                        help="which return window's top-16 defines a qualifying day")
    args = parser.parse_args()

    # The candidates CSV carries every window side by side (qualifies_1m/3m/6m and
    # per-window rank/population); this picks one. Output file is named for the window.
    w = args.window
    qual_col, rank_col, pop_col = f"qualifies_{w}", f"rank_in_bucket_{w}", f"bucket_population_{w}"
    out_csv = OUTPUT_CSV.replace("htf_1m_", f"htf_{w}_")

    candidates = pd.read_csv(CANDIDATES_CSV)
    all_qual = candidates[candidates[qual_col] == True].copy()  # noqa: E712
    all_qual["date"] = pd.to_datetime(all_qual["date"]).dt.date
    streaks, qual = build_streaks(candidates, qual_col)  # qual = all_qual minus dropped one-off single-day streaks
    print(f"[{w}] {len(streaks):,} streaks (>= {MIN_STREAK_DAYS} days) across {streaks['ticker'].nunique():,} tickers "
          f"-- {all_qual['date'].shape[0] - qual['date'].shape[0]:,} single-day-streak rows dropped")

    qual_by_ticker = qual.groupby("ticker")["date"].apply(list).to_dict()

    # meta_lookup built from all_qual (unfiltered) is a strict superset -- fine to use, since
    # it's only ever looked up for dates already known to be in the filtered qualifying_dates.
    meta_lookup = {
        (row.date, row.ticker): {
            "mktcap_bucket": row.mktcap_bucket,
            "rank_in_bucket": getattr(row, rank_col),
            "bucket_population": getattr(row, pop_col),
        }
        for row in all_qual.itertuples()
    }

    tickers = sorted(streaks["ticker"].unique())
    if args.tickers:
        wanted = set(t.strip().upper() for t in args.tickers.split(","))
        tickers = [t for t in tickers if t.upper() in wanted]
    elif args.smoke_test:
        tickers = tickers[:20]
    elif args.limit:
        tickers = tickers[: args.limit]
    print(f"processing {len(tickers):,} tickers")

    all_rows = []
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_ticker, t, streaks[streaks["ticker"] == t], qual_by_ticker[t],
                meta_lookup,
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
        "ticker", "revised_ticker", "first_qualifying_date", "last_qualifying_date",
        "mktcap_bucket", "bucket_population", "rank_on_first_qualifying_date",
        "best_rank_in_bucket", "worst_rank_in_bucket",
        "num_hh_flagpoles", "hh_dates", "hh_confirmed_dates", "suggested_resistances",
        "latest_suggested_resistance",
        "is_valid_flag", "resistance_override", "status",
        "streak_still_active",
    ]
    out = out[[c for c in column_order if c in out.columns] + [c for c in out.columns if c not in column_order]]
    out = out.sort_values(["ticker", "first_qualifying_date"], na_position="first")
    out_path = out_csv.replace(".csv", "_SMOKETEST.csv") if args.smoke_test else out_csv
    out.to_csv(out_path, index=False)
    print(f"\nWrote {len(out):,} rows to {out_path}")
    print(out["status"].value_counts())


if __name__ == "__main__":
    main()
