# HTF Manual Annotation Framework — Full Discussion Context

## Purpose of this document

This document captures the **full reasoning framework and back-and-forth discussion** that led to the current HTF annotation design.

It is intentionally broader than a build spec.

Claude Code should read this to understand:
- what the user was originally trying to do manually
- why that workflow became too slow
- what Qullamaggie's actual setup sequence implies
- how the meaning of the green box changed during the discussion
- what the user means by a setup being "confirmed"
- why resistance must be point-in-time and versioned
- how multiple flags on the same ticker should work
- why the user wants to keep TradingView as the visual source of truth
- what the red-box / shakeout phenomenon is
- how later entry backtests should relate to these annotations
- what questions were asked and how the user answered them

This is not just implementation instructions. It is the research logic behind the implementation.

---

# 1. Original problem the user was facing

The user is manually reviewing historical HTF candidates in TradingView.

The manual process looked roughly like this:

1. Open a historical ticker/chart.
2. Visually identify a Qullamaggie-style flag / higher-low region.
3. Draw a box over the candles that visually represent the flagging structure.
4. Manually type the date range into an Excel column such as:
   - `8/29-9/6`
   - or multiple ranges like:
   - `1/4-2/5, 3/4-4/15`
5. Repeat this for many historical candidates.

The problem was that this was taking far too long.

The main friction was not identifying the setup itself.

The main friction was:
- drawing the box
- reading the exact dates
- switching to the spreadsheet
- typing those dates
- then repeating the same process thousands of times

The user wanted a way to speed up the recording of the manually drawn setup regions.

---

# 2. Important correction: the user was already storing date ranges, not every candle

At first, there was a misunderstanding.

The user was **not** manually typing every trading day inside a box.

Instead:

`8/29-9/6`

means:

> the higher-low flag structure existed from August 29 through September 6

And:

`1/4-2/5, 3/4-4/15`

means:

> one flag existed from January 4 through February 5, and a second distinct flag existed from March 4 through April 15

So the existing Excel `Flag Days` field is already a compact interval representation.

The bottleneck is still real because the user must manually read and type the interval endpoints.

---

# 3. Reinterpretation of Qullamaggie's setup

A major conceptual correction occurred during the discussion.

The initial user framing was approximately:

> If the stock is making higher lows, perhaps any day inside that region could be considered an entry day.

Then the discussion revisited Qullamaggie's actual setup logic.

The better interpretation is:

**big prior move -> pullback/sideways -> tightening -> higher lows / surfing behavior -> clear resistance / line of least resistance -> breakout / range break**

The higher lows themselves are not the entry.

They are the **setup structure**.

The actual trade opportunity only begins once:
- the setup has become mature enough to recognize
- a clear resistance level / line of least resistance can be defined
- the stock later starts breaking or approaching that level

This changed the role of the green box.

---

# 4. New meaning of the green box

The green box should now mean:

> "This is the region where a legitimate higher-low / tightening flag structure formed."

It should **not** mean:

> "Every day in this box is an entry day."

This is a crucial distinction.

The box is evidence that the prerequisite setup exists.

Only after enough structure has formed should the system become eligible for entry testing.

That means the backtest architecture should separate:

## Setup identification
Human visual judgment:
- flag exists
- higher lows exist
- structure is mature enough
- resistance can be defined

## Entry testing
Machine/backtest:
- resistance break
- 1-minute ORH
- 5-minute ORH
- 30-minute ORH
- 60-minute ORH
- prior-day high
- first green daily close
- flag-region high
- combinations of the above

The user explicitly wants to test these later rather than assume one entry is correct now.

---

# 5. "Line of least resistance" / discretionary resistance

The user likes the conceptual framing of:
- Livermore-style line of least resistance
- Darvas-style box breakout logic

After a valid higher-low box has formed, the user wants to define a discretionary horizontal resistance level above the flag.

This resistance is the price level where:

> if the stock later starts moving toward or through that level, the setup becomes actionable for entry-rule testing

The user has **not** yet proven that resistance is always equal to:

> highest high of the completed green-box region

