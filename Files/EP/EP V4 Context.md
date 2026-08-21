# Episodic Pivot V4 — Project Context

**Created:** 2026-08-21
**Dataset:** `Files/EP/EP V4.xlsx` (9,605 rows x 102 columns)
**Status:** Data pipeline complete. Ready for pivot-table / findings analysis (same next step V3 went through).

---

## 1. What V4 is, and why it exists

V3's candidate universe was built while the Polygon plan only had **5 years of daily-bars history**, so every gap/ADR/liquidity/market-cap filter — and therefore every candidate in V3 — was implicitly restricted to roughly **2021-08 → 2026-08**.

In 2026-08, the Polygon plan was upgraded to **20 years of bars history**. Benzinga's earnings feed (the source of every EP candidate) goes back to **2011-05-12**, which the new plan now fully covers. V4 is the same methodology as V3, re-run across the **full available history (2011 → today)** instead of just the last 5 years — roughly 3x the calendar range and a much larger, more statistically meaningful candidate set.

Nothing about the qualifying criteria changed. V4 is V3's pipeline, unblocked from its old plan ceiling.

---

## 2. Pipeline / process

Three scripts, run in sequence, all in `Scripts/`:

### Stage 0 — `pull_all_benzinga_earnings_raw.py` (exploratory, not part of the final pipeline)
Fast, unfiltered dump of every confirmed Benzinga earnings event, all columns, no Polygon calls (so no gap/ADR/etc. — just the raw feed). Used to size the problem before committing to a multi-hour run: **245,728 events, 9,146 unique tickers, 2011-05-12 → 2026-08-20** (Benzinga also had some already-confirmed future report dates past today, correctly out of scope for candidate filtering). Output: `Files/EP/Data Pulls/Benzinga All Earnings Raw.xlsx`.

