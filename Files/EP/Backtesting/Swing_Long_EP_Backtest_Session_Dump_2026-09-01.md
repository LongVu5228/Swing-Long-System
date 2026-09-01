# EP Backtest — Session Data Dump (2026-09-01)

Exhaustive summary of one long working session on the Episodic Pivot (EP) swing-long backtest, written for handoff to another AI (ChatGPT) as context. Covers everything investigated, fixed, built, and decided — including dead ends and open questions. Prior context (V1 spec freeze, screening pipeline design, era/day0 conventions) lives in `Swing_Long_EP_Backtest_Master_Context_FROZEN_V1_2026-08-30.md` in the same folder; this doc picks up from there.

Codebase: `Files/EP/Backtesting/ep_backtest/` (Python package). Outputs: `Files/EP/Backtesting/outputs/`.

---

## 1. Starting point

Coming into this session, a coarse-to-fine screening pipeline (Stage0 → Screen1 → Screen2) had already narrowed a ~10,368-combo full grid (6 entry timeframes × 12 stop types × 6 trail types × 2 sell styles × 4 target ladders × 3 core-pct splits) down to **Screen2: 600 strategies** (25 base entry/stop/trail triples that survived Screen1's ranking × 24 sell/ladder/core combos each). An "18 Consistent Across Eras" shortlist existed (G_score > 5 in every era except 2022 and 2026+), built from Screen2 results.

Era buckets used throughout: `01|2012-2016, 02|2017-2019, 03|2020, 04|2021, 05|2022, 06|2023-2025, 07|2026+`. 2022 and 2026+ are excluded from "consistency" scoring — 2022 as a known-bad regime for the whole strategy class, 2026+ as a right-censored, still-incomplete year (`STILL_OPEN_AT_DATA_END` trades are dropped from stats, biasing recent periods against still-open winners).

**G_score formula** (used everywhere): `0.5 * clip(EV_R/0.30*10, 0, 10) + 0.5 * clip(profit_factor/2.0*10, 0, 10)`.

---

## 2. Major bug #1: `20ma_touch` was silently discarding valid trades

### Discovery
User asked "which strategies are the consistent 18" and we drilled into individual strategies. Found that for any base strategy using the `20ma_touch` trail type, roughly **16% of triggered setups were being thrown out entirely** as `INVALID_STOP_GEOMETRY`.

### Root cause
`trailing_stops.touch_level_series()` sets the trailing floor to *yesterday's raw 20-day MA value* (floored at the initial ADR stop). For EP setups (which gap up hard), the 20MA can still be sitting at or above the entry price on day 1 (hasn't caught down yet). `simulate_trade.py`'s guard (added earlier to prevent a real fabricated-fill bug, confirmed on CCL 2020-03-20) checks `entry_day_level >= entry_fill` and — instead of using a sane fallback — discarded the whole trade.

### Verification
Directly measured: for `30m/0.333333adr/20ma_touch`, 260 of 1650 trades (15.8%) were `INVALID_STOP_GEOMETRY`; for `60m/0.333333adr`, 237 of 1569 (15.1%).

### Fix
Built a new trail type: **`20ma_touch_adr_fallback`** (`trailing_stops.py: is_touch_with_fallback()`, `touch_level_series_with_fallback()`; new `level_series_for()` param `reference_price`). Mechanic: use the raw touch level normally; on any day (from entry onward) where that level is still ≥ the position's reference price, fall back to the ADR-based floor instead of invalidating; once the touch level first drops below reference price, "activate" permanently (sticky, via masked cummax — same pattern as the existing ratchet-type masking fix for pre-entry-history leakage). Threaded `reference_price` through all 4 call sites: `simulate_trade.py` (V1/V2), `partial_taking.py` Phase 1 & Phase 2, `multi_partial_taking.py` `_downside_scan` (the one actually used by all V3b/screen2 testing). Added `config.TRAIL_TYPE_20MA_TOUCH_ADR_FALLBACK`, `config.ADAPTIVE_TIGHTEN_ACTIVATION_PCT` — kept as an *additional* trail type, not merged into the frozen `TRAIL_TYPES` list, so no prior grid needed re-running for other trail types. New unit tests in `tests/test_v2_trailing_stops.py` (4 tests covering the fallback logic, sticky activation, pre-entry masking).

### Result — narrow test (4 combos: 30m/60m × equal/exponential, stop=0.333333adr, ladder=early_start, core=0.3)
Recovered trades: 30m +260, 60m +237, **0 rejections remaining**.
- 30m recovered trades were *good* (29.6% win, +0.18R avg) — fallback improved G-score slightly.
- 60m recovered trades were *near-breakeven* (26.6% win, -0.003R avg) — fallback **reduced** G-score meaningfully (best-of-18 combo dropped from G=6.36 → 5.81).

