# Swing Long / Episodic Pivot Backtest System — Master Context for Claude Code

**Created:** 2026-08-29  
**Purpose:** Carry forward the full design logic, findings, assumptions, unresolved definitions, and implementation plan for the user's new Python-based swing-long / Episodic Pivot backtester.

---

# 1. Executive Summary

The user is transitioning from a large Excel-based backtesting workflow into a Python backtesting engine.

The old Excel workbook was not merely a spreadsheet of statistics. It functioned as a real event-driven backtesting and parameter-optimization system:

1. Start with a fixed historical event universe.
2. Test multiple entry rules.
3. Test multiple stop rules.
4. Check whether stops would have been touched before the planned exit.
5. Calculate every trade in **R-multiples**.
6. Aggregate strategy-level statistics.
7. Rank execution combinations using a custom score.
8. Isolate one family of parameters at a time by disabling the rest.

The new system should preserve this logic but move the simulation layer into Python.

The new backtest is for **swing-long Episodic Pivot (EP) trades**, not the prior swing-short/day-trading system. It will be materially more complex because positions may:

- enter intraday,
- have multiple possible initial stops,
- sell partials over time,
- maintain a protected core position,
- move the stop to breakeven,
- trail on 10-day / 20-day moving-average logic,
- remain open for many days or weeks,
- and be segmented later by chart pattern and other event characteristics.

The recommended architecture is:

> **Python = simulation / optimization engine**  
> **Parquet + DuckDB = data layer**  
> **Excel = inspection / PivotTable / manual-review layer**

The core design philosophy should remain:

> **Signal → Entry → Initial Stop → Position Management → Exit → R outcome → Strategy Metrics → Ranking → Robustness / OOS Validation**

Do not collapse these layers together.

---

# 2. What the Old Excel Backtester Actually Did

The old workbook was analyzed in detail. Its key tabs were:

- `Updated Backtest Sheet`
- `Pivot`
- `Win 1`
- `Winner R`
- `Loser R`
- `Table`
- `Matrix`

## 2.1 Updated Backtest Sheet

One row represented one historical stock/event.

The sheet contained raw event data plus many derived strategy-result columns.

The old execution grid primarily tested:

### Entry timing
- Day 1 open
- Close of first red 5-minute candle
- Close of first red 10-minute candle
- Close of first red 15-minute candle
- Close of first red 30-minute candle
- Close of first red 60-minute candle

Clarification from user:

> “First 5m red close” means the close of the **first red 5-minute candle**.  
> Same definition for 10m / 15m / 30m / 60m.

### Planned exits
- Day 1 close
- Day 2 open
- Day 2 close
- Day 3 open
- Day 3 close

### Stop families originally designed
- Static % above entry
- Static % above HOD
- Static % above PMHOD

However, the HOD and PMHOD families were deliberately disabled with `NA` in the saved workbook.

The user intentionally wanted to isolate the **static-%-from-entry stop family first**.

The ranking formulas were designed so disabled/invalid `NA` strategies fell to the bottom automatically.

This “isolate one dimension/family before adding another” philosophy should be preserved in the new system.

---

# 3. Old Backtester: Important Sequencing Logic

One of the best parts of the old workbook was that it attempted to model the **price path before the exit**, rather than merely comparing entry price to final exit price.

Example:

A short entered after 30 minutes should not be marked stopped out because price had traded above the stop during the first 10 minutes before the trade even existed.

The old workbook therefore maintained post-entry high fields such as:

- HOD 5M to Close
- HOD 10M to Close
- HOD 15M to Close
- HOD 30M to Close
- HOD 60M to Close

Clarification from user:

> `HOD 30M to Close` meant the high **after the 30-minute entry became valid**.  
> After the first red 30-minute candle formed and the short entered at its close, the sheet checked the HOD from then onward.

This is extremely important.

The Python engine should improve on this by simulating chronologically candle-by-candle, making special “HOD after X” helper columns unnecessary.

---

# 4. Old R-Multiple Accounting

The old system normalized trades using **R**.

For a short:

- Entry = trade entry price
- Initial stop = defined stop
- Initial per-share risk = `Stop - Entry`
- `1R` = initial risk

A normal profitable trade was conceptually:

\[
R = \frac{Entry - Exit}{Stop - Entry} - Costs
\]

A stopped-out trade was approximately:

\[
R = -1 - Slippage_R - Fees_R - Overnight_R
\]

The old assumptions included:

- stop-out slippage = **0.20R**
- commissions / fees / locates = **0.05R**
- overnight cost = **0.07R per night**

Clarification from user:

> These were intentionally expressed as fractions of R.

The user prefers R because it makes strategies with different prices and risk distances comparable.

This preference should remain central to the new system.

---

# 5. Important Improvement to Cost Modeling

Continue **reporting results in R**, but future Python architecture should preferably originate realistic costs in their natural units before converting them to R.

Reason:

If the initial stop width changes, a fixed cost of `0.05R` implies a different dollar/price cost for each stop width.

Example:

- $100 entry
- 1% stop → $1 risk/share
- 5% stop → $5 risk/share

A $0.10/share real transaction cost is:

- 0.10R under the 1% stop
- 0.02R under the 5% stop

Therefore preferred future approach:

1. calculate raw price execution,
2. apply realistic slippage / fees / spread / other cost,
3. compute net P&L,
4. divide net P&L by **initial trade risk**,
5. report final result in R.

For an early V1, simplified R-based cost assumptions are still acceptable if explicitly documented.

---

# 6. Old Strategy-Level Metrics

The old `Table` tab calculated:

- Profit Factor
- EV
- Win Rate
- Avg Winner
- Avg Loser
- Net EV
- Custom G Score

## 6.1 Win Rate

