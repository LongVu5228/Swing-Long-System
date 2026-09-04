"""
Build the comprehensive Excel workbook for the 4th chosen one strategy:
E60M / 0.50ADR / close_below_20ma / equal_depletion / start20 / C50.

Tabs: Summary, Trade Log, Fills Detail, Per-Ticker Summary, Year Breakdown,
Drawdown & Equity Curve.

Reads outputs/walkforward/fourth_chosen_full_sim.pkl (built by
build_4th_chosen_workbook_data.py) -- entry_timestamp is always a genuine tz-aware
intraday Timestamp (comes straight from minute-bar data), but sales_detail timestamps
are a MIX: real intraday timestamps for minute-bar-precision exits, and plain
`datetime.date` objects (no time-of-day, no timezone) for exits that fall back to
daily-bar approximation (SMA20_EXIT, TARGET_TRADE_THROUGH_DAILY_APPROX -- used once a
trade runs past the minute-bar scanning window). 855 of 2,230 fill rows (38%) are this
daily-approx kind.

Bug fixed 2026-09-03 (caught by user spot-checking the workbook -- REAL's 10/6/2025
SMA20_EXIT was showing as 10/5/2025 8:00 PM): the original build ran EVERY timestamp
through `pd.to_datetime(col, utc=True).dt.tz_convert('America/New_York')`. That's correct
for real intraday timestamps, but for a plain date with no time attached, `utc=True`
silently assumes midnight UTC -- converting midnight UTC to ET (UTC-4 in October) lands
on 8pm the PREVIOUS day. The underlying realized_R/simulation math was never affected
(it used the correct date internally); this was purely a display bug in this export
step. Fixed by converting each timestamp individually based on its actual type instead
of a blanket column-wide conversion -- a plain date has no time-of-day to convert, it's
already the correct ET calendar day.
"""
import datetime as dt
import sys
sys.path.insert(0, '.')
import numpy as np
import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl.styles import Font

STRATEGY_ID = 'E60M__S0.50ADR__TCLOSE_BELOW_20MA__EQUAL_DEPLETION__LSTART20__C50'
DT_FAMILY = ['DT', 'DT SW', 'DT U']


