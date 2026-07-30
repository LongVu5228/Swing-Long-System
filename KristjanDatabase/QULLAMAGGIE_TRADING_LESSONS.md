# Qullamaggie Trading Lessons: A Synthesized Playbook

**Source:** Kristjan "Qullamaggie" Kullamägi's YouTube trading livestreams, distilled from transcripts.

**Coverage:** 2017-01-22 through 2023-12-15 — the complete channel history, organized into 10 topic sections rather than split by time period. Each section spans the full seven years internally: where a setup, rule, or piece of vocabulary changed or sharpened over time (e.g. the shift toward episodic pivots, sell-rule discipline getting stricter, position sizing at larger account scale), that evolution is folded directly into the relevant section's examples rather than isolated in a separate "later years" section — every specific claim is still tagged with the date(s) it actually comes from.

**Scale of the underlying data:**
- **588 videos** identified across the full channel history; **507 transcripts** successfully retrieved (~86% coverage — the rest had no captions available, were private/deleted, or were non-English). Retrieval used a two-stage pipeline: `youtube-transcript-api`/`yt-dlp` for the initial pass, then a paid third-party transcript API to get past YouTube's own IP-level rate limiting on the remainder.
- **~3.24 million words** (roughly 68MB) of raw caption text across those transcripts — at a rough ~1.3 tokens/word, on the order of **4-4.5 million tokens** of raw source material.
- **232,461 timestamped caption segments** indexed into a searchable local SQLite full-text database, independent of this document, for direct keyword lookup across the whole corpus.

**Compilation method:**
1. The transcript corpus was split chronologically into **27 batches**. Each batch was processed by a separate AI subagent that read its slice of raw transcripts directly and extracted discrete, dated, ticker-cited lessons into 10 fixed categories (setups, chart reading, risk management, psychology, mistakes, etc.), writing its own notes file rather than summarizing from memory.
2. That produced **~45,900 words** of structured intermediate notes — roughly a **70x compression** of the raw transcript text, with every claim still traceable back to a specific date/video.
3. This document is a second synthesis pass on top of those notes: deduplicating repeated principles across years, cross-referencing the same stock or lesson showing up in different sessions, and — through several rounds of review — going back to the original source transcripts to pull direct quotes, real named/dated trade examples, and clickable timestamped YouTube links for every claim, rather than relying on the paraphrased batch notes alone.
4. Net result: **~14,200 words**, meaning the entire multi-year video archive is represented here at roughly **1/230th** its original raw transcript length — compressed and cross-referenced by AI across dozens of separate reading and writing passes, not manually skimmed or written from memory.

This is a summary and paraphrase of his publicly stated views and trade narration on stream — not a verbatim transcript, and not financial advice.

---

## Table of Contents