\[
WinRate = \frac{\#WinningTrades}{N}
\]

## 6.2 Average Winner

Mean R among trades where `R > 0`.

## 6.3 Average Loser

Mean R among trades where `R < 0`.

Average loser remains negative.

## 6.4 Risk-to-Reward / RR

Clarification from user:

> **RR means conventional risk-to-reward / payoff ratio.**

Recommended definition:

\[
RR = \frac{AvgWinner}{|AvgLoser|}
\]

This was **not** the same thing as Profit Factor.

## 6.5 Profit Factor

\[
PF = \frac{GrossWinningR}{|GrossLosingR|}
\]

Equivalent under ordinary conditions to:

\[
PF =
\frac{WinRate \times AvgWinner}
{(1-WinRate)\times |AvgLoser|}
\]

## 6.6 Expected Value

\[
EV =
WinRate \times AvgWinner
+
(1-WinRate)\times AvgLoser
\]

Because Avg Loser is negative.

Interpretation:

> **Expected R earned per trade**

## 6.7 Net EV / Total Expected R

Old workbook:

\[
NetEV = EV \times N
\]

This is useful when strategies have different trade counts/frequencies.

If all strategies have the same N, Net EV and EV rank strategies almost identically.

---

# 7. Old G Score — Correct Definition

The user confirmed the intended old score was:

> **50% EV + 50% Profit Factor**

The Matrix text had once shown 45% EV / 35% PF / 20% frequency, but this was not the intended active scoring system.

The actual intended G Score was:

- normalize EV onto a 0–10 scale
- normalize PF onto a 0–10 scale
- average them 50/50

Old caps were approximately:

- EV target/cap: `0.30R`
- PF target/cap: `2.0`

Conceptually:

\[
GScore = 0.50(EVScore) + 0.50(PFScore)
\]

The new Python system can retain G Score as a **ranking preference**, but should never discard the raw statistics.

---

# 8. Small Old Workbook Issues That Should Not Be Repeated

## 8.1 Sample-size denominator error

The old workbook had a `COUNTA()-2` sample-count formula that reported 378 when the Pivot contained 379 actual trades.

This produced tiny distortions in WR / PF / EV.

New rule:

> Never use a manually adjusted global denominator.

Each strategy should compute:

\[
N = \text{count of valid eligible observations for that exact strategy}
\]

## 8.2 Missing strategy in Pivot

The old workbook intentionally omitted `60m entry → Day1 close`.

User confirmed this omission was intentional.

## 8.3 Disabled stop families

HOD and PMHOD stop families were intentionally `NA`.

Do not interpret them as broken strategy formulas.

This was deliberate parameter isolation.

---

# 9. Old Backtester’s Real Conceptual Structure

The old system separated:

## Signal / Setup
“Which historical events belong in this setup universe?”

from:

## Execution
“How should I trade a valid signal?”

The execution search was effectively a **grid search / Cartesian product** over:

> Entry × Stop × Exit

This is a valid systematic-backtesting architecture.

The new Python engine should preserve this separation.

---

# 10. Why Python Is the Natural Next Step

The new long system introduces dynamic position management that becomes unwieldy in Excel:

- partial exits,
- moving stops,
- trailing stops,
- core positions,
- long holding periods,
- daily MA conditions,
- intraday entry timing,
- many parameter combinations.

Python can simulate each position **chronologically**, rather than reverse-engineering outcomes from a huge number of summary columns.

The important conceptual change:

> Do not calculate “what happened eventually” and infer the trade.

Instead:

> Move through market data candle-by-candle and allow the strategy to know only what was available at each timestamp.

---

# 11. New Backtest Parameter Sheet — Current Draft

The user’s new parameter sheet currently contains the following.

---

## 11.1 Chart Pattern

Current pattern categories:

- `CPH`
- `DT`
- `DT SW`
- `DT U`
- `SW`
- `U`
- `UDS`
- `UT`
- `UTU`

Working meanings from prior project context:

- **CPH** = cup and handle
- **DT** = downtrend
- **DT SW** = downtrend then sideways
- **DT U** = downtrend then U-type recovery
- **SW** = sideways
- **U** = U-shaped base/recovery
- **UDS** = up → down → sideways; roughly high-tight-flag-like structural behavior
- **UT** = uptrend
- **UTU** = uptrend then U / fish-hook style reset before the gap

These describe the chart structure **before the EP gap**.

---

## 11.2 Entry Type (Buy)

Current candidate entries:

- `1M Highs`
- `5M Highs`
- `10M Highs`
- `15M Highs`
- `30M Highs`
- `60M Highs`

Likely interpretation to confirm:

> Wait for the opening-range candle to fully form, then place/trigger a long entry when subsequent price trades above that completed candle’s high.

Example candidate definition:

- First 15-minute candle = 9:30–9:45 ET
- Once completed, its high becomes the buy trigger
- Entry can only occur after that high is known
- Price action before the trigger cannot stop out a position that does not yet exist

This requires exact confirmation before coding.

---

## 11.3 Initial Stop Type

Current proposed stop types:

### Static % from entry
- `0.5% From Entry`
- `1% From Entry`
- `2% From Entry`
- `3% From Entry`
- `5% From Entry`

### Structural
- `LOD`
- `Low of Candle`

### ADR-based
- `1 ADR % Entry`
- `1/2 ADR % Entry`
- `2 ADR % Entry`
- `1/3 ADR % Entry`
- `1/4 ADR % Entry`

Recommended internal normalization:

- `0.25 ADR`
- `0.3333 ADR`
- `0.50 ADR`
- `1.00 ADR`
- `2.00 ADR`

---

# 12. Potential Look-Ahead Issue: LOD Stop

The Python engine must define LOD carefully.

Incorrect:

> Use the final Day-1 low, even if that low occurs hours after the entry.

Correct candidate definition:

> At the exact entry timestamp, use the **lowest traded low observed up to that moment**.

For example, if the 30m breakout entry happens at 10:08:

\[
KnownLOD_{entry} =
\min(Low_{9:30}, ..., Low_{10:08})
\]

That value can become the initial LOD stop.

This avoids look-ahead bias.

Definition still requires user confirmation.

---

# 13. Potential Definition: Low of Candle

Likely interpretation to confirm:

If entry type = `15M High`:

- opening-range candle is 9:30–9:45
- entry trigger = its high
- `Low of Candle` stop = low of that same completed 15-minute candle

Likewise for 1m / 5m / 10m / 30m / 60m.

Needs explicit confirmation.

---

# 14. ADR Stop Concept

Likely intended logic:

If pre-gap ADR = 6%:

- `1/4 ADR` = 1.5% stop below entry
- `1/3 ADR` = 2.0%
- `1/2 ADR` = 3.0%
- `1 ADR` = 6.0%
- `2 ADR` = 12.0%

Preferred formula for a long:

\[
StopPrice = Entry \times (1 - ADRPct \times ADRMultiplier)
\]

Important question:

> ADR should almost certainly be the **pre-gap 14-day ADR**, excluding the EP day itself.

This is not yet formally confirmed in the current conversation.

---

# 15. Trailing Stop Type

Current proposed rules:

- `10MA`
- `Close below 10MA`
- `Low of the Close below 10MA`
- `20MA`
- `Close below 20MA`
- `Low of the Close below 20MA`

These are **position-management rules**, not initial stops.

They should generally activate after entry and potentially after some other milestone depending on final design.

---

# 16. Important MA Timing Distinctions

These variants are very different and must not be conflated.

## 16.1 10MA

Possible interpretation:

> A live stop is placed at the 10-day moving average.  
> If intraday price touches/breaks it, exit immediately.

## 16.2 Close Below 10MA

Possible interpretations:

### Option A
Exit at the same day’s close once the close is known to be below the 10MA.

### Option B
Signal becomes known at close; exit next day open.

Option B is strictly cleaner if using only end-of-day confirmation without a market-on-close execution model.

Must be explicitly chosen.

## 16.3 Low of the Close-Below-10MA Day

Likely concept:

1. A daily bar closes below the 10MA.
2. Do not immediately exit.
3. Use that bar’s low as a new stop.
4. Allow the stock to reclaim the MA if the low does not break.

Needs precise confirmation.

Same questions apply to 20MA variants.

---

# 17. Profit Target / Partial-Sale Logic

Current parameter sheet:

### Profit Target
- `Every X% Sell`
- `Every X candles Sell`

### Profit %
- `X%`

This is substantially more complex than the old backtester because a trade can now have multiple executions and changing remaining size.

---

# 18. Correct Mental Model for Position Management

The engine should represent a position using **shares or normalized position units**.

Example:

- initial position = 100 units
- entry = $100
- initial stop = $95
- risk/share = $5
- initial total risk = `$500`
- therefore `1R = $500`

Suppose:

- sell 20 units at +10%
- sell 20 units at +20%
- sell 20 units at +30%
- preserve 40-unit core
- trail core with 10MA

The engine should maintain state:

- shares/units remaining
- realized P&L
- current stop
- initial stop
- initial R in dollars
- next target
- whether first partial has occurred
- whether breakeven has activated
- whether core floor has been reached

Final trade R:

\[
TradeR =
\frac{
\sum RealizedPnL_{partials} + RealizedPnL_{final}
}{
InitialRiskDollars
}
\]

**Initial risk must remain the R denominator for the entire trade.**

Do not redefine 1R after the stop moves.

---

# 19. Core %

Current proposed parameter:

> `Core %` in **10% increments**

Likely intended grid:

- 10%
- 20%
- 30%
- 40%
- 50%
- 60%
- 70%
- 80%
- 90%
- possibly 100%

Open question:

> Include `0%` core for a pure scale-out strategy?

Likely semantics:

> If `Core = 30%`, profit-target partials are not allowed to reduce the remaining position below 30% of original size.

The final 30% is reserved for the trailing-stop logic.

Needs confirmation.

---

# 20. Breakeven Stop After First Sell

Current parameter:

> `Yes / No`

Likely logic if enabled:

1. Trade reaches first partial-sale condition.
2. Execute first partial.
3. Stop on remaining shares moves to breakeven.
4. Later trailing stops can only replace breakeven if they tighten the stop further.

Open question:

> Is “breakeven” exactly original entry or entry adjusted for costs?

Recommended simple V1 definition:

\[
BEStop = EntryPrice
\]

Later cost-adjusted BE may be added if needed.

---

# 21. “Fundamentals” Row in Parameter Draft

Current cells:

- `Green / Red Candle?`
- `ADV per Minute Candle?`

These are not actually conventional fundamentals.

They are more accurately **event / intraday context features**.

Recommended future naming:

> `Signal Features / Context`

rather than `Fundamentals`.

---

# 22. Green / Red Candle Feature

The exact candle is not yet defined.

Potential interpretations:

- 1-minute opening candle
- 5-minute opening candle
- 15-minute opening candle
- whole EP gap-day daily candle

This must be resolved.

The EP V4 research already found opening-candle color to be a meaningful descriptive variable, especially in combination with ADR / gap size in some horizons.

However, it should initially be treated as a **segmentation feature**, not automatically multiplied into every execution strategy.

---

# 23. ADV per Minute Candle Feature

This is currently ambiguous.

Possible intent:

> Compare early-session cumulative volume with pre-gap average daily share volume.

Examples:

\[
First5mADVFrac =
\frac{SharesTradedFirst5m}{PreGap30DAvgDailyShares}
\]

or a speed-normalized measure:

\[
VolumePace =
\frac{First5mVolume / 5}
{PreGapAvgDailyVolume / NormalSessionMinutes}
\]

The user's EP project already contains early relative-volume / cumulative-volume research.

Do not invent the exact definition until the user confirms it.

---

# 24. Signal Variables vs. Execution Variables

This separation is crucial.

## Signal / setup features
Examples:

- Chart Pattern
- ADR
- Gap size
- Candle color
- RVOL
- IPO age
- Market cap
- turnover
- EPS / revenue surprise
- SPY regime

These answer:

> **Which EPs should I trade?**

## Execution variables
Examples:

- 1m/5m/15m/30m/60m high entry
- initial stop type
- breakeven logic
- partial schedule
- core %
- trailing stop

These answer:

> **How should I trade a valid EP?**

Do not immediately put both groups into one massive Cartesian product.

---

# 25. Recommended Treatment of Chart Pattern

Do **not** initially create nine independent versions of every execution strategy for:

- CPH
- DT
- DT SW
- DT U
- SW
- U
- UDS
- UT
- UTU

Instead:

1. Backtest execution on the full eligible EP universe.
2. Store chart pattern on every trade row.
3. Afterward calculate:
   - overall execution performance,
   - performance by chart pattern,
   - interaction / conditional effects where justified.
4. Only promote chart pattern into a formal strategy filter if the pattern difference is stable and sufficiently supported.

This greatly reduces overfitting and preserves sample size.

---

# 26. Why Brute-Forcing Everything at Once Is Dangerous

Suppose the system includes:

- 6 entries
- 12 initial stops
- 6 trails
- 5 profit increments
- 10 core percentages
- 2 breakeven states

That alone is:

\[
6 \times 12 \times 6 \times 5 \times 10 \times 2
= 43,200
\]

execution combinations.

If multiplied by 9 chart patterns:

\[
43,200 \times 9 = 388,800
\]

candidate strategies.

This is computationally possible.

The larger problem is **statistical data mining / overfitting**.

Therefore the backtest should be staged.

---

# 27. Recommended Development Stages

## V1 — Entry + Initial Stop

Goal:

> Determine which opening-range entry and initial-stop families produce favorable initial trade geometry.

Test:

- 1m / 5m / 10m / 15m / 30m / 60m high
- static % stops
- LOD
- candle low
- ADR stops

Use a deliberately simple exit for V1.

Possible simple exit choices to define:

- fixed holding period,
- fixed daily close,
- simple technical trail.

The key is to avoid introducing all partial logic immediately.

---

## V2 — Trailing Stop

Take the strongest **region/family** from V1, not merely one exact cell.

Add:

- 10MA
- close below 10MA
- low of close-below-10MA day
- 20MA
- close below 20MA
- low of close-below-20MA day

Study parameter surfaces and stability.

---

## V3 — Partial Taking + Core

Then test:

- every X% partials,
- every X candles partials,
- core size,
- breakeven after first sale.

This is where the simulator becomes a true position state machine.

---

## V4 — Conditional Signal Features

Only after execution logic is reasonably stable:

- chart pattern
- green/red candle
- early volume
- ADR
- gap
- turnover
- IPO age
- etc.

Test whether these meaningfully improve trade selection.

---

# 28. Critical Robustness Principle: Find Plateaus, Not One Magic Cell

Do not conclude:

> “15M entry + 0.5 ADR stop is the best strategy because it ranked #1.”

Instead inspect the whole parameter neighborhood.

Desired result:

| Entry \ Stop | .25 ADR | .33 ADR | .50 ADR | 1 ADR | 2 ADR |
|---|---:|---:|---:|---:|---:|
| 1M | weak | okay | okay | okay | weak |
| 5M | okay | good | good | good | okay |
| 10M | good | strong | strong | strong | good |
| 15M | good | strong | strongest | strong | good |
| 30M | okay | strong | strong | strong | good |
| 60M | weak | okay | good | okay | weak |

If several neighboring settings work:

> Likely robust parameter region.

If one isolated cell is great and every adjacent setting is poor:

> Likely overfit / noise.

This should become a core visual output of the Python system.

---

# 29. Recommended Python Simulation Model

The cleanest long-term architecture is a **state machine** that iterates candle-by-candle.

Pseudo-state:

```text
NO_POSITION
    ↓
WAITING_FOR_ENTRY_TRIGGER
    ↓
OPEN_POSITION
    ↓
PARTIALS_ACTIVE
    ↓
CORE_ONLY
    ↓
EXITED
```

At each candle, the engine asks:

```text
If no position:
    Is the opening range complete?
    Is the entry trigger now known?
    Has price crossed the trigger?

If position exists:
    Did initial/current stop trigger?
    Did a profit target trigger?
    Should a partial be sold?
    Did first partial activate breakeven?
    Has the core floor been reached?
    Did trailing-stop condition activate?
    Did final exit occur?
```

This is much safer than trying to calculate final outcomes using one giant vectorized formula.

---

# 30. Recommended Python Strategy Object

A strategy can be represented as configuration data.

Example:

```python
strategy = {
    "entry_type": "15m_high",
    "initial_stop_type": "0.5_adr",
    "trailing_stop_type": "close_below_10ma",
    "profit_take_type": "every_x_pct",
    "profit_step_pct": 0.10,
    "core_pct": 0.30,
    "breakeven_after_first_sell": True,
}
```

Important:

> Strategy parameters should be **data**, not hardcoded into separate functions for every combination.

The simulator reads the config and behaves accordingly.

---

# 31. Suggested Code Modules

A Claude Code implementation should eventually separate concerns.

Example repository structure:

```text
backtest/
│
├── config/
│   ├── strategy_grids.py
│   └── constants.py
│
├── data/
│   ├── loaders.py
│   ├── market_calendar.py
│   └── feature_join.py
│
├── engine/
│   ├── simulator.py
│   ├── entry_rules.py
│   ├── initial_stop_rules.py
│   ├── trailing_stop_rules.py
│   ├── profit_taking.py
│   ├── position.py
│   └── execution.py
│
├── metrics/
│   ├── trade_metrics.py
│   ├── strategy_metrics.py
│   ├── g_score.py
│   └── robustness.py
│
├── optimization/
│   ├── grid_search.py
│   ├── parameter_surfaces.py
│   └── walk_forward.py
│
├── outputs/
│   ├── trade_results/
│   ├── strategy_results/
│   ├── charts/
│   └── excel_exports/
│
└── tests/
    ├── test_entry_rules.py
    ├── test_stop_rules.py
    ├── test_partial_sales.py
    ├── test_trailing_stops.py
    └── test_no_lookahead.py
```

Do not overbuild this entire structure on day one.

Start small, but preserve clean boundaries.

---

# 32. Suggested Core Function Signatures

Example conceptual API:

```python
simulate_trade(
    event,
    minute_bars,
    daily_bars,
    strategy,
    cost_model
) -> TradeResult
```

Then:

```python
run_strategy(
    events,
    strategy,
    data_store
) -> list[TradeResult]
```

Then:

```python
summarize_strategy(
    trade_results
) -> StrategyMetrics
```

Then:

```python
run_grid(
    events,
    strategy_grid
) -> StrategySummaryTable
```

---

# 33. Recommended Trade Result Schema

Every simulated trade should preserve enough information to audit it later.

Suggested columns:

```text
strategy_id
ticker
event_date
chart_pattern

entry_type
entry_timestamp
entry_price

initial_stop_type
initial_stop_price
initial_risk_per_share

position_units_initial

first_partial_timestamp
first_partial_price
partials_count

core_pct
breakeven_enabled
breakeven_activated_timestamp

trailing_stop_type
final_exit_timestamp
final_exit_price
final_exit_reason

gross_pnl
costs
net_pnl
realized_R

max_favorable_R
max_adverse_R

holding_minutes
holding_days

stopped_out
never_triggered_entry
data_quality_flag
```

Additional event features may be attached:

```text
ADR
gap_pct
market_cap
turnover
IPO_age
early_rvol
candle_color
SPY_regime
EPS_surprise
Revenue_surprise
...
```

This table becomes the replacement for the old giant `Pivot` source.

---

# 34. Recommended Strategy Summary Schema

One row per strategy:

```text
strategy_id

entry_type
initial_stop_type
trailing_stop_type
profit_take_type
profit_step
core_pct
breakeven

eligible_events
triggered_trades
entry_rate

wins
losses
breakevens

win_rate
avg_winner_R
avg_loser_R
RR
profit_factor
EV_R
total_R

median_R
std_R

max_drawdown_R
max_drawdown_pct_if_portfolio_mode

avg_hold_days
median_hold_days

positive_years
negative_years
worst_year_EV
best_year_EV

G_score
```

Do not rank solely on G Score.

Always keep the complete metric record.

---

# 35. Strategy IDs

Use deterministic strategy IDs based on configuration.

Example:

```text
E15M__S050ADR__TCL10__PX10__CORE30__BE1
```

or use a hash plus readable columns.

The key requirement:

> The same parameter combination must always map to the same ID.

This makes audit and comparison easy.

---

# 36. Data Layer Recommendation

The current EP event universe already exists separately from execution data.

Suggested data architecture:

## `ep_events.parquet`
One row per EP event.

Possible fields:

- ticker
- reaction_date
- chart pattern
- pre-gap ADR
- gap %
- market cap
- dollar volume
- turnover
- IPO age
- EPS / revenue features
- early-volume fields
- regime fields
- etc.

## Minute bars
Partitioned by ticker/date or date.

Fields:

- timestamp
- open
- high
- low
- close
- volume

## Daily bars

Fields:

- date
- open
- high
- low
- close
- volume
- 10DMA
- 20DMA
- other calculated fields as needed

Suggested stack:

- Python
- Pandas or Polars
- Parquet
- DuckDB

Excel remains optional for final review/output.

---

# 37. Avoid Look-Ahead Bias Everywhere

The new engine must enforce point-in-time behavior.

Examples:

## Opening-range high
Cannot be known until that opening-range candle is complete.

## LOD
Only low **known at the entry timestamp** may define the stop.

## Daily 10MA / 20MA
Must use moving-average information available at that time.

## Close-below-MA rule
Cannot use a closing signal before the close exists.

## Future chart labels
Manual pre-gap chart patterns are okay only if they were classified from price history preceding the gap.

## Fundamentals
Must remain point-in-time if later used as filters.

---

# 38. Entry Fill Modeling Needs Explicit Rules

A buy-stop trigger needs a fill model.

Potential hierarchy:

### Simplest V1
If a minute bar trades through the trigger:

\[
Fill = TriggerPrice
\]

### More realistic
If minute opens above the trigger:

\[
Fill = MinuteOpen
\]

Otherwise:

\[
Fill = TriggerPrice + Slippage
\]

This prevents impossible fills when price gaps/jumps through the level.

Exact rule has not yet been selected.

---

# 39. Same-Bar Ambiguity

Minute OHLC does not reveal the exact sequence of high and low inside the minute.

If, after entry, the same 1-minute candle contains both:

- entry trigger,
- stop level,

the engine may not know which occurred first.

This must have a defined policy.

Possible conservative rule:

> If intrabar order is unknowable and both entry and stop are touched in the same bar, assume the adverse sequence.

Or use finer data if available.

This issue should be explicitly tested and documented.

---

# 40. Daily MA Exit Timing

Likewise, a “close below 10MA” strategy needs a precise execution assumption.

Possible clean implementation:

```text
At daily close:
    calculate whether close < 10DMA

If yes:
    execute next session open
```

Alternative:

> model a market-on-close order if the signal is designed to be acted on in the final seconds.

Do not silently use the same closing price as both the signal-generating data and the fill unless that is explicitly justified.

---

# 41. R Must Be Frozen at Initial Risk

For every trade:

\[
InitialRiskPerShare = |Entry - InitialStop|
\]

If using normalized 100-unit size:

\[
InitialRiskDollars =
InitialRiskPerShare \times InitialUnits
\]

Then throughout the entire trade:

\[
1R = InitialRiskDollars
\]

Even after:

- partial sales,
- stop to breakeven,
- MA trailing stop,
- core-only phase.

This keeps outcomes comparable.

---

# 42. Position Sizing vs. R Outcome

There are two distinct concepts.

## Trade-quality backtest
Normalize every trade to 1R initial risk.

Useful for:

- EV
- RR
- PF
- strategy comparison

## Portfolio backtest
Size actual positions based on account equity/risk budget and simulate overlapping positions.

Useful later for:

- CAGR
- portfolio drawdown
- capital utilization
- exposure
- correlation
- simultaneous signals

The new system should begin with **trade-quality backtesting**, as the old workbook did.

Portfolio simulation should be a later layer.

---

# 43. Frequency Should Be Reported Even If Not in G Score

The confirmed G Score is:

> 50% EV / 50% PF

Frequency should not be secretly injected into G Score.

But strategy output should still report:

- eligible events
- triggered entries
- entry rate
- N
- trades/year

A strategy with extraordinary EV from 20 trades should not be interpreted the same as one with similar EV from 1,000 trades.

---

# 44. Entry Rate Is Especially Important

Some opening-range entry types may simply never trigger for many EPs.

Example:

- 1m high may trigger on 95% of events
- 60m high may trigger on 55%

Therefore distinguish:

```text
Eligible events
Triggered trades
Entry rate
```

Do not treat “no entry” as a loss.

---

# 45. Win / Loss / Breakeven Definition

Old workbook used:

- win if `R > 0`
- otherwise effectively non-win

New engine should explicitly define:

- Win: `R > epsilon`
- Loss: `R < -epsilon`
- Breakeven: within ±epsilon

This prevents tiny floating-point transaction-cost noise from creating fake wins/losses.

---

# 46. Recommended Additional Metrics

Preserve old metrics:

- N
- WR
- Avg Winner
- Avg Loser
- RR
- PF
- EV
- Total R
- G Score

Add:

- median R
- standard deviation of R
- 25th / 75th percentile R
- 90th / 95th percentile R
- maximum trade R
- maximum loss R
- max favorable excursion in R
- max adverse excursion in R
- average hold time
- median hold time
- annual EV
- annual PF
- annual WR
- performance by era/regime
- positive-year count
- worst-year result
- confidence interval around EV
- bootstrap distribution of EV if needed later

Do not overcomplicate V1; store trade-level data so these can be calculated later.

---

# 47. The New Backtest Should Optimize Outliers, Not Just Win Rate

This swing-long EP project is structurally capable of producing large outlier winners.

Therefore a strategy with:

- lower win rate,
- modest losses,
- very large winners,

may be superior to a high-WR strategy that cuts all tails.

RR, PF, EV, tail contribution, and winner distribution matter.

Do not optimize only for win rate.

---

# 48. Outlier Attribution

Later, useful analysis:

```text
What % of Total R came from:
top 1 trade?
top 5 trades?
top 1% of trades?
top 5% of trades?
```

This helps distinguish:

- genuine broad edge,
- edge dependent on a few monster EPs.

For Qullamaggie-style swing systems, tail dependence is expected to some degree, but should be understood.

---

# 49. Development Sample vs. Validation Sample

The old workbook mainly ranked all candidate executions on the same sample.

The new process should improve this.

Recommended:

## Development / in-sample
Used to:

- compare entries,
- compare stops,
- rank parameter families,
- identify strong regions.

## Validation / OOS
Used only after candidate rules are chosen.

Questions:

- Does EV remain positive?
- Does PF remain healthy?
- Is performance directionally similar?
- Does the neighboring parameter region remain strong?
- Does it survive different eras?

Do not keep tweaking the strategy on the OOS period or it stops being OOS.

---

# 50. Walk-Forward / Era Validation Later

Because EP data spans many market environments, later validation should include:

- pre-COVID
- COVID momentum era
- 2022 bear/chop
- post-2022 / recent era

The exact splits can be defined later.

The point is not that a strategy must perform identically every year.

The point is to understand whether it:

- completely dies outside one regime,
- degrades gracefully,
- or maintains a persistent edge.

---

# 51. Parameter Surface / Heatmap Output

A major desired Python output is a parameter landscape.

Example:

```text
Rows = Entry Type
Columns = Initial Stop Type
Cell = EV / PF / G Score
```

Produce separate heatmaps for:

- EV
- PF
- G Score
- N
- RR

Then later:

```text
Entry × Trail
Stop × Trail
Profit Step × Core %
```

This is more informative than a simple rank list.

---

# 52. Ranking Should Favor Robust Families

Recommended strategy-selection hierarchy:

1. Strong raw EV
2. Healthy PF
3. Adequate N
4. Reasonable RR
5. Neighboring parameter combinations also work
6. Stable across years/regimes
7. Survives OOS
8. Operationally realistic

Then use G Score as a concise ranking layer.

Do not choose a brittle #1 simply because it wins by 0.01 score.

---

# 53. Python Grid Search Example

Conceptually:

```python
from itertools import product

entries = [
    "1m_high",
    "5m_high",
    "10m_high",
    "15m_high",
    "30m_high",
    "60m_high",
]

stops = [
    "0.5pct_entry",
    "1pct_entry",
    "2pct_entry",
    "3pct_entry",
    "5pct_entry",
    "lod",
    "entry_candle_low",
    "0.25adr",
    "0.333adr",
    "0.5adr",
    "1adr",
    "2adr",
]

for entry, stop in product(entries, stops):
    strategy = {
        "entry_type": entry,
        "initial_stop_type": stop,
    }
    run_strategy(strategy)
```

Later dimensions can be added once earlier stages are understood.

---

# 54. Do Not Materialize Every Strategy as Spreadsheet Columns

The old Excel design created separate strategy-result columns.

Python should use **long-format result tables**.

Preferred:

| strategy_id | ticker | date | R |
|---|---|---|---:|
| S001 | NVDA | ... | 3.2 |
| S001 | APP | ... | -1.0 |
| S002 | NVDA | ... | 2.7 |

This scales much better.

Excel PivotTables can recreate the wide view later if desired.

---

# 55. Unit Tests Are Extremely Important

Because this is custom financial simulation code, small bugs can create huge false edges.

Build hand-verified toy cases.

Examples:

## Entry test
- opening 15m high = 105
- next bars stay below → no entry
- later high = 106 → entry triggers

## Pre-entry stop test
- price fell to 90 before entry
- entry later occurs at 105
- stop based on post-entry logic must not be triggered by the earlier 90

## LOD-known-at-entry test
- known LOD at entry = 97
- eventual EOD LOD = 92
- initial stop must use 97, not 92

## Partial test
- targets 110, 120
- verify exact units sold

## Core floor test
- 30% core
- profit algorithm must never sell below 30 units out of original 100

## BE test
- first partial hits
- remaining stop moves to entry

## MA close test
- close crosses below MA
- exit occurs according to selected timing convention

Every complex rule should have a small deterministic unit test.

---

# 56. Auditability Requirement

Every trade should be reproducible.

Ideal debug output for one trade:

```text
2024-02-22 09:45 — 15m opening range complete
OR High = 51.20
OR Low = 48.90

09:53 — price trades 51.20
ENTRY 100 units @ 51.20

Initial stop = 48.90
Initial risk = 2.30/share
1R = 230 dollars

Day 3 — target +10% reached
SELL 20 @ 56.32
Stop moved to BE = 51.20

Day 8 — target +20% reached
SELL 20 @ 61.44

Day 19 — close below 10DMA signal

Day 20 open
EXIT remaining 60 @ 65.10

Gross P&L = ...
Costs = ...
Final R = ...
```

A debug/trade-log mode like this will make the engine much easier to trust.

---

# 57. Recommended Data-Timezone Handling

All intraday trading logic should use one consistent market timezone:

> **America/New_York**

Do not mix UTC and Eastern silently.

Store UTC if convenient, but convert explicitly for session rules.

Need to handle:

- DST
- half days if relevant
- market holidays
- premarket if later used

---

# 58. Session Scope Needs Definition

For current EP entries, likely regular-session opening range:

- 9:30 ET onward

Open questions:

- Is premarket price used in entry triggers?
- Can stops trigger in after-hours?
- Can stops trigger in premarket on later days?
- Are MA exits regular-session only?

The old short workbook explicitly modeled PM/AH highs, so this question matters.

The new system has not yet defined extended-hours stop behavior.

---

# 59. Maximum Holding Period Needs Definition

Trailing-MA strategies can theoretically remain open a long time.

Need a hard policy.

Possible:

- no maximum; exit only by strategy rule,
- 3 months,
- 6 months,
- 12 months,
- end before next earnings report,
- whichever comes first.

Not yet defined.

---

# 60. Overlapping EPs / Repeat Signals Need Definition

Possible scenario:

- stock has EP #1
- position remains open
- same ticker reports another earnings event and produces EP #2

Need policy:

- ignore second signal while position exists,
- pyramid/add,
- close/restart,
- allow separate virtual trades.

For **trade-quality research**, easiest initial policy may be to treat each EP independently.

For portfolio realism later, overlapping same-ticker signals must be handled.

---

# 61. Corporate Actions / Splits

Any long-horizon position simulation must ensure price series is split-consistent.

The entry, stop, targets, and MA series must all use the same adjustment convention.

Do not mix:

- adjusted daily bars
- unadjusted intraday bars

without proper split handling.

This should be verified in the data pipeline.

---

# 62. New System: Unresolved Questions to Answer Before Coding

The following questions were intentionally left open.

They should be answered explicitly before V1 implementation.

## Entry Definition

1. Does `1M High` mean buy as soon as price trades above the high of the **first completed 1-minute candle**, so earliest possible entry is after 9:31?

2. Same for 5M/10M/15M/30M/60M: is the trigger based on the first completed opening-range candle?

3. If price jumps/gaps through the entry trigger, what fill should be assumed?
   - exact trigger
   - next available price / bar open
   - trigger + slippage

4. If the opening-range candle closes at its high, the system cannot have entered before that candle completed. Confirm entry begins only afterward.

---

## Initial Stop

5. Static stop for a long:
   \[
   Stop = Entry \times (1 - X\%)
   \]
   Confirm.

6. Does `LOD` mean LOD known **at the exact entry timestamp**?

7. Does `Low of Candle` mean the low of the opening-range candle used to define the entry?

8. ADR stop:
   - is ADR the pre-gap 14-day ADR?
   - does `1 ADR` mean one full ADR percentage below entry?

9. Normalize ADR multipliers internally to:
   - 0.25
   - 0.3333
   - 0.50
   - 1.00
   - 2.00
   Confirm.

---

## Trailing Stops

10. Does plain `10MA` mean an intraday stop directly at the current 10DMA?

11. `Close below 10MA`:
   - sell at same close?
   - sell next day open?

12. `Low of the Close below 10MA`:
   - after a close below 10MA, use that day’s low as a stop on subsequent days?
   - confirm exact logic.

13. Same three questions for 20MA variants.

---

## Profit Taking

14. `Every X% Sell`:
   Are targets measured from **original entry price**:
   - +X%
   - +2X%
   - +3X%
   - etc.?

15. How much position is sold at each profit target?

16. What X% values should be tested?
   Example:
   - 5%
   - 10%
   - 15%
   - 20%
   - 25%
   - etc.

17. `Every X candles sell`:
   - what candle timeframe?
   - daily candles?
   - how much gets sold at each interval?

---

## Core

18. Does `30% core` mean partial-taking logic can never reduce the position below 30% of original size?

19. Test core from 10% through 100% in 10% increments?
   Include 0%?

---

## Breakeven

20. After first partial:
   - exact entry price as BE?
   - or cost-adjusted BE?
   - should later trailing stop replace BE only when higher?

---

## Context Features

21. `Green/Red Candle`:
   Which candle exactly?

22. `ADV per Minute Candle`:
   Define formula precisely.

23. Confirm chart pattern should initially be stored as a segmentation feature rather than multiplied into every strategy combination.

---

## Holding / Event Handling

24. How long may the trade remain open?

25. What happens at the next earnings report while still holding?

26. Can more than one virtual trade exist in the same ticker simultaneously?

---

## R Accounting

27. Confirm:
   > `1R` is fixed using original entry-to-original-stop distance for the entire life of the trade.

Strong recommendation: **Yes.**

---

## Development Sequence

28. Confirm preferred staged approach:

- V1 Entry × Initial Stop
- V2 Trailing Stop
- V3 Partial sales / Core / BE
- V4 Conditional signal features

Strong recommendation: **Yes.**

---

# 63. Additional Questions Claude Code Should Ask Before Implementation

Beyond the 28 questions above, also clarify:

29. Regular-hours-only stops or can PM/AH stop the trade?

30. Can entry occur only on Day 1, or can an untriggered opening-range breakout remain valid later in the day / subsequent day?

31. Is there a latest Day-1 entry cutoff?
   Example:
   - 11:00 ET
   - noon
   - any time before close

32. Does the buy trigger require:
   - trade above high by one cent/tick,
   - trade at high,
   - close above high?

33. What is the tick-size / rounding convention?

34. Are entries assumed at 100 normalized shares/units for simulation?

35. How should trading halts be handled?

36. How should missing minute bars be handled?
   - skip event
   - conservative assumption
   - fallback to another timeframe

37. How are delisted names handled during long holding periods?

38. Should dividends matter during holding periods?

39. If the stop and profit target are both crossed in the same one-minute bar, what order is assumed?

40. If multiple partial targets are jumped through in one gap, are all crossed targets filled?
   - at target levels
   - at opening price
   - one partial only

These are implementation details, but they can materially affect results.

---

# 64. Suggested Minimal V1 Scope

Do not start with every parameter from the screenshot.

A sensible first implementation:

## Universe
Existing EP event dataset.

## Entries
- 1m high
- 5m high
- 10m high
- 15m high
- 30m high
- 60m high

## Initial stops
- 0.5%
- 1%
- 2%
- 3%
- 5%
- LOD-known-at-entry
- opening-range candle low
- 0.25 ADR
- 0.333 ADR
- 0.5 ADR
- 1 ADR
- 2 ADR

## Simple V1 exit
Choose one intentionally simple standardized exit before coding.

Examples:
- fixed Day N close,
- simple 10DMA exit,
- another single deterministic rule.

Then calculate:

- N
- entry rate
- WR
- Avg W
- Avg L
- RR
- PF
- EV
- Total R
- G Score

Use this to understand Entry × Stop first.

---

# 65. Why a Simple V1 Exit Is Necessary

Entry quality cannot be evaluated without an exit, but adding six trailing stops and twenty partial-sale variants immediately makes it impossible to know **why** a combination wins.

The user’s old approach was strong because it deliberately isolated strategy families.

Follow the same philosophy:

> Answer one research question at a time.

Example sequence:

### Research Question 1
Which opening-range entry timing is best?

### Research Question 2
Conditional on a strong entry region, which initial-stop family is best?

### Research Question 3
Which trailing style preserves outliers best?

### Research Question 4
Does systematic partial-taking improve EV/PF/drawdown?

### Research Question 5
How much core should be retained?

### Research Question 6
Does breakeven-after-first-sale help or truncate tails?

This is scientifically cleaner than mixing all variables immediately.

---

# 66. G Score Usage in the New System

Keep:

\[
GScore = 50\% EVScore + 50\% PFScore
\]

But improve ranking presentation.

For every top strategy, show:

- rank
- G Score
- EV
- PF
- WR
- RR
- N
- total R
- entry rate
- yearly stability

Also compare it to nearby strategies.

Do not report only “Rank #1”.

---

# 67. Potential Future G Score Improvements

Do **not** add these immediately.

Possible later additions only if justified:

- minimum-N gate
- stability penalty
- OOS score
- drawdown penalty
- tail-concentration flag

But simplicity is preferred.

The confirmed user preference is still a simple 50/50 EV/PF score.

---

# 68. Export Back to Excel

Python can generate:

```text
Trade Results.xlsx
Strategy Summary.xlsx
Parameter Heatmaps.xlsx
```

or CSV/Parquet equivalents.

Suggested Excel tabs:

- `Strategy Summary`
- `Trade Level`
- `By Year`
- `By Chart Pattern`
- `By ADR`
- `By Gap`
- `By Regime`

This preserves the user's ability to PivotTable and inspect results manually.

---

# 69. Suggested Workflow for Claude Code

Once definitions are answered:

### Step 1
Inspect existing EP data files and current code/data schemas.

### Step 2
Identify minute-bar and daily-bar source format.

### Step 3
Write a tiny single-trade simulator.

### Step 4
Hand-verify 5–10 trades against charts.

### Step 5
Add all V1 entry types.

### Step 6
Add all V1 initial-stop types.

### Step 7
Generate trade-level long-format output.

### Step 8
Generate strategy summaries.

### Step 9
Reproduce EV / PF / RR / G Score.

### Step 10
Create heatmaps / parameter surfaces.

### Step 11
Only after validation, add V2 trailing-stop module.

Do not jump directly to a giant optimizer.

---

# 70. Core Philosophy to Preserve

The strongest aspects of the user's original Excel approach were:

1. **Trade-level transparency**
2. **R normalization**
3. **Explicit stop sequencing**
4. **Parameter grid search**
5. **Separating signal from execution**
6. **Isolating parameter families**
7. **Keeping raw outcomes**
8. **Ranking by EV and PF rather than win rate alone**

The Python migration should make these better, not replace them with a black-box backtesting library.

---

# 71. North-Star Architecture

Final conceptual pipeline:

```text
Historical EP Universe
        ↓
Point-in-Time Event Features
        ↓
Minute / Daily Market Data
        ↓
Execution Strategy Config
        ↓
Chronological Trade Simulator
        ↓
Trade-Level Results in R
        ↓
Strategy-Level Metrics
        ↓
EV / PF / RR / WR / N / Total R
        ↓
50/50 EV-PF G Score
        ↓
Parameter Surface / Robustness Analysis
        ↓
Year / Era / Pattern Segmentation
        ↓
OOS / Walk-Forward Validation
        ↓
Final Strategy Rules
```

---

# 72. One-Sentence Brief for Claude Code

> Build a point-in-time Python event-driven backtester for historical Episodic Pivot long trades that reproduces the user's old Excel philosophy—chronological entry/stop simulation, fixed initial-R accounting, exhaustive but staged parameter testing, EV/PF-based ranking, and fully auditable trade-level outputs—while adding dynamic partial sales, core retention, breakeven logic, and MA trailing stops in later versions.

---

# 73. Immediate Next Action

**Do not code the full system yet.**

First ask the user to answer the unresolved rule-definition questions in Section 62, especially:

- exact opening-range entry trigger,
- fill behavior,
- LOD timing,
- candle-low definition,
- ADR stop definition,
- MA exit timing,
- partial-sale sizing,
- core semantics,
- breakeven semantics,
- holding-period rules,
- extended-hours handling.

Once those are locked, implement **V1: Entry × Initial Stop** with one simple standardized exit.

That is the cleanest continuation point.
