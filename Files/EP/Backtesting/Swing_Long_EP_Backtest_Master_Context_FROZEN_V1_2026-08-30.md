# Swing Long / Episodic Pivot Python Backtest — Master Context + Frozen V1 Specification

**Updated:** 2026-08-30  
**Project:** Swing Long System / Episodic Pivot Backtesting  
**Status:** **EP Backtest V1 rules are now sufficiently defined to begin implementation.**  
**Purpose:** Give Claude Code a single, internally consistent source of truth for building the new Python backtester.

---

# 0. Superseding Rule

This document supersedes earlier drafts where rules were still uncertain.

If an older assumption conflicts with this file, **this file wins**.

The user is migrating from a custom Excel backtesting system into a Python event-driven backtester for **long Episodic Pivot (EP)** trades.

The intended progression is iterative:

1. **V1 — Entry × Initial Stop**
2. **V2 — Trailing Stop Variants**
3. **V3 — Partial Profit-Taking / Core / Breakeven**
4. **V4 — Signal Filters / Chart Pattern / Volume / Candle Color / Other Conditional Features**
5. Later — earnings-risk handling, portfolio simulation, re-entries, more advanced robustness work

The user explicitly wants to build this in stages and learn from each stage before adding complexity.

---

# 1. Core Philosophy

The system must answer:

> **Given a historical EP event, what would the strategy have known at each exact point in time, and what would have happened if it followed the defined rules?**

The backtester must avoid:

- look-ahead bias
- using future lows/highs to define stops
- using future candle color before the candle has closed
- using future volume before that volume exists
- assuming fills at prices that were no longer available
- using next-day data to improve same-day decisions
- silently changing the meaning of R after the trade begins

The system should be **chronological and auditable**, not a black-box summary.

---

# 2. What the Old Excel Backtester Did Correctly

The old swing-short/day-trading workbook already implemented several sound systematic ideas:

1. One row per historical event.
2. Separate **signal** from **execution**.
3. Test many Entry × Stop × Exit combinations.
4. Express outcomes in **R-multiples**.
5. Check whether a stop was touched **after entry**, not before.
6. Preserve trade-level results.
7. Calculate:
   - Win Rate
   - Avg Winner
   - Avg Loser
   - Risk/Reward
   - Profit Factor
   - EV
   - Total R / Net EV
8. Rank strategies with a custom score.
9. Deliberately disable strategy families with `NA` when isolating one dimension.

This is essentially a valid grid-search / parameter-optimization structure.

Python should preserve these strengths while eliminating spreadsheet fragility.

---

# 3. Old Workbook Metrics — Definitions to Preserve

## 3.1 Win Rate

\[
WinRate = \frac{WinningTrades}{ValidTrades}
\]

## 3.2 Average Winner

\[
AvgWinner = mean(R \mid R > 0)
\]

## 3.3 Average Loser

\[
AvgLoser = mean(R \mid R < 0)
\]

Average loser remains negative.

## 3.4 Risk-to-Reward (RR)

The user explicitly defines RR as the conventional payoff ratio:

\[
RR = \frac{AvgWinner}{|AvgLoser|}
\]

Do **not** use “RR” to mean Profit Factor.

## 3.5 Profit Factor

\[
PF = \frac{GrossWinningR}{|GrossLosingR|}
\]

## 3.6 Expected Value

\[
EV =
WinRate \times AvgWinner +
(1-WinRate)\times AvgLoser
\]

Interpretation:

> expected R earned per trade

## 3.7 Total R / Net EV

\[
TotalR \approx EV \times N
\]

When strategies have different entry rates / N, report both EV and total realized R.

---

# 4. G Score — Confirmed User Preference

The intended ranking score is:

> **50% EV score + 50% Profit Factor score**

Not 45/35/20.

Not RR.

Not Win Rate.

Conceptually:

\[
GScore = 0.50(EVScore) + 0.50(PFScore)
\]

Raw metrics must always remain visible alongside G Score.

G Score is a **ranking preference**, not proof of robustness.

---

# 5. Old Excel Issue to Avoid

The old workbook had a tiny sample-size error where a manual `COUNTA()-2` denominator returned 378 instead of 379.

New rule:

> Every strategy calculates its own valid N directly from its actual eligible / triggered trades.

Never use a manually adjusted global denominator.

Always distinguish:

- eligible EP events
- triggered trades
- no-entry events
- invalid-data events

---

# 6. New Python Architecture

Recommended conceptual pipeline:

```text
Historical EP Events
        ↓
Point-in-Time Event Features
        ↓
Minute + Daily OHLCV
        ↓
Strategy Configuration
        ↓
Chronological Trade Simulator
        ↓
Trade-Level Results
        ↓
Strategy-Level Metrics
        ↓
EV / PF / RR / WR / N / Total R
        ↓
50/50 EV-PF G Score
        ↓
Parameter Surface / Stability Analysis
        ↓
Feature Slices
        ↓
OOS / Era Validation
```

---

# 7. Python Should Use a State Machine

V1 states:

```text
PENDING_ENTRY
    ↓
OPEN_POSITION
    ↓
EXITED
```

Later versions add:

```text
OPEN_POSITION
    ↓
PARTIALS_ACTIVE
    ↓
CORE_ONLY
    ↓
EXITED
```

At every bar, the engine may use only information available at that time.

---

# 8. EP Backtest V1 — Research Question

V1 intentionally asks only:

> **For an EP long setup, which opening-range breakout entry timing and which initial-stop family produce the strongest trade outcomes when all combinations use the same standardized exit?**