1. [Entries & Setups](#1-entries--setups)
   - [1.1 The core setup — "high tide flag" / momentum breakout](#11-the-core-setup--high-tide-flag--momentum-breakout)
   - [1.2 Pocket pivots](#12-pocket-pivots)
   - [1.3 Episodic pivots (EPs) / earnings breakouts](#13-episodic-pivots-eps--earnings-breakouts)
   - [1.4 IPO breakouts](#14-ipo-breakouts)
   - [1.5 Parabolic shorts and parabolic longs (mean-reversion, multi-day)](#15-parabolic-shorts-and-parabolic-longs-mean-reversion-multi-day)
   - [1.6 Mean-reversion day trades](#16-mean-reversion-day-trades-distinct-from-the-multi-day-parabolic-setups-above)
   - [1.7 Weekly/monthly moving-average bounces (position trades)](#17-weeklymonthly-moving-average-bounces-position-trades)
   - [1.8 Commodity and cyclical stocks — the exception to "never buy dips"](#18-commodity-and-cyclical-stocks--the-exception-to-never-buy-dips)
   - [1.9 Failed-breakout resets](#19-failed-breakout-resets)
   - [1.10 Distressed and bankruptcy-catalyst bounces](#110-distressed-and-bankruptcy-catalyst-bounces)
   - [1.11 Sector sympathy and vehicle choice](#111-sector-sympathy-and-vehicle-choice)
   - [1.12 What he avoids](#112-what-he-avoids)
2. [Chart Reading & Technical Analysis](#2-chart-reading--technical-analysis)
   - [2.1 The minimal toolkit, and what he explicitly rejects](#21-the-minimal-toolkit-and-what-he-explicitly-rejects)
   - [2.2 The moving-average framework](#22-the-moving-average-framework)
   - [2.3 Frontside vs. backside](#23-frontside-vs-backside)
   - [2.4 Undercut-and-reclaim](#24-undercut-and-reclaim)
   - [2.5 Relative strength — the central read](#25-relative-strength--the-central-read)
   - [2.6 Volume as the second core input](#26-volume-as-the-second-core-input)
   - [2.7 "Resistance" is mostly a downtrend concept](#27-resistance-is-mostly-a-downtrend-concept)
   - [2.8 Multi-timeframe reading](#28-multi-timeframe-reading)
   - [2.9 ADR — measuring a stock's technical character](#29-adr--measuring-a-stocks-technical-character)
   - [2.10 Leveraged, proxy, and correlated instruments](#210-leveraged-proxy-and-correlated-instruments)
   - [2.11 Market-wide breadth and regime diagnostics](#211-market-wide-breadth-and-regime-diagnostics)
   - [2.12 Price leads fundamentals](#212-price-leads-fundamentals)
3. [Position Sizing & Risk Management](#3-position-sizing--risk-management)
   - [3.1 Risk per trade — the core percentage](#31-risk-per-trade--the-core-percentage)
   - [3.2 Position concentration limits](#32-position-concentration-limits)
   - [3.3 Asymmetric risk/reward — the whole game](#33-asymmetric-riskreward--the-whole-game)
   - [3.4 Starter positions vs. full-size entry — a real tension in his own rules](#34-starter-positions-vs-full-size-entry--a-real-tension-in-his-own-rules)
   - [3.5 Liquidity and borrow cost as sizing constraints](#35-liquidity-and-borrow-cost-as-sizing-constraints)
   - [3.6 Margin discipline — "deserved, not entitled"](#36-margin-discipline--deserved-not-entitled)
   - [3.7 Sizing stops to volatility (ADR-based stops)](#37-sizing-stops-to-volatility-adr-based-stops)
   - [3.8 The short side's structural asymmetry](#38-the-short-sides-structural-asymmetry)
   - [3.9 Studying historical blowups](#39-studying-historical-blowups)
   - [3.10 Portfolio-level risk — position count as a personal stress indicator](#310-portfolio-level-risk--position-count-as-a-personal-stress-indicator)
   - [3.11 Platform and broker redundancy](#311-platform-and-broker-redundancy)
   - [3.12 What he refuses to trade regardless of setup quality](#312-what-he-refuses-to-trade-regardless-of-setup-quality)
4. [Trade Management (Adds, Trims, Stops)](#4-trade-management-adds-trims-stops)
   - [4.1 The 3-to-5-day trim rule, and how it flexes with market conditions](#41-the-3-to-5-day-trim-rule-and-how-it-flexes-with-market-conditions)
   - [4.2 Default stop placement — the close, not the wick](#42-default-stop-placement--the-close-not-the-wick)
   - [4.3 Adding to winners — the mechanics of pyramiding into strength](#43-adding-to-winners--the-mechanics-of-pyramiding-into-strength)
   - [4.4 "You cannot outsmart the moving average" — the recurring self-critique](#44-you-cannot-outsmart-the-moving-average--the-recurring-self-critique)
   - [4.5 Deviating from the rules backfires — named casualties](#45-deviating-from-the-rules-backfires--named-casualties)
   - [4.6 Short-side exit mechanics — fundamentally different from longs](#46-short-side-exit-mechanics--fundamentally-different-from-longs)
   - [4.7 Willingness to re-enter after a stop-out](#47-willingness-to-re-enter-after-a-stop-out)
   - [4.8 Earnings-holding discipline](#48-earnings-holding-discipline)
   - [4.9 Fast/extreme movers need a faster trail](#49-fastextreme-movers-need-a-faster-trail)
   - [4.10 When overriding the rules is actually correct](#410-when-overriding-the-rules-is-actually-correct)
   - [4.11 Execution mechanics](#411-execution-mechanics)
5. [Profit Taking & Exit Strategy](#5-profit-taking--exit-strategy)
   - [5.1 "Let the stock tell you" — why fixed price targets get rejected almost universally](#51-let-the-stock-tell-you--why-fixed-price-targets-get-rejected-almost-universally)
   - [5.2 The core trade-off — sell a little too late, not a lot too early](#52-the-core-trade-off--sell-a-little-too-late-not-a-lot-too-early)
   - [5.3 Selling too early — the self-rated weak spot](#53-selling-too-early--the-self-rated-weak-spot)
   - [5.4 Defending large open profits actively](#54-defending-large-open-profits-actively)
   - [5.5 Home-run trading — the Pareto principle](#55-home-run-trading--the-pareto-principle)
   - [5.6 Exit mechanics change at size — "get out when I can, not when I want to"](#56-exit-mechanics-change-at-size--get-out-when-i-can-not-when-i-want-to)
   - [5.7 Trading price over opinion — the Tesla short-to-long flip](#57-trading-price-over-opinion--the-tesla-short-to-long-flip)
   - [5.8 Reframing losses against total account size](#58-reframing-losses-against-total-account-size)
   - [5.9 Exit style is a trade-off, not a universal rule](#59-exit-style-is-a-trade-off-not-a-universal-rule)
   - [5.10 "Silly season" runners — the trail that gives back too much](#510-silly-season-runners--the-trail-that-gives-back-too-much)
6. [Market Timing & Regime Reading](#6-market-timing--regime-reading)
   - [6.1 The two-regime framework — "easy dollar" vs. "hard penny"](#61-the-two-regime-framework--easy-dollar-vs-hard-penny)
   - [6.2 The hardest regime isn't a crash — it's chop](#62-the-hardest-regime-isnt-a-crash--its-chop)
   - [6.3 Reading breadth and correlation — the clearest regime-change signal](#63-reading-breadth-and-correlation--the-clearest-regime-change-signal)
   - [6.4 Case study: "the rug pull"](#64-case-study-the-rug-pull)
   - [6.5 The best time to buy breakouts — right after a correction resolves](#65-the-best-time-to-buy-breakouts--right-after-a-correction-resolves)
   - [6.6 Position count and personal exposure as a sentiment gauge](#66-position-count-and-personal-exposure-as-a-sentiment-gauge)
   - [6.7 Euphoria is a warning sign, not a green light](#67-euphoria-is-a-warning-sign-not-a-green-light)
   - [6.8 Historical base rates, cited to counter emotional extremes](#68-historical-base-rates-cited-to-counter-emotional-extremes)
   - [6.9 Ignoring macro, Fed policy, and news entirely](#69-ignoring-macro-fed-policy-and-news-entirely)
   - [6.10 Case study: the GameStop/meme-stock squeeze (January 2021)](#610-case-study-the-gamestopmeme-stock-squeeze-january-2021)
   - [6.11 Case study: the 2022 bear market](#611-case-study-the-2022-bear-market)
   - [6.12 Sitting out is a valid, even superior, strategy](#612-sitting-out-is-a-valid-even-superior-strategy)
7. [Watchlist & Stock Selection Criteria](#7-watchlist--stock-selection-criteria)
   - [7.1 The primary gate — ADR and dollar volume, before anything else](#71-the-primary-gate--adr-and-dollar-volume-before-anything-else)
   - [7.2 The actual scan mechanics — what the screens really look like](#72-the-actual-scan-mechanics--what-the-screens-really-look-like)
   - [7.3 Fundamentals as "fuel," never the trigger](#73-fundamentals-as-fuel-never-the-trigger)
   - [7.4 Institutional-quality names vs. pure pump stocks — knowing which bucket you're in](#74-institutional-quality-names-vs-pure-pump-stocks--knowing-which-bucket-youre-in)
   - [7.5 Proactive theme-building — watchlists made before the theme is obvious](#75-proactive-theme-building--watchlists-made-before-the-theme-is-obvious)
   - [7.6 "The shittier the stock, the bigger the move"](#76-the-shittier-the-stock-the-bigger-the-move)
   - [7.7 Real-name-brand backing as a credibility signal — and its limits](#77-real-name-brand-backing-as-a-credibility-signal--and-its-limits)
   - [7.8 What gets filtered out entirely](#78-what-gets-filtered-out-entirely)
   - [7.9 The liquidity test — placing a real test order](#79-the-liquidity-test--placing-a-real-test-order)
   - [7.10 "Our job is to be in the stocks other funds want"](#710-our-job-is-to-be-in-the-stocks-other-funds-want)
   - [7.11 A stock's "personality" — reading repeated stop-outs as a fit problem](#711-a-stocks-personality--reading-repeated-stop-outs-as-a-fit-problem)
   - [7.12 The Luckin Coffee fraud and its ripple effect on Chinese-ADR trust](#712-the-luckin-coffee-fraud-and-its-ripple-effect-on-chinese-adr-trust)
8. [Psychology & Mindset](#8-psychology--mindset)
   - [8.1 Emotion is not the enemy — channel it, don't suppress it](#81-emotion-is-not-the-enemy--channel-it-dont-suppress-it)
   - [8.2 Discipline over being right — "love your stops, not your dogs"](#82-discipline-over-being-right--love-your-stops-not-your-dogs)
   - [8.3 Patience and boredom tolerance as the central skill](#83-patience-and-boredom-tolerance-as-the-central-skill)
   - [8.4 Losses and drawdowns as the cost of doing business, not a personal failing](#84-losses-and-drawdowns-as-the-cost-of-doing-business-not-a-personal-failing)
   - [8.5 Reviewing and owning mistakes publicly, in real time](#85-reviewing-and-owning-mistakes-publicly-in-real-time)
   - [8.6 Complacency after success — danger peaks right after the easiest stretches](#86-complacency-after-success--danger-peaks-right-after-the-easiest-stretches)
   - [8.7 Real skill isn't transferable secondhand — borrowed ideas vs. earned conviction](#87-real-skill-isnt-transferable-secondhand--borrowed-ideas-vs-earned-conviction)
   - [8.8 "Psychology" problems are usually edge problems in disguise](#88-psychology-problems-are-usually-edge-problems-in-disguise)
   - [8.9 Extreme ownership — rejecting manipulation narratives and external blame](#89-extreme-ownership--rejecting-manipulation-narratives-and-external-blame)
   - [8.10 Chronic overtrading — his own most self-identified recurring leak](#810-chronic-overtrading--his-own-most-self-identified-recurring-leak)
   - [8.11 React, don't predict — trader vs. investor mindset](#811-react-dont-predict--trader-vs-investor-mindset)
   - [8.12 The origin story — blowing up the account early, and what actually changed](#812-the-origin-story--blowing-up-the-account-early-and-what-actually-changed)
9. [Common Mistakes / What Not To Do](#9-common-mistakes--what-not-to-do)
   - [9.1 Stubbornness — refusing to cut a loss, and fighting the tape](#91-stubbornness--refusing-to-cut-a-loss-and-fighting-the-tape)
   - [9.2 Chasing — buying a stock well past its actual breakout trigger](#92-chasing--buying-a-stock-well-past-its-actual-breakout-trigger)
   - [9.3 Buying breakouts in a choppy, non-trending market](#93-buying-breakouts-in-a-choppy-non-trending-market)
   - [9.4 Shorting too early, and the specific danger of day-one parabolic shorts](#94-shorting-too-early-and-the-specific-danger-of-day-one-parabolic-shorts)
   - [9.5 Holding through earnings or other binary catalysts without a plan](#95-holding-through-earnings-or-other-binary-catalysts-without-a-plan)
   - [9.6 Overriding predefined rules, and freezing under pressure](#96-overriding-predefined-rules-and-freezing-under-pressure)
   - [9.7 Options, CFDs, and forex — avoided almost entirely](#97-options-cfds-and-forex--avoided-almost-entirely)
   - [9.8 Fat-fingered execution — a chronic, accepted cost of trading size](#98-fat-fingered-execution--a-chronic-accepted-cost-of-trading-size)
   - [9.9 Ignoring liquidity and borrow constraints](#99-ignoring-liquidity-and-borrow-constraints)
   - [9.10 Following influencers, paid gurus, and copy-trading](#910-following-influencers-paid-gurus-and-copy-trading)
   - [9.11 Overtrading mediocre setups instead of waiting for genuinely tight ones](#911-overtrading-mediocre-setups-instead-of-waiting-for-genuinely-tight-ones)
   - [9.12 The opposite failure — hesitating on genuinely great setups](#912-the-opposite-failure--hesitating-on-genuinely-great-setups)
10. [Other Notable Lessons](#10-other-notable-lessons)
    - [10.1 Reading list and mentors — and the admission that none of it is original](#101-reading-list-and-mentors--and-the-admission-that-none-of-it-is-original)
    - [10.2 The core skill-building method — building a personal, decades-deep chart database](#102-the-core-skill-building-method--building-a-personal-decades-deep-chart-database)
    - [10.3 Day trading vs. swing/position trading — why the shift happens as an account scales](#103-day-trading-vs-swingposition-trading--why-the-shift-happens-as-an-account-scales)
    - [10.4 Markets are not zero-sum](#104-markets-are-not-zero-sum)
    - [10.5 News, politics, and macro treated as noise](#105-news-politics-and-macro-treated-as-noise)
    - [10.6 Tools and platforms, and how the stack evolved](#106-tools-and-platforms-and-how-the-stack-evolved)
    - [10.7 Realistic return expectations, benchmarked against real traders](#107-realistic-return-expectations-benchmarked-against-real-traders)
    - [10.8 Short selling — roughly half his profits, but a structurally harder game to scale](#108-short-selling--roughly-half-his-profits-but-a-structurally-harder-game-to-scale)
    - [10.9 The EP era compressed his actual trading day](#109-the-ep-era-compressed-his-actual-trading-day)
    - [10.10 Structural and tax adjustments at scale](#1010-structural-and-tax-adjustments-at-scale)
    - [10.11 Broker redundancy and commission structure as account insurance](#1011-broker-redundancy-and-commission-structure-as-account-insurance)
    - [10.12 The anti-scam rule, and trading in strong currencies](#1012-the-anti-scam-rule-and-trading-in-strong-currencies)

---

## 1. Entries & Setups

Kullamägi's own shorthand — "I only trade three setups" — is real and gets repeated almost every year from 2020 onward. But that's his teaching simplification, not the full picture of what actually shows up across 27 batches of live trade narration. In practice there are at least ten distinct, separately-named patterns he trades, each with its own specific rules, plus several vehicle- and context-specific variations layered on top. This section covers all of them, anchored to real trades with real tickers and numbers wherever the source material provides them.

**Citation format:** every example below is tagged with the video title, upload date, and — where the exact moment is known — a direct YouTube link with a timestamp, so you can jump straight to it and watch the original clip yourself. A core group of videos does most of the heavy lifting for this section, reused across multiple subsections:

- **"My setups, methodology, and how to build trading mastery"** — 2020-05-27 — https://www.youtube.com/watch?v=KciAjkEFA6s — a dedicated methodology stream he says viewers had been requesting from him for "way too long"; he finally walks through his core setups end to end using recent real trades.
- **"How to trade (and not to trade) insanity stocks. $BPTH $LFIN $DRYS $AQXP $KBIO $DGLY $VLTC"** — 2019-03-10 — https://www.youtube.com/watch?v=pNWdgezy2VA — a catalog of the most violent low-float squeezes he'd traded or watched over his career.
- **"Lack of good setups again"** — 2020-09-30 — https://www.youtube.com/watch?v=oKfvcX-S4M0
- **"EV Gold Rush!"** — 2021-01-12 — https://www.youtube.com/watch?v=46Dw3UTmKlA
- **"Great earnings breakouts"** — 2019-11-07 — https://www.youtube.com/watch?v=8uyENUhiW1c
- **"Seeing some big opportunities setting up"** — 2021-05-07 — https://www.youtube.com/watch?v=uFJDGcCzR3A — also the source for the commodity/cyclical framing and FCX/SMH walkthrough in 1.8, and the GBTC/MSTR vehicle-choice exchange in 1.11.

A second tier of videos supplies one or two specific examples each, used in a single subsection and cited inline there. Listed here by which subsection they feed, for reference:

| Used in | Example it supplies | Date | Link |
|---|---|---|---|
| 1.2 Pocket pivots | CrowdStrike (CRWD) walkthrough | 2021-05-26 | https://www.youtube.com/watch?v=A2gkEQC6O_Y |
| 1.2 Pocket pivots | TDOC pocket-pivot cross-reference | 2021-01-20 | https://www.youtube.com/watch?v=jCvLY7F8g80 |
| 1.2 Pocket pivots / vocabulary note | Pinterest (PINS) pocket pivot, and the VCP definition | 2021-01-21 | https://www.youtube.com/watch?v=D1NMXfSXpYk |
| 1.4 IPO breakouts | Day-one-risk caution | 2020-02-03 | https://www.youtube.com/watch?v=qmhLHCHRBnM |
| 1.4 IPO breakouts | "Why IPO breakouts" framing | 2021-06-09 | https://www.youtube.com/watch?v=gwoJzKevjeY |
| 1.3 Episodic pivots | 2023-era EP-dominance commentary | 2023-05-19 | https://www.youtube.com/watch?v=_y9Wo0eBP4A |
| 1.7 Weekly/monthly MA bounces | DQ weekly-chart rescue | 2021-01-25 | https://www.youtube.com/watch?v=dvZBux4ffy0 |
| 1.9 Failed-breakout resets | AMRS/EXEL false-breakout examples | 2021-02-05 | https://www.youtube.com/watch?v=FamRgrbApII |
| 1.9 Failed-breakout resets | False-breakout principle restated | 2021-03-19 | https://www.youtube.com/watch?v=7jPFXy_nrBE |
| 1.10 Distressed bounces | CCL distressed-bounce trade | 2020-04-17 | https://www.youtube.com/watch?v=SvTWDAao4pI |
| 1.11 Sector sympathy | Coronavirus-stock sympathy watchlist | 2020-02-26 | https://www.youtube.com/watch?v=e5Cc6XHg-7E |
| 1.11 Sector sympathy | Sympathy-play definition | 2020-09-29 | https://www.youtube.com/watch?v=JxOTlvGUSF0 |
| 1.12 What he avoids | Beyond Meat gap-chasing refusal | 2020-02-19 | https://www.youtube.com/watch?v=AG226y4hi1E |
| 1.12 What he avoids | GBTC hard-stop loss | 2020-06-02 | https://www.youtube.com/watch?v=uZFKiMA3M1I |
| Vocabulary note | Tennis ball action definition | 2021-05-20 | https://www.youtube.com/watch?v=Pde5BeC0JEk |

### 1.1 The core setup — "high tide flag" / momentum breakout

A stock makes a large initial momentum move, then pulls back or goes sideways and finds support on a rising moving average (the 10-day for the fastest stocks, 20-day for normal swings, 50-day for slower/large-cap names). It builds a series of higher lows, the daily range tightens noticeably, and it breaks out again on above-average volume. This single pattern — surf the moving average, tighten, break out — is the one he says is worth mastering above all others, and he finds it repeating across every year and every instrument he's traded. Entries trigger on a break of an "opening range" — the high or low of the first 1-minute, 5-minute, or 60-minute candle — with faster timeframes giving an earlier, tighter-stop entry that fails more often, and slower ones giving a later but more reliable one.

- **INO (Inovio Pharmaceuticals), short.** INO ran roughly 300% over four sessions on no real news — "just speculation, hype, or a pure pump" — then gapped up euphorically on day five and tanked. His entry wasn't guesswork: it pushed a little at the open, then took out its opening-range lows on the 15-minute chart (around $16.20 on the 60-minute chart that day, versus roughly $18 on the faster 1- and 5-minute charts — a reminder that "opening range" isn't one fixed number, it depends which timeframe you're using).
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=108s*
- **BLDP (Ballard Power), long.** A bull-flag breakout in the fuel-cell sector, which was "super hot" at the time — bought on the opening-range-high break around $10.40-10.50.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1645s*
- **FAS (triple-leveraged financial ETF), long.** Had been flagging off its lows, building a tight range over the prior week, then gapped up on high volume. He actually took a small loss on the first attempt — bought near the open, it faded, he got stopped — then re-bought once it took out the opening-range highs a little later; it ran straight up from there. A clean example of getting stopped and simply re-entering once the setup re-confirms, rather than abandoning it.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1673s*
- **SC (Sea Limited), long.** Bought on a flag break; the stock had "held up very well" during the COVID crash, then broke out of a small flag — he calls it "one of the fastest-growing stocks in the market right now."
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1471s*

**Tightness over volatility.** The single biggest visual "tell" separating a five-star setup from a mediocre one is how tight and narrow the price range is immediately before the breakout. "If it isn't tight, it's not right." Working through his scan live on **2020-09-30** ("Lack of good setups again"), this shows up as a running series of instant pass/fail verdicts:

- A stock referred to as "dvpr" gets a pass for "relentlessly building higher lows."
  - *2020-09-30, "Lack of good setups again", t=249s*
- GNC gets a nod for "tightening, looks good."
  - *2020-09-30, "Lack of good setups again", t=890s*
- A stock up five straight days with no base at all gets dismissed outright: "dude this thing is up five days in a row, where's the setup here."
  - *2020-09-30, "Lack of good setups again", t=864s*
- BLDP again, this time messy on the daily but "a big flag on a weekly" — a conditional yes specifically *because* the whole fuel-cell sector (PLUG, BE, BLDP together) is showing the same pattern at once.
  - *2020-09-30, "Lack of good setups again", t=1182s*

Putting the two clips together, the core setup is really a two-stage filter, not a single pattern. Stage one is structural — a stock has to actually be surfing a rising moving average with a series of higher lows (INO, BLDP, FAS, and SC in the walkthrough above all pass this test before he'll even consider them). Stage two is the live pass/fail scan — even a structurally valid base gets rejected instantly if the range in front of it isn't tight ("dude, this thing is up five days in a row, where's the setup here"), and a merely-decent chart gets upgraded from a pass to a genuine buy when the whole sector is confirming at once, as with the BLDP/fuel-cell pass. The FAS trade is the one that best shows what happens when the setup is *right* but the timing is off: he lost money on the first attempt at the open, took the stop without hesitation, and simply re-bought once the opening-range-high broke a second time — treating the failed first attempt as new information about the trigger, not as a reason to abandon the thesis.
### 1.2 Pocket pivots

A pocket pivot is a breakout that happens *inside* an existing base or range, rather than off a clean multi-week consolidation into brand-new territory — a stock with prior momentum pulls back to a major moving average, builds a small range there, then breaks that smaller range on higher volume, all while still technically inside its larger pattern. Unlike most of the other setups in this section, he actually spells this one out in full, twice, on two different named stocks — so there's a real "textbook example" to learn from here, not just a definition.

- **CrowdStrike (CRWD) — his own "picture perfect" example.** On **2021-05-26** a viewer pushes back that a current CRWD candle "doesn't look like a breakout," and he uses it as a teaching moment, pointing back at what had happened roughly two weeks earlier: "a stock with previous momentum that pulls back to one of the major moving averages, builds a little bit of a range, and then breaks out of that range — like, this was a picture perfect pocket pivot." Specifically: CRWD found support on its rising 100-day, started building higher lows, got tighter, then broke out of that small range on higher volume — "and look at it now, and now everyone's getting excited about this being a breakout... but if you want to make money in the markets, this is where you buy it." The point he's making live is pointed: by the time a pocket pivot looks like an obvious breakout to everyone else, the real entry already happened days earlier, inside the range.
  - *2021-05-26, "Some bigs moves starting!!", t=3213s*
- **A second CRWD moment, same video, restated even more plainly** after a follow-up question: "it's a breakout inside of a range — it's inside of a bigger range." He also adds an important scope note right after: "pocket pivots are for slower-moving stocks anyways, and you shouldn't be trading slower-moving stocks" — i.e., he considers this setup a secondary tool mainly relevant for larger/slower names, not something most of his (faster, higher-ADR-focused) audience should prioritize.
  - *2021-05-26, "Some bigs moves starting!!", t=3344s*
- **An unnamed stock compared directly to TDOC, 2021-01-20.** Looking at a slow-moving, choppy name that's been "surfing the 100-day for a while" and building higher lows, he calls it live: "this is called like a pocket pivot, it's a breakout that's inside of a base." He then draws a direct comparison to **TDOC (Teladoc)** — the same stock covered as an earnings-breakout example in section 1.3 — pointing out that when he originally bought TDOC, "it was the same thing, it was kind of building higher lows and kind of breaking out inside of its base... the word for it is a pocket pivot." This is a useful cross-reference: TDOC's entry, in his own retrospective framing, technically fits *both* labels (episodic pivot on the earnings gap itself, pocket pivot on the specific basing pattern that preceded it), which is a reminder that these category names describe the *chart mechanics* of an entry, not mutually exclusive boxes a stock has to fit into.
  - *2021-01-20, "Extended stocks breaking down! $MARA $RIOT $BNGO", t=2894s*
- **Pinterest (PINS), 2021-01-21.** Bought the day before: "had a little bit of a breakout, it's just been surfing this moving average — really nice. They had a little bit of a pocket pivot as it's called — like inside-range breakout." A smaller, quieter, less-narrated example than CRWD, but useful precisely because it shows the pattern at a more modest scale (his own words: "a little bit of a pocket pivot") rather than only the dramatic textbook case.
  - *2021-01-21, "Bitcoin nearing the 50-day! Major support?", t=479s*

Putting the CRWD walkthrough together with the TDOC/PINS examples, the pattern to actually watch for is: (1) a stock that already has real prior momentum, not a fresh unknown name; (2) a pullback to a major moving average (10-, 20-, 50-, or 100-day depending on the stock's speed) rather than a full multi-week reset; (3) a small, tight range forming right at that average; (4) a breakout of *that small range* on above-average volume — which will often look, to an outside observer scrolling past days later, like "just a continuation move," not a real entry point. His own framing is that the pocket pivot buyer is intentionally getting in before the move looks obvious to everyone else, which is also exactly why it's a harder setup to trust in real time than a clean breakout from a big, visually obvious base.

### 1.3 Episodic pivots (EPs) / earnings breakouts

His favorite swing setup, and by 2023 his dominant one: a company beats earnings/revenue estimates substantially, raises guidance, gaps up double digits on volume, and trades its entire average daily volume within the first 5-15 minutes — all while breaking out of a multi-month sideways base.

- **TDOC (Teladoc).** A good earnings beat on both EPS and revenue, a gap up on heavy volume, breaking out of what he calls a "multi-year range" on the weekly chart after building higher lows for over a year. Ran about 160% over the following months — he admits he sold around $105 and the stock roughly doubled from there without him.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=919s*
- **"ICHR."** The fundamental side of the setup made explicit: EPS growth of 261% year-over-year, revenue growth of 49%, with forward estimates calling for another 156% growth in the current year and 54% the year after — the kind of acceleration he wants to justify treating an earnings gap as holdable rather than a one-day pop.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=989s*
- **DXCM (Dexcom), weekly chart.** Higher lows for six months inside a year-long range, then a gap up on good earnings that "more than doubled" the stock. Separately, during the COVID crash it had "a big shakeout" and bounced perfectly off its rising 200-day — the same name illustrating both the earnings-breakout entry and (later) a weekly-moving-average bounce.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1067s*
- **PDD (Pinduoduo).** He didn't buy the earnings gap itself, but bought once the stock bounced off its rising 20-day coming out of a long range — "very good earnings numbers," clean breakout, straight up since.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1424s*
- **An unnamed 2023 EP, bought three separate times.** By 2023 EPs had become his dominant setup, and he narrates one live where conviction survived two straight stop-outs: "I bought it initially on the EP day... it just went straight down, got stopped out. I think I got stopped out twice on it — I re-bought it, they stopped me out, then I re-bought it yesterday. So we're taking two losses on it so far, we'll see, hopefully third time's the charm." His justification for re-entering after two losses on the same name rather than moving on: "it's all about risk/reward — this thing, once it gets going, [can] double in a flash, it's already done it once this year." In the same session he states the broader regime shift plainly: "breakouts haven't really been working the past 18 months — what has been working is EPs. EPs have been working pretty decently... the breakout [setup] has been choppy."
  - *2023-05-19, "Episodic Pivots, Kenny boy and old times", t=1951s*

The precise definition sharpens over the years: by 2021 a gap on already-"known" news doesn't count, the surprise has to be genuine; by 2022 a good EP has to gap *over* all its declining moving averages into clean air, and he states flatly he never trades EPs on the short side; by 2023 the entry window compresses to the first 3-10 minutes, with a simple mechanical template (buy the first 5-minute candle's high, stop at low of day, size under ~1% of average daily volume) he recommends to smaller traders as a starting point. The 2023 EP example above also shows a real exception to his usual "cut it and move on" instinct (see 1.12): repeated stop-outs on the *same* EP name are tolerated specifically when the risk/reward on a fresh trigger stays wide enough — a double-or-nothing payoff profile is worth re-underwriting even after two losses, in a way a slower, tighter setup wouldn't be.

### 1.4 IPO breakouts

Recent IPOs get treated as their own category, favored specifically because a young stock has no multi-year trading history to create overhead resistance — technical analysis, in his words, "works very well" on them precisely because there's no old baggage on the chart.

- **Livongo, long.** Bought a couple of months after IPO, following roughly six months of sideways action post-listing (the stock was "kind of expensive" and the market wasn't yet sure it could sustain its growth). It guided higher and gapped up on volume — not huge volume, but the pattern looked clean enough to take. Still holding roughly half his shares at the time of the video; calls IPO breakouts "super powerful."
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1249s*
- **Fastly, long.** Bought a couple of weeks after IPO, after it had gone sideways since listing. A report showing 38% revenue growth (pre-profitability) with good guidance triggered by far the largest volume day since the IPO — the stock traded its full ~1.5 million share average daily volume within the first 5-10 minutes, which made it "pretty obvious early" this was a real move, not a fade.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1294s*
- **Why he actively favors the category, stated directly.** Scanning a batch of recent listings live, including one he flags simply as "another recent IPO": "recent IPO breakouts can be very powerful, since they're usually low float, and many times they're kind of exciting businesses — it's the first time you get to buy a certain business... I really like IPO breakouts." He draws the contrast explicitly against a long-established, already-widely-owned name in the same breath — an old company can only be "discovered" once by the market, while every recent IPO is still going through that discovery phase, which is what produces the low-float, high-institutional-demand combination he's hunting for.
  - *2021-06-09, "Yuuuge opportunities", t=1719s*
- **General framing, 2021 batches (not individually timestamped — synthesized from batch notes, not a single sourced clip).** Recent IPOs get more benefit of the doubt than established stocks on a merely mediocre-looking setup, because scarcity value — a small, fresh float institutions haven't finished accumulating — can drive a big move on its own.
- **The counterweight: day-one risk still applies.** The same freshness that makes IPOs attractive also means an IPO's actual first trading day is exactly the kind of "day-one" move he generally won't chase, on any stock, regardless of category. His broader rule, learned from his own early day-trading years: "when I used to day trade, now I almost never [trade it] day one — day one is where accounts are broken, I learned it the hard way, trust me on that one." Applied to IPOs specifically, this is why both Livongo and Fastly above were bought only after months of post-listing sideways action, never on the actual debut — the "no overhead resistance" edge is real, but it doesn't kick in until the stock has had time to build an actual range for him to trade around.
  - *2020-02-03, "Coronavirus stocks choppiest theme pumps I've ever seen.", t=2346s*

### 1.5 Parabolic shorts and parabolic longs (mean-reversion, multi-day)

A stock up 200-1000%+ in a short span is a short candidate — but never on day one or two of the move. He waits for day three or later, when the first real technical weakness appears (a failed opening range, a failed VWAP reclaim, a break of the rising 60-minute moving averages).

- **MRNA (Moderna), short.** The stock was already up roughly 500% over six months — a huge move for a large-cap — on COVID-vaccine speculation, then put out data that was "decent," but from only eight patients, which he calls "kind of irrelevant" as a real catalyst. He was stalking it for a short and believes he took (and lost on) an early attempt at the opening-range lows before it worked; late in the day the stock built a tight range, tested VWAP, failed to reclaim it, broke down, and faded roughly 70% over the following four to five sessions: "you don't randomly short them... you wait for them to actually start going lower... you wait for weakness."
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=284s*
- **GBTC (Grayscale Bitcoin Trust), long — the mirror of the same pattern.** The stock had already run hundreds of percent, then fell nearly 70% over four sessions, gapped down hard on the fourth day, put in a small washout below the open — and then reclaimed VWAP and opening-range lows on that same day. That reclaim was his long trigger; the stock bounced roughly 110% in the following two days. "Such a perfect trade," he says, because it gave him both a textbook short (the top) and a textbook parabolic long (the bottom) within the same multi-week cycle in the same instrument.
  - *recounted, 2020-05-27, "My setups, methodology, and how to build trading mastery", describing a December 2017 trade, t=598s*

For how violent and how *fast* these setups can be at the extreme end, his **2019-03-10** video ("How to trade (and not to trade) insanity stocks") is more instructive than any single well-behaved example. He runs through several low-float micro-cap squeezes from his own trading history:

- A cryptocurrency-mania-era micro-cap stock that he didn't trade at all but watched run up **380% in one session, then another 430% the next** — roughly 2,600% combined in two days.
  - *2019-03-10, "How to trade (and not to trade) insanity stocks. $BPTH $LFIN $DRYS $AQXP $KBIO $DGLY $VLTC", t=95s*
- **KBIO**, which he shorted going into a Friday afternoon believing it was an easy short on a bankrupt shell of a company — he wanted to be flat before a personal trip to Spain, only partially covered before the close, stepped away, and came back to find the stock up 500% against him, roughly 20-25% of his total account. He covered into that spike; the stock then more than doubled again from where he'd covered, and kept running into the following week. "A sloppy trade from my side" — the explicit rule drawn from it: never short a low-float micro-cap unless it's *already* up thousands of percent, and even then, only once it's confirmed backside — never while it's still climbing.
  - *2019-03-10, "How to trade (and not to trade) insanity stocks. $BPTH $LFIN $DRYS $AQXP $KBIO $DGLY $VLTC", t=266s*
- An earlier trade, referenced only by ticker fragments in the stream (a stock he calls "QXB" in the moment), where he shorted into strength, added repeatedly as it kept rising, and ultimately covered a loss of **$86,000 — about a quarter of his account at the time** — in roughly an hour, before going to a barbecue with friends in what he dryly describes as "not my best mood."
  - *2019-03-10, "How to trade (and not to trade) insanity stocks. $BPTH $LFIN $DRYS $AQXP $KBIO $DGLY $VLTC", t=172s*
- **DGLY**, a body-camera stock from the 2014 "police body cam" news cycle, which ran about 720% from a roughly $4 starting price — smaller in percentage terms than the others, but notable because he'd had no locate to short it and was structurally prevented from taking the trade, which in hindsight he's glad about.
  - *2019-03-10, "How to trade (and not to trade) insanity stocks. $BPTH $LFIN $DRYS $AQXP $KBIO $DGLY $VLTC", t=508s*
- **VLTC**, a slower-burning squeeze that stretched over roughly three weeks rather than a single violent session, ultimately running about 2,500% — he shorted it "every single day" during the move and, by his own account, lost money on most of those individual attempts even though the broader thesis (it would eventually crack) was directionally correct.
  - *2019-03-10, "How to trade (and not to trade) insanity stocks. $BPTH $LFIN $DRYS $AQXP $KBIO $DGLY $VLTC", t=582s*

The throughline across all of these: sizing and timing discipline matter far more than being directionally right. Being early — or simply unlucky with timing, as in the KBIO trade — on a genuine low-float squeeze can cost 20-25% of an account in well under an hour, no matter how "obviously" overvalued or fundamentally broken the underlying company is.

### 1.6 Mean-reversion day trades (distinct from the multi-day parabolic setups above)

Separately from the multi-day parabolic short/long swing setups, he names a faster, shorter-hold "mean-reversion" pattern as one of his favorite pure day-trading setups: a stock that's had a sharp multi-day run (either direction) reverses hard, often on day three of the move, and the trade is over within the same session or the next. It's the same underlying logic as the parabolic trades — fade extension, don't anticipate it — but compressed into hours instead of days.

- **EMPH, short.** An overextended trade: one leg up, second leg up, third, fourth, fifth leg up — on the third day it took out opening-range lows, that's where he shorted it. On the 60-minute chart you can see a multi-hour range and then a clean breakdown of that range; his risk on the entry was "like a dollar." Still short roughly half size at the time of the video, just trailing it.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1543s*
- **VACS, short.** Another overextended name, up roughly 1,400% in a few months. First signs of trouble came on the first day it merely went sideways instead of extending further: it showed weakness, took out opening-range lows, tested VWAP, failed at VWAP — that's where he shorted it, around $56.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1351s*
- **The $125,000 loss.** Not every mean-reversion attempt works: he narrates a short where he was "a little bit too aggressive too early," and it cost him $125,000 — then compounds the mistake by failing to re-add once the stock actually did show the weakness he'd originally been looking for. The stock fell 30-40% anyway without him fully positioned for it; he ends up buying the eventual bounce off the 60-minute chart instead, closing the loop from a losing short into a working long on the same name, but explicitly flags the sequence as "not a super clean setup, just a variation" rather than a trade to be proud of.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1612s*

The throughline: the day-trade version of mean-reversion punishes being early far more severely and far faster than the slower multi-day parabolic version, because there's no multi-day cushion to absorb a bad entry — EMPH and VACS worked because he waited for a specific break (opening-range lows, a failed VWAP test); the $125K loss happened because he didn't.

### 1.7 Weekly/monthly moving-average bounces (position trades)

Separate from his main fast-breakout style, he names bounces off major weekly or monthly moving averages (the 20-, 50-, 100-, or 150-week) as their own, slower, lower-risk setup meant for patient position trades held over months rather than days or weeks. This is the setup he reaches for on names too large or too slow to fit his usual opening-range/daily-chart mechanics — and, separately, it's the reason he insists on checking more than one chart timeframe before writing a stock off.

- **Unnamed stock.** Bounces cleanly off its rising 200-day moving average right after announcing a mixed securities offering. On stream: "not my type of setup, but this is one type of setup that you can swing and position trade." The risk/reward he gives is telling — "maybe ten dollars... to make a hundred or two hundred," a much wider dollar stop than his usual tight opening-range entries, justified because the target move (a bounce off a major long-term average) tends to be proportionally larger too. He explicitly tells viewers this is exactly the kind of pattern to log in a personal "market winner study" even when it isn't their own primary style.
  - *2021-01-12, "EV Gold Rush!", t=203s*
- **DXCM.** During the COVID crash the stock had "a big shakeout" and bounced perfectly off its rising 200-day moving average — the same name that also produced one of his cleanest earnings-breakout trades (see 1.3), illustrating that a single stock can hand a trader two completely different setup types at two different points in its life.
  - *2020-05-27, "My setups, methodology, and how to build trading mastery", t=1067s*
- **DQ (Daqo New Energy) — the weekly chart rescuing a setup the daily chart hid.** Explaining live why he'd bought a name that looked unremarkable on his usual daily chart: "it was a little bit choppy on the daily, it looked like [garbage] — but then you look at the weekly... wow, look at this flag. That's why I bought it, I looked at the weekly." By the time of this session he'd already sold, and the stock had run roughly 30% higher than his exit — "that's the story of my life" — but the setup call itself was validated by the follow-through. He generalizes the lesson immediately afterward, unprompted: "those patterns happen on the weekly, they happen on the 60-minute, they happen on the daily, they happen on the 5-minute — choose your time frame." The specific implication for slower/larger names: a chart that looks genuinely bad on the daily is not the same thing as a bad setup — it may just be the wrong timeframe to be looking at it on.
  - *2021-01-25, "Did I trade $100M worth of stocks today? YES!", t=3730s*

### 1.8 Commodity and cyclical stocks — the exception to "never buy dips"

Commodity, cyclical, and foreign-listed names get an explicit carve-out from his usual "only buy confirmed breakouts, never buy dips" rule — these stocks tend to be choppier than growth stocks and their breakouts fail more often, so the better entry is a pullback or an undercut-and-reclaim of a rising moving average.

- **The rule, explained directly, with historical context.** Asked essentially why he treats this group differently: "commodities are tricky — they're better to buy when they just test the rising moving average, like the 50 or the 100... growth stocks are usually better to buy off breakouts, especially the leading ones, but not necessarily commodities, they don't work as well as breakouts." He backs this with a specific historical reference rather than just a personal hunch: during the 2003-2007 commodity bull market (and again 2009-2011), commodities were the market's leading sector for years, "and they were generally kind of tricky — many of the leading names, you had to buy them when they bounced off a rising moving average."
  - *2021-05-07, "Seeing some big opportunities setting up", t=3978s*
- **Semiconductor allocation.** He'd built roughly **half his account** across a cluster of semiconductor names (AMAT, LRCX, SOXL, and TSM) about a month earlier, and by this session the bases on those names "look even better" even as software/growth EPs from the same period were failing and fading below their declining moving averages ("look at all these so-called earnings gappers... they're all fading now").
  - *2021-05-07, "Seeing some big opportunities setting up", t=1831s*
- **SQM (lithium).** Repeatedly tries to break out, gets slammed back down, builds another higher low — an annoying, frustrating pattern to watch live, but one he explicitly doesn't abandon: "the thing is, once it goes, it's gonna make a big move... it wouldn't surprise me if it doubles." Patience through repeated failed breakouts is treated as normal for this asset class, not a reason to give up on the name.
  - *2021-05-07, "Seeing some big opportunities setting up", t=1896s*
- **FCX (Freeport-McMoRan) and SMH — the undercut-and-reclaim rule applied live to two different names.** Earlier in the same session FCX gets dismissed in passing as "a mess," and he explains exactly why later on: "that's why I passed on FCX — I wasn't trusting this breakout. Now it's obviously working, but... these types of setups where it undercuts a key moving average and then reclaims, these types of setups work really well for commodity names." In the same breath he points at SMH (the semiconductor ETF) as the pattern actually working the way he wants it to: it had undercut its rising 100-day, tested it again, reclaimed, and by this point was reclaiming its 50-day too — "it's showing strength, it doesn't want to go down." The contrast is the whole lesson in miniature: FCX's breakout worked anyway this one time, but he still passed on it *at the moment of the breakout itself*, because a straight breakout on a commodity name is a bet against the base rate, even when it occasionally pays off.
  - *2021-05-07, "Seeing some big opportunities setting up", t=1507s and t=4044s*

### 1.9 Failed-breakout resets

A breakout that fails and falls back into its base isn't a dead setup — it can rebuild into something better than the original attempt. The mechanism: a second attempt, built on the higher low left behind by the first failed move, often has better risk/reward than the original breakout did, because the range is now tighter and the weak hands from the first failed move have already been shaken out. This isn't a throwaway line he says once — he restates the same principle, essentially word for word, on at least two separate occasions months apart, and demonstrates it live on named stocks both times.

- **VSTO.** The stock had "a random breakup" a couple of weeks earlier that faded because of broader market weakness, not anything wrong with the stock itself. Rather than writing it off, he kept watching it: "it tried to break out, it failed, pulled back... kept building higher lows and now the setup is even better." Stated as a general principle in the same breath: "your failed breakouts can be very valuable."
  - *2020-09-30, "Lack of good setups again", t=1348s*
- **AMRS (Amyris), long.** Walking through his watchlist live, he flags a "false go" from a couple of weeks earlier: on the 60-minute chart, AMRS tried to break its range, failed, and "fell back into the base" — but instead of breaking down further, it kept building higher lows from there. His verdict, watching the second setup form: "sometimes false breakouts can give you a much stronger setup later on... embrace false breakouts." Directly next to it on the same scan, he flags **EXEL**, a stock he'd taken a loss on the day before, as a live example of the same pattern still in progress — pulled back, still building higher lows, "looks really good... if it closes like this."
  - *2021-02-05, "Many people experiencing their first pump and dump! Learn how to not be a sucker in the stock market", t=4833s*
- **The rule restated, six weeks later.** Unprompted, scanning a fresh batch of charts: "false breakouts can give you valuable information — if a failed breakout goes lower and puts in a higher low, that's valuable information, of course it's part of the base." Coming from an entirely different session with different stocks on screen, this is the closest thing to a formal definition he gives the pattern — confirmation that VSTO and AMRS weren't one-off exceptions but examples of a rule he actively scans for.
  - *2021-03-19, "Crypto setups for next week!", t=232s*

Put together, the checklist for treating a failed breakout as a *setup* rather than a *rejection* is: (1) the failure has to be attributable to something external (market weakness, a broad pullback) rather than stock-specific bad news; (2) price has to fall back and hold *above* the prior low, not just retest and break it — that higher low is the entire signal; (3) the range that forms on the second attempt should be visibly tighter than the first. When those three line up, he treats the second breakout as higher-probability than the first one would have been, not merely an acceptable consolation entry.

### 1.10 Distressed and bankruptcy-catalyst bounces

A specific fundamental trigger — a restructuring announcement, a new debt deal, or a partnership — on a company that otherwise looks left for dead can produce moves of 100-300%+ off the lows very quickly, with fundamentals treated as essentially irrelevant to the trade.

- **MNK (Mallinckrodt).** Announced it was hiring a restructuring firm and bounced **170% in a few days** starting from that announcement — a stock that looked like it was heading to bankruptcy instead finding its low on the news that it was formally addressing its debt.
  - *2019-11-07, "Great earnings breakouts", t=666s*
- **CHK (Chesapeake Energy), "a couple of years back."** Beaten down for years, a big gap down, then the identical trigger — a restructuring-firm hire — turned out to be the exact low, followed by a bounce of **over 300% over the following months**.
  - *recounted, 2019-11-07, "Great earnings breakouts", t=673s*
- **CCL (Carnival Cruise Line), long — the same logic applied live, with an honest losing outcome.** During the COVID crash, cruise and travel names were among the most distressed stocks on the market, and he picked CCL specifically out of that group rather than a peer: "I'm gonna buy CCL, opening-range breakout on CCL, because this is the one that raised money — so they're not likely to go bankrupt. They were the ones that raised money, and the Saudi [sovereign wealth fund] has a stake in it — not that it means anything, but..." The company-specific backing (a completed capital raise, a strategic sovereign stake) was the explicit reason he chose CCL over other similarly-battered cruise and airline names on his screen that session. The trade itself didn't work — CCL failed to follow through and he was stopped out within the same session — which is included here deliberately: the fundamental backing changes *which* distressed name he's willing to risk capital on, it doesn't guarantee that specific attempt pays off.
  - *2020-04-17, "Sell the news coming in the markets?", t=2472s*
- **The pattern itself.** He explicitly names the restructuring-announcement trigger "kind of an interesting phenomenon" worth watching for on its own: the trigger isn't a chart pattern at all, it's a specific category of corporate announcement (hiring restructuring help, completing a financing, landing a strategic investor) that reliably marks psychological capitulation in a name everyone has already given up on. Within a weak group of similarly distressed names, he prefers whichever one has some additional company-specific backing over peers without it — CCL over other cruise names, MNK and CHK once the restructuring news hit — but as CCL shows, that selection edge narrows the odds, it doesn't remove the normal risk of any single swing trade failing.

### 1.11 Sector sympathy and vehicle choice

A "sympathy play" is his own term for a stock that runs mainly because a related name in its sector got news, not because of anything specific to the stock itself — and it changes how strictly he applies his usual setup criteria.

- **The definition, stated plainly.** Asked live what a sympathy play actually is: "it's a stock that runs up in sympathy to another stock — if a stock in a sector gets [news], [traders] try to pump all the others in the same sector." He immediately adds a filter on top of the definition, though: he doesn't watch news on every individual stock, so what he actually screens for is sympathy names moving *on volume*, not just any stock with a vague thematic connection — dismissing one candidate on-screen outright because it was "up two thousand percent" only due to a reverse split, not real trading interest.
  - *2020-09-29, "Major indinces getting rejected at supply levels...", t=2157s*
- **APT vs. "N&VC" — quality filter within a sympathy group.** During the early-2020 coronavirus-stock mania he kept a dedicated watchlist of 33 separate "corona stocks," but drew a hard line inside that group between names with a real underlying business and pure pump vehicles: "there's a huge difference between this and something like N&VC, which is literally — their only business is selling stock, their only business is pumping this thing up." His long holding, a face-mask maker (referred to on stream as "APT"), was by contrast "a real business, profitable, they even have a buyback in place... they're working day and night to get their face masks produced" — and he explicitly names it as the one stock in the entire 33-name sympathy watchlist he expected to actually make money from the story rather than from share issuance. Same logic as the fuel-cell trio below: the sector tailwind gets you interested, but he still separates the legitimate businesses from the paper from there.
  - *2020-02-26, "Covid / Corona stocks going nuts! I'm long a bunch!", t=1854s*
- **Sector sympathy loosens the setup bar.** An individual chart doesn't need to be textbook-perfect when the whole sector is moving together — a merely-good 3.5-star setup can act like a 5-star one when several related names are breaking out at once. The fuel-cell trio from 1.1 (PLUG, BE, BLDP) is the clearest recurring example: a messy-looking BLDP chart gets a conditional pass specifically because all three names are moving together.
  - *2020-08-10 and 2020-11-04, cited from batch notes rather than a single re-verified clip*
- **GBTC vs. MSTR — vehicle choice within a single theme.** Asked live whether he'd consider MSTR (MicroStrategy) as an alternative Bitcoin proxy to GBTC, his answer is a clean illustration of how he actually decides between two vehicles chasing the same underlying story: "yes, there's only one problem — MSTR looks like [garbage] and GBTC looks like a piece of diamond." Vehicle choice is entirely subordinate to which chart shows the cleaner setup, not brand loyalty to one proxy.
  - *2021-05-07, "Seeing some big opportunities setting up", t=1603s*
- **The underlying-first rule.** He never trades a leveraged or proxy instrument "blindly" — before a leveraged small-cap fund he checks the Russell first; before a leveraged silver fund he checks silver first; before GBTC he checks Bitcoin itself first. The leveraged or proxy vehicle only gets traded once the underlying confirms; it's a bigger-ADR wrapper around a thesis that has to hold up on its own chart first.
  - *2021-05-07, "Seeing some big opportunities setting up", t=1608s*

Reading these together, sympathy and vehicle choice are really the same skill applied at two different scales: within a sector, he wants the sympathy names that are moving on real volume and (ideally) have a real underlying business, not just thematic noise; within a single story playable through multiple instruments, he wants whichever specific chart is cleanest, checked against its own unlevered underlying first. The sector or theme gets you looking; the individual chart still has to earn the trade.

### 1.12 What he avoids

Several of the clearest lessons in this category come from his own admitted mistakes, narrated live in the moment rather than cleaned up in hindsight — which makes them more useful, not less, since he shows the actual cost in dollars.

- **Dip-buying, self-admitted weakness.** "I pretty much never buy dips, I'm a very bad dip buyer" — he only buys confirmed breakouts, not anticipated bottoms. Notably, this is a direct contrast with the commodity/cyclical exception in 1.8, where dip-buying is the *correct* approach for that asset class — the rule is style- and asset-specific, not universal.
  - *2020-01-27 / 2020-01-31, cited from batch notes*
- **Chasing a gap — Beyond Meat, live refusal.** Watching Beyond Meat gap up the morning after its actual breakout day, he states the rule as it happens rather than after the fact: "Beyond Meat is up today, it's gapping up, and there is no entry here — in my opinion, the entry was yesterday. Today it's just chasing." He passes on the name entirely and spends the same minutes queuing sell orders into strength on positions he already owns, rather than adding a new one at a worse price.
  - *2020-02-19, "Tesla going to $1500?", t=485s*
- **Frontside shorting.** A stock still riding rising moving averages, not yet extended, is dangerous to short and has nearly hurt his account before; the two legitimate times to short are after a genuine parabolic move, or once a stock has confirmed "backside" (trading below declining averages).
  - *general principle, recurring across many videos rather than one clip*
- **Day-one shorting.** He rarely shorts a stock on its very first big move day, preferring to see how it digests first — a rule that shows up directly in the VACS and INO examples above (1.1, 1.6), both of which he waited on rather than shorting immediately.
- **Skipping the hard stop on a volatile position — GBTC, the $38K lesson.** He'd bought roughly $35,000 of GBTC on the long side, running only a mental stop rather than a resting hard-stop order — his normal practice, since hard stops mostly go in only once price nears the actual exit level. Bitcoin then gapped violently against him intraday with no warning: "oh my god, what the hell is that candle... I was gonna risk like 10, 12K on it, I'm down like 36K on it now, instantly." He closed the full position for a $38,000 loss against a planned risk of $10-12K, then drew the lesson explicitly, still live on stream: "if I had a hard stop in, I would have probably saved myself fifteen thousand or so, maybe even more... you hesitate, you die — or at least you won't die, but your account will." He didn't rewrite his whole stop-management approach afterward (he still runs mental stops as a rule), but the episode is his own on-camera case study for why a genuinely violent, low-liquidity-hours move is exactly the scenario a mental stop fails to protect against.
  - *2020-06-02, "Best swing trading market ever. Just activate autopilpot and all bad news gets absorbed", t=5949s*

The common thread across all five: none of these are abstract risk-management platitudes — each is a rule he can point to a specific dollar figure for, either money he lost breaking it (GBTC) or money he avoided losing by following it (Beyond Meat). Avoidance, for him, isn't a personality trait, it's a running tally of what specific mistakes have actually cost him.

**A note on vocabulary.** Two borrowed terms recur often enough across the years to be worth defining directly, in his own words, rather than left implicit in the examples above:

- **VCP.** Asked to explain the term live, he deflates the jargon on the spot: "for a tightening range, it's another VCP — you know what it stands for? Volatility Constriction Pattern, okay, I call it higher lows, that's it. Tight-in, tightening range, that's what VCP is." This is the same mechanic underlying nearly every entry in 1.1 and 1.2 above — he's explicit that it's not a separate concept from "surfing a moving average and tightening," just a name other traders (Mark Minervini) put on it first.
  - *2021-01-21, "Bitcoin nearing the 50-day! Major support?", t=3069s*
- **Tennis ball action.** Also credited directly to Minervini: a stock that gets pushed down and immediately pops back up, like a tennis ball hitting the ground. Watching SC (Sea Limited — the same stock from the 1.1 breakout example, at an earlier point in its move) hold up during a broad pullback: "this is strong, this is like Mark Minervini says, tennis ball action — you try to push it below water and it just pops back up. This is what you want to see, this is what relative strength looks like." He uses it specifically as a live diagnostic for genuine relative strength, distinct from a stock merely being "up" — the tell is *how fast and how completely* it recovers after being pushed down, not just that it eventually does.
  - *2021-05-20, "Indices strong, BUT running into key moving averages", t=3354s*

---

## 2. Chart Reading & Technical Analysis

His technical toolkit is deliberately minimal: price, volume, and a handful of moving averages — nothing more. He explicitly and repeatedly dismisses most of what's commonly taught as technical analysis as noise, arguing price and volume already contain whatever information those indicators are trying to extract, and that stacking more indicators just produces more contradictory signals. He estimates 90-95% of technical analysis as commonly taught is "garbage." This section covers the actual reading skills underneath that minimalism — not what he trades (Section 1), but how he looks at a chart to decide anything at all.

**Citation format:** same as Section 1 — video title, upload date, and timestamp where known, in a sub-bullet under each example.

### 2.1 The minimal toolkit, and what he explicitly rejects

His stated toolkit is price, volume, and moving averages — "the less you use, the better." Everything else he names gets rejected by name, with a specific reason, not just a vague "I keep it simple."

- **RSI, MACD, Bollinger Bands.** "No, I'm not using RSI or MACD, I don't think there is any value in those... they don't buy on price, and I already have moving averages and price on my chart, so I don't need an indicator to tell me something I already see. I don't use Bollinger Bands either." On RSI specifically, he singles out why it fails him on the long side: "RSI on the downside can be useful, but on the upside — the best stocks are overbought most of the time, so RSI is an indicator that doesn't give any value when things go up. Study any big move in the stock market and it's gonna be above RSI 90 for a big part of its move — so it's just totally worthless as an overbought indicator."
  - *2020-02-25, "Now is the time to stalk for RELATIVE STRENGTH", t=3436s*
- **Level 2 and time-and-sales.** "I don't really look at Level 2, only when I'm about to enter an order — I briefly look at it just to see the spread. Otherwise, no, I really couldn't give a [damn] about it. It's just all algos trading back and forth, I don't think there is an edge there... there's absolutely no edge in looking at Level 2 or time-and-sales" — for the liquid momentum names he trades, at least. He carves out one honest exception: Level 2 can matter on micro-caps where a single actor is visibly pushing the stock, but calls it "totally pointless" for anything else in his universe.
  - *2020-05-13, "Finally about to get a base building period", t=2085s*
- **"Volume Buzz" (TC2000's projected-volume tool).** Watching a stock front-load half its daily volume into the first 10 minutes, he explains live why the tool's projection is actively misleading: "Volume Buzz is a very flawed indicator... it looks at [the early volume] and thinks it's gonna keep trading this type of volume for the rest of the day, but that's not really true — if you look at the volume, it's just going lower, it's just declining. So it's definitely not gonna trade 50 million, it probably won't even trade 30 million. Volume Buzz in TC2000 is very flawed, it doesn't show you a realistic picture — it's based on fantasy, unfortunately, like a lot of indicators are. You have to understand what they're actually showing." Notably, he still keeps it visible on his own charts despite the warning — a reminder that "I have it on my screen" and "I trust it" aren't the same thing for him.
  - *2021-01-20, "Extended stocks breaking down! $MARA $RIOT $BNGO", t=6401s*
- **Institutional-ownership indicators.** Asked about MarketSmith's institutional-ownership indicator directly, he doesn't hedge: "I think it's pretty useless, it's a lagging indicator... that gets updated once per quarter. Look, it's very simple — take a stock like AMD: if it goes from 80 to 120, I bet there will be an increase in the amount of funds holding it. So how is it gonna help you that you find out three months later, 'oh, the institutional ownership went up, oh I should have bought it when it broke out'? It's such a useless indicator." In the same breath he draws a genuine distinction rather than rejecting everything wholesale: he calls MarketSmith's separate RS (relative strength) *line* "very useful," just redundant for him personally — "you don't need it because you can see it yourself" on the raw chart.
  - *2021-10-14, t=1902s*
- **Head-and-shoulders and classic chart-pattern naming.** A viewer flags that LAC (Lithium Americas) "looks like a head and shoulders." His answer is two words — "I don't care" — followed by the general rule: "head and shoulders is one of the least reliable patterns out there, one of the most useless patterns." His own favorites, named in the same breath, are the "bat formation" and the high tide flag (1.1) — chart shapes he trusts precisely because they're really just moving-average-and-tightness mechanics wearing a name, not classic technical-analysis textbook shapes.
  - *2021-12-15, t=95s*

Reading all five together, the pattern in what gets rejected isn't "complexity" per se — it's anything that either (a) restates information already visible in price and moving averages, just with extra lag or noise layered on top, or (b) makes a forward-looking claim (Volume Buzz's volume projection, a head-and-shoulders' implied reversal) that isn't actually supported by how the specific instrument behaves. His own summary line for the whole category: **90-95% of technical analysis as commonly taught is "garbage."**
  - *2020-06-02, "Best swing trading market ever. Just activate autopilpot and all bad news gets absorbed"*

### 2.2 The moving-average framework

On daily charts: the 10-, 20-, 50-, 100-, and 200-day simple moving averages. On the 60-minute chart: 10, 20, and sometimes 65-period exponential moving averages. Which average a stock "obeys" is itself informative — but the framework is less about the exact numbers than most people assume.

- **SHOP vs. ROKU — "surfing" as the visible footprint of real demand.** Comparing two leading stocks live on the same session: Shopify, down on the day, still gets called a leader — "it's still acting good even though it's down on the day... this is what institutional stocks do, they pull back and then buyers come in on the dip, this is why you get these higher lows — those are signs that there's demand for the stock." He immediately contrasts it with Roku, which had stopped building higher lows: "this thing is not building higher lows anymore, it's just in a sideways channel — this is not a leading stock, the 10 and 20 are now sloping down, it's lost its short-term momentum, it probably needs some news or something to get moving again." Same toolkit (10-day, 20-day), same market session, opposite verdicts — the moving averages themselves don't say anything; whether price is finding orderly support on them versus drifting sideways below them is the actual read.
  - *2020-08-19, t=2380s*
- **The exact period barely matters — stacking timeframes does.** In a genuinely funny/deliberate demonstration, he sets a moving average to 69 specifically to prove a point: "it doesn't matter what [expletive] moving average you're using — the point is, use some shorter moving average, then a mid-term, then a little bit of a longer term, right, that's the point. Doesn't matter if you use the 10, 15, or 7 — it doesn't matter, guys, it doesn't [expletive] matter. Doesn't matter if you use the 50 or the 60 — the point is have a shorter term, have a little bit of a longer term, and then another little bit longer term." The system is the relationship between a fast, a medium, and a slow average — not the specific numbers chosen for each.
  - *2022-02-08, t=2278s*
- **"Tennis ball action" — Sea Limited vs. Tesla, side by side, in the same session.** Naming the Minervini concept live while comparing two charts: "Tesla is starting to move again, it's just running into the declining 10-day and still below the 20 — very weak bounce, compared to some of the strong stocks. Like SC [Sea Limited] — this is strong, this is like Mark Minervini says, tennis ball action, you try to push it below water and it just pops back up. This is what you want to see, this is what relative strength looks like — and it's actually above all the moving averages." Same market, same session, two stocks testing the same kind of support — one obeys its averages cleanly and snaps back, the other struggles underneath a declining one, and the difference is legible at a glance once you know what to look for.
  - *2021-05-20, t=3354s*

Put together: the moving-average framework isn't a fixed set of magic numbers, it's a three-tier speed structure (fast/medium/slow) applied consistently, read by whether price is *respecting* the tiers (SHOP, SC) or has broken the relationship between them (ROKU, Tesla in the same clip) — which speed tier a given stock respects is itself the signal of how "institutional" versus "retail-only" its current move actually is. "Tennis ball action" is really just a memorable name for the same underlying mechanic as SHOP's higher lows in the first example — buyers stepping in fast enough at a moving average that the dip barely registers before price is back above it.

### 2.3 Frontside vs. backside

This is his primary chart-reading gate for short-side risk, and — unusually for this document — he explains it partly through his own scar tissue rather than just as an abstract rule.

- **Why it matters: an admitted near-blowup.** Asked about a stock that looks tempting to short while still climbing: "it's an important concept to understand, because I lost so much money shorting frontside — I've almost blown up several [accounts] by shorting frontside. These are really important concepts to understand: why do you get a real parabolic, or you short the backside." Frontside shorting isn't framed as a beginner mistake he's warning others away from in the abstract — it's a mistake he's made repeatedly and expensively himself.
  - *2020-07-02, t=868s*
- **The precise definition, given live.** Asked to define the term directly: "backside is when the moving averages that were previously support become resistance — the 10 and the 20 EMAs and the 65 EMA on the 60-minute charts." Nothing more exotic than that — it's a support/resistance role-reversal read on the same handful of averages from 2.2, not a separate indicator.
  - *2020-12-30, t=3130s*
- **The rule enforced live, in real time, against pressure to short early.** A viewer pushes to short a name that's merely gone sideways for two days after a run. His refusal is immediate and stated as a hard rule, not a judgment call: "no, if you short it now you're gonna blow up sooner or later, this is a horrible idea — you either wait for a parabolic or you wait for backside, neither of those criteria are present right now, this thing could go straight to 100... don't touch it here, don't even look at it today, there's no point." The stock sitting quietly is precisely the state that's hardest to read as "safe" and easiest to short prematurely — which is exactly why he calls it out on stream instead of letting it pass.
  - *2020-12-30, t=3082s*
- **The confirmation moment, narrated live on a real position.** Watching a name he's already short flip states in real time: "it's now kind of backside — it's below VWAP, these moving averages are starting to slope down, and it's building lower highs — so far so good." The three conditions arrive together on the chart (below VWAP, sloping-down averages, lower highs), and only once they do does he treat the short as validated rather than merely hoped-for.
  - *2020-12-09, t=5267s*

The rule in one line: there are exactly two states he'll short from — a confirmed, extended parabolic (1.5) or confirmed backside (moving averages flipped to resistance, price below VWAP, lower highs forming) — and everything in between, no matter how "toppy" a stock looks, is frontside and off-limits. This is the same underlying mechanic as 1.12's "day-one shorting" and "frontside shorting" avoidances, just described here from the chart-reading side rather than the trade-avoidance side.

### 2.4 Undercut-and-reclaim

- **FMC (FMC Corporation), long — the clean version.** Scrolling his own portfolio for live examples: "if you get an undercut of a previous low that gets bought up immediately in an uptrend, that's a bullish sign, that's very bullish — FMC, this is one... I was long, it had a big, big dip, it undercut the rising 20-day, but it immediately got bought back up — that's a bullish sign, that's one I'd mainly point to." A second stock in the same portfolio scroll: "this thing had a big rally, undercut the 10-day here, and it immediately got bought back up, closed above the range, above the 10-day — those kinds of things happen all the time."
  - *2020-07-02, t=4019s*
- **The rule, generalized, with the one condition that makes it work.** "If you have a stock in an uptrend, you get an undercut of the wall of the rising 10 or 20, or sometimes the 50-day moving averages, and it reclaims quickly — that's a simple-ish sign. But the key is it has to be *in an uptrend*, it can't be some random stock." He immediately gives a second worked example on the same principle: a stock that "had a big run, went sideways, had a pullback below the 10 and 20-day, but reclaimed immediately — that's a sign of strength."
  - *same clip, t=4071s*
- **The honest limitation — he admits he hasn't fully solved the entry mechanics.** Pushed on how to actually *trade* this pattern rather than just recognize it after the fact: "the problem I see is you don't know if it's gonna be an undercut or if it's gonna be a legit breakdown — you don't know until after it's happened. That's the problem with the setup: where do you put your stop, where's your entry? I haven't figured out how to trade that setup." This is a rare moment where he flags a pattern he trusts as *real* (it shows up "all the time") but doesn't yet have a clean, repeatable entry trigger for — recognizing the tell on a chart after the fact is easier than trading it live.
  - *same clip, t=4122s*
- **A single market scan where the pattern shows up four separate times.** Scrolling his watchlist during a broad-market bottoming attempt: "a lot of big pullbacks to the major moving averages, some of them are showing some bottoming action — the ones that had big pullbacks but are still holding their uptrends, building higher lows, many of them have had undercuts of major moving averages, undercuts and reclaims — so there's a lot of positive signs going on." He names them as he scrolls: JD undercutting its 200-day and reclaiming, BEAM undercutting and reclaiming its 100-day ("look how nicely, undercut, reclaimed the next day"), XBI producing "a beautiful reversal, undercut and reclaim," and IBB bouncing cleanly off its 200-day in the same session. He immediately caveats the whole scan, consistent with the honest limitation above: "again, it doesn't mean anything yet." Four unrelated tickers producing the identical tell in the same session is offered as evidence the pattern is structural, not a coincidence he noticed on one chart.
  - *2021-03-30, t=5650s, t=5589s, t=8360s, t=8369s*

The reverse version — a failed breakdown through resistance followed by an immediate strong reclaim — gets the identical read on the bearish-to-bullish side, and both directions share the same core requirement: the undercut has to happen against an established trend (up or down) for the reclaim to mean anything. On a directionless, random stock, the same wiggle is just noise.

### 2.5 Relative strength — the central read

Constantly comparing a stock's behavior to its index, sector peers, or a correlated instrument is core to nearly every decision he makes — but the read only works under specific conditions, which he's careful to spell out rather than apply blindly.

- **BILI and LVGO — "the stock is literally yelling in your face."** During a two-session, market-wide selloff, he points to what a genuine leader does differently: "what did Billy [BILI] do? It tried to go lower on Thursday, on the big red down day — couldn't [break down], found support on the rising 20-day. On Friday, when the markets kept going down, this thing actually broke out — this is where I bought it... that's relative strength, the stock is literally yelling in your face, 'I want to go higher.' All you have to do is listen." He names a second stock doing the same thing in the same session — Livongo, "another one that was literally yelling in everyone's faces," already tripled in a few months and still finding buyers on red days.
  - *2020-06-19, t=2377s*
- **ZOOM — the nuance most people get wrong.** A viewer flags Zoom as a short candidate specifically *because* it's down on a day when other tech names are green. He corrects the read live, and in doing so states the actual rule: "when a stock is in the middle of a range, relative strength or relative weakness don't really mean much... I don't think you can look at relative strength or relative weakness unless it's over many, many days." Applied to Zoom specifically: "you've got to look at the trend of the stock — it's just building higher lows, it's just building a base. If it breaks out, it's gonna go straight up... it's too early to call it weak unless it fails this series of higher lows and fails the rising 10-day — then it could get interesting for a potential short. But right now it's one of the strongest stocks, really." One red day against a green tape is not the same signal as multiple sessions of genuine divergence.
  - *2020-05-20, t=3690s*
- **"Down days are golden" — a market-wide uptrend used as a stock-picking filter, not a reason to panic.** Watching most of his own portfolio hold up during a broad-market wobble: "most of my stocks are showing relative strength, not all of them, but most — so instead of panicking and thinking the market will go to zero, this is the time when you spot the opportunity. When a market is in a big uptrend, their down days — that's when big money is made, just by stalking the strong ones, the market will tell you the stocks that want to go up." He restates it later in the same session as a near-mantra: "these down days are golden, the down days will tell you which of your stocks are weak and which ones are not — it's a gift."
  - *2020-06-24, t=1201s, t=1649s*
- **NVDA and AMD, October 2021 — relative strength as a discovery tool, not just a confirmation one.** Explaining, nearly two years later, how he actually found one of the biggest trades of his career: "if you see a market pullback and you see a trending stock holding up much better, that's a powerful sign — that's one of the ways the funds kind of draw the charts for us. It's how I found Nvidia back in October [2021] — AMD and Nvidia, back in mid-October 2021, huge relative strength, and AMD, this one actually broke out one day before the market... I traded one of them, I think it was AMD, because it broke out the day before, and then Nvidia broke out this day here." The relative-strength read wasn't used here to confirm a stock he already liked — it was the entire method by which the two names first got flagged, ahead of a market-wide move that hadn't happened yet.
  - *2023-05-19, t=2861s*

Put together, the rule has a load-bearing condition most people skip: relative strength/weakness is a real signal only against a *moving* market (a clear up day or down day for the index) and only when it persists — a single day, or a stock sitting in the middle of an undecided range, tells you close to nothing. The BILI/LVGO and NVDA/AMD reads worked because they held up across multiple sessions against a falling or choppy tape; the Zoom read would have been a mistake because it was one green-market day against a stock that was simply consolidating, not actually diverging. Read across all four examples, relative strength functions as both a confirmation tool on stocks already on the watchlist (BILI, LVGO) and a discovery tool for finding the next leader before the broader market moves (NVDA, AMD) — the same read, pointed in two different directions depending on whether the stock is already known or not.

### 2.6 Volume as the second core input

Judged by dollar volume (price × shares traded), never raw share count — a low-priced, high-share-volume stock can be far less liquid in the way that actually matters than a high-priced, low-share-volume one.

- **GME, and the $400,000 lesson in why the distinction is real money, not trivia.** Watching GME weaken during the meme-stock unwind, he flags something share-volume alone would miss: "it's also like — dollar volume, not only has the share volume gone down, the dollar volume has cupped by 95-plus. If you look at the share volume, it's been going down, right — but if you look at the dollar volume, it's gone down even more, because the price has gone down that much too. Look at the peak day versus yesterday: the dollar volume is down 97 [percent] from when it topped, versus yesterday — but the share volume is down less, share volume is down 92." He then connects the read directly to his own money: "yeah, it's typical for these types of [names], it's so hard to trade — that's why I lost $400,000 on it. I did a little bit more size than I should have, I had an enormous slippage on that thing — I probably had $100,000 in slippage both in and out, total." The dollar-volume collapse wasn't an academic distinction here; it was the direct cause of a six-figure slippage bill on a stock he was already directionally right about.
  - *2021-02-12, t=4061s*
- **Declining volume on a pullback read as bullish, not a warning sign.** Watching a basket of cannabis names pull back on visibly lighter volume: "the declining volume, it's a good thing — the market can still go up on lower volume, going down on low volume is bullish. This whole bull market the past ten years has been mostly on low volume, so that's just normal." The instinct to treat shrinking volume during a pullback as a bad sign gets the mechanism backwards — light volume on the way down means sellers are thin, which is exactly what a healthy pullback inside an uptrend is supposed to look like.
  - *2020-04-27, t=2597s*

The two readings work together rather than in tension: light volume is a *good* sign during a pullback (sellers are scarce, the GME collapse in dollar volume was itself a symptom of buyers disappearing entirely, not a healthy quiet period) but a *bad* sign if it persists into what should be a breakout day. The volume read that pairs with both: a sideways base that trades on progressively lighter volume, followed by a breakout day on a clear volume spike, is the ideal signature — it says a stock quietly ran out of sellers before it ran out of buyers. A breakout on unremarkable or declining volume gets far less trust, regardless of how clean the chart pattern looks on price alone, and a stock whose dollar volume is collapsing the way GME's did is a stock whose liquidity can no longer be trusted at size, independent of which direction the thesis points.

### 2.7 "Resistance" is mostly a downtrend concept

- **Netflix and Apple — the receipts.** Making the case on real charts rather than as an abstract opinion: "forget about that word resistance — you only need to be concerned about the word support, if you're swing trading on the long side. There's no such thing as resistance." Pulling up Netflix's monthly chart: "look at the declines on this stock — how many times has this stock been down like 70%? Look at all this so-called resistance that was created here — the stock should never have gone up there, because there was so much resistance... but turns out it was all imaginary, there was no resistance, the stock went straight up." Same exercise on Apple's 2018 selloff: "look at all this resistance that was created here, but turns out there was no resistance — all you had to do was follow good setups. You can get that word out of your vocabulary. If the stock has momentum and a good setup, that's all you need to care about."
  - *2020-10-12, t=2872s*
- **The honest qualifier — "support" isn't fully real either.** Immediately after, unprompted, he narrows his own claim rather than overselling it: "support is kind of imaginary too, to some extent — except for the leading momentum stocks, that's why I use this 10/20/50/100-day moving average, because they've worked for 100 years... but yeah, a lot of support is imaginary too — I see a lot of people draw some random lines and call it support and resistance, and there's just nothing there." The moving-average framework (2.2) isn't exempt from his own skepticism about drawn lines — it's specifically *because* it's a systematic, tested reference rather than a hand-drawn line that he trusts it.
  - *same clip, t=3139s*
- **The sharper rule, stated directly on a live position.** Asked about a level on a stock he currently owns: "I'm not a big believer in resistance unless it's something that's downtrending — I'm more a believer in ranges. The only time I use the word resistance is when something's [downtrending] — on the way down, both the 20 and the 50 have been acting as resistance, so that's only when things are in a downtrend do I use the word resistance. But something like this, that I bought — I don't see this as resistance, this is not resistance, it's a range. There is no resistance on a stock or ETF that's about to hit all-time highs."
  - *2021-04-30, t=1849s*
- **Why a "range" isn't a static wall — repeated tests make the eventual break more likely, not less.** Watching a stock fail repeatedly at the same level: "it's been trying to break out of this range over and over again, and eventually it's gonna succeed, and when it succeeds there's gonna be a big move... the more times a breakout level or support level is tested, the higher the probability of an eventual break — that's my observation." This directly inverts the popular assumption that a level gets "stronger" each time it holds; in his framing, repeated tests are attrition against the level, not confirmation of it.
  - *2019-10-24, t=3373s*

The four together give a precise, non-hand-wavy rule: "resistance" is a real, useful word only when a moving average has already flipped from support to resistance in a confirmed downtrend (2.3's backside) — everywhere else, what looks like a ceiling on a chart is just a range waiting to be broken, and each additional failed attempt makes the eventual break more likely rather than proving the ceiling is real. The two named large-cap examples show it breaking almost every time history gets checked.

### 2.8 Multi-timeframe reading

- **Top-down confirmation, demonstrated live.** Checking whether a setup is real, he walks through the exact sequence rather than just eyeballing one chart: "have you checked the tick chart? Does it have higher lows on a tick chart too? Let's look at the tick chart... no, it's actually building lower highs and lower lows on a tick chart. Nope — nothing there, guys. You always have to confirm: you have to look at a daily chart, the weekly chart, and *then* you confirm the trade on a tick chart. If you don't see it on a tick chart, there's no trade, it's over." A setup that looks valid on the daily but fails on the finest available timeframe doesn't get a pass for "probably still working" — all three have to agree.
  - *2022-01-12, t=2124s*
- **GME and the 1-minute chart he hates but sometimes needs.** He's explicit that his default is *not* the 1-minute chart: "I hate trading really on the one minute chart... but these types of stocks, you kind of have to — they're so fast. GME has an ADR of 2,450[%], it's insane — one tick could be a 5% move, could be a 10% move. So out of the gate I usually trade these under one minute, and I hate trading only one minute, I really do." He gives the specific reason a session later, as an honest self-critique rather than a tidy rule: "you need to wait for an area that makes sense, where you can have a set risk/reward... this is what many people do, especially the ones [glued to] the one-minute chart — they just... I was this way too in the beginning, I kept taking these small losses and they kind of compounded, and then when I nailed the move, I was just making bad losses — it's just stupid." The fastest chart isn't avoided out of purism; it's avoided because it produces exactly this pattern of small, frequent, compounding losses even when the larger directional call is right.
  - *2021-01-25, t=2355s and t=4993s*
- **Linear vs. logarithmic — a deliberate, situational choice, not a fixed preference.** Explaining why he's on a linear (arithmetic) chart for a stock that's already up a lot: "log scale makes it hard to see the short-term, in my opinion — I think it's easier to see recent price action [on linear]. I don't care about the price action [from a year ago] — I already know the stock is up a lot, I want a higher resolution on what's happened recently. If I switch to a logarithmic chart, I can't even see what's happening in the past few months." He then flags the exact opposite case, unprompted: "but then there are stocks that are really beaten down — then I do it the other way around, I use the logarithmic chart sometimes to see a higher resolution of what's happened recently." The choice of chart type itself is read as a tool matched to what you're trying to see, not a fixed setting.
  - *2020-10-12, t=3196s*

The common thread: no single timeframe or chart type is trusted in isolation. A setup needs the daily and weekly to agree before he'll even look at an entry trigger, the entry trigger itself gets read on whatever timeframe the stock's own speed demands (60-minute for normal names, 1-minute only when ADR forces it), and even the axis scaling gets chosen based on which few months of price action actually matter for the decision in front of him.

### 2.9 ADR — measuring a stock's technical character

Average Daily Range (a stock's typical daily percentage move) is a distinct, purpose-built measurement — not a byproduct of the moving-average framework, and not to be confused with the signals that actually decide whether a chart is *good*.

- **The definition, stated precisely.** Asked what ADR actually tells you: "ADR is no representation of relative strength, it's just a representation of volatility in percent." He draws this line deliberately, right after passing on a setup that looked fine otherwise — a high ADR doesn't make a mediocre chart tradeable, and a low ADR doesn't make a strong chart weak. It answers exactly one question: how much does this thing typically move.
  - *2021-03-10, t=4044s*
- **DraftKings vs. a slow mover — why the number matters practically.** Comparing two names side by side on his scan: "this is a fast-moving stock, something like this — ADR 13.8 — versus something like this, ADR 2.6. This is the type of stock you want to trade, high ADR — that's how you're gonna build your accounts." Earlier in the same session he dismisses a name outright on the same basis: "Jefferies has very low ADR, it's a slow mover — focus on higher ADR stocks."
  - *2020-12-11, t=3057s*
- **Five named tickers, ranked by ADR, in one breath.** Making the case for security selection with real numbers rather than a general preference: "[this name is] too slow, it's not a great day-trading stock, it's not a great swing-trading stock, it's a very slow name — ADR is 2.4 percent, that's the average daily range, compared to something like Tesla, that's at 4.2 percent, or Shopify, that's at 4.9 percent — you want stocks with high ADRs. Microsoft is a very, very slow name, I don't think it's a great trading stock at all... look for example at something like Nikola, ADR is at 20.8% — that's like eight times higher than Microsoft, that's a huge difference... Apple, even slower, 2.2% ADR — these are not trading stocks." He closes the point with the underlying logic: "security selection is very important in this game, you want the fastest-moving, most liquid names when you trade, and cut all the random stocks out."
  - *2020-06-18, t=1356s, t=1402s*
- **ADR selects the stock; a separate range measurement sizes the stop.** Explaining why he passed on an otherwise interesting setup: "if the price change on the day is more than the average true range, I'm not gonna do the trade — if my stop cannot be more than the average range, [it] skews up the risk/reward. And if you look at something like the EP, I don't count the gap, the gap doesn't matter." ADR answers "is this stock worth trading at all," while this daily-range check answers a narrower question on a specific entry — "is today's move already too big to place a sane stop against" — and the two get applied at different stages of the same decision.
  - *2020-11-25, t=6216s*

ADR functions as a pure speed filter, sitting logically upstream of everything else in this section: it doesn't tell you whether a stock is trending (2.2), whether it's frontside or backside (2.3), or whether it has relative strength (2.5) — it just tells you whether the stock is fast enough to be worth analyzing with those tools at all. The eight-times gap between Nikola (20.8%) and Microsoft (2.4%) is the same distinction as DraftKings (13.8%) versus a 2.6%-ADR name — a low-ADR name can still technically satisfy every other rule in this section and still get passed on simply for being too slow to move an account (see 1.1's "trading stocks" vs. "investing stocks" distinction, and Section 7's liquidity/volatility screening criteria for how this feeds into stock selection). The daily-range-vs-stop check is the same measurement family applied downstream, once a trade is already being considered — see 3.7 for how this becomes a full ADR-based stop-sizing rule.

### 2.10 Leveraged, proxy, and correlated instruments

- **TQQQ read off QQQ, not itself — and a real result attached to getting it right.** Explaining why he wouldn't chart-read a triple-leveraged Nasdaq ETF directly: "you can't look to do moving averages on TQQ, really — you have to look at QQQ, and the Qs didn't really bounce off the 100-day... you can't really TA TQQ that way, it's a triple ETF, you have to look at the main one — in this case it's QQQ, the unlevered one." He then narrates what that read was worth in practice, during a multi-day market correction shorted almost entirely off opening-range-low triggers on TQQ and Tesla: "the first four or five days of this correction I made a lot of money on the short side — I probably made like a million and a half or more between TQQ and Tesla, probably two million. I also gave back like half a million on my longs that I was still holding." The unlevered-underlying rule isn't just theoretically cleaner — it's the read that produced a seven-figure result on the specific trade being described.
  - *2020-09-22, "Leaders leading", t=626s and t=2722s*
- **Three proxy pairs, named back to back, as a standing rule rather than a one-off.** Asked directly whether he checks the underlying before trading a leveraged or proxy wrapper: "when I trade the triple-leveraged [instruments], I always look at the unlevered instrument first, that's what guides me — like GBTC, I'm not trading this thing blindly, I'm looking at Bitcoin first. Same thing with HEQ, I'm looking at what does silver look like — or if I trade TNA, I'm like, okay, what does Russell look like." Three completely different asset classes (crypto, precious metals, small-cap equities), same rule applied to each without exception.
  - *2021-05-07, t=1635s*
- **The same rule enforced live, mid-trade, on TNA specifically.** Scanning during an active TNA position: "you can't look at TNA, you have to look at Russell — this is the one you have to look at, the moving average in TNA is irrelevant. Russell tried to come out [of a range], couldn't reclaim the 50-day, now it's right back on it." The instruction isn't abstract policy here — it's the actual chart he's using, in real time, to manage a real position in the wrapper.
  - *2021-05-25, t=2627s*
- **VWAP — the one tool he trusts without fully understanding it.** Distinct from the leveraged-ETF read, VWAP is his key intraday pivot on extended momentum names and on the short side specifically — failing to reclaim it is a short trigger, reclaiming and holding above it is bullish. He's on record admitting he doesn't fully understand the underlying mechanism and simply trusts that it works, which is a notable exception to his usual insistence on understanding *why* a tool works (2.1) before relying on it.

The pattern across leveraged and proxy instruments: the wrapper (TQQQ, GBTC, HEQ, TNA, a leveraged silver ETF) is treated purely as a bigger-ADR way to express a directional view — the actual technical analysis happens on the unlevered underlying every time (Bitcoin, silver, the Russell), and the wrapper only gets traded once that underlying chart already confirms the setup. The rule holds across every asset class named in this subsection, which is what separates it from a single observation about one ETF — it's a general policy for reading any leveraged or derivative instrument.

### 2.11 Market-wide breadth and regime diagnostics

- **The mechanical index-level filter, and his own honest failure to follow it.** Explaining a regime-reading rule he calls simple and robust: "use the 10-day and the 20-day — if the 10-day is above the 20-day and both are trending higher, that's a very good market. If the 10-day gets below the 20-day, you should be a bit cautious; if the 10-day starts sloping down, you should be more cautious. If the 10-day slopes down, the 20-day slopes down, and the 10-day is below the 20-day, you should probably not buy any breakouts at all — that's a very simple, very robust market filter." He then admits, in the same breath, that he'd personally ignored it the day before, after being asked why he was 80% long into a weak session: "I wish I followed it, but yesterday I didn't follow it, so it is what it is — the 20-day had started sloping lower, the 10-day had already been sloping lower, and they'd actually crossed several sessions ago, and yet I still tried to buy some breakouts." The rule surviving his own violation of it, on stream, in real time, is a more convincing endorsement than if he'd only ever described it working.
  - *2020-10-30, t=6123s*
- **Which indices actually count — and which one famous one doesn't.** Asked directly about the S&P 500's relevance to his process: "the S&P is not correlated to anything, S&P 500 is irrelevant for the stocks we trade, doesn't matter... Nasdaq is much more relevant — Nasdaq, Russell, IWM, and COMPQ are much more relevant for you guys, and I also look at QQQ a lot because I trade a lot of QQQ stocks. But the only stock in the whole S&P 500 that's relevant — and that's Tesla — that's the only one that's relevant for us. The index itself is not relevant. Russell and the Nasdaq are what we should be looking at if you're doing market analysis." Reading market health off the wrong benchmark, in his framing, isn't a small error — it's tracking an index most of his actual universe barely correlates to.
  - *2020-12-22, t=1688s*
- **Stock-level breadth as its own diagnostic, independent of the index-level moving-average filter.** Reviewing a session where the major indices looked merely soft but individual leaders were quietly cracking: "you never want to see so many leading stocks breaking down at the same time — it's fine if there's only one here and there, but literally all of them broke below some major moving averages yesterday, so that's never a good sign, I really didn't like the price action yesterday." He treats this as a trigger serious enough to override his own mechanical process: "when you start seeing a lot of leading stocks breaking down at the same time, sometimes I override my sell rules and just get out before it's too late — you don't want to get scored in a bad sell-off." This is the same diagnostic later built into a full case study in 6.4 ("the rug pull") — narrowing individual-stock breadth beneath a still-calm-looking index is treated as a more reliable early warning than the index's own moving averages.
  - *2020-10-22, t=754s, t=2119s*

The three diagnostics point the same direction: regime reading isn't a vibe or a headline-driven judgment call. It's the identical moving-average framework from 2.2 applied one level up, to the *right* index rather than the most-quoted one; it's cross-checked against how many individual leaders (not just the index average) are actually breaking down at once; and the rule only has value if it's actually followed on the uncomfortable days, which is precisely when he admits to breaking it himself. Read together, the index-level filter and the stock-level breadth check are two independent alarms on the same underlying condition — a market that's rolling over — and the second one is explicitly treated as important enough to override the mechanical sell rules that govern everything else in this document.

### 2.12 Price leads fundamentals

This is the closest thing in the document to a stated thesis on *why* chart reading works at all, rather than just how to do it.

- **NVDA — asked and answered directly, six months before the report.** Put the question to him plainly: is it accurate to say technical price behavior is predictive of positive financial fundamentals? "Yes — we saw that with NVIDIA. NVIDIA has been going up for six months before this monster, monster earnings report — holy [expletive], the guidance was just absolutely massive. But the market sniffed it out a long time ago, right, you see it [in the chart first]." The chart wasn't a lagging confirmation of a good quarter that had already happened — the six months of price strength *preceded* the earnings beat that "explained" it in hindsight.
  - *2023-06-01, t=3159s*
- **The same NVDA report, from the other side — what the guidance actually turned out to be.** A week later, asked whether he weighs forward earnings estimates more heavily than trailing ones: "forward earnings is everything. The market is forward-looking, the market doesn't care about current earnings, the market doesn't give a [damn]... forward growth guidance — that's pretty much what the market participants, the analysts, [are pricing]." Applied directly to what had just happened: "[the stock] gapped up because they expect huge, huge revenue growth coming forward — that's what it's trading on, the future, not the past... it's not that Nvidia's earnings or revenue guidance was one of the best ever in the space — no, it's like the best one in the history of the world, maybe the company has never made that big of a raise in their revenue guidance." The two clips bracket the same event from both sides: price moved for six months on an expectation that hadn't been confirmed yet, and when the confirmation finally arrived, it turned out to be the most extreme version of that expectation he could recall ever seeing reported.
  - *2023-06-09, t=2503s, t=2593s*

The implication he draws from this, consistent with why fundamentals only ever function as secondary confirmation elsewhere in this document (1.3's EP earnings-growth checks, 1.10's restructuring-announcement trigger, 7.3's "earnings are fuel"): for a short-term swing trader, waiting for the fundamental story to be confirmed in a press release or earnings call means waiting for information the price has usually already reflected for months. This isn't presented as mysticism about markets being omniscient — the mechanism is simply that the analysts and institutions setting forward guidance and buying ahead of it are themselves the source of both the price move and the eventual confirmed number, so the chart and the fundamentals are two readings of the same underlying flow of informed capital, offset in time. Fundamentals matter more the longer the intended holding period — a position trader can afford to wait for confirmation — but for the setups that dominate this document, the technical read isn't a proxy for the fundamentals, it's frequently *ahead* of them, and the NVDA case is offered as the single cleanest example in the whole corpus of that lead time being made explicit, checked, and then verified after the fact.

---

## 3. Position Sizing & Risk Management

This is the mechanical backbone underneath everything in Section 1 — the same setups, traded with different sizing discipline, produce completely different survival odds. This section covers how much, not what or when.

**Citation format:** same as Sections 1 and 2 — video title, upload date, and timestamp where known, in a sub-bullet under each example.

### 3.1 Risk per trade — the core percentage

- **Asked directly, mid-stream, and answered with a real number.** "What percent of my account am I risking per trade? Around 0.3 to 0.5 percent or so." He immediately adds an honest, unprompted note about how that's changed over time rather than presenting it as a number that's always been true: "I'm taking smaller risks than I used to, but I'm going for like big multiples of risk on every trade I take."
  - *2020-07-30, t=7653s*

That 0.3-0.5% figure recurs across the corpus with minor variation (some sessions cite up to 1-2% on the rare highest-conviction setup), but the more consistent claim than any specific number is the one made explicitly here: the *percentage* shrank as the account grew, even as the dollar amounts it represents grew enormously — the process stayed mechanical and small-risk-per-trade rather than scaling risk tolerance up with account size. This is the foundation the asymmetric-reward math in 3.3 is built on: a small, consistent risk unit only works if the reward side is allowed to run into large multiples of it.

### 3.2 Position concentration limits

- **Tesla and a hypothetical Elon Musk heart attack — why 25% is the ceiling, stated vividly.** Explaining the hard cap directly: "don't put more than 25% of your account in any given stock. There's just no need — let's say you go long Tesla, you put 50% of your account in this thing, and the next day this thing breaks out, you put 50% of your money in this, or even worse, you put 100% of your money in this thing — and then overnight Elon Musk gets a heart attack and dies. This thing is going to be down 70%." He gives a second, more mundane version of the identical risk: "you put a big position in some micro-cap biotech stock, they have some bad news, it's gonna go down 90% overnight — you're dumb, your career is over. You don't have any career anymore in trading, at least." The specific catalyst doesn't matter (a founder's death, a biotech readout) — the lesson is that concentration risk is a single-event risk, and no setup quality justifies being wiped out by one headline.
  - *2020-08-05, t=7219s*
- **The "small account edge" — the same ceiling, deliberately relaxed for small accounts.** Responding to a viewer worried that low-float stocks are inherently too risky to concentrate in: "why would buying a solid setup on a low-float stock that then becomes a pump be risky? That's what we want — that's what sell rules are for, you're not gonna get stuck in a dump. Low floats are great... almost all of the high-ADR stocks are low floats, those are the only stocks you should be focused on." The logic: a small account can concentrate meaningfully in illiquid, high-ADR micro- and small-cap names capable of doubling or tripling in days — moves a large account can't access at meaningful size without moving the stock against itself. He frames this as a genuine structural advantage smaller traders have over him now, recommending they lean into concentration rather than imitate the wider diversification appropriate for a much larger account.
  - *2021-06-22, t=4637s*

The two examples aren't actually in conflict — they're the same rule at different account scales. The 25% ceiling is about *company-specific event risk* (a single headline that can hit any stock regardless of size), which caps concentration at any account size. The small-account edge is about *how many names* you spread that capped exposure across — a small account can run fewer, more concentrated positions than a large one because it can exit a single name's full size without moving the market against itself, while a large account is structurally pushed toward more positions at smaller weights each simply to get capital deployed at all.

### 3.3 Asymmetric risk/reward — the whole game

- **The 10x screening rule, and NVAX as the worked example.** Stating the filter he applies before taking any trade at all: "if I can't realistically think I can make say 10 times my initial risk, I'm probably not going to take the trade. Many of my swing longs I can make 20, 30, 50 times my initial risk." He immediately grounds it in a real, recent trade: "something like NVAX — bought it here, sold it like 60% higher a couple weeks later, I made easily ten times my initial risk on this thing." The 60% stock move and the "10x initial risk" framing are two different units on purpose — the position's percentage gain matters less than how many multiples of the *original defined risk* it represents.
  - *2020-07-30, t=7685s*
- **The data-driven case for why cutting losers matters more than picking winners.** Asked whether more data analysis could improve his edge, he says no — not because he hasn't done the analysis, but because he already has: "I've done some basic data analysis, and I found out that most of my losses — if I would just avoid five of my biggest losers every year, I would have made twice the amount of money, three times the amount of money. That's usually the first conclusion most traders reach once they start looking over their trades. That's the biggest one: avoid the big losers, cut the losers fast. If just one loser gets out of control, it can hurt you a lot." He adds the honest caveat that this insight alone isn't sufficient: "if you're doing a lot of things wrong, data analysis is not going to help you" — cutting losers fast is necessary but not a substitute for having a real edge in the first place.
  - *2021-02-25, t=5461s*

The math underneath both examples is the same one that makes a 25-30% win rate survivable (see 1.5, 1.6): a handful of trades running 10-50x their initial risk can carry a portfolio of mostly small, quickly-cut losses — but only if the losing side of that equation stays genuinely small and mechanical, which is exactly what the five-biggest-losers data point is measuring.

### 3.4 Starter positions vs. full-size entry — a real tension in his own rules

Two recurring pieces of sizing advice in this corpus point in opposite directions, and the honest thing to do is present both rather than quietly pick the one that sounds more coherent.

- **The starter-position rule (most common framing across the corpus).** Positions are frequently built starting at a quarter-to-half of eventual size, with the remainder added only once the setup confirms with continued strength or a fresh breakout — never averaging into a loser, only ever averaging up into a winner ("pyramiding"). This is the default framing in most sessions, especially on newer or lower-conviction ideas.
- **The direct counter-rule — buy full size, don't add at all.** Asked specifically about position sizing, he draws a hard causal line between adding and the size of achievable reward: "you're not getting 10 to 50 [times] reward trades ever if you [add to them] — you buy everything at once, and then you let it [ride], that's the key to getting 10, 20, 50 times reward the risk: not adding to them. If you start adding, you ruin your average." The mechanism is precise, not just a preference: adding shares above your original entry raises your *average* cost basis, which mathematically caps how many multiples of your *original* risk the position can ultimately return, even if the stock itself keeps running.
  - *2021-06-04, t=3809s*

The two aren't simply contradictory once you notice what each is optimized for. The starter-position approach is a way to test a new or lower-conviction idea cheaply and only commit real size once the market confirms it — it's a risk-reduction tool for the entry decision. The buy-full-size rule is about protecting the *reward* side of an already-confirmed, highest-conviction swing long once you're in it — it's an optimization for maximizing the R-multiple on a position you're already confident enough to hold at size. Read together: size up gradually into uncertainty, but once you're committed to a real position, resist the urge to keep adding on top of it if squeezing out the largest possible multiple is the goal.

### 3.5 Liquidity and borrow cost as sizing constraints

Position size should scale with a stock's dollar volume — a repeated heuristic is to never be more than roughly 1% of a stock's average daily dollar volume. On the short side specifically, borrow availability and cost are treated as a real, dollar-denominated constraint on the trade itself, not an afterthought.

- **Nikola — a new personal record for locate fees, paid anyway.** Mid-position, he reports the cost live: "I paid $22,000 to borrow 30,000 shares — I've never paid this much in locate fees before, that was a new all-time high for me." Doing the exact math on stream: "they were pretty expensive... almost $23,000 bucks is what I paid for my locates on Nikola." His conclusion isn't regret, it's acceptance of the cost as the price of the trade: "you gotta pay to play sometimes, you gotta pay to play, that's just what it is."
  - *2020-06-09, t=6585s*
- **SPCE — the honest counter-example, where avoiding the fee cost more than paying it would have.** Short 30,000 shares heading into a weekend, he covers the entire position specifically to dodge financing cost: "I was short 30,000 shares of SPCE, I covered it all because I didn't want to hold it over the weekend and pay borrow fees — I would have paid like $20,000 in borrow fees over the weekend, I didn't want to do that." The stock gapped down over the weekend anyway: "if I'd held it over the weekend, I would have literally paid $20K in borrow fees, but I would be up $20K on the trade just over the weekend. Well, it's what it is, a little bit frustrating." He doesn't retroactively call the decision wrong — the point isn't that avoiding financing cost is always correct, it's that it's a real, quantifiable trade-off weighed *before* the outcome is known, not an afterthought once the bill arrives.
  - *2020-02-24, t=571s*

Read together, these show the same discipline cutting both ways: sometimes the right call is to pay a large, known locate cost because the setup justifies it (Nikola), and sometimes it's to eat a smaller, certain cost (closing early) rather than risk a larger, uncertain one (holding through a weekend) — and either way, the decision gets made with the actual dollar figure in hand, not guessed at.

### 3.6 Margin discipline — "deserved, not entitled"

Leverage gets built up gradually as results improve, never jumped into all at once — and pulled back hard the moment the market's *character*, not just its direction, starts to feel wrong.

- **The QuantumScape mania — catching himself mid-euphoria, live.** Trading small positions in QS-adjacent SPAC names during the December 2020 EV-SPAC mania, he narrates his own psychological state rather than just his positions: "it's kind of addictive, that's what's so scary, and that's why you got to be so careful when you go on a big run and nail things left and right — you're gonna start chasing that high and start making bad decisions. When the market turns, when the speculation money leaves, you could give back half or most of what you made. So I'm doing trades here and there, but I'm on red alert mode here — the more craziness we see, the more cautious I get. I refuse to give back any profits — I've been there so many times, I double or triple my account and then give back half because I don't know when to stop once the market changes character. I refuse to be a victim, I'm gonna be proactive." Note what he's *not* doing: he isn't pulling out of the market entirely — he's still trading, just deliberately smaller and more defensively, treating his own rising excitement as the risk signal rather than any specific chart.
  - *2020-12-09, t=3028s*
- **The quantified ceiling that emerged as the account grew.** Asked directly about position-sizing theory at a much larger account size: "it's kind of hard to calculate the [full] Kelly factor, but use half Kelly for trading — if you think you can calculate it, use half Kelly." Pressed on whether he'd ever run the kind of leverage that blew up Bill Hwang's Archegos fund: "do I ever go Bill Hwang on a baby account? No, too much leverage — I may go one-and-a-half times leverage in my portfolio, no more than that." He studies blowups like Archegos, Long-Term Capital Management, and Niederhoffer specifically to reverse-engineer the recurring failure pattern (excessive leverage, no exit rules, over-concentration in a single name or thesis) rather than to feel superior to the people involved — see 3.9.
  - *2022-04-12, t=2566s*

The QuantumScape story and the half-Kelly rule are the same discipline at two different points in his career: early on, the defense against overleveraging in a euphoric run was self-awareness and deliberately small size ("red alert mode"); once the account was large enough that a mistake could be genuinely catastrophic, that same instinct got formalized into an explicit, quantified ceiling.

### 3.7 Sizing stops to volatility (ADR-based stops)

This is where 2.9's ADR (Average Daily Range) measurement becomes an actual risk-management number rather than just a chart-reading filter.

- **The fraction rule, with PLUG as the named exception.** Asked about stop sizing directly: "having a 5% stop on an ADR-10 stock, that's absolutely fine — half ADR. Try to keep your stop somewhere around a third, half, two-thirds, something like that. If you can have a stop that's one-third of the average daily range — or the average true range, doesn't matter, it's basically the same thing — that's very good." He then names the deliberate exception to his own rule: "sometimes I use a full 100%, like something like PLUG — I try to avoid it, but if it's a really good setup, I may do it." The rule isn't absolute; it's a strong default with an explicitly acknowledged override for the highest-conviction setups.
  - *2021-01-26, t=4192s*

The logic connects directly to 3.3's asymmetric-reward math: a stop set at a third of ADR gets stopped out more often (more small losses) but preserves a wide multiple if the trade works, while a full-ADR stop on a name like PLUG accepts a larger single loss in exchange for more room for the setup to actually play out — reserved for the setups he trusts enough to give that room to.

### 3.8 The short side's structural asymmetry

Shorting is mathematically asymmetric in a way going long isn't: max gain on a short is capped at 100% (the stock goes to zero), while the loss is theoretically unlimited. A losing short also *grows* as a percentage of the account as it moves against you, while a losing long shrinks.

- **The $1 million TVIX loss, walked through candidly.** Asked directly why a specific short went bad: "because I was a bit too early on it — I was a little bit too early on TVIX. If you're too early when shorting, you're dead." He then narrates the exact sequence: "I went short on this over the weekend, I had a good entry, opening-range lows, locked in some profits, closed the week — I'm thinking this thing is gonna go back to the 140s. Then on Monday, this thing gaps up — it gaps up 50%, and I take a million-dollar loss on it. I covered it pre-market — that was my million-dollar loss on TVIX." His stated takeaway is direct, not softened: "shorting is hard, you're gonna get run over a lot of times — that's why position sizing is so important." A leveraged, volatile instrument gapping 50% against a short position turned a good entry and a profitable week into a seven-figure loss in a single weekend.
  - *2020-09-02, t=4401s*

This is the concrete cost behind every short-side rule elsewhere in this document: never shorting frontside (2.3), waiting for confirmed weakness rather than anticipating a top (1.5's parabolic-short pattern), and treating borrow cost as a real constraint (3.5) all trace back to the same asymmetric math — a short position has no natural ceiling on how much it can hurt you, which is why the entry criteria for shorting are stricter across this entire document than for going long.

### 3.9 Studying historical blowups

He explicitly studies famous trading blowups — Archegos/Bill Hwang (see 3.6's half-Kelly discussion), Long-Term Capital Management, Victor Niederhoffer — not to feel superior to the people involved, but to reverse-engineer the recurring failure pattern.

- **A lesser-known case, and the rule he distills from all of them.** Bringing up a Norwegian retail trader as a fresh example rather than one of the famous funds: "he was just a retail trader, he made like — I think several hundred million euros, or even maybe a billion euros or something... and then he kind of blew up. The same story over and over again." The lesson he draws applies as much to a solo retail account as to a multi-billion-dollar fund: "don't be a victim, you gotta study this and avoid their mistakes. You should never, ever disrespect risk and low-probability events, because it's the low-probability events that are gonna take you out." He closes with the single line that ties every rule in this section together: "the ultimate risk manager is position size."
  - *2021-03-17, t=2466s*

The pattern he extracts is consistent across every named case, famous or obscure, fund or individual: excessive leverage, no real exit rules, and over-concentration in a single name or thesis. None of these blowups, in his framing, were caused by bad luck alone — they were caused by sizing and leverage decisions that made a single low-probability event catastrophic instead of survivable, which is precisely the failure mode every other rule in Section 3 (the 25% concentration cap, the half-Kelly leverage ceiling, the ADR-based stop sizing) is built to prevent.

### 3.10 Portfolio-level risk — position count as a personal stress indicator

Distinct from the market-regime version of this signal (Section 6 covers what a high position count means for reading the *market*), this is about what a high position count does to *him* — too many open names becomes a personal management and stress problem independent of whether the market is about to turn.

- **"My positions indicator" — noticed, tracked, and half-joked about.** Watching his own portfolio grow: "man, I have so many — oh my god, guys, do you remember my positions indicator? What happens every time I hit 30 positions?" He answers his own question with a genuine track record, not just a hunch: "it happened three times in a row since I started streaming — every single time I get to 30 positions, the market starts to pull back within a few days. It's an insanely reliable indicator." He then half-jokingly floats managing his own behavior around it: "or actually, if I just keep it at 29" — instead of entering another position when he sees something good, deliberately holding the line at 29.
  - *2021-01-13, t=3486s*
- **The same number, years later, as a hard-earned rule rather than an observation.** By 2023, the pattern-noticing has calcified into a flat personal ban: "I'm never gonna have 30 positions again — never, ever. Too many."
  - *2023-05-23, t=1402s*

The two clips together show the same insight maturing from "an interesting thing I've noticed about my own portfolio" into "a rule I will not break" — roughly parallel to how the half-Kelly leverage ceiling in 3.6 formalized what had been instinctive caution in the QuantumScape story. In both cases, an early, semi-superstitious self-observation eventually hardens into an explicit, stated limit once enough repetitions confirm it wasn't a coincidence.

### 3.11 Platform and broker redundancy

A distinct, purely operational risk-management practice that has nothing to do with position sizing or leverage: never keeping 100% of an account, or trading access, on a single platform.

- **The IB outage, and the hedge it would have enabled.** "I would never have 100% of my account anywhere — it's kind of nice to have at least two trading platforms, two brokers... let's say IB was down a couple of days ago — IB is one of the best brokers when it comes to stability, but they were down, first time in many years. Let's say you have a position in IB that's going against you, it's stopping you out, but you can't get into the platform — what could you do? Let's say I'm long Tesla and it's about to stop me out: what I could do is go short in that other account that's not down, so I would hedge that, versus having Tesla going straight down, me being long, and not being able to get out." This is "boxing" (see 1.9's citation-adjacent principle) used as a genuine operational hedge, not just a position-management technique — the second broker exists specifically so a platform failure never leaves both sides of the book unmanageable at once.
  - *2020-12-10, t=2709s*
- **The counterintuitive part — why panic-switching brokers after a rare outage is the wrong lesson.** He mocks the instinct to flee a stable broker after its first-ever failure: "IB was down, first time in a long time this week... it was so funny, I saw people on Twitter talking about moving their funds to Robinhood or Ameritrade — I laughed out loud. How stupid do you have to be? You're moving from a broker that's been down for the first time in five years to a broker that's down a couple of times per month." Redundancy, in his framing, means adding a second reliable platform *alongside* a track record of stability — not abandoning a proven one over a single rare incident.
  - *same clip, t=2782s*

### 3.12 What he refuses to trade regardless of setup quality

A handful of instruments get ruled out categorically, independent of how good any individual setup looks — the instrument itself is the risk, not the trade.

- **Options — "a sucker's game."** Passing on a name specifically because the only way he'd play it as a short is through options: "options are a sucker's game, that's why I prefer shorting [stock outright] — it's needless complexity, and you always want the odds in your favor. Every time you add complexity, you have worse odds." The objection isn't to any specific options strategy — it's to complexity itself as something that mathematically erodes edge, restated here as a direct extension of the same minimalism that drives 2.1's rejection of most technical indicators.
  - *2020-07-08, t=1942s*
- **CFDs — "poison," and a complete metaphor for why.** "Avoid CFDs, guys, they're poison — the leverage makes you think you're gonna get rich, but you're not, you're just gonna blow up. There's a reason CFDs are banned [for US retail traders]." Pressed on why, he doesn't just assert it, he builds out the analogy fully: "CFDs — it's comparable to insect traps. It looks shiny and exciting, the insect goes into the trap, and then the insect dies in the trap. And if you haven't figured out, the insect in this analogy is the retail trader." Notably, he adds that CFDs "don't exist in the US" as his own market — the rule isn't purely theoretical, it also reflects that the instrument literally isn't part of his own tradeable universe.
  - *2020-07-15, t=2929s*
- **Triple-leveraged ETFs, treated as a fundamentally different animal.** Covered in depth in 2.10: never technically analyzed directly, only ever read off their unlevered underlying, and never sized or held with the same assumptions as a normal stock — decay and compounding mean a "buy and hold" instinct that works on a regular stock actively works against you on these.

The common thread across all three: each one adds a layer of leverage, complexity, or structural decay between the trader's decision and the actual outcome, which is exactly the kind of variable his entire approach (minimal toolkit, mechanical risk sizing, asymmetric reward math) is built to eliminate rather than manage around.

---

## 4. Trade Management (Adds, Trims, Stops)

This is the machinery that turns a good entry (Section 1) into an actual realized result — how a position gets trimmed, trailed, added to, and occasionally overridden between the moment it's bought and the moment it's finally closed.

**Citation format:** same as Sections 1-3 — video title, upload date, and timestamp where known, in a sub-bullet under each example.

### 4.1 The 3-to-5-day trim rule, and how it flexes with market conditions

By far the most consistently repeated piece of trade management across the entire corpus: once a breakout is confirmed and hasn't stopped him out, wait roughly 3 to 5 days, then sell a third to half of the position and move the stop on the remainder to breakeven. It's stated so often it functions as the default operating system for every winning trade — but he's explicit that the exact numbers aren't fixed.

- **The market-condition flex, stated as a feel rather than a formula.** Asked if there's a particular timing rule: "not really — you gotta develop a feel for it. In choppy markets, sell on day three, sell half. In good markets, sell on day five, sell a third — something like that." The rule tightens (sell more, sooner) specifically when the tape is harder to trust, and loosens (sell less, later) when the trend is confirmed and working.
  - *2020-09-01, t=803s*
- **The account-size flex, stated just as directly.** Explaining why he gives the same general rule slightly differently depending on who's asking: "if I had a smaller account, I would be more aggressive taking profits... I know most people have small accounts, so I always say sell a third to half after three to five days, and the smaller your account, the more you need to sell. If you have a really small account and you're trying to aggressively build it, you should sell half after three days. If you have a bigger account, you'll feel a little more confident — maybe you should sell a third after five." He adds an honest aside that he doesn't always follow his own stated rule exactly, since he's managing a much larger, longer-tenured account than most of his audience.
  - *2021-04-16, t=1964s*

From there, the remaining shares are trailed using a moving-average *close* (typically the 10-day for fast movers, 20-day for slower ones) rather than an intraday touch — see 4.2 for why the close specifically, not the wick, is what triggers the eventual full exit.

### 4.2 Default stop placement — the close, not the wick

For longs, the low of the entry/breakout day is the initial stop the large majority of the time; as a position works, the stop is raised toward breakeven and then trailed with a moving average — but the trigger is always a *closing* price below the average, never an intraday touch.

- **NVAX — the trade that taught him the rule the hard way.** "Do not be in a hurry to take profits — that's why you need to be using a trailing stop, like the 10-day moving average, because you never know how high a stock can go from entry. Look at NVAX — this one I messed up. I thought this thing was done; in the low $80s I sold all of my position. I bought it on a five-star setup, it ran up 67, 70% in two weeks, I was like, 'it's not gonna go higher.' After I sold it, it went up another 130% — and it never closed below the 10-day. You would have gotten stopped out [eventually] if you'd followed the rules, which I didn't, because I'm an idiot, I had an opinion, and my opinion was wrong. I should have just stuck to the rules." The mechanical fact he keeps coming back to is specific: the *daily close* never violated the 10-day during that entire additional 130% move — only his own discretionary judgment did.
  - *2020-08-13, t=4729s*

The discipline this produces: a scary-looking intraday wick through the trailing average is treated as noise, not a signal, as long as the stock closes back above it by the end of the session. Several of his largest winners survive precisely because a bad intraday moment never became a bad closing price — see 4.4 for what happens when he overrides this rule anyway, on a different named stock.

### 4.3 Adding to winners — the mechanics of pyramiding into strength

Adds only happen on fresh confirmation of continued strength — never simply because a position is already up, and never into a loser (see 3.4 for the related, genuinely contested question of starter-sizing vs. buying full size up front).

- **The multi-timeframe add ladder, explained directly.** Asked how he decides when to add: "well, two-fold — I use conventions to add to my position. I may buy the one-minute opening-range high, and then I may add on the 5-minute opening-range high, and maybe even add more on the 60-minute opening-range high." He immediately flags the accuracy/risk trade-off across those timeframes: "the one-minute has a lower accuracy rate — you're gonna get stopped out more often on the one-minute opening-range highs or lows. The 5-minute and 60-minute have a little higher win rate, but usually you also have to use wider stops — so it's a risk/reward thing." He also notes a volume-timing nuance specific to earnings scalps: "sometimes the first one-minute candle isn't enough, you have to wait a little longer to actually see volume coming in."
  - *2020-06-02, t=3578s*

Each rung of the ladder is treated as a separate decision with its own confirmation and (per 3.4's "different stop levels for different lots" point) often its own stop — not a single blended average-up. Faster timeframes add sooner and cheaper but get stopped more often; slower timeframes add later and cost more in stop distance but confirm more reliably — the choice of which rung to use is itself a risk/reward call, not a fixed rule.

### 4.4 "You cannot outsmart the moving average" — the recurring self-critique

By 2021 this is arguably the single most-repeated self-critique in the entire corpus, and it has real, named trades attached to it rather than staying an abstract lesson.

- **Workhorse — a missed 500% gainer, admitted in real time.** "I had Workhorse from $3.60 to ten — if I had held that, even a small position, if I'd had a little more patience, I would have had almost a 500% gainer. But I always sell these things too early. It's the same thing that happened a couple of months ago, when everything I sold went up another 50, 100% in a few days — I hate when that happens." This isn't hindsight commentary recorded after the fact; it's a live admission on the same stream, with the stock still trading in front of him.
  - *2020-07-01, t=360s*
- **BILI — the trade behind the mantra itself.** Checking in on a stock referred to on stream as "Billy" (almost certainly BILI, Bilibili) that he'd already sold: "it's only up 70% since I sold it." He walks through exactly what the mechanical rule would have done instead — hold it: "all you had to do was be faithful, wait, use the 10-day moving-average trailing stop — it hasn't had a close below the 10-day, it undercut it a few times but held or closed above it." Then, to his audience directly: "I'm doing these mistakes so you don't have to, I'm doing it for you guys — you literally cannot outsmart these moving averages."
  - *2021-01-14, t=2862s*

The lesson isn't new in kind between the two — Workhorse and BILI are the same mistake, roughly six months apart — but by the BILI clip it's no longer framed as an occasional lapse. It's a recurring, quantified pattern he actively studies (see 3.9) and still, by his own admission, keeps repeating. He does name the honest flip side elsewhere: on rare, exceptional positions he acknowledges deliberately keeping a runner past where his own rule would have exited, accepting that this means being "wrong" by his own system on some individual trades in exchange for occasionally capturing a true outlier winner — presenting the tension between "trust the rule" and "occasionally override it for a real outlier" as genuinely unresolved, not a solved problem with a clean answer.

### 4.5 Deviating from the rules backfires — named casualties

- **Four names, one scary market dip, one honest confession.** During a market-wide selloff, he admits to exiting several positions before their actual rules triggered: "I kind of cheated, I'm not proud of it, but I did cheat on some of the exits. Like SC, for example — never really closed below the 20-day, it held the lows of that day, I should still be in SC. Twilio too — it never really closed below the 20, it closed right at it and then started building higher lows, and now it's at new highs, I should still be in Twilio too. But it got scary, everything went lower, and I've been there where I give back a lot of open profits because everything tanks, so I just tried to be smart instead of following the rules. I'm telling you guys, it's better to follow the rules than try to be smart — now I'm paying for it in reverse, since I'm not long those stocks anymore and they're going higher." He goes on to name two more: Fastly ("never closed below the 20-day except for these days, but it was still way higher than [where I sold]") and Livongo ("never even violated the rising [average], I should be in this thing too — but it's so hard when things go straight up, this thing went up 45% in just a few days, it's so hard to have conviction").
  - *2020-07-20, t=3219s*
- **GUSH, two years later — the identical mistake recurring.** "I had GUSH with like 119, 120, I had a decent position, then I got stopped out on this day because I didn't wait for it to close below the 20-day — which it never did, it reclaimed into the close. So bad. Not following my own rules cost me a big trade — could have been the trade of the year, one of the trades of the year. I missed two big trades just because I didn't follow my own sell rules. Every time I think I'm smarter than a 10-and-20-day moving average, this is what happens — every single time. Okay, not every time, sometimes I'm lucky — but just trusting the moving average, it's the hardest thing. It really is."
  - *2022-04-13, t=2728s*

The gap between the two clips is nearly two years, and the mistake is identical both times: reacting to an intraday move instead of waiting for the close the rule actually specifies (4.2). The stated lesson is repeated almost verbatim across both — follow the predefined rules rather than override them in the moment — and the fact that it recurs years apart, on completely different tickers, is itself the evidence for why 4.4's mantra needs repeating rather than being a one-time fix.

### 4.6 Short-side exit mechanics — fundamentally different from longs

The mirror image of 3.8's structural asymmetry, applied to the actual exit process rather than the risk math: because a short's maximum gain is mathematically capped, the whole exit approach flips from "trail and let it run" to "scale out on a known ceiling."

- **GME, and the logic explained directly.** "How I set profit targets on the long side — it's very hard, that's why you use a trailing stop, because you don't know if the stock is going to go up 10% or 100%. On the short side it's much easier, because the stock can't go down more than 100%, so it's very easy to adjust for that. If you think a stock is going to fade a lot — like GME, in my case when I shorted it — I knew every time it goes down 10, 15%, I probably want to cover, say, 10, 15, 20% of my position. That's it. On the short side you shouldn't use trailing stops as much — you can use the 10 or 20 EMAs on the 60-minute, or the daily 10-day or 20-day if it's a larger mega-cap short — but it's more important to cover into strength [weakness] when short than [it is to sell into strength] on a long."
  - *2021-02-05, t=4229s*

The practical difference: a long position's upside is unknowable, so it gets trailed with a moving average and let run indefinitely (4.2's close-not-wick discipline). A short's upside is bounded at 100% and, in practice, rarely delivers more than 40-60% before mean-reverting — so instead of waiting for a single trailing-stop trigger, he pre-commits to taking fixed percentage chunks off at fixed percentage declines, covering into the position's own strength (i.e., the stock falling) rather than waiting for it to show weakness first.

### 4.7 Willingness to re-enter after a stop-out

- **"Grab your balls and re-buy it."** Asked directly how he mentally handles re-entering a setup that already stopped him out once: "mentally — well, grab your balls and re-buy it. It's just a click of a mouse, not a big deal. And if you have no balls, well, use your imagination. Just a click of a mouse. If you think it's a good setup, you get stopped out, and it triggers again — well, you have to get back in, because the universe doesn't give a [damn] that you got stopped out. The market doesn't give a [damn]." There's no cap on how many times he'll take the same setup on the same name if it keeps re-forming — a stop-out is information about that specific attempt, not a verdict on the underlying thesis.
  - *2022-04-06, t=1382s*

This connects directly to 1.9's failed-breakout-reset pattern: if a second attempt on a higher low is often *better* risk/reward than the first, refusing to re-enter after a stop purely out of ego or frustration means systematically skipping the improved version of a setup he already believed in once. The discipline isn't blind repetition — it's re-underwriting the same setup criteria fresh each time — but there's no arbitrary limit on how many attempts a genuinely valid, re-forming setup gets.

### 4.8 Earnings-holding discipline

A recurring, near-absolute rule: never hold a full position through an earnings report, in either direction, regardless of how strong the setup looks. The exception is holding a partial position specifically from a position of strength — an existing profit cushion that can absorb a bad gap — and even then only with reduced size.

- **PDD — the ~$200K lesson in forgetting your own calendar.** Live, mid-loss: "I'm getting killed on PDD pre-market — I forgot they had earnings. I went into these earnings almost full size, I only sold maybe 10-15% of my position into strength, and I probably should have sold like half before the close. I forgot they had earnings, and now it's gapping down..." He does the math out loud as it happens: "I'm gonna take a pretty big loss, close to $200K, if I get stopped out — and that's on me, because I broke my own rules, because I was sloppy." No hedging or blaming the stock: the loss is attributed entirely to a process failure (not checking the earnings calendar before sizing up), not to the setup itself or the market being unfair.
  - *2020-08-21, t=399s*

The rule this trade violates is simple to state and, per his own account, easy to break through sheer carelessness rather than a considered decision to gamble: check the calendar before building size, not after the gap already happened. A position that's "almost full size" going into an unknown catalyst is functionally the same bet as deliberately holding full size through a known one — the earnings-risk rule only protects you if it's checked *before* the position is built, not discovered afterward.

### 4.9 Fast/extreme movers need a faster trail

On stocks that move extremely quickly (100%+ in a handful of days, or even in a single session), the standard daily moving-average trail from 4.1/4.2 is too slow by design — the stock can give back a large chunk of the move before a daily close-below signal ever triggers.

- **$13 to $49 in one session — why the daily stop is "just stupid" on this kind of move.** Describing a stock that broke out intraday from $13 and ran to $49 the same day: "you can't use a 10 or 20-day daily moving average for a stop, that's just stupid — by the time it gets there, the move, it gives back all the move. You have to sell into strength. So it depends, depends on the stock." The fix on names moving this violently is either an intraday trailing reference (a 60-minute or faster moving average) or actively selling into strength in small increments rather than waiting for any trailing signal to fire at all.
  - *2023-12-15, t=1142s*

This is a genuine exception to 4.2's close-not-wick discipline, not a contradiction of it — the rule was always "use the average that matches the stock's actual speed" (2.2), and a 300%+ single-day mover has no meaningful daily-close reference point to trail against in the first place. The decision of which timeframe to trail on is itself a judgment call matched to how fast the specific stock is actually moving, not a fixed universal setting.

### 4.10 When overriding the rules is actually correct

Everywhere else in this section, overriding a predefined exit is the mistake (4.5). This is the one deliberate, named exception, and he's careful to distinguish it from ordinary rule-breaking.

- **Selling Twitter and a big SC position without waiting for the 10-day.** Watching several leading stocks roll over on the same day: "I'm gonna sell Twitter, I'm gonna sell it — I don't think these social media stocks are gonna be immune, they're all gonna pull back. I'm not even gonna wait for a 10-day, I want to play defense here." SC, described as a big position at the time, gets the same treatment. He explicitly connects the decision to a specific historical precedent rather than a generic feeling: "this is starting to remind me of what happened in early or late February this year, when I got stopped out of [several] positions — they all started breaking down, and then we had the COVID selloff. We didn't know it was gonna be that bad, but that's why you gotta play defense. When you start seeing a lot of leading stocks breaking down at the same time, sometimes I override my sell rules and just get out before it's too late. You don't want to get caught in a bad selloff."
  - *2020-10-22, "Leading stocks breaking down!", t=2020s*

The distinction from 4.5's cautionary tales is specific and stated plainly: an individual stock holding near its own trailing average, in isolation, is noise to be ignored (4.2). Many *unrelated* leading stocks breaking down on the *same day* is the market-breadth signal from 2.11 and Section 6 showing up in his own portfolio in real time — and that's a different category of information than one position looking scary on its own, which is exactly why it earns an exception to a rule he otherwise insists on following to the letter.

### 4.11 Execution mechanics

Stops are placed as market orders, never stop-limit, since a stop-limit can fail to fill entirely during a fast decline — but even market orders aren't all equal.

- **Why a broker's routing logic matters as much as the order type.** Comparing a plain stop-limit to Interactive Brokers' smart-routing algorithm during a fast drop: "with a stop-limit, it would still create this wick, it wouldn't make a difference. But with [IB's smart algo], when the price drops too much, it waits a little bit — that's what's great about it, I really like it, it's not perfect, but it's way better than using these other routes." He explains the underlying mechanism: "the algo sees a big market order coming in, they pull the bids, and then when my order is done, they bring the bid back up — so it kind of waits a split second for the bids to come back in, and then it keeps selling." A market order guarantees a fill; which specific fills you get during a violent move still depends on the execution logic behind it, not just the order type on paper.
  - *2020-12-10, t=2421s*
- **The $77,000 lesson in correcting mistakes immediately.** Reviewing a trade that went badly: "I should have covered more aggressively, I only covered a little because I wanted it to dip — it never did. This is a trade I was gonna risk like $30-40 thousand on, and instead I lost $77,000. Not happy about that at all." He draws the general rule directly from the specific loss, restating something he'd said minutes earlier on the same stream: "you need to correct your mistakes immediately, as soon as you realize you made a mistake — it may be anything, an entry, a position-sizing error, or just some random fat-finger [trade] — you need to correct it immediately."
  - *2020-06-29, t=2958s*

Neither of these is a strategic decision in the way the rest of Section 4 is — they're operational discipline: choosing a broker whose execution logic actually helps during volatility, and treating any mechanical error (wrong size, wrong direction, a fat-fingered order) as something to fix the instant it's noticed rather than something to rationalize or wait out.

---

## 5. Profit Taking & Exit Strategy

Where Section 4 covers the mechanics of trimming and trailing, this section is the strategy layer underneath it — how much conviction to give a winner, when the mechanical rule should bend, and how he thinks about exits at a portfolio level rather than trade by trade.

**Citation format:** same as Sections 1-4 — video title, upload date, and timestamp where known, in a sub-bullet under each example.

### 5.1 "Let the stock tell you" — why fixed price targets get rejected almost universally

- **A recent IPO, and the case against setting any target at all.** Asked directly what his target is on a fresh IPO already up nearly 5% from entry: "target? There's no target, just trail it. It's a recent IPO in a hot sector — there's no target for it, it could go to infinity and beyond, or it could just go straight down, I don't know. Just pull a random number out of your ass, that's the target — I mean, it's a recent IPO, there's nothing to go on here." The point isn't that price targets are lazy or unsophisticated — it's that on a stock with no trading history, any specific number is *definitionally* unfounded, since there's no prior price action to derive it from.
  - *2020-05-29, t=1687s*

The trailing moving-average stop (4.2) functions as the entire exit mechanism instead: hold until the rule says to sell, not until an arbitrary number is hit. A trade he expects to move a modest 15-25% gets trimmed faster and in fewer stages; a trade he thinks could double or triple gets sold far more slowly, in small increments, over a much longer stretch — the pace of selling is itself a signal of how much conviction he's willing to give the position, decided as the trade develops rather than fixed in advance.

### 5.2 The core trade-off — sell a little too late, not a lot too early

- **MRNA, live and genuinely undecided.** Talking through an extended position in real time: "extended, like MRNA right now — I'm a little bit conflicted here, should I sell it all? It looks vulnerable, it looks like it could pull back to the mid-200s any time... on the other hand it could go to $400." He resolves the conflict by stating the underlying rule rather than guessing: "you're either gonna sell too late or too early, but I'd rather sell a little bit too late, after the stock has gone up 100 or 200%, rather than sell too early on a stock that's about to go up 200%." He makes the trade-off concrete with a hypothetical: "let's say a small-cap stock goes up 200%, breaks out of a perfect flag, and then goes down — I'd rather sell it here, 20% off the highs, rather than sell it after it's only gone up 20% total. I'd rather sell a little bit too late than a lot too early, that's the point I'm trying to make. This is why it's so important to have some kind of trailing stop."
  - *2021-07-20, t=2934s*
- **The narrow exception — Shopify, sold ahead of its own formal stop.** Not every position gets the benefit of the doubt equally. Comparing a lagging position to a strong one held simultaneously: "I'm thinking about selling my Shopify, it's just not performing well — if Shopify closes weak, I'd rather keep my TQQ, because this one had a big, big move, I'd rather keep this one even if it pulls back to the 20-day, I'd be fine with it. The Shopify, it's kind of close to stopping me out anyway, I'm gonna move my stop to breakeven... if it closes weak, I'll get out of it." This is discretion operating *within* the trailing-stop framework, not against it — he's tightening a specific underperformer's effective stop because it's already showing relative weakness against a stronger name in the same book, not overriding the rule on a whim.
  - *2021-04-14, t=4068s*

The two examples together show the actual shape of the trade-off: give a genuinely strong, still-working position (MRNA, TQQ) the most benefit of the doubt and risk selling a little late, while a merely-adequate position that's already lagging (Shopify) gets the tighter leash. It's not "always hold longer" — it's "hold longer in proportion to how much the position has actually earned that patience."

### 5.3 Selling too early — the self-rated weak spot

Selling is far harder than entering — entries are "the easy part," which is why mechanical, simple sell rules matter more than clever ones. He rates his own entries near 5/5 and his exits closer to 3.5/5, and the gap shows up constantly in real, named trades.

- **MRNA and UPST, both sold "too early" in the same stretch.** "The moral of the story is I haven't been able to outsmart my sell rules, even though I always try to — so far it hasn't worked. I always think I can outsmart my own sell rules, and I keep making the same mistakes. I always complain about selling too early because I think things look extended — I sold MRNA, where I bought it at like $235, sold it in the $330s-340s. It went up another almost 50% in the next few weeks. UPST, another one — I sold it at like $285, thought it looked extended, it went up another 43% in the next month. I don't know why I keep doing that." His own explanation, only half-joking: "imagination is the greatest superpower you can have in the stock market — forget about discipline, discipline is for losers. You need to be able to imagine a stock making an enormous move, you have to believe it. Sometimes I lack in imagination, that's when these kinds of things happen."
  - *2021-10-21, t=3509s*

The "discipline is for losers, imagination is the superpower" line is deliberately provocative — everywhere else in this document he argues the opposite (mechanical rules beat gut feel, see 4.4). Taken together with 4.4's BILI/Workhorse examples and 4.5's SC/Twilio/Fastly/Livongo/GUSH casualties, the honest picture is that this specific failure mode — discretionary early selling driven by a story ("it looks extended") rather than the actual trailing-stop signal — is the single most repeated, cross-year, named-ticker weakness in his entire trading history, and by his own account still not fully solved even after naming and studying it for years.

### 5.4 Defending large open profits actively

- **FCEL — $200,000 given back in fifteen minutes, and the exact cause named.** Opening the stream already down from where he'd been: "I gave back $200,000 in profits — I was long, sold some on the way up, sold some at like $3.93 market, and then earnings hit it. I didn't see it, I was slacking, I was doing other stuff, I was very sloppy. It's easy to get complacent in a market like this." He quantifies exactly where the profit went: "I was up like $250K on it total, including shares from the day before — now I'm only up maybe $50K on it, which is still a decent trade, but $200K is a pretty significant sum, I'm not happy about it." The root cause, stated without hedging: "I got sloppy, that's what happened. I should have watched the chart, that's what I should have done — as soon as it started selling off on earnings, I should have [reacted]. Mistakes were made. But that's okay, I'll survive, I'm just $200,000 poorer than I was a couple of hours ago."
  - *2020-01-22, "I gave back $200K in profits on $FCEL in 15 minutes...", t=205s*

The lesson isn't "trail your stop and walk away" — it's the opposite, and specific to outsized open profits during a known volatile window (here, an earnings reaction he'd simply lost track of). A large unrealized gain needs active, eyes-on attention precisely when it's most vulnerable, not "set and forget" trailing-stop discipline alone; a mechanical stop still eventually protects the position, but by the time it triggers on a violent enough move, a meaningful chunk of the gain is already gone.

### 5.5 Home-run trading — the Pareto principle

- **"95% of my profits come from 5% of my trades."** Asked whether the Pareto principle applies to his own results: "oh yeah, definitely, the Pareto rule is very real in trading — I would say 95% of my profits come from 5% of my trades." He adds a genuinely useful nuance rather than treating it as a universal constant: "it depends on what type of trader you are. If you're more of a day trader, it's probably gonna be like 80/20; if you're a swing trader or position trader, it's gonna be like 5/95 or something; and if you're a scalper, it's probably gonna be maybe 60/40." The ratio itself is a function of holding period — the longer you're willing to hold, the more concentrated your profits get in a small number of trades.
  - *2022-01-27, t=1766s*
- **X, COPX, FCX, and NUGT — what "10-15x initial risk" actually looks like in a live portfolio.** Making the case that large multiples aren't theoretical: "15 times risk is very possible in the US stock market — just look at some of the things in my portfolio. Look at X, for example — when I bought it initially, my average was $24.94, let's call it $25. I had less than a dollar of risk on it, and I'm up like 12, 13, 14 times my initial risk on it. Same thing with COPX and FCX — I'm up 10-15 times my initial risk on them. NUGT, my initial buy — this one too, I'm probably up 10-15 times my initial risk on it."
  - *2022-04-12, t=1800s*

Both points describe the same underlying reality from different angles: most trades in a given year will roughly wash, and the entire year's return is effectively decided by a small handful of positions he simply never sold early on (5.3) and let compound into double-digit multiples of the original risk (3.3). The job, as he frames it elsewhere, isn't to make every trade a winner — it's to make sure the rare 10-15x trade is never capped by an unnecessary early exit.

### 5.6 Exit mechanics change at size — "get out when I can, not when I want to"

- **Selling a "big move" that's only 20%, explained live.** Trimming a position that most of his audience would consider barely worth touching: "chill here, guys, I'm selling tiny, tiny bits — I'm up more than 20% on it. It's not one of these low-float micro-caps that goes up 500%, so 20% is a big move [for a name this size]. Selling a tiny bit, just locking in — I don't have the luxury of a small account, I need to get out when I can, not when I want to." He generalizes it directly to his audience: "I don't have the luxury like you guys have, I'd have to trade a bit differently."
  - *2021-03-18, "Setups developing but they need more work", t=4842s*

This is the exit-side mirror of 3.2's small-account-edge and 3.10's liquidity-driven concentration limits: a small account can wait for its exact preferred exit level because its size doesn't move the stock, while a large position has to be sold in pieces, opportunistically, whenever the market actually offers the liquidity to absorb it — "when I can" rather than at a chosen target. The 5.1-5.5 philosophy of letting a winner run as long as possible still applies, but the *execution* of taking profit becomes a liquidity-management problem at size, not just a conviction call.

### 5.7 Trading price over opinion — the Tesla short-to-long flip

- **$6 million short to $4 million long, inside a few seconds.** Going through his positions live: "Tesla — sold some pre-market, looks like it's capping down a bit now, but we're acting really well. I went from being short 3,900 shares to being long 2,300 shares inside of a few seconds. So I went from being $6 million short to being about $4 million long. That's probably my biggest position switch ever." He immediately adds the honest, slightly rueful footnote rather than presenting it as a perfectly executed masterstroke: "now I wish I had done even more on the long side, but whatever, it's a decent position in case it wants to go higher."
  - *2020-07-21, t=380s*

The size of the swing is what makes the example instructive — a ~$10 million total reversal in position, executed in seconds, on a stock he'd apparently been confidently bearish on moments earlier. Nothing about his opinion of Tesla changed in those seconds; what changed was what price actually did, and the whole framework in this document (mechanical stops, no fixed targets, trailing rather than predicting) exists specifically to make a reversal like this possible without an ego cost — the position flips the instant the *evidence* flips, independent of how recently or how confidently the opposite thesis was held.

### 5.8 Reframing losses against total account size

- **A $900K GME loss, immediately weighed against a $1.5M Palantir gain from the same weekend.** Covering a losing GME short: "took a decent — okay, $900K loss, all right. Not even in the top five of my losses." He puts the number in context immediately, unprompted: "I'm gonna make it back on the next trade — like Palantir from Friday, I bought this a little bit before I stopped the stream, I'm up one and a half million on it. So that $900K loss is really nothing — I've literally done nothing since Friday, I'm up $1.5 million on it. Just to put things in perspective, it's not a big deal."
  - *2021-01-25, t=3516s*
- **The retrospective twist — the loss that turned out to have saved him millions.** Watching GME continue its historic squeeze after he'd already covered: "this could have been the best trade of my trading career — I would be down like $4-5 million at this point if I didn't take my loss. That $900K is the best loss I've ever taken in my life."
  - *same clip, t=4780s*

Both bullets are the same discipline from two different angles. In the moment, a large loss gets sized against total account performance rather than treated as a catastrophe on its own — a $900K loss next to a $1.5M gain the same weekend is, arithmetically and emotionally, a net-positive stretch, not a crisis. In hindsight, the same loss is reframed again: taking it mechanically, on schedule, rather than holding and hoping, is exactly what capped a position that could have cost several times more if he'd stayed in out of stubbornness. Reframing isn't about pretending a loss doesn't hurt — it's putting a single trade's dollar figure back into the context of the portfolio and the discipline that produced it, rather than judging it in isolation.

### 5.9 Exit style is a trade-off, not a universal rule

- **Cash flow vs. maximum growth, named as two legitimate, different goals.** Responding to a viewer's idea for a more aggressive selling approach: "that's a very good idea if you want to generate cash flow and not maximize account growth — selling aggressively is very important if you wanna prioritize consistency and cash flow over maximizing profits. You gotta be more aggressive in selling because you're gonna be more consistent throughout these different market cycles, while someone who looks for big moves may not make money in a choppy environment. You can still generate cash flow in a choppy environment — in a really good market you're not gonna generate as much money, but you will probably make money much more consistently."
  - *2021-06-01, t=2310s*

This directly qualifies 5.2's "sell a little too late" default — that preference is optimized for maximizing total account growth (which is what 5.5's Pareto-principle home runs require), not for the smoothest possible equity curve. A trader prioritizing consistent income over compounding the account as fast as possible has a legitimate reason to trim harder and earlier than everything else in this section recommends — the "right" exit style depends on which of those two goals is actually being optimized for, not on which one sounds more disciplined.

### 5.10 "Silly season" runners — the trail that gives back too much

On the rare stock that moves 100-500%+ in a matter of days, the standard moving-average trail (4.9) gives back so much of the move so fast that it stops being a sensible exit method at all — but the "fix" for that has its own failure mode, which he's careful to flag rather than present as a clean solution.

- **INDO — the counter-example to his own "sell into strength" advice.** Reflecting on the wildest single-name runners: "runners like this go up 500, 1,000% in a week or two — we saw a lot of these in 2020, 2021, there was nothing to learn, I just messed it up, and this is why I don't really believe in this thing, 'oh, you have to sell into strength' — no, you don't. If you bought the EP here on INDO and you sold it the next day when it was up 130%, you missed out on some big money."
  - *2023-12-01, t=2513s*

Put next to 4.9's $13-to-$49 same-day example (where trailing on the daily chart was explicitly "just stupid" and selling into strength was the *right* call), the honest picture is that there's no single correct answer for the most extreme runners — a daily trail bleeds too much on a violent single-day spike, but reflexively selling into strength can just as easily cap a name that keeps compounding for weeks. Which failure mode you're more exposed to depends on whether the specific runner in front of you turns out to be a one-day spike or the start of a genuine multi-week move — something that, by his own admission, often can't be known in advance.

---

## 6. Market Timing & Regime Reading

This is one of the richest and most consistent themes across the entire span — Kullamägi treats "what kind of market is this" as a constant, ongoing question that reshapes everything else about how he trades, far more than any single stock's chart.

**Citation format:** same as Sections 1-5 — video title, upload date, and timestamp where known, in a sub-bullet under each example.

### 6.1 The two-regime framework — "easy dollar" vs. "hard penny"

Markets are repeatedly split into two broad types, borrowing language from other traders: an "easy dollar" market (a strong, persistent trend where mistakes get forgiven and nearly every reasonable setup works) versus a "hard penny" market (choppy, directionless, where only the very best setups have edge and most trades — even good-looking ones — fail to follow through). Recognizing which regime is currently active, and adjusting trade frequency and size accordingly, is treated as more important than any individual chart pattern.

- **A $1.5 million loss, rebuilt in under a week — what "forgiving" actually looks like in dollars.** "I've already made back that $1.5 million loss from last week — I lost almost $1.5 million shorting this stock, I went short on the 29th of July, that was last Wednesday, and today is Tuesday. So in less than a week I made it all back — that was almost 7-8% of my account, and in less than a week I'm already at new highs, pretty much. That's what happens in a good market — you can have so many [messed-up trades] and it will all be forgiven in a short amount of time." He immediately draws the contrast with the opposite regime, using the same technical framework from Section 2: "this is like late 2018, not a good swing-trading market — you see the 20-day sloping down during this whole move, the 10-day too, they tried to turn up here and here but failed. There will be select good setups that may even work, but the fail rate is just high."
  - *2020-08-04, t=3712s*

The dollar figures are what make the regime distinction concrete rather than a vague mood read: the exact same trader, running the exact same process, can lose 7-8% of an account and be back at new highs within a week in an easy-dollar market, or watch a string of individually reasonable setups fail one after another in a hard-penny one — the difference isn't skill fluctuating week to week, it's which regime the market is actually in.

### 6.2 The hardest regime isn't a crash — it's chop

A market that's obviously falling is, somewhat counterintuitively, described as easier to navigate than a market producing a stream of legitimate-looking setups that then fail to follow through — the former makes it easy to simply sit in cash, while the latter tempts continued, increasingly costly participation.

- **A slow, quiet session, and the reminder he gives himself mid-stream.** On a day with "not a lot of green stocks" on his main watchlist, well after the morning's action had already played out: "now it's all a waiting game — the morning action is over, and now the rest of the day is just the patience game. Remember, it's not the most active trader who wins, it's the most patient trader who wins at this game. You gotta wait for those spots." He explicitly leaves the door open to add later, but only conditionally: "if this rally starts failing mid-to-late day, I may add more — but only on a tight setup," refusing to lower his own bar just because the session has been slow.
  - *2020-09-02, t=2639s*

The line between "hard penny" chop (6.1) and this specific quiet-day discipline is really the same regime described at two different zoom levels — a whole multi-week stretch can be choppy, or a single session inside an otherwise fine market can simply have nothing worth forcing. Either way, the correct response is identical: do less, wait for the setup to actually qualify, and treat idle time as the job working correctly, not the job failing.

### 6.3 Reading breadth and correlation — the clearest regime-change signal

When previously independent, uncorrelated winning stocks all start breaking down together on the same day, that's treated as a much more serious signal than any single stock's normal pullback — a hallmark of a genuine top or regime shift rather than routine rotation (the live version of this is 6.4's "rug pull"). Narrowing breadth, well before the headline indices themselves show any weakness, is the early tell he watches for instead.

- **Two real stats, and why the index alone was hiding them.** Reading out numbers he'd seen on Twitter, live: "the average stock in the Nasdaq Composite is down 34-35% from 52-week highs, but the index itself looks like this [near its own highs]... 40% of S&P 500 stocks are down 10% or more from 52-week highs, and the index looks like this [fine]." He's careful not to overclaim originality here: "it's not like it's coming as a surprise, you can see it just looking at charts, but it's still nice to see data on it." He immediately gives the reason the index-level view is misleading on its own: "the indices don't tell you the whole story — like if you look at Nasdaq, this run here was free money, I more than doubled my account [during that stretch]." A strong-looking headline number and a genuinely broad, healthy market are two different things, and only one of them is visible by looking at the index alone.
  - *2021-09-17, t=1866s*

Real market crashes have historically started from price already below the 50-day/200-day moving averages — a single scary red day while a stock or index is still making new highs above rising short-term averages is, by his framing, not itself a crash signal. The breadth read is the earlier, more reliable warning: by the time the index itself rolls over, the underlying deterioration (as the Nasdaq/S&P stats above show) has usually already been building for a while underneath it.

### 6.4 Case study: "the rug pull"

Unlike the GameStop and 2022 bear-market case studies, this one is short — a single 24-hour arc — and it's valuable specifically *because* it's short: it shows the breadth-reading skill from 6.3 called live, one day before the market actually confirmed it.

- **Day one — the warning, stated as a prediction, not hindsight.** After four months of an aggressive bull run: "the market breadth is really bad right now — the amount of stocks going higher is getting fewer and fewer. I think we're gonna have a hard market pullback unless we get a new sector pulling the market higher, but right now it's just a very, very thin market in terms of the amount of stocks going higher — pretty much the COVID names, some of the fuel-cell/electric names, and some software/tech names, that's pretty much it. Outside of that, not really a lot of sectors going higher."
  - *2020-07-13, t=2216s*
- **Day two — confirmation, and the systematic unwind.** Opening the next session: "we finally got some rug pull yesterday, which was very expected since the Nasdaq was going parabolic... there were some insane opportunities yesterday on the short side." He then walks through the actual portfolio change, name by name: "a lot of stocks I've been long for many months, I've sold them — the only things I'm still long are VIR (a COVID stock), ZS (right on the rising 10-day), Roku, APT (a mask stock), and MRNA, BNTX, VXX, which are all COVID-19 stocks — that's it. And now I'm heavily net, net, net short. I added more to my Tesla, I have 2,000 shares short of Tesla now." Reviewing the two days together: "I'm very systematically selling things off, and I went heavily short, so even though a lot of the stocks I was long went down yesterday and today, I still managed to [come out ahead]."
  - *2020-07-14, t=114s and t=3239s*

The case study is a clean, compressed demonstration of the whole chapter's thesis: the breadth deterioration was visible and stated *before* the market itself confirmed it, and the response wasn't a single dramatic trade but a systematic, name-by-name liquidation of a multi-month long book down to a handful of theme-specific holdings, paired with building real short size (not just closing longs) once the read was confirmed. Nothing about it depended on knowing why the pullback was coming — only on watching the underlying breadth, exactly as 6.3 describes.

### 6.5 The best time to buy breakouts — right after a correction resolves

This is one of the most repeated individual claims across the entire corpus, restated in some form in nearly every year covered — and it's stated as a specific, learnable window, not a vague "buy dips" platitude.

- **The window defined precisely, with the aging-uptrend caveat.** Explaining a stretch of poor breakout follow-through: "it hasn't been a great breakout market for the past few weeks — that's what happens when the indices are extended. The best time to buy breakouts is when the market has pulled back, like a 5-10% correction in an uptrend — those are usually the best times. Or if the market breaks out of a multi-month range, those are good too. But not when the market's already been grinding higher for many months." He states the reason he actively looks forward to pullbacks rather than fearing them: "that's what I always welcome pullbacks [for], because I know that's where the big money is made — after a pullback."
  - *2021-01-28, "Cool $10M+ day today", t=3787s*

The logic ties directly back to 2.2's moving-average framework: a market that's been trending for months has its short-term averages stretched far above the longer-term ones, which is exactly the "extended" condition that makes fresh breakouts more likely to fail. A pullback or multi-month range lets those averages "catch up" to price (the same mechanic described for individual stocks in 1.1 and 1.9), resetting the odds back in favor of the breakout actually working — which is why the setup quality he's looking for doesn't change, but the *win rate* on identical-looking setups shifts dramatically depending on where the broader market is in its own cycle.

### 6.6 Position count and personal exposure as a sentiment gauge

Section 3.10 covers this same number from the personal-management-and-stress side; here the same indicator is read as a signal about the *market*, not about him.

- **A three-for-three track record, laid out with dates.** Explaining why his own position count functions as a genuine market-timing tool: "the 30-positions indicator has been right, it's happened three times since last year. It happened just before the market topped in February last year and we got the COVID crash — that's when I hit 30 positions after a multi-month bull run. It happened here in August, late August last year, after we'd had a multi-month rally, and then we had a big rug pull [6.4] — a lot of momentum stocks were down much more than the index. And it also happened a couple of weeks ago. It's such a great indicator, it's unbelievable — every time I hit 30 positions, [it's] time to start taking profits." At the moment he's describing this, his own book is already positioned defensively: "about 85% short and less than 10% long."
  - *2021-02-26, "Market in limbo", t=4794s*

The mechanism he's implicitly describing is that his own position count isn't an arbitrary personal quirk — it's a byproduct of how many individually-valid setups are triggering across the whole market at once. Thirty simultaneous long setups is itself only possible in a very broad, very extended rally; the number quietly encodes the same breadth information as 6.3's Nasdaq/S&P stats, just measured through his own trade log instead of an index screener.

### 6.7 Euphoria is a warning sign, not a green light

A market where "everything is straight up" is treated as a late-cycle, high-risk signal, precisely because it feels like the easiest, most rewarding environment to be aggressively long — and his own rising personal excitement about the market is explicitly used as a contrarian signal to start hedging.

- **"When you start feeling like a genius" — including himself, by name.** During the QuantumScape/EV-SPAC mania (the same stretch narrated from the margin-discipline side in 3.6): "there's gonna be so many short setups for next week if everything keeps going up like this, straight up. And this is a very dangerous market, because a lot of traders feel like geniuses right now. And when you start feeling like — including me, including me — when you start feeling like a genius, that's usually when bad things happen, every single time." He immediately catches himself getting pulled into the same euphoria on a specific stock: "QS, I wish I had held my initial entry, my initial buy at $20, $20.50 — I wish I was still in it. Oh my god, QS, I need to size down on it."
  - *2020-12-22, t=1489s*

The signal isn't the market going up — it's the *feeling* it produces in him personally, and he's explicit that the feeling doesn't discriminate by experience level: naming himself as susceptible in the same breath he warns his audience is what makes this a genuine self-monitoring practice rather than a lecture aimed only at newer traders.

### 6.8 Historical base rates, cited to counter emotional extremes

References to how often equity indices have historically been in an uptrend versus not (the Dow up or sideways roughly 86% of the time since 1915; the Nasdaq in a "favorable" condition roughly 62% of the time since the 1970s) are used to push back both against "stocks only go up" complacency during euphoric periods and against excessive fear during selloffs — a 20%+ index decline is described as a fairly routine, roughly every-3-to-4-year occurrence and historically a buying opportunity, while 30-50%+ declines are rare.

- **Rate hikes as a counterintuitively bullish base rate.** Pushing back on a viewer worried that rising rates should mean a market top: "you should ignore most of it — let the market confirm, and you should know the data. Just because rates are going higher, the market should crash — that's not true. Markets usually keep going for another six to nine months after a rate hike has begun. So it's actually a bullish thing, not a bearish thing."
  - *2021-12-30, t=3649s*
- **The "grandma" test for what will actually crash the market.** Arguing that widely-discussed macro risks are, by definition, already priced in: "if something's gonna crash the market, it's gonna be something unknown. Like COVID last year — which one of these super smart people predicted, 'hey, we're gonna have a global pandemic crashing the markets'? Not a single one. It was hyperinflation and all these things people were worried about — what we got was a global pandemic. It's gonna be the same thing next time, it's gonna be something no one expects... it's rarely the thing every grandma is already aware of — if your grandma knows it, it's probably not gonna affect the markets."
  - *2021-11-12, t=4235s*

Both examples do the same job as the Dow/Nasdaq base rates: they're used to talk himself (and his audience) out of overreacting to whatever the dominant narrative of the moment is — whether that narrative is fear (rate hikes, inflation headlines) or complacency (a long uptrend feeling permanent). The base rate isn't a market-timing tool on its own; it's a check against treating a normal, statistically expected event as if it were unprecedented.

### 6.9 Ignoring macro, Fed policy, and news entirely

A recurring, sometimes blunt refrain across nearly every year covered: politics, Fed policy, and general macro commentary are explicitly said to have no predictive value for his process, and price action is what matters — narratives and opinions, his own included, are subordinate to what price is actually doing.

- **A viewer's "you should quit trading" and a $500K rebuttal.** Recounting an exchange from a few days earlier: "someone told me last week, 'hey, I see you're long [this stock], you should stop trading, you should quit trading' — and that was literally one of the first two days after I bought it. The stock is up 25% since, and I'm up like half a mil on it. Kind of funny — maybe he's the one who should stop trading." He generalizes the lesson immediately, applying it to his own opinions just as much as anyone else's: "you can have personal opinions about the stock — you hate the product, you had a bad customer service experience, whatever — all of that doesn't matter, price action is king. Your opinions don't matter, my opinions don't matter, they just don't. We tend to believe they do, but they don't — that's just the way it is."
  - *2020-08-05, t=691s*

This is the same discipline as 5.7's Tesla short-to-long flip, applied to *narrative* rather than a single directional thesis: a personal opinion about a company, a Fed decision, or a political headline is treated as noise with no execution value, precisely because none of it changes what the chart is actually doing — and the $500K gain on a stock he was being told to abandon is the concrete evidence that following the opinion instead of the price would have been the costly choice.

### 6.10 Case study: the GameStop/meme-stock squeeze (January 2021)

This period produces an unusually large amount of real-time, specific commentary that doubles as a live regime read.

- **"Never short day one" gets a real casualty attached to it.** Reviewing the week's trades with his stream, he calls out a friend directly for shorting GME the day it broke out of a high-tide flag: "why did you short it on day one? Never short on day one, never ever short on day one — it was just breaking out of a high-tide flag, why were you shorting? ... You cannot save yourself. As a swing trader you don't short day one, you wait for those perfect opportunities, that's where your edge comes in — let the amateurs short day one, let them get squeezed, take a bunch of losses." Asked afterward if he'd gotten squeezed shorting GME on day one himself, the answer is a flat "bad mistake" — followed by his own admission that this specific rule took him "so long" to actually learn.
  - *2021-01-26, t=3774s*
- **What being "right" on the short still cost him.** Separately, even after finally shorting into confirmed weakness rather than day one, the position carried a real, painful cost that had nothing to do with the stock's direction: "I paid like $150,000 in borrow fees since yesterday on GME... I don't want to be in it for a long time." This is the live version of the borrow-cost discipline covered in Section 3 — being fundamentally and technically correct on a short doesn't mean the trade is free, and financing cost alone can rival the position's actual profit on an extreme-borrow name.
  - *2021-01-26, t=3865s*
- **The "why" is explicitly irrelevant to execution.** Throughout the mania he's consistent that a genuine short squeeze (a broken-model stock rising purely off supply/demand and forced short covering) gets traded exactly like any other technical setup — never shorting day one of a parabolic move, waiting for confirmed backside weakness — because the underlying *reason* a stock is moving (social-media-driven squeeze vs. any other catalyst) doesn't change what the chart requires of him as an entry.
- **A portfolio-level lesson, stated as a general risk-management rule rather than GME-specific:** even a small allocation (as low as 1-3% of a portfolio) to a name that later gets forced into a violent multi-thousand-percent squeeze can be enough to wreck an entire year's performance for anyone caught positioned against it — a point he ties directly to well-publicized hedge-fund losses from the same period, and uses to reinforce why position-concentration limits (Section 3) apply even to conviction shorts on "obviously" broken companies.

### 6.11 Case study: the 2022 bear market

The most sustained drawdown-regime commentary in the entire span, and a real-time test of the two-regime framework (6.1) and breadth-reading discipline (6.3) developed over the years before it.

- **The historical-shape comparison, made just two months in.** Early in the decline, asked whether this is really a bear market: "it depends how you look at it — a significant portion of stocks are in a bear market, it's just the big indices holding up and masking it. If you look at the Russell, it's almost in bear-market territory. But this has only been two months, it's nothing — bear markets can be years. You get legs down, multi-month bear-market rallies, that stalls out, you get chop, then it rolls over again. Study the markets from mid-2000 to early 2003, or mid-2007 to early 2009, you'll see this. We've been going on for two months, it's nothing." A two-month decline, on his own framing, isn't enough data to say anything about the shape of the whole cycle.
  - *2022-01-21, t=1979s*
- **"Easy money" windows still exist inside a bear-market year — with two real, dated examples.** Explaining why the choppy tape pushed him toward leveraged ETFs: "these types of markets are better traded with ETFs, because everything kind of moves the same way anyway — it's just easy to do with triple [leveraged] ETFs." He's explicit that the current stretch isn't one of those rare windows: "an easy-money environment, you can double or triple your accounts in a couple of months — this is not it, this is not an easy-money environment, not even for day traders, because you don't get a lot of individual stocks moving on their own, everything is super correlated." He names the signal that would tell him a window is opening — "it's when you start seeing things decoupling from the indices that's when you know better times may be ahead" — and cites two real, dated windows from the prior year as proof they're recurring, not rare: "easy-money environment, January-February 2021, mid-October to mid-November last year — and we're gonna have one or two easy-money environments this year, I'm 100% certain. There's a couple of easy-money environments every year, even during bear-market years."
  - *2022-02-01, t=1691s*
- **The earnings heuristic that emerges from this stretch, with a named example.** "A good report won't help you if the stock goes down, and a mediocre report — as long as it's a surprise — can make a big move. It's not about good or bad, it's about better or worse than feared." Watching the regime start to turn: "right now we're slowly starting to see 'buy the dip' starting to work again — stocks are reacting well to bad news, like Wayfair." A market rewarding an outright bad number, in his framing, is a more meaningful bullish regime-change tell than any single good headline.
  - *2023-01-26, t=1032s*

Leadership itself splits into two distinct patterns depending on the type of decline: during the bear market's deepest, fastest sell-offs, the most beaten-down names tend to lead the recovery's first leg; during shallower pullbacks within an ongoing uptrend, it's instead the names already showing the most relative strength that lead once pressure lifts — an explicit, named distinction between "recovery from a crash" leadership and "pullback within a trend" leadership that ties directly back to 6.3's breadth-reading framework.

### 6.12 Sitting out is a valid, even superior, strategy

During choppy or unclear stretches, deliberately doing less — fewer trades, smaller size, or no trades at all — is repeatedly framed not as passivity but as a specific skill, one that most losing traders fail to exercise because it's psychologically uncomfortable to do nothing while others are (apparently) making money.

- **"Our job is not to trade, our job is to wait."** On a dead, directionless session: "this market is so sluggish, man — and this is what the market is most of the time. It's not really going up, it's not going down, it just exists. The market is open, and it doesn't really mean anything — it could as well be closed, it's not gonna make a difference. Our job — our job is not to trade, our job is to wait. That's our job. And once you understand that, you have a good shot of making it in trading — unless, obviously, everything else is in place too: risk management, setup identification, all of that."
  - *2021-04-20, t=3253s*

The reframe is deliberate: patience isn't presented as a special discipline reserved for obviously bad markets (6.1's hard-penny regime, 6.2's chop) — it's presented as the *default* state of the job, since a genuinely tradeable market is, by his own accounting, the exception rather than the rule (6.11's "1-2 easy-money windows a year, even in bear years"). Everything else in this section — reading breadth (6.3), timing breakouts to correction resolutions (6.5), watching his own position count (6.6), catching his own euphoria (6.7) — exists to identify the specific, comparatively rare windows where the job actually is to trade, rather than to wait.

---

## 7. Watchlist & Stock Selection Criteria

This is the filtering layer that runs before any of Section 1's setups even get considered — what makes it onto the screen at all, and what gets dismissed before a chart is ever pulled up.

**Citation format:** same as Sections 1-6 — video title, upload date, and timestamp where known, in a sub-bullet under each example.

### 7.1 The primary gate — ADR and dollar volume, before anything else

Before a chart is judged on pattern quality, it has to clear two numbers: average daily range (ADR%) and average dollar volume. Both are treated as binary gates, not soft preferences — a stock that fails either one doesn't get a second look regardless of how clean the setup looks.

- **"Low ADR is equal to [garbage], high ADR is equal to gold."** Delivered while passing on an otherwise decent-looking setup for no reason other than its range: "like that, that would have been a good setup, but you know it doesn't matter how nice it looks if it's a low-ADR stock, it's [garbage], you shouldn't be trading this thing, you should never trade [garbage]. Low ADR is equal to [garbage], high ADR is equal to gold."
  - *2020-08-10, t=3387s*
- **Costco as the standing negative example.** Pulled up live and picked apart twice in the same session: "avoid stuff like Costco, the guys — don't even look at something like this, you will never make any money trading something like it, it's too slow... you want stocks that have an average daily range of at least four percent, maybe even five or six percent." Minutes later, with the number on screen: "ignore Costco, there's — ignore, just don't talk about it, there's nothing there, it's 1.5 percent ADR, no reason to trade something like this."
  - *2020-08-03, t=2301s, t=2331s, t=2406s*
- **The five percent ADR rule, codified.** By late 2021 the standing that guides screening gets stated as an explicit, named cutoff: "the five percent ADR rule is a very good cutoff for stock selection, you get rid of ninety-five percent of the time-wasting stocks — and even that is not a guarantee, you still have to do discretionary analysis."
  - *2021-09-16, t=2410s*

Put together, the throughline is that liquidity and volatility are prerequisites, not tiebreakers — they're checked before any pattern work begins, which is why Section 2.9's chart-reading treatment of ADR and Section 3.7's ADR-based stop sizing both assume this gate has already been cleared.

### 7.2 The actual scan mechanics — what the screens really look like

- **The dollar-volume cutoff scales with account size, not a fixed number.** Walking through the exact formula live: "take your account size and multiply it by 50, or multiply by a hundred even better — so if you have a fifty-thousand-dollar account, your volume cutoff should be five million. If you have a two-hundred-thousand-dollar account, your volume cutoff should be twenty million. And no one should have less than, say, two-three million dollar-volume cutoff on their scans — there's no reason to trade stocks that trade less than a few million dollars worth of stock, it's just too random." Later in the same session, building a new scan from scratch in TC2000: "no one should have less than five million in dollar volume, everyone should probably put at least ten million in dollar volume cutoff" — with Visa singled out as the standing example of a stock that clears every liquidity bar and is still "just a waste of time."
  - *2020-08-12, t=2708s, t=3429s, t=3290s*
- **The scans themselves are deliberately simple — three timeframes, nothing exotic.** Asked directly what scans he runs: "I just scan for the strongest stocks on every timeframe — one month, three months, six months. Scans are just scans, like anyone can scan, scans are the easy part, it doesn't really matter what scans you run." He mocks the opposite failure mode in the same breath — traders who "have like fifty things in their scans."
  - *2020-07-08, t=2248s, t=2324s*

The mechanics are almost anti-climactic on purpose: rank by relative strength across a handful of lookback windows (1/3/6 months, sometimes extended to 9/12/18), filter by the account-scaled dollar-volume and ADR cutoffs from 7.1, and stop there. The edge isn't in the scan's sophistication — it's in the discipline of actually running it every day and then applying the pattern recognition from Section 1 and 2 to whatever survives.

### 7.3 Fundamentals as "fuel," never the trigger

- **"Earnings are fuel" — the one-line summary of where fundamentals fit.** Reviewing a growth-stock watchlist live, triple- and quadruple-digit EPS and revenue growers side by side: "focus on the growth stocks, because earnings are fuel, okay, you need fuel, you need a reason for something to go up. Stocks don't go up just because — you find the stocks that have a reason to go up, and then you look for patterns on those stocks." In the same scan, a hot-sector name with weak revenue growth still gets included specifically because sector heat substitutes for the fundamental case — see 7.6.
  - *2020-12-17, t=3616s*

The consistent pattern across the corpus (see the batch notes on MarketSmith/Koyfin growth screens, general principle rather than a single re-verified clip) is that revenue and EPS growth are checked *after* a technical setup is already on the table, never used to source ideas on their own. A stock with no chart doesn't get bought because its growth numbers are exceptional, and a stock with a five-star chart doesn't get passed on because its fundamentals are thin or unknown — fundamentals raise conviction and holding power through a shakeout, they don't replace the pattern as the actual buy trigger.

### 7.4 Institutional-quality names vs. pure pump stocks — knowing which bucket you're in

- **The original framing, drawn live off a chart comparison.** "There's two types of stocks — you have the institutional-quality stocks, which I'm mostly in, and then there are the pure, like, pump stocks — the ones that are data-driven by retail buying, by chat rooms, by Wall Street Bets, you know, the Robinhood type of stocks... if it's a higher-priced stock that's trending and riding the rising 10- and 20-day moving averages, that's an institutional-quality stock."
  - *2020-07-10, t=2101s, t=2151s*
- **The same taxonomy, restated a year later with sharper language.** "There's two types of stocks that make big moves: global leaders, and — what should I call them — hype stocks, or pumps, and sometimes even outright frauds. And I have a combination of them, I have some pumps and I have some global leaders."
  - *2021-03-31, t=3633s*

The two clips are a year apart and use different vocabulary (institutional-quality vs. global leader, pump vs. hype stock), but they're the identical mental model: a deliberate two-bucket portfolio, held simultaneously, with each bucket getting different size and conviction treatment (see 3.2 on the small-account edge and 3.6 on margin discipline). The tell for which bucket a stock is in is mechanical, not narrative — price behavior around the 10/20-day moving averages, not the story behind the ticker.

### 7.5 Proactive theme-building — watchlists made before the theme is obvious

- **The coronavirus sector list, built and scolded into viewers in real time.** Frustrated that almost no one else was tracking it: "I have to say I'm a little bit disappointed, guys — how are you not monitoring these coronavirus stocks, it's the hottest sector, only one person saw it, and that person didn't even buy it... if you have a hot sector like this, you have to monitor it, you have to create a watchlist and scroll through all of the stocks during the day. I have 40 coronavirus stocks in my watchlist, sorted by dollar volume — most of them are too illiquid for me to trade, but I go through the liquid ones every day."
  - *2020-03-04, t=2743s*
- **The AI/quantum-computing list, built months ahead of the run.** Three years later, the identical discipline, with the payoff arriving on stream: "the list of AI and quantum computing stocks that I made back in January is finally starting to pay off, these stocks are starting to run one by one... it's all about preparation, guys. This list, AI and quantum computing names, I made this list back in January, I shared it on Twitter even." The catalyst he names for the theme is broad and structural, not stock-specific: "the market is waking up to the fact that AI is gonna need a lot of computing power" — the list existed before that realization was consensus.
  - *2023-05-23, t=1213s, t=1507s*

The three-year gap between the two examples is the point: proactive, hand-built theme lists aren't a one-off habit tied to one unusual market (2020's COVID crash), they're a standing practice applied to whatever the next speculative theme turns out to be. The work is manual and unglamorous — scrolling dozens of loosely related tickers daily, most of which never move — and it's explicitly framed as something "no one else is gonna do... you gotta put in the work" (general principle, recurring across many videos), which is also why it recurs as a competitive edge rather than a scan output.

### 7.6 "The shittier the stock, the bigger the move"

- **Blink Charging as the named illustration.** Comparing two speculative EV-charging names live: "SBE is a non-scam. Blink? Okay, all I needed to know — yeah, Blink is a super scam, and that's the leading one. That's what I keep telling — that the shittiest stock makes the biggest moves. It's kind of funny how it works."
  - *2020-12-18, t=1137s*
- **The GLP-1/weight-loss theme, flagged the same way in real time.** Naming the next hot theme as it's forming: "another theme that's really hot right now is the weight-loss, the weight-loss drugs, the GLP-1... I hope the weight-loss — like, smaller and mid-cap weight-loss-related stocks are going to wake up eventually and make you, you know, five, ten [baggers]." The batch notes describe the same logic applied to the list itself: every loosely related name gets added, since it's usually a handful of junk names, not the category leader, that end up being the 5-10x movers.
  - *2023-12-01, t=2201s*

The mechanism isn't superstition — it's supply and demand. A low-quality, high-share-count name with no natural institutional buyer has almost unlimited room to re-rate on pure speculative flow, while a well-owned quality name in the same theme already has a "fair" price largely set by funds that already hold it. That's also why this rule doesn't contradict 7.4's institutional-quality framework: it's a description of which *bucket* produces the largest percentage moves, not a reason to abandon risk discipline on the pump-stock side of the portfolio.

### 7.7 Real-name-brand backing as a credibility signal — and its limits

- **QuantumScape vs. Nikola — the same "big names behind it" heuristic, cutting opposite ways.** Reading up on QuantumScape live: "Volkswagen is a big owner, it's backed by Bill Gates, this thing is interesting... when you have multiple big names behind something, I think the odds of success are higher — obviously Nikola being the exception, they kind of duped everyone. GM — I wonder how much due diligence General Motors did on this company, what a bunch of overpaid idiots."
  - *2020-12-03, t=2893s, t=2950s*

Credible institutional or brand-name backing is used as a probability adjustment, not a guarantee — and the Nikola example is kept in the story specifically *because* it broke the rule, not despite it. The honest lesson isn't "big names mean it's safe," it's "big names raise the base rate enough to justify a closer look," which is a softer, more defensible claim than the pattern would suggest if only the QuantumScape half of the comparison were told.

The signal is also treated as secondary to the technical setup, consistent with 7.3's "fundamentals as fuel" framing — brand-name backing is cited as a reason to hold a position with more conviction through a shakeout once a real setup is already in place, never as a standalone reason to buy a chart that isn't there yet. And the Nikola exception carries forward: the same skepticism toward loud institutional validation resurfaces in 7.12's account of Chinese-ADR distrust after the Luckin Coffee fraud, where a credible-seeming name (backed by real revenue claims and legitimate exchange listing) turned out to be the exact kind of story this heuristic is supposed to catch but occasionally misses.

### 7.8 What gets filtered out entirely

- **Short-seller hit pieces — mostly noise, occasionally right, never a standalone reason to avoid a stock.** Walking through a name that had been targeted repeatedly: "there's been short-seller pieces on it since many years back... 'we believe the stock is worth no more than a dollar and a cent per share,' this hit when the stock was six bucks, two years ago — and there's been several hit pieces since, Citron hit it here too, and now look at the stock... the market apparently doesn't agree, just follow the price. These hit pieces — GSX too, if you'd just traded the setups you would have made money, GSX was hit by both Citron and Muddy Waters and then boom, went up three hundred percent in a couple months." He immediately balances it with the times the short sellers were right: "sometimes they nail it, like Muddy Waters nailed Sino-Forest back in 2011, day two of my trading career, that thing went down ninety percent in two days" — and, elsewhere in the same session, Citron hitting Shopify near $100 and being "just so wrong."
  - *2020-08-19, t=2716s, t=2795s, t=2820s, t=2918s*
- **Fundamentals-blind trading, with one explicit exception: real halt risk.** Asked whether he'd bother checking the fundamentals on a speculative runner: "would I bother checking out the fundamentals for [it]? I don't need to, they're probably [garbage], doesn't matter. I made a lot of money trading [garbage] stocks, frauds, sketchy companies, doesn't matter — unless it's something that's a legit halt risk, now that's another thing." He grounds the exception in the Sino-Forest case specifically: "they had guys outside the factory filming the traffic for a month, and we think ninety-nine percent of this company's revenue is faked... it went down ninety percent in three days and got delisted. If someone comes out with a real short thesis, that's called halt risk — don't go long that stock, especially not overnight."
  - *2021-03-12, t=5606s, t=7106s, t=7203s*

The two filters aren't the same thing, and keeping them separate matters: a stock being low-quality, fraud-suspect, or hit by a short report is not by itself a reason to avoid it — the price action is. The one carve-out is *credible, evidence-based* fraud allegations (fabricated factory traffic, fabricated revenue) that carry real halt/delisting risk, which is a position-management problem (don't hold it overnight) rather than a watchlist-filtering one.

### 7.9 The liquidity test — placing a real test order

- **The test-order method, stated as a literal procedure.** "You set an order for say ten percent of the average volume, and then you buy and see what happens — that's how you know if it's liquid or not. If you get filled without slippage, you know it's liquid. If you only get filled on a few shares up to your limit, then you know it's not liquid. And once you know it's liquid, you're gonna market-order the [heck] out of it in the future." He backs it with a concrete result from the same session — buying and selling roughly a quarter of a day's volume in a $53-54 ETF with only "a couple pennies of slippage," calling it proof of "how insanely liquid" some ETFs are, "not all of them."
  - *2021-03-11, t=2669s, t=2567s*

The test matters because headline share volume and dollar volume can both be misleading, especially for ETFs where market-maker creation/redemption means real capacity often exceeds what raw volume numbers imply (see the ETF-rotation note in 3.5 and the batch-note reference to TNA/GBTC/SMH-era ETF trading). Rather than trusting the scan output blindly, the actual liquidity of a name gets verified once, empirically, with real size — and after that first test, the result is trusted going forward instead of re-litigated on every entry.

### 7.10 "Our job is to be in the stocks other funds want"

- **The line stated directly, as a rebuttal to value-investing logic.** Responding to a viewer's fundamentals-based framing of a trade: "our job is to be in the stocks that other people want — or actually, other funds want, that's our job." He contrasts it with what he considers a losing mental model: traders chasing "hidden value on some obscene company that no one else finds hidden value in," adding that if that style of investing genuinely worked, its practitioners wouldn't "underperform the market year in, year out."
  - *2021-11-12, t=343s*

This reframes the entire watchlist-building exercise in 7.1-7.9: the goal was never to find stocks the market has mispriced and is about to "discover" — it's to identify which names institutional capital is already choosing to flow into (visible in price, volume, and relative strength) and get positioned alongside that flow before it's finished. It's the same logic underlying the CAN SLIM-style filters referenced in the batch notes — current/annual earnings growth, a new catalyst, supply and demand, market leadership, institutional sponsorship — treated as a description of what a stock other funds want *looks like*, not an independent value framework of its own.

### 7.11 A stock's "personality" — reading repeated stop-outs as a fit problem

- **IMPX as the named "devil stock."** After the fourth or fifth stop-out on the same name in one session: "I got stopped out of a hundred thousand shares of IMPX, I hate this stock, why do I hate this stock so much? Maybe because it always stops me out, that's why I hate it, it's like the devil stock, it really is." He generalizes the observation a few minutes later, unprompted: "all stocks have different characteristics, and some — like IMPX's characteristic — also..." He goes on to take a $35,000 loss on the same name later in the session, still trading it despite naming the pattern out loud.
  - *2020-05-21, t=2431s, t=3432s, t=4697s*
- **A second name, same session, same read.** On a different short candidate stopping him out repeatedly the same day: "the problem is it's such a [choppy] short, I got stopped out like two, three times on it — every time it breaks out, it pulls back and stops you out, it never gets going, this is the problem with this one."
  - *2020-05-21, t=3414s*

The synthesis he states himself is the useful part: recognizing a name's "characteristic" is treated as data about fit, not as a reason to force the trade harder. In practice this doesn't always translate into instantly dropping the name (see the $35,000 IMPX loss taken in the same session after already naming the pattern) — the lesson functions more as a standing caution than an automatic hard rule, closer in spirit to the small-account-edge tension in 3.4 than to a clean, always-followed filter.

### 7.12 The Luckin Coffee fraud and its ripple effect on Chinese-ADR trust

- **Real-time contagion trading on the day the fraud broke.** Watching Luckin Coffee (LK) halt repeatedly through the session: "LK is pretty amazing, seventy-six million shares and it's been halted most of the day so far, it's been trading for like three or four minutes... yeah, LK, I wouldn't be trading this thing, exactly, halt risk is huge, absolutely." In the same session he extends the suspicion to an unrelated China-listed name purely by association: "another [name is] speculating that it's GSX, which is also not a crazy [claim], a stock from China may also be cooking their books too... keep an eye on this GSX, if they lose faith in these [China] names, this thing is gonna go to 20." He acts on the suspicion directly: "I shorted a bunch of GSX, nothing crazy, but man, if they lose confidence in this thing... this thing is gonna be down thirty percent in a few days."
  - *2020-04-02, t=1610s, t=1668s, t=1230s, t=1339s, t=1540s*

This is the origin point of a distrust that shows up repeatedly elsewhere in the corpus — GSX gets flagged again as a possible books-cooking risk in the following weeks (see batch notes, 2020-04-03), and the general skepticism toward Chinese-ADR accounting becomes a standing background caution rather than a one-off reaction. It also complicates the "ignore short-seller hit pieces, just follow the price" rule from 7.8: Luckin is explicitly named later (2021-03-12, see 7.8) as one of the cases where the short sellers were actually right, which is the honest reason the halt-risk carve-out exists in the first place — a credible fraud allegation on a China-listed name gets taken more seriously after Luckin than it would have before, precisely because the base rate for that specific category shifted.

---

## 8. Psychology & Mindset

**Citation format:** same as Sections 1-7 — date and timestamp in a sub-bullet under each example.

### 8.1 Emotion is not the enemy — channel it, don't suppress it

- **A direct rejection of "trade with no emotion" advice.** Asked how he handled a recent bout of frustration: "you can't manage your emotions, and I think people who think you should manage your emotions — I think you're full of [it], you should just accept the emotions." He immediately connects the unmanaged version of this to a specific personal weakness (see 8.10): "this is why I overtrade, I'm a chronic overtrader — sometimes I just put on trades I know they're not optimal, but I do it in smaller size just to get that fix, I need my fix, that's how it is... emotions like FOMO and whatever, they won't ever go away, they're always gonna be there."
  - *2019-10-25, t=2547s*
- **The same position restated, with the operative word being "channel."** "I think emotions are a very important part of trading — I don't buy into the [nonsense] that you should be emotionless, that you should suppress your emotions and feelings, and I think it's all [nonsense] from people who don't even trade or aren't successful traders. You should be emotional, but you should channel the emotions."
  - *2020-05-27, t=5739s*

The two clips, nearly a year apart, land on the identical claim: suppression isn't the goal, and pretending otherwise is itself treated as a tell that the person giving that advice doesn't actually trade. What "channeling" means in practice is the mechanical rule-following covered in 8.2 — stops, sizing, predefined setups — functioning as the outlet that absorbs the emotion instead of pretending it isn't there.

### 8.2 Discipline over being right — "love your stops, not your dogs"

- **Reframing a stop-out as neutral information, not a personal attack.** "You're not gonna feel disappointed when you get stopped out, because you take it personally — don't take it personally, the market is just telling you, hey, wait a minute, I'm not ready yet, the stock is just telling you, I'm not ready — the stop is a way for you to protect yourself, it's all about framing. Instead of thinking, oh, the market makers are counting my stops, the market's against me — no, it's all about, hey, it's okay, the stock is telling me it's not ready yet, and now I have to regroup and wait for a better setup."
  - *2020-06-19, t=2557s*
- **The line credited to Dan Sanger.** Immediately following the reframe above: "love your stops — and I learned that from Dan Sanger — don't love your dogs, love your stops."
  - *2020-06-19, t=2614s*

The two pieces are one idea, not two: a stop is easy to "love" mechanically only once it's been stripped of the personal sting, which is exactly what the not-ready-yet reframe is doing. This is the psychological engine behind the mechanical stop rules covered in Section 4.2 — the discipline to actually take a stop at the close, every time, depends on this framing being internalized first.

### 8.3 Patience and boredom tolerance as the central skill

- **The one-line summary of the entire skill.** "Remember, it's not the most active trader who wins, it's the most patient trader who wins at this game."
  - *2020-09-02, t=2639s*

Trading is repeatedly described as roughly 90-95% waiting and boredom (general principle, recurring across many videos in the batch notes rather than a single re-verified figure), with getting visibly excited about a trade treated as a personal warning sign to size down, not a green light to size up. Real intuition — as opposed to noise dressed up as a gut feeling — is only considered reliable after roughly five years and thousands of hours of screen time. Sitting in cash with nothing to do is treated as correct, not a failure of activity, and the batch notes describe patience specifically as tolerance for *doing nothing* through slow, low-opportunity stretches — sometimes literally trading almost nothing for days at a time — so that maximum aggression is still available whenever a real setup actually shows up.

The throughline connects directly to 8.10: boredom tolerance and overtrading are framed as the same muscle, just exercised in opposite directions, which is why managing one so often means managing the other. It's also the psychological precondition for 6.12's "sitting out is a valid, even superior, strategy" — a rule that only survives contact with a genuinely slow market if boredom itself has already been made tolerable.

### 8.4 Losses and drawdowns as the cost of doing business, not a personal failing

- **The loss ratio, given as an honest estimate rather than a precise figure.** Asked how much he loses for every dollar he makes: "I don't know, I could probably find out, but obviously I do take a lot of losses too — but my, I guess, would be for every million in profits I have maybe eight hundred thousand in losses, I don't know the exact number, but that's a guess, I don't know, maybe even nine hundred K in losses."
  - *2020-09-04, t=2908s*
- **Drawdowns named explicitly as structural, not a failure of process.** Asked how he avoids drawdowns: "you don't. Drawdowns are a feature, not a bug — now the key is to keep the drawdowns as small as possible." Pressed on his own worst stretch: "my longest drawdown after I became a profitable trader was in 2015... it was a nine-month-long drawdown, I went sideways for nine months, that was pretty — that sucked."
  - *2020-09-24, t=2636s, t=2737s*

The two claims fit together deliberately: a roughly 80-90-cents-lost-per-dollar-made ratio only makes sense as a business model if drawdowns of many months are accepted as a normal, recurring feature of the process rather than evidence something is broken — which is precisely why the nine-month 2015 stretch is offered as the standing worst-case example rather than something hidden or downplayed.

### 8.5 Reviewing and owning mistakes publicly, in real time

- **A monthly video built entirely around cataloging his own mistakes.** Opening a dedicated recap: "let's do a recap of my February trading and go through some of the most notable mistakes I made during the month — both stupid losses and like five-star setups where I didn't capitalize, because of sizing, or I missed them completely. Every month I go through my mistakes, and every month I realize that I could have made 50 to 100 percent more money that month if I just eliminated or minimized the top five biggest mistakes."
  - *2017-03-22, t=7s*
- **The framing for absorbing any single mistake, stated plainly.** "It's not about how many times you fall, it's about how many times you get up — that's what separates the successful traders from the ones who aren't successful. You should always try to learn from your mistakes — if you froze yesterday, what's your plan of not freezing again?"
  - *2020-09-04, t=374s*

The monthly-review habit, run consistently enough to be a recurring video format rather than a one-off, is the concrete mechanism behind the get-up-not-fall-down framing — mistakes aren't just tolerated in the abstract, they're actively logged, quantified (50-100% of a month's returns, by his own estimate), and turned into next month's specific fix. This is also the same instinct behind narrating real-time errors on stream elsewhere in the corpus (early stop-outs, oversized earnings holds, fat-fingered orders) rather than editing them out — the review process only works if the raw material isn't hidden in the first place.

### 8.6 Complacency after success — danger peaks right after the easiest stretches

- **A live, unprompted admission of losing his edge mid-hot-streak.** Explaining a decision to skip paying for a borrow he'd normally cover: "I've had a really good trading couple of months — like half of the money I've ever made is from the past two months — so you kind of get complacent, you kind of lose your hunger a little bit."
  - *2020-06-22, t=1354s*
- **The explicit countermeasure during the QuantumScape/battery-stock mania — going more defensive exactly as things were going best.** "When the market turns, when the speculation money leaves, you gotta be so careful, you could give back half of what you made — so I'm pretty much... on red-alert mode here. The more craziness we see, the more cautious I get, I refuse to give back any profits — I've been there so many times, I double, triple my account and give back half." He generalizes the response: "when you start seeing warning signs, you gotta be proactive — shoot first, ask questions later, that's how you have to be."
  - *2020-12-09, t=3049s, t=3531s*

The two clips show the same risk from both sides: the honest admission that his own hunger genuinely fades after a great stretch (6.6, 6.11), paired with the deliberate, named countermeasure — treating a hot streak as the moment to get *more* careful, not less, since it's specifically when euphoria and overreach have historically produced his largest losses. This is the psychological root of the margin-discipline and de-risking behavior covered mechanically in 3.6 and 6.4.

### 8.7 Real skill isn't transferable secondhand — borrowed ideas vs. earned conviction

- **The line, and an unusually candid admission behind it.** "You can steal ideas, you can't borrow conviction, that is very true. I've stolen every single trading concept I use — or let's say borrowed, I borrowed everything, I haven't come up with any of the things I use, not a single thing."
  - *2021-11-05, t=2530s*

The claim isn't false modesty — every specific technique discussed elsewhere in this document (the moving-average rules, the ADR filters, the "love your stops" line itself in 8.2) is explicitly credited to someone else (O'Neil, Sanger, Minervini, Livermore). What he presents as genuinely his own is the conviction layer on top: thousands of hours spent personally verifying which borrowed rule actually holds up against his own sample of historical charts, which is the only part of the process that can't be shortcut by simply copying another trader's picks or rules wholesale.

The batch notes describe the same principle applied bluntly to the practice of copy-trading specifically: following another trader's individual stock picks is said to never produce consistent profitability on its own (general principle, recurring across many videos), because a borrowed pick without the underlying pattern recognition behind it is just a tip, not a repeatable process. Relatedly, verifying any specific rule — which moving average actually works for a given kind of stock, for instance — against a large personal sample of historical charts, rather than taking any mentor's word for it, is presented as how genuine conviction, the kind that survives a drawdown without being abandoned, actually gets built. That verification habit is the concrete version of Section 10's "core skill-building method": thousands of annotated charts, accumulated individually, rather than a shortcut through anyone else's homework.

### 8.8 "Psychology" problems are usually edge problems in disguise

- **A trading coach, dismissed outright — with a specific reason, not just a shrug.** Asked live whether a trading coach is worth paying for: "is a trading coach a good idea? No, it's a waste of time... you don't need a trading psychologist." Pushed on what these services are actually selling: "what you need is not some coaching, you need coaching *in the context of a setup* — what you need is a setup, and knowing when the trade is set up, and knowing when to take a step back. That solves 99% of your problems." On what the coaching itself typically consists of: "what do these trading coaches do? Are they gonna tell you, 'oh, you should meditate 15 minutes before market open'? It's just a bunch of [nonsense], none of those things are gonna help you... look what he's selling — he's selling hand-holding. You pay him money and he's gonna hold your hand."
  - *2021-01-21, t=3202s*

The underlying claim is specific, not just dismissive: discipline is presented as something that emerges naturally once a trader has deeply internalized a specific setup's actual statistics — when it works, when it fails — rather than a separate character trait that can be trained on its own, independent of the underlying skill. This reframes most of what looks like a "psychology" problem elsewhere in this section (8.3's impatience, 8.10's overtrading) as downstream symptoms of an under-studied setup rather than a standalone deficiency, which is also the direct argument for the chart-study discipline described in 8.7 and Section 10's "core skill-building method."

### 8.9 Extreme ownership — rejecting manipulation narratives and external blame

- **The rule stated as absolutely as any in this document, with a book recommendation attached.** "Everything that happens to you is your fault — if you lose money on a trade, your fault. It's not the market makers that were gunning for your stops, it's not... someone who announced something, blah blah — no, it's your fault... responsibility and fault." Asked directly whether he'd recommend the book: "have you read the book *Extreme Ownership*? I read like two-thirds of it, by Jocko Willink — it's like one of the best trading books I've ever read," despite it not being a trading book at all.
  - *2022-04-06, t=2142s, t=2188s*
- **The same rule applied specifically to "algo manipulation" complaints, a full year earlier.** Asked whether he ever struggles with anger at perceived market-maker manipulation: "no — one, there are no market makers, it's all algos, and two, there's no manipulation, it's called a market... forget about the algos, they're irrelevant, sometimes they work for you, sometimes they work against you, they're just doing what humans used to do. The algo doesn't give a [care] about your stop, they mostly don't even see your stops if you have a good broker. Get used to getting stopped out, okay — get used to getting stopped out."
  - *2021-09-17, t=2891s*

The two clips, a year apart, are the same conclusion from opposite directions: one names the specific villain traders like to blame (market-maker manipulation, algo stop-hunting) and dismantles it mechanically, while the other states the resulting policy as a blanket rule with a borrowed name attached. Emotional control specifically is treated as something that "cannot be taught remotely" through books or streams — only built through direct, personal, often painful experience over years (general principle, recurring across the corpus) — and he treats anyone claiming to have fully solved it with open suspicion.

### 8.10 Chronic overtrading — his own most self-identified recurring leak

- **Self-diagnosed early, and treated as a permanent trait to manage rather than a phase to outgrow.** "This is why I overtrade, I'm a chronic overtrader — sometimes I just put on trades I know they're not optimal, but I do it in smaller size just to get that fix, I need my fix, that's how it is. I do small stupid things on purpose to avoid doing big stupid things later, if you understand what I mean — I need to get my training fix." His stated countermeasure, offered without irony: "that's why I play World of Warcraft, to take my mind off trading."
  - *2019-10-25, t=2564s*
- **The same underlying compulsion, renamed and still unresolved more than two years later.** "I'm not over-trading, but I'm over-clicking — I'm constantly looking for trades, my finger clicking like a maniac. That's how I get my dopamine kick, that's how I keep the addiction under control."
  - *2022-02-04, t=2676s*

The two-and-a-half-year gap between the examples is the honest part: this isn't a beginner's mistake he later solved, it's a standing personal weakness he manages with substitutes (video games, deliberately smaller "fix" trades) rather than ever claiming to have eliminated. It's also the clearest real-world instance of 8.1's "channel it, don't suppress it" principle — the FOMO and restlessness don't go away, they get redirected into activities and small, contained trades that don't threaten the account.

### 8.11 React, don't predict — trader vs. investor mindset

- **The line stated as a direct trading maxim.** "You have to listen to it, not predict it — that's the thing, there's no money in prediction, but there's a lot of money in listening."
  - *2021-02-05, t=4036s*
- **"Never fall in love with or hate a stock" — the same idea applied to individual positions, with a named example.** Asked why he was bullish on a name purely because it was going up: "you should never love a stock, it's just all vehicles, trading vehicles — you should never fall in love as a trader, you should never fall in love with the stock, you should never hate it either. Because, you know, you may love [it], but [it] doesn't love you back — [it] doesn't know who you are, doesn't care about you." He applies the identical caution to the QuantumScape mania in the same session: "it's very important to have specific rules and not to fall in love with these things — do they have a potential game-changing battery technology? Yes, but... just because this thing is hot right now, up a thousand percent in a month, you should be really careful, don't fall in love with these things."
  - *2020-12-22, t=3894s, t=4225s*

Both quotes describe the identical discipline at two different scales: don't have a fixed opinion about where the market is going (listen, don't predict), and don't have a fixed emotional attachment to any single stock, no matter how good its story or how much money it's currently making. This is the psychological foundation underneath the trader-vs-investor distinction elsewhere in the corpus — a technical breakout buyer sells on a sell signal no matter how good the underlying business is, precisely because the stock was never a relationship to begin with.

### 8.12 The origin story — blowing up the account early, and what actually changed

- **Three or four blown accounts in the first two years, by his own count.** Asked how much capital he started with: "I started trading with about, I don't know, five, seven thousand — but I think I blew up about, I don't know, three, four times in the first year or two years." Asked what changed: "because I learned how to trade, that's why — I did more of things that worked and less of things that didn't work, that's the reason I didn't blow up another three, four times. But it took me two years of full-time trading to get there."
  - *2019-11-11, t=3489s*
- **The $700,000 loss — proof the same flaw resurfaces even years after "learning how to trade."** Years after establishing himself, describing a stubborn, one-sided position: "what I did — when I traded mainly one stock on the wrong side, and I lost $700,000. I still have some mental scars I need to heal from before I can do that video, but it's definitely on the way... it wasn't that bad of a loss, it was about 20 percent of my equity, and I made it back in the next three weeks — so it did end well, but it's one of the biggest mistakes in my career, it was just so stupid."
  - *2019-03-10, t=1689s*

Read together, the two stories complicate the tidy version of the origin story: the first two years of blowing up repeatedly were a beginner problem eventually solved by "doing more of what worked" — but the $700,000 stubbornness loss happened well after that point, on a single mishandled position, showing that the underlying flaw (refusing to cut a loss quickly, covered as the single most-cited mistake in Section 9) never fully goes away just because a trader has become consistently profitable. What changes with experience isn't immunity to the mistake, it's the speed of recovery — three weeks to rebuild $700K, instead of a blown account.

---

## 9. Common Mistakes / What Not To Do

**Citation format:** same as Sections 1-8 — date and timestamp in a sub-bullet under each example.

### 9.1 Stubbornness — refusing to cut a loss, and fighting the tape

- **Fastly, repeatedly re-shorted against a runaway uptrend, for a cumulative six-figure loss in one session.** Convinced the stock was overextended after a 600% run: "Fastly, I'm gonna focus on the short side, can it go to 100 bucks? Sure it can, but right now this thing is up six hundred percent from the March lows... I just don't think the odds favor this thing." He shorts, gets stopped out for a loss, and re-shorts repeatedly through the day as the stock keeps grinding higher — "I lost 29K in like 30 seconds on this thing," then "I took a seventy-one thousand dollar loss on Fastly," then, still fighting the same thesis hours later: "I'm gonna take a nice loss on Fastly again — I'm down, closing in on 135K, my biggest loss in a couple of weeks."
  - *2020-06-23, t=616s, t=784s, t=1254s, t=3731s*

The instructive part isn't the size of any single stop-out — it's that he kept re-entering the identical short thesis on the identical stock as it kept proving him wrong, rather than accepting that the tape itself was the disconfirming evidence. This is the mechanical version of the $700,000 stubbornness loss covered in 8.12 — the same flaw (refusing to let price override a fixed thesis), just visible here across several re-entries in a single session rather than one large position held too long.

### 9.2 Chasing — buying a stock well past its actual breakout trigger

- **The rule stated directly, mid-scan.** "It's very important to buy them as soon as they start breaking out, not on the second day after they're already up a bunch from the entry point." Moments later, passing on a name for exactly this reason: "chasing — it's not good, you know, just wait, there's so many other stocks that are starting to set up."
  - *2020-06-18, t=1120s, t=1657s*

The mechanism is the same one covered in Section 1's entry criteria: a valid breakout has a specific, low-risk entry point close to the base, and every day past that point both raises the entry price and pushes the stop further away, degrading the risk/reward on what may still be a perfectly good stock. The Workhorse example in 4.5 shows the more expensive version of this same mistake — not just a slightly worse entry, but a full missed multi-bagger caused by exactly this kind of second-day hesitation.

### 9.3 Buying breakouts in a choppy, non-trending market

Cited repeatedly across the corpus (general principle, recurring across many videos in the batch notes) as one of the fastest ways to lose money: breakout strategies specifically require a market that's actually trending, and the same setup that works cleanly in a trending tape produces a string of same-day failed breakouts and whipsaw losses once the broader market shifts into chop. The batch notes describe this as a lesson he has had to "relearn" more than once rather than something solved permanently after the first costly stretch — a market correction is specifically named as the trigger, since the exact chart pattern that would resolve upward in a healthy tape instead reverses immediately once broader participation narrows.

The fix isn't a different setup, it's reduced size and frequency — only getting aggressive with breakouts once many setups are confirming across the market simultaneously (see 6.2's treatment of chop as the hardest regime to trade, harder than an outright crash), and treating an isolated "good-looking" breakout in an otherwise directionless tape as a reason for extra suspicion rather than extra conviction. This is the mistake-side mirror of 6.5's rule about the best time to buy breakouts being right after a correction resolves — the two are the same underlying read on market regime, just stated as what to do instead of what not to do.

### 9.4 Shorting too early, and the specific danger of day-one parabolic shorts

- **"Never ever short day one" — the rule delivered as an emphatic, near-absolute standalone principle.** Confirming a viewer had been squeezed shorting GME on the day it first broke out: "why did you short it on day one? Never short on day one, never ever short on day one, it was just breaking out of a high tide flag... just have one rule when shorting parabolic moves: one, there needs to be a parabolic, okay — never ever short day one, okay, ever, never ever. You cannot save yourself so much money, so much headache... you wait for those five-star opportunities, that's where your edge comes in. Let the amateurs short on day one, let them get squeezed, take a bunch of losses, lose their accounts." The viewer confirms the mistake moments later, and the response is direct: "bad mistake... it took me so long to learn that one day-one rule."
  - *2021-01-26, t=3782s, t=3803s, t=3893s*
- **The origin of the rule — his own account, in 2014, on PLUG.** "You may have heard of this stock, PLUG — I also shorted it back in 2014, last time my fuel cells were really hot, this thing went from like 50 cents to almost 12 bucks in a few months... I hadn't really defined this setup yet, I was aware these things can make big moves, but I didn't really have any concept of entries and exits, and I got squeezed — I was randomly shorting it, I lost, I think, like a quarter or a third of my account the day before, because I didn't know this setup, and I went really aggressive on it, I added to a loser, I did all of these stupid things you shouldn't do."
  - *2021-01-15, t=2469s, t=2550s*

Read together, these are the same mistake seven years apart, from both sides of the camera: an undefined entry rule on a parabolic short costs him a quarter to a third of his own account in 2014, and the rule that resulted from it — never short day one, wait for five-star confirmed weakness — is still being actively taught, and still being actively ignored by newer traders, in the middle of the 2021 GME squeeze. The correct approach, stated as the resolution to both stories, is to short *after* weakness is confirmed, never to anticipate a top on a stock that's still going up.

### 9.5 Holding through earnings or other binary catalysts without a plan

- **"Gambling, not trading" — the line drawn explicitly, in response to a viewer's suggestion.** Asked why not just buy before earnings reports for the extra pop: "well, go ahead, start buying stocks before earnings reports, you report back what will happen... that's gambling, not trading, and we are traders in this room — no gamblers welcome."
  - *2020-07-31, t=661s*

The distinction he draws isn't "never hold through an earnings report" — it's holding *purely out of habit or hope*, with no real thesis and no cushion, versus deliberately choosing to hold a partial, already-profitable position through a catalyst with a plan for both outcomes. The PDD earnings loss detailed in 4.8 (roughly $200,000, on a position held without that plan) is the concrete cost of ignoring this distinction rather than a separate lesson.

The same "gambling, not trading" label is applied elsewhere in the batch notes to buying ahead of a scheduled binary biotech data event specifically (general principle, recurring across the corpus) — a category treated as even less defensible than an earnings hold, since a biotech trial readout is a true coin-flip with no technical or fundamental edge on either side, versus an earnings report where at least price action and growth trends offer some prior signal. Both cases collapse into the same underlying rule: a scheduled, binary, all-or-nothing event is either sized and planned for explicitly in advance, or avoided entirely — it is never something to be inside of by default just because a position happens to still be open when the date arrives.

### 9.6 Overriding predefined rules, and freezing under pressure

- **Freezing during a live trade, named directly as unacceptable.** Reviewing a moment where he failed to execute a planned exit: "you froze and didn't execute well, that's not a good thing... you should never freeze. You should always have a plan for any scenario, should always have an out, and when that out triggers, you should just execute, no second thoughts."
  - *2020-09-04, t=240s*

This is the mechanical failure mode behind 9.4's PLUG story — "I added to a loser, I did all of these stupid things you shouldn't do" is a description of exactly this, abandoning a predefined plan mid-trade under pressure. Elsewhere in the corpus this same override shows up as "playing rocket scientist" — trying to outsmart a simple, mechanical trailing-stop rule with discretion in the moment (see 4.4) — and multiple narrated episodes across the years show the discretionary deviation consistently producing a worse outcome than simply following the system would have. The fix stated here is procedural, not motivational: define the "out" for every scenario in advance, so execution under pressure becomes a checklist item rather than a decision.

### 9.7 Options, CFDs, and forex — avoided almost entirely

- **Options named a "loser's game," with an honest hedge attached.** "I think options is a loser's game — but obviously there are people that make a lot of money in options, I just... can't recall a single person I've heard of, for every [winner], it's because it's so much harder."
  - *2021-02-03, t=1941s*

This is the softer, more qualified companion to the harder-edged options and CFD language already covered in 3.12 — the "sucker's game" framing there is about the lottery-ticket psychology options encourage, while this clip is specifically about the difficulty of the instrument itself: he doesn't claim options are unbeatable, only that he's never personally verified anyone doing it consistently, which is a meaningfully different and more careful claim. Forex gets folded into the same bucket in the batch notes with even less hedging (general principle, recurring across the corpus) — he says he's never seen or verified a profitable forex trader, versus many verified profitable stock swing traders, and treats that asymmetry itself as the reason to stay away from all three instruments until already consistently profitable trading straight equities.

### 9.8 Fat-fingered execution — a chronic, accepted cost of trading size

- **A weekly habit, and the one time it became a $1.5 million loss.** In the aftermath of his largest publicized loss: "that was a really dumb trade... those of you who have been on my stream for a while, you know I fat-finger trades at least a couple of times per week — I oversell, I double-click on the sell or buy button, that happens a lot, almost every week." Asked if he'd change anything to prevent it happening again: "I'm never gonna make a fat-finger trade again? No — they're always gonna happen, it was just an extreme scenario, that could have happened on any stock... I fat-finger all the time, at least a few times per week, that I accidentally buy or sell twice the size, but they're usually not on these ultra-momentum stocks. I don't think I can adjust to a point where that will never happen again — you just have to be fine with it."
  - *2020-07-30, t=544s, t=6031s*

The framing is deliberately unheroic: he doesn't present the $1.5 million loss as a freak, unrepeatable event, he presents it as the tail risk of an error he makes routinely and has made peace with as a permanent cost of trading actively and at size — the same acceptance-of-structural-cost logic that runs through 8.4's treatment of drawdowns. The specific danger named is compounding this same habit with leverage: "imagine you do a highly leveraged options trade [and] fat-finger it — things can go south so fast," which is offered as one more concrete reason options in particular are avoided (9.7).

### 9.9 Ignoring liquidity and borrow constraints

Committing size to a name — long or short — without first checking whether that size can actually be deployed and exited cleanly is treated as a distinct category of avoidable loss from a bad entry or a bad thesis (general principle, recurring across the batch notes). On the short side specifically, several otherwise good-looking setups are described as skipped outright purely because shares were unborrowable or prohibitively expensive to locate — a discipline that only makes sense alongside 3.5's examples of the inverse mistake (paying $22,800 in Nikola locate fees rather than passing, and the SPCE weekend-borrow-cost trade-off), since the two only work together as a coherent rule: know the borrow cost and availability *before* sizing into a short, then make a deliberate, priced-in decision either way rather than discovering the constraint mid-trade.

On the long side, the same category of mistake shows up as trading illiquid microcaps or thin recent IPOs beyond what the actual liquidity can support — the batch notes describe this specifically as a trap for a larger account, where the trader effectively becomes the volume, gets shaken out by their own order flow, and even a clean double or triple in the stock barely moves the needle on total account size once position sizing is capped by what the name can actually absorb. The corrective habit is the liquidity test already covered in 7.9 — verify tradability with a real, small order before committing meaningful size, rather than assuming a scan result is automatically tradable at the size a given account requires.

### 9.10 Following influencers, paid gurus, and copy-trading

- **"They better have audited returns... run the other way."** On trading educators and self-styled gurus: "99 percent of them are total frauds — if anyone is trying to sell you something, they better be able to back it up, they better have audited returns or something. If they can't back it up, run the other way." He connects this directly to his own low profile: "that's how I am so under the radar, because I don't market myself — I literally don't market myself."
  - *2020-10-30, t=3532s*

This is the market-facing companion to 8.7's "you can steal ideas, you can't borrow conviction" — the batch notes describe the same skepticism applied specifically to copy-trading (following another trader's individual alerts instead of building personal rules, explicitly discouraged even toward his own trades) and to commentators who post ideas but trade tiny size themselves, with the alternative offered being to study traders with demonstrable size and long, verifiable track records instead of anyone whose actual returns can't be checked.

### 9.11 Overtrading mediocre setups instead of waiting for genuinely tight ones

- **A live trade-log review, ending in a hard numeric rule.** Reviewing a struggling trader's activity: "you're doing like four or five trades every single day — stop it, no more than one trade per day for you, no more than one trade per day, you're gonna blow up so fast." Generalizing the fix moments later, for a different reviewed trader: "the best thing you can do: stop trading altogether, learn what a good setup looks like, and then you start doing one trade per day, no more — because at this rate you're gonna blow up, you'll be making four, five, six trades per day, and almost all of them are losing trades."
  - *2021-04-19, t=3956s, t=4344s*

This is a distinct failure mode from 8.10's chronic overtrading, even though the visible behavior looks similar — 8.10 is about managing an emotional itch with small, deliberately contained trades that don't threaten the account, while this is about genuinely mediocre, low-quality setups taken at real size out of impatience, which is what actually produces the account-blowing loss rate. The one-trade-per-day prescription is a blunt instrument specifically for traders who haven't yet developed the discretion to tell the two apart.

### 9.12 The opposite failure — hesitating on genuinely great setups

- **"Asleep at the wheel."** Reviewing a stretch of missed pre-announced earnings setups: "I was really asleep at the wheel back in January, when some of these things pre-announced."
  - *2017-02-24, t=281s*
- **A 320% move, missed over a single penny.** "I'm more pissed about the [one] that I missed — I mean, oh my god, can you imagine, I didn't want to pay up one penny for it, and I missed a three hundred and twenty percent move."
  - *2017-02-23, t=473s*

These sit as the deliberate counterweight to every other entry in this section: the corpus is just as willing to name hesitation, not just recklessness, as a costly and recurring mistake. The batch notes describe the same failure recurring years later in the episodic-pivot era — repeatedly missing large winners by hesitating on clear five-star EPs, reinforcing the point made in Section 1.3 that most EPs have to be bought within minutes of triggering, not reviewed and second-guessed. Paired with 9.2's chasing and 9.4's early-shorting, the honest picture is a trader whose errors run in both directions — too fast into some setups, too slow into others — rather than a single consistent bias that could be fixed with one blanket rule.

---

## 10. Other Notable Lessons

**Citation format:** same as Sections 1-9 — date and timestamp in a sub-bullet under each example.

### 10.1 Reading list and mentors — and the admission that none of it is original

- **"I've literally copied every single trading concept."** Explaining why he doesn't try to reinvent his methodology: "most people are just better off copying what works, but everyone wants to reinvent the wheel, and very few do... I've literally copied every single trading concept, every setup, everything — the average daily range, the EP setup, the breakout setup, the parabolic short — none of these things I discovered myself, even this new thing, the red line."
  - *2021-05-11, t=3493s*

The named sources behind that borrowed toolkit recur consistently across the corpus: *Reminiscences of a Stock Operator* (the Jesse Livermore biography) as his all-time favorite trading book, William O'Neil's *How to Make Money in Stocks* (the source of the CAN SLIM framework), the *Market Wizards* series, Michael Covel's *Trend Following*, and Dan Sanger's audited newsletters (general principle, recurring across many videos in the batch notes). Several specific Livermore rules are endorsed near-verbatim on stream: don't trade every day, distrust your own opinion until price confirms it, never let a trade quietly become an "investment" by ignoring your stop, and never average into a loser. This is the origin-story companion to 8.7's "you can steal ideas, you can't borrow conviction" — the ideas themselves are explicitly, repeatedly credited elsewhere; conviction is the only part described as genuinely self-built.

### 10.2 The core skill-building method — building a personal, decades-deep chart database

Building a large personal database of historical winning (and losing) stock chart setups — cited at "thousands" of annotated examples accumulated over many years in a note-taking tool (Evernote is mentioned specifically) — is described with striking consistency across dozens of separate videos spanning the full archive (general principle; no single clip is cited here since the claim is remarkably stable and repeated rather than concentrated in one memorable phrasing) as the single most valuable exercise for developing real pattern recognition, more useful than any course, mentor, or book alone. This is framed as requiring at least 1,000+ hours of dedicated study before a trader can expect to develop genuine, tested setups and the conviction to hold them through a drawdown.

The method described is consistent in its specifics: scroll every liquid US stock (later extended to historical stocks across decades and market cycles) on a monthly or weekly chart, tag every big historical mover, and study what the setup looked like immediately before the move started — the same process underlying 7.5's proactive theme-building and the "setup database" language that recurs throughout Sections 1 and 8. Reviewing past breakouts and gap-ups roughly a month later, to calibrate what actually followed through versus what failed, is described as a complementary habit that closes the loop on the same study process.

### 10.3 Day trading vs. swing/position trading — why the shift happens as an account scales

Day trading is consistently described as a tool for growing a small account quickly, not a long-term destination — as the account grows into the high six or seven figures and beyond, day-trading strategies stop scaling and the natural shift is toward swing and position trading, which captures full-sized multi-week-to-multi-month moves instead of small intraday scalps (general principle, recurring across the batch notes; see also 8.12's origin story and Section 9's treatment of day trading's scaling limits). The transition itself is described as something that took over a year to make deliberately, not something to rush — day trading offers more frequent feedback and "instant gratification," which is part of why it's a reasonable place to start, but the same frequent feedback loop is exactly what stops scaling once size becomes the binding constraint rather than skill.

The structural reason given is mechanical rather than psychological: intraday liquidity at any given moment caps how much size can be deployed and exited without moving the stock against the position, and that cap doesn't grow proportionally with account size the way a multi-day or multi-week holding period's capacity does. He describes day trading as, in effect, a beginner's tool that teaches a very fast, very cheap feedback loop — useful precisely because losing lessons are small and quick — but says explicitly he'd have started swing trading immediately if restarting his own career, since the compounding ceiling on a swing-trading account is structurally much higher than on a day-trading one of the same size.

### 10.4 Markets are not zero-sum

- **The direct rebuttal to a "someone has to lose for me to win" framing.** "That's literally not how markets work — markets are not a zero-sum game, it's not like poker, where if one guy wins a hundred bucks another guy loses. Markets are a wealth creation mechanism... if you make a hundred bucks doesn't mean someone else lost a hundred bucks." He grounds the claim in a specific mechanism, not just an assertion: companies distribute free cash flow to shareholders "in the form of buybacks or dividends, and some of that free cash flow gets invested in the business in the form of acquisitions or research and development — it's not a zero-sum game, this ain't poker."
  - *2020-07-02, t=3854s, t=4337s*

This is offered as part of the underlying rationale for a fundamentally bullish long-term bias even amid frequent short-term trading in both directions — the short-selling described extensively in 10.8 and Section 3.8 is a tactical response to individual overextended stocks, not a bet against the broader system, which he treats as a structurally different claim from a permabear's worldview.

### 10.5 News, politics, and macro treated as noise

- **"You've wasted two seconds of your life."** Dismissing a viewer's concern about a political headline moving markets: "who cares, just follow price action — if you spend more than two seconds on politics, you have wasted two seconds of your life." He grounds it in a specific historical example rather than just an opinion: "how many people didn't sell all their stocks when Trump got elected, and the market has been straight up since... these politicians, it doesn't matter who gets elected, the market is gonna do what the market is gonna do."
  - *2020-07-02, t=1937s*

A recurring, sometimes blunter version of this refrain runs across nearly every year covered: Fed policy, quad-witching, bond yields, and general macro commentary are explicitly said to have no predictive value for his process, and the stated approach is that if something like a real macro shift is actually happening, "you'll see it reflected in the setups — you don't need to know why" (general principle, recurring across the batch notes). Price action and the specific setups on the screen are what matter; narratives and opinions — his own included — are treated as subordinate to what price is actually doing, which is the same underlying instinct as 8.11's "react, don't predict."

### 10.6 Tools and platforms, and how the stack evolved

- **ThinkorSwim's decline, and what reliability is actually worth.** "ThinkorSwim used to be a great platform, until — who bought it? TD Ameritrade, I think around 2013 — since then it's pretty much downhill, how anyone still uses ThinkorSwim, you probably should get something better... in the past seven years it's been down all the time, slow, buggy." By contrast: "Interactive Brokers, I've had for like five, six years, never been down, not a single time — and I also use Sterling Trader, that thing has never been down either, maybe once in six or seven years." The stated priority is explicit: "I don't really care about any functionality, I just want it to be fast and stable."
  - *2020-08-18, t=2568s, t=2654s, t=2759s*

The consistent platform stack for most of this history is TC2000 (used for scanning and charting, not execution) paired with a fast, stable execution platform (Sterling Trader Pro and/or Interactive Brokers). This shifts somewhat by 2023: TradingView gets adopted and praised for its interface and community despite weaker scanning tools than TC2000 (general principle, recurring in the later batch notes), ThinkorSwim is criticized further, and MarketSmith is dinged specifically for slow fundamental-data updates, especially on Chinese ADRs — a detail that connects directly to 7.12's account of post-Luckin distrust of that entire data category.

### 10.7 Realistic return expectations, benchmarked against real traders

- **A stated floor, and the ceiling in a genuinely good year.** "What return can you expect as a decent swing trader? Easily 100 [percent] on average per year, just trading on the long side without using any leverage — if you're a good swing trader, you can average easily 100 percent, not every year, some years are gonna be tougher... that's like their floor. If you're a really good swing trader in a really good market, you can easily make 500, a thousand percent in a really good year — like last year, every good swing trader made at least 500 last year, or at least 300, without using any leverage."
  - *2021-04-05, t=3457s, t=3488s*

The number is offered as a benchmark against real, verifiable traders rather than a generic promise — the batch notes describe him repeatedly warning that any coach or service advertising a specific return figure needs audited results to back it up (see 9.10), and this 100%-floor/300-1000%-good-year range is presented in that same spirit: a claim he's willing to attach his own name and stream to, not a marketing number.

### 10.8 Short selling — roughly half his profits, but a structurally harder game to scale

- **The lifetime split between long and short profits, and why shorting is easier to find good setups for.** "Short selling is very important — I guess about half of the money I made is from shorting, and when I was a day trader I guess two-thirds, maybe three-quarters of my money was from short selling, but nowadays it's about half or a third." Asked why: "it's easier to find really, really good short setups than really good long setups — when you see something [extended], you just know it's gonna pull back, it could go higher, but you know it's gonna pull back eventually, so you just wait for those first cracks. But when you buy something, it's like, okay, it's a great setup, but is it gonna go? It could go to 100, but is it gonna do that? There's more uncertainty with longs."
  - *2020-06-10, t=5947s, t=5971s*
- **The supply imbalance stated as simple arithmetic.** "For every parabolic long setup there are like five parabolic short setups — it's just mathematics, the long ones you just don't get as often."
  - *2020-06-12, t=3741s*

This is the setup-quality and setup-frequency side of an asymmetry whose risk-mechanics side is covered in 3.8 — shorts are described as both more predictable to identify and simply more abundant, which is a different claim from 3.8's point about capped upside and unlimited downside risk on the short side. Both point toward the same practical conclusion reached at scale (10.10): shorting is a real edge, but one that becomes progressively less attractive to lean on as an account and a public track record both grow.

### 10.9 The EP era compressed his actual trading day

- **"You really only need like one hour of your day."** Describing his 2023 routine, built almost entirely around episodic pivots (1.3): "for those of you who are working, you really only need like one hour of your day — you start doing research, you make your entries, and then you're free, takes one hour every day." Asked to break down where the actual trading happens: "30 minutes usually, most of my trading happens in the first, say, 30-45 minutes, probably like 70-80 percent [of my activity]."
  - *2023-05-23, t=2181s, t=2216s, t=2346s*

This is a marked contraction from the more varied, longer-session trading style described in the earlier years of the archive, and it mirrors the account-scale shift covered in 10.10 — less time spent, not more, as both skill and account size grew, with a single high-conviction setup (the EP) doing the work that used to require actively managing several setup types across a full session.

### 10.10 Structural and tax adjustments at scale

- **Small, speculative positions deliberately routed into a tax-free account.** On a cluster of small quantum-computing positions: "these are very small, I have them in my tax-free accounts, because these are the ones that can double, triple, quadruple, five, ten bagger."
  - *2023-06-08, t=2129s*

As his account grew, he describes deliberately shifting a larger share of his trading into this tax-advantaged account structure and reducing his short-selling activity over time (general principle, recurring in the later batch notes), citing both tax efficiency and reduced screen time as motivations — framing shorting as a strategy that scales poorly for a professional manager anyway, since a short's maximum gain is capped at 100% while a long's upside is theoretically unlimited. Read alongside 10.8, the picture is a trader who built roughly half his lifetime edge on the short side while it was the more efficient use of his time and capital, then deliberately dialed it back once account size and tax structure made the long side comparatively more efficient — not because the short-side edge itself had stopped working.

### 10.11 Broker redundancy and commission structure as account insurance

- **A single trade's commission bill, in two different fee structures.** Comparing a percentage-based Swedish broker against his US, per-share broker on an identical trade: "commission percentage — that's the problem, anytime you pay a percentage in commissions you're getting ripped off, you should either get a flat fee or pay per share... my commissions on this trade would have been $13,200 [with the percentage broker], but with my US broker, I pay per share, including ECN fees — this is what I paid: $200. You can get your commissions down by like 99 percent if you switch to a US broker."
  - *2021-02-19, t=1954s, t=2201s*

The $13,000 gap on a single trade is the concrete version of a warning repeated across the batch notes in softer form: do the math on total dollar volume traded, not the headline percentage rate, since a fee structure that looks negligible on a small account becomes a direct, compounding tax on returns at real size. This sits alongside — but is a distinct concern from — the broker-*outage* redundancy covered in 3.11: 10.11 is about not overpaying for execution, 3.11 is about not being unable to execute at all; the discipline of running multiple brokers addresses both at once.

### 10.12 The anti-scam rule, and trading in strong currencies

A blanket, explicitly stated rule against ever sending money to anyone who contacts him unsolicited is offered as general advice given how frequently his public profile attracts impersonation and fraud attempts (see also the impersonation-account exchange narrated in 1.9). The rule is stated as absolute rather than case-by-case — no unsolicited contact, online or in person, however convincing, ever justifies sending money — on the reasoning that a legitimate opportunity never actually requires that specific channel, so the rule costs nothing to follow even in the rare case the request happens to be real.

A related, less obvious piece of structural advice appears in the later batch notes: trade US markets in US dollars rather than a weaker home currency, even if it means eating a higher tax rate in the process (general principle, recurring in the 2022-2023 batch notes) — the reasoning given is that a persistently weak local currency is itself a hidden, uncompensated risk sitting underneath every trade, and the tax difference is a known, bounded cost next to that open-ended one. Both rules share the same underlying shape: a small, certain, easily-dismissed-as-excessive cost (refusing a plausible-sounding unsolicited offer, accepting a higher tax bill) traded off against a rare but potentially catastrophic and uncapped downside, which is the same risk-management logic that runs through the position-sizing rules in Section 3.

---

*This document synthesizes all 27 source batches (2017-2023) into 10 unified topic sections, each spanning the full channel history rather than being split by time period — every subsection cites the specific date(s) its claims come from directly. Raw, per-period source notes with full video citations are preserved in `data/analysis/lesson_batches/` for anyone who wants to trace any point back to its specific source video and date.*