That may turn out to be true often.

But for now, resistance remains discretionary.

This is important because the research should not prematurely force a mechanical resistance definition before testing it.

---

# 6. The most important look-ahead issue

A critical backtesting problem was identified.

Suppose the final visual box spans:

`Aug 29 -> Sep 12`

If the user only realizes on Sep 6 that enough higher-low structure has formed to call it a valid setup, then it would be invalid to let the backtester consider entries on Aug 30 or Sep 1 merely because those dates later turned out to be inside the final hindsight-drawn box.

The final box contains future information.

Therefore the backtest needs a separate point-in-time field.

---

# 7. The `setup_confirmed` concept

The user agreed to this definition:

## `flag_start`
Where the higher-low / flag structure visually began developing.

This is descriptive.

It can be identified with hindsight.

It does not make the setup actionable.

## `setup_confirmed`
The **first date where enough of the box has formed that the user's trained eye is satisfied that it is a legitimate higher-low flag**.

This is the key point-in-time timestamp.

The user explicitly clarified:

> "once enough of the box has formed that my eye is satisfied it's a legit higher low flag"

At this point:
- the setup is now considered valid
- a line of least resistance can be defined
- future entry logic can begin to be tested

The backtester must not use entry triggers before this date.

## `final_flag_end`
The eventual right edge of the box after the chart continues to develop.

This may extend well past `setup_confirmed`.

---

# 8. Important example: box can keep extending after confirmation

The discussion used this example:

- Aug 29 -> Sep 6:
  enough higher lows have formed
- On Sep 6:
  the user would say:
  > "this is now a real setup; tomorrow I would consider buying if it starts breaking resistance"
- The stock does not break out
- It continues making higher lows through Sep 12
- The user extends the box to Sep 12

The user explicitly agreed:

> Sep 6 should remain the `setup_confirmed` date even though the final box later extends to Sep 12.

Therefore:

- `flag_start = Aug 29`
- `setup_confirmed = Sep 6`
- `final_flag_end = Sep 12`

This point is non-negotiable because it is what prevents look-ahead leakage.

---

# 9. Box lifecycle as the user experiences it

The practical chart process is now understood as:

## Developing
The stock pulls back.

The user is watching.

No valid setup yet.

It may:
- continue lower
- make lower lows
- become messy
- or begin forming higher lows

## Confirmed
Enough structure has formed that the user says:

> "This is a legitimate higher-low flag."

At this moment:
- setup is considered valid
- `setup_confirmed` is frozen
- resistance can be drawn
- the stock can go on a breakout watchlist

## Active
The stock keeps flagging.

The user may:
- extend the right edge of the box
- update the resistance level
- continue watching

`setup_confirmed` does not move.

## Resolved
The setup eventually:
- breaks resistance
- fails
- makes a meaningful lower low
- or becomes irrelevant / stale

---

# 10. Multiple flags per ticker

A single ticker can have multiple separate valid flag occurrences.

The user said:
- some tickers have around 4 boxes over the entire chart
- max observed is around 10

Example logic:

1. Flag #1 forms
2. It fails or stops behaving properly
3. One week later a new higher-low structure develops
4. Flag #2 is created

These are separate setup occurrences.

Do not overwrite the first setup with the second.

The annotation system should support at least 10 flags per ticker.

---

# 11. What closes a box

The user explained that the box may continue being extended while the stock remains in a valid higher-low / flagging structure.

The box may stop when something like a lower low forms and the user no longer believes the same structure is intact.

The user may then:
- close that box
- stop watching it
- move it to backlog
- or later create a separate new flag if a fresh structure develops

The final box end is therefore partly descriptive of how the setup ultimately evolved.

It should not retroactively alter when the setup first became valid.

---

# 12. Red boxes: lower-low / shakeout / reclaim behavior

The user noticed another recurring pattern that does **not** fit the clean higher-low green-box structure.

Sometimes the chart:
- pulls back
- makes a lower low
- looks like it is failing
- then produces a large green candle / reclaim
- acts as if weak holders were shaken out
- then begins moving higher again

