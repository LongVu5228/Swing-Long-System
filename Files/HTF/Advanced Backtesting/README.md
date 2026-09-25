# HTF Manual Flag Recorder

Pine Script annotation tool for recording discretionary high-tight-flag judgments inside
TradingView, then exporting them as structured data.

**Use `htf_recorder_5slot.pine`.** 5 slots, 20 click prompts. Place your real flags, then
spam-click one candle through whatever's left — a slot whose start and end land on the same
bar is read as unused and exports as `enabled = 0` with null fields, so the parser skips it.
Emitted by `generate_recorder.py --slots N` if you ever want a different count. `v1` is the
hand-written proof of concept that validated the design — keep for reference, don't use.

**Why the chain can't end early:** the click prompts are TradingView UI, not Pine. They run
before the script executes, so no click pattern can stop them — every declared slot prompts,
every time. (× on the popup only re-asks the current prompt; confirmed 2026-09-17.) A chart
with more than 5 flags needs the 10-slot build; rare enough to handle when it happens.

**Validated 2026-09-17 on a real ARM export:** `ANNO_KEY`/`ANNO_VAL` columns come through
Chart Data Export, `display.data_window` plots are included, `YYYYMMDD` dates survive intact,
and the red-box logic correctly derived `LL_NO_RECLAIM` and discarded its R1 click.

## What it does

- You click points on the chart to mark `flag_start`, `setup_confirmed`, `final_flag_end`,
  and up to two versioned resistance levels per flag.
- It draws the box, a dashed marker at `setup_confirmed`, and the resistance lines.
- It publishes every annotation value as numbers that "Export chart data" writes to CSV.
- A summary table renders your existing `Flag Days` text convention (`8/29-9/6, 3/4-4/15`)
  so you can read it straight off the chart even before the export path is working.

It does **not** detect flags. Human judgment defines the setup; this only records it.

## Install

1. TradingView → Pine Editor → paste `htf_manual_flag_recorder_v1.pine` → Save → Add to chart.
2. On add, TradingView walks you through click-prompts for each interactive input.
3. Set "Chart review status" and enable the flag slots you need in the settings dialog.

## Per-ticker workflow

1. Type the symbol → Enter
2. `/` → `HTF` → Enter. 4 clicks per flag, then spam one candle through the rest.
4. Double-click the indicator name → set review status, flip any red slots to `LOWER_LOW`
5. Right-click chart → Export chart data → pick the recorder
6. **Remove the indicator before switching tickers.** Inputs persist across symbol
   switches; if you forget, the next chart's export carries this ticker's flags under the
   wrong filename. The ingestion script will sanity-check R1 against the chart's own prices
   as a backstop, but the habit is the real fix.

The ticker comes from the export filename (`BATS_ARM, 1D.csv`) — nothing to type.

## Export format