V1 deliberately does **not** optimize:

- trailing-stop type
- profit partials
- core size
- breakeven-after-first-sale
- pre-earnings exit
- chart-pattern filters
- first-candle-color filters
- early-volume filters
- re-entries

Those come later.

---

# 9. EP Backtest V1 — Entry Grid

Test six opening-range definitions:

1. `1M High`
2. `5M High`
3. `10M High`
4. `15M High`
5. `30M High`
6. `60M High`

The opening-range candle is always the **first regular-session candle of that duration beginning at 9:30 ET on EP Day 0**.

Examples:

- 1M range = 9:30–9:31
- 5M range = 9:30–9:35
- 10M range = 9:30–9:40
- 15M range = 9:30–9:45
- 30M range = 9:30–10:00
- 60M range = 9:30–10:30

---

# 10. Entry Trigger

For each entry type:

\[
Trigger = OpeningRangeHigh + \$0.01
\]

Conceptually this is a **buy stop-market order** one penny above the opening-range high.

Earliest 1M entry:

> approximately **9:31:01 ET**, after the first 1-minute candle has fully completed and its high is known.

Same principle for all longer opening ranges.

The system may never enter before the defining opening-range candle is complete.

---

# 11. Opening-Range Trigger Is Fixed

The trigger is calculated **once from Day 0's first opening-range candle**.

It does **not** recalculate on Day +1, Day +2, etc.

Example:

```text
EP Day 0 first 15M high = $50.00
Trigger = $50.01
```

That same `$50.01` trigger remains pending for the entire allowed entry window.

Do not calculate a new 15M high every morning.

---

# 12. Pending Entry Window — Confirmed

A pending order remains eligible from:

> **Day 0 through Day +7 inclusive**

Eight possible regular trading sessions:

```text
D0
D+1
D+2
D+3
D+4
D+5
D+6
D+7
```

If the original fixed trigger has not filled by the closing bell on D+7:

```text
entry_status = NO_ENTRY
```

Do not carry the order beyond D+7.

D+1 etc. mean **trading sessions**, not calendar days.

---

# 13. Entry Day Offset Must Be Recorded

Do **not** initially define `15M-D0`, `15M-D1`, etc. as separate strategies.

Instead, a single entry strategy such as `15M High` produces an outcome attribute:

```text
entry_day_offset = 0
entry_day_offset = 1
...
entry_day_offset = 7
entry_day_offset = NULL if no entry
```

Dashboard/analysis can then slice:

- D0 entries
- D+1
- D+2
- ...
- D+7
- No Entry

This preserves the ability to discover that delayed breakouts may be better without prematurely multiplying the strategy grid.

---

# 14. Regular-Hours Entry Only

Pending buy orders are active only during:

> **9:30 AM – 4:00 PM America/New_York**

No premarket entry.

No after-hours entry.

If trigger is crossed after hours, ignore it.

If the next regular session opens above the trigger, use the gap-through logic below.

---

# 15. Entry Fill Model — Confirmed

## 15.1 Normal trade-through

If price trades normally through the trigger during regular hours:

\[
FillPrice = TriggerPrice + EntrySlippage
\]

Slippage must be configurable.

## 15.2 Gap / jump through trigger

If a regular-session candle opens above the trigger before a normal trade-through occurred:

\[
FillPrice = CandleOpen + EntrySlippage
\]

Example:

```text
Trigger = 50.01
Next eligible regular-session open = 55.00
Entry fill = 55.00 + configured slippage
```

Do not pretend the strategy got 50.01.

---

# 16. If Opening-Range Candle Closes at Its High

The order does not exist until that defining candle completes.

Therefore:

- no fill inside the defining opening-range candle
- first eligible opportunity is the next candle
- if next candle opens above the trigger, fill at next candle open + slippage

---

# 17. Entry Slippage Affects Stop Geometry

Entry price means the **actual simulated fill**, not the trigger.

Therefore any stop defined as X% from entry or X ADR from entry must use the actual fill.

Do not calculate those stops from the pre-slippage trigger.

---

# 18. V1 Initial Stop Grid — 12 Types

### Static percentage from actual entry fill
1. `0.5%`
2. `1%`
3. `2%`
4. `3%`
5. `5%`

### Structural
6. `LOD Known at Entry`
7. `Low of Trigger Candle Known at Entry`

### ADR based
8. `0.25 ADR`
9. `0.3333 ADR`
10. `0.50 ADR`
11. `1.00 ADR`
12. `2.00 ADR`

Thus:

\[
6\ EntryTypes \times 12\ StopTypes = 72\ V1\ combinations
\]

---

# 19. Static Stop Formula

For a long:

\[
Stop = EntryFill \times (1 - StopPct)
\]

---

# 20. ADR Definition — Confirmed

Use the project's existing **pre-gap 14-day ADR** definition, consistent with the TradingView scanner / EP scanner.

The EP day is excluded.

If ADR = 6%:

- 0.25 ADR = 1.5%
- 0.3333 ADR ≈ 2.0%
- 0.50 ADR = 3.0%
- 1.00 ADR = 6.0%
- 2.00 ADR = 12.0%

Formula:

\[
Stop =
EntryFill \times
(1 - ADRPct \times ADRMultiplier)
\]

Internally normalize multipliers:

```text
0.25
0.3333333333
0.50
1.00
2.00
```

---

# 21. LOD Stop — Confirmed

`LOD` means:

> the current regular-session Low of Day **known at the exact moment the entry is filled**

It does **not** mean:

