"""
Noise/random-entry benchmark for the 4th chosen one (EBTA Ch.1 -- Aronson, Evidence-Based
Technical Analysis, 2007).

Aronson's core Ch.1 finding: a rule with ZERO predictive power still shows a positive
expected return if it has a long/short POSITION BIAS and the underlying market has a
nonzero net trend over the test window (his worked example: two pure-roulette-wheel
rules, 90% and 60% long, both show positive annualized returns over a bull period despite
having no signal at all -- the "edge" is 100% attributable to being long during an
uptrend). His fix (detrending the market index before computing rule returns) doesn't
translate directly to our event-driven, per-ticker, R-multiple setup -- the equivalent
here is a noise/random-entry benchmark.

Our EP strategy is ALWAYS long whenever in a trade (maximal position bias), tested over
2012-2026 (net bullish for small/mid-cap growth names). White's Reality Check / Hansen SPA
(run 2026-09-01) correct for search bias across 600 candidate exit-mechanics variants --
they say nothing about whether the EP entry TRIGGER (chart pattern + gap + ADR threshold)
itself adds real timing skill beyond simply being long a volatile small/mid-cap name during
a bull run.

This builds a noise benchmark using the EXACT SAME mechanics as the 4th chosen one
(E60M / 0.50ADR / close_below_20ma / equal_depletion / start20 / C50) -- same tickers, same
entry/stop/trail/partial-taking code -- but entered on RANDOM dates for those tickers
instead of real EP-trigger dates. If the real EP-triggered EV_R doesn't clear this noise
benchmark by a wide, statistically significant margin, "the edge" could be long-bias-in-a-
bull-market rather than genuine EP-specific timing skill.

Noise-date sampling constraints per ticker:
  - >= WARMUP_MIN trading days into that ticker's cached daily history (adr14 needs a
    14-day lookback with margin; the 20MA trail needs 20 days).
  - <= CUTOFF_DATE (data-availability buffer near "today").
  - NOT within +/- EXCLUSION_BUFFER trading days (by row-index proximity within that
    ticker's own trading-day sequence) of ANY real EP event date for that ticker -- across
    the full EP V5 universe, not just the 605 trades being benchmarked, so there's zero
    leakage of real EP-adjacent price action into the noise pool.
  - NOISE_PER_TRADE random draws per real trade instance (not per unique ticker), so a
    ticker that contributed 3 real trades gets proportionally more noise draws than one
    that contributed 1 -- matches the real sample's per-ticker weighting instead of
    treating every ticker equally regardless of how much it mattered to the real result.

adr14 is recomputed for each noise date using the exact formula EP V5's adr14 column was
built from (Scripts/build_benzinga_candidate_list.py, compute_features): mean(high) -
mean(low) over the 14 trading days strictly before the reaction date, divided by the prior
day's close (pre_gap_close). Stored here as the same decimal fraction convention
load_events.py uses (e.g. 0.0619, not 6.19).

Usage:
    python -m ep_backtest.noise_benchmark
"""

import os
import random
import time
from datetime import date

import numpy as np
import pandas as pd
from tqdm import tqdm

from . import calendar_utils, config, daily_bars, exits, minute_bars, multi_partial_taking
from .entry import find_entry
from .initial_stop import compute_initial_stop
from .load_events import load_ep_v5

ENTRY_TYPE, STOP_TYPE, TRAIL_TYPE = "60m", "0.50adr", "close_below_20ma"
SELL_STYLE, CORE_PCT, LADDER_NAME = "equal_depletion", 0.5, "start20"
TARGET_PCTS = config.V3_MULTI_TARGET_LADDERS[LADDER_NAME]
SELL_AMOUNT = config.V3_MULTI_SELL_AMOUNT_EQUAL
DT_FAMILY = ["DT", "DT SW", "DT U"]

WARMUP_MIN = 30
EXCLUSION_BUFFER = 15
CUTOFF_DATE = date(2026, 8, 18)
NOISE_PER_TRADE = 5
SEED = 42

REAL_SIM_PATH = os.path.join(config.OUTPUTS_DIR, "walkforward", "fourth_chosen_full_sim.pkl")
OUT_DIR = os.path.join(config.OUTPUTS_DIR, "robustness")


def compute_adr14(daily_df: pd.DataFrame, as_of_date: date):
    """Same formula as EP V5's adr14 column (build_benzinga_candidate_list.compute_features),
    returned as a decimal fraction (e.g. 0.0619) matching load_events.py's convention."""
    d = daily_df.sort_values("date").reset_index(drop=True)
    idx = d.index[d["date"] == as_of_date]
    if len(idx) == 0:
        return None
    i = idx[0]
    prior = d.iloc[:i]
    if len(prior) < 14:
        return None
    prior14 = prior.tail(14)
    pre_gap_close = prior["close"].iloc[-1]
    if not pre_gap_close:
        return None
    return float((prior14["high"].mean() - prior14["low"].mean()) / pre_gap_close)


