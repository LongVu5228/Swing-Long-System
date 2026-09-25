"""
V2 of the HTF daily-universe scan -- a new, SEPARATE dataset from
Files/Buyable Gap Up/scan_htf_universe.py, per user's explicit request (2026-09-14) to
run this as a parallel build rather than overwrite the pipeline they've already been
manually reviewing (Files/HTF/htf_1m_flag_review_by_date.csv has real in-progress work
in it). Nothing here touches that file, that script, or its raw_data_htf/ cache.

What changed vs. V1, and why (see project_htf_backtest_design memory for the full trail):
  - MKTCAP_MIN: $100M -> $50M. A real named Qullamaggie trade (INDO, entered 2022-03-03,
    "perfect, perfect high tight flag breakout") was checked against V1's raw data and
    found to fail the $100M gate by ~$11M ($89.17M actual) despite clearing every other
    gate by a wide margin and easily gapping through the RS cut. The $100M floor was
    never sourced from a Qullamaggie quote -- it came from the user's own live
    TradingView screener setup -- so this is real evidence it was excluding exactly the
    "shittier stock, bigger move" (Section 7.6) category his own biggest names sometimes
    come from.
  - Selection rule: top-2% PERCENTAGE cutoff -> FLAT top-16 count (settled 2026-09-14,
    after trying 10% and 5% first). A real named trade (ABAT, Oct 2025) was checked
    day-by-day and found to rank 15th-37th for a full 10 days while already up
    86-200%, before finally cracking a top-2% cutoff on 10/10 -- by which point the move
    was already mostly over. Loosening to 10% or 5% barely helped (still rank 14-16,
    still not until 10/9-10/10) -- a PERCENTAGE cutoff tightens automatically as the
    gated population grows, which is exactly what kept happening to ABAT as more names
    piled onto the list through early October. A FLAT count doesn't do that: checked
    against real data, top-16 catches ABAT on 10/1 (rank 16) instead. INDO (the other
    named-trade check, entered 2022-03-03, rank 3 of 153 that day) stays comfortably
    inside a top-16 cutoff either way, so this doesn't trade one real case for another.
  - NEW technical gate: rising 10-day AND rising 20-day SMA, evaluated as a hard P123-
    level AND-condition alongside ADR/ADV/mktcap (not a downstream local check like
    resistance_zigzag.py's pivot detection) -- explicit user choice, since folding it
    into the daily P123 scan keeps the candidate population small enough for the
    downstream Polygon-based pivot pass to stay cheap; doing it locally across the full
    unfiltered universe would not.
  - "Rising" definition (user's explicit "natural read" choice): each MA checked over
    its OWN period -- SMA10 compared to its value 10 trading days ago, SMA20 compared to
    its value 20 trading days ago (not a shared shorter lookback for both).
  - Scope: 1M only for now (ret_1m flat top-16 cut). ret_3m/ret_6m are NOT pulled in this
    version -- out of scope per the user's explicit answer, add back later if 3M/6M get
    revisited under this same design.

Formula note (verify-before-trust, same discipline as adr_formula()/MktCap before it):
SMA values are built the same manual-summation way as the project's existing adr14
formula (no confirmed native Sma() shortcut in P123's formula language) --
sma_rising_formula(N) returns (SMA_now - SMA_N_days_ago); positive means rising.
Thresholded locally in Phase 2 (>0), not baked into the raw pull, same reasoning as
every other threshold in this project: change it and re-run --filter-only for $0.

Usage:
    python scan_htf_universe_v2.py --smoke-test              # pulls+filters Jan of --start-year only
    python scan_htf_universe_v2.py                           # full ~20-year pull+filter (resumable pull)
    python scan_htf_universe_v2.py --start-year 2015 --end-year 2020
    python scan_htf_universe_v2.py --filter-only              # re-filter cached data only, 0 API calls
"""
import argparse
import os
import sys
import time
from datetime import date

import pandas as pd
import pandas_market_calendars as mcal
import pyarrow.parquet as pq

BGU_DIR = os.path.join(os.path.dirname(__file__), "..", "Buyable Gap Up")
sys.path.insert(0, BGU_DIR)
from p123_client import P123Client  # noqa: E402

UNIVERSE_NAME = "ApiUniverse"