The user has been marking these as red boxes.

The original plan was:
- finish all green boxes first
- later revisit and analyze the red boxes

However, once annotation becomes fast, it is better to preserve them during the same review session.

Suggested setup type:

`SHAKEOUT_RECLAIM`

This should remain separate from:

`HL_FLAG`

Do not merge them into one backtest unless later evidence supports doing so.

The human eye still determines when one of these structures exists.

---

# 13. Why the old HH/LH/HL pivot algorithm should not define setups

The user does not trust the previously implemented pivot algorithm enough to define the actual flag regions.

The user's view is:

> human visual pattern recognition is more accurate for this purpose

The old pivot logic can still be useful for:
- generating historical candidates
- giving rough structural hints
- producing scanner populations

But it should **not** be authoritative for:
- flag start
- setup confirmation
- final flag end
- resistance

The human eye remains the classifier.

This is deliberate.

The project is specifically trying to preserve discretionary chart recognition while making the recording/backtest process systematic.

---

# 14. Resistance can change over time

A very important clarification was made.

The user does **not** want a single resistance value per flag.

As the chart develops, the resistance may move.

Example:

- Setup confirmed Sep 6
- User initially draws resistance at $50
- Price does not touch $50
- Flag keeps developing
- User later decides the cleaner resistance is $53 on Sep 12

The user said it is fine to update/move resistance as the chart develops.

Therefore resistance must be **versioned point-in-time**.

---

# 15. Resistance versioning logic

Example:

## Resistance #1
- effective date: Sep 6
- price: $50

## Resistance #2
- effective date: Sep 12
- price: $53

Backtest interpretation:

- Sep 6 through Sep 11:
  active resistance is $50
- Sep 12 onward:
  active resistance is $53

The later $53 level must never be used before Sep 12.

Otherwise the backtest would leak hindsight information.

---

# 16. What happens if earlier resistance gets touched

The user clarified another subtle case.

Suppose:
- Resistance #1 is drawn
- price later touches or trades through it intraday

That counts as Resistance #1 being touched.

Even if:
- the final backtested 5-minute ORH rule would not have filled
- or another entry rule would not have triggered

That is okay.

The resistance event and trade entry are separate concepts.

The user explicitly agreed:

> merely trading through/touching the line intraday counts as resistance being triggered/touched

But:

> trade triggered depends on whichever entry rule is being tested

Therefore:

**Resistance touch = market fact**

**Trade entry = strategy-rule outcome**

Do not conflate them.

---

# 17. Why this separation matters

Later the backtest may compare:

- resistance-touch + 1m ORH
- resistance-touch + 5m ORH
- resistance-touch + 30m ORH
- prior-day high
- direct resistance break
- first green close
- other trigger logic

A resistance touch can occur without a later entry rule filling.

That is not an error.

It is exactly what the backtest is meant to study.

---

# 18. TradingView is the visual source of truth

The user strongly prefers TradingView for actual pattern judgment.

The user does not fully trust a custom local chart viewer for this step because:
- TradingView is familiar
- the visual presentation is part of the trained discretionary eye
- the user wants the backtest labels to come from the same charting environment they actually use

Therefore the best design should **not** replace TradingView as the visual review interface.

A local companion program may be acceptable for clicking/recording if necessary, but the setup should still be judged in TradingView.

---

# 19. Companion app idea

A companion-app concept was discussed.

The idea:

- user judges the setup in TradingView
- a local chart-review helper is synchronized to the same ticker/date range
- user clicks the corresponding candles in the helper
- app records:
  - start
  - confirmed
  - end
  - resistance
- then saves and moves to the next ticker

The user said this could be acceptable if:
- TradingView remains open for the actual visual judgment

However, the user still prefers a solution that stays entirely inside TradingView if possible.

---

# 20. Silent Pine Script / TradingView-native annotation idea

The preferred workaround became a custom Pine Script indicator.

The purpose of Pine is **not** to detect the flag.

The purpose is to let the user make manual, structured, data-backed annotations inside TradingView.

Conceptually:

**HTF Manual Flag Recorder**

