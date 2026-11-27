# HTF Backtest — Findings So Far (living doc)

> **Final locked strategy + stats: see `HTF_Strategy_FINAL.md` (one page).** The TL;DR below predates the 2026-11-23/24 re-runs (delisted flags, 30m entry, filters, -1.3R losses).

> **Session notes 2026-11-25 (held-out failure, live screener, P123 feed, decisions, next steps): `HTF_Session_Notes_2026-11-25.md`.**

Last updated 2026-11-21 (end of day). Covers the hand-annotation phase (rows 1–1,216 of 3,862 in TradingView + all 338 delisted dev rows in the local recorder), the minute-bar engine, Stage 1 (936-strategy grid, §17–18), Stage 2a/2b partials + order expiry (§19–20, §23), the validation gauntlet (§24), market cap / pattern (§25), the delisted survivorship result (§29), the local-recorder workflow (§30), the combined re-rank (§31) and the daily-bar data check fixes (§32). **Where we are: §33 (start here next session). §10–11 and §23–25 are survivor-only -- superseded by §29/§31 where they conflict.**
Results are in R (risk units) unless noted. **Read §11 (caveats) before trusting any number.**

---

## 0. TL;DR

1. **The edge lives in the monster winners.** About 3% of trades reach +10R, and those 65 trades produced about 80% of net R. Remove the top 5% of trades and every pattern, year and regime is about breakeven.
2. **Baseline system** (0.75×ADR stop, daily bars, ladder plus a 20-day SMA core exit): **about +0.54R per trade** on about 2,100 trades.
3. **Pattern matters a little; regime matters a lot.**
   - Green HTF and Perfect HTF are the steadiest patterns. Big Red Flag is the weakest and the most common.
   - The best windows come right after **SPY reclaims its 200-day line after a 10%+ correction**: +1.1 to +1.3R per trade for 2–3 months, with 10R+ winners about twice as common.
4. **Monster winners are about equally likely in every pattern** (2–5% each, not significantly different). Timing matters more than shape.
5. **Main blowup risk: earnings gaps.**
   - 6.6% of trades gap through the stop. 1 in 100 of those gaps costs −5R or worse.
   - Proposed rule: no entry with earnings in the next 10 trading days. Not yet backtested.
6. **Biggest open question: hindsight.** These flags were marked knowing what happened next. A Bar Replay test (re-marking flags without seeing the future) and small live trading are the real tests.
7. **Minute-bar strategy grid (Stage 1, §17):** opening-range entries (1–60m) and the R1 buy-stop are a flat plateau and beat daily-close entries by ~0.15R; 20-day-line exits beat 10-day; the stop is the big lever. Leading candidate: **5m (or 15m) opening-range entry, 0.75–1.0 ADR stop, exit on a 20-day-line touch** — about +0.43 to +0.49R per trade, ~−33 to −41R max drawdown. The 0.5 ADR stop earns slightly more (+0.53R) but is negative without its monsters and doubles drawdown. The 5m opening range filters false breaks (skipped flags lost −100R under the R1 buy-stop, §17 follow-ups).
8. **Partials (Stage 2a, §20) are a second-order lever:** selling early (+10–15%, every 3 days) clearly costs 0.04–0.07R; selling later (first sale +30–40%, spacing to +100%) adds about +0.02R (borderline) at ~3–4R more drawdown. Sell size, core %, breakeven: no effect.
9. **Without monsters, only green-side flags hold up** (Big Green, Green HTF, Perfect HTF), and only with stops ≥0.75–1.0 ADR (§18 follow-up). Red flags and Big Perfect are negative ex-top-5% at every stop.
10. **Order expiry + gauntlet (2026-11-17, §23–24):** keep the buy order live **15 trading days** after confirmation, then cancel (beats the hand-drawn box: +0.51R). The finalist **5m OR / 0.75 ADR / 20ma_touch / e15** passes everything run so far: parameter plateau, walk-forward (every later period positive), White RC + Hansen SPA over 1,656 variants (p ≤ 0.005, t 7.35 vs bar 3.63), block-bootstrap CI +0.37..+0.65R, slippage break-even ~0.9%/fill. Max DD −40R, 2 losing years (2008, 2011). Partials: first sale +30% / 7.5% spacing adds +0.02R (optional).
11. **Market cap is the strongest filter candidate (§25):** <$2B +0.72R vs $2B+ +0.32R in every era; trade-order DD −40R → −23.5R but −35% total R and half the 10R+. The small-cap edge is the same across patterns (interaction p = 0.94).

12. **SURVIVORSHIP (§29, 2026-11-21): the 338 delisted dev rows (1,287 flags, 1,055 trades) earn only +0.20R vs
    +0.51R on the TradingView survivors** (diff +0.31R, ticker-clustered 95% CI +0.06..+0.57, p ~0.007). Combined dev
    sample: **+0.41R on 3,219 trades**. The <$2B edge does NOT replicate in delisted names (+0.18 vs +0.22R). Every
    number above §29 is survivor-only and optimistic.
13. **The finalist changes (§31):** re-ranked on survivors + delisted, the old 5m / 0.75 ADR pick is rank 318 of 936
    (DD -74R). Tight ADR stops lose most; 15-30m entries beat 5m on drawdown. Candidates: 30m / 4% (EV +0.38, DD -45),
    15m / 1.0 ADR (+0.37, -49), 30m / 1.5 ADR (+0.31, -39), 15m / last_higher_low / adaptive 5-10 trail (+0.18, -19,
    best Calmar 28). Not yet through expiry / partials / gauntlet -- user picks the trade-off first.
14. **From row 1,217 on, charting is in the local recorder** (§30), ~2x faster than TradingView (87 vs 36-52 flags/hr).
---

## 1. Dataset and workflow

| Item | Value |
|---|---|
| Ticker list | `Files/HTF/htf_scanner_master_by_ticker.csv` = Google Sheet "Raw HTFs" tab (3,862 rows) |
| Progress | row 1,051 (DKNG), 27%; 488 tickers, 2,624 flags recorded |
| Patterns hand-labeled | all flags AA→CVI (2,191) via the sheet, Nov 6–9; flags from CVM on are labeled in the recorder (Auto + overrides) |
| Dropped as "not a flag" | 80 (`htf_dropped_flags.csv`) |
| Excluded tickers (charted on the wrong listing) | AGN, ARCH, ARNA, BKS, CUB, **CNR** (TSX Canadian National, not NYSE Core Natural Resources). Always check an export's exchange prefix; German, OTC and CFD listings of the *same* company are fine (CIS, CIT, CSH, ATAI, DIDIY) |
| Time invested | about 57 h of charting (30 active days, Sep 25 – Nov 11, about 2 h/day, about 5 min/chart) + about 15–25 h of sheet labeling = **about 70–80 h** |
| Pace | about 18 list rows/h, about 46 flags/h. About 150 h left at this pace (finish about Jan–Feb 2027) |

**Tools (all in `Files/HTF/Advanced Backtesting/`)**
- **`generate_recorder.py`** builds the 7-, 20- and 40-slot TradingView recorders. Schema 5 adds a Pattern dropdown that defaults to **Auto**: a Pine port of the labeler picks the pattern and shows "(auto)" on the box, and choosing a pattern overrides it.
- **`ingest_exports.py`** reads the newest export per ticker from Downloads and keeps a second recorder's flags. For Auto slots it re-runs the labeler and writes `pattern_recorded` + `pattern_source`.
- **`sync_sheet_reviews.py`** syncs the sheet into the truth file. Labels picked in the recorder always beat sheet rows for re-recorded tickers (ALTO, BIDU).
- **`htf_pattern_labeler.py`** is the auto-labeler. It matches your labels 69–72% of the time. A slope within 1e-9 of zero counts as flat, so a flat top reads as Perfect, the same as in the Pine port.
- **`generate_pattern_overlay.py`** builds the review overlays (6 alphabetical scripts).
- **`generate_scanner_days.py`** builds the scanner-day shading plus a 2×2 panel: first seen, last seen, streaks (and list row), next ticker. If two blocks show, the second is an older delisted company that used the same ticker; check it's the right chart.
- **`quick_backtest_chosen_one.py`** is the baseline daily backtest; `read_master()` applies the exclusions and drops.

---

## 2. Baseline system ("chosen one" on daily bars)

- **Entry:** the first session after the confirmed date whose high crosses R1 (the line of least resistance), filled at R1, or at the open if it gaps above. The window runs through the flag's end date.
- **Stop:** 0.75 × ADR14 below entry. The "mid" daily assumption counts the breakout day's low only on a gap.
- **Ladder:** sell 10% of the position at each of +20, +27.5, +35, +42.5 and +50%; stop to breakeven after the first sale; the 50% core exits on the first close below the 20-day SMA.
- **Costs:** 0.1% slippage per fill.
- **Result:** about 2,100 trades, **+0.54R per trade**, about 30% win rate.
- **Hold times:** median 3 days; 53% of trades are done within 3 days, mostly stop-outs.

**Earlier stop findings (memory: intraday stop finding):** with real 60-minute opening-range entries (on the 277 flags since late 2024), a **0.5 ADR stop gets shaken out on the breakout day** (+0.32R vs +0.77R on daily bars). At 0.75–1.0 ADR, intraday and daily results converge at about +0.42R. Daily-bar results are an upper bound.

**Stop variants tested on daily bars:**

| Stop | Avg R per trade | Avg return per trade | Note |
|---|---|---|---|
| **0.75×ADR** | +0.54R | **+2.08%** (best) | keep |
| 2% fixed | +0.85R | +1.70% | 82% stopped out; flattered by daily bars |
| 3% fixed | +0.67R | +2.00% | |
| Low of day, min 1% / 2% risk | +0.72 / +0.59R | | raw low of day produced a +394R artifact |

**Sell everything on a ≥10/15/20% gap-up:** +18 / +48 / +29R in total. That's noise: it helped 51 trades and hurt 38. Not adopted.

---

## 3. Patterns (your 6-pattern labels, about 2,050 trades)

| Pattern | Trades | Win % | Avg R per trade | 95% range | Total R | Without 10R+ trades | 5R+ rate | 10R+ rate |
|---|---|---|---|---|---|---|---|---|
| Big Green Flag | 326 | 33% | **+0.74** | +0.38 to +1.13 | +242 | +0.22 | 10.0% | 3.6% |
| Green HTF | 329 | 33% | +0.68 | +0.36 to +1.05 | +224 | +0.30 | **11.9%** | 2.9% |
| Perfect HTF | 243 | 34% | +0.67 | +0.28 to +1.10 | +163 | +0.30 | 11.5% | 2.9% |
| Red HTF | 288 | 28% | +0.59 | +0.20 to +0.98 | +169 | +0.01 | 9.2% | 4.1% |
| Big Perfect Flag | 161 | 29% | +0.50 | +0.01 to +1.07 | +81 | −0.15 | 6.7% | **4.3%** |
| Big Red Flag | 704 | 27% | **+0.37** | +0.14 to +0.60 | +261 | +0.04 | 8.4% | 2.5% |