def build_noise_events(real_trades: pd.DataFrame, all_events: pd.DataFrame) -> pd.DataFrame:
    rng = random.Random(SEED)
    real_dates_by_ticker = all_events.groupby("ticker")["reaction_date"].apply(set).to_dict()

    candidate_cache = {}
    used_by_ticker = {}
    noise_rows = []

    for ticker in tqdm(sorted(real_trades["ticker"].unique()), desc="building candidate pools"):
        daily_df = daily_bars.pull_ticker_daily_bars(ticker, real_trades[real_trades["ticker"] == ticker]["event_date"].min())
        if daily_df is None or daily_df.empty:
            candidate_cache[ticker] = []
            continue
        d = daily_df.sort_values("date").reset_index(drop=True)
        d = d[d["date"] <= CUTOFF_DATE].reset_index(drop=True)
        n = len(d)
        if n < WARMUP_MIN + 10:
            candidate_cache[ticker] = []
            continue

        real_idx = set()
        for rd in real_dates_by_ticker.get(ticker, set()):
            matches = d.index[d["date"] == rd]
            if len(matches):
                real_idx.add(matches[0])

        candidates = []
        for i in range(WARMUP_MIN, n):
            if any(abs(i - ri) <= EXCLUSION_BUFFER for ri in real_idx):
                continue
            candidates.append(d.loc[i, "date"])
        candidate_cache[ticker] = candidates
        used_by_ticker[ticker] = set()

    n_trade_instances = 0
    n_exhausted = 0
    for row in real_trades.itertuples():
        ticker = row.ticker
        pool = candidate_cache.get(ticker, [])
        available = [dt for dt in pool if dt not in used_by_ticker.get(ticker, set())]
        if not available:
            n_exhausted += 1
            continue
        draw_n = min(NOISE_PER_TRADE, len(available))
        drawn = rng.sample(available, draw_n)
        used_by_ticker[ticker].update(drawn)
        for dt in drawn:
            noise_rows.append({"ticker": ticker, "reaction_date": dt})
        n_trade_instances += 1

    print(f"built noise pool from {n_trade_instances}/{len(real_trades)} real trade instances "
          f"({n_exhausted} had no available candidate dates)")
    return pd.DataFrame(noise_rows)


def process_noise_event(ticker: str, noise_date: date):
    minute_df = minute_bars.get_event_window_minute_bars(ticker, noise_date)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, noise_date)
    if minute_df is None or minute_df.empty or daily_df is None or daily_df.empty:
        return {"ticker": ticker, "noise_date": noise_date, "status": config.STATUS_MISSING_MINUTE_DATA}

    adr14 = compute_adr14(daily_df, noise_date)
    if adr14 is None:
        return {"ticker": ticker, "noise_date": noise_date, "status": "MISSING_ADR14"}

    daily_sma = exits.add_sma10(daily_df)
    sessions = calendar_utils.sessions_from(noise_date, config.MAX_ENTRY_DAY_OFFSET + 1)

    try:
        entry = find_entry(minute_df, noise_date, sessions, ENTRY_TYPE)
    except ValueError:
        return {"ticker": ticker, "noise_date": noise_date, "status": "ENTRY_ERROR"}
    if entry.entry_status != config.STATUS_VALID_TRADE:
        return {"ticker": ticker, "noise_date": noise_date, "status": config.STATUS_NO_ENTRY}

    stop = compute_initial_stop(STOP_TYPE, entry, adr14)
    if not stop.valid:
        return {"ticker": ticker, "noise_date": noise_date, "status": stop.reason}

    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date, window=config.SMA20_WINDOW):
        return {"ticker": ticker, "noise_date": noise_date, "status": config.STATUS_INELIGIBLE_NO_10SMA}

    log = []
    mp = multi_partial_taking.run_multi_partial_position_management(
        minute_df, daily_sma, entry, stop.stop_price, entry.entry_fill, TRAIL_TYPE, TARGET_PCTS,
        SELL_STYLE, SELL_AMOUNT, CORE_PCT, sessions, log,
    )

    return {
        "ticker": ticker, "noise_date": noise_date, "status": mp.status,
        "entry_fill": entry.entry_fill, "initial_stop_price": stop.stop_price,
        "adr14": adr14, "n_sales": len(mp.sales), "realized_R": mp.realized_R,
    }


def block_bootstrap_mean(values: np.ndarray, block_length: int, n_boot: int, rng: np.random.Generator) -> np.ndarray:
    n = len(values)
    n_blocks = int(np.ceil(n / block_length))
    means = np.empty(n_boot)
    for b in range(n_boot):
        idx = []
        for _ in range(n_blocks):
            start = rng.integers(0, n)
            idx.extend([(start + k) % n for k in range(block_length)])
        means[b] = values[np.array(idx[:n])].mean()
    return means