For each flag:
- start date
- setup-confirmed date
- final end date
- setup type
- resistance #1 effective date
- resistance #1 price
- resistance #2 effective date
- resistance #2 price
- etc.

The Pine script can visually draw:
- the box
- confirmation marker
- resistance lines

And also expose those values numerically for export.

---

# 21. Why ordinary TradingView rectangles are not sufficient

The user's dream solution was:

> draw rectangles normally in TradingView and then export all rectangle start/end dates

Unfortunately, normal UI drawings are not directly available to Pine as structured data for export.

That is why the Pine script needs to own the interactive date/price values itself.

It effectively creates a "data-backed rectangle."

---

# 22. Interactive Pine inputs idea

Useful Pine concepts discussed:

- `input.time()`
- `input.price()`
- interactive placement
- draggable chart values
- visual boxes/lines
- plots for export

The ideal user experience is:

1. Decide visually where the flag begins
2. Set/click `flag_start`
3. Set/click `setup_confirmed`
4. Set/click `final_flag_end`
5. Set/click discretionary resistance
6. Let Pine draw the box/line
7. Export the annotation later

This avoids manually reading and typing date strings.

---

# 23. One export per ticker, not one export per box

A concern arose:

If there are about 2,000 tickers, would this require 2,000 TradingView CSV exports?

Yes, potentially one export per ticker/chart.

But importantly:

If ACAD has:
- 4 green boxes
- multiple resistance levels

all of that should be captured in **one ACAD export**.

The workflow is not:
- one export per flag

It is:
- one export per ticker/chart

---

# 24. 2,000 exports are annoying but not computationally problematic

The real problem with 2,000 exports is user friction.

It is not storage or processing.

A later automation can reduce this burden:

1. User finishes a ticker.
2. Presses one shortcut.
3. Browser/AutoHotkey automation triggers Chart Data Export.
4. A Python folder watcher detects the new CSV.
5. It extracts only annotation fields.
6. Appends them into a master dataset.
7. Archives or deletes the raw export.
8. Confirms save.
9. User moves to next ticker.

This later automation is separate from Pine V1.

---

# 25. Why alerts/webhooks are not the first choice

A direct TradingView-to-local bridge would be ideal, but Pine is not designed to arbitrarily write local files.

Alerts/webhooks are also not a perfect fit for historical annotation because:
- alerts are fundamentally realtime-oriented
- changing script inputs does not automatically provide a clean historical annotation synchronization mechanism

Therefore the practical V1 path is:

**Pine annotations -> Chart Data Export -> local parser**

---

# 26. Subscription concern

The user asked whether this workflow requires TradingView Premium.

The conclusion reached was:

Premium is not necessary for the planned annotation workflow.

The important capability is chart-data export and Pine scripting support.

The user should not buy the highest-cost Premium plan merely for this project.

The workflow was framed as:

**TradingView -> human visual labeling**

then

**local data + Polygon/Massive -> quantitative backtesting**

This keeps TradingView focused on the part the user trusts it for.

---

# 27. Current research architecture

The complete conceptual architecture is now:

## Stage A — historical candidate generation
Existing scanner produces historical candidates.

Machine is optimized for recall.

It does not decide whether a setup is genuinely valid.

## Stage B — manual human classification in TradingView
User visually inspects each chart.

Human decides:
- whether a flag exists
- where it begins
- when it becomes legitimately recognizable
- how long it continues
- what resistance levels matter
- whether it is a normal HL flag or shakeout/reclaim type

## Stage C — structured annotation
Pine converts those visual judgments into structured point-in-time data.

## Stage D — quantitative entry testing
Later backtester asks:

Given that the setup was confirmed on this date and resistance at that time was this price:

Which entry rule worked best?

Possible tests:
- 1m ORH
- 5m ORH
- 30m ORH
- 60m ORH
- prior-day high
- direct resistance cross
- first green daily close
- highest flag high
- combinations

## Stage E — trade management testing
Stops/exits/partials/trails are tested later.

---

# 28. Questions asked during the discussion and user answers

## Question 1
When the user draws a green box, does it mean:

