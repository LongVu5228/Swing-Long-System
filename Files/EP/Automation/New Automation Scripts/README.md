# EP Swing-Long Engine

Automates DAS Trader Pro execution for the **long** side of the EP (Episodic
Pivot) swing strategy -- "Chosen One #4" from the backtest project:

```
E60M__S0.50ADR__TCLOSE_BELOW_20MA__EQUAL_DEPLETION__LSTART20__C50
```

Source of the strategy rules: `Files/EP/Backtesting/Swing_Long_EP_Backtest_Session_Dump_2026-09-01.md`
(section 10) and the `ep_backtest/` package (`entry.py`, `initial_stop.py`,
`trailing_stops.py`, `multi_partial_taking.py`, `config.py`).

## Which script to run

**`ep_long_daily.py` is the one you actually run.** `ep_long_engine.py` is
kept as an unused backup/reference -- same strategy shape, but it's a
continuously-running process rather than a daily launch, and its sizing/stop
were anchored to the actual fill price instead of the planned trigger. Don't
launch both against the same DAS account.

`ep_long_daily.py`'s two real differences from the backup, both ported from
the proven short-side system (`Old Swing Short Scripts/Algo/algo/alextweak.py`):

1. **Daily lifecycle, not continuous.** Task Scheduler launches it fresh each
   morning (~9:20 ET); it does one Entry Sheet read at 09:29:30, confirms
   each candidate's gap % live at 09:30:00, manages the day, and exits
   cleanly around 16:15 ET -- Task Scheduler relaunches it the next morning.
   A held position's stop/ladder orders rest at the broker (`TIF=GTC+`)
   independent of whether this process is running, so multi-day holds
   survive the daily on/off cycle fine; state still persists to disk and
   reconciles against live DAS positions/orders on every reconnect.
2. **Sizing/stop anchored to the planned trigger price, not the fill.**
   `fixed_stop_px` is computed once when the buy-stop is armed (off the OR
   breakout trigger) and never recalculated from the actual fill. If the
   entry fills worse (slippage) or better than planned, a size-reconciliation
   loop -- ported from `alextweak.py`'s `run_size_reconciliation` /
   `adjust_order_pending` single-flight gate -- trims or adds shares via
   plain market orders until `(avg_fill - fixed_stop_px) * shares` lands back
   on the original target dollar risk. Only one such adjust order is ever in
   flight per ticker at a time (the fix for a past "two orders at once"
   failure). Verified against a worked $5.10-planned/$5.20-filled example --
   see the scratchpad test if you want to rerun it.

Both scripts are meaningfully simpler than the short-side system -- no
shorting, no locates, no 4 AM premarket stop coverage.

## Live-test findings (2026-09-10)

Real DAS connection testing on this account surfaced two things worth
knowing, both already fixed in `ep_long_daily.py`:

- **Route confirmed: `SMAT`** for all five route constants (see the
  order-routes section under Setup for the full story -- `PRO20`, carried
  over from the short side, was rejected outright on this account).
- **Ladder targets are resting LIMIT sell orders, not sell-stops.** An
  earlier design used sell-STOP orders for the ladder (place a stop above
  market, "trigger" once price gets there). Live-tested and confirmed wrong:
  a sell-stop's trigger condition is "price <= stop price," which is already
  true when the stop is placed *above* current market price -- so DAS treats
  it as instantly marketable and fires it immediately, not once price
  actually climbs there. Reverted to plain limit sells for the ladder, which
  is the correct mechanism for "sell only once price rises to X." The
  protective stop (`ROUTE_STOP`, below market) is unaffected -- that
  direction is exactly what a sell-stop is supposed to do.

## How it works

The Google Sheet has 4 tabs. You only ever touch the first one; the other
three are fully bot-managed views of the engine's own internal state.

**Sheet-write timing differs between the two scripts.** `ep_long_engine.py`
(the unused backup) writes Watch List/Positions on every relevant event plus
a 5-minute timer. **`ep_long_daily.py` (the one you run) batches ALL sheet
writes into a single pass at end of day** (`run_eod_updates`, called right
before the ~16:15 ET shutdown): Watch List and Positions get (re)synced once,
every History row opened or closed that session gets written, and every
Entry Sheet row processed that morning gets cleared -- all in one pass, not
as each event happens. This trades away intraday sheet visibility (the
sheet reflects yesterday's end-of-day state until tonight's pass) for far
fewer Sheets API calls, per explicit request. Nothing is lost in between --
entries/exits/ladder fills are tracked in `ep_long_daily.py`'s own state
file the whole time; the sheet is just a once-a-day snapshot of it, not the
source of truth.