# --- Thresholds: change these freely, then run --filter-only to re-apply for $0 ---
ADR_WINDOW = 14
ADR_PCT_MIN = 5.0
ADV_WINDOW = 30
ADV_MIN = 10_000_000
MKTCAP_MIN = 50  # in $millions -- lowered from V1's 100, see module docstring (INDO)
TOP_N = 16   # FLAT count cutoff, not a percentage. Tried 10%/5% first (2026-09-14) and
              # both failed to meaningfully fix the ABAT lag problem -- a PERCENTAGE cutoff
              # tightens automatically as the gated population grows, which is exactly what
              # kept pushing ABAT's effective bar higher every day through early October as
              # more names piled onto the list. A flat count doesn't do that: checked
              # against real data, top-16 catches ABAT on 10/1 (rank 16) instead of 10/9-10
              # under any percentage variant, while INDO (rank 3 of 153 on its 2022-03-03
              # entry day) stays comfortably inside it either way. 16 chosen as a round
              # number in the range both real cases validated against, not a further-tuned
              # optimum -- revisit if it turns out too loose/tight once the full history runs.
RET_WINDOWS = {"ret_1m": 21, "ret_3m": 63, "ret_6m": 126}  # ~21 trading days/month.
                          # 3M/6M added 2026-09-21 (were "1M for now" on 09-14). Pulled
                          # together because P123 cost scales with universe x dates, not
                          # formula count -- 6M rides along for ~free vs. a second full
                          # re-pull later. Years cached before this change lack the new
                          # columns; pull_year skips a year only if its parquet already
                          # has every column in FORMULA_NAMES, so re-running the pull
                          # refreshes exactly the stale years and nothing else.
SMA_PERIODS = (10, 20)  # both must be rising -- user's explicit "natural read": each MA
                          # checked over its own period, not a shared shorter lookback
# -----------------------------------------------------------------------------

DEFAULT_START_YEAR = 2005
DEFAULT_END_YEAR = date.today().year

RAW_DATA_DIR = os.path.join(os.path.dirname(__file__), "raw_data_htf_v2")
OUTPUT_CSV = os.path.join(os.path.dirname(__file__), "htf_universe_candidates_v2.csv")

# Market-cap tiers (2026-09-15, ARM investigation): a single combined ret_1m ranking
# structurally excludes mega-caps -- explosive small/micro-caps dominate every top-16 cut
# even on a day a mega-cap like ARM put up a textbook +58% HTF move. Bucket boundaries
# come from real per-day median gated-population counts checked against actual data
# (small ~27/day, mid ~12/day, large+ ~5/day) -- wide enough that each bucket still has a
# real population to rank within, not so wide it re-merges the mega-caps back into the
# small-cap flood. TOP_N (16) reused flat per bucket, not scaled down -- no evidence yet
# that a thinner bucket needs a smaller cutoff, and flat-16 is the same choice already
# validated against ABAT/INDO for the unbucketed version.
MKTCAP_BUCKETS = [
    ("small", 50, 2_000),
    ("mid", 2_000, 10_000),
    ("large_plus", 10_000, float("inf")),
]
OUTPUT_CSV_BUCKETED = os.path.join(os.path.dirname(__file__), "htf_universe_candidates_v2_bucketed.csv")

QUOTA_SAFETY_STOP = 100


def adr_formula() -> str:
    high_terms = "+".join(f"Hi({i})" for i in range(ADR_WINDOW))
    low_terms = "+".join(f"Low({i})" for i in range(ADR_WINDOW))
    return f"((({high_terms})-({low_terms}))/{ADR_WINDOW})/Close(0)*100"


def adv_formula() -> str:
    return f"AvgDailyTot({ADV_WINDOW})"


def mktcap_formula() -> str:
    return "MktCap"  # confirmed live 2026-09 (V1) -- returns dollars-in-millions


def ret_formula(n_days: int) -> str:
    return f"Close(0)/Open({n_days})-1"  # matches TradingView's Performance% formula, see V1


def sma_rising_formula(length: int) -> str:
    now_terms = "+".join(f"Close({i})" for i in range(length))
    prior_terms = "+".join(f"Close({i})" for i in range(length, length * 2))
    return f"(({now_terms})/{length})-(({prior_terms})/{length})"  # positive = rising


