# Two New Robustness Tests, Inspired by "Evidence-Based Technical Analysis" (David Aronson, 2007)

**Date:** 2026-09-03
**Strategy under test (mainly):** the "4th chosen one" — `E60M / 0.50 ADR stop / trail below 20-day moving average / sell in stages / start taking profit at +20% / core 50%`
**Book used:** *Evidence-Based Technical Analysis* by David Aronson (the PDF sitting in this folder) — a well-known book about how to test trading rules honestly, and about the sneaky ways backtests fool people.

---

## 1. Why we did this

I read the relevant chapters of the book and found two real gaps in everything we'd tested so far — not nitpicks, actual holes:

1. **We never checked whether our edge is just "being long stocks in a market that went up."** The book has a whole chapter on this exact trap.
2. **We only ever tested one "pretend I don't know the future" split of the data.** The book says you should do this several times at different points in time, not just once, before trusting the result.

This document explains, in plain language, what each test actually does, what we found, and what it means for the strategy.

---

## 2. Test 1 — "Is this just being long stocks in a bull market?"

### The problem, explained simply

Imagine a trading rule that is completely random — it has zero skill, might as well be picked by a coin flip. Now imagine that coin is weighted so it says "buy" 90% of the time and "sell" 10% of the time. If you test that worthless rule during a period where the stock market mostly went up, **it will show a profit** — not because the rule is smart, but purely because it was betting "up" most of the time during an up market. The book proves this with real numbers: two totally random, skill-free rules, tested on real S&P 500 data from 1976-2004 (a period stocks rose overall), both come out looking profitable. Neither has any actual insight. It's an illusion caused by (a) always betting the same direction, and (b) the market drifting that direction anyway.

Our EP strategy is **always long** — every single trade is a bet that the stock goes up. And the years we tested (2012-2026) were mostly good years for small/mid-cap growth stocks. So a fair question is: how much of our strategy's profit is genuine skill at picking the right moments (the "episodic pivot" signal), versus just the fact that we're always long volatile stocks during a period when those kinds of stocks tended to go up anyway?