1. The morning of an EP, you add a row to the **Entry Sheet** tab (ticker,
   gap %, ADR14 %, chart pattern, enabled, Yday Close) -- no date column
   needed, a row present here is always "today's" candidate. The engine
   reads it, subscribes to time & sales, confirms gap % live at 09:30:00,
   and tracks the high of the first 60 minutes (9:30-10:30 ET). Every row
   read that morning -- armed, skipped, or rejected -- is queued for
   clearing at EOD (see above), so nothing lingers to be wrongly re-armed
   tomorrow.
2. At 10:30:00 ET it computes the breakout trigger (OR high + $0.01), sizes
   the position off your account equity and the ADR-based stop distance, and
   places a **buy-stop** order good for up to 8 trading sessions (D0..D0+7).
   That order shows up on **Current Watch List** at tonight's EOD sync while
   it's still resting; if it never fills, it's canceled and you get a
   Discord alert immediately (that part isn't batched -- notifications are
   real-time regardless of when the sheet itself gets written).
3. On fill: `ep_long_daily.py` first reconciles size to the fixed,
   trigger-anchored stop (see "Which script to run" above), then places the
   stop-market order and 5 resting limit-sell ladder orders at +20/27.5/35/42.5/50%
   off the reconciled average fill, each for 10% of the final share count.
   The remaining 50% ("core") never gets a ladder order. The position (and
   its History row) become visible on the sheet at the next EOD sync.
4. The moment the first ladder rung fills, the stop is replaced to breakeven
   for whatever shares remain, permanently -- tracked immediately in state,
   reflected on the sheet at the next EOD sync.
5. Every trading day, a few minutes before the close, the engine checks
   whether today's close is below the 20-day SMA of closes. If so, it cancels
   the stop and any un-filled ladder rungs and sells everything remaining via
   an `AtClose` order. This is the only way the "core" 50% ever exits, absent
   a stop-out first. Either way, its **History** row gets its Exit
   Date/Reason/P&L/R filled in at EOD -- nothing is ever deleted from
   History, it's the permanent YTD record.
6. All of this is persisted to disk after every change (`ep_long_daily.py`
   uses `state/ep_long_daily_state.json`; the backup uses a separate
   `state/ep_long_state.json` so the two can never collide), and reconciled
   against DAS's own `GET POSITIONS`/`GET ORDERS` on every startup -- so a
   crash, a manual restart, or the weekend maintenance reboot
   (`WeekendWindowsMaintenance.ps1`) doesn't lose track of anything. If a
   restart finds a live position with no resting protective stop, the engine
   re-arms one immediately and sends a loud Discord alert (again: real-time,
   not batched -- only the routine sheet snapshot waits for EOD).

## Setup

1. **Copy `.env.example` to `.env`** in this same folder and fill in:
   - `DAS_USER` / `DAS_PASS` / `DAS_ACCT` -- this account's DAS login. Per
     your answer, this should be a **different account number** than the
     short-side system (separate risk allocation). If your broker/DAS setup
     requires a second DAS terminal instance for a second account, set
     `DAS_PORT` to that instance's configured CMD API port.
   - `DAS_ACCOUNT_RESERVE` -- dollars held back before computing risk (same
     idea as the short side's `ACCOUNT_RESERVE`; there's no sane default, set
     your own).
   - `RISK_PCT_PER_TRADE` -- fraction of (equity - reserve) risked per trade.
     Defaults to 0.05 (5%) if unset -- **decide this deliberately**, the
     backtest doesn't define a position-sizing rule on its own (it only
     measures R-multiples), this is a live-trading addition.
   - `DISCORD_WEBHOOK_URL` -- can reuse the short-side system's webhook, or
     use a separate one for a dedicated channel.
   - `SHEET_CREDENTIALS_FILE` -- Google service-account JSON filename
     (default `credentials.json`).
   - `GOOGLE_SHEET_ID` -- **preferred**: the ID from the sheet's URL
     (`.../spreadsheets/d/<THIS PART>/edit`). Robust against renames; set
     this and `GOOGLE_SHEET_NAME` is ignored. Leave blank to fall back to
     opening by name instead.
2. **Put your Google service-account credentials JSON** in this folder,
   named to match `SHEET_CREDENTIALS_FILE` (default `credentials.json`). This
   can be the **same** service account the short-side system uses (it only
   needs access to a new sheet you share with it), or a new one.