### Full-scale rerun
Ran fallback trail across all 8 (entry,stop) pairs that had used `20ma_touch` in Screen2's top-25 (192 combos: 8 pairs × 2 sell × 4 ladder × 3 core). Result vs strict `20ma_touch` (matched pairs, n=192):
- Mean G-score change: **-0.49** (fallback scores lower on average — i.e., strict `20ma_touch` was inflated)
- Only 37/192 (19%) improved
- 60m entries hurt far more (avg -0.77) than 30m (avg -0.20)
- `3pct_entry` stop was the *only* stop type that improved under fallback (some combos +0.28 to +0.36 G)
- **The prior all-time-best strategy in the whole 600-combo Screen2 search** (`60m/0.50ADR/20ma_touch/equal_depletion/start40/C30`, G=8.41) **dropped to G=7.49** under the fix — no longer even the best variant of its own base strategy.

### Consequence for "Consistent 18"
Rebuilt the trades dataset: `outputs/trades_v3b_screen2.parquet` (original) minus all `trail_type=='20ma_touch'` rows, plus the new 192-combo fallback rows → **`outputs/trades_v3b_screen2_corrected.parquet`** (the canonical corrected 600-strategy trades file used for everything from here on).

Re-ran "Consistent Across Eras" on the corrected data: **all 8 of the `20ma_touch`-based entries in the original 18 failed** — every one specifically at **era 04|2021** (worst-era G dropped from 5.98-7.36 down to 2.90-4.46), even though every *other* era stayed strong (G≈8.4-10). Mechanism: 2021 was full of extended/melt-up momentum names (SPAC/meme-stock era) that gap far above their own 20MA at entry — exactly what the bug was excluding. Recovering those trades revealed 2021 specifically was bad for that population.

**Result: Consistent-18 → Consistent-10**, all 10 survivors using `close_below_10ma` trail (no touch-type survived). Rebuilt workbook: `outputs/V4 Master Strategies (20MA Fallback Fix).xlsx`.

The 10 (pre-DT-filter, i.e. as understood at that point in the session):
```
E60M_S3PCT_ENTRY_close_below_10ma_equal_late_start_C30      G=7.19
E30M_S0.333333ADR_close_below_10ma_equal_start40_C30        G=7.00  <- "1st chosen one"
E30M_S0.333333ADR_close_below_10ma_equal_start20_C30        G=6.55  <- "2nd chosen one"
E30M_S0.333333ADR_close_below_10ma_equal_start20_C50        G=6.50
E30M_S0.333333ADR_close_below_10ma_equal_early_start_C30    G=5.76
E30M_S0.333333ADR_close_below_10ma_equal_early_start_C50    G=5.68
E30M_S0.333333ADR_close_below_10ma_equal_early_start_C70    G=5.60
E30M_S0.333333ADR_close_below_10ma_exp_early_start_C30      G=5.58
E30M_S0.333333ADR_close_below_10ma_exp_early_start_C50      G=5.55
E30M_S0.333333ADR_close_below_10ma_exp_early_start_C70      G=5.52
```

Why `close_below_10ma` dominated `low_of_close_below_10ma` (ratchet): (a) screen1 funnel effect — `close_below_10ma` had 4 (entry,stop) pairs advance to Screen2's top-25 vs only 1 for the ratchet type (not a fairness issue: every pair WAS tested with every trail type in Screen1's 324-combo pass, the ratchet type's pairs just scored lower); (b) genuine mechanical difference on the one shared base pair (60m/3%): `close_below_10ma` exits outright on the first bad-close day (locks in more frequent modest wins, win 20.8% vs 18.2%, higher PF), while the ratchet only tightens the floor on a bad-close day (gives trades a "second chance," bigger avg winner 5.96R vs 5.17R but lower win rate — nets out worse here).

---

## 3. Major bug/finding #2: chart_pattern `DT*` family is a massive drag

### Discovery
User was specifically suspicious of the `DT` (Downtrend) chart_pattern classification (an EP V5-provided taxonomy column, already carried into every trade row via `event_meta_from_row`). Checked full-history stats for `DT`-only trades on the chosen strategy: G=4.11 (below the 5.0 threshold), PF=1.09, EV_R=+0.083R (barely positive) — confirmed as weak.

### Escalation — checked ALL patterns, pooled across the 10 consistent strategies
Full pattern taxonomy present in the data: `DT, DT SW, DT U, UDS, UT, U, UTU, SW, CPH, DELISTED`. Pooled EV_R by pattern (summed across all 10 strategies, thousands of trades per bucket — not a small-sample artifact):