- **Red setups win less often.** Red and Big Red win 27–28% of the time vs 33% for Green, a gap unlikely to be chance. Their R per trade is +0.28R lower, which is borderline (about a 5% chance it's luck).
- **HTF vs Flag:** +0.64R vs +0.49R per trade, not proven.
- **No pattern is better at producing monster winners.** The rates aren't significantly different, at either the 5R+ or 10R+ cutoff, and the ranking flips depending on the cutoff. Big Perfect Flag's early "1 big winner in 60 trades" was bad luck; at 161 trades it's normal.
- **Consistency across years** (counting only years with 8+ trades of that pattern):

| Pattern | Positive years | Worst year | Steadiness ratio* |
|---|---|---|---|
| **Green HTF** | 75% | −0.36 | **0.85** |
| **Perfect HTF** | **83%** | **−0.30** | 0.70 |
| Big Perfect Flag | 50% | −0.39 | 0.68 |
| Big Green Flag | 69% | −0.74 | 0.59 |
| Red HTF | 82% | −0.69 | 0.59 |
| Big Red Flag | 68% | **−0.97** | 0.54 |

*Average yearly R divided by how much it swings from year to year; higher is steadier.

- **Red HTF is two years.** 2016 (+64R) and 2025 (+61R) made about 74% of its total; in most other years, removing the single best trade turns the year negative.
- **Big Red Flag** is spread across good years (2009, 2010, 2017, 2019, 2023, 2024), but **2020–22 was flat**: 212 trades for +2R. In a market where everything runs, a stock still making lower lows is a laggard.
- **Sizing idea (untested):** size up Green and Perfect HTFs, size down Big Red and Big Perfect Flags.
- **Auto-labeler misses:** most are Green vs Perfect on near-flat tops, red HTFs you saw as Green or Perfect, the HTF/Flag boundary (40% of the pole given back), and Spiky or Expanding flags.

---

## 4. Monster winners and frequency

- **10R+ trades:** 65 of 2,051 (3.2%), about +893R in total, about 80% of net. 20R+: 4 trades (BBIO, AMD, COHR, CLSK).
- **Top 5% of trades (≥7.6R):** 109 trades made +1,286R, more than the system's net. Without them, average R per trade is −0.05R.
- **Projection for the full list (3,862 tickers):** about **8,500 trades and about 270 10R+ winners** (range 210–345), plus about 17 20R+ (range 5–42).
- **Per year (projected to the full list):**
  - **Setups:** about 200 a year before 2019; 500–1,000 a year since 2020.
  - **Big winners:** 0–36 a year. None at all in 2007, 2008, 2011, 2012 or 2015.
  - **Best years by 10R+ rate:** 2016 (10.5%), 2010, 2017, 2018.
- **Entries come in bursts:** 55% of days since 2020 have no new setup; the busiest day projects to about 50.
- **Open positions if you took every setup** (projected): 2018–19 about 10–13 (peak 24–36); 2020–21 about 31 (peak about 100); 2024–25 about 23–27; 2026 about 40. **You can't take them all, so a ranking rule is needed.**

---

## 5. Market regime

**SPY Chillax (10/20-day SMA trend), Green vs Down:**
- +0.67R vs +0.48R per trade; win rates are about equal, Green's winners are just bigger.
- Green beat Down in every era through 2021; Down did better in 2022–26.
- On the weekly chart, Chillax shows no signal.

**SPY vs its 200-day line:**
- **Above vs below:** +0.61R vs +0.20R per trade. Without the top 5% of trades, both sides are about breakeven (not significant).
- **SPY above a still-falling 200-day line** ("recovery"): **+1.83R per trade** over 109 trades, with a 10.8% 10R+ rate.

**SPY reclaiming its 200-day line** (9 events since 2005, each after 20+ sessions below):

| Window after the reclaim | Trades | Avg R per trade | 10R+ rate |
|---|---|---|---|
| 0–2 months | 181 | **+1.30** | 6.1% |
| 0–3 months | 254 | +1.14 | 5.1% |
| Rest of the time | | +0.46 | about 3% |

- The edge is unlikely to be chance from 2 months on. Without the 5 best trades it's still +0.81R per trade.
- **Failed signals:** 2008, 2011, 2015 and Jan 2023 lost money; Nov 2022 was flat.
- **Strongest signals** were the crosses that held 20+ days: Mar 2016 (+4.17R per trade) and May 2025 (+1.61R).
- **The 200-day line's slope didn't matter.** "Clearly falling" gave +1.33R per trade; "flat" gave +0.77R; May 2025's line was flat to rising. **Working rule: SPY back above its 200-day line after a 10%+ correction, slope ignored.**

**After corrections:**
- 0–12 months after a 20%+ bottom: +0.71R per trade (vs +0.47R otherwise).
- The first 3 months are the weakest (+0.39R): bottoms are choppy.
- Depth doesn't predict results. The year after Feb 2016's −14% was the best (+2.41R per trade, 11% 10R+); the year after Oct 2022's −25% was the weakest (+0.18R).
- **Monster winners cluster at market bottoms:** Mar 2009, Jan 2019, May 2020, Jul 2022, Oct–Nov 2023, May–Jun 2025.

**Pattern × regime (avg R per trade):**
- Every pattern does best in the recovery regime (about +2R for the HTFs and Big Green Flag).
- In a normal bull market (SPY above a rising 200-day line), Big Red Flag is the weakest at +0.27R.

---

## 6. Over time

**Contiguous periods (avg R per trade):**

| Period | Avg R |
|---|---|
| 2005–06 | +0.92 |
| 2007–08 | −0.17 |
| 2009–10 | +1.05 |
| 2011–12 | −0.79 |
| 2013–15 | +0.41 |
| 2016–17 | +1.63 |
| 2018–26 | +0.47 (stable) |

- **Removing each year's own top 5% of trades:** only 9 of 22 years stay positive. Only 2005, 2009, 2010, 2016 and 2017 are clearly positive.
- **Analyze by period groups and regimes, not single years.** Single years are too thin, even with the full list.

---

## 7. Scanner (top 16 per market-cap bucket)

- The scanner shows the top 16 stocks by 1M, 3M or 6M return in each market-cap bucket. "On the scanner" means being in that top 16.

**Entries made while the stock is on the scanner:**

| Pattern | Share of entries on the scanner |
|---|---|
| Perfect HTF | 65% |
| Green HTF | 60% |
| Red HTF | 50% |
| Big Green Flag | 37% |
| Big Perfect Flag | 36% |
| **Big Red Flag** | **15%** |

- **Flag start on the scanner:** 59% overall.
- **Days since the stock left the scanner** (for entries after it left): median 21–25 days for HTFs, 41–49 days for Big Flags.
- **44 of 65 10R+ winners came after the stock left the scanner** (32 of 37 among the Big Flags).
- This backs the two-scanner plan: a live screener for HTFs, and a daily review of stocks that left the scanner (kept for about 6 months) for Big Flags.
- **Rank within the top 16:**
  - Stocks that hit #1 in their streak averaged +0.64R per trade, vs about +0.45R for ranks 2–12; 13–16 is too small to judge.
  - The relationship is weak (rank correlation −0.08). 40% of trades come from stocks that hit #1.
  - **Ranks 17+ are not yet tested** (see §10).

---

## 8. Risk, sizing and earnings

- **Position value is about 25× the dollars risked** (stop distance median 4.1%; 10–90% range 2.7–6.9%).
- **Gaps through the stop:** 6.6% of trades. Median −1.25R; 1 in 20 of these gaps costs −2.8R or worse; 1 in 100, −5.2R or worse.
  - Worst cases: CDLX −7.1R, CIS −5.9R, CORZ −4.3R.
  - Extra cost beyond −1R: about −72R in total (about 6% of net).
- **DAKT flag 1 (Aug 2006)** was stopped by 3 cents the day before a −28% earnings gap. Holding it would have cost about −6R.
- **A stock going to zero** costs the whole position, about 26R.
- **Account:** $30k (maybe +$10k), 4× intraday buying power, but **2× overnight ($60k) is what counts for swing trades**.
- **Plan:**
  - **0.25% risk per trade for the first 50–100 live trades.** At $40k that's $100 a trade: positions about $2,500, about 30 positions fit at 2×, a −6R gap costs −1.5%, a stock going to zero costs −6%.
  - Step up to 0.5% if live results come in near +0.4 to +0.5R per trade.
  - **Cap a single position at about 20% of equity.** Use margin for **more** positions, not bigger ones.
  - Cap total open risk at about 15R. A market-wide gap hits everything at once: 30 positions × −2R = −15%.
- **Earnings rule (proposed, untested):**
  - No new entry if earnings are within the next **10 trading days**.
  - If you're in, earnings come up, and the first +20% sale hasn't happened, cut half or all before the report.
  - Once the stop is at breakeven, holding through earnings is fine.
  - Basis: losers are typically stopped out in 2 days (90% within 12); winners make the first +20% sale in a median 6 days (75% within 10, 90% within 16).

---

## 9. What's not done / known issues

- **Unlabeled:** ACHC 3 (the chart ends before the flag; re-export ACHC).
- **Old re-click items:** AAOI 14 (R1 mis-click), CURLF 6 (R1 breaks the same day it goes live), CRSR 4 and 5 (possible mis-clicks).
- **Two old auto-labels remain:** AA 12 (Spiky Top) and AUPH 4 (Expanding).
- **Shared tickers on the list:** check the second (delisted) company before recording (CZR 2013–15, CNR, and 61 such chart symbols in total).
- **The Pine recorder (schema 5)** compiles and works in TradingView; Auto matches the Python labeler on all 2,192 flags in the mirror test.

---

## 10. Test queue

1. **Strategy matrix (§12): in progress.** Stage 1 and 2a done (§17–20); remaining steps in §21.
2. **Earnings filter backtest:** pull historical earnings dates (P123 or Polygon); test the 10-day rule; check whether it costs monster winners.
3. **Does scanner rank matter outside the top 16?**
   - Rebuild daily ranks from `Files/HTF/raw_data_htf_v2/*.parquet`: every stock that passed the scanner's filters, about 6,800 a day, with 1M/3M/6M returns, ADR, volume, market cap and SMA slopes.
   - Compare follow-through for ranks 1–16, 17–32, 33–64 and 65+.
   - Read the parquet files with the repo `.venv` Python, not bare `python`.
4. **Bar Replay hindsight check:** re-mark 30–50 flags without seeing the future and compare with the hindsight-marked versions.
5. **Sizing by pattern and regime.**
6. **Exposure caps and position ranking** for the days with too many setups.
7. **Market regime filter (user to-do, 2026-11-12).** The red or flat years (2007, 2008, 2011, 2012, 2022, 2026) all came in bad or choppy markets, so a regime filter likely matters more than any pattern filter. Test on the final strategy, using the day-before close only:
   - SPY vs its 200-day line (above or below, rising or falling) · **0–3 months after SPY reclaims its 200-day line** following a 10%+ correction, slope ignored (+1.1 to +1.3R per trade so far) · **IWM above its 200-day line** (it tracked EP's results better than SPY) · SPY Chillax Green vs Down.
   - Ways to apply it: trade or don't trade · **size up or down by regime** (for example 0.5% risk in a reclaim window, 0.25% normally, fewer or smaller entries when SPY is below a falling 200-day line) · a cap on open positions by regime.
   - Judge by: monster capture kept, drawdown and red-year losses reduced, walk-forward stable. Only 4–9 regime events since 2005, so prefer simple rules and sizing changes over hard on/off switches.

---

## 11. Caveats (read these)

- **Hindsight.** Flags were marked knowing what happened next. Earlier benchmark: hand-picked +1.17R vs scanner-only +0.06R vs random-date noise −0.06R per trade. The edge is in the selection, which is exactly what hindsight can inflate.
- **Daily bars.** These can't order the stop vs targets within a day; intraday results came in lower at a 0.5 ADR stop (§2).
- **Sample sizes.** Per year, per pattern-year and per regime-pattern cells are mostly 5–50 trades; differences under about 0.3R are noise. Monster-winner counts per cell are single digits.
- **Coverage.** A–DK so far. Projections assume the rest of the alphabet looks the same.
- **Regime results** rest on a handful of events (4 corrections of 20%+, 9 SPY reclaims of the 200-day line).

---

## 12. Next phase: the HTF strategy matrix (plan)

The goal is to find the best entry × stop × exit combination, scored the way EP was, then confirm on data that wasn't used for tuning.

**Scoring.** EP's G-score was `0.5 × min(EV ÷ 0.30 × 10, 10) + 0.5 × min(PF ÷ 2.0 × 10, 10)`. **The caps need re-basing for HTF:** HTF's average R per trade already exceeds 0.30R, so most HTF strategies would max out the EV half and the score couldn't separate them. Also report, per strategy:
- 10R+ rate, and average R without the 10R+ trades
- worst year, and share of positive eras
- average return per trade in %, max drawdown, and exit efficiency

**Grid:**

| Dimension | Options | Data needed |
|---|---|---|
| **Entry (one dimension, 9 options)** | **Opening-range high (EP-style):** 1M, 5M, 10M, 15M, 30M, 60M. Each session from the day after the confirmed date through the flag's end date gets its own range. Trigger = the higher of R1 and the range high, + $0.01; fills only after the range closes, at the trigger or at the open on a gap above. **Daily:** R1 cross (buy-stop at R1; exact once minute data is in); buy at the close above R1; next-day open after a close above R1 | minute for the opening-range entries and an exact R1 cross; daily for the other two |
| Initial stop (13) | 2/3/4/5% fixed; 0.33/0.5/0.75/1.0/1.5×ADR; **10-day low** (lowest low of the 10 sessions before entry); last higher low (most recent swing low before entry); **entry-day low of day (LOD)**, with a minimum risk of 1%; trigger candle low. **No flag-low stop:** the box clicks are too inconsistent, so structure stops come from price only (2026-11-11) | daily for the close-above-R1 and next-day-open entries (the LOD is fully known then); for the R1-cross entry, only the minute data shows the LOD at the moment of entry. Daily bars alone produced a +394R artifact earlier (§2), hence the 1% minimum |
| Trailing/core exit (8) | close below 10-day SMA; close below 20-day SMA; touch 10-day SMA; touch 20-day SMA; 10-day SMA ratchet; 20-day SMA ratchet; **adaptive** (close below 10-day SMA until +30%, then a close below the 5-day SMA); **20-day SMA touch with ADR fallback** | daily |
| **Main grid** | 9 entries × 13 stops × 8 trails = **936 strategies**, with the reference partial setup fixed | |
| Partials: Stage 2, full EP spec (§47–55) | **Target type:** price ladder (a sale every X% from the original entry) · time-based (a sale at the close every 3/5/10 daily candles, none on the entry day) · single sale (+10/15/20/30/50%) · none. **Ladder start:** +10/20/30/40%. **Spacing:** 5/10/15%, or evenly spaced to +50% or extended to +100%. **Sell amount:** 2.5/5/10 points of the original position (equal) or 5/10/20% of what's left (exponential). **Style:** equal · exponential. **Core %:** 0–100 (practical 0/30/50/70/100). **Breakeven after the first sale:** yes/no. A gap through several targets sells them all at the real open. About 950 partial setups in total | daily |
| Staging | **1:** main grid (936) → **2a:** top 25, change one partial dimension at a time (about 750) → **2b:** top 5, every partial combination across the dimensions that mattered (about 4,750) → **3:** filters on the top 10. Re-check the trail after partials are added; EP warns the best trail can change | |
| Re-entry | none; re-buy a reclaim of R1 within 7 sessions | daily (better with minute) |
| Filters (applied to winners only) | pattern; SPY regime; on/off scanner; earnings window | daily |

**Order of work:**
1. **Phase A (now, daily bars, all flags):** entry (daily variants) × stop × exit × partials. Pick the top 25 by the re-based G-score, check them across eras, then sweep partials in full on those.
2. **Phase B (intraday):** minute opening-range entries and intraday stops.
   - **Free data covers only flags since Oct 2024** (about 300). Use them as a preview.
   - **Full test:** the user is buying the Massive (Polygon) plan at about $200 (2026-11-11). That tier's minute history should go back about 20 years, covering the whole 2005+ sample; verify the actual start date on day one.
   - **Have the downloader built and tested on the free tier before subscribing.** It should pull minute bars only for each flag's entry window (confirmed date to flag end, plus a few days) and cache them. Download everything in the first days of the subscription.
3. **Phase C:** filters (pattern, regime, earnings, rank) on the top strategies only, to avoid over-fitting.
4. **Robustness:** check performance era by era. Use the rows charted *after* the strategy is frozen as the held-out test set.

**Lessons from EP to reuse:**
- Sanity-check placeholder costs before believing that nothing works.
- Hand-check the biggest winners of each new engine.
- Watch for stop levels sitting above the entry price.
- Watch for stale moving averages after a crash.

---

## 13. Validation gauntlet (adapted from EP, 2026-11-12)

Sources: the EP spec (`Files/EP/Backtesting/Swing_Long_EP_Backtest_Master_Context_FROZEN_V1_2026-08-30.md` §37–38, 56, 60, 64–69, 81–89), the session notes (`Swing_Long_EP_Backtest_Session_Dump_2026-09-01.md` §4–8, 11–14) and the EBTA robustness test (`EBTA_Book_Robustness_Findings_2026-09-03.md`). The code to reuse is in `Files/EP/Backtesting/ep_backtest/`: `noise_benchmark.py`, `walkforward_fold.py`, `drawdown_aware_pick.py`, `oos_test.py`, `rolling_oos_test.py`, `trade_metrics.py`.

**1. Engine checks**
- Unit tests for entry timing, gaps, the same-bar stop-vs-entry rule, the LOD known at entry, and the trigger-candle low.
- Audit mode that narrates a single trade.
- Hand-check the biggest winners of every new engine.
- Status codes: NO_ENTRY, INVALID_STOP_GEOMETRY (stop at or above the entry, or a stale moving average above the price), STILL_OPEN.

**2. Grid read**
- Heatmaps (entry × stop) of EV, PF, G-score, RR, sample size and entry rate. Look for a broad region that works, not the single best cell.

**3. Robustness on each top candidate**
- **Era table, plus a consistency score** = worst year's avg R per trade minus the spread of yearly averages (years with 8+ trades).
- **Max drawdown and longest losing streak**, in trade order.
- **Tail dependence:** % of total R from the top 1 and top 5 trades and the top 1%, 5% and 10% of trades; re-run without the 10 biggest winners.
- **Parameter-neighborhood nudges:** a smooth change is encouraging; a cliff means the combination is overfit.
- **Slippage re-runs** at 0.1%, 0.3% and 1% per fill: find the break-even cost, and split by liquidity (ADR, turnover, market cap).

**4. Selection**
- Compare the top G-score pick with the Calmar pick (total R ÷ max drawdown) and the lowest-drawdown pick.
- EP's lesson: the G-score pick can hide drawdowns no one could sit through, and drawdown-aware picks landed on more stable recipes.

**5. Statistics**
- Moving-block bootstrap confidence intervals (block sizes of 1, 10, 25 and 50 trades; ordered by date, blocked by date).
- **White's Reality Check plus Hansen SPA (SPA_l, SPA_c, SPA_u) across the whole grid.** These are mandatory: about 936 + 5,000 combinations get tested, more than EP's 600.
- **Noise benchmark:** same tickers, random dates at least 15 sessions from any flag, same rules; block-bootstrap the real-minus-noise difference. The earlier HTF benchmark: hand-picked +1.17R, scanner-only +0.06R, random dates −0.06R per trade.

**6. Walk-forward**
- Re-run the whole search for 3 folds: train through 2015, 2019 and 2022, each tested on the years after.
- Expect the winning settings to drift. Trust the **concept** if every fold stays profitable, not the exact parameters.

**7. Real-world checks**
- Bar Replay hindsight test (30–50 flags).
- Held-out rows charted after the strategy is frozen.
- Live trading at 0.25% risk.
- A portfolio layer: max positions, one trade at a time per stock, cap on open risk, CAGR and portfolio drawdown.

**Also to test (from EP):**
- IWM above its 200-day line as a small-cap regime filter. For EP it tracked results better than SPY: correlation r = 0.49 between IWM's share of days above its 200-day line and yearly EV.
- A pre-earnings grid: ignore earnings, or sell 25/50/75/100% of the whole position, core included, the day before the report.
- Re-entry after a stop-out, treated as a separate system and validated as a pair with the main one.

**Problems specific to HTF**
- **Hindsight in marking flags:** only Bar Replay and live trading can test it.
- **Pattern labels are hindsight features.** Filter on the auto-labeler computed from bars up to entry, never on your labels (EP's rule: a filter must be known at entry).
- **Survivorship bias:** delisted scanner names often have no TradingView chart, so they're never charted. Measure the share of rows skipped for that reason, and check how those stocks ended up.
- **Overlapping flags on the same stock** can double-count a trade. Handle it with one trade at a time per stock in the portfolio layer, and with date-blocked bootstraps.
- **Split-adjustment consistency:** ADR and bars must come from the same price snapshot.
- **Daily-bar optimism** until the Massive minute data is in.

---

## 14. Does strength rank matter? Test 1 of the top-16 question (2026-11-12)

Script: `rank_strength_test.py` (repo `.venv` Python). Output: `rank_strength_results.csv`, 2.1M signal rows.
- **Data:** every US stock, every 5th trading day, 2005–2026. Forward returns measured from the next day's open, checked against TradingView prices.
- **Rank groups:** (A) a replica of the scanner (filters + best rank across 1M/3M/6M within the market-cap bucket); (B) every liquid stock by its 3-month-return percentile within the bucket.
- **"Fresh +100% month"** = a new 1-month gain of +100% or more that starts after the signal day, within about 6 months.

**B: Qullamaggie's broad claim holds.** The strongest stocks are far more likely to make another monster move.

| 3M-return percentile | top 1% | 1–2% | 2–5% | 5–10% | 10–25% | 25–50% | bottom 50% |
|---|---|---|---|---|---|---|---|
| Fresh +100% month | **6.1%** | 3.6% | 2.4% | 1.5% | 0.9% | 0.6% | 1.3% |
| Fresh +50% month | 26.6% | 18.4% | 12.9% | 9.0% | 6.1% | 4.5% | 8.1% |
| 6M ≤ −50% | 11.7% | 7.7% | 5.5% | 4.0% | 2.8% | 2.2% | 3.7% |
| Median 6M return | −2% | 0% | +2% | +3% | +4% | +4% | +4% |

- The pattern held in **every era**: the top 1% had 4–10× the monster rate of mid-ranked stocks.
- The **typical leader does worse than average.** Its median return is lower, and it's about 3–4× as likely to fall 50%. **The strongest stocks have fatter tails in both directions.** That's why the system needs tight stops plus letting winners run, not buy-and-hold.
- The bottom 50% has a slightly higher monster rate than the middle (beaten-down rebounds and squeezes), but no edge.

**A: inside the scanner, rank 16 is not a cliff.** Date-matched differences, other group minus top 16, with 95% ranges from bootstrapping dates:

| vs ranks 1–16 | 6M return | Fresh +100% month | Fresh +50% month | 6M ≥ +100% | 6M ≤ −50% |
|---|---|---|---|---|---|
| 17–32 | −0.3 pts (noise) | **−1.6 pts** (real) | **−5.0 pts** (real) | −0.8 pts | −1.3 pts (fewer blowups) |
| 33–64 | **+3.7 pts** | −1.0 pts (noise) | −3.1 pts | +0.9 pts (noise) | −1.4 pts |
| 65+ | +2.3 pts (noise) | **−4.1 pts** | −5.3 pts | −0.2 pts | −3.4 pts |

- The top 16 has modestly more fresh monster months than ranks 17–32: 7.4% vs 6.5% overall. On average returns, it's no better, or slightly worse.
- By era, ranks 17–64 matched or beat the top 16 on monster rate in 2005–08 and 2013–17. The top 16 led in 2018–26.
- **Read:** strength matters a lot between leaders and the rest of the market, about 6–8× monster rates. *Among* stocks that already pass the scanner's filters, rank adds only a small edge. **Widening the scanner to the top 32** would add about 22 stocks a day with only slightly lower monster odds, and would catch names like ABAT earlier.

**Caveats:**
- This measures a **stock's** follow-through from an ordinary day, not your flag setups or trading rules. That's Test 2's job (same detector across rank groups).
- Survivorship: 6-month outcomes are missing for 8–13% of the top groups (delisted or merged). Those could skew either way.
- Monster rates jump in 2018–26 for every group: more volatile small caps and better data.

---

## 15. Scanner workload, Qullamaggie's process, and your liquidity floor (2026-11-12)

**Your scanner's daily turnover** (`htf_universe_candidates_v2_bucketed.csv`, 2005–2026):

| | Median per day |
|---|---|
| Names on the list | 35 (77 on busy days) |
| New vs yesterday | 6 |
| Not seen at all in the prior month | **3–4** |

The real nightly workload is about 3–6 new charts. Widening to the top 32 would roughly double it to about 6–12.

**How Qullamaggie scans** (from `KristjanDatabase/data/analysis/lesson_batches/`):
- Ranks stocks by relative strength over 1, 3, 6, 9, 12 and 18 months, taking the **top 1–2%**, sometimes the top ~7%, with dollar-volume and ADR floors (batch_08, batch_10). That's hundreds of names, much wider than the top 16.
- Flips through charts in seconds and keeps only names setting up. Sets alerts at breakout levels. Keeps a "tracking watchlist" of past breakouts to train his eye (batch_02, batch_10).
- **Treat his "top 1–2%" as a rule of thumb.** Choose your own cutoff from a **catch-rate vs workload curve**: the share of future monster moves each cutoff catches, against new charts per day, odds per chart, and days of warning. It's built from `rank_strength_results.csv`. Not run yet.

**Live process implied:**
- A nightly pass of about 10–20 minutes, looking only at the new names.
- A watchlist with an alert at each name's R1 line.
- A daily filter on the 6-month list of stocks that left the scanner, surfacing only names near their line. That list is where 2/3 of the monster winners came from (§7).

**Dollar-volume floor for your account (now $35k):**
- His rule: 50–100 times account size = $1.75–3.5M a day, but with a **hard floor of about $5–10M a day for anyone** (batch_12). The floor governs.
- **Keep the scanner's $10M.** A typical position ($2.5–4.5k) is about 0.03–0.05% of a day's trading, so the floor protects against **spread and slippage**, not fills.
- If the catch-rate curve favors $5M, test those names with higher slippage. EP broke even at about 0.5–0.9% slippage per fill.
- ADR floor: his is about 2.2–2.4%; yours is 5% (stricter, fine for flags).

---

## 16. Game plan: finding the strategy (bookmark, 2026-11-13)

**Phase 0: Data**
1. Buy Massive; put the key in the repo-root `.env` (MASSIVE_API_KEY or POLYGON_API_KEY). From `Files/HTF`, run `../../.venv/Scripts/python.exe -m htf_backtest.minute_bars --probe` to confirm how far back the minute history goes.
2. Run `-m htf_backtest.minute_bars --workers 8`: about 2,000 merged windows (2,524 flags, 479 tickers, 2005-03 onward), each from the confirmed date to the flag's end + 10 sessions (~43k sessions in total), saved as parquet in `Files/HTF/backtest_data/minute_bars/`. Then `--extra SPY,IWM`, plus random dates for the noise benchmark.
3. Review the MISMATCH windows in `backtest_data/minute_manifest.csv` (minute data vs TradingView daily closes: reused tickers, splits, bad data). The free-tier test on 3 windows matched to within 0.03–0.2%.

**Phase 1: Engine**
4. One trade simulator: 9 entries × 13 stops × 8 trails + EP's full partial-sale options. Minute-level for the entry window and about 2 weeks after entry; daily bars after that.
5. Unit tests, audit mode, and a hand-check of the biggest winners before trusting any number.

**Phase 2: Find the strategy** (development sample = flags through row 1,051, DKNG)
6. Main grid of 936 strategies with the reference partial ladder. Heatmaps; look for broad regions that work, not single cells.
7. Rank by **monster capture rate** with guardrails: tolerable drawdown, roughly break-even without monsters, no losing era. Show the G-score and Calmar picks alongside.
8. Partials: change one dimension at a time on the top 25, then every combination on the top 5. Re-check the trail afterward.

**Phase 3: Prove it's real** (§13)
9. Robustness: era consistency, drawdown and losing streak, tail dependence, parameter nudges, slippage at 0.1/0.3/1%.
10. Statistics: block-bootstrap confidence intervals, White's Reality Check + Hansen SPA across the whole grid, noise benchmark.
11. Walk-forward with training through 2015, 2019 and 2022.

**Phase 4: Filters and sizing** (on the winner only)
12. Market regime: SPY/IWM vs the 200-day line, 0–3 months after a 200-day reclaim, Chillax. Applied through sizing, or trade/don't-trade.
13. Pattern (auto-labeler only), on vs off the scanner, rank (top 16 vs 32), earnings.
14. Portfolio layer: $35k, 0.25% risk, a 20% cap per position, a cap on open risk, one trade at a time per stock, CAGR and drawdown.

**Phase 5: Reality check**
15. Bar Replay hindsight test (30–50 flags) → held-out rows → live trading at 0.25% risk.

**Side tracks:** monster vs look-alike gallery; scanner catch-rate curve; top-16 Test 2.

## 17. Stage 1 grid results (2026-11-13, dev sample AA..DKNG, minute bars)

Run: 2,522 flags x 936 strategies (2h32m, 6 workers). 2,302 flags produced at least one trade.
Status: OK 1,848,428 / NO_ENTRY 397,488 / MISSING_MINUTE 66,456 / MINUTE_MISMATCH 39,312 /
INVALID_STOP 5,439 / STILL_OPEN 3,469. Files: backtest_outputs/trades_stage1.parquet,
strategy_summary_stage1.csv, strategy_summary_stage1_plus.csv (+ monster capture, neg years).
Monster flag set = 388 flags where ANY strategy made 10R+; mon_cap5 = share of them a strategy turned into 5R+.
Reference ladder (start20, 50% core) on every row -- partials not yet varied.

**By dimension (averaged over the others):**
- Entry: all 6 opening-range entries + r1_cross are a flat plateau (EV +0.32..+0.36R). Daily entries are clearly
  worse: close_above_r1 +0.20, next_open_after_close +0.17 (worse fill, wider effective stop, fewer 10R+).
  5m is marginally best; 60m has the lowest drawdown but ~15% fewer trades.
- Stop: tight volatility stops win on EV but live entirely off monsters. 0.5 ADR: EV +0.38, EV ex-10R -0.21,
  DD -78R. 0.75 ADR / 4%: EV +0.37, EV ex-10R +0.08, DD -47R. 1.0 ADR: +0.34 / +0.22 / -39R.
  Structure stops (low_10d, last_higher_low) have median ~12.7% stops: zero 10R+ trades, EV ~+0.2R, but tiny DD.
  0.33 ADR / 2% / trigger-candle low are too tight (DD -110..-175R). LOD stop is middling.
- Trail: 20-day-line exits beat 10-day exits across the board (+0.33..+0.35 vs +0.25..+0.29). 20ma_touch best.

**Key strategies (trail 20ma_touch):**
| strategy | trades | win | EV R | PF | EV ex-10R | 10R+ | monster cap | max DD R | lose streak | neg yrs | med stop |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 5m / 0.50 ADR | 2114 | 21% | 0.534 | 1.65 | -0.19 | 4.4% | 51% | -77 | 27 | 6 | 2.7% |
| 5m / 0.75 ADR | 2113 | 28% | 0.489 | 1.71 | +0.11 | 2.8% | 44% | -41 | 19 | 3 | 4.0% |
| 5m / 4% | 2110 | 28% | 0.490 | 1.70 | +0.10 | 2.9% | 44% | -41 | 19 | 3 | 4.0% |
| 5m / 1.0 ADR | 2109 | 33% | 0.425 | 1.72 | +0.27 | 1.3% | 34% | -33 | 19 | 3 | 5.4% |
| r1_cross / 0.75 ADR | 2232 | 28% | 0.472 | 1.68 | +0.10 | 2.8% | 46% | -42 | 25 | 3 | 4.0% |
| 5m / last_higher_low | 2106 | 39% | 0.224 | 1.77 | +0.22 | 0% | 4% | -13 | 16 | 3 | 12.7% |

**Read:** the 0.75 ADR / 4% stop with a 5-30m opening-range entry and 20-day trail is the robust middle:
~92% of the 0.5 ADR EV, half the drawdown, positive without monsters, 3 negative years vs 6. 0.5 ADR is the
"max monsters" corner (+7 pts monster capture) but its edge is entirely the right tail -- most fragile to
slippage and to the White RC / SPA multiple-testing penalty. Not yet validated: these are in-sample, best-of-936.
Next: Stage 2a partial sweep on the top ~25 (keep both the 0.5 and 0.75 ADR families), then the gauntlet.

## 18. Stage 1 by pattern and year (2026-11-14)

Reference = 0.75 ADR stop, 20ma_touch trail. Avg R per trade (5m / 60m entry): Perfect HTF 0.69 / 0.69,
Big Green 0.66 / 0.48, Green HTF 0.45 / 0.51, Red HTF 0.44 / 0.25, Big Red 0.42 / 0.34, Big Perfect 0.32 / 0.42.
- No pattern clearly prefers 60m; only Big Perfect (148 trades) and Green HTF lean that way. 60m beat 5m in total R in
  only 4 of 22 years (2018, 2019, 2026 roughly even) -- 60m mostly just skips trades.
- Stop preference differs by pattern (5m entry): Big Green Flag wants WIDER stops (4-5% / 1.0 ADR: +0.68..0.72);
  Perfect HTF and Big Perfect like TIGHT (0.33 ADR / 2%: +0.68..0.86, but EV ex-10R deeply negative).
- Per-pattern "best of 936" picks (EV 1.0-1.4R) are almost all 0.33 ADR / trigger-candle stops with ~150-250 trades
  and negative EV ex-10R = monster luck; do not adopt without Reality Check. Treat as hypotheses only.
- By year, every pattern has losing years; all-pattern losing years are 2007, 2008, 2011 (both entries). Per-pattern
  per-year cells hold 5-30 trades, so one monster flips them.
- 2 flags carry new labels "Expanding HTF" / "Spiky Top HTF" (1 each) -- check those recordings.

## 19. Stage 2a setup (2026-11-14, completed)

- Engine: htf_backtest/partials.py -- EP's multi-partial loop generalized (time-based sales at the close every N
  sessions, no partials, fixed sell size per rung, breakeven on/off), reusing EP's primitives. Reference config
  reproduces Stage 1 exactly (60-flag verify: 1,500/1,500 rows, max |dR| = 0). Breakeven arms only after a sale
  made in profit (time sales can sell below entry). 14 unit tests pass.
- Shortlist (25): 5m / 15m / r1_cross x stops 0.5 ADR, 0.75 ADR, 4%, 1.0 ADR, 5% x 20ma_touch, plus 5m x the same
  stops x close_below_20ma / close_below_10ma. Hand-built for coverage: a composite rank would have dropped the
  whole 0.5 ADR family.
- 27 partial variants (one dimension at a time): ref; time every 3/5/10 sessions; single sale +10/15/20/30/50%;
  none (core 100); ladder start 10/30/40; spacing 5/10/15/20 (20 = evenly to +100); 9 rungs to +100;
  fixed 2.5/5 pts; exponential 5/10/20% of remaining; core 0/30/70; no breakeven.
- Run: 2,522 flags x 25 x 27 = 1.70M strategy-trades -> trades_stage2a.parquet / strategy_summary_stage2a.csv.
- Still to build: order expiry test (5/10/15/20 sessions or none, ignoring the drawn box end).

## 20. Stage 2a results (2026-11-14)

1.70M strategy-trades (OK 1.44M). Averaged over the 25 shortlist strategies, the ref ladder = +0.445R/trade.
**Partials are a second-order lever: no variant moves EV more than +0.02R; early selling costs up to -0.09R.**

Paired bootstrap vs ref (same trades), 5m / 20ma_touch:
| variant | 0.5 ADR | 0.75 ADR | 1.0 ADR | read |
|---|---|---|---|---|
| start40 (first sale +40%) | +0.031 [-0.002,+0.070] | +0.024 [-0.001,+0.053] | +0.024 [+0.003,+0.048] | best, borderline significant |
| single sale +50% | +0.026 | +0.021 | +0.020 | ~same as start40 |
| spacing 20 (to +100%) | +0.018 | +0.013 | +0.016 [+0.002,+0.031] | small, consistent |
| none (hold 100%) | +0.025 | +0.009 | +0.018 | noisy, more DD |
| core 0 | -0.017 | -0.006 | -0.017 | neutral |
| single sale +15% | -0.062 | -0.058 | -0.045 | clearly worse (p<0.01) |
| start10 | -0.061 | -0.051 | -0.035 | clearly worse |
| time every 3 sessions | -0.071 | -0.070 | -0.052 | clearly worse |

- Pattern: sell LATER and LESS. Every "late / sparse" variant beat ref on 25 of 25 strategies (start30/40, spacing15/20,
  9 rungs to +100); every "early" one lost on all 25. Same across stop widths and trails.
- Cost of selling later: max drawdown about 3-4R worse, worst year slightly worse, win rate ~2 pts lower.
- Early selling buys smoothness: single +10/15% cuts DD by 6-10R and negative years from ~4 to ~2.5, at -0.05..-0.09R EV.
- Exponential / fixed-amount / core 30-70 / breakeven off: all within +/-0.01R of ref -- don't matter.
- Trail is unchanged by partials (20-day exits stay best; 10ma close gains least from later selling).
- Stop still dominates: 0.5 ADR rows top every EV list (+0.55..0.57R with start40) but EV ex-top-5% is -0.30..-0.38 and
  DD -80..-97R; best Calmar rows are 1.0 ADR with early single sales (+0.37..0.46R, DD -26..-32R, 2-3 negative years).

### Stage 1 follow-ups (2026-11-14, answered in chat)

- **Entry window / "expiration":** no fixed expiry. The buy order is live from the session after setup_confirmed to the
  flag's own drawn final_flag_end (median window 5 trading days, 90th pct 13, max 61; median entry 4 days after
  confirmation). Drawn box end = hindsight -> order-expiry test queued (§21).
- **Opening-range mechanics:** the 5 minutes only DEFINE the range; the buy-stop at max(OR high, R1) + 1c stays live
  all session after 9:35, then resets next day. No time-of-day cutoff modeled (3:55pm fills count).
- **Chasing above R1:** 78% of 5m fills are within 0.5% of R1. Fills 0.5-4%+ above R1 show no consistent win-rate edge
  (5m and 30m disagree); 4%+ above has the highest 10R+ rate in both (~4-5% vs 2.5%), small samples. The stop is
  measured from the fill, so R per trade is unchanged by chasing.
- **Entry not on the first R1-cross day:** only 1-6% of OR fills (5m: 45 trades). The OR entries SKIP flags whose cross
  never cleared the OR high: under the R1 buy-stop those skipped flags made 5m: 129 flags, -0.77R avg, 6% win, 0 monsters,
  -100R total; 60m: 474 flags, -0.40R, 5 monsters given up, -192R. The 5m OR is a false-breakout filter.
- **By pattern without the top 5% (5m / 20ma touch):** Big Green +0.07 / +0.18 / +0.24 at 0.75 / 1.0 / 1.5 ADR; Green HTF
  -0.12 / +0.05 / +0.14; Perfect HTF +0.12 / +0.07 / +0.08; Red HTF, Big Red, Big Perfect negative at every stop.
  At 0.5 ADR every pattern is negative ex-top-5%. -> test pattern-dependent stop width (auto-labeler patterns only).
- **Does more data help:** yes. 5m/0.75 ADR EV +0.49R has a 90% bootstrap range of +0.38..+0.60 (SE 0.07); the top
  strategies sit inside each other's noise and rest on 60-90 10R+ trades. Full list (~3x flags) shrinks the range ~42%.
  Master has 2,522 dev flags (AA..DKNG) and only 2 after (DKS) -- DKS..ZYXIQ is the held-out final exam and needs Massive
  minute data later.

## 21. Status and next steps (2026-11-14, end of day)

**Done:** Massive minute data (1,842 windows OK, 59 rescaled, ~95.5% of flags usable) · engine (htf_backtest, 14 tests) ·
Stage 1 (936 strategies, §17) · by-pattern / by-year cuts (§18) · Stage 2a partials (§20).
Outputs in `Files/HTF/backtest_outputs/` (trades_stage1.parquet, trades_stage2a.parquet, summaries). Not in git and
not backed up -- copy `backtest_data/` + `backtest_outputs/` to Drive/external.

**Next, in order:**
1. ~~**Stage 2b (small):**~~ DONE 2026-11-17, §23. ~5 strategies (5m/15m x 0.75/1.0 ADR, + 5m/0.5 ADR) x first sale +20/30/40% x spacing
   7.5/15/20% (~9 combos) -> under an hour. Only start and spacing mattered in 2a.
2. ~~**Order-expiry test:**~~ DONE 2026-11-17, §23 -> 15-session expiry. cancel the buy 5/10/15/20 sessions after confirmation (or never), ignoring the drawn box end.
   Needs entry.find_entry to take an expiry; minute coverage ends at final_flag_end + 10 sessions, so report how often
   an expiry runs past the cached data (pull extra minute windows if it matters).
3. **Validation gauntlet (§13):** White RC / Hansen SPA over all ~1,600 tried variants, walk-forward (train through
   2015/2019/2022), noise benchmark, slippage 0.1/0.3/1%, parameter nudges.
4. **Filters on the winner only (full list now §26):** regime (§10 item 7), pattern-dependent stop width (auto-labeler), scanner/rank,
   earnings 10-day rule, entry time-of-day cutoff, max % above R1.
5. Portfolio layer -> Bar Replay hindsight test -> held-out DKS..ZYXIQ -> live at 0.25% risk.

**Data issues to fix:** 2 flags labeled "Expanding HTF" / "Spiky Top HTF" (not one of the 6 patterns); ~113 flags
lost to MISSING/BAD minute data (retry the 55 EMPTY windows with the ticker resolver).

## 22. Blind flag re-grade (2026-11-15, in progress)

Hypothesis (user, discretionary, unverified): red flags with a "clean", tight, orderly downtrending
look work; messy ones are the drag. Red patterns currently fail EV-ex-top-5% at every stop but hold
many monsters, so a working filter would beat dropping red entirely.

Tool (`Advanced Backtesting/`): `generate_trainer.py` -> `htf_trainer.pine`, a TradingView overlay
that blacks out every bar after the chosen flag's setup_confirmed date ("Flag # on this ticker"
input, untick "Black out" to reveal), and `htf_trainer_queue.csv`: all 2,191 hand-labeled flags
(not only red, so the pattern answer is blind), random ticker order (seed 42), random A/B half.
User fills pattern (codes G/P/R/BG/BP/BR), r1_date (YYYYMMDD of the R1 bar), optional clean
(1/2/3), notes. `htf_trainer_key.csv` maps train_id -> flag_no (don't open while grading).
Re-running never overwrites the queue without `--force`.

Scoring: `score_trainer.py [--half A]` -> pattern agreement + confusion matrix, R1-date gap vs
r1_source_bar (trading days), and Stage 1 backtest R (5m / 0.75 ADR / 20ma_touch) by the blind
label vs the original label, red<->non-red flips, and by clean grade. Build any rule on half A,
check on B. Note the backtest R uses the ORIGINAL R1; if blind R1s differ a lot, re-run those.

## 23. Order-expiry test + Stage 2b (2026-11-17)

Run: `python -m htf_backtest.run_stage2 --stage expiry` / `--stage 2b` (5 finalists: 5m/15m x 0.75/1.0 ADR +
5m/0.5 ADR, all 20ma_touch). Outputs `trades_expiry.parquet`, `strategy_summary_expiry.csv`,
`trades_stage2b.parquet`, `strategy_summary_stage2b.csv`. Expiry "box" rows == Stage 1 (12,610 rows, 0 diffs).

**Expiry (buy order live N sessions after setup_confirmed, ignoring the hand-drawn box end).** DATA_SHORT
(order still live past cached minute data and the daily high crossed R1) = 83 of ~88k rows: negligible.
5m / 0.75 ADR / 20ma_touch:

| expiry | trades | win | EV | total R | mon_cap5 | max DD | neg yrs |
|---|---|---|---|---|---|---|---|
| 3 | 475 | 25% | +0.27 | 129 | 8% | -33 | 8 |
| 5 | 1,175 | 27% | +0.42 | 499 | 21% | -31 | 4 |
| 10 | 1,936 | 28% | +0.47 | 911 | 36% | -39 | 3 |
| **15** | **2,164** | 28% | **+0.51** | **1,104** | 43% | -40 | **2** |
| 20 | 2,239 | 28% | +0.50 | 1,117 | 44% | -42 | 2 |
| 30 | 2,288 | 28% | +0.49 | 1,131 | 44% | -42 | 2 |
| box (hindsight) | 2,113 | 28% | +0.49 | 1,033 | 44% | -41 | 3 |

Same shape on all 5 strategies. Short expiries kill the monsters (many break out 1-3 weeks after
confirmation); marginal trades days 10->15 averaged ~+0.84R, 15->20 ~+0.18R, 20->30 ~+0.28R.
**Rule: order live 15 sessions after confirmation, then cancel.** The hand-drawn box was not inflating results.

**Stage 2b (first sale +20/30/40% x spacing 7.5/15/20%, 5 rungs; box-end entries).** Later selling adds
+0.02-0.03R (paired bootstrap 90% CI excludes 0 on 5m/0.75 and 5m/1.0) but every gain comes from the tail:
win rate 28% -> 26%, EV ex 10R +0.11 -> -0.03, EV ex top 5% -0.09 -> -0.16, monster capture flat or lower,
drawdown unchanged. Spacing barely matters. Partials stay a second-order lever. Compromise pick:
**start +30%, spacing 7.5%** (+0.019R, CI +0.003..+0.036, highest monster capture 44.6% on 5m/0.75); keeping
the +20% ladder is equally defensible if robustness (ex-top-5%) is the priority.

**Next:** validation gauntlet (§13) on the finalists with the 15-session expiry baked in, then filters,
portfolio layer, held-out DKS..ZYXIQ.

## 24. Validation gauntlet results (2026-11-17)

Code: `htf_backtest/gauntlet.py` (`--only rc|wf|grid|final|slip`), finalist re-runs `run_stage2 --stage gauntlet`
with `HTF_SLIPPAGE=0.001/0.003/0.01` (5 finalists x ref + s30_sp7.5 ladders x 15-session expiry; slip 0.1% ref
rows == expiry e15 rows exactly). Reports `backtest_outputs/gauntlet_report_*.txt` + CSVs.

**Parameter neighbourhood: PASS.** Entry x stop heatmap (20ma_touch) is a plateau: the 6 OR entries + r1_cross
are within ~0.05R of each other at any stop; only stop width moves results (0.5 ADR +0.52 / ex-10R -0.19 /
DD -75; 0.75 ADR +0.47 / +0.10 / -41; 1.0 ADR +0.43 / +0.26 / -33). No cliff around the finalist.
Pick rules: max EV = G-score = 5m/0.5 ADR (DD -77, 6 neg years); Calmar / min-DD picks land on
last_higher_low / 1.5 ADR (mon_cap5 4-9%) -- they kill the monsters, so they don't fit the objective.

**Walk-forward (Stage 1 grid re-searched per fold): PASS.**

| train | test | % of 936 positive in test | max-EV pick test EV | 5m/0.75 ADR test EV (rank) |
|---|---|---|---|---|
| <=2015 | 2016-19 | 100% | +1.02 | +0.86 (247) |
| <=2019 | 2020-22 | 88% | +0.31 (DD -70) | +0.36 (8) |
| <=2022 | 2023-26 | 100% | +0.31 | +0.39 (80) |

Train/test rank correlation +0.72 / +0.41 / +0.60. Calmar and EV-ex-top5% pick rules did worse out of sample.
The automatic max-EV pick is always a 0.5 ADR stop -- choosing 0.75 ADR is a deliberate DD-for-EV trade.

**White's RC + Hansen SPA over all 1,656 variants tried (Stage 1 + 2a + 2b + expiry), moving-block
bootstrap by date-ordered flag: PASS.** p_RC 0.001-0.005, p_SPA_l/c/u 0.000 at blocks 1/10/25/50. Null 95% max-t
3.31-3.63; finalist t = 7.35 (e15), 7.00 (box). 99.9% of variants positive, ~85% clear the search-adjusted bar
-- the effect is broad, not one lucky cell. Tests "> 0", NOT "> long-bias": that is the noise benchmark's job.

**Finalists @ 15-session expiry, slip 0.1%:**

| strategy | ladder | n | EV | total | max DD | neg yrs | EV ex top 5% | top 5% share of R | 90% CI (block 50) |
|---|---|---|---|---|---|---|---|---|---|
| 5m/0.5 ADR | s30 | 2,165 | +0.57 | 1,239 | -80 | 5 | -0.29 | 148% | +0.38..+0.76 |
| **5m/0.75 ADR** | **s30** | 2,164 | **+0.53** | 1,151 | **-41** | **2** | -0.10 | 118% | +0.39..+0.69 |
| 5m/0.75 ADR | ref | 2,164 | +0.51 | 1,104 | -40 | 2 | -0.07 | 113% | +0.37..+0.65 |
| 15m/0.75 ADR | ref | 2,139 | +0.47 | 1,014 | -41 | 4 | -0.09 | 118% | +0.34..+0.62 |
| 5m/1.0 ADR | ref | 2,160 | +0.43 | 925 | -34 | 2 | -0.02 | 105% | +0.32..+0.54 |

Every finalist's CI excludes 0 at every block size. Tail dependence is total: the top 5% of trades make 105-148%
of all R (the rest is net negative); top single trade only ~2%, top 5 trades ~10% -- many monsters, no one
trade carries it. Era table 5m/0.75 ADR/e15 (EV): 2005 +0.66, 06 +1.73, 07 +0.12, **08 -0.32**, 09 +0.98,
10 +1.62, **11 -0.46**, 12 +0.44, 13 +0.47, 14 +0.72, 15 +0.52, 16 +1.21, 17 +0.91, 18 +0.45, 19 +0.88,
20 +0.60, 21 +0.29, 22 +0.04, 23 +0.39, 24 +0.60, 25 +0.67, 26 +0.12 (partial).

**Slippage per fill (entry, every partial, stop):**

| strategy | 0.1% | 0.3% | 1% | break-even |
|---|---|---|---|---|
| 5m/0.5 ADR | +0.55 | +0.34 | -0.33 | ~0.65% |
| 5m/0.75 ADR | +0.51 | +0.39 | -0.08 | ~0.9% |
| 5m/1.0 ADR | +0.43 | +0.34 | +0.07 | ~1.2% |

Tighter stops are more cost-sensitive (cost is a bigger fraction of R). At 1% the <$10 names hold up best
(+0.25/+0.54) and $10+ go negative; stop width <3% loses most. Realistic liquid-name cost (0.1-0.3%) leaves
+0.39..+0.51R.

**Still open:** minute-engine noise benchmark (random dates, same rules -- needs ~2,500 new minute windows;
daily version: hand-picked +1.17R vs noise -0.06R); then filters (§10/§21 item 4), portfolio layer, Bar Replay,
held-out DKS..ZYXIQ.

## 25. Market cap + pattern breakdown of the finalist (2026-11-17, step 4 preview)

5m / 0.75 ADR / 20ma_touch / e15 / ref ladder, 2,164 trades. Market cap = P123 `raw_data_htf_v2` value on/just
before setup_confirmed (known at entry; 99.6% matched). Script: `htf_backtest/breakdown_cap_pattern.py`.

| cap | n | win | EV | EV ex 10R | EV ex top 5% | 10R+ | max DD |
|---|---|---|---|---|---|---|---|
| <300M | 115 | 34% | +1.17 | +0.59 | +0.43 | 4 | -7 |
| 300M-1B | 475 | 32% | +0.73 | +0.33 | +0.13 | 13 | -23 |
| 1-2B | 423 | 29% | +0.58 | +0.10 | -0.03 | 16 | -24 |
| 2-10B | 812 | 26% | +0.27 | -0.03 | -0.25 | 19 | -58 |
| 10B+ | 331 | 26% | +0.51 | +0.08 | -0.09 | 11 | -19 |

<2B beats 2B+ in every era (EV 2005-14 +0.89 vs +0.39; 2015-19 +0.88 vs +0.63; 2020-26 +0.57 vs +0.27);
difference +0.39R, bootstrap 90% CI +0.14..+0.62. <2B is also the only group positive ex-top-5% in two eras.
The 2-10B bucket in 2020-26 (555 trades, +0.17) is the single biggest drag. Candidate filter for step 4 --
must still survive higher small-cap slippage and walk-forward.

By pattern (hindsight labels; live needs the auto-labeler): Perfect +0.72, Big Green +0.69, Big Red +0.49,
Red +0.47, Green +0.46, Big Perfect +0.35, unlabeled DE..DK +0.37. Pattern x cap cells are 10-200 trades --
too noisy to read individually (e.g. Red HTF swings -0.03 -> +1.13 between adjacent cap buckets).

**Pattern x cap interaction (`htf_backtest/breakdown_cap_x_pattern.py`): NONE detectable.** Small (<2B) minus
large (2B+) EV per pattern: Green +0.54 (90% CI +0.00..+1.10), Big Green +0.54 (-0.13..+1.22), Perfect +0.52
(-0.17..+1.25), Big Red +0.47 (+0.02..+0.92), Big Perfect +0.37 (-0.38..+1.12), Red HTF +0.03 (-0.61..+0.69).
Heterogeneity across the 6 (Cochran Q, permutation within cap group) p = 0.94; red vs non-red diff-in-diff
-0.18R (CI -0.69..+0.32). Same with winners capped at 10R (p = 0.95). Read: the small-cap edge is one effect
across all patterns (~+0.4..0.5R); Red HTF's flat number is indistinguishable from noise. Power is low --
per-cell SE of the difference ~0.35-0.45R, so only ~1R interactions are detectable; the full 3,862-row list
(~3.7x flags) would roughly halve the CIs.

## 26. Step 4 test list, consolidated (2026-11-17)

Every candidate is tested on the finalist (5m / 0.75 ADR / 20ma_touch / 15-session expiry), must use only
information known at entry (patterns = auto-labeler, never hand labels), and passes only if it holds in both
halves of the years + the 3 walk-forward folds without giving up many monsters. Sizing rules are judged on
return per unit of drawdown, not EV.

**A. Entry filters (original list, §21 item 4)**
1. Market regime: SPY / IWM vs 200d (rising/falling), 0-3 months after a SPY 200d reclaim (§10 item 7).
2. Earnings within 10 trading days -- Benzinga dates (`Files/EP/Data Pulls/Benzinga All Earnings Raw.xlsx`,
   dense 2015-mid 2026, report time included).
3. Scanner rank at entry (top 16 vs 17-32 vs 33-64; §14 said 16 is not a cliff).
4. Entry time-of-day cutoff (no cutoff modeled today; 3:55pm fills count).
5. Max % above R1 at fill (78% fill within 0.5%; 4%+ above had the most 10R+, small n).

**B. New candidates raised in chat / earlier sessions, not on the original list**
6. **Market cap** (§25): <2B +0.72R vs 2B+ +0.32R, every era; DD -40R -> -23.5R (about half of that cut is just
   fewer trades). Test as (a) skip >2B, (b) half size >2B, (c) <2B at ~1.7x risk for equal DD. Re-test with
   higher small-cap slippage. One rule for all patterns (interaction p = 0.94).
7. **Pattern-based sizing instead of skipping**: red patterns at half risk (they still hold ~half the monsters);
   Big Perfect Flag is the weakest (+0.35R, negative ex-top-5% at every stop) -- smaller size or drop.
8. **Pattern-dependent stop width** (already listed): 0.75 ADR for green/perfect vs 1.0+ ADR for red/big types.
9. **"Clean" red flags** -- blind re-grade (§22); feeds a measurable rule (channel fit, range contraction,
   biggest down day, volume dry-up) if the grades separate results.
10. **Flag shape features from the daily feature tests** (memory, 2026-10-30, daily proxy): price drift over the
    flag (uptrending flags +0.81R vs drifting down +0.42R; slope quintiles monotonic), higher-low vs lower-low
    setup, flag length (very short green flags +1.02R, n=50), depth of pullback, prior-run (pole) size.
11. **Distance from all-time high**: at/near ATH flags did WORSE (+0.21R vs +0.86R for >50% below ATH;
    not significant) -- test as a filter or sizing input.
12. **Entry price**: $5-10 names +1.22R (n=275) vs $10-20 +0.31R at 0.1% slippage; partly the cap effect.
13. **Minimum stop width**: stops <3% of price lose the most under higher slippage -- floor the stop % or skip.
14. **On-scanner vs off-scanner entries** (scanner "graduates" re-setting up, median 47 days after dropping
    off): +0.87R vs +1.17R on daily proxy -- check on minute engine; matters for the live watchlist design.

**C. Trade management (needs re-simulation)**
15. **Earnings hold rule** (risk-sizing memo): if earnings land before the first +20/30% sale, cut half/all the day
    before; hold through once at breakeven. Plus EP's pre-earnings grid (sell 0/25/50/75/100% incl. core).
16. **Re-entry after a stop-out**: re-buy if back over R1 within N sessions (+0.32 -> +0.63R per flag at 0.5 ADR on
    the 2024-26 hourly sample); validate as a pair with the main system.
17. Re-check the trail after the partial ladder change (s30 vs ref).

**D. Belongs to step 5 (portfolio layer), noted here so it isn't lost**
18. Max open risk cap (~15R at original stops) for market-wide gaps; 6.6% of trades gap through the stop
    (median -1.25R, worst -7.1R).
19. Max positions / ranking on busy days (2020-21: 250+ entries a year); one trade at a time per ticker.
20. Account-level drawdown (overlapping positions), not the trade-order drawdown used so far.

**E. Validation leftovers**
21. Minute-engine noise benchmark (random dates; needs ~2,500 new minute windows).
22. Survivorship: share of scanner names never charted because the delisted chart is missing.
23. 2011-13 (807-813 days under water in both cap versions) and 2022 -- check whether regime filters fix them.

## 27. Status + START HERE next session (2026-11-17, end of day)

**Done this session:** order-expiry test (15 sessions, §23) · Stage 2b partials (§23) · validation gauntlet
(`htf_backtest/gauntlet.py`, §24: all pass except the minute noise benchmark, not yet run) · market cap x pattern
breakdown + interaction test (§25) · drawdown with/without >$2B · consolidated step 4 list (§26) · blind trainer
simplified (§22: blacks out after confirmation; user fills pattern + R1 date + clean grade in
`Advanced Backtesting/htf_trainer_queue.csv`; score with `score_trainer.py`). Benzinga earnings dates located:
`Files/EP/Data Pulls/Benzinga All Earnings Raw.xlsx` (245k events, dense 2015-mid 2026; read-only, never write).

**Current finalist:** 5m opening-range entry, 0.75 ADR stop, 20ma_touch exit, buy order cancelled 15 sessions after
setup_confirmed, ref ladder (+20%, 7.5% spacing) or s30 (+30%). EV +0.51R, 2,164 trades, DD -40R.

**Next session, in order:**
1. Step 4 quick filters on existing trades (`backtest_outputs/trades_gauntlet_slip0.1.parquet`, strategy
   E5M__S0.75ADR__T20MA_TOUCH): market cap variants (skip / half size / 1.7x risk), entry price, min stop %,
   max % above R1, regime (needs SPY + IWM daily bars), scanner rank, earnings 10-day rule. Each judged on
   both year halves + the 3 walk-forward folds + monsters kept.
2. Things needing re-simulation: time-of-day cutoff, pattern-dependent stop width (auto-labeler patterns),
   earnings hold rule / pre-earnings sales, re-entry after stop-out, trail re-check. Add modes to
   `run_stage2.py` the way `--stage expiry/gauntlet` were added.
3. Optional: minute noise benchmark (needs ~2,500 new Massive minute windows; ask before pulling).
4. Then step 5: portfolio layer (§26 D), Bar Replay, held-out DKS..ZYXIQ, live at 0.25%.

**Run commands** (from `Files/HTF`, repo venv): `../../.venv/Scripts/python.exe -m htf_backtest.run_stage2 --stage
2a|2b|expiry|gauntlet [--limit N] [--workers 6]` (slippage via env `HTF_SLIPPAGE`); `-m htf_backtest.gauntlet
[--only rc|wf|grid|final|slip]`; tests `-m pytest -q htf_backtest/tests` (14 pass). `Files/HTF/` is not in git and
`backtest_data/` + `backtest_outputs/` are not backed up -- copy them to Drive/external.

## 28. Delisted rows: data pull + local recorder (2026-11-18)

**Survivorship gap:** 1,252 of 3,862 list rows (32%) are delisted P123 names ("TICKER^YY"); TradingView has no chart
for most, so they were skipped -- 338 of the 1,051 development rows. All results so far exclude them (buyouts AND
bankruptcies), direction of the bias unknown.

**Data (`htf_backtest/delisted_bars.py`):** daily bars 2003 -> end of the delisting year for every row
(`backtest_data/delisted_daily/`, 131 MB). Each row is checked against P123's own 1-month return on its scanner
days: 1,230 OK (median diff 1.6%), 21 SUSPECT (partial coverage / reused symbol), 1 EMPTY (FCE.A). Minute bars
for each scanner streak + 126 sessions after: **done 2026-11-18, 2,238/2,238 windows OK, 3.37 GB**
(`backtest_data/delisted_minute/`; 15 early test rows + ACORQ->ACOR re-pulled after a symbol bug). `simulate.minute_frame` falls back to that folder for "^" tickers.

**Local recorder (`Advanced Backtesting/local_recorder/`):** `server.py` (localhost:8765) + `recorder.html`
(lightweight-charts): candles, volume, SMA 10/20/50, 1M/3M/6M scanner shading, flagpole-high markers, ticker list
with reviewed / flag-count / data-status badges. Per flag: Start, R1 bar, Confirm, End clicks + pattern (Auto
default). Saves to `annotations_local.json` and writes `~/Downloads/DELISTED_<ticker>, 1D.csv` in the TradingView
recorder export format (schema 5) -> `ingest_exports.py` as usual (regex now accepts "^"). Round trip verified:
Auto -> labeler pattern, R1 = source bar high, manual Big Red with End = Confirm -> LL_NO_RECLAIM.
Recorder also shows the live Auto guess (server runs the same `label_flag` call as ingest: 201/201 identical
on TV Auto flags) and draws boxes like the TV recorder. Auto = the labeler, 71.7% exact vs the 2,191 hand labels
(red/non-red 89.9%; weak on HTF-vs-Flag size and Green/Perfect/Red HTF) -> candidate: train a classifier on
labeler features with the hand labels (A/B split).
Next: chart the 338 delisted dev rows, re-run the finalist + step 4 with them included.

**Delisted-trade rules to build before the delisted comparison (2026-11-19):**
- Buyouts: e.g. ARRY 2019-06-17 (Pfizer, $48 cash) gapped ~$30 -> ~$46, pinned under $48 until delisting. A
  trade from flag 17 is ~+20R and real. Today a trade still open at data end = STILL_OPEN_AT_DATA_END and is
  EXCLUDED from stats -> would silently drop buyout winners. For "^" tickers: force exit at the last bar's close.
- Tag buyout trades (gap then a pinned, tight range until delisting) and report EV with and without them --
  M&A gaps are luck, not the HTF edge. Same idea for bankruptcies (trade open into a delisting collapse).

**Stage 2c (profit-taking alternatives) -- built, NOT run (user: no need to test, 2026-11-19).** `partials.py`
supports ladder targets in pct / R / ADR units, Qullamaggie's single time partial (1/3-1/2 after 3-5 days, then
breakeven), and sell-into-extension (close >= SMA10 + k*ADR, or Bollinger close >= SMA20 + k*sigma);
`stage2c_variants()` (18) and `run_stage2 --stage 2c` (5m x 0.75/1.0 ADR x 4 trails, e15, non-delisted flags,
records adr14 for an ADR-dependent 10- vs 20-day trail). Expectation if ever run: partials stay second-order
(2a/2b: +-0.02-0.07R, early selling hurts); extension sales are the only idea with plausible EV upside.