3. **Create the Google Sheet** with 4 tabs, exactly named as below (the bot
   looks tabs up by name, not position). See this folder's draft workbook
   for a populated example of all 4 -- ask for a fresh copy if you don't
   have it, or just build the 4 tabs directly from the layout below.

   **Tab 1 -- "Entry Sheet"** (the only one you edit):

   | Ticker | Gap % | ADR14 % | Chart Pattern | Enabled | Yday Close |
   |---|---|---|---|---|---|

   **`ep_long_daily.py` requires the "Yday Close" column** (add it to your
   existing sheet if it's not there yet -- `ep_long_engine.py`, the unused
   backup, doesn't need it). It's the actual dollar close, e.g. `3.29` --
   used to live-confirm each candidate's gap % at the 09:30:00 official open
   print, mirroring `alextweak.py`'s morning filter exactly. The sheet's own
   Gap % column stays purely informational, same as before.

   - No date column -- a row present here is always treated as **today's**
     candidate (add it the morning of the EP). The engine clears every row
     it processes (armed, skipped, or rejected) so nothing lingers into
     tomorrow as a false "today" candidate.
   - **Gap %** is informational only (flows through to History) -- not used
     in any calculation; **Yday Close** is what's actually checked live.
   - **ADR14 %**: as a percent, e.g. `5.2` means 5.2%. This is the one
     number the whole stop calculation depends on -- get it right
     (14-trading-day average high-low range as % of the pre-gap close; see
     `Scripts/build_benzinga_candidate_list.py` for the exact formula if you
     want to automate computing it instead of eyeballing it).
   - **Chart Pattern**: kept for record-keeping (flows into History) and as
     a safety net -- `DT`, `DT SW`, `DT U` are auto-excluded even if
     `Enabled=TRUE` (the single highest-leverage filter found in the whole
     backtest project, see session dump section 3), though in practice you
     shouldn't be entering DT-family tickers yourself.
   - **Enabled**: `TRUE`/`FALSE` (or `1`/`yes`). A `FALSE` row is left alone
     (not cleared) so you can flip it on later.
   - **Yday Close**: `ep_long_daily.py` only -- rejects the candidate outright
     (with a Discord alert) if missing/invalid, or if the live 9:30 gap %
     comes in under 5% (`MIN_GAP_PERCENT`) or the open is under $2
     (`MIN_PRICE`), both adjustable constants near the top of the script.

   **Tab 2 -- "Current Watch List"** (bot-writes; one row per unfilled
   resting buy-stop order): Ticker, Armed Date (D0), OR High, Trigger Price,
   Shares, Order Type (always "Buy Stop -> Market"), Route, Expires On,
   Days Left, Status.

   **Tab 3 -- "Current Positions"** (bot-writes; one row per open position,
   the detailed live dashboard): Ticker, Entry Date, Entry Price, Shares
   (Orig), Original Position Size ($), R Risk Amount ($), Shares Remaining,
   Shares Remaining %, Current Position Size ($), Core Shares (Riding
   Trail), Stop Price, Stop Status, Target +20/27.5/35/42.5/50%, Last Close,
   20D SMA, Dist. to Trail Exit %, Unrealized %.

   **Tab 4 -- "History"** (bot-writes; one permanent row per trade, for
   life): Entry Date, Ticker, Chart Pattern, Gap %, ADR14 %, Entry Price,
   Shares (Orig), R Risk Amount ($), Exit Date, Exit Reason, Realized P&L
   ($), Realized R. Written at entry, then updated in place at exit --
   Realized P&L/R are kept as real numbers (not decorated strings like the
   two dashboard tabs) specifically so you can sum/average/pivot them later.

4. **Order routes -- confirmed 2026-09-10.** All five (`ROUTE_ENTRY`,
   `ROUTE_STOP`, `ROUTE_ADJUST`, `ROUTE_LADDER`, `ROUTE_EXIT`) are set to
   `SMAT`, verified with a real `NEWORDER`/`CANCEL` round-trip on this
   account (1-share SPY buy-stop, 1% away, went Sending -> Accepted ->
   Canceled cleanly). The original carried-over guess, `PRO20`, was rejected
   outright: `Can't Find Route![RGEL]` -- route codes turned out to be
   scoped per-account on this broker, not broker-wide, so the short-side
   scripts' working routes didn't transfer over. Only the BUY direction was
   directly tested this way; SMAT is DAS's own smart-routing layer (not a
   specific ECN destination) and the short-side scripts already use it for
   BUY-to-cover orders, so it's a reasonable bet for the SELL side too
   (stop/ladder/exit/trim) -- but watch the first real stop/ladder placement
   closely to confirm. `test_das_live.py` and `test_das_routes.py` in this
   folder are the diagnostic scripts used to find this; keep them around for
   future route/connectivity troubleshooting (harmless -- `test_das_routes.py`
   is read-only, and `test_das_live.py` always cancels its own test order).

