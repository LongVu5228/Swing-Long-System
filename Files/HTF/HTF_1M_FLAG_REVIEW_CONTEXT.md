# HTF 1M Flag Review — Project Context

> This document is a self-contained briefing for an AI assistant with no prior knowledge of this
> project. It explains what is being built, why, how the data was generated, what every column in
> the output file means, and which design decisions are already settled (and why). Read it before
> answering questions about the dataset.

---

## 1. What this project is

A systematic historical backtest of **Qullamaggie's "high tight flag" (HTF) setup**, run over US
equities from **2005 to present**.

Qullamaggie (Kristjan Kullamägi) is a Swedish swing trader known for trading a small number of
momentum setups. The "high tight flag" is one of them: a stock makes an explosive, near-vertical
price advance (the **flagpole**), then pauses and consolidates tightly near the highs (the **flag**)
without giving back much of the gain. The trade is a breakout above the consolidation, betting the
advance resumes.

The goal of this project is **not** to auto-generate trade signals. It is to produce a
**human-reviewable candidate list**: every historical instance where a realistic, real-time scanner
would have surfaced a stock that then formed a flag-like structure. The user then manually opens each
chart and labels whether it was a genuine HTF setup. That labeled dataset is the actual deliverable —
it's what makes it possible to later measure base rates, win rates, and which screening criteria
actually matter.

**Key framing:** this is a *recall-oriented* pipeline. It is designed to surface candidates for human
eyes, not to be precise on its own. A moderate amount of junk in the list is acceptable; systematically
missing real setups is not.

---

## 2. The two data sources

| Source | Role | Notes |
|---|---|---|
| **Portfolio123 (P123)** REST API | The daily universe scanner. For every trading day 2005→today, computes fundamental/technical values for every US stock. | `/data/universe` endpoint. Uses a custom formula language. Metered by quota. |
| **Polygon.io** | Daily OHLCV bars for individual candidate tickers, used for the pivot/pattern detection stage. | `/v2/aggs/ticker/{t}/range/1/day/...` |

**Two-phase design:** the expensive P123 pull is done once and cached to Parquet (`raw_data_htf_v2/*.parquet`,
one file per year, ~37.6M ticker-day rows). All thresholds are then applied **locally** against that cache,
so re-tuning a threshold costs $0 and takes seconds rather than re-hitting the API. This is why thresholds
live as constants in the filter step, not baked into the pulled formulas.

---

## 3. The filter stack (in order)

### Stage 1 — P123 daily universe gate
Applied to every US stock, every trading day. **All five conditions must hold simultaneously (AND).**

| Criterion | Threshold | Formula as submitted to P123 |
|---|---|---|
| ADR% (14-day Average Daily Range) | ≥ 5.0% | `((ΣHi(0..13) − ΣLow(0..13))/14) / Close(0) × 100` |
| Average dollar volume (30-day) | ≥ $10,000,000 | `AvgDailyTot(30)` |
| Market capitalization | ≥ $50M | `MktCap` (returns $ in millions) |
| 10-day SMA rising | > 0 | `avg(Close 0..9) − avg(Close 10..19)` |
| 20-day SMA rising | > 0 | `avg(Close 0..19) − avg(Close 20..39)` |

Notes on these:
- **ADR%** is a volatility filter — it selects stocks that actually move enough to be worth trading.
  This formula is algebraically identical to the TradingView ADR indicator the user runs live.
  *Known quirk:* it systematically **understates** volatility during fast sustained run-ups, because
  it divides a blend of older (lower-priced) dollar ranges by today's much higher close. A stock in a
  violent uptrend can read ~4.3% on this formula while "feeling" far more volatile. This has caused
  real misses (see §7).
- **SMA "rising"** is defined as *net change over the MA's own period* — i.e. the 10-day SMA today vs.
  the 10-day SMA ten trading days ago. It is **not** a day-over-day tick check. This is more forgiving
  than it sounds: a short 3–5 day pullback can still leave the average net higher. But an extended
  base or deep consolidation **will** flip it negative and drop the stock off the scanner for those days.
- There is **no price minimum, no float filter, no sector exclusion, and no fundamental/earnings screen.**

### Stage 2 — Market-cap bucketing, then relative-strength ranking
Everything that clears Stage 1 is split by **that day's** market cap into three tiers:

| Bucket | Range |
|---|---|
| `small` | $50M – $2B |
| `mid` | $2B – $10B |
| `large_plus` | $10B+ |

Within each bucket, stocks are ranked by **1-month return**, defined as `Close(0) / Open(21) − 1`
(today's close vs. the open 21 trading days ago — this matches TradingView's Performance% convention,
which uses the *open* of the reference bar, not the close).

**Top 16 per bucket per day** are kept.

Two decisions embedded here, both driven by real cases rather than theory:
- **Flat count (16), not a percentage.** A percentage cutoff (top 2%/5%/10% was tried) tightens
  automatically as the qualifying population grows, which repeatedly pushed real setups off the list
  exactly when momentum was broadening. A real trade (ABAT, Oct 2025) ranked 15th–37th for ten straight
  days while already up 86–200%, and only cracked a top-2% cut on 10/10, by which point the move was
  largely over. A flat top-16 catches it on 10/1.