- eventual Day-1 low
- eventual entry-day low
- lowest low from Day 0 through entry day
- any future low after entry

If the trigger finally fills on D+3:

> use D+3's current LOD known at entry.

Example:

```text
D+3 opens = 46
D+3 trades to 45
D+3 later rallies
Trigger fills at 50.01 at 13:00

LOD stop = 45
```

---

# 22. Low of Trigger Candle — Corrected Definition

This does **not** mean the low of the original Day-0 opening-range candle.

It means:

> the low, known at the exact entry moment, of the timeframe candle that actually triggers the breakout entry.

Example:

- Entry type = `15M High`
- Day-0 9:30–9:45 high = $50
- stock tanks
- at 10:42 it finally trades through $50.01
- the triggering 15-minute candle is the 10:30–10:45 candle

The stop uses:

> the low of that 10:30–10:45 candle **observed only through 10:42**.

Do not use a future 10:44 low.

This is point-in-time.

---

# 23. Same-Minute Entry / Stop Ambiguity

With 1-minute OHLC, exact intrabar sequencing may be unknowable.

If one 1-minute bar contains both:

- the entry trigger, and
- the initial stop,

and sequence cannot be established:

> use the **conservative adverse assumption**.

Treat it as entry followed by stop-out.

Later finer data can refine this.

---

# 24. Stop Execution — Stop-Market Logic

## Normal trade-through

If regular-session price trades through the stop:

\[
ExitFill = StopPrice - StopSlippage
\]

for a long.

## Gap through stop

If next regular session opens below the stop:

\[
ExitFill = SessionOpen - StopSlippage
\]

Example:

```text
Stop = 45
Next regular open = 30
Exit = 30 minus configured slippage
```

No magical fill at 45.

---

# 25. No Premarket / After-Hours Stop-Outs

For now:

> only regular-session price action can trigger stops.

Premarket / after-hours may move dramatically but do not trigger the stop.

If stock gaps 50% lower overnight, exit at next regular-session opening price minus configured stop slippage.

---

# 26. V1 Standardized Exit — Frozen

Every one of the 72 V1 Entry × Stop combinations uses the same exit:

> **First daily close below the finalized 10-day SMA → exit at that same day's official closing price.**

This is intentionally fixed so V1 isolates Entry × Initial Stop.

No next-day-open delay.

---

# 27. 10SMA for V1 Close-Based Exit

Use the normal finalized daily 10-period simple moving average:

\[
10SMA_t =
\frac{
Close_t + Close_{t-1} + ... + Close_{t-9}
}{10}
\]

At the close:

```text
if Close_t < 10SMA_t:
    exit at Close_t
```

This is the only MA behavior V1 needs.

Do not implement intraday 10MA/20MA touch approximations in V1.

---

# 28. Same-Day V1 Exit Is Allowed

If entry occurs intraday and that same day ultimately closes below finalized 10SMA:

> enter intraday and exit at that same day's close.

No minimum one-day hold.

---

# 29. Insufficient 10SMA History

If stock lacks enough valid daily history to calculate 10SMA:

> mark event as **ineligible for V1 standardized-exit testing**.

Do not use a shortened MA.

---

# 30. V1 R Definition — Frozen

For a triggered long:

\[
InitialRiskPerShare =
EntryFill - InitialStop
\]

Then:

\[
InitialRiskDollars =
InitialRiskPerShare \times InitialUnits
\]

Define:

\[
1R = InitialRiskDollars
\]

This value is frozen forever for that trade.

It never changes, even in later versions when:

- stop moves to breakeven
- trail moves higher
- partials are sold
- only core remains

Final realized R:

\[
TradeR =
\frac{NetRealizedPnL}{InitialRiskDollars}
\]

---

# 31. Invalid Stop Geometry

Guard against nonsensical initial stops:

- stop >= actual entry
- zero risk distance
- negative risk distance
- corrupted ADR
- missing required structural low

Record explicit status:

```text
INVALID_STOP_GEOMETRY
```

Exclude from valid strategy N.

---

# 32. No-Entry Events

If trigger does not fill by D+7 close:

```text
entry_status = NO_ENTRY
```

A no-entry event is:

- not a win
- not a loss
- not included in EV / PF / WR
- included in entry-rate / frequency statistics

---

# 33. V1 Entry Rate

For each strategy:

\[
EntryRate =
\frac{TriggeredTrades}{EligibleEvents}
\]

Report:

- eligible events
- triggered trades
- no-entry count
- entry rate
- entry-day-offset distribution

---

# 34. V1 Core Strategy Metrics

For each of the 72 V1 combinations report at minimum:

- Strategy ID
- Entry Type
- Initial Stop Type
- Eligible Events
- Triggered Trades
- No Entry
- Entry Rate
- D0 Entry %
- D+1 %
- D+2 %
- D+3 %
- D+4 %
- D+5 %
- D+6 %
- D+7 %
- Win Rate
- Avg Winner R
- Avg Loser R
- RR
- Profit Factor
- EV R/trade
- Total R
- Median R
- Standard deviation R
- Avg holding days
- Median holding days
- G Score

Recommended extra fields:
- MFE R
- MAE R
- top-tail contribution
- by-year metrics

---

# 35. Win / Loss / Breakeven

Use a small epsilon:

```text
R > +epsilon → Win
R < -epsilon → Loss
otherwise → Breakeven
```

Avoid floating-point dust.

---

# 36. V1 Strategy IDs

Use deterministic readable IDs.

Examples:

```text
E01M__S005PCT
E15M__SLOD
E30M__S050ADR
E60M__S200ADR
```