5. **Run it once by hand first**: `python ep_long_daily.py`. It runs a
   startup self-test against literal sample lines from the CMD API manual
   (order/trade/bar/position/account-info field positions) and refuses to
   start if any of those assumptions don't hold. Watch the console/log for
   the reconciliation output and the "Started" Discord message.

6. **Task Scheduler** (for `ep_long_daily.py` -- the one you actually run):
   - Trigger: **daily at ~09:20 ET**, weekdays. It idles until 09:29:30 for
     the Entry Sheet read, then handles the rest of the day, and exits
     cleanly around 16:15 ET -- so this single daily trigger is all you
     need (no "at startup" trigger required the way a continuous process
     would want, though adding one as a same-day crash-recovery net is
     harmless: `wait_for_das_port` makes it tolerant of firing before DAS
     has finished logging in, and the singleton lock prevents a duplicate
     if the scheduled instance is still alive).
   - Action: run `python.exe` with `ep_long_daily.py` as the argument and
     this folder as the working directory.
   - Its own singleton lock (`ep_long_daily.lock` in `%TEMP%`, separate from
     `ep_long_engine.py`'s) prevents two copies from running simultaneously.

## Known simplifications / things to watch (read before trusting this at size)

- **Same-day-close exit is an approximation, not exact.** The backtest
  assumes a fill at the literal closing print the instant a close violates
  the 20-day SMA. Live, the engine checks a few minutes early
  (`CLOSE_CHECK_TIME`, default 15:55 ET) using the last trade price as a
  stand-in for the close, then submits an `AtClose` order so the real fill
  happens at the actual close. Price can still move in those last few
  minutes; verify your broker/DAS's `AtClose` semantics and submission
  cutoff, and adjust `CLOSE_CHECK_TIME` if needed. If `AtClose` proves
  unreliable, switch `TRAIL_EXIT_TIF` to `"DAY+"` and it'll be an immediate
  market sell instead of waiting for the close print.
- **Order routes are unconfirmed guesses** (see setup step 4).
- **No holiday calendar dependency required, but recommended**: entry-watch
  expiry (`D0 + 7 trading sessions`) uses `pandas_market_calendars` (NYSE) if
  it's installed in this environment, for holiday-accurate session counting;
  otherwise it silently falls back to a Monday-Friday-only count, which
  could compute a slightly-wrong expiry date around a holiday.
- **One watch or position per ticker at a time.** If the same ticker
  produces a second EP event while a position or watch from a prior event is
  still open, the newer sheet row is silently ignored until the first one
  resolves. Fine for how this is used today; would need extending if that
  changes.
- **Risk sizing is a new addition, not from the backtest.** The backtest
  only measures R-multiples; `RISK_PCT_PER_TRADE`/`DAS_ACCOUNT_RESERVE` are
  a live-trading necessity layered on top, same pattern as the short-side
  system. Decide these numbers deliberately.
- **Credentials are clean** (env vars / `.env`, gitignored) unlike the
  short-side scripts, which hardcode the DAS login in source. If you ever
  want the short-side scripts fixed to match, that's a separate, explicit
  task -- not done automatically here.

## Files in this folder

- `ep_long_daily.py` -- **the one you run.** Daily lifecycle, trigger-price-
  anchored sizing/stop, size reconciliation (see "Which script to run").
- `ep_long_engine.py` -- unused backup/reference (continuous process,
  fill-price-anchored stop). Not launched, not maintained going forward.
- `notify_discord.py` -- identical copy of the short-side system's Discord
  webhook helper (shares the same cross-process rate limiter in `%TEMP%`).
- `.env.example` -- template; copy to `.env` and fill in (gitignored). Both
  scripts read the same `.env`.
- `credentials.json` -- you provide this (Google service-account key,
  gitignored). Shared by both scripts.
- `state/ep_long_daily_state.json` -- `ep_long_daily.py`'s persisted
  watches/positions (gitignored, created automatically). `ep_long_engine.py`
  uses a separate `state/ep_long_state.json` so the two never collide even
  if both were somehow launched.
- `logs/` -- daily tee'd terminal output per script (`ep_long_daily_*.txt` /
  `ep_long_*.txt`), gitignored, created automatically.
- `test_das_live.py` -- diagnostic: connects, confirms account/equity, fetches
  a live SPY quote, then tries a small set of candidate routes for a 1-share
  buy-stop 1% away, canceling the moment one is accepted. This is how `SMAT`
  was confirmed (see order-routes note above). Safe to rerun any time.
- `test_das_routes.py` -- diagnostic: read-only `GET RouteStatus` query,
  no orders touched. A lighter-weight check when you just want to see what
  DAS reports without placing anything.