- **Bucketing by market cap.** A single combined ranking structurally excludes large- and mega-caps,
  because explosive micro/small-caps dominate every return-percentile cut. ARM's textbook +58% one-month
  advance in spring 2026 never cracked a combined top-16. Under bucketing it ranks as high as 2nd in
  `large_plus`. Qullamaggie himself notes liquid large-caps set up rarely but are tradeable when they do.

### Stage 3 — Flagpole confirmation (pattern detection)
Candidates from Stage 2 get their Polygon daily bars pulled, and a **zigzag/pivot state machine**
(ported from the user's own TradingView Pine Script indicator) runs over them.

The state machine classifies each confirmed pivot as:
- **HH** — Higher High (a new swing high above the prior swing high)
- **LH** — Lower High (a swing high that failed to exceed the prior one)
- **HL** — Higher Low (a swing low above the prior swing low)
- **LL** — Lower Low

Pivot confirmation uses `lb=2, rb=2` — two bars on each side. This means **a pivot is only known to be a
pivot 2 trading days after it happened.** That lag is real and deliberately preserved.

A row is emitted only when:
1. A **confirmed HH** exists (the flagpole peak), **and**
2. That HH is **followed by an LH or HL** — proving an actual pullback/consolidation formed against it,
   rather than the stock simply continuing to make fresh highs with no pause, **and**
3. The stock had **already appeared on the scanner** (Stage 2) on a date **at or before the HH's
   confirmation date** — this is the **no-lookahead rule**, and it is strict. A stock cannot have a past
   setup retroactively justified by a scanner appearance that happened later. Violating this was a real
   bug that got fixed; it silently inflated results.
4. That scanner appearance was within **45 calendar days** before the HH confirmed.

`suggested_resistance` is always the HH price itself. (Intermediate LH levels were deliberately dropped:
in the state machine an HL never updates resistance, so LH/HL-derived levels were either exact duplicates
of the HH price or strictly lower, already-failed levels. Only the original flagpole high is treated as a
level worth watching.)

### Stage 4 — Streak grouping and noise removal
- Consecutive scanner appearances are grouped into a **streak**. Appearances within **25 trading days**
  of each other belong to the same streak. One row is emitted per streak, listing **every** confirmed HH
  within it (semicolon-separated), rather than one row per HH.
  - *Rationale:* a stock in a genuine multi-month run drops in and out of the top 16 as its rank fluctuates,
    without the underlying story changing. W (Wayfair) in 2020 had gaps of 6–28 trading days off the list
    during one continuous advance. A 3-day tolerance shattered that into six rows.
  - *Tradeoff accepted:* a 25-day window may occasionally merge two genuinely unrelated runs on the same ticker.
- Streaks lasting only **one day** are dropped entirely, treated as rank noise rather than sustained
  relative strength.

---

## 4. Output file schema

**File:** `htf_1m_flag_review_v2_flagpole_bucketed_v2.csv`
**Grain:** one row per (ticker, streak).

| Column | Meaning |
|---|---|
| `ticker` | Ticker as it appeared in P123's historical universe. May carry point-in-time suffixes like `^13` or `.1^18` for delisted/renamed securities. |
| `revised_ticker` | Cleaned/current ticker symbol, resolved for chart lookup. |
| `first_qualifying_date` | **The earliest date the scanner would have surfaced this stock for this streak.** This is the "you could have seen it on this day" date — *not* the date of the price peak. This is the natural unique key alongside ticker. |
| `last_qualifying_date` | Last date of the streak's scanner presence. |
| `mktcap_bucket` | `small` / `mid` / `large_plus`, taken as of `first_qualifying_date`. ⚠️ See §7 — for ~7% of rows the stock crossed a bucket boundary mid-streak and this label reflects only day one. |
| `bucket_population` | How many stocks cleared Stage 1 in that bucket on `first_qualifying_date` (i.e. the size of the pool it was ranked against). |
| `rank_on_first_qualifying_date` | Its rank within that bucket on that specific day (1 = strongest 1-month return). Always ≤ 16 by construction. |
| `best_rank_in_bucket` | Best (lowest) rank achieved at any point during the streak. |
| `worst_rank_in_bucket` | Worst (highest) rank during the streak. |
| `num_hh_flagpoles` | Count of confirmed flagpoles in this streak. |
| `hh_dates` | Semicolon-separated dates of each confirmed higher high — **the actual price peaks**. |
| `hh_confirmed_dates` | When the pivot algorithm could *know* each HH was a peak (= `hh_date` + 2 trading days). |
| `suggested_resistances` | The HH price for each flagpole — the breakout levels to watch. |
| `latest_suggested_resistance` | The most recent flagpole's price, i.e. the currently-relevant level. |
| `is_valid_flag` | **Blank — this is the human's job.** Y/N: was this a genuine HTF setup on the chart? |
| `resistance_override` | **Blank — human input.** Used when the human disagrees with the algorithmic resistance level. |
| `status` | `OK` = usable row. `no_pivot_yet` = stock was on the scanner but never formed a confirmed flagpole. `no_daily_bars` = Polygon had no price history (usually long-delisted). `exception: ...` = data error, negligible count. |
| `streak_still_active` | Whether the streak was ongoing as of the build date (only populated on non-`OK` rows). |

### Current dataset stats
- **10,179** `OK` rows — 5,054 `small`, 3,639 `mid`, 1,486 `large_plus`
- 3,214 `no_pivot_yet`, 841 `no_daily_bars`, 6 exceptions
- **14,240** rows total, **4,187** unique tickers, **25,942** confirmed flagpoles
- Coverage: 2005-01-03 → 2026-09-11

---

## 5. How the human review works

The user filters to **one ticker at a time**, opens that ticker's chart (TradingView), navigates to each
date in `hh_dates`, and judges whether a legitimate high tight flag formed there. They then fill in
`is_valid_flag` with Y or N.

The file is deliberately sorted by `ticker`, then `first_qualifying_date` to support this workflow.

---

## 6. Glossary

- **ADR%** — Average Daily Range as a percent of price. A volatility measure; Qullamaggie screens for high ADR.
- **Flagpole** — the explosive advance preceding the consolidation. Here, operationalized as a confirmed HH pivot.
- **Flag** — the tight consolidation/pullback after the pole. Operationalized as an LH or HL following the HH.
- **HH / LH / HL / LL** — Higher High / Lower High / Higher Low / Lower Low; swing-pivot classifications.
- **Streak** — a continuous-ish run of days a stock appeared on the scanner (gaps up to 25 trading days tolerated).
- **Lookahead bias** — using information that would not have been available in real time. Strictly guarded against here.
- **EP (Episodic Pivot)** — a *different* Qullamaggie setup (gap-up on news after a downtrend). Separate project in this repo; don't conflate.

---

## 7. Known limitations and open questions

These are **acknowledged and accepted**, not bugs to be reported back:

1. **ADR understates volatility during fast run-ups.** The formula divides historical dollar ranges by
   today's (much higher) close. ARM read 4.34% against a 5% floor on 2026-04-24 despite an obvious
   high-volatility advance, and was excluded that day purely on this. Had it cleared, it would have
   ranked 9th of 499 in `large_plus`.
2. **The SMA-rising AND gate drops stocks during genuine consolidation.** Confirmed on real cases
   (DRYS Aug 2007, ACAD). Because only *one* qualifying day within 45 days before HH confirmation is
   needed — and the initial rally almost always supplies one — this rarely kills a flagpole outright.
   Its real cost is that the stock can vanish from a *live* scanner view precisely during the days the
   flag is forming. Switching to OR (either SMA rising) showed ~57% more qualifying days on ACAD. **Not
   implemented; AND is still in force.**
3. **Bucket label is stamped from day one of the streak.** ~1,031 of 14,242 streaks cross a market-cap
   boundary mid-streak (e.g. W crossing $10B in April 2020, AAOI mid→large_plus). For those rows, the
   `mktcap_bucket` label and the rank/population figures mix two different peer pools. Deliberately left
   as-is.
4. **Scope is 1-month return only.** 3-month and 6-month relative-strength variants are planned but not
   built — adding them requires a full re-pull of the P123 cache (~2,900 quota units), since the cached
   Parquet files have no `ret_3m`/`ret_6m` columns.
5. **No explicit "50% move in 14 days" or "pullback ≤15%" numeric test.** Earlier prototypes used hard
   thresholds like these. The current pipeline replaces them with the HH→LH/HL pivot structure, which
   captures the same shape without a brittle magic number. A future variant may add these as an extra
   screen layered on top.
6. **Survivorship considerations.** Delisted and renamed tickers are deliberately retained (hence
   `revised_ticker` and the `^NN` suffixes). Rows with `no_daily_bars` are genuinely unchartable, not
   filtered for convenience — dropping them wholesale would introduce survivorship bias.

---

## 8. Related context in the repo

- The pivot/zigzag logic is a direct port of the user's live TradingView Pine indicator, so the backtest
  and the live chart agree on what counts as a pivot.
- A separate, more mature project in the same repo backtests **Episodic Pivots (EP)**. It has its own
  findings document and conventions. Do not mix the two.
- Qullamaggie's trading principles are transcribed in a reference document in the repo; screening
  choices here are cross-checked against it rather than invented.

---

## 9. What good help looks like

When assisting with this dataset:
- **Verify against real data before asserting.** This project's working method is to check individual
  tickers and dates against actual price history before trusting any heuristic or threshold. Plausible
  reasoning that hasn't been checked has been wrong here repeatedly.
- **Respect the no-lookahead rule** in any analysis. Any statistic that uses information unavailable on
  the decision date is invalid for this purpose.
- **Don't propose re-tuning thresholds without evidence** from specific real cases. Every current value
  traces back to a concrete example (INDO, ABAT, ARM, DRYS, W, ACAD, AAOI).
- Recall matters more than precision. Suggestions that tighten the funnel need to justify what real
  setups they'd cost.