Rather than one plot per field (which would blow past Pine's 64-plot cap at 10 slots), the
script emits a **key/value stream** across the final bars of the chart. Each bar carries one
`(ANNO_KEY, ANNO_VAL)` pair; rows past the end of the record are blank.

The parser reads every row with a non-null `ANNO_KEY` and rebuilds a dict. Order doesn't
matter. Adding slots costs bars, not plots.

### Field IDs

Global:

| Key | Meaning | Encoding |
|---:|---|---|
| 1 | Schema version | integer, currently `1` |
| 2 | Chart review status | `0` NOT_REVIEWED · `1` REVIEWED_FLAGS_FOUND · `2` REVIEWED_NO_FLAG |

Per flag — key is `flag_number * 100 + field`:

| Field | Meaning | Encoding |
|---:|---|---|
| 1 | Enabled | `0` / `1` |
| 2 | Setup type | `1` HL_FLAG · `2` LL_NO_RECLAIM · `3` LL_RECLAIM (null if slot unused) |
| 3 | `flag_start` | `YYYYMMDD` |
| 4 | `setup_confirmed` | `YYYYMMDD` — for HL: higher-low confirmed; for LL: lower-low confirmed |
| 5 | `final_flag_end` | `YYYYMMDD` — for HL: box right edge; for LL: reclaim-end date, equal to field 4 when no reclaim |
| 6 | R1 effective date | `YYYYMMDD`, null if no R1. Never set for LL_NO_RECLAIM. |
| 7 | R1 **source bar** date | `YYYYMMDD`. **The price is that bar's high** — the parser reads it from the `high` column of this same CSV. Null if no R1. |
| 8 | R2 effective date | `YYYYMMDD`, null if no R2 |
| 9 | R2 **source bar** date | `YYYYMMDD`, resolved the same way. Null if no R2. |

Schema version 2 (2026-09-22) changed fields 7 and 9 from a price to a source-bar date. You
click the candle whose high *is* the level rather than placing the price by eye — exact
level, no pixel noise, and the record says which bar set it. The script can't export the
derived price itself: the record is written across the final bars, so a source bar inside
that window wouldn't have been scanned yet when its slot gets written.

So Flag 1's `setup_confirmed` is key `104`; Flag 2's R2 price is key `209`.

### The two setup types share the same four clicks

| Click | HL_FLAG (green) | LOWER_LOW (red) |
|---|---|---|
| 1 | flag start | flag start |
| 2 | higher-low confirmed | lower-low confirmed |
| 3 | final flag end | reclaim-end date — the bar where the recovery finishes near recent highs. **Click the same bar as #2 to mean "no reclaim, it just failed."** |
| 4 | R1 price | R1 price — only kept when there was a reclaim; discarded otherwise |

The type is set per slot via the "Setup type" dropdown in the settings dialog, after clicking.
The script derives `LL_NO_RECLAIM` vs `LL_RECLAIM` from whether click 3 landed on the same
bar as click 2 — you never label that distinction by hand. The corner table shows `HL`,
`LL fail`, or `LL reclaim` per slot so you can confirm it read your clicks the way you meant.

Dates are `YYYYMMDD` integers rather than Unix milliseconds — 13-digit epoch values can come
back from TradingView's CSV formatter in scientific notation, silently losing the day.

### Why `REVIEWED_NO_FLAG` matters

Key `2` is what lets this export replace the manual `is_valid_flag` column in
`../htf_1m_flag_review_v2_flagpole_bucketed_v2.csv` entirely. Without an explicit
reviewed-and-rejected state, an absent annotation is ambiguous between "haven't looked yet"
and "looked, nothing there" — and the scanner's precision can never be computed, because
there are no recorded negatives.

## Known gaps

- **2 resistance versions per flag.** The stream encoding makes adding a third trivial.
- **No join key back to the candidate list.** The scanner rows key on
  (`ticker`, `first_qualifying_date`); annotations will have to be matched by ticker plus
  date-range overlap. Ambiguous when flags on one ticker sit close together.
- **No parser yet.** Next thing to build: watch Downloads, parse each export into the
  master annotation table, regenerate the playback Pine file.

## Scanner Days overlay

`generate_scanner_days.py` emits `htf_scanner_days_*.pine` — four scripts that together
hold every `status = OK` streak from the review CSV (10,179 ranges, 3,206 tickers). Each
shades the bars from `first_qualifying_date` through `last_qualifying_date` in purple, chillax-
style, for whichever ticker is on the chart. **Add all four and leave them on**; only the one
holding the current ticker draws. Shading spans the whole streak, including any gaps where the
ticker briefly dropped off the top-16, since the 25-day tolerance merged those.

Split four ways because Pine caps source size; the generator keeps each under 40 KB. Rerun it
whenever the review CSV is rebuilt and re-paste the four scripts.

## Playback

`htf_flag_playback_POC.pine` demonstrates the read-only half: a script with annotations
hardcoded as data that draws the right boxes on whichever ticker is open, with no inputs and
no prompts. The real version is generated from the master annotation table by the ingestion
script. Add it once, leave it on; it also doubles as a "did I already review this?" signal.