def main():
    t0 = time.time()
    os.makedirs(OUT_DIR, exist_ok=True)

    print("loading real trades and full EP V5 universe...", flush=True)
    real_sim = pd.read_pickle(REAL_SIM_PATH)
    real_sim["event_date"] = pd.to_datetime(real_sim["event_date"])
    real_trades = real_sim[(real_sim["status"] == "OK") & (~real_sim["chart_pattern"].isin(DT_FAMILY))].copy()
    real_trades["event_date"] = real_trades["event_date"].dt.date
    print(f"{len(real_trades)} real trades (OK, non-DT-family)", flush=True)

    all_events = load_ep_v5()

    print("building noise-date candidate pools and drawing noise events...", flush=True)
    noise_events = build_noise_events(real_trades, all_events)
    noise_events = noise_events.drop_duplicates(subset=["ticker", "reaction_date"]).reset_index(drop=True)
    print(f"{len(noise_events)} unique noise (ticker, date) draws", flush=True)
    noise_events.to_csv(os.path.join(OUT_DIR, "noise_event_dates.csv"), index=False)

    print(f"prefetching minute bars for {len(noise_events)} noise events...", flush=True)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=15) as ex:
        futs = {
            ex.submit(minute_bars.get_event_window_minute_bars, row.ticker, row.reaction_date): (row.ticker, row.reaction_date)
            for row in noise_events.itertuples()
        }
        for _ in tqdm(as_completed(futs), total=len(futs), desc="minute bars"):
            pass

    print("simulating noise events...", flush=True)
    rows = []
    for i, row in enumerate(noise_events.itertuples()):
        r = process_noise_event(row.ticker, row.reaction_date)
        rows.append(r)
        if (i + 1) % 300 == 0:
            print(f"  {i+1}/{len(noise_events)} processed ({time.time()-t0:.0f}s)", flush=True)

    noise_df = pd.DataFrame(rows)
    noise_df.to_parquet(os.path.join(OUT_DIR, "noise_benchmark_trades.parquet"), index=False)
    print(f"\nnoise sim done: {noise_df['status'].value_counts().to_dict()}", flush=True)

    noise_ok = noise_df[noise_df["status"] == "OK"].sort_values("noise_date").reset_index(drop=True)
    real_ok = real_trades.sort_values("event_date").reset_index(drop=True)

    print(f"\n=== POINT ESTIMATES ===", flush=True)
    n_real, n_noise = len(real_ok), len(noise_ok)
    real_R, noise_R = real_ok["realized_R"].to_numpy(), noise_ok["realized_R"].to_numpy()
    real_ev, noise_ev = real_R.mean(), noise_R.mean()
    real_wr = (real_R > 0).mean()
    noise_wr = (noise_R > 0).mean()
    real_pf = real_R[real_R > 0].sum() / abs(real_R[real_R < 0].sum())
    noise_pf = noise_R[noise_R > 0].sum() / abs(noise_R[noise_R < 0].sum())
    print(f"REAL  (EP-triggered): n={n_real}, win_rate={real_wr*100:.1f}%, PF={real_pf:.3f}, "
          f"EV_R={real_ev:.4f}, total_R={real_R.sum():.2f}", flush=True)
    print(f"NOISE (random entry): n={n_noise}, win_rate={noise_wr*100:.1f}%, PF={noise_pf:.3f}, "
          f"EV_R={noise_ev:.4f}, total_R={noise_R.sum():.2f}", flush=True)
    print(f"EV_R real - noise = {real_ev - noise_ev:.4f} ({(real_ev-noise_ev)/abs(noise_ev)*100 if noise_ev else float('nan'):+.1f}% relative)", flush=True)

    print(f"\n=== TWO-SAMPLE BLOCK BOOTSTRAP: H0 = real mean R <= noise mean R ===", flush=True)
    rng = np.random.default_rng(SEED)
    B = 2000
    results = []
    for block_len in [1, 10, 25, 50]:
        real_boot = block_bootstrap_mean(real_R, block_len, B, rng)
        noise_boot = block_bootstrap_mean(noise_R, block_len, B, rng)
        diff = real_boot - noise_boot
        p_value = float((diff <= 0).mean())
        ci_low, ci_high = np.percentile(diff, [2.5, 97.5])
        results.append({"block_length": block_len, "mean_diff": diff.mean(), "ci_low": ci_low,
                         "ci_high": ci_high, "p_value_real_not_gt_noise": p_value})
        print(f"  block_length={block_len:>3}: mean(real-noise) diff={diff.mean():+.4f}, "
              f"95% CI=[{ci_low:+.4f}, {ci_high:+.4f}], p(real<=noise)={p_value:.4f}", flush=True)

    pd.DataFrame(results).to_csv(os.path.join(OUT_DIR, "noise_benchmark_bootstrap.csv"), index=False)
    print(f"\ntotal elapsed: {time.time()-t0:.0f}s", flush=True)
    print(f"outputs written to {OUT_DIR}", flush=True)


if __name__ == "__main__":
    main()