## 29. Delisted rows charted + backtested: survivorship result (2026-11-21)

**Charting done:** all 338 delisted dev rows (AA..DKNG) reviewed in the local recorder: 1,291 flags on 247 tickers
(91 rows had no flags; 4 empty stub flags skipped). Re-exported every ticker from `annotations_local.json` and
ingested (master backup in scratchpad `htf_annotations_master_backup_20261121.csv`): **1,287 delisted rows,
master now 3,911 rows / 734 tickers.** 982 auto-labelled, 303 manual; 2 with no pattern (AKS^20 #10 Expanding,
CLVSQ^23 #15 Spiky Top -- Auto returned a non-trade class; pick one in the recorder and re-save).

**Engine changes:** `partials.run_partials(..., force_exit=True)` for "^" tickers sells whatever is open at the last
daily close (`DELISTED_LAST_BAR`) instead of STILL_OPEN; `simulate.minute_frame(..., last_bar=)` clips the post-flag
window at the delisting date; `run_stage2 --stage delisted` = gauntlet config (FINAL x ref/s30 x e15) on "^" flags,
output `trades_delisted_slip0.1.parquet` (stack onto `trades_gauntlet_slip0.1.parquet`). 18 tests pass.
Forced exits fired **0 times**: every trade hit its stop / 20MA before delisting (ARRY bought out 2019-06-17,
traded to 2019-07-29, 20MA exit 07-16 at +30.3R).

**Data checks:** minute close vs daily close on all 1,055 entry days: median ratio 1.0000, none off >3%.
Gap-through stops 19% vs 16% on TV (incl. DAILY_APPROX) -- comparable. 188 flags (15%) MISSING_MINUTE_DATA: 166
charted >6 months after the scanner streak (outside the pulled windows), 22 at a window edge. Pulling them needs
Massive minute access (ask first).

**Results, finalist 5m / 0.75 ADR / 20ma_touch / e15 / ref:**

| | trades | win % | EV R | EV ex top 5% | 10R+ | max DD |
|---|---|---|---|---|---|---|
| TV survivors | 2,164 | 28.4 | +0.51 | -0.07 | 63 | -40R |
| Delisted | 1,055 | 24.0 | +0.20 | -0.38 | 25 | -84R |
| Combined | 3,219 | | **+0.41** | | 88 | |

- Difference TV - delisted +0.31R, ticker-clustered bootstrap 95% CI [+0.06, +0.57], P(<=0) 0.007.
- Buyouts among delisted 10R+: only ARRY (Pfizer, +30.3R) and CMRX (Jazz, +13.4R). Without them delisted EV +0.16R.
- Every finalist variant is +0.20-0.22R on delisted; 1.00 ADR stop is best there (+0.22R, DD -47R vs -83R at 0.75).
- By cap: <$2B DEL +0.18 (TV +0.72); $2B+ DEL +0.22 (TV +0.34). **The small-cap edge looks largely survivorship**
  (small caps that stayed listed are the winners by construction). Re-judge the §25 cap filter on the combined set.
- By colour: non-red DEL +0.25 (TV +0.57), red DEL +0.13 (TV +0.49). Non-red <$2B: DEL +0.32 vs TV +0.86; combined
  +0.62R (824 trades).
- By era DEL: 2005-14 +0.17, 2015-19 +0.31, 2020-26 +0.14 -- weaker in every era, not one bad period.
- Caveats: delisted flags were charted later, in a different tool, 75% Auto pattern labels; pattern-level DEL vs TV
  splits mix Auto vs hand labels (TV uses `htf_pattern_truth.csv`). Joined table:
  `backtest_outputs/delisted_vs_tv_joined.parquet`.

**Implications / next:** (1) all step 4 filters must be judged on the combined TV + delisted set; (2) re-run the
gauntlet pieces (walk-forward, RC/SPA) on the combined set before trusting +0.41R; (3) re-check the 1.00 vs 0.75 ADR
stop choice on the combined set; (4) the held-out DKS..ZYXIQ set has ~914 more delisted rows -- chart them in the
local recorder before any out-of-sample test, or the OOS test is survivor-only too.

## 30. Local recorder replaces TradingView for the rest of the list (2026-11-21)

- **Speed:** local recorder 87 flags / active hour (2.3 min per ticker) vs TradingView 36 overall, ~52 in its best
  weeks -> ~1.7-2.4x faster at the same 5.2-5.4 flags per ticker. Remaining ~2,700 rows ~110-120 h vs ~180 h on TV.
- **Workflow from row 1,217 (after EQT):** chart everything in `local_recorder/` (filter "to do": rows >1216 + every
  delisted row, not reviewed = 1,791 still-listed + 914 delisted). TradingView-charted rows show a blue TV badge.
  Exports: `DELISTED_<t>, 1D.csv` (^) / `LOCAL_<t>, 1D.csv` (still-listed) -> `ingest_exports.py` as usual.
  The 91 no-flag delisted dev rows are now saved as reviewed / no flags.
- **Data:** `delisted_bars.py --active` pulled daily bars for all 2,610 still-listed rows -> `backtest_data/list_daily/`
  + `list_daily_manifest.csv`: 2,360 OK, 213 partial history (renamed symbols: Massive returns the new symbol only),
  37 price mismatch vs P123, 13 no check. To-do range: 147 partial + 17 mismatch (warning banner in the chart).
  Possible fix: stitch the former symbol's bars in front. P123 mktcap/adv30 per ticker: `backtest_data/p123_by_ticker/`.
- **Still needed for backtesting newly charted still-listed flags:** minute windows via `htf_backtest.minute_bars`
  (Massive) -- note its TV-chart scale check reads `chart_exports/`, which the ingest fills from LOCAL_ exports.
- Stage 1 grid on the 1,287 delisted flags running (`--delisted-only`, tag `stage1_delisted`) -> re-rank all 936
  strategies on TV + delisted, then re-run expiry / partials / gauntlet on the new shortlist.

## 31. Stage 1 re-ranked on survivors + delisted (2026-11-21)

`run_grid --delisted-only` (tag stage1_delisted, 1,287 flags x 936) stacked onto trades_stage1 ->
`htf_backtest.rerank_combined` -> `backtest_outputs/rerank_combined.csv` (box expiry, ref ladder, like Stage 1).
Ranked on Calmar + EV ex top 5% (the two survivorship hurt most).

- **Old finalist 5m / 0.75 ADR / 20ma_touch: rank 318 of 936** -- EV +0.39R, DD -74R, Calmar 16, EV on delisted +0.18.
- **Tight ADR stops lose most:** median DD by stop 0.75 ADR -75R, 0.5 ADR -84R, 0.33 ADR -117R vs 4% -56R,
  1.5 ADR -46R, last_higher_low -28R, low_10d -23R. Entry: 30m/15m/60m beat 5m/1m/r1_cross on DD.
- Families (combined, 3,000 trades each):

| strategy | EV | EV ex top5% | total R | max DD | Calmar | delisted EV | stop % |
|---|---|---|---|---|---|---|---|
| 15m / last_higher_low / close<adaptive 5-10 (rank 4) | +0.18 | +0.00 | 528 | -19 | 28.2 | +0.09 | 12.3 |
| 30m / 1.5 ADR / 20ma_touch (rank 40) | +0.31 | -0.01 | 865 | -39 | 22.2 | +0.17 | 7.6 |
| 15m / 1.0 ADR / 20ma_touch (rank 110) | +0.37 | -0.10 | 1078 | -49 | 21.9 | +0.20 | 5.1 |
| 30m / 4% / 20ma_touch (rank 158) | +0.38 | -0.17 | 1055 | -45 | 23.7 | +0.21 | 4.0 |
| 5m / 0.75 ADR / 20ma_touch (old) | +0.39 | -0.19 | 1214 | -74 | 16.3 | +0.18 | 3.8 |

- R is risk-normalised, so Calmar is the like-for-like comparison at equal % risk; wide stops also cut slippage in R
  (0.1% of price = 0.01R at a 12% stop vs 0.03R at 3.8%) -- relevant to the live stop-slippage problem.
- Next: shortlist -> e15 expiry + partials + gauntlet (walk-forward, RC/SPA, slippage) on the combined set.


## 32. Daily-bar data check: reused / renamed symbols (2026-11-21)

**Problem (user, on ES):** scanner days sat on prices that didn't fit. Massive aggregates are per SYMBOL: "ES" before
2015 is EnergySolutions (IPO 2007), while P123's ES is Eversource (NU until 2015-02-19). The puller's P123 check used
the median over the whole history, so 12 good years outvoted 8 bad ones. Same flaw in the delisted check.

**Fixes:**
- `htf_backtest/recheck_streaks.py` -> `backtest_data/streak_check.csv`: checks each scanner streak separately
  (3 months before .. 1 month after) against P123 ret_1m. Two corrections to the comparison itself:
  P123 ret_1m = **22 sessions**, not 21 (21 failed fast movers: QUBT 11% vs 5%, RLAY/VNDA/TMC/SKYH/USAR all pass at 22),
  and differences are taken in **log returns** (a 5% absolute miss on a +300% month is not a data error).
- `htf_backtest/fix_renames.py` -> `rename_fix_manifest.csv`: rebuilds still-listed bars from Massive ticker events
  (`/vX/reference/tickers/{t}/events`): drops current-symbol bars from before the company owned the symbol, fills
  earlier segments with the listed former symbols (AACG <- ATAI 2008), tries list/resolver candidates that hand over
  within 3 sessions. A rebuild is kept only if it matches P123 on more streaks or shows fewer wrong-company streaks
  (AA kept as is: Massive restarts it at the 2016 Alcoa split, P123 keeps the old history). 58 rows rebuilt;
  originals in `list_daily/_orig/`. Events are incomplete (ES lists no NU), so ES 2008 now shows NO bars, not wrong ones.
- Recorder: list badge BAD_DATA / SOME_STREAKS_BAD and a banner naming the bad streak ("don't flag there").

**After the 22-session + log-return fixes:** still-listed 2,288 OK / 119 SOME_BAD / 203 ALL_BAD
(was 601 bad); to-do range 218 active + 17 delisted rows with a bad streak. Many remaining bad streaks have NO bars
(the company's older symbol is unknown to Massive).
**Delisted backtest exposure:** only 28 of 1,055 delisted trades sit near a bad streak; without them delisted EV
+0.21R (vs +0.20R) -- §29 stands.

## 33. Status + START HERE next session (2026-11-21, end of day)

**Done today:** all 338 delisted dev rows charted + ingested (§29) · survivorship result: delisted +0.20R vs survivors
+0.51R, combined +0.41R · forced-exit rule (fired 0 times) · Stage 1 grid on delisted flags + combined re-rank (§31:
old finalist rank 318) · local recorder extended to the whole list, daily bars for all 2,610 still-listed rows,
P123 panel per ticker (§30) · reused/renamed-symbol data check + rebuild (§32) · charting speed measured (2x TV).

**Decisions waiting on the user:**
1. Strategy trade-off (§31): higher EV + deeper DD (30m / 4%, 15m / 1.0 ADR) vs smoother (30m / 1.5 ADR, structure
   stops). Then run the shortlist (~5) through e15 expiry + partials + gauntlet ON THE COMBINED SET:
   `run_stage2` needs FINAL replaced by the shortlist (and the delisted stage stacked), `gauntlet.py` must read
   TV + delisted trades.
2. Ingest the 73 TradingView exports DLPN..EQT still in Downloads (`ingest_exports.py`).

**User is charting** rows 1,217+ and the remaining 914 delisted rows in the local recorder (server: `cd
"Files/HTF/Advanced Backtesting/local_recorder"` then `../../../../.venv/Scripts/python.exe server.py`, open
http://127.0.0.1:8765, filter "to do"). Skip streaks the banner marks bad.

**Before backtesting newly charted still-listed flags:** pull their minute windows (`htf_backtest.minute_bars`, needs
the Massive subscription). Held-out set (DKS..ZYXIQ) stays untouched for tuning.

**Run commands** (from `Files/HTF`): `-m htf_backtest.run_grid --delisted-only --tag stage1_delisted` ·
`-m htf_backtest.rerank_combined` · `-m htf_backtest.run_stage2 --stage delisted` · `-m htf_backtest.delisted_bars
--active` · `-m htf_backtest.fix_renames [--tickers ...]` · `-m htf_backtest.recheck_streaks` · tests
`-m pytest -q htf_backtest/tests` (18 pass). `backtest_data/` + `backtest_outputs/` are not backed up.

**Next test spec, user's entry rule (2026-11-22, agreed, NOT run yet) -- "ORB above the line":**
each live session (15-session window after confirmation; a failed / fake breakout does NOT kill the flag):
wait for the 30m opening range; ONLY if the 30m high > R1, buy-stop at 30m high + 1 tick (fill after 10:00,
cancel at the close); if the 30m high <= R1, no order that day even if price breaks R1 later. Fills after price
dips back under R1 are fine; no max-extension limit. Stop = ADR-based % below the order price (e.g. 0.75 / 1.0 /
1.5 ADR). Code change: in entry.find_entry OR branch, `continue` when or_high <= r1 and trigger = or_high + tick
(current rule uses max(or_high, R1) -> ~70% of fills are afternoon breakouts AT the line; those had fewer
same-day stop-outs: 17% vs 25% for over-OR-high fills, 5m/0.75 ADR). Compare vs current rule on TV + delisted.

**Blind trainer moved into the local recorder (2026-11-22): http://127.0.0.1:8765/trainer.** Server-side blackout:
`/api/trainer/item` returns bars, scanner windows, earnings and P123 data cut at setup_confirmed (verified: last bar =
confirmation day on every checked item, no labels sent). Ticker hidden by default (toggle). Queue = the existing
`htf_trainer_queue.csv` (2,191 hand-labelled flags, random ticker order, halves A/B); 2,087 gradable with local bars
covering the confirmation day (others: renamed-symbol gaps). Answers (pattern / r1_date / clean 1-3 / notes) save
into the queue -> `score_trainer.py` unchanged. Plan: 200-300 of half A, then score; key question = does the blind
"clean" grade (and blind manual pattern) reproduce the +0.45-0.77R vs +0.11R manual-vs-Auto gap.

## 34. Phases 2-3 redone on TV + delisted flags; entry-rule test; blind trainer result (2026-11-23)

**Blind trainer (271 graded, half A):** red/non-red agreement with the hindsight labels 85%, exact pattern 61%,
R1 date exact 47% (median gap 2 days). Blind green/perfect calls +1.30R vs blind red +0.05R (old finalist);
gap ~1.1R with R capped at 10, permutation p ~0.003, same under 30m / 4%. As big as the hindsight-label gap ->
the pattern edge is not hindsight. Caveats: flags were charted before (memory), and it tests sorting, not finding.
On TV flags, skip-red by HAND labels beats the AUTO labeler (median DD -28R vs -42R, EV +0.41 vs +0.37) ->
step 4 pattern filters use the user's hand call, not the labeler (live, the user labels by eye anyway).

**Entry-rule test** (`run_stage2 --stage entry`, `entry_test_report.py`; 6 entries x 5 stops x 2 trails, e15,
ref ladder, 3,809 dev flags TV + delisted; new entry types in `entry.py`: `orb30`, `c5m/c10m/c15m`).
Median over the 10 stop x trail combos:

| entry | EV | max DD | EV TV | EV DEL |
|---|---|---|---|---|
| hybrid 30m OR (max(OR high, R1), live all day) | +0.29 | -52 | +0.36 | +0.15 |
| hybrid 5m OR (current) | +0.30 | -66 | +0.38 | +0.13 |
| 15m / 5m / 10m bar CLOSE above R1 (original idea) | +0.25 / +0.24 / +0.22 | -66..-71 | | |
| 30m ORB, only if OR high > R1 (user's rule) | +0.14 | -71 | +0.19 | +0.06 |

Why the ORB-above rule loses (30m / 1.0 ADR, vs hybrid 30m): same-day entries identical (1,242); the 354 trades it
skips averaged -0.91R under the hybrid (good, ~+320R); but on 1,534 flags it enters a LATER day at a +4.5% higher
fill and EV drops +0.68 -> +0.17 (~-780R). The best HTF trades open under R1 and break it intraday; waiting a day
chases them. Bar-close entries just pay a bit more than the buy-stop at the line. **Keep the hybrid OR entry.**

**Shortlist (`run_stage2 --stage final2 --strategies ...`, ref vs s30 ladder, slippage 0.1/0.3/1%):**

| strategy (20ma_touch) | EV | EV ex top5% | max DD | EV @0.3% | DD @0.3% | break-even slip |
|---|---|---|---|---|---|---|
| 5m / 0.75 ADR (old finalist) | +0.41 | -0.17 | -81 | +0.28 | -115 | 0.72% |
| 30m / 4% | +0.37 | -0.18 | -53 | +0.27 | -70 | 0.75% |
| 30m / 1.0 ADR | +0.34 | -0.11 | -52 | +0.26 | -72 | 0.88% |
| **30m / 1.5 ADR** | **+0.29** | **-0.03** | **-46** | **+0.24** | **-55** | **1.12%** |
| 5m / 1.5 ADR | +0.30 | -0.02 | -55 | +0.25 | -64 | 1.16% |
| 30m / last_higher_low | +0.19 | -0.02 | -30 | +0.15 | -36 | 1.14% |

**New finalist: 30m hybrid OR entry / 1.5 ADR stop / 20ma_touch / 15-session expiry / ref ladder.** Block-bootstrap
90% CI on EV [+0.23, +0.36] at every block size; 20 of 22 years positive (2008 -17R, 2011 -21R; 2022 +0.03);
top 10 trades = 8% of total R; s30 ladder adds +0.004R (keep ref). Gauntlet (`gauntlet --combined`): Reality Check /
SPA over 1,722 variants x 3,809 flags p <= 0.004 at every block size; finalist t 8.6 vs null 95% max-t 3.78.
Walk-forward on the combined Stage 1 grid: 98% / 87% / 99% of strategies positive in test 2016-19 / 2020-22 /
2023-26 (median test EV +0.38 / +0.17 / +0.27); Spearman train-vs-test +0.75 / +0.38 / +0.60; single-best picks
by max EV / Calmar land mid-pack in test -> pick from the broad good region, not the top cell.

**Red-flag filter on the finalist (hand labels, 0.1%):** all 3,128 trades +0.29 / DD -46 / Calmar 20.1; skip red
1,715 trades +0.33 / ex top5% +0.01 / DD -27 / Calmar 20.9; red at half size DD -36 / Calmar 20.8. Return per unit
of DD is ~equal; skipping red = half the trades with a smoother curve. Smoothest: skip red + 30m / last_higher_low
(+0.25R, DD -16R, few 10R+).

**START HERE next:** step 4 filters (§26) on 30m / 1.5 ADR / 20ma_touch / e15 with the hand red/green call
(skip vs half size), on TV + delisted, at 0.1% and 0.3% slippage. Files: `trades_final2_slip{0.1,0.3,1}.parquet`,
`trades_entry_test_slip0.1.parquet`, `report_entry_test_slip0.1.csv`, `gauntlet_report_combined_*.txt`.

## 35. Step 4 entry filters on the new finalists (2026-11-23)

`htf_backtest/step4_filters.py` -> `backtest_outputs/step4_filters.csv`. Strategies 30m / 1.5 ADR and 30m / 0.75 ADR
(20ma_touch, e15, ref ladder), TV + delisted, slippage 0.1 / 0.3%, all flags vs skip red (hand labels). Features
known at entry only (P123 cap / ADV30 at confirmation; SPY / IWM vs 200d SMA on the prior close, pulled to
`backtest_data/index_SPY|IWM.parquet`; Benzinga earnings in the next 10 sessions, 2015+). Pre-declared cutoffs.
Strict pass = kept EV beats unfiltered in all 5 periods (05-15, 16-26, WF 16-19 / 20-22 / 23-26) + higher Calmar +
>= 70% of 10R+ kept.

**Market regime is the one filter that matters.** SPY above its 200d (prior close), 1.5 ADR, 0.1%: trades dropped
(19%) earned +0.00R; DD -46 -> -20R, Calmar 20 -> 45, all 9 10R+ trades kept. Skip red + SPY > 200d: DD -27 ->
-12.5R, EV +0.33 -> +0.43, ex-top-5% +0.09. Most of the gain is 2005-15 (2008, 2011); in 2016-26 it is small but
positive (+0.02..0.07R); fails the strict all-periods test only by -0.01R in one window with no bear market (a
regime filter cannot help in years that never go below the 200d). "SPY or IWM > 200d" passes strictly in 3/8 cells.
**Adopted.**

Not adopted: cap < 2B (the §25 TV-only edge loses 2/3 of the 10R+ trades and fails 2016-19 on TV + delisted);
price >= 5 / 10, ADV30 >= $5M / 20M, stop >= 3% / 5%, ADR >= 4% / 6% (all make it worse -- cheaper, quieter names
did better at these slippage assumptions); no earnings within 10 sessions (those trades did BETTER, +0.45 vs +0.27;
earnings handling stays a management question, §26 C). Fill <= 2% over R1: small, consistent gain on skip red
(passes strictly for both stops at 0.1%), costs 20% of trades -- optional "don't chase" rule, retest live.

**Stacked results (skip red + SPY > 200d), 22 years, ~63 trades / year:**

| | slip | win | win/loss | EV | ex top 5% | 10R+ | max DD | Calmar | losing yrs | worst yr |
|---|---|---|---|---|---|---|---|---|---|---|
| 30m / 1.5 ADR | 0.1% | 41% | 2.8 | +0.43 | +0.09 | 6 | -12.5 | 47 | 2 | -1.7 |
| 30m / 1.5 ADR | 0.3% | 40% | 2.7 | +0.37 | +0.04 | 6 | -13.4 | 38 | 2 | -4.4 |
| 30m / 0.75 ADR | 0.1% | 30% | 4.2 | +0.59 | -0.01 | 41 | -20.1 | 40 | 1 | -6.1 |
| 30m / 0.75 ADR | 0.3% | 29% | 3.9 | +0.42 | -0.15 | 37 | -25.4 | 23 | 3 | -10.2 |

The regime filter makes the high-RR 0.75 ADR version viable even at 0.3% slippage (DD -86 -> -25R). Plan: start
1.5 ADR (robust), measure live slippage on the first 20-30 fills; if <= ~0.1%, move to 0.75 ADR for the bigger
winners. Both: skip red (hand call) + only trade when SPY closed above its 200d the day before.

**Next:** §26 C trade management (earnings hold rule, re-entry after stop-out, trail re-check) and D portfolio layer
(open-risk cap, max positions on busy days, account-level DD) on the stacked rules; then Bar Replay + held-out rows.

## 36. Step 13 trade management: re-entry, earnings, trail re-check (2026-11-23)

`htf_backtest/mgmt.py` (one pass, up to 3 attempts per flag, each attempt's sales stored) -> `trades_mgmt_slip0.1`;
`mgmt_report.py` -> `step13_reentry.csv`, `step13_earnings.csv`. Trails: `run_stage2 --stage final2` 2 stops x 8
trails -> `trades_trails_slip0.1`. Attempt 1 reproduces the final2 / highrr trades exactly (62/62, |dR| = 0).
"Filtered" = skip red (hand) + SPY > 200d on the prior close (re-entries must pass SPY too).

**Re-entry after a LOSS** (fresh 30m OR buy-stop at max(OR high, R1), fresh stop, from the session after the
stop-out). Per-flag R, filtered:

| stop | window / max attempts | unknown flags | R per flag base -> with re-entry | re-entry trade EV | DD | Calmar | periods better |
|---|---|---|---|---|---|---|---|
| 1.5 ADR | inside 15-session window / 2 | 1% | +0.44 -> +0.53 | +0.36 | -12.5 -> -18.0 | 48 -> 40 | 5/5 |
| 1.5 ADR | inside window / 3 | 1% | +0.44 -> +0.54 | +0.34 | -12.5 -> -17.9 | 48 -> 41 | 5/5 |
| 1.5 ADR | within 10 sessions of exit / 3 | 9% | +0.53 -> +0.72 | +0.41 | -11.6 -> -15.8 | 57 -> 57 | 5/5 |
| 0.75 ADR | inside window / 2 | 1% | +0.60 -> +0.74 | +0.32 | -20 -> -32 | 40 -> 32 | 5/5 |
| 0.75 ADR | within 10 sessions / 3 | 8% | +0.72 -> +1.07 | +0.46 | -19 -> -33 | 48 -> 41 | 5/5 |

Re-entry trades earn about as much as first entries (+0.3..0.45R) and add +20-50% total R, better in every period;
the cost is a deeper DD (more R at risk in clusters), so return / DD is flat to slightly lower. "Re-enter after ANY
exit" variants are NOT usable: winners exit late, their re-entry windows run past the cached minute data
(DATA_SHORT), dropping them leaves a loser-only sample. The "within 5 / 10 sessions" rows drop 4-9% unknown flags
(late re-entries) -- treat as optimistic. **Adopt: one re-try (max 2 attempts) after a stop-out, inside the
original 15-session window.**

**Earnings hold rule** (2015+, attempt-1 trades open at the close before a report; BMO/unknown -> prior close,
AMC -> that close). 15% of filtered trades are exposed; 41-63% of those are cushioned.

| rule (filtered) | 1.5 ADR EV / DD / Calmar | 0.75 ADR EV / DD / Calmar |
|---|---|---|
| hold through | **+0.39 / -11.2 / 34** | **+0.52 / -19.8 / 26** |
| sell all | +0.30 / -15.5 / 19 | +0.43 / -23.0 / 18 |
| sell half | +0.35 / -10.4 / 33 | +0.47 / -21.1 / 22 |
| sell all unless cushioned | +0.33 / -11.2 / 29 | +0.47 / -22.5 / 20 |
| sell half unless cushioned | +0.36 / -11.2 / 31 | +0.49 / -19.2 / 25 |

Exposed trades average +2.1R (1.5 ADR) / +4.2R (0.75 ADR) held through; selling costs 0.5-0.8R per exposed trade and
half the 10R+ winners. Worst held-through outcome filtered: -1.65R (1.5 ADR), -3.3R (0.75 ADR); unfiltered 0.75 ADR
-7.3R. **Adopt: hold through earnings** (sell half if a single gap of -3R+ is unacceptable at your size).

**Trail re-check (filtered):** 20ma_touch stays best or tied: 1.5 ADR Calmar 47 (close_below_20ma 47, low_of_close
_below_20ma 43, 10ma trails 29-37); 0.75 ADR Calmar 40 (close_below_20ma 33 with 49 vs 41 10R+ trades; 10ma
trails 25-33). **Keep 20ma_touch.**

**Rule set after step 13:** 30m hybrid OR entry, 1.5 ADR (or 0.75 ADR) stop, 20ma_touch, ref ladder, orders live 15
sessions, skip red, SPY > 200d prior close, one re-try after a stop-out inside the window, hold through earnings.
**Next: step 14 portfolio layer** ($35k, 0.25% risk, position / open-risk caps, account-level DD with overlaps).

## 37. Cross-candle entry test (user idea, 2026-11-24)

Rule (`entry.py` xc5m / xc15m / xc30m): each session, the first N-min candle (from 9:30) that trades above R1; once it
closes, buy-stop at its high + 1 tick, live to the close; no fill -> next session starts fresh; 15-session window.
`run_stage2 --stage final2 --tag xcross_slip{0.1,0.3}`, 20ma_touch, ref ladder, TV + delisted.

Filtered (skip red + SPY > 200d), EV / max DD:

| entry | fill vs R1 (median) | 1.5 ADR @0.1% | 1.5 ADR @0.3% | 0.75 ADR @0.1% | 0.75 ADR @0.3% |
|---|---|---|---|---|---|
| hybrid 30m (current) | +0.2% | +0.43 / -12.5 | +0.37 / -13.4 | +0.59 / -20 | +0.42 / -25 |
| hybrid 5m | +0.2% | +0.44 / -14.3 | +0.39 / -16.0 | +0.61 / -26 | +0.47 / -33 |
| cross candle 5m | +0.7% | +0.44 / -12.9 | +0.38 / -15.3 | +0.57 / -27 | +0.44 / -35 |
| cross candle 15m | +1.0% | +0.42 / -14.5 | +0.36 / -15.5 | +0.58 / -30 | +0.42 / -46 |
| cross candle 30m | +1.4% | +0.39 / -15.2 | +0.34 / -16.3 | +0.51 / -24 | +0.38 / -30 |

Unfiltered, the cross candle cuts the 0.75 ADR drawdown (-50 vs -64R at 0.1%, same EV) by skipping fake pokes; with the
filters on that advantage is gone. Plateau again: hybrid 30m and cross-candle 5m are equivalent; bigger candles pay
more above R1 and trail. Keep the hybrid 30m (smoothest at both slippages); cross-candle 5m is an acceptable alternative.

## 38. Decisions locked (2026-11-24, user)

**Stop 0.75 ADR** (high-RR; plan for -1.3R per loss as the conservative cost assumption). **One re-try** after a stop-out
inside the 15-session window (user's choice, knowing that at -1.3R losses the re-try trades earn only +0.09R and DD
-38 -> -50R; at normal slippage +0.31R, DD -20 -> -31R). Max attempts 3 adds +0.05..0.26R on 220 trades: no.
Full rule set: hybrid 30m OR entry (buy-stop max(R1, 30m high) + 1c, cancel EOD, 15 sessions), 0.75 ADR stop, ref
ladder, 20ma_touch, skip red (Red HTF + Big Red Flag, hand call), no new entries (incl. re-tries) when SPY closed
below its 200d the day before (existing positions managed normally), hold through earnings, one re-try.
Expect (skip red + SPY, 0.75 ADR, before re-try): 30% win, 4.2:1, +0.59R (+0.38R at -1.3R losses), median ~58
trades/yr in the 27% dev sample -> ~210/yr on the full list, heavily clustered (48% of weeks no trade; peaks
~44/week, up to ~70 open positions projected) -> step 14 caps needed. Top 5% of trades = 100-160% of total R.
Next: step 14 portfolio layer; live scanner (pinned, memory project_htf_live_scanner_plan).

## 39. Final-system deep dive: costs, SPY rule, patterns, tails, frequency, re-tries, EV math (2026-11-24)

All on the locked system (30m hybrid OR / 0.75 ADR / 20ma_touch / ref ladder / e15), TV + delisted dev flags,
`trades_highrr_slip0.1` / `trades_final2_slip0.1` / `trades_mgmt_slip0.1`.

**Cost model: "every loss costs an extra 0.3R / 0.5R"** (user's conservative assumption instead of % slippage; losers
get -0.3/-0.5R added, winners as backtested at 0.1%). Skip red + SPY > 200d:

| stop | loss cost | avg loss | win/loss | EV | max DD | losing yrs | worst yr |
|---|---|---|---|---|---|---|---|
| 0.75 ADR | none | -1.00 | 4.2 | +0.59 | -20 | 1 | -6 |
| 0.75 ADR | -1.3R | -1.30 | 3.2 | **+0.38** | -38 | 4 | -22 |
| 0.75 ADR | -1.5R | -1.50 | 2.8 | +0.24 | -62 | 7 | -32 |
| 1.5 ADR | none | -0.74 | 2.8 | +0.43 | -12.5 | 2 | -2 |
| 1.5 ADR | -1.3R | -1.04 | 2.0 | +0.25 | -22 | 4 | -16 |
| 1.5 ADR | -1.5R | -1.24 | 1.7 | +0.13 | -43 | 6 | -25 |

A fixed R cost hits both stops equally in R, so the 0.75 ADR version (bigger winners) wins; % slippage hits tight stops
harder in R (0.3% of price = ~0.08R on a 3.9% stop vs ~0.04R on 7.7%), which is why 1.5 ADR looked more robust in §34.
-0.3R extra = ~1.2% of price per losing exit on 0.75 ADR -- very conservative except for gaps (already modelled:
~1 in 5 stop-outs gap through). Decision: 0.75 ADR, plan at -1.3R.

**0.75 ADR by view (0.1% slip | -1.3R losses):** all flags +0.38 / DD -64 / 3 neg yrs | +0.16 / -120 / 9;
skip red +0.44 / -47 | +0.23 / -86; SPY > 200d only +0.46 / -32 | +0.24 / -87; **skip red + SPY +0.59 / -20 / 1 |
+0.38 / -38 / 4**. Half size instead of skip when SPY < 200d: Calmar 27 vs 40 (worse) -> skip.

**Why the SPY rule now matters (but looked weak in §5):** §5 was all patterns, survivors, daily proxy: below-200d
+0.20R. Now (30m / 0.75 ADR, EV above / below): survivors all patterns +0.52 / +0.11, survivors non-red +0.68 / -0.17,
delisted non-red +0.39 / -0.19, combined non-red +0.59 / -0.18 (1 10R+ of 337). On survivors 6 of the 7 below-200d
10R+ trades were RED flags -- they propped up the old all-pattern view. Removed trades (skip red) lost in 2008 -17R,
2009 -12, 2010, 2011, 2015, 2023, 2025, 2026; 2022 ~0 (-21R at -1.3R); only 2018-19 slightly positive (12 trades).
The post-reclaim windows (§5, +1.1..1.3R) are kept by construction. **Live rule:** SPY daily close vs SMA200 checked
after the close; if below -> no new entries next day (incl. re-tries); held positions managed normally; armed flags stay
armed, window keeps counting (re-entering after a mid-window reclaim is untested). Mechanical, no "close enough".

**Patterns (SPY > 200d, 0.75 ADR):** EV / ex-top-5% / EV at -1.3R / 10R+ / DD at -1.3R:
Big Perfect +0.68 / +0.06 / +0.47 / 6 / -17; Perfect HTF +0.67 / +0.02 / +0.47 / 9 / -37; Big Green +0.55 / -0.04 /
+0.34 / 11 / -45; Green HTF +0.54 / -0.05 / +0.33 / 15 / -27; **Red HTF +0.35 / -0.28 / +0.13 / 14 / -48; Big Red +0.29
/ -0.30 / +0.06 / 16 / -91** (741 trades, 23% win, most common). Reds make monsters at the same rate; their ordinary
trades lose ~0.3R more. Skip both; if ever adding one back, Red HTF at half size, never Big Red. Big Perfect is now
strong (+0.68, n=177) -- opposite of the survivor-only Stage 1.

**Tail dependence (skip red + SPY, 1,381 trades):** top 5% = 70 trades, each >= 7.7R, = 102% of total R (158% at -1.3R).
EV without top 1% +0.41 (+0.19); without top 5% -0.01 (-0.23); without top 10% -0.35 (-0.58). A monster-hunting
system: never cut winners short, don't skip uncertain green setups, expect flat/down stretches between ~3 monsters a
year (sample), measure real loss R from day one.

**Frequency (sample = rows 1-1,051 of 3,862 = 27% of the list; x3.7 for the full list):** mean 63 trades/yr, **median
58** (2016-26 median 68); 2020 158, 2021 149, 2022 11, 2008 1. Full list ~210/yr median (~4/week), ~250 recent;
R/yr at -1.3R ~+24 sample -> ~+90R full list (~+22%/yr at 0.25% risk, $35k) -- before position caps; DD in R
will be deeper on the full list (rough guess -80..-140R) -> step 14. 10R+ ~1.9/yr sample (~7/yr full), 5R+ ~5.9 (~22).
**Clustering:** 48% of weeks and 22% of months have no new trade; busiest 10% of months = 34% of trades (Dec 2020: 29);
open positions in sample median 3, 90th pct 6, max 19 (2020-12-23) -> projected ~22 / ~70 at peak. Needs a position
cap + busy-day priority rule.

**Re-tries (W15, after a loss), skip red + SPY, 0.75 ADR:**

| max attempts | trades | R/flag | total R | DD | Calmar | extra attempt EV |
|---|---|---|---|---|---|---|
| 1 | 1,381 | +0.59 / +0.38 | 813 / 525 | -20 / -38 | 40 / 13.7 | -- |
| 2 | 1,986 | +0.74 / +0.43 | 1,014 / 592 | -31 / -50 | 33 / 11.9 | +0.31 / +0.09 |
| 3 | 2,194 | +0.79 / +0.45 | 1,081 / 617 | -34 / -51 | 32 / 12.1 | +0.26 / +0.05 |

(normal slip / -1.3R losses). Re-try trades win less often, so a fixed loss cost hurts them most. User chose ONE
re-try (§38); two re-tries add almost nothing. Mechanics: stopped out -> from the next session the flag is armed again
with the same daily rule inside the original window (clock not reset), fresh 0.75 ADR stop from the new fill, same
size, SPY rule applies, no re-try after a winning exit, no third attempt.

**Hybrid entry, plain words:** after 30 minutes, buy-stop at max(R1, 30-min high) + 1c, live to the close, cancel and
redo daily for 15 sessions. Case 1 (open below R1, 30m high < R1): order at R1 -> intraday breakout filled at the line
(~70% of fills, best trades). Case 2 (pokes above R1 in the first 30m): order over the 30m high (filters fades).
Case 3 (gap over R1): order over the 30m high. The user's ORB rule skips case 1 and buys a later day ~4.5% higher.
Entry minute is a plateau (§37): pick for convenience.

**EV arithmetic / simulator:** EV = win% x avg win - loss% x avg loss = 0.305 x 4.21 - 0.695 x 1.30 = +0.38R. "R:R 3.2"
is avg win / avg loss (4.21 / 1.30); 0.30 x 3.2 - 0.70 x 1 = +0.26 is the same thing in units of the average loss
(0.26-0.29 x 1.3 = ~0.34-0.38R). `Files/EP/Tools/Equity Curve Simulator.html` models win = +(RR - cost), loss =
-(1 + cost): enter win rate 30.5, RR 4.51, cost 0.3, risk 0.25%, ~210 trades, $35,000 -> EV +0.38R. It uses one fixed
win size, so it understates dry spells / DD for this fat-tailed system; step 14 (real trade replay) is the real test.

**Live scanner: pinned** (memory `project_htf_live_scanner_plan`). TradingView screener lacks "SMA vs N days ago" and
SMAs on the preview grid; Pine Screener only scans a watchlist (<=1,000) or index (<=4,000); thinkorswim desktop custom
study editor freezes on this PC (Windows 11 build 26300 has no WMIC; log "Cannot run program wmic"); TOS web has no
custom thinkScript. Plan: morning P123 pull with the exact scanner formulas + 6-month graduates + Massive daily bars ->
local recorder "live mode" grid (SMA10/20), arm flags -> armed_flags.csv.

## 40. Lock re-check: entries head-to-head + core split on the final system (2026-11-24)

`run_stage2 --stage lock` (7 entries x 0.75 ADR x 20ma_touch x e15 x 8 partial variants, 3,809 dev flags TV + delisted,
0.1% slip) -> `trades_lock_slip0.1.parquet`; `lock_report.py` -> `lock_recheck.csv`. R includes -1.3R per loss; no
re-try (same for every row). Paired bootstrap by flag vs 30m/ref (flag R = 0 when not traded), 90% CI on total R.

FINAL view (skip red hand labels + SPY prior close > 200d):

| entry (ref ladder) | n | win | RR | EV | EV ex5 | total | max DD | Calmar | neg yrs | dTotal vs 30m [90% CI] |
|---|---|---|---|---|---|---|---|---|---|---|
| 1m | 1424 | 30.9% | 3.29 | +0.42 | -0.20 | 597 | -42 | 14.1 | 6 | +71 [-47, +192] |
| r1_cross (buy-stop at R1 from the open) | 1432 | 31.0% | 3.27 | +0.42 | -0.20 | 597 | -47 | 12.7 | 4 | +72 [-51, +202] |
| 5m | 1416 | 30.6% | 3.30 | +0.41 | -0.22 | 574 | -48 | 11.9 | 5 | +49 [-50, +154] |
| **30m (locked)** | 1381 | 30.5% | 3.24 | +0.38 | -0.23 | 525 | **-38** | 13.7 | 4 | 0 |
| 15m | 1404 | 30.2% | 3.26 | +0.37 | -0.24 | 520 | -43 | 12.0 | 3 | -5 |
| xc5m cross candle | 1403 | 30.5% | 3.18 | +0.36 | -0.24 | 505 | -51 | 9.9 | 4 | -21 |
| 60m | 1358 | 30.3% | 3.15 | +0.33 | -0.24 | 453 | -39 | 11.6 | 6 | -72 [-178, +25] |

Read: still a plateau -- no entry differs from 30m significantly (every CI spans 0). r1_cross / 1m earn ~+0.04R more
per trade (+~50 extra trades) at ~4-9R more drawdown; 30m has the lowest DD. The earlier "30m beats r1_cross on DD"
(§31) only half-holds: lowest DD yes, best Calmar no (1m 14.1). Backtest ignores open-auction fill quality (r1_cross
fills gap-ups at the open), which favours waiting live.

Exits on 30m (FINAL view): start40 / spacing20 +12R [-20/-13, +45/+36]; s30 +8R; core0 +5R [-43, +50] but best DD
(-33) / Calmar 16.0 / EV ex5 -0.16 with fewer 10R+ (35 vs 41); core30 +2R; ref 0; core70 -3R; hold 100% (no partials)
-32R [-80, +20], DD -44, 6 neg years. Core split 0-70% doesn't matter for EV (same as §20); less core = smoother,
no partials = worst. All-flags view ranks the same way.

## 41. HELD-OUT TEST: the locked system FAILED on the first held-out batch (2026-11-25)

Ingested the pending exports (backup htf_annotations_master_backup_20261125.csv): 447 held-out flags on 94 tickers
(DKS..ETSY, rows after DKNG; dev unchanged). Minute bars pulled (329 windows). Locked system run ONCE:
`HTF_SAMPLE=holdout run_stage2 --stage lock --tag lock_holdout_slip0.1` + `mgmt` (trades_mgmt_holdout_slip0.1).
(Fixed on the way: minute_bars.py now skips ^ rows -- pulling them created empty minute_bars/<^ticker>/ folders that
would have hidden the real delisted_minute bars; removed, 0 rows lost.)

30m / 0.75 ADR / 20ma_touch / ref ladder, R incl. -1.3R per loss:

| view | DEV n / win / EV [90% CI] / maxDD / 10R+ | HELD-OUT n / win / EV [90% CI] / maxDD / 10R+ |
|---|---|---|
| FINAL (skip red + SPY>200d) | 1381 / 30.5% / **+0.38 [+0.23,+0.54]** / -39 / 41 | 180 / 21.1% / **-0.40 [-0.66,-0.13]** / -81 / 1 |
| FINAL + one re-try | (~ +0.3) | 274 / 20.4% / -0.34 [-0.58,-0.08] / -107 / 4 |
| all flags | 3133 / 27.1% / +0.16 / -121 / 79 | 386 / 20.5% / -0.35 / -137 / 1 |
| green, SPY below | 337 / -0.41 | 45 / +0.09 (noise) |
| red | 1413 / +0.08 | 160 / -0.42 |

Diagnostics -- NOT explained by: charting tool (TV -0.42, local -0.30), label source (auto -0.40, manual -0.40),
ticker concentration (ticker-cluster CI -0.65..-0.15), entry/stop geometry (stop 3.8% vs 3.7%, fill +0.2% over R1
both), luck of ticker draw (0 of 5,000 random 84-ticker dev slices reach -0.40; dev 5th pct +0.03). Trades simply
didn't run: MFE >= 5R in 12.8% vs 21.9% dev; one 10R+ (expected ~5). No green-vs-red edge in held-out either.
Annotation drift: 4.8 flags per scanner row vs 3.7 in dev (looser?), R1 age 9 vs 7 days, flag length same.

Hypotheses (open): (1) dev results inflated -- flags drawn/redrawn with hindsight while backtests ran, plus picking
the strategy on dev; (2) looser annotation in the newer batch; (3) segment/regime chance (D-E tickers). The whole flag
population underperforms, not just the filtered strategy, so (1)/(2) are more likely than strategy overfit alone.
**Verdict: do NOT go live at size. Next: a second held-out batch annotated live-style (screener replay mode, only
data up to the arm date), spread across the alphabet, to separate hindsight annotation from a real edge.**
