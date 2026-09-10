# EP Swing-Long Engine

Automates DAS Trader Pro execution for the **long** side of the EP (Episodic
Pivot) swing strategy -- "Chosen One #4" from the backtest project:

```
E60M__S0.50ADR__TCLOSE_BELOW_20MA__EQUAL_DEPLETION__LSTART20__C50
```

Source of the strategy rules: `Files/EP/Backtesting/Swing_Long_EP_Backtest_Session_Dump_2026-09-01.md`
(section 10) and the `ep_backtest/` package (`entry.py`, `initial_stop.py`,
`trailing_stops.py`, `multi_partial_taking.py`, `config.py`).

This is meaningfully simpler than the short-side system
(`Old Swing Short Scripts/`) -- no shorting, no locates, no 4 AM premarket
stop coverage. But it runs differently: it's **one continuously-running
process**, not a fresh script launched and exited each day, because an EP
long entry can sit watching for a breakout for over a week (D0..D0+7), and
once filled a position can be held for weeks riding a trailing stop.

## How it works

The Google Sheet has 4 tabs. You only ever touch the first one; the other
three are fully bot-managed live views, rebuilt from the engine's own state
on every change -- see "Google Sheet tabs" below for the full column layout
of each.

1. The morning of an EP, you add a row to the **Entry Sheet** tab (ticker,
   gap %, ADR14 %, chart pattern, enabled) -- no date column needed, a row
   present here is always "today's" candidate. The engine picks it up,
   subscribes to time & sales, and tracks the high of the first 60 minutes
   (9:30-10:30 ET). Every row it processes -- armed, skipped, or rejected --
   gets cleared from Entry Sheet immediately, so nothing lingers to be
   wrongly re-armed tomorrow.
2. At 10:30:00 ET it computes the breakout trigger (OR high + $0.01), sizes
   the position off your account equity and the ADR-based stop distance, and
   places a **buy-stop** order good for up to 8 trading sessions (D0..D0+7).
   While that order rests unfilled, it shows up on the **Current Watch List**
   tab. If it never fills, the order is canceled, the candidate drops off
   Watch List, and you get a Discord alert.
3. On fill: places a protective stop-market order (`entry_fill * (1 - ADR14 * 0.50)`)
   and 5 resting limit sell orders (the "ladder") at +20/27.5/35/42.5/50% off
   entry, each for 10% of the original share count. The remaining 50% ("core")
   never gets a ladder order. The ticker moves from Watch List onto the
   **Current Positions** tab, and a row is added to **History** (Entry Date
   through R Risk Amount filled in, Exit columns still blank).
4. The moment the first ladder rung fills, the stop is replaced to breakeven
   (`entry_fill`) for whatever shares remain, permanently. Current Positions
   updates live (which rungs are filled, current stop status, live P&L) --
   on every fill immediately, plus a background refresh every 5 minutes so
   Current Position Size / Unrealized % track live price even between fills.
5. Every trading day, a few minutes before the close, the engine checks
   whether today's close is below the 20-day SMA of closes. If so, it cancels
   the stop and any un-filled ladder rungs and sells everything remaining via
   an `AtClose` order. This is the only way the "core" 50% ever exits, absent
   a stop-out first. Either way the position disappears from Current
   Positions and its **History** row gets its Exit Date/Reason/P&L/R filled
   in -- nothing is ever deleted from History, it's the permanent YTD record.
6. All of this is persisted to `state/ep_long_state.json` after every change,
   and reconciled against DAS's own `GET POSITIONS`/`GET ORDERS` on every
   startup -- so a crash, a manual restart, or the weekend maintenance reboot
   (`WeekendWindowsMaintenance.ps1`) doesn't lose track of anything. If a
   restart finds a live position with no resting protective stop, the engine
   re-arms one immediately and sends a loud Discord alert.

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

   | Ticker | Gap % | ADR14 % | Chart Pattern | Enabled |
   |---|---|---|---|---|

   - No date column -- a row present here is always treated as **today's**
     candidate (add it the morning of the EP). The engine clears every row
     it processes (armed, skipped, or rejected) so nothing lingers into
     tomorrow as a false "today" candidate.
   - **Gap %** is informational only (flows through to History) -- not used
     in any calculation.
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

4. **Confirm the order routes.** `ROUTE_ENTRY`, `ROUTE_LADDER`, and
   `ROUTE_EXIT` (all currently defaulted to `PRO20`) and `ROUTE_STOP`
   (`SMAT`) are carried over guesses from the short-side scripts' route
   conventions -- **DAS route codes are broker-specific and not documented
   in the CMD API manual**, so these need a real confirmation (or a small
   live test with 1 share) before trusting them at size. Edit the constants
   near the top of `ep_long_engine.py` if your broker uses different codes
   for buy-side vs. sell-side or for stop vs. limit orders.

5. **Run it once by hand first**: `python ep_long_engine.py`. It runs a
   startup self-test against literal sample lines from the CMD API manual
   (order/trade/bar/position/account-info field positions) and refuses to
   start if any of those assumptions don't hold. Watch the console/log for
   the reconciliation output and the "Started" Discord message.

6. **Task Scheduler**: since Task Scheduler already manages the short-side
   `launcher.py` on this VPS, add a task for this engine too:
   - Trigger: **At startup** (covers the weekend maintenance reboot) and
     optionally also **daily at ~8:45 AM ET** with "if the task is already
     running, do nothing" -- this way a crash gets picked back up same-day
     without creating a duplicate if it's still alive.
   - Action: run `python.exe` with `ep_long_engine.py` as the argument and
     this folder as the working directory.
   - The engine's own singleton lock (`ep_long_engine.lock` in `%TEMP%`)
     prevents two copies from running simultaneously regardless.

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

- `ep_long_engine.py` -- the engine (everything above).
- `notify_discord.py` -- identical copy of the short-side system's Discord
  webhook helper (shares the same cross-process rate limiter in `%TEMP%`).
- `.env.example` -- template; copy to `.env` and fill in (gitignored).
- `credentials.json` -- you provide this (Google service-account key,
  gitignored).
- `state/ep_long_state.json` -- persisted watches/positions (gitignored,
  created automatically).
- `logs/` -- daily tee'd terminal output (gitignored, created automatically).