def to_naive_et(value):
    """Convert a mixed-type timestamp (tz-aware intraday Timestamp OR plain
    datetime.date) to a naive-ET pandas Timestamp, without corrupting plain dates."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return pd.NaT
    if isinstance(value, dt.datetime):
        ts = pd.Timestamp(value)
        if ts.tzinfo is not None:
            ts = ts.tz_convert('America/New_York').tz_localize(None)
        return ts
    if isinstance(value, dt.date):
        return pd.Timestamp(value)
    return pd.to_datetime(value)


sim = pd.read_pickle('outputs/walkforward/fourth_chosen_full_sim.pkl')
sim['event_date'] = pd.to_datetime(sim['event_date'])

ok = sim[(sim['status'] == 'OK') & (~sim['chart_pattern'].isin(DT_FAMILY))].copy()
ok = ok.sort_values('event_date').reset_index(drop=True)
print(f'{len(sim)} total events processed, {len(ok)} OK + non-DT-family trades')

# ---------- Trade Log ----------
trade_log = ok[[
    'ticker', 'event_date', 'chart_pattern', 'adr14', 'adr_category', 'trading_turnover_pct_category',
    'spy_trend_color', 'entry_timestamp', 'entry_day_offset', 'entry_fill', 'initial_stop_price',
    'n_sales', 'realized_R',
]].copy()
trade_log['risk_per_share'] = trade_log['entry_fill'] - trade_log['initial_stop_price']
trade_log['cumulative_R'] = trade_log['realized_R'].cumsum()
running_peak = trade_log['cumulative_R'].cummax()
trade_log['drawdown_R'] = trade_log['cumulative_R'] - running_peak
trade_log = trade_log.rename(columns={'entry_timestamp': 'entry_datetime'})
trade_log['entry_datetime'] = trade_log['entry_datetime'].apply(to_naive_et)

# ---------- Fills Detail (one row per partial sale + final exit) ----------
fills_rows = []
for _, row in ok.iterrows():
    for sale in row['sales_detail']:
        fills_rows.append({
            'ticker': row['ticker'], 'event_date': row['event_date'], 'sale_num': sale['sale_num'],
            'sale_timestamp': sale['timestamp'], 'sale_price': round(sale['price'], 4),
            'pct_of_original_sold': round(sale['pct_of_original'] * 100, 2), 'reason': sale['reason'],
        })
fills = pd.DataFrame(fills_rows)
fills['sale_timestamp'] = fills['sale_timestamp'].apply(to_naive_et)

# ---------- Per-Ticker Summary ----------
per_ticker = ok.groupby('ticker').agg(
    n_trades=('realized_R', 'count'),
    total_R=('realized_R', 'sum'),
    avg_R=('realized_R', 'mean'),
    win_rate=('realized_R', lambda x: (x > 0).mean() * 100),
    best_trade_R=('realized_R', 'max'),
    worst_trade_R=('realized_R', 'min'),
).reset_index().sort_values('total_R', ascending=False)
per_ticker[['total_R', 'avg_R', 'win_rate', 'best_trade_R', 'worst_trade_R']] = per_ticker[
    ['total_R', 'avg_R', 'win_rate', 'best_trade_R', 'worst_trade_R']].round(3)

# ---------- Year Breakdown ----------
ok['year'] = ok['event_date'].dt.year
year_rows = []
for yr, g in ok.groupby('year'):
    n = len(g)
    wins = g[g['realized_R'] > 0]['realized_R']
    losses = g[g['realized_R'] <= 0]['realized_R']
    win_rate = len(wins) / n * 100
    pf = wins.sum() / abs(losses.sum()) if losses.sum() != 0 else np.inf
    year_rows.append({
        'year': yr, 'trades': n, 'win_rate_pct': round(win_rate, 1),
        'avg_winner_R': round(wins.mean(), 3) if len(wins) else np.nan,
        'avg_loser_R': round(losses.mean(), 3) if len(losses) else np.nan,
        'profit_factor': round(pf, 3), 'EV_R': round(g['realized_R'].mean(), 4),
        'total_R': round(g['realized_R'].sum(), 2),
    })
year_df = pd.DataFrame(year_rows)
n_all = len(ok); wins_all = ok[ok['realized_R'] > 0]['realized_R']; losses_all = ok[ok['realized_R'] <= 0]['realized_R']
year_df = pd.concat([year_df, pd.DataFrame([{
    'year': 'ALL', 'trades': n_all, 'win_rate_pct': round(len(wins_all)/n_all*100, 1),
    'avg_winner_R': round(wins_all.mean(), 3), 'avg_loser_R': round(losses_all.mean(), 3),
    'profit_factor': round(wins_all.sum()/abs(losses_all.sum()), 3), 'EV_R': round(ok['realized_R'].mean(), 4),
    'total_R': round(ok['realized_R'].sum(), 2),
}])], ignore_index=True)

# ---------- Drawdown & Equity Curve ----------
eq = trade_log[['ticker', 'event_date', 'realized_R', 'cumulative_R', 'drawdown_R']].copy()
max_dd = eq['drawdown_R'].min()
max_dd_idx = eq['drawdown_R'].idxmin()
eq['is_max_drawdown_point'] = eq.index == max_dd_idx

r = ok['realized_R'].to_numpy()
is_win = r > 0
streaks, cur = [], 0
for w in is_win:
    if not w: cur += 1
    else:
        if cur > 0: streaks.append(cur)
        cur = 0
if cur > 0: streaks.append(cur)
max_streak = max(streaks) if streaks else 0

ok_sorted = ok.sort_values('realized_R', ascending=False)
top10n = max(1, round(len(ok_sorted) * 0.10))
pct_top10 = ok_sorted.head(top10n)['realized_R'].sum() / ok_sorted['realized_R'].sum() * 100

# ---------- Summary tab ----------
wins = ok[ok['realized_R'] > 0]['realized_R']; losses = ok[ok['realized_R'] <= 0]['realized_R']
n = len(ok)
summary_data = [
    ('Strategy ID', STRATEGY_ID),
    ('Entry', '60m opening-range breakout'),
    ('Stop', '0.50 x ADR14'),
    ('Trail', 'close_below_20ma'),
    ('Sell style', 'equal_depletion'),
    ('Target ladder', 'start20 (20 / 27.5 / 35 / 42.5 / 50%)'),
    ('Core %', '50% (rides trail uncapped past +50%)'),
    ('DT-family (DT/DT SW/DT U) excluded', 'Yes'),
    ('', ''),
    ('Triggered trades', n),
    ('Win rate', f'{len(wins)/n*100:.1f}%'),
    ('Avg winner (R)', round(wins.mean(), 3)),
    ('Avg loser (R)', round(losses.mean(), 3)),
    ('RR', round(wins.mean()/abs(losses.mean()), 3)),
    ('Profit factor', round(wins.sum()/abs(losses.sum()), 3)),
    ('EV_R (expectancy per trade)', round(ok['realized_R'].mean(), 4)),
    ('Total R', round(ok['realized_R'].sum(), 2)),
    ('Median R', round(ok['realized_R'].median(), 3)),
    ('Std dev R', round(ok['realized_R'].std(), 3)),
    ('', ''),
    ('Max losing streak (trades)', max_streak),
    ('Max drawdown (R)', round(max_dd, 2)),
    ('Max drawdown ticker/date', f"{eq.loc[max_dd_idx,'ticker']} @ {eq.loc[max_dd_idx,'event_date'].date()}"),
    ('Outlier reliance (% of total R from top 10% of trades)', f'{pct_top10:.1f}%'),
    ('', ''),
    ('OOS train G-score (<=2019)', 9.48),
    ('OOS test G-score (>=2020)', 9.55),
    ('OOS train EV_R', 0.561),
    ('OOS test EV_R', 0.566),
    ('', ''),
    ('Slippage sensitivity: EV_R at 0.1% (baseline)', 0.618),
    ('Slippage sensitivity: EV_R at 0.3%', 0.421),
    ('Slippage sensitivity: EV_R at 1.0%', -0.109),
    ('Slippage breakeven (approx)', '~0.85-0.9% per fill'),
]
summary_df = pd.DataFrame(summary_data, columns=['Metric', 'Value'])

# ---------- Write workbook ----------
out_path = 'outputs/V4 Master Strategies - 4th Chosen One Detail.xlsx'
with pd.ExcelWriter(out_path, engine='openpyxl') as writer:
    summary_df.to_excel(writer, sheet_name='Summary', index=False)
    trade_log.to_excel(writer, sheet_name='Trade Log', index=False)
    fills.to_excel(writer, sheet_name='Fills Detail', index=False)
    per_ticker.to_excel(writer, sheet_name='Per-Ticker Summary', index=False)
    year_df.to_excel(writer, sheet_name='Year Breakdown', index=False)
    eq.to_excel(writer, sheet_name='Drawdown & Equity Curve', index=False)

    for sheet_name, df in [('Trade Log', trade_log), ('Fills Detail', fills), ('Per-Ticker Summary', per_ticker),
                            ('Year Breakdown', year_df), ('Drawdown & Equity Curve', eq)]:
        ws = writer.sheets[sheet_name]
        last_col = get_column_letter(len(df.columns))
        ws.auto_filter.ref = f'A1:{last_col}{len(df) + 1}'
        ws.freeze_panes = 'A2'

    ws_sum = writer.sheets['Summary']
    ws_sum.column_dimensions['A'].width = 48
    ws_sum.column_dimensions['B'].width = 40
    for cell in ws_sum['A']:
        cell.font = Font(bold=True)

print(f'wrote {out_path}')
for name, df in [('Summary', summary_df), ('Trade Log', trade_log), ('Fills Detail', fills),
                  ('Per-Ticker Summary', per_ticker), ('Year Breakdown', year_df), ('Drawdown & Equity Curve', eq)]:
    print(f'  {name}: {len(df)} rows')
