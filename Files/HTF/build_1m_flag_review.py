"""
Builds the human-review CSV for the 1M HTF setup: cross-references confirmed LH
(lower-high) pivot events -- from resistance_zigzag.py, ported from the user's live
"KK Pinescript Tradingview" indicator -- against the qualifies_1m streak windows in
Files/Buyable Gap Up/htf_universe_candidates.csv.

Design (confirmed with user 2026-09-09, see project_htf_backtest_design memory):
  1. Collapse qualifies_1m==True rows into per-ticker streaks. A ticker dropping off
     the scanner for up to 2 TRADING days still counts as the same streak (per-ticker
     gap tolerance, trading-day-aware via the NYSE calendar -- NOT calendar days, since
     a Fri->Mon gap is 3 calendar days but 0 trading days and must not split a streak).
  2. For each distinct ticker, pull its full daily-bar history (buffered ~1yr before
     its earliest streak) and run compute_pivots() -- independent of scanner status,
     same as the live indicator would behave on a chart that doesn't know about any
     screener.
  3. Keep only confirmed LH (lower-high) pivots -- "made a high, pulled back, resistance
     line formed" -- NOT HH (still trending up, no flag yet). This is Option B: one row
     per distinct flag EPISODE, not one row per continuous scanner-presence streak, so a
     stock that flags multiple times while staying strong (e.g. NVAX in 2020, 7 separate
     LH episodes in one 10-month window) gets multiple review rows, not one that would
     silently drop everything but the most recent cycle.
  4. REVISED 2026-09-09 (real AAOI counter-example: 5/12/17 qualified, then dropped OFF
     the gate for the pullback/handle, requalified briefly on 5/22 and 5/26 -- three
     separate 1-day streaks under the old rule, none of which could ever contain the LH
     pivot's own confirmed_date, so this real setup was silently dropped entirely). A
     genuine base/pullback COOLS the 1-month return metric by definition -- requiring the
     LH pivot itself to fall inside a qualifying window is backwards, since the pullback
     is exactly when the stock is expected to fall OUT of a momentum-based RS gate.
     Fixed: match on the HH pivot immediately BEFORE each LH (the flagpole top) instead
     -- Qullamaggie's precondition is that the INITIAL MOVE is top-tier, not that the
     pullback also clears the bar. An LH survives if its preceding HH's pivot_date falls
     within HH_QUALIFY_WINDOW_DAYS of ANY qualifying day for that ticker (not necessarily
     the same streak) -- ties the pattern back to "this stock had a real, top-tier move,"
     without requiring the flag itself to re-clear a momentum filter it's supposed to fail.
  5. Streaks with no nearby matched LH (still making fresh highs, no pullback yet, or no
     real move preceded any pullback close enough) still get ONE placeholder row per
     streak with a blank suggested_resistance -- user confirmed it's fine to skip these
     without opening a chart.

Output columns (renamed 2026-09-09 for clarity, see project_htf_backtest_design memory):
ticker, revised_ticker (P123 "^YY" suffix stripped), first_qualifying_date (earliest day
this setup's ticker hit the scanner -- user's unique key), rank_that_day / population_that_day
(this ticker's 1-based rank by ret_1m among that day's gated population, and how many
tickers passed the gate that day -- e.g. "rank 8 of 310" -- automates the manual
AAOI/ABAT/AACG spot-checks done earlier in this project; built once, locally, from the
cached raw_data_htf/*.parquet, 0 extra API calls), hh_date (the flagpole top), hh_price,
pivot_kind (LH or HL), pullback_date (the pullback bar's own date, was "pivot_date"),
resistance_confirmed_date (was "confirmed_date" -- when suggested_resistance actually
became knowable, pullback_date + 2 trading days), suggested_resistance, is_valid_flag
(blank, user fills Y/N), resistance_override (blank, only if the suggestion is wrong).

Dropped 2026-09-09: matched_qualifying_date -- redundant once first_qualifying_date
exists (both prove the same no-lookahead fact; first_qualifying_date is simpler and is
the user's chosen key), and confusing alongside it (e.g. AACG's matched_qualifying_date
was identical to confirmed_date on every row, telling the user nothing extra).

Usage:
    python build_1m_flag_review.py --smoke-test          # first 20 tickers only
    python build_1m_flag_review.py                        # full run, all ~2,760 tickers
    python build_1m_flag_review.py --limit 200             # first N tickers (testing)
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
sys.path.insert(0, BGU_DIR)
sys.path.insert(0, SCRIPTS_DIR)

load_dotenv(os.path.join(REPO_ROOT, ".env"))

from fill_episodic_pivots_v3 import get_daily_bars, PLAN_CUTOFF  # noqa: E402
from build_benzinga_candidate_list import resolve_historical_ticker  # noqa: E402
from build_v2_features import clean_ticker  # noqa: E402
from resistance_zigzag import compute_pivots  # noqa: E402
from scan_htf_universe import ADR_PCT_MIN, ADV_MIN, MKTCAP_MIN  # noqa: E402 -- same gate,
                                                                  # single source of truth

CANDIDATES_CSV = os.path.join(BGU_DIR, "htf_universe_candidates.csv")
RAW_DATA_DIR = os.path.join(BGU_DIR, "raw_data_htf")
CACHE_DIR = os.path.join(os.path.dirname(__file__), "data_cache", "daily_bars")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "htf_1m_flag_review.csv")

MAX_STREAK_GAP_TRADING_DAYS = 3  # gap <= 3 trading days between qualifying dates = same
                                  # streak (up to 2 absent days in between); > 3 = new streak
PULL_BUFFER_DAYS = 365  # calendar days of history pulled BEFORE a ticker's earliest
                          # streak start, so pivots that predate the streak (like NVAX's
                          # early 2020 flagpole) are visible to the pivot detector
HH_QUALIFY_WINDOW_DAYS = 45  # calendar days, FORWARD-ONLY: a pullback (LH/HL) event counts
                               # as "tied to a real qualifying move" only if a qualifying
                               # day exists AT OR BEFORE its confirmed_date, and not more
                               # than this many days earlier -- never after (see the
                               # lookahead fix in process_ticker's matching loop). Bounded
                               # so a stale, unrelated qualifying day from years earlier
                               # still can't match.
PLACEHOLDER_SUPPRESS_WINDOW_DAYS = 60  # don't emit a "no_pivot_yet" placeholder for a
                                         # streak if a real matched LH already covers it
                                         # from within this many days -- avoids AAOI-style
                                         # redundant placeholders next to the real match
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
    """Loads every cached raw_data_htf/*.parquet (the pre-filter P123 pull -- ADR/ADV/
    mktcap/ret_1m for EVERY ticker EVERY day, not just the ones that made top-2%),
    re-applies the same gate as scan_htf_universe.py, then ranks each day's gated
    population by ret_1m descending. Lets each review row show 'this ticker ranked X of
    Y that day' directly, instead of requiring a manual one-off check like the AAOI/ABAT
    spot-checks earlier in this project (see project_htf_backtest_design memory).

    Returns (rank_lookup, count_lookup):
      rank_lookup[(date, raw_ticker)] -> 1-based rank that day (only gated tickers appear)
      count_lookup[date] -> total tickers that passed the gate that day
    """
    files = sorted(f for f in os.listdir(RAW_DATA_DIR) if f.endswith(".parquet"))
    frames = [pd.read_parquet(os.path.join(RAW_DATA_DIR, f)) for f in files]
    all_data = pd.concat(frames, ignore_index=True)
    all_data = all_data.dropna(subset=["adr14", "adv30", "mktcap", "ret_1m"])

    pop = all_data[
        (all_data["adr14"] >= ADR_PCT_MIN)
        & (all_data["adv30"] >= ADV_MIN)
        & (all_data["mktcap"] >= MKTCAP_MIN)
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
    pull_end = ticker_streaks["streak_end"].max()

    revised_ticker = clean_ticker(ticker)  # strips P123's "^YY" point-in-time suffix,
                                             # e.g. "AAI^11" -> "AAI" -- the real symbol,
                                             # though a delisted name still won't be
                                             # pullable on a live broker either way

    # Pull all the way through TODAY, not just a few days past the streak's end (pull_bars
    # clips to TODAY anyway) -- a real ABAT counter-example (Oct 2025) showed a violent
    # move's pullback can take well over a week to actually confirm (LH confirmed 10/23,
    # 8 days after the qualifying streak ended 10/15). Since this is historical backtesting,
    # not live monitoring, there's no cost reason to truncate the forward pull tightly --
    # always pulling to TODAY guarantees we see however long the real pullback took.
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

    # Pair each pullback-confirming event (LH OR HL -- see docstring point 6: an HL in an
    # active uptrend is just as real a "pause, here's the resistance" moment as an LH, it's
    # the AAOI-shape continuation flag rather than the NVAX-shape reversal flag, and the
    # algorithm's own resistance_after value is already correct for both) with the HH
    # immediately before it (the flagpole top).
    #
    # REVISED 2026-09-09 (real lookahead bug, caught by the user): a qualifying day must
    # fall AT OR BEFORE the pullback's confirmed_date, never after -- checking a symmetric
    # +/- window let a stock's LATER qualification (e.g. AAOI first qualifying on 5/12/17)
    # retroactively "justify" an EARLIER, unrelated pullback (a 5/1/17 HH -> pullback
    # confirmed 5/5/17, a week before AAOI ever qualified for anything). No real-time
    # trader running this exact scanner would have been watching AAOI on 5/5 -- it hadn't
    # earned a spot on the list yet. A qualifying day can only make a LATER pullback
    # reviewable, never one that already happened before discovery. HH_QUALIFY_WINDOW_DAYS
    # now bounds how far the qualifying day can be BEFORE the pullback confirms (not
    # "before or after" a pivot date), so a stale, unrelated qualifying day from years
    # earlier still can't match either.
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
                first_q = min(valid_q)  # first day (within the window) this setup's stock hit the
                                          # scanner -- user's chosen unique key for this setup
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

    print("building rank/population lookup from raw_data_htf (0 API calls, local only)...")
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
    # explicit column order (single source of truth, rather than relying on dict
    # insertion order matching across the 3 separate row-construction paths in
    # process_ticker) -- first_qualifying_date pinned 3rd per user's request, it's their
    # intended unique key
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
