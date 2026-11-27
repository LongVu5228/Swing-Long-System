# HTF session notes: 2026-11-25

Everything built and decided this session. The strategy evidence lives in `HTF_Backtest_Findings_CURRENT.md` (sections 40–41);
the rules are in `HTF_Strategy_FINAL.md`.

## 1. Strategy results this session

- **Lock re-check (findings section 40).** On the final filters, the plain R1 buy-stop and 1m entries made +0.42R per trade
  versus +0.38R for the 30m hybrid. That gap is not significant, and 30m had the lowest drawdown, so 30m stays. The core
  split (0–70%) doesn't change expectancy: core 0 is the smoothest, holding with no partials is the worst. Breakeven stays
  after the first partial (no further test, at the user's call).
- **Held-out test FAILED (findings section 41).** 447 held-out flags (DKS..ETSY) were ingested. On 180 FINAL trades the
  result was −0.40R per trade (90% CI −0.66 to −0.13), against +0.38R on dev. The gap is not explained by the charting
  tool, the label source, ticker concentration, entry geometry or luck. The trades simply didn't run. Likely causes are
  hindsight in the dev annotations, or looser new annotations (4.8 flags per row vs 3.7). **Don't trade at size.** Next:
  a second held-out batch annotated live-style in replay mode.
- **Market cap × green/red.** All cap buckets are positive for green flags. The $2–10B bucket is unstable (+0.93R in
  2005–15, −0.02R in 2016–26), so trade all caps.
- **SPY × green/red.** Green flags with SPY below its 200-day lose −0.41R per trade (DD −145R). Red flags are about +0.08R
  in any regime. Both filters are justified.
- **Triple-list flags (on 1M+3M+6M) did NOT do better.** Dev: +0.23R versus +0.52R for the rest. The best result was
  flags on no list that month (+0.63R): graduates matter.
- **Expectancy.** "R:R calculators" express R in units of the average loss: 0.305 × 3.24 − 0.695 = +0.29, and
  0.29 × 1.30 = +0.38R of planned risk. That is about $33 per trade at $35k / 0.25%.

## 2. Data

- **All-stock daily store** (`htf_backtest/market_store.py`, built before the Massive free-tier downgrade). It holds
  `backtest_data/market_daily/<year>.parquet` for 2018-01-02 onward: about 12.7k stocks a day, 459 MB. Grouped daily costs
  1 call per session. Splits are checked by re-pulling (SNDK 1:8 test passed). Server start runs `update()`.
- **P123 live feed** (`Files/HTF/p123_daily.py`). The user bought P123; the key is in `Files/Buyable Gap Up/.env`. The
  script appends only the missing days to `raw_data_htf_v2/<year>.parquet` with the exact backtest formulas. The backfill
  of 09-22 → 11-24 cost 25 of 250 monthly credits; each day after costs about 1. Server start runs it. A local scan from
  the store matched P123 on only 85–98% of names, so P123 stays the source.
- **Held-out minute bars** were pulled, and `minute_bars.py` now skips delisted (^) rows. Pulling them had created empty
  folders that hid the real delisted bars; those folders were removed.
- **Before downgrading Massive:** do the EP delisted-survivorship redo, and check whether the EP VPS bot calls Massive.

## 3. Local screener (http://127.0.0.1:8765/screener)

Start it with `local_recorder/Start HTF Screener.bat`. It always restarts: it stops any server on port 8765, then runs the
P123 pull, then the bars update.

- **Views.** Today, Graduates (on that list within the last 63 sessions) and Backlog (older; delisted names dropped). A
  ticker never leaves the screener. A "→ Backlog" button sends a graduate away until it hits a scan again.
- **Tabs.** All (unique across the 9 lists), then 1M/3M/6M × Small/Mid/Large, All armed, and Recently drawn (any drawing
  made or edited in the last 30 days).
- **Grid.** 4×2 that can be switched. Today, All armed and Recently drawn scroll; All, Graduates and Backlog page with
  arrows. Charts show SMA10/20 and volume on 3M / 6M / 1Y / 5Y daily / 5Y weekly, with yyyy-mm-dd dates. Each chart
  zooms on its own; "Reset zoom (all)" resets them together.
- **Card header.** Left: ticker, then the ARMED/WATCH chip with a short pattern name (Big G / Perf / Big Perf / Green),
  then tags. Right: the 1M/3M/6M chips, market cap, ADR % and the 🏷 button.
- **Tags** (stored in `tags.json`): UT orange, DT light red, BG/SG light green, PF/BPF purple, N/A gray struck-through,
  plus custom tags. Arming auto-adds SG/BG/PF/BPF; red patterns add no tag. The tag filter is one "Tags ▾" dropdown
  (2026-11-27): checkboxes for Armed / Unarmed (status), every tag, and Untagged, plus "Must have all tags". Off means
  ANY checked entry matches; on means a ticker needs ALL of them. It shows a live count, and the grid redraws when the
  menu closes. Both choices are remembered (localStorage `filter` / `filterAll`).
- **Drawings** (`drawings.json`). Alt+T trendline, Alt+H horizontal line. Click a line to select it, Delete removes it,
  drag moves an end point or the whole line. Lines can end in the blank future area. They are synced across every chart
  of the ticker.
- **Arming.** Double-click a daily candle: its high becomes R1, then a pattern popup arms it (red patterns are watch
  only). You can also arm from the full chart (`/chart`). Armed items don't expire; disarm them yourself. Trade state is a
  daily-bar estimate until DAS is wired in.
- **Right panel** (redesigned 2026-11-26, see section 6). Three collapsible sections (Armed R1, Watch only, History),
  all using the same 2-column square cards.
- **Live vs replay.** The newest P123 day is labelled LIVE and uses `armed_live.json`. Older dates are replay practice
  and use `armed_replay.json`. Tags and drawings are global.

## 4. Decisions

- Entries go through the **DAS bot watching live quotes** for every armed ticker. At 10:00 it computes
  trigger = max(R1, 30m high) + 1¢, sends the buy-stop when price is within ~1%, and skips everything when SPY's prior
  close is below its 200-day. TradingView watchlist alerts and webhooks were rejected: per-ticker R1 would need manual
  pasting, and the VPS would need a public endpoint. TradingView alerts are optional phone notifications only.
- P123 is the scan source; the local Massive scan is not.
- Step 14 (portfolio caps) was dropped. The user is fine with the open-position peaks.

## 5. Next steps

1. Build the DAS bot: `htf_long_daily.py`, cloned from EP's `ep_long_daily.py`, on the same VPS. Get the armed list to
   the VPS (SSH), then dry-run or paper first.
2. Run a second held-out batch, live-style, in the screener's replay mode, before trading at size.
3. Do the EP survivorship redo while Massive is still on the paid plan.
4. Optional: put the replay date picker behind a "Practice" toggle.

## 6. Screener updates: 2026-11-26

All of these were checked in headless Edge on a spare-port copy. The user's armed, tags and drawings files were not touched.

### Bug fixes
- **Dragging a trendline end to the right panned the chart.** The chart is now frozen while you drag; the line moves in
  place, and the visible range is kept. Charts open with blank space past the last candle, so lines can end in the future.
- **The pager jumped left when a tag filter was on.** The toolbar no longer wraps; the hint text shortens with "…" instead.
- **Disarming from a grid chip seemed not to work.** It did work, but the page took about 6 s to show it. Disarm now
  updates the page at once (the server catches up in the background), and the server caches lists and bars in memory,
  so the armed view takes 0.13 s instead of about 6 s.
- **Tag menu:** each toggle saves right away, but the grid only redraws when the 🏷 menu closes.

### Right panel
- **Sections.** Armed R1, Watch only (red flags) and History (last 30 days) are collapsible `<details>` blocks. Armed R1
  remembers whether it is open (localStorage `armedOpen`).
- **Cards.** A 2-column grid of square cards.
  - The header is filled with the setup color:
    - Big Green: dark green.
    - Green: light green.
    - Big Perfect: dark purple.
    - Perfect: light purple.
    - Big Red: dark red.
    - Red: light red.
  - The header holds the ticker, ↗ (full chart) and ✕ (disarm, or remove from watch; none on History), plus the short
    pattern name and "R1 Nd" (trading days since the R1 candle).
  - Right of that sits the % distance from the last close to the trigger (R1 + 1¢). Negative means the price is above the
    trigger. History shows the estimated result ("+1.2R mm-dd") or "disarmed mm-dd" instead.
  - Below the header is a square mini chart with the R1 line and synced drawings.
- **Sorting.** Armed and Watch are sorted by |distance to R1|, closest first.
- **Timeframe.** 1M / 2M / 3M buttons plus Reset zoom sit in the Armed R1 title bar. The choice is remembered
  (localStorage `ptf`) and applies to every panel chart. The default is 1M. These ranges are panel-only (`panelOnly` in
  `TF`) and are not on the grid toolbar. The toolbar's "Reset zoom (all)" now resets only the grid.
- **History contents.** Flags disarmed in the last 30 days, plus armed flags whose estimated (daily-bar) trade closed in
  that window. Watch flags you remove don't go to History.

### Files changed
- `local_recorder/screener.html`: `sqCard(a, kind)`, `SQ_PAT`, `histNote`, `disarmNow`, `flushTags`, the panel
  timeframe (`S.ptf`), the sorting.
- `local_recorder/scr_common.js`: the 1M/2M panel ranges, the drag freeze, `updateDrawing`, the right-side blank space.
- `local_recorder/screener_data.py`: the `_BCACHE` / `_LCACHE` caches, `r1_days`. Server code changed, so restart
  with `Start HTF Screener.bat`.

### Still open (unchanged)
1. Build the DAS bot (`htf_long_daily.py`, cloned from EP's `ep_long_daily.py`) on the VPS; dry run first.
2. Run a second held-out batch, live-style in replay mode, before trading at size. The first held-out test FAILED:
   −0.40R per trade.
3. Do the EP survivorship redo before the Massive downgrade.
4. Optional: put the replay date picker behind a "Practice" toggle.