### Stage 1 — `build_benzinga_candidate_list.py`
Pulls every confirmed Benzinga event ticker-agnostic (no per-ticker loop, no Master Order dependency), resolves the true reaction date from release timing (before-open/during-market/after-close, using the actual release timestamp — never picks whichever day's gap looks bigger), then computes point-in-time features from Polygon and applies the qualifying filters:

| Filter | Threshold |
|---|---|
| Gap % (open vs. prior close) | >= 5% |
| ADR (14-day average daily range) | >= 2% |
| Market cap (pre-gap) | >= $100M |
| Dollar volume (30D average) | >= $10M |

All four must pass (`final_ep_candidate = True`) for a row to become a candidate. Default range is now full history → today (previously required explicit `--from-date`/`--to-date`). Auto-writes a `PASSING ONLY` companion file (rows where all 4 filters pass) so there's no manual Excel filtering step anymore.

```
python Scripts/build_benzinga_candidate_list.py --label "Full History"
```
Output: `Benzinga EP Candidates - Full History.xlsx` (all 245,502 confirmed events + flags) and `Benzinga EP Candidates - PASSING ONLY - Full History.xlsx` (9,605 passing candidates).

### Stage 2 — `fill_episodic_pivots_v3.py`
Takes the passing-only candidate list and computes the full ~100-column V3 feature set: forward 1M/3M/6M highs/closes (measured from gap-day open, matching the project's MFE definition), TTM EPS/revenue growth, dividend yield, sector, intraday candle volumes (1/5/10/15/30/60min), SPY trend regime, all the bucket/category columns. Candidate-list path is now a `--input` override instead of a hardcoded file.

```
python Scripts/fill_episodic_pivots_v3.py --input "Files/EP/Data Pulls/Benzinga EP Candidates - PASSING ONLY - Full History.xlsx" --label "Full History"
```
Output: `Episodic Pivots V3 Filled - Full History.xlsx`, row-aligned and pasted into `Files/EP/EP V4.xlsx` (9,605 rows x 102 columns, same schema as `Episodic Pivots V3.xlsx`).

---

## 3. Bugs found and fixed during this build

Two real bugs surfaced while scaling the pipeline from a 5-year to a 15-year range — neither existed as a *visible* problem in V3 because V3's whole range sat inside the window where both bugs happen to behave correctly.

### 3.1 `build_v2_features.py`: `api_get()` crashed instead of retrying on network timeouts
Every other `api_get()` in this project wraps the request in try/except and retries with exponential backoff on `requests.exceptions.RequestException`. This one didn't — a plain read-timeout (routine on a run touching 245k events) propagated all the way up through the `ThreadPoolExecutor` and killed the whole process. Cost: lost 35 minutes of progress at 79% through the first full-history run.
**Fix:** added the same try/except-and-backoff wrapper the other scripts already use.

### 3.2 `build_benzinga_candidate_list.py`: every pre-2020 event's reaction date silently collapsed to 2020-01-02
This is the one that actually mattered. The NYSE trading-day calendar used to resolve each event's reaction date was built with `start_date="2020-01-01"`. For any `release_date` older than that, `TRADING_DAYS.searchsorted(...)` fell through to index 0 instead of raising — meaning **every one of the 105,333 pre-2020 events (43% of the full dataset) got its reaction date snapped to the exact same day: 2020-01-02.**

Practically, this meant gap%/ADR/liquidity/market-cap for every pre-2020 candidate were being computed against random Jan-2020 price action for whatever ticker, not the real earnings-day move. Symptom: the first full-history run produced only **7,108 passing candidates** total — barely more than V3's 5,754 from the 2021-2026 window alone, because 10 extra years of history were contributing almost nothing (pass rate ~0.05-0.1% for 2011-2019 vs. the real ~2-8% range). Verified against ground truth: pulled the actual `reaction_date` column and found literally every pre-2020 row equal to `2020-01-02`.

**Fix:** NYSE calendar now starts `2010-01-01` (comfortably before Benzinga's 2011-05-12 floor), plus an explicit bounds check so any future out-of-range date returns `None` (fails loudly) instead of repeating this silent-snap failure mode.

**After the fix**, a clean rerun produced smooth, continuous per-year numbers with no discontinuity — confirmed by re-summing the corrected per-year breakdown against the total.

---

## 4. Findings

### 4.1 Final counts (post-fix, current V4 dataset)
- **245,502** confirmed Benzinga earnings events, 2011-05-12 → 2026-08-20
- **9,605** pass all 4 qualifying filters → this is `EP V4.xlsx`
- V3 (2021-08 → 2026-08 only) had 5,754 passing candidates out of 108,700 events in that window — V4 roughly adds ~3,850 more candidates by reaching back to 2011.

### 4.2 Pass rate climbs steadily from ~2-3% (2012-2019) to ~7-8% (2024-2025)
This is real, not a residual bug — checked per-year `qualifies_gap` / `qualifies_adr` / `qualifies_liquidity` / `qualifies_mktcap` breakdowns individually and the climb is smooth across all four, no cliffs.

| Year | Pass rate |
|---|---|
| 2012 | 3.1% |
| 2015 | 1.9% |
| 2018 | 2.8% |
| 2020 | 4.3% |
| 2022 | 4.0% |
| 2024 | 5.3% |
| 2025 | 7.2% |

**Cause:** `MKTCAP_MIN` ($100M) and `DOLLARVOL_MIN` ($10M) are fixed nominal dollar thresholds, but the market is nominally much bigger today than in 2012 — S&P 500 was ~127 in Jan 2012 vs. ~764 today (2026-08-21), a ~6x difference, driven by market growth rather than CPI (actual CPI inflation over the same period is only ~1.35x, nowhere near enough to explain the gap). A static dollar bar filters out a much larger share of the 2012-era universe than today's.

### 4.3 Market-level-adjusted thresholds were evaluated and rejected
Computed what the candidate set would look like if `MKTCAP_MIN`/`DOLLARVOL_MIN` scaled per-event by `SPY_close_at_event_date / SPY_close_today` (continuous scaling from real Polygon SPY history, not year-bucketed):

- Scaled: **11,677 candidates**, 2,443 unique tickers (+22% vs. fixed)
- Fixed: **9,605 candidates**, 2,150 unique tickers

**Decision: kept fixed thresholds.** Reasoning:
- The lift was smaller than expected (~22%, not the ~50%+ that might close the visible pass-rate gap) because gap% and ADR% are already percentage-based and unaffected by scaling — they're doing most of the filtering already. Loosening the dollar thresholds only recovers candidates that were failing *specifically* on size/liquidity while already clearing both percentage bars.
- Scaling only ever needs to be a one-time historical-research decision (it does **not** create an ongoing maintenance burden — live/forward screening stays a fixed $100M/$10M bar regardless), but it does mean the historical dataset and the live screening rule would be answering slightly different questions (era-relative size vs. absolute size). Given the modest uplift, decided the added inconsistency wasn't worth it.
- Net effect: V4's pre-2020 candidates skew toward the largest/most-liquid movers of their era rather than a representative cross-section — accepted as a known limitation rather than corrected for.

---

## 5. File locations

| File | Purpose |
|---|---|
| `Scripts/pull_all_benzinga_earnings_raw.py` | Stage 0 (exploratory) — raw unfiltered dump |
| `Scripts/build_benzinga_candidate_list.py` | Stage 1 — candidate filtering |
| `Scripts/fill_episodic_pivots_v3.py` | Stage 2 — full feature fill |
| `Scripts/build_v2_features.py` | Shared helpers (`PLAN_CUTOFF`, `resolve_historical_ticker`, `clean_ticker`, `api_get`) imported by both stage 1 and stage 2 |
| `Files/EP/Data Pulls/Benzinga All Earnings Raw.xlsx` | Stage 0 output |
| `Files/EP/Data Pulls/Benzinga EP Candidates - Full History.xlsx` | Stage 1 output, all events + filter flags |
| `Files/EP/Data Pulls/Benzinga EP Candidates - PASSING ONLY - Full History.xlsx` | Stage 1 output, 9,605 passing candidates only |
| `Files/EP/EP V4.xlsx` | Final V4 dataset — Stage 2 output, pasted in (9,605 rows x 102 cols) |
| `Files/EP/V3/Swing_Long_EP_Master_Findings_CURRENT.md` | V3's quantitative findings doc (ADR, Turnover, outcome buckets) — V4's equivalent findings doc (pivot tables, win rates by bucket) has not been built yet |

## 6. Next step

`EP V4.xlsx` is a raw filled dataset, not yet analyzed — no pivot tables or win-rate findings built on it yet. The natural next step mirrors what happened after V3's raw fill: build PivotTables (ADR bucket, Turnover, Gap % category, etc.) against the outcome columns (1M/3M/6M High %, Close Performance %) and write up conclusions the way `Swing_Long_EP_Master_Findings_CURRENT.md` did for V3 — this time with ~1.7x more data and 15 years instead of 5.