A. every day in the box is a potential entry day

or

B. the entire region is simply the higher-low setup structure?

### User's evolved answer
Originally the user would have said A.

After revisiting Qullamaggie's actual method, the user agreed B is better.

The green box should mean the setup structure exists.

Entry only becomes relevant after:
- enough structure has formed
- a resistance / line of least resistance exists

---

## Question 2
Can one HTF have multiple separate boxes?

### User answer
Yes.

A stock can:
- flag
- fail
- then form another higher-low flag one week later

That should become a separate occurrence.

Some tickers have around 4.
Max observed is around 10.

---

## Question 3
How is the beginning of the box chosen?

### User answer
Entirely discretionary based on the human eye.

The user watches the pullback and asks whether:
- it begins forming higher lows
- it continues making lower lows
- it shows a shakeout/reclaim behavior

The start is not currently based on an objective formula.

---

## Question 4
Would a local chart-review tool be acceptable?

### User answer
Maybe.

The user strongly prefers TradingView for actual visual judgment.

A local helper could be acceptable if:
- TradingView remains open
- the helper is only used to click/record dates after visually identifying them in TradingView

---

## Question 5
Suppose the box is visually Aug 29 -> Sep 12, but enough structure already exists on Sep 6.

Should Sep 6 remain the setup-confirmed date?

### User answer
Yes.

This was explicitly confirmed.

---

## Question 6
When setup is confirmed, should resistance be based only on information available at that time?

### User answer
Resistance can later be updated as the chart develops.

The user will record the resistance that existed at each stage.

If earlier resistance gets touched, preserve it as Resistance #1 and later create Resistance #2, #3, etc.

This is why resistance must be versioned.

---

## Question 7
If price merely touches/trades through resistance intraday, does that count as resistance being hit?

### User answer
Yes.

Even if a 5m ORH entry later would not fill.

Resistance touch and trade trigger are separate.

---

## Question 8
When does the user know the setup exists?

### User answer
The user clarified:

> "once enough of the box has formed that my eye is satisfied it's a legit higher low flag"

This is the exact meaning of `setup_confirmed`.

---

# 29. Core principles that Claude Code must not accidentally violate

1. Human judgment defines the flag.
2. Pine records the judgment; it does not replace it.
3. `setup_confirmed` is the first point-in-time date the setup was truly recognizable.
4. `final_flag_end` can extend later without changing `setup_confirmed`.
5. No backtest entry before `setup_confirmed`.
6. Resistance is discretionary.
7. Resistance can change over time.
8. Resistance versions must preserve their effective dates.
9. Later resistance must never be used earlier.
10. Resistance touch is not the same as trade entry.
11. Multiple flags per ticker are valid.
12. Green HL flags and red shakeout/reclaim structures should be separately labeled.
13. TradingView remains the visual source of truth.
14. The current goal is speeding up annotation, not automating pattern recognition.
15. The eventual backtest should compare entry methods after the setup is confirmed.

---

# 30. Preferred terminology

Use these terms consistently:

- `flag_start`
- `setup_confirmed`
- `final_flag_end`
- `setup_type`
- `HL_FLAG`
- `SHAKEOUT_RECLAIM`
- `resistance_id`
- `resistance_effective_date`
- `resistance_price`
- `resistance_touch`
- `trade_trigger`

Avoid calling every candle in the box an "entry day."

The box is the setup region.

---

# 31. Final conceptual model

The current best model is:

> A stock has already made a strong prior move.  
> It pulls back and begins organizing.  
> The human watches for a legitimate higher-low / tightening structure.  
> Once enough structure has formed, the setup becomes confirmed.  
> At that moment, a discretionary line of least resistance is defined.  
> The chart may continue flagging, the box may extend, and resistance may be updated.  
> Each resistance version is stored with its own effective date.  
> If price touches a resistance level, that is recorded as a market event.  
> A separate later backtest decides whether any particular entry rule actually triggered.  
> The goal is to discover which entry logic best exploits a manually identified HTF setup without introducing look-ahead bias.

This framework should guide every implementation decision.