FORMULA_NAMES = ["adr14", "adv30", "mktcap"] + list(RET_WINDOWS.keys()) + ["sma10_rising_diff", "sma20_rising_diff"]
FORMULAS = (
    [adr_formula(), adv_formula(), mktcap_formula()]
    + [ret_formula(n) for n in RET_WINDOWS.values()]
    + [sma_rising_formula(10), sma_rising_formula(20)]
)


def trading_days_in_year(year: int) -> list:
    cal = mcal.get_calendar("NYSE")
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    if year == date.today().year:
        end = date.today().isoformat()
    schedule = cal.schedule(start_date=start, end_date=end)
    return [ts.date() for ts in schedule.index]


def raw_path(year: int) -> str:
    return os.path.join(RAW_DATA_DIR, f"{year}.parquet")


def _records_from_result(result: dict) -> list:
    records = []
    for entry in result.get("dates", []):
        dt = entry["dt"]
        tickers = entry["tickers"]
        cols = entry["data"]
        for i, ticker in enumerate(tickers):
            rec = {"date": dt, "ticker": ticker}
            for name, col in zip(FORMULA_NAMES, cols):
                rec[name] = col[i]
            records.append(rec)
    return records


def pull_year(client: P123Client, year: int) -> tuple:
    days = trading_days_in_year(year)
    if not days:
        return 0, 0, None
    as_of_dts = [d.isoformat() for d in days]

    result = client.post("/data/universe", {
        "type": "Stock", "universe": UNIVERSE_NAME, "formulas": FORMULAS, "asOfDts": as_of_dts,
    })

    records = _records_from_result(result)
    os.makedirs(RAW_DATA_DIR, exist_ok=True)
    df = pd.DataFrame(records)
    df.to_parquet(raw_path(year), index=False)
    return len(df), result.get("cost"), result.get("quotaRemaining")


def filter_all_cached_years() -> int:
    if not os.path.isdir(RAW_DATA_DIR):
        print(f"No cached raw data yet in {RAW_DATA_DIR}/ -- run a pull first.")
        return 0

    files = sorted(f for f in os.listdir(RAW_DATA_DIR) if f.endswith(".parquet"))
    if not files:
        print(f"No cached raw data yet in {RAW_DATA_DIR}/ -- run a pull first.")
        return 0

    frames = [pd.read_parquet(os.path.join(RAW_DATA_DIR, f)) for f in files]
    all_data = pd.concat(frames, ignore_index=True)
    all_data = all_data.dropna(subset=["adr14", "adv30", "mktcap", "sma10_rising_diff", "sma20_rising_diff"])

    pop = all_data[
        (all_data["adr14"] >= ADR_PCT_MIN)
        & (all_data["adv30"] >= ADV_MIN)
        & (all_data["mktcap"] >= MKTCAP_MIN)
        & (all_data["sma10_rising_diff"] > 0)
        & (all_data["sma20_rising_diff"] > 0)
    ].copy()

    # Each return window gets its OWN independent top-N cut on its own day/value (a ticker
    # can qualify_3m without qualifying_1m, etc.) -- rows are unioned across windows so a
    # ticker only needs to crack top-N on ANY one window to get a candidate row that day.
    keep_masks = []
    for win in RET_WINDOWS:
        pop[win] = pd.to_numeric(pop[win], errors="coerce")
        rank = pop.groupby("date")[win].rank(method="first", ascending=False)
        qualifies = (rank <= TOP_N) & pop[win].notna()
        pop[f"qualifies_{win.split('_')[1]}"] = qualifies
        keep_masks.append(qualifies)

    any_qualifies = pd.concat(keep_masks, axis=1).any(axis=1)
    candidates = pop[any_qualifies].copy()
    candidates = candidates.sort_values(["date", "ticker"]).reset_index(drop=True)
    candidates.to_csv(OUTPUT_CSV, index=False)

    print(f"Filtered {len(all_data):,} cached (ticker, date) rows across {len(files)} year(s)")
    print(f"  -> {len(pop):,} pass ADR>={ADR_PCT_MIN}%(14d), ADV>=${ADV_MIN:,.0f}, "
          f"MktCap>=${MKTCAP_MIN:,.0f}M, SMA10 & SMA20 both rising")
    for win in RET_WINDOWS:
        col = f"qualifies_{win.split('_')[1]}"
        print(f"  -> {candidates[col].sum():,} in the top {TOP_N} by count on {win}, per day")
    print(f"  -> {len(candidates):,} total candidate rows (union across windows)")
    print(f"Wrote {OUTPUT_CSV}")
    return len(candidates)


