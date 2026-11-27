# HTF Swing Strategy: final rules and expected stats

> **WARNING (2026-11-25): the held-out test FAILED.** On 180 held-out trades (tickers DKS..ETSY) the same rules made
> **-0.40R per trade** (90% range -0.66 to -0.13) vs +0.38R on the dev sample. The stats below are dev-sample only and
> are NOT validated. Do not trade at size until a second held-out batch says otherwise. See findings doc section 41.

Locked 2026-11-24, re-checked 2026-11-25. The evidence behind every rule is in
`HTF_Backtest_Findings_CURRENT.md`, sections 34–40.

## 1. The rules

| Step | Rule |
|---|---|
| **Find** | Each evening, look over the HTF scanner lists: top 16 per market-cap group (Small $50M–2B, Mid $2–10B, Large $10B+) by 1-, 3- and 6-month return. The scan's gates are ADR14 ≥ 5%, dollar volume ≥ $10M, market cap ≥ $50M, and SMA10 and SMA20 both rising. Also look over the graduates: names on a list in the past 6 months but not today. |
| **Pick** | Your eye call on the chart: a high tight flag with a clear R1 (the line of least resistance). **Skip Red HTF and Big Red Flag.** Trade Green HTF, Perfect HTF, Big Green Flag and Big Perfect Flag. |
| **Arm** | R1 = the high of the R1 candle. The day you arm it counts as the confirmation day. |
| **Market filter** | **No new entries (re-tries included) on a day after SPY closed below its 200-day SMA.** Open positions are managed as normal. |
| **Entry** | Every session for the next **15 sessions**: at 10:00 ET, place a buy-stop at **max(R1, the 30-minute opening high) + $0.01**, live until the close. Unfilled orders die at the close and are placed again the next day at 10:00. If the stock gaps over R1, you only buy it if it breaks that day's 30-minute high. |
| **Stop** | Fill price × (1 − 0.75 × ADR14). ADR14 = (average high − average low over the last 14 sessions) ÷ the prior close. |
| **Partials** | Sell 10% of the position at **+20%, +27.5%, +35%, +42.5% and +50%** from the fill. A gap through several levels sells them all at the open. |
| **Breakeven** | After the first partial, the stop on the rest moves to the entry price. |
| **Core exit** | Whatever is left (at least the 50% core) sells on the **first intraday touch of the 20-day SMA**. There are no further targets. |
| **Earnings** | Hold through them. Don't sell before the report. |
| **Re-try** | One. If the first trade is stopped out for a loss inside the 15-session window, the same entry rule can fire once more (it still has to pass the SPY filter). |
| **Size** | Start at 0.25% of the account risked per trade (entry − stop). At $35k that's about $87 per trade. |

## 2. Expected stats

Measured on the dev sample: 3,809 flags (tickers AA–DKNG, about 27% of the list), including about 1,300 delisted
names, 2005–2026. **Every loss is counted as −1.3R** to cover slippage. The re-try is not included unless noted.

| Measure | Value |
|---|---|
| Win rate | **30.5%** |
| Average win / average loss | **+4.21R / −1.30R** (about 3.2 : 1) |
| Expectancy | **+0.38R per trade** (+0.59R at normal 0.1% slippage) |
| Max drawdown | **−38R** (about −50R with the one re-try added) |
| Losing years | 4 of 22 (the bad ones: 2008, 2011) |
| Without the top 5% of winners | **−0.23R per trade**: the edge is the rare 10R+ runners, so **never skip a valid trade** |
| Trades per year | median 58 in the dev sample, so **about 210 a year on the full list** |
| Clustering | 48% of weeks have no trade; hot markets bring many at once |
| Open positions | dev sample: 3 on a typical day, peak 19; full list: about 10 typical, peaks around 50–70 |
| Typical stop width | about 4–6% of price |
| Equity Curve Simulator inputs | win rate 30.5, RR 4.51, cost 0.3, risk 0.25%, 210 trades, $35,000 |

### By market cap (green flags, SPY above 200d)

| Group | Trades | Per trade | Max DD |
|---|---|---|---|
| Under $300M | 73 | +0.33R | −19R |
| $300M–2B | 625 | **+0.47R** | −24R |
| $2B–10B | 503 | +0.22R (+0.93R in 2005–15, −0.02R in 2016–26) | −45R |
| Over $10B | 172 | +0.55R | −15R |

Trade all caps. Watch the $2B–10B group in the held-out test.

### Why the two filters matter

| Flags | SPY | Per trade | Max DD |
|---|---|---|---|
| Green | above 200d | **+0.38R** | −38R |
| Green | below 200d | **−0.41R** | −145R |
| Red | either | about +0.08R | −50 to −82R |

## 3. How we know it's not luck

- **Robustness checks:** the system family passed every one we ran.
  - Reality Check / SPA tests against 1,722 alternative strategies: p ≤ 0.004.
  - Walk-forward: every later test period was positive.
  - Block-bootstrap confidence intervals exclude zero.
  - Break-even slippage is about 0.7–0.9% per fill.
- **Blind trainer:** on about 270 flags graded without hindsight, green calls made +1.30R and red calls +0.05R (p ≈ 0.003).
- **Entry timing is a plateau:** the R1 buy-stop, the 1-minute and the 5-minute entries were all within noise of the 30-minute entry. The 30-minute entry has the lowest drawdown and avoids opening-auction fills (§40).
- **Partials barely matter:** keeping 0–70% core all earn the same. Selling early hurts; holding everything (no partials) is worst (§20, §40).
- **Filters that failed** (fixed cutoffs, must win in every period): market cap, price, dollar volume, stop width, ADR, extension above R1, SPY's 200d rising, IWM, earnings within 10 days, flag length.

## 4. Known risks

- The edge is concentrated in a few big runners each year. Losing streaks and flat stretches are normal.
- Assuming −1.3R per loss is a guess. Measure your real fills in the first months.
- Drawdowns are in R units: −38R × 0.25% ≈ −9.5% of the account.
- The rules haven't yet been run on the held-out rows (tickers after DKNG). That is the next check.