Same config must always map to same ID.

---

# 37. V1 Parameter Surfaces — Required

Do not only sort the 72 strategies by rank.

Build matrices:

```text
Rows = Entry Type
Columns = Initial Stop Type
```

Generate separate surfaces for:

- EV
- PF
- G Score
- RR
- N
- Entry Rate

Goal:

> find robust regions, not one magic cell.

---

# 38. How to Interpret V1

Bad:

> “15M + 0.50 ADR ranked #1, therefore use it.”

Better:

> “10M–30M entries paired with 0.33–1.0 ADR stops form a broad region with positive EV, healthy PF, and stable sample size.”

Broad plateau > isolated spike.

---

# 39. Chart Pattern — Feature, Not V1 Optimization Dimension

Current chart-pattern categories:

- CPH
- DT
- DT SW
- DT U
- SW
- U
- UDS
- UT
- UTU

Known meanings:

- CPH = cup and handle
- DT = downtrend
- DT SW = downtrend then sideways
- DT U = downtrend then U-type recovery
- SW = sideways
- U = U-shaped base / recovery
- UDS = up-down-sideways
- UT = uptrend
- UTU = uptrend then U / fish-hook reset

V1 should:

1. backtest execution across all eligible EPs
2. attach chart pattern to each trade
3. slice results afterward

Do not multiply chart pattern into the 72-strategy grid.

---

# 40. Signal-Feature Availability — Mandatory Future Rule

Future features must have a timestamp representing when they become knowable.

Suggested metadata:

```text
feature_available_at
```

Examples:

## First 1M candle color
Available after first 1M candle completes.

## First 5M candle color
Available at 9:35.

Cannot decide whether to take a 1M entry that occurred before 9:35.

## First 5M volume ratio
Available at 9:35.

## Full gap-day daily candle color
Available only at/after 4:00 PM close.

Can be used descriptively, but cannot be a same-day intraday entry filter without look-ahead.

---

# 41. Future Candle-Color Filters

User later wants to test ideas such as:

> “Ignore first red 5-minute opening candles and only trade when first 5-minute candle is green.”

This is a **signal filter**, not an execution rule.

Potential fields:

- first 1M candle green/red
- first 5M candle green/red
- perhaps other opening windows
- full gap-day green/red

All must obey `feature_available_at`.

---

# 42. Future Early-Volume Filters

User's intended concept:

> require first 5-minute volume to be at least X × pre-gap 30-day average daily share volume.

Example:

\[
First5M\_ADVRatio =
\frac{First5MVolume}
{PreGap30DAvgDailyShareVolume}
\]

Possible later threshold example:

```text
First5M_ADVRatio >= 0.45
```

Purpose:

> avoid low-volume opening-range breakouts.

Only valid once first 5 minutes have elapsed.

---

# 43. V2 — Trailing Stop Research

After V1 identifies promising Entry × Initial Stop regions, test:

1. `10MA Touch`
2. `Close Below 10MA`
3. `Low of Close-Below-10MA Day`
4. `20MA Touch`
5. `Close Below 20MA`
6. `Low of Close-Below-20MA Day`

Do not add them to V1.

---

# 44. V2 Plain 10MA / 20MA Touch — Deferred

User intent:

> intraday touch below MA exits immediately.

Exact intraday MA approximation is **not frozen yet**.

Potential approaches discussed:

- prior closes + today's open, frozen for day
- dynamically updating intraday
- prior finalized MA
- other approximation

Do not silently choose until V2.

---

# 45. V2 Close-Below-MA Rule — Clarified

For `Close Below 10MA` / `Close Below 20MA`:

- use finalized daily close
- use finalized daily SMA
- if close is below MA:
  - exit at that same day's official close
- never wait until next day's open

V1 already uses `Close Below 10SMA` as its standardized exit.

---

# 46. V2 Low-of-Close-Below-MA Rule

Clarified behavior:

1. A day closes below selected MA.
2. Do **not** immediately exit.
3. That day's low becomes a stop for subsequent regular-session trading.
4. If another qualifying close-below-MA day later creates a higher low:
   - ratchet stop upward.
5. Never lower the trailing stop.

No premarket/AH stop trigger under current simple assumptions.

If next regular session gaps below stop:
- sell at regular-session open minus slippage.

Same logic for 10MA and 20MA.

---

# 47. V3 — Profit-Taking / Partial-Sale Logic

V3 will introduce:

- profit target spacing
- partial-sale amount
- partial style
- core %
- breakeven after first sale

These should be separate dimensions.

---

# 48. Profit Target Type A — Every X% Move

Targets are measured from **original entry price**.

If:

```text
Entry = 100
X = 10%
```

targets:

```text
110
120
130
140
...
```

anchored to original entry.

---

# 49. Profit Target Type B — Every X Daily Candles

Confirmed:

- timeframe = daily candles
- sell at daily close
- entry day = Day 0
- no partial on Day 0

Example:

If `X = 5 candles`:

> first time-based partial at close of fifth full trading day after entry day.

---

# 50. Partial Parameters Must Be Separate

At least two independent variables:

## Target spacing
Examples:
- every 5%
- every 10%
- every 15%
- every X daily candles

## Sell amount
Examples:
- 2.5 percentage points
- 5 percentage points
- 10 percentage points
- etc.

Do not encode “every 10% sell 5%” as one indivisible parameter.

---

# 51. Core % — Confirmed

Core is protected from normal partial-selling logic.

Example:

```text
Original normalized position = 100
Core = 30%
Non-core = 70
```