| Pattern | Pooled trades | EV_R | G |
|---|---|---|---|
| DELISTED | 99 | +1.92R | 10.00 (tiny sample, ~10/strategy — caveat, don't trust) |
| CPH | 389 | +1.92R | 10.00 |
| UDS | 2397 | +0.74R | 9.73 |
| UTU | 497 | +0.51R | 8.91 |
| U | 956 | +0.37R | 8.62 |
| UT | 1605 | +0.33R | 8.50 |
| SW | 418 | +0.32R | 8.44 |
| **DT** | 4561 | **+0.015R** | **2.79** |
| **DT SW** | 3959 | **-0.085R** | **2.25** |
| **DT U** | 1559 | **-0.509R** | **1.08** |

**All 3 `DT*` variants are weak-to-negative and it holds essentially identically across all 10 strategy variants** (i.e., a property of the setup itself, not any one exit rule).

### Impact of excluding `DT`, `DT SW`, `DT U` together
On the chosen strategy (`30m/0.333ADR/close_below_10ma/equal/start40/C30`): trades 1652→639 (61% of trade volume removed), but:
- EV_R: 0.232R → **0.712R** (3.1x)
- PF: 1.26 → 1.79
- Total R: 382.4 → **454.8** (higher, despite 61% fewer trades)
- G: 7.00 → 9.47

**All 10 "Consistent" strategies improved similarly** — G-scores that had ranged 5.52-7.19 all converged to a tight 9.3-9.5 band. Interpretation: most of what differentiated the original 10 from each other wasn't real exit-mechanic edge, it was just how much bad `DT*` exposure each happened to carry.

DT-family frequency by year (on the chosen strategy's population): overall 61.3% of all trades are DT-family. Notably concentrated in 2022 (88.6% of that year's trades were DT-family) — a big part of *why* 2022 was so bad generally. No clean fade-out over time (2024-25 dip to ~45-47%, 2026 back up to 54%).

**Streak/drawdown effect of the filter is real but partial, not a fix-all**: on the chosen strategy, longest losing streak 41→27, streaks-of-15+ 20→8, streaks-of-10+ 54→17. When checking exactly what remained of the original catastrophic March-May 2026 41-loss streak after filtering: 54 of 104 trades in that window survived the filter, and it was *still* mostly one long losing stretch (`U`/`UDS`/`UT`/`SW`/`CPH` patterns, not `DT*`) — i.e., the March-May 2026 blowup was a broad, cross-pattern failure, not something the DT filter would have caught.

### Full 600-strategy re-screen with DT-family excluded
No new backtest needed — re-aggregated existing trade-level data (`trades_v3b_screen2_corrected.parquet` already carries `chart_pattern` per trade). Took 53 seconds total.

**"Consistent Across Eras" (G>5 in every complete era) count: 10 → 155 of 600.**

New #1 (previously not even considered): `E60M__S0.25ADR__T20MA_TOUCH_ADR_FALLBACK__EQUAL_DEPLETION__LEARLY_START__C30`, min-era G=8.78 (old best overall was 7.36). Top ~12 rows all variants of `60m/0.25ADR/20ma_touch_adr_fallback`.

Saved outputs: `outputs/strategy_summary_v3b_screen2_dtexcluded.csv`, `outputs/era_breakdown_v3b_screen2_dtexcluded.csv`, `outputs/consistent_across_eras_dtexcluded.csv` (155 rows).

---

## 4. Re-ranking by *actual* consistency (not just era-threshold pass/fail)

User pushed back that "% negative years" / era-threshold pass-fail has real blind spots: blind to magnitude (a -0.01R year counts same as -1.0R), blind to intra-year streaks (a year could look "fine" while containing a brutal 20-30 trade losing stretch mid-year — exactly what was later found), calendar-year-boundary artifacts, and ignores per-year sample size.

### Concrete example that motivated this: `60m/0.25ADR/20ma_touch_adr_fallback/early_start/C30` (the new post-DT-filter #1)
Full-history: 610 trades, 18.7% win, PF=1.81, EV_R=0.720R, G=9.52. **4 of 5 complete eras hit the G-score cap of 10.00** (2021 the exception at 8.78). Looked spectacular.

But per-YEAR breakdown showed **August 4-14, 2026** alone: 24 trades, only 1 winner (4.2% win rate), **-23.0R** — this single 10-day cluster flipped all of 2026 from what would have been net-positive (+12.9R Jan-Jul) to net-negative (-10.1R total). All-time worst losing streak for this exact strategy was actually 30 losses spanning Sept 2021 - June 2022 (-32R) — i.e. it has an established pattern of occasional severe streaks, and 2026 landed another one very recently (weeks before "today," 2026-09-01).

### Built two better consistency metrics
1. **Year-level std-dev / worst-single-year EV_R** (script computed for all 155 consistent-post-DT candidates, min 8 trades/year, years 2015-2025 only). `consistency_score = min_year_EV_R - std_year_EV_R`.
2. **Real max drawdown + longest losing streak**, computed directly from the chronological trade sequence (peak-to-trough cumulative R) — the standard, most rigorous measure, catches exactly the August-2026-style cluster that year-bucket metrics can miss.

### Top-20 by proper consistency ranking (drawdown + streak), all DT-family excluded
`outputs/consistency_ranked.csv`, `outputs/drawdown_ranked_top20.csv`, `outputs/outlier_dependency_top20.csv`.

Key patterns across the top 20:
- `early_start` ladder dominates (18/20) — same finding as pre-DT-filter days, holds up again.
- Two win-rate "families": `60m/0.50ADR` (~31-32% win) vs `30m/0.333ADR` / `60m/0.333ADR` (~24-25% win).
- `20ma_touch_adr_fallback` variants have the **highest raw G-scores** (up to 9.86) but also the **worst drawdowns** (-37.4R to -40.6R, bottom of the whole top-20) and highest year-std — confirms the August-2026 cluster is a structural property, not a one-off.
- `close_below_10ma` variants have the worst "% negative years" (27-36%) of the group despite decent EV_R.
- `close_below_20ma` (both 30m/0.333ADR and 60m/0.50ADR variants) has the best balance: shallow drawdown, low negative-year frequency, decent-not-flashy EV_R.

### Outlier / tail-dependency test (top-10% contribution)
User's stated top priority late in session: "ones that aren't prone to outliers... I'd like to not rely on outliers." Ran two different cuts:
- **Remove the literal 10 single biggest winners**: all 20 candidates stay profitable (EV_R 0.18-0.35R remaining). Not fragile to a tiny handful of extreme trades.
- **Remove the entire top 10% of trades by size** (a much larger group, ~60-64 trades): **none** of the 20 stay profitable — every single candidate derives *more than 100%* of its total return from its best decile (165.6% to 207.2%), meaning the bottom 90% of trades are net-negative in aggregate on their own. This is a structural property of the whole strategy class (low win rate + skewed winners = momentum/breakout swing trading, matches Qullamaggie's own framework per user, who cross-referenced this against the Qullamaggie trading lessons in `KristjanDatabase/`), not fixable by exit-rule tuning.
- Ranked least-to-most outlier-reliant: `20ma_touch_adr_fallback` family is actually **least** reliant (165.6-175.2%) despite its bad drawdown; `close_below_20ma` next (178-207%); `close_below_10ma` most reliant (204-206%). I.e., drawdown-smoothness and outlier-independence are *different* risk dimensions — no single strategy in the top 20 wins on both.

---

## 5. Entry timeframe / stop-type / core_pct robustness sweep

Held trail=`close_below_20ma`, ladder=`early_start`, sell=`equal_depletion`, core=`C30` fixed, varied entry×stop:

| Entry | Stop | Win% | EV_R | Total R | Max Streak | Max DD | Outlier% |
|---|---|---|---|---|---|---|---|
| 30m | 0.333ADR | 23.9% | 0.675 | 431.2 | 21 | -35.8 | 195.4% |
| 30m | 0.50ADR | 31.8% | 0.549 | 349.4 | 17 | -37.7 | 180.4% |
| 30m | 3% entry | 29.4% | 0.533 | 339.0 | 22 | -34.6 | 190.8% |
| 60m | 0.333ADR | 24.8% | 0.596 | 363.0 | 21 | **-39.6 (worst)** | **207.2% (worst)** |
| **60m** | **0.50ADR** | **32.0%** | 0.546 | 330.6 | **15 (best)** | -34.5 | **178.9% (best)** |
| 60m | 3% entry | 29.4% | 0.507 | 307.4 | **14 (best)** | **-31.9 (best)** | 195.5% |

**Findings:** `0.333ADR` stop is the *least* robust choice by streak/drawdown/outlier-reliance despite having the highest raw total_R — the opposite of what its headline numbers suggested. `60m` entry is generally more robust than `30m` when paired with `0.50ADR` or `3%` stops (shorter streak, shallower drawdown); roughly a wash with `0.333ADR`.

### Core_pct dial (holding everything else fixed)
Tested C30/C50/C70 on both `early_start` and `start20` ladders (60m/0.50ADR/close_below_20ma base). **Streak length is IDENTICAL across all core_pct values within a given ladder** (15 for early_start, 21 for start20) — core_pct never affects win/loss streak risk, only drawdown depth and outlier-concentration (both worsen monotonically as core increases) and total return/G-score (both improve monotonically as core increases). For `early_start`, OOS test G actually *improved* going from C30→C50→C70 (9.45→9.55→9.64), arguing FOR higher core, not against — this updated the initial "always be conservative" instinct: since core doesn't touch streak, and OOS confirms the higher-core versions aren't more fragile, there's a legitimate case for not defaulting to C30 out of habit.

---

## 6. Out-of-sample (OOS) testing

### Pre-session (already existing, described for continuity)
Single train(<2023)/test(≥2023) split across all strategies in the OLD (pre-DT-fix) `trades_v3b_screen2.parquet`: Spearman rank correlation between train G-score and test G-score = **-0.114** (essentially no predictive power, slightly inverted). Separately, a rolling 4-split OOS test (naive best-pooled-G-score selection vs. "maximin"/consistency-based selection) found consistency-based picking beat naive picking in 3 of 4 splits, ~2.3x higher average test-period EV.

### Re-run on the corrected (DT-family-excluded) dataset, this session
`run_oos_test()` (module: `ep_backtest/oos_test.py`) re-run on the DT-filtered 600-strategy set, same 2023 split. Overall Spearman correlation: **0.007** (still ~zero across the full 600 — explained by a ceiling/compression effect: many strategies now cluster near G=9-10 post-filter, so correlation across the whole population is mostly measuring noise among near-tied top performers). **But the top-10 strategies by TRAIN G-score all held up almost perfectly OOS**: train G=10.0 (capped) for all 10, test G ranged **9.2-9.7** — a dramatically different, much more reassuring picture than the blanket correlation number alone suggests. This meaningfully updates the earlier "there wasn't a single strategy provably good for the future" conclusion — that finding predates the DT-family fix.

Saved: `outputs/oos_test_dtexcluded.csv`.

### Targeted OOS checks on the specific "chosen ones" (see §8)
Individual strategy_id lookups from the same `oos_test_dtexcluded.csv` — see per-strategy stats below.

---

## 7. Slippage sensitivity (real re-simulation, not an approximation)

`config.SLIPPAGE_PCT` baseline = **0.001 (0.1%)** per fill (note: this contradicts an earlier project-memory note claiming "1%" — the actual constant in `config.py` is 0.1%; not resolved/reconciled this session, flagging as a discrepancy worth checking). Slippage is applied via `_slip_add`/`_slip_sub` inside the simulation at every fill (entry + each partial sale + final exit — typically 6-7 fills per trade for a multi-target strategy), so cost compounds across a trade's lifecycle.

Because slippage affects fill prices *during* simulation, testing higher slippage required actual re-runs (not post-hoc adjustment of cached trades). Done via temporarily monkey-patching `config.SLIPPAGE_PCT` and re-running `run_v3b_grid` for a single base strategy at `workers=1` (single-threaded — required because `ProcessPoolExecutor` on Windows uses spawn, so worker processes re-import `config` fresh and wouldn't see a parent-process attribute mutation; not worth threading a new explicit parameter through the whole call chain for a one-off test). Each single-combo, single-threaded, full-2355-event run took ~2.5-3.6 minutes.

**Strategy #3 (`60m/0.50ADR/close_below_20ma/equal/early_start/C30`):**
| Slippage | EV_R | PF | Total R |
|---|---|---|---|
| 0.1% (baseline) | +0.546R | 1.78 | +330.6 |
| 0.3% (3x) | +0.360R | 1.47 | +218.0 |
| 1.0% (10x) | **-0.143R** | **0.86** | **-86.7** |

Breakeven ≈ **0.5-0.7%** per fill (interpolated).

**Strategy #4 (`60m/0.50ADR/close_below_20ma/equal/start20/C50`):**
| Slippage | EV_R | PF | Total R |
|---|---|---|---|
| 0.1% (baseline) | +0.618R | 1.79 | +373.8 |
| 0.3% (3x) | +0.421R | 1.50 | +254.6 |
| 1.0% (10x) | **-0.109R** | **0.90** | **-66.0** |

Breakeven ≈ **0.85-0.9%** per fill — slightly *more* slippage-resilient than #3.

Both remain solidly profitable at 3x current slippage assumption; both break down only if real-world execution runs meaningfully worse than ~0.5-0.9% per transaction — plausible on thinner names right after a volatile gap, not yet tested by liquidity tier (see open items).

---

## 8. Market regime filter — IWM (small-cap) 200-day MA

User's original hypothesis (SPY 200MA / broad market trend) tested first and found weak: correlating each YEAR's % of trading days SPY was above its own 200MA vs that year's strategy EV_R gave only r=0.27 (n=14 years, excluding partial 2026). Per-year inspection showed no clean pattern except the obvious 2022 outlier (a real broad bear market).

Switched to **IWM (Russell 2000 ETF)** as a small-cap-specific proxy (EP setups are small/mid-cap momentum names, could decouple from SPY's regime). Pulled full IWM history back to 2009 via `daily_bars.pull_ticker_daily_bars('IWM', ..., refresh=True)` (cache had only started at 2018 previously; needed the extra runway for a 200-day warmup covering 2012+). Correlation of yearly EV_R vs:
- IWM % days above own 200MA: **r=0.49** (best of everything tried)
- SPY % days above own 200MA: r=0.27
- IWM/SPY relative-strength (ratio above its own 50MA, rising): r=0.35 / r=0.48 depending on exact formulation — all worse than IWM's own absolute trend.

**Built an actual backtestable filter** (not just correlation): split every trade in the chosen strategy's population by whether IWM was above/below its own 200MA on the entry date (point-in-time, no lookahead — most recent IWM close ≤ event date).

| | IWM Above 200MA | IWM Below 200MA |
|---|---|---|
| Trades | 931 | 721 |
| PF | 1.37 | 1.11 |
| EV_R | 0.333R | 0.101R |
| G_score | 8.42 | 4.46 (fails threshold) |

Real, meaningful, backtestable signal — not pursued further as an actual applied filter this session (the DT-family finding took priority), but flagged as usable going forward.

---

## 9. Ideas explored but NOT built / inconclusive

### "2nd attempt" re-entry system
User's idea: take losers from the chosen strategy, build a fresh opening-range-breakout entry for those same tickers after the stop-out, see if it's independently profitable. Discussed methodology at length (defined properly, this is legitimate — a real-time-realizable rule, not lookahead — but risks compounding curve-fitting since it's a second search layer on top of an already-searched first system; needs its own independent OOS validation, higher bar than a standalone hypothesis).

**Evidence-gathering done** (not a real backtest, just an MFE-style check): for the 41-trade catastrophic March-May 2026 losing streak, checked what price did in the 5/10 trading days *after* the stop-out. 87.8% reached +5% from the exit price within 10 days, 58.5% reached +10%, mean 10-day move +22.5%. Repeated on **all 1382 losers** (full honest population, not cherry-picked): weaker but still real — 71.4% reached +5%, 52.7% reached +10%, mean +13.6%, median +10.6%. Confirms the effect is genuine (not just an artifact of one unusually-reversion-prone streak) but more modest than the streak-only check suggested.

**Not yet built:** an actual mechanical re-entry trigger (e.g., new high-of-day breakout within N days of stop-out), simulated with real slippage/sizing, independently OOS-tested. This remains open.

### "Reverse depletion" sell style (back-loaded, majority sold near +50%)
User's idea, discussed conceptually only — not built or tested. Analysis using the already-known MFE distribution (see below) showed the concept has a structural problem: only 2.8-4.4% of trades ever reach +40-50%, so a back-loaded sell schedule's "big final sale" would essentially never fire for 95%+ of trades — in practice it would behave almost identically to just running a much larger `core_pct` (e.g. C85-90%) with a token early trim, not "bank more profit as trades prove themselves further" as originally imagined. User accepted this framing; not built.

### MFE / target-ladder-extension question ("what if partials went to 70-90-100%?")
Checked directly using existing trade data (`max_favorable_R` converted to % gain via `(entry_fill - initial_stop_price)/entry_fill`) for the `start40/C30` population (1652 trades): only 2.8% of trades ever reach +50% MFE, 1.5% reach +70%, 0.5% reach +100%. Median MFE across all trades: 2.3%. **Conclusion: extending the target ladder past 50% would affect <1% of trades — not a game-changer.** The real leak identified instead: winners only capture ~29-50% of their own MFE on average (`avg_exit_efficiency_winners`), i.e. the exit mechanism gives back a lot of peak gain before firing — a different problem (exit tightness, not target placement).

### Adaptive-tighten trail (10MA → 5MA switch once up 30%+)
Built and tested as a response to the above MFE finding — hypothesis: instead of a distant fixed target, tighten the trailing stop once a trade proves itself, to capture more of a big winner's peak. Built as new trail type `close_below_adaptive_5_10` (`config.TRAIL_TYPE_CLOSE_BELOW_ADAPTIVE_5_10`, `config.ADAPTIVE_TIGHTEN_ACTIVATION_PCT=0.30`; `trailing_stops.build_adaptive_ma_column()`, wired only into `multi_partial_taking.py`'s `_downside_scan` — the V3b engine, not V1/V2/V3 single-target paths). Needed a new `sma5` column (`config.SMA5_WINDOW=5`, added to `exits.add_sma10()`). 3 new unit tests.

Tested head-to-head against plain `close_below_10ma` on 2 base strategies × 3 ladders (6 combos): exit efficiency on winners DID improve in all 3 comparable cases (+1.6 to +2.5pp), confirming the mechanism works as designed — but net effect on G-score/EV_R was a **wash** (one combo +0.12, one -0.11, one +0.03). The extra capture on winners was offset by getting whipsawed out earlier on trades that would've recovered under the wider 10MA. **Not adopted as a preferred trail type**, though it remains available in the codebase.

---

## 10. The four "chosen ones" — final candidates, in order of selection

All figures below use the DT-family-excluded (`DT`, `DT SW`, `DT U`) trade population, from `outputs/trades_v3b_screen2_corrected.parquet`.

### #1 — `E30M__S0.333333ADR__TCLOSE_BELOW_10MA__EQUAL_DEPLETION__LSTART40__C30`
30m entry, 0.333×ADR stop, close_below_10ma trail, equal_depletion sell, start40 ladder (40/42.5/45/47.5/50%), C30 core.
Trades 639, win 16.6%, avg winner 9.74R, avg loser -1.08R, RR 8.99, PF 1.79, EV_R 0.712R, total_R 454.8, G=9.469, exit-eff(winners) 50.4%.

### #2 — `E30M__S0.333333ADR__TCLOSE_BELOW_10MA__EQUAL_DEPLETION__LSTART20__C30`
Same base, start20 ladder (20/27.5/35/42.5/50%). Trades 639, win 18.9%, PF 1.78, EV_R 0.690R, total_R 440.8, G=9.461.

### #3 — `E60M__S0.50ADR__TCLOSE_BELOW_20MA__EQUAL_DEPLETION__LEARLY_START__C30`
60m entry, 0.50×ADR stop, close_below_20ma trail, equal_depletion, early_start ladder (10/20/30/40/50%), C30 core.
Trades 606, win 32.0%, avg winner 3.88R, avg loser -1.03R, RR 3.78, PF 1.78, EV_R 0.546R, total_R 330.6, G=9.46.
Max losing streak 15 (best in its peer group), max drawdown -34.5R, outlier-reliance (top 10%) 178.9%.
Era: 4/5 complete eras G>7.4; 2022 fails (G=1.68, EV_R -0.27R); 2026+ soft (G=3.47, EV_R +0.048R, but note the whole year is dominated by 2 events — March-May cross-pattern streak elsewhere and the August cluster is NOT this strategy's issue, this one stays barely positive in 2026).
OOS: train G=9.46 → test G=9.45 (essentially flat, no degradation). Overall rank 420/600 by full-history G among all Screen2 strategies (post-DT-filter).
Slippage breakeven ≈0.5-0.7%.
Sell schedule: 14% at each of +10/20/30/40/50%, remaining 30% rides `close_below_20ma` trail uncapped.
C50/C70 variants also fully profiled — same trades/streak, deeper drawdown and higher outlier-reliance as core increases, but total_R/EV_R/G also increase, and OOS *improves* with higher core (C50: 9.48→9.55; C70: 9.49→9.64) — i.e., higher core isn't more fragile here.

### #4 (final pick) — `E60M__S0.50ADR__TCLOSE_BELOW_20MA__EQUAL_DEPLETION__LSTART20__C50`
Same entry/stop/trail as #3, but start20 ladder + C50 core (chosen for an intuitive 50/50 core split after weighing #3's early_start/C30 vs a less-conservative start20/C70 option).
Trades 605, win 24.8%, avg winner 5.63R, avg loser -1.03R, RR 5.44, PF 1.79, EV_R 0.618R, total_R 373.8, G=9.486.
Max losing streak 21, max drawdown -33.8R, outlier-reliance (top 10%) 183.0%.
Rank 385/600 (full-history G, post-DT-filter).
OOS: train G=9.54 → test G=9.44.
Slippage breakeven ≈0.85-0.9% (marginally more resilient than #3).
Sell schedule: 10% at each of +20/27.5/35/42.5/50%, remaining 50% core rides trail uncapped.
Breakeven RR for 24.8% win rate = (1-0.248)/0.248 = 3.03; actual RR 5.44 → **1.80x above breakeven** (near-identical margin-of-safety to #3's 1.78x at 32% win / RR 3.78 — different packaging of essentially the same edge).

**Per-year tables for #3 and #4 both fully computed** (2012-2026, all columns: trades/win_rate/avg_winner/avg_loser/RR/PF/EV_R/total_R/hold_days/pct_real_move/exit_eff/G_score) — see chat log or re-derive via `year_breakdown.summarize_by_year()` on the filtered strategy_id subset if needed; not re-pasted here for length, but straightforward to regenerate.

---

## 11. Recurring findings / principles established this session

1. **`early_start` ladder (start profit-taking at just +10%) is the single most consistency-boosting lever found** — shows up dominant in nearly every "most robust" ranking, independent of trail type or stop.
2. **`DT*`-family chart patterns (`DT`, `DT SW`, `DT U`) are structurally weak-to-negative and represent the majority (61%) of trade volume** — the single highest-leverage filter discovered all session.
3. **Core_pct (C30/50/70) trades drawdown-depth and outlier-concentration against total return, but does NOT affect losing-streak length at all** — a cleanly separable dial from ladder/trail choices.
4. **`0.333ADR` stop is consistently the least robust of the stops tested** (longest streaks, deepest drawdowns) despite often having the highest raw total_R — a recurring "flashy but fragile" pattern.
5. **RR alone is meaningless without win rate** — what matters is RR relative to breakeven RR = (1-win)/win. Both major "chosen ones" families sit at ~1.78-1.80x breakeven despite very different win-rate/RR packaging (32%/3.78 vs 16.6%/8.99).
6. **Every strategy tested is fundamentally outlier-dependent** (>100% of total_R from top-decile trades) — inherent to momentum/breakout swing trading with a skewed payout distribution (cheap frequent losses, rare large wins), not fixable via exit-rule tuning; matches Qullamaggie's own trading philosophy per user's cross-reference.
7. **Bugs that inflate exactly the metric used for robustness screening are the most dangerous kind** — both major fixes this session (`20ma_touch` exclusion, `DT*` contamination) were specifically corrupting the era-consistency test that was supposed to catch bad strategies, not just adding random noise.
8. **A single-split OOS correlation across a huge, already-well-screened population can look near-zero even when the actual top candidates hold up great** — ceiling/compression effects among near-tied top performers can mask a real, useful signal; always check the top-N specifically, not just the blanket correlation.

---

## 12. Explicitly open / not done

- **Full walk-forward re-optimization**: re-run the entire Stage0→Screen1→Screen2 search restricted to train-only data at each point in time, to test whether these strategies would have actually been *discovered* using only past information (not just re-scored). Deferred every time it's come up — most rigorous OOS test possible, also the most expensive (same order of magnitude as the original ~3.5hr Screen1+Screen2 run).
- **Parameter-neighborhood test**: nudge stop/ADR/ladder values slightly, check if performance degrades smoothly or falls off a cliff (smoothness = more trustworthy, cliff = likely overfit combo). Flagged since early in the broader project, never run.
- **Liquidity-tier breakdown of the slippage sensitivity**: split by `adr_category`/`trading_turnover_pct_category` (already columns in the trade data) to see if the slippage danger zone is concentrated in the thinnest-liquidity names (filterable) or spread evenly (unavoidable).
- **Concurrency / capital-capacity check**: how many trades would be open simultaneously at any point — the backtest implicitly assumes unlimited concurrent capital; a real account capped at, say, 10 positions would experience clustered bad stretches (like Aug 2026) much more sharply.
- **Statistical significance / bootstrap CI on EV_R**: never formally quantified whether the edge could plausibly be zero given trade count and R-variance.
- **Re-entry / "2nd attempt" mechanical system**: evidence-gathering done (see §9), actual system never built or tested.
- **IWM-200MA regime filter**: built and validated as usable (§8) but never actually applied/layered onto the final chosen strategy's numbers.
- **Slippage baseline discrepancy**: project memory says "slippage = 1% of ref price" but the actual `config.SLIPPAGE_PCT` constant is 0.1%. Not reconciled this session — worth checking which is correct/intended.
- **Final decision**: user has NOT yet committed to a single final strategy among the 4 "chosen ones" — session ended with #4 as the most recent pick and this summary doc requested, not an explicit final choice.

---

## 13. Key file/output reference

- `ep_backtest/config.py` — all frozen constants, plus this session's additions (`TRAIL_TYPE_20MA_TOUCH_ADR_FALLBACK`, `TRAIL_TYPE_CLOSE_BELOW_ADAPTIVE_5_10`, `ADAPTIVE_TIGHTEN_ACTIVATION_PCT`, `SMA5_WINDOW`, `V3_MULTI_TARGET_LADDERS_EXTENDED_TO_100` (built, unused)).
- `ep_backtest/trailing_stops.py` — `touch_level_series_with_fallback()`, `build_adaptive_ma_column()`, `is_touch_with_fallback()`, `is_adaptive_close_based()`.
- `ep_backtest/exits.py` — now also computes `sma5`.
- `ep_backtest/multi_partial_taking.py` — `_downside_scan()` now takes `original_entry_fill` and dispatches to the new fallback/adaptive trail types.
- `ep_backtest/tests/test_v2_trailing_stops.py` — 7 new unit tests this session (all passing; full suite 42/42).
- `outputs/trades_v3b_screen2_corrected.parquet` — **the canonical corrected 600-strategy trade-level dataset** (20ma_touch bug fixed). All DT-family filtering is applied on top of this at query time (`chart_pattern` column), not baked into a separate file.
- `outputs/strategy_summary_v3b_screen2_dtexcluded.csv`, `era_breakdown_v3b_screen2_dtexcluded.csv`, `consistent_across_eras_dtexcluded.csv` — full 600-strategy re-screen, DT-family excluded (155 consistent).
- `outputs/consistency_ranked.csv`, `drawdown_ranked_top20.csv`, `outlier_dependency_top20.csv` — top-20 robustness rankings.
- `outputs/oos_test_dtexcluded.csv` — re-run OOS split on corrected data.
- `outputs/V4 Master Strategies (20MA Fallback Fix).xlsx` — rebuilt master workbook reflecting the corrected Consistent-10 (pre-DT-filter-discovery version; NOT yet rebuilt with the DT-family filter applied — that would be a natural next step if resuming this work).
- Various `outputs/trades_slippage_*.parquet` and `.log` files — one-off slippage sensitivity re-runs, single-threaded.

---

*End of dump. Written by Claude (Sonnet 5) for handoff to ChatGPT, 2026-09-01.*