None of our earlier tests this project (White's Reality Check, the Hansen SPA test, the basic walk-forward test) actually answer this question — they check different things (like "did we get lucky by testing 600 variations and picking the best one"), not this specific "long-bias in an up market" problem.

### What we built to test it

We built a **fake control group** — a stand-in for "a strategy with zero real skill, but the exact same long-bias and same mechanical rules."

For each of our 605 real winning trades (real ticker, real EP-trigger date), we:
1. Took that same ticker.
2. Picked 5 **random other days** for that ticker — days that had nothing to do with a real episodic pivot event, no gap-up, no special chart pattern, nothing. Just random Tuesdays, so to speak.
3. Made sure those random days were far away (15+ trading days) from any real EP event for that ticker, so there's zero chance of accidentally re-using real signal.
4. Ran the **exact same trading rules** as the real strategy on that random day — same entry trigger (buy if price breaks above the first 60 minutes' high), same stop-loss (0.5× the stock's typical daily range), same trailing stop (exit if price closes below the 20-day moving average), same staged profit-taking.

This gave us 2,561 "fake" trades — same tickers, same mechanical rules, same long-bias, but entered on random days with no real EP signal behind them. If our real strategy is genuinely better than this random control group, that's real evidence of skill. If it's about the same, the "edge" is probably just long-bias-in-an-up-market.

### What we found

| | Real EP-triggered trades | Random/fake trades |
|---|---|---|
| Number of trades | 605 | 2,561 |
| Win rate | 24.8% | 25.8% |
| Profit factor (money won ÷ money lost) | 1.79 | 1.33 |
| **Average profit per trade (in R, i.e. multiples of money risked)** | **0.618R** | **0.234R** |

Two things jump out:

- **The random control group is NOT zero.** It made money too — 0.234R per trade on average, just from randomly buying volatile stocks and riding a mechanical stop/trail. This is the book's warning proven true on our own data: some of our profit really is just "being long stocks that tend to go up," not signal skill.
- **But the real strategy clearly beats the random one** — 0.618R vs 0.234R, about 2.6x higher. Win rates are nearly identical (24.8% vs 25.8%), so the extra edge isn't about picking more winners — it's about the winners being bigger relative to losers when the trade is a real EP event. That's a meaningful, encouraging sign that the EP trigger itself is adding something real.

### Is that gap actually real, or could it be luck?

We ran the difference (real minus fake) through the same "block bootstrap" significance test used earlier in this project — the short version: take the actual trades, shuffle and re-sample them thousands of times (in realistic chunks that respect the fact trades near each other in time tend to move together), and see how often a gap this big could show up purely by chance.

| How big a time-chunk we resample at once | Is the gap statistically real? |
|---|---|
| 1 trade at a time (loosest, least realistic) | Yes — only 2.3% chance this is luck |
| 10 trades at a time | Yes — 4.0% chance |
| 25 trades at a time | Borderline — 4.9% chance |
| **50 trades at a time (most realistic — accounts for trades clustering in time)** | **Borderline-no — 5.7% chance** |

The usual scientific cutoff for "statistically significant" is a 5% or lower chance of it being luck. At the loose end we clear that bar. At the most careful, realistic end (accounting for the fact nearby trades aren't fully independent of each other — something we proved matters a lot earlier in this project), we land just on the wrong side of that line.

**Plain-English verdict:** the real strategy does look meaningfully better than a "just be long stocks" control group, and the direction and size of the gap is encouraging — but we can't say with full confidence that gap is guaranteed real rather than a coincidence. It's a "leaning positive, not proven" result. Not a clean pass like some of our earlier tests, not a failure either.

---

## 3. Test 2 — Testing the strategy-picking process on three separate "time machines"

### What walk-forward testing means, in plain terms

Imagine you could travel back to some date in the past, and from that point you could only look at data *before* that date. You use that limited data to pick your best trading strategy out of many candidates. Then you fast-forward to today and check: how did that specific pick actually perform on the years afterward — years it never got to see or use while being chosen?

This is about as honest a test as you can run, because the strategy genuinely never had access to the "future" data it's being judged on.

We had already done this once, earlier in the project:
- **Pretend it's January 2020.** Only use 2012-2019 data (311 events) to search through ~600 candidate strategies and pick the best one.
- **Then test that specific pick on 2020-2026 — years it never saw.**
- Result: the pick's average profit per trade dropped about 25% going from "training" data to the real unseen years, but stayed clearly profitable across a large number of trades (532). That was a genuinely encouraging result.

The book's point is: **one such test isn't enough.** You want to repeat it at multiple points in time to see if that result was consistent, or if it just happened to work out that one time. So we added two more "time machines":

- **Pretend it's January 2022.** Only use 2012-2021 data (820 events) to pick a strategy. Test it on 2022-2023 (never seen).
- **Pretend it's January 2024.** Only use 2012-2023 data (1,396 events) to pick a strategy. Test it on 2024-2026 (never seen).

Every time, the "pick a strategy" step re-ran the full search process (a coarse first pass through 324 strategy combinations, then a deeper second pass on the most promising 25) completely from scratch, using only the data available at that point in time.

### What we found — all three time machines side by side

| Time machine | Data used to pick ("training") | Strategy it picked (blind) | How well it did on training data | Years tested on (never seen) | How many real trades in that test | How well it actually did | How much worse than training |
|---|---|---|---|---|---|---|---|
| **#1 (2020)** | 2012-2019 | 60-min entry / 3% stop / trail below 10-day MA / start selling early / 30% core | 0.71R avg profit/trade | 2020-2026 | 532 | 0.53R avg profit/trade | -25% |
| **#2 (2022)** | 2012-2021 | 60-min entry / 3% stop / trail below 20-day MA (low-of-day version) / start selling late / 70% core | 1.03R avg profit/trade | 2022-2023 | 70 | 0.50R avg profit/trade | -52% |
| **#3 (2024)** | 2012-2023 | 15-min entry / ADR-based stop / trail on 20-day MA touch / start selling early / 70% core | 0.99R avg profit/trade | 2024-2026 | 325 | **0.12R avg profit/trade** | **-88%** |

("Avg profit per trade" is measured in R — multiples of the money risked on the trade — same unit used throughout this whole project, so these numbers are directly comparable to everything else we've reported.)

### What this actually means, in plain English

**Finding #1 — every single blind test picked a DIFFERENT "best" strategy.** Different entry timing (60-minute breakout vs 15-minute breakout), different stop-loss method, different trailing-stop rule, different profit-taking schedule. None of the three matches each other. **None of them match the 4th chosen one either** — the strategy that's actually been the leading candidate for this whole project.

What this suggests: the *broad idea* behind the EP strategy (buy the gap-up event, use a stop based on the stock's volatility, trail with some kind of moving average, sell in stages rather than all at once) keeps showing up as genuinely profitable no matter which years you test it on. But the *exact fine-tuned settings* — is it a 15-minute or 60-minute entry, a 3% stop or an ADR-based stop, which specific moving average — seem to shift around depending on which years happen to be in the training data. That's a classic sign that the fine details are partly fitting noise in whatever data window they're given, rather than reflecting one single "true" best recipe. The core concept looks more trustworthy than any one specific exact parameter combination.

**Finding #2 — the most recent test showed the worst result, and it's not a small, unreliable sample.** Test #3 (pretend it's 2024, test on 2024-2026) had 325 real trades in its "never seen" test — a solid, meaningful sample size, not a fluke-prone handful. And it showed the strategy's average profit per trade fall by 88%, with the win rate dropping to just 9.2%. It stayed barely profitable overall, but only barely — a much weaker showing than tests #1 and #2.

**Finding #3 — the trend across all three tests is getting worse, not staying flat.** -25%, then -52%, then -88%. That's a worsening pattern over time, not random noise bouncing around a stable number. It could mean the market conditions of 2024-2026 specifically were tougher for this kind of strategy, or it could mean the edge is genuinely fading as more traders/algorithms catch onto the same kind of pattern (a very common real phenomenon — edges often decay once they become known). We don't yet know which explanation is correct — that's an open question, not a settled one.

---

## 4. Putting it all together — the honest bottom line

**The good news:** every test this project has run — the search-bias correction (White's Reality Check / Hansen SPA), the original walk-forward test, and now this random-entry control group — has found *some* real, positive edge that's hard to fully explain away as luck or as a testing artifact. This isn't a strategy with zero substance behind it.

**The more sobering news, from today specifically:**
- The "is this just being long stocks" test came back borderline, not a clean pass. Some real portion of the profit probably is just long-bias in a mostly-rising market for this kind of stock — the question is how much, and we can't fully separate that out with full statistical confidence yet.
- The strategy-picking process doesn't land on the same answer twice. Every blind test picked a different set of exact rules, which is a real overfitting warning sign about the fine details (though not necessarily about the core EP concept).
- The most recent and largest out-of-sample test showed real, substantial performance decay — the weakest of the three tests, on the best-sized sample of the three. That's worth taking seriously, not brushing off.

None of this means the strategy is fake or worthless — it means our confidence should be a notch more cautious than it was before today, and there are concrete open questions worth chasing before treating any single exact parameter set as "the" answer.

---

## 5. Open questions worth investigating next

1. **Why did the 2024-2026 test decay so much more than the earlier ones?** Is it something specific to that period (market regime, volatility environment), or a sign of general edge decay over time?
2. **Given that the exact "winning" parameters keep changing, does a simpler, less fine-tuned version of the strategy hold up more consistently** across all three time windows than any single hyper-optimized pick does?
3. **Can the "is it just long-bias" gap be tightened up** — e.g., a bigger random-entry control sample, or extending the same test to the other 3 "chosen ones," not just the 4th?
4. These sit alongside the still-open items from the main session dump doc (parameter-neighborhood sensitivity, liquidity/slippage-tier breakdown, concurrent-position capital capacity, the split-adjustment data-quality question, and the IWM-200MA regime filter).

---

## 6. Where the code and data live

- New reusable scripts: `ep_backtest/noise_benchmark.py` (Test 1) and `ep_backtest/walkforward_fold.py` (Test 2, reusable for any train/test year split).
- Test 1 outputs: `outputs/robustness/` (noise trade log, candidate noise dates, bootstrap results).
- Test 2 outputs: `outputs/walkforward/fold2_train2021/` and `outputs/walkforward/fold3_train2023/` (screen1/screen2 trade logs, strategy summaries, winner test results). The original fold (train≤2019) lives directly under `outputs/walkforward/` from the earlier session.