Normal target-based partials may only sell the 70 non-core units.

They may never reduce position below 30-unit core.

Candidate core grid later:

```text
0%
10%
20%
...
100%
```

0% explicitly included.

---

# 52. Partial Style 1 — Equal Non-Core Depletion

Example:

```text
Original position = 100
Core = 30
Non-core = 70
Sell amount parameter = 5 percentage points
```

Then:

```text
70 / 5 = 14 sales
```

Each partial sells:

> 5 units, i.e. 5 percentage points of original normalized position,

but all sales come entirely from the 70-unit non-core bucket.

The 30-unit core is untouched.

This is **not** 5% of 70 each time.

Recommended name:

```text
EQUAL_NONCORE_DEPLETION
```

---

# 53. Partial Style 2 — Exponential Remaining-Non-Core

Example:

```text
Original position = 100
Core = 30
Initial non-core = 70
Sell parameter = 5%
```

At each target:

```text
Sell 5% of remaining non-core
```

Sequence:

```text
3.5000
3.3250
3.15875
...
```

Use fractional normalized units in research so there is no arbitrary one-share discontinuity.

Recommended name:

```text
EXPONENTIAL_REMAINING_NONCORE
```

---

# 54. Gap Through Multiple Profit Targets

Example:

```text
Entry = 100
Targets = 110, 120, 130
Prior close = 105
Next regular open = 135
```

All crossed standing targets are considered reached.

Scheduled partials tied to those targets execute at approximately:

> the 135 regular-session opening price, adjusted by the eventual exit/slippage model.

Do not fill them at stale 110/120/130.

---

# 55. Breakeven After First Sell — Future V3

Parameter:

```text
breakeven_after_first_sell = True / False
```

If enabled:

1. first partial executes
2. remaining stop moves to **breakeven adjusted for fees/slippage**
3. later trailing stop supersedes BE only if higher

Trailing stops never loosen risk.

Exact cost-adjusted BE formula can be finalized in V3.

---

# 56. Pre-Earnings Management — Future

User wants to backtest both:

### A. Ignore next earnings
Continue technical trail.

### B. Reduce before earnings
Sell configurable percentage of **entire remaining position**, including core, the day before earnings.

Candidate later grid:

```text
0%
25%
50%
75%
100%
```

Execution concept:

> regular-session close immediately before earnings announcement.

Leave out of V1.

---

# 57. Holding Period — Confirmed

No arbitrary maximum hold.

Once entered:

> hold until active exit/trailing rule exits the trade, no matter how long.

V1 uses standardized close-below-10SMA exit until trade ends.

---

# 58. One Shot / One Kill Per EP — Confirmed

For now:

> one entry attempt / one trade per EP ticker instance.

No re-entry after stop-out.

No pyramiding.

Re-entry comes later.

---

# 59. Repeat EP While Existing Virtual Trade Is Open

For initial trade-quality research:

> treat each EP instance independently in its own virtual simulation.

Full portfolio/same-ticker capital logic comes later.

---

# 60. Slippage Architecture

Separate:

```text
entry_slippage
stop_exit_slippage
normal_exit_slippage
```

Changing entry slippage can alter:

- actual fill
- static stop
- ADR stop
- R denominator
- later trade path

Therefore dashboard changes may require **re-simulation**, not cosmetic post-processing.

Store both raw trigger/stop levels and actual fills.

## 60.1 V1 Default Slippage Value — Confirmed, Revised 2026-08-30

For V1, use a single placeholder convention for all three slippage types:

\[
Slippage = 0.1\% \times ReferencePrice
\]

**Revision history:** originally set to 1% (2026-08-30, same day). The first full-universe
V1 run at 1% showed every static-percentage stop at 0.5%-2% landing at exactly 0% win rate —
not a finding about those entries, but a mechanical artifact: 1% slippage on entry plus 1% on
the stop exit (≈2% round-trip) exceeded the stop's own width, so `stop_price` for a 0.5% stop
computed out to a level *above* the original breakout trigger, meaning virtually any normal
pullback closed the trade. Revised down to 0.1% (≈0.2% round-trip) so it stays comfortably
below even the tightest stop while still real enough to penalize thin stops. Still an explicit
placeholder, not a researched cost model — the mechanism (percent of reference price, applied
symmetrically to entry/stop/normal exits) is unchanged, only the number is smaller.

Where `ReferencePrice` is the price level the fill is measured against for that specific event:

- `entry_slippage`: 0.1% of the entry trigger price (normal trade-through) or of the session open (gap-through) — added, since it's a long entry.
- `stop_exit_slippage`: 0.1% of the initial stop price (normal trade-through) or of the session open (gap-through) — subtracted, since it's a stop-out sell.
- `normal_exit_slippage`: 0.1% of the finalized daily close on the 10SMA-exit day — subtracted.

Example:

```text
Stop price = 45.00
Stop slippage = 1% x 45.00 = 0.45
Exit fill on normal trade-through = 45.00 - 0.45 = 44.55
```

This is an explicitly named placeholder ("for now"), not a researched cost model — expect it to be revisited once real fill data or broker statistics are available. It unblocks Phase 2/3 hand-verification, which is its only job right now.

---

# 61. Costs

Historically user sometimes modeled costs directly in R.

Preferred new long-term method:

1. simulate actual fills
2. calculate raw P&L
3. apply cost model
4. convert net P&L to R using frozen initial risk

V1 may use simplified configurable assumptions if exact cost model is not finalized.

Do not hardcode silent costs.

---

# 62. Data Output — Trade-Level Long Format