def _assign_bucket(mktcap: pd.Series) -> pd.Series:
    bucket = pd.Series(pd.NA, index=mktcap.index, dtype="object")
    for name, lo, hi in MKTCAP_BUCKETS:
        mask = (mktcap >= lo) & (mktcap < hi)
        bucket[mask] = name
    return bucket


def filter_all_cached_years_bucketed() -> int:
    if not os.path.isdir(RAW_DATA_DIR):
        print(f"No cached raw data yet in {RAW_DATA_DIR}/ -- run a pull first.")
        return 0

    files = sorted(f for f in os.listdir(RAW_DATA_DIR) if f.endswith(".parquet"))
    if not files:
        print(f"No cached raw data yet in {RAW_DATA_DIR}/ -- run a pull first.")
        return 0

    frames = [pd.read_parquet(os.path.join(RAW_DATA_DIR, f)) for f in files]
    all_data = pd.concat(frames, ignore_index=True)
    all_data = all_data.dropna(subset=["adr14", "adv30", "mktcap", "sma10_rising_diff", "sma20_rising_diff"])

    pop = all_data[
        (all_data["adr14"] >= ADR_PCT_MIN)
        & (all_data["adv30"] >= ADV_MIN)
        & (all_data["mktcap"] >= MKTCAP_MIN)
        & (all_data["sma10_rising_diff"] > 0)
        & (all_data["sma20_rising_diff"] > 0)
    ].copy()

    pop["mktcap_bucket"] = _assign_bucket(pop["mktcap"])
    pop = pop.dropna(subset=["mktcap_bucket"])  # drops nothing given MKTCAP_MIN floor, kept for safety

    # Same independent-per-window union as filter_all_cached_years(): each window ranks
    # within (date, bucket) on its own return column, top-N cut applied separately, rows
    # unioned so a ticker only needs to crack top-N on ANY one window that day.
    keep_masks = []
    for win in RET_WINDOWS:
        suffix = win.split("_")[1]
        pop[win] = pd.to_numeric(pop[win], errors="coerce")
        rank = pop.groupby(["date", "mktcap_bucket"])[win].rank(method="first", ascending=False)
        pop_size = pop.groupby(["date", "mktcap_bucket"])[win].transform("size")
        qualifies = (rank <= TOP_N) & pop[win].notna()
        pop[f"qualifies_{suffix}"] = qualifies
        pop[f"rank_in_bucket_{suffix}"] = rank.where(qualifies)
        pop[f"bucket_population_{suffix}"] = pop_size.where(qualifies)
        keep_masks.append(qualifies)

    any_qualifies = pd.concat(keep_masks, axis=1).any(axis=1)
    candidates = pop[any_qualifies].copy()
    candidates = candidates.sort_values(["date", "mktcap_bucket", "ticker"]).reset_index(drop=True)
    candidates.to_csv(OUTPUT_CSV_BUCKETED, index=False)

    print(f"Filtered {len(all_data):,} cached (ticker, date) rows across {len(files)} year(s)")
    print(f"  -> {len(pop):,} pass ADR>={ADR_PCT_MIN}%(14d), ADV>=${ADV_MIN:,.0f}, "
          f"MktCap>=${MKTCAP_MIN:,.0f}M, SMA10 & SMA20 both rising")
    for win in RET_WINDOWS:
        suffix = win.split("_")[1]
        col = f"qualifies_{suffix}"
        print(f"  -> {candidates[col].sum():,} in the top {TOP_N} per bucket per day on {win}")
        for name, lo, hi in MKTCAP_BUCKETS:
            n = len(candidates[(candidates["mktcap_bucket"] == name) & candidates[col]])
            hi_str = "+" if hi == float("inf") else f"-{hi:,.0f}M"
            print(f"       bucket '{name}' (${lo:,.0f}M{hi_str}): {n:,}")
    print(f"  -> {len(candidates):,} total candidate rows (union across windows)")
    print(f"Wrote {OUTPUT_CSV_BUCKETED}")
    return len(candidates)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-year", type=int, default=DEFAULT_START_YEAR)
    parser.add_argument("--end-year", type=int, default=DEFAULT_END_YEAR)
    parser.add_argument("--smoke-test", action="store_true",
                         help="pull just January of --start-year, print sample values, no filtering")
    parser.add_argument("--filter-only", action="store_true",
                         help="re-apply current thresholds to already-cached raw data -- 0 API calls")
    parser.add_argument("--filter-bucketed", action="store_true",
                         help="re-apply thresholds with market-cap bucketed top-N ranking (separate "
                              "output file, doesn't touch htf_universe_candidates_v2.csv) -- 0 API calls")
    parser.add_argument("--refresh", action="store_true",
                         help="re-pull years even if already cached (normally skipped)")
    args = parser.parse_args()

    print("Formulas (raw values cached, thresholds applied locally/for free):")
    for name, f in zip(FORMULA_NAMES, FORMULAS):
        print(f"  {name}: {f}")
    print(f"Current thresholds: adr14>={ADR_PCT_MIN}% adv30>=${ADV_MIN:,.0f} mktcap>=${MKTCAP_MIN:,.0f}M "
          f"sma10&sma20 rising, top {TOP_N} by count on ret_1m\n")

    if args.filter_only:
        filter_all_cached_years()
        return

    if args.filter_bucketed:
        filter_all_cached_years_bucketed()
        return

    client = P123Client()

    if args.smoke_test:
        print(f"SMOKE TEST -- pulling January {args.start_year} only, NOT writing the year cache")
        days = [d for d in trading_days_in_year(args.start_year) if d.month == 1]
        as_of_dts = [d.isoformat() for d in days]
        result = client.post("/data/universe", {
            "type": "Stock", "universe": UNIVERSE_NAME, "formulas": FORMULAS, "asOfDts": as_of_dts,
        })
        print(f"cost: {result.get('cost')}, quotaRemaining: {result.get('quotaRemaining')}")
        records = _records_from_result(result)
        df = pd.DataFrame(records)
        for col in ["mktcap", "sma10_rising_diff", "sma20_rising_diff"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        print(f"\n{len(df):,} rows pulled. non-null rates: "
              f"mktcap={df['mktcap'].notna().mean()*100:.1f}% "
              f"sma10={df['sma10_rising_diff'].notna().mean()*100:.1f}% "
              f"sma20={df['sma20_rising_diff'].notna().mean()*100:.1f}%")
        sample = df.dropna(subset=["mktcap"]).sort_values("mktcap", ascending=False).head(15)
        print(sample[["date", "ticker", "mktcap", "adr14", "sma10_rising_diff", "sma20_rising_diff"]].to_string(index=False))
        df.to_csv(os.path.join(os.path.dirname(__file__), "htf_universe_v2_SMOKETEST.csv"), index=False)
        print("\nWrote htf_universe_v2_SMOKETEST.csv for further inspection.")
        return

    years = list(range(args.start_year, args.end_year + 1))
    t0 = time.time()
    for year in years:
        if os.path.exists(raw_path(year)) and not args.refresh:
            cached_cols = set(pq.read_schema(raw_path(year)).names)
            if set(FORMULA_NAMES) <= cached_cols:
                print(f"  {year}: already cached with all formulas, skipping (use --refresh to force)")
                continue
            print(f"  {year}: cached but missing {sorted(set(FORMULA_NAMES) - cached_cols)} -- re-pulling")
        yt0 = time.time()
        n_rows, cost, quota = pull_year(client, year)
        print(f"  {year}: pulled {n_rows:,} rows, cost={cost}, quotaRemaining={quota}, "
              f"took {time.time()-yt0:.0f}s")
        if quota is not None and quota < QUOTA_SAFETY_STOP:
            print(f"\nStopping: quotaRemaining ({quota}) below safety threshold "
                  f"({QUOTA_SAFETY_STOP}). Re-run later to resume -- already-cached years are skipped.")
            break

    print(f"\nPull phase done ({time.time()-t0:.0f}s). Filtering...")
    filter_all_cached_years()


if __name__ == "__main__":
    main()