Do not create one spreadsheet column per strategy.

Suggested V1 schema:

```text
strategy_id
ticker
event_date
chart_pattern

entry_type
opening_range_high
entry_trigger
entry_day_offset
entry_timestamp
entry_fill
entry_slippage

initial_stop_type
initial_stop_level
initial_risk_per_share

exit_timestamp
exit_price
exit_reason

gross_pnl
costs
net_pnl
realized_R

holding_days
holding_minutes

MFE_R
MAE_R

eligible_flag
entry_status
data_quality_flag
```

Attach useful EP features too:

```text
ADR
gap_pct
market_cap
turnover
IPO_age
first_1m_color
first_5m_color
first_5m_ADV_ratio
full_day_color
etc.
```

Features can be attached without becoming V1 filters.

---

# 63. Strategy Summary Output

One row per V1 strategy:

```text
strategy_id
entry_type
initial_stop_type

eligible_events
triggered_trades
no_entry
entry_rate

d0_entries
d1_entries
...
d7_entries

win_rate
avg_winner_R
avg_loser_R
RR
profit_factor
EV_R
total_R
median_R
std_R

avg_hold_days
median_hold_days

G_score
```

Recommended:
- positive years
- worst-year EV
- best-year EV
- top-5%-trade contribution

---

# 64. Parameter Heatmaps

Required V1 heatmaps:

- EV
- PF
- G Score
- RR
- N
- Entry Rate

Rows = Entry Type  
Columns = Initial Stop Type

---

# 65. Slice Tables After V1

After full-universe execution results exist, generate slices:

- chart pattern
- entry day offset
- year
- era
- ADR bucket
- gap bucket
- market cap
- turnover
- first-candle color
- early volume
- gap-day color

But descriptive slicing does not automatically make a feature a valid historical filter.

Feature timing must be respected.

---

# 66. Robustness Philosophy

Do not select a strategy merely because it has the highest score.

Look for:

- broad neighboring parameter strength
- adequate N
- stable EV
- healthy PF
- reasonable RR
- consistency by year / era
- OOS survival

Isolated spike = suspicious.

Broad plateau = encouraging.

---

# 67. Development vs. Validation

Later use:

## Development sample
For:
- comparing parameters
- finding strong regions
- forming rules

## OOS / validation
Used only after rules are chosen.

Do not keep tuning on OOS.

Because EP V4 spans many years, later inspect:

- pre-COVID
- COVID momentum era
- 2022 bear/chop
- recent post-COVID periods

Exact date splits later.

---

# 68. Unit Tests — Mandatory

## A — Earliest 1M entry
- first 1M high known after 9:31
- trigger = high + 0.01
- no entry before completion

## B — Defining candle closes at high
- next candle opens through trigger
- fill at next candle open + slippage

## C — Delayed D+3 entry
- original D0 trigger fixed
- D0–D+2 no entry
- D+3 fills
- `entry_day_offset = 3`

## D — D+8 no entry
- no fill D0–D+7
- `NO_ENTRY`

## E — LOD
- future day's eventual low is lower
- stop uses only LOD known at entry

## F — Trigger-candle low
- 15M trigger occurs mid-candle
- stop uses low of triggering 15M candle only through entry timestamp

## G — Same-minute entry/stop
- both touched in same 1M bar
- adverse assumption → stopped

## H — Gap through stop
- stop = 45
- next open = 30
- exit = 30 - stop slippage

## I — Same-day 10SMA exit
- intraday entry
- same-day finalized close < 10SMA
- exit same close

## J — Insufficient 10SMA
- <10 valid closes
- event ineligible

---

# 69. Debug / Audit Mode

Engine should narrate one trade.

Example:

```text
Ticker: XYZ
EP Date: 2024-05-01
Strategy: E15M__S050ADR

09:45 — first 15M range completes
OR High = 50.00
Trigger = 50.01

D0 — no trigger
D+1 — no trigger
D+2 10:42 — trades through 50.01

Entry fill = 50.04 after slippage

Pre-gap ADR = 6.0%
Stop multiplier = 0.50 ADR
Stop distance = 3.0%
Initial stop = 48.5388

1R/share = 1.5012

...
Day N close = 72.00
Final 10SMA = 72.40
Close < 10SMA

Exit = 72.00

Net P&L = ...
Final R = ...
```

---

# 70. Suggested Code Structure

Keep concerns separate without overbuilding.

```text
ep_backtest/
│
├── config/
│   ├── v1_grid.py
│   └── slippage.py
│
├── data/
│   ├── load_events.py
│   ├── load_minute_bars.py
│   ├── load_daily_bars.py
│   └── calendar.py
│
├── engine/
│   ├── simulator.py
│   ├── entries.py
│   ├── initial_stops.py
│   ├── exits.py
│   └── fills.py
│
├── metrics/
│   ├── summarize.py
│   ├── g_score.py
│   └── surfaces.py
│
├── outputs/
│   ├── trade_level/
│   ├── strategy_summary/
│   └── heatmaps/
│
└── tests/
```

---

# 71. Suggested V1 Strategy Config

```python
strategy = {
    "entry_type": "15m_high",
    "initial_stop_type": "0.50_adr",
    "entry_valid_through_day_offset": 7,
    "baseline_exit": "close_below_10sma_same_close",
}
```

Slippage/cost model should be separate.

---

# 72. Suggested V1 Entry Grid

```python
ENTRY_TYPES = [
    "1m_high",
    "5m_high",
    "10m_high",
    "15m_high",
    "30m_high",
    "60m_high",
]
```

---

# 73. Suggested V1 Stop Grid

```python
STOP_TYPES = [
    "0.5pct_entry",
    "1pct_entry",
    "2pct_entry",
    "3pct_entry",
    "5pct_entry",
    "lod_known_at_entry",
    "trigger_candle_low_known_at_entry",
    "0.25adr",
    "0.333333adr",
    "0.50adr",
    "1.00adr",
    "2.00adr",
]
```

---

# 74. Suggested Result Status Values

```text
VALID_TRADE
NO_ENTRY
INELIGIBLE_NO_10SMA_HISTORY
MISSING_MINUTE_DATA
MISSING_DAILY_DATA
INVALID_STOP_GEOMETRY
CORRUPT_EVENT
```

Never silently drop an event.

---

# 75. Timezone

Use:

> `America/New_York`

All session logic exchange-local and DST-safe.

---

# 76. Regular Session

For V1:

```text
09:30:00 – 16:00:00 ET
```

Entry triggers and stop triggers use regular hours only.

Daily close exit uses official regular-session close.

---

# 77. Market Holidays / Session Offsets

D+1 etc. mean **trading sessions**, not calendar days.

Friday D0 → Monday D+1 if Monday open.

Use exchange calendar.

---

# 78. Data Resolution

Primary execution simulation should use **1-minute OHLCV** if available.

Aggregate longer opening ranges from 1-minute data.

This keeps 5M/10M/15M/30M/60M consistent.

---

# 79. Trigger-Candle Construction

For a 15M strategy:

- defining OR high comes from D0 first 15M aggregate
- later trigger-candle low comes from the 15M bucket containing actual entry timestamp
- use only sub-bars observed through entry

Same concept for 5M/10M/30M/60M.

For 1M:
- trigger candle is the 1-minute bar containing breakout.

---

# 80. Fill Precision

Trigger is one cent over OR high.

For standard $0.01 tick:

```text
trigger = round_to_tick(OR_high + 0.01)
```

Future nonstandard tick issues can be handled later.

---

# 81. V1 Is Trade-Quality Research, Not Portfolio Simulation

Every EP trade is normalized independently.

V1 does not yet model:

- account equity
- simultaneous capital constraints
- max positions
- portfolio CAGR
- portfolio drawdown
- risk budgeting across concurrent trades

Those belong to later portfolio layer.

---

# 82. Trade Quality vs. Portfolio Backtest

Trade-quality backtest asks:

> Which execution rule has edge?

Portfolio simulation asks:

> What happens when finite capital is deployed across overlapping signals?

Keep separate initially.

---

# 83. Future Re-Entry Research

Later can test:

- stopped-out D0 then re-breakout
- second opening-range breakout
- 10/20MA support reclaim
- later consolidation breakout

Not V1.

---

# 84. Future Earnings-Risk Research

Later compare:

- ignore earnings
- sell 25%
- sell 50%
- sell 75%
- sell 100%

This may materially change outlier retention.

---

# 85. Future Partial/Trail Interaction

Do not assume best trail stays best after partial-selling.

Later progression may be:

```text
Entry × Initial Stop
→ Trail
→ Partial Style
→ Partial Spacing
→ Sell Amount
→ Core %
→ BE yes/no
```

Only after narrowing earlier stages.

---

# 86. Overfitting Control by Staging

Entire candidate space can explode.

User explicitly wants iterative isolation.

### V1
72 Entry × Initial Stop combinations

### V2
Take strong V1 regions and add 6 trail styles

### V3
Add partial rules / core / BE

### V4
Add signal filters / interactions

This is both cleaner and statistically safer.

---

# 87. Existing EP Research Context

The broader EP project already found descriptive associations for factors including:

- ADR
- turnover
- relative volume
- market cap
- ATH location
- chart pattern
- candle color
- some interaction variables

But those were mainly future-upside/MFE-style studies, not realized execution backtests.

This engine converts EP event quality into actual strategy outcomes.

Do not assume a factor associated with future MFE automatically improves realized EV.

---

# 88. Main Statistical Objective

Do not optimize win rate alone.

This swing-long style is intended to preserve outlier winners.

Pay special attention to:

- EV
- PF
- RR
- winner tail
- total R
- stability
- later drawdown

Lower WR can be better if winners are much larger.

---

# 89. Tail Contribution — Recommended Later Metric

Calculate:

```text
% Total R from top 1 trade
% Total R from top 5 trades
% Total R from top 1% trades
% Total R from top 5% trades
```

This shows whether edge is broad or monster-trade dependent.

---

# 90. V1 Source of Truth — Compact Summary

## Universe
Historical qualifying EP events.

## Entry
Buy stop-market at:

\[
Day0OpeningRangeHigh + \$0.01
\]

for 1M, 5M, 10M, 15M, 30M, 60M.

## Entry validity
D0 through D+7 trading sessions inclusive.

## Entry level
Fixed from D0 opening range.

## Regular hours
Entry + stops only 9:30–16:00 ET.

## Fill
- normal cross → trigger + slippage
- open/jump through → current regular-session open + slippage

## Stops
12 initial-stop variants.

## Stop reference
Always point-in-time.

## Exit
First finalized daily close below 10SMA, sold at that same close.

## R
Frozen from actual entry fill to original initial stop.

## No entry
Excluded from trade metrics, included in entry-rate metrics.

## Grid
72 strategies.

## Ranking
50% EV score + 50% PF score.

## Analysis
Look for broad parameter regions, not one isolated #1.

---

# 91. Immediate Claude Code Implementation Plan

### Phase 1 — Inspect Data
Identify:

- EP events file/schema
- minute bars storage
- daily bars storage
- ADR field
- chart pattern field
- reaction/event date
- split-adjustment convention

### Phase 2 — Build One-Trade Simulator
Implement one manually specified strategy on one event.

Verify:
- OR high
- fixed trigger
- delayed entry
- fill logic
- LOD
- trigger-candle low
- 10SMA exit
- R

### Phase 3 — Unit Tests
Implement Section 68 toy cases.

### Phase 4 — Run One Strategy Across All EPs
Example:
`15M High + 0.50 ADR stop`

Export trade-level results and manually inspect.

### Phase 5 — Run All 72 V1 Strategies

### Phase 6 — Summarize
Calculate:
- N
- entry rate
- entry-day distribution
- WR
- Avg W
- Avg L
- RR
- PF
- EV
- Total R
- G Score

### Phase 7 — Heatmaps / Surfaces

### Phase 8 — Slice, But Do Not Yet Optimize Filters
Explore:
- chart pattern
- year
- era
- ADR
- gap
- delayed entry day

Do not add new rules until V1 behavior is understood.

---

# 92. What Claude Code Should NOT Do Yet

Do not yet:

- implement profit partials
- implement core %
- implement BE-after-partial
- implement 10MA-touch / 20MA-touch approximations
- optimize chart pattern
- optimize first-candle color
- optimize early volume
- implement pre-earnings selling
- implement re-entry
- build full portfolio equity curve
- add machine learning
- add advanced multiple-testing machinery before basic engine is trusted

First make V1 correct and auditable.

---

# 93. Key User Preferences to Preserve

- Practical > unnecessarily academic.
- Simple and transparent > black box.
- R-based trade comparison is preferred.
- EV and PF matter more than win rate alone.
- Outlier capture matters.
- Isolate parameter families before combining them.
- Keep raw trade-level results.
- Use slicers/pivots after execution.
- Avoid look-ahead.
- Delayed breakout entries are explicitly worth studying.
- One-shot-one-kill initially.
- Build iteratively and learn from each version.

---

# 94. Final One-Sentence Brief for Claude Code

> Build EP Backtest V1 as a point-in-time, 1-minute-driven Python simulator that tests 72 combinations of fixed Day-0 opening-range-high buy-stop entries (1M/5M/10M/15M/30M/60M, valid through D+7) and 12 initial-stop rules, holds every triggered trade until the first finalized close below the 10SMA, reports outcomes in frozen initial-risk R, preserves all trade-level audit data, and ranks parameter regions using the user's 50/50 EV–Profit-Factor G Score without yet adding partials, core, breakeven, chart-pattern filters, or later-stage complexity.

---

# 95. Status

**EP Backtest V1 specification is frozen enough to begin coding.**

V1 slippage default confirmed (2026-08-30), revised same day: flat 0.1% of reference price (originally 1%, revised down after the first full-universe run showed 1% mechanically forced 0% win rates on stops <=2% wide), applied to entry/stop/normal-exit fills alike (see Section 60.1). Placeholder, not a researched cost model.

Intentionally deferred issues:

- exact intraday approximation for plain 10MA/20MA touch trails
- final partial-size grids
- final target-spacing grids
- exact full cost model (beyond the V1 1%-of-reference-price placeholder)
- exact pre-earnings reduction grid if changed
- portfolio capital constraints
- re-entry rules

None of these block V1 implementation.

---

# 96. Master Event Universe — Confirmed (2026-08-30)

`Files/EP/EP V5.xlsx`, sheet `Data`, is now the **master source of EP events / tickers** for this backtest. It supersedes the Benzinga candidate list / EP V4 universe referenced earlier in this document.

Confirmed contents (as of 2026-08-30):

- **2,358 EP events**, **1,079 unique tickers**
- Date range: **2012-05-15 → 2026-08-18**
- 118 columns, including (relevant to V1/V2):
  - `reaction_date`, `ticker` — event identity
  - `Chart Pattern` — already populated with the exact taxonomy assumed in Section 39: `DT`, `DT SW`, `UDS`, `DT U`, `UT`, `U`, `UTU`, `SW`, `CPH`, plus a `DELISTED` category (15 rows) not previously accounted for in this doc
  - `gap_pct`, `adr14` — feed directly into the V1 ADR-stop grid (Section 18/20)
  - `pre_gap_market_cap`, `avg_share_volume_30d`, `dollar_volume_proxy_30d`, `Trading Turnover %` — signal/segmentation features (Section 40-42, 65)
  - `1M/5M/10M/15M/30M/60M Candle Close/Green-Red/Volume/Relative Volume 30D/Dollar Volume` — precomputed opening-candle stats; useful for cross-checking the simulator's own minute-bar-derived OR highs and for the future candle-color/early-volume filters (Section 41-42), but the simulator must still derive its own point-in-time OR high/trigger from raw minute bars per Section 78 rather than trusting these precomputed columns as the entry trigger source, since the trigger geometry (Section 10-11) needs the actual sub-minute price path, not just the closing value of each window.

Open item: the `DELISTED` chart-pattern value (15 events) needs a defined handling rule — most likely folds into the mid-trade data-continuity gap flagged in the prior review (Section 8's unresolved status-code question), since a pre-EP delisting flag may correlate with exactly the kind of ticker where daily-bar history stops mid-hold.

There is also a `Matrix` sheet in `EP V5.xlsx` (11x13) not yet inspected in detail — likely a summary/pivot view, not part of the raw event schema.
