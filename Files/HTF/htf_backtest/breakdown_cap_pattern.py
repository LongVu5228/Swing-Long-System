import glob, numpy as np, pandas as pd
t = pd.read_parquet('backtest_outputs/trades_gauntlet_slip0.1.parquet')
t = t[(t.status == 'OK') & (t.strategy_id == 'E5M__S0.75ADR__T20MA_TOUCH') & (t.partial == 'ref')].copy()
truth = pd.read_csv('Advanced Backtesting/htf_pattern_truth.csv')[['ticker', 'flag_no', 'truth']]
t = t.merge(truth, on=['ticker', 'flag_no'], how='left')
t['truth'] = t.truth.fillna('unlabeled (DE..DK)')
tk = set(t.ticker)
raw = []
for f in sorted(glob.glob('raw_data_htf_v2/*.parquet')):
    r = pd.read_parquet(f, columns=['date', 'ticker', 'mktcap'])
    r['base'] = r.ticker.str.split('^').str[0]
    raw.append(r[r.base.isin(tk)])
raw = pd.concat(raw)
raw['date'] = pd.to_datetime(raw.date).astype('datetime64[ns]'); raw['base'] = raw.base.astype(object)
t['ticker'] = t.ticker.astype(object)
t['conf'] = pd.to_datetime(t.setup_confirmed.astype(int).astype(str)).astype('datetime64[ns]')
t = t.sort_values('conf')
raw = raw.sort_values('date')
# delisted names share a base ticker with later listings: take the row on/just before confirmation, within 10 days
m = pd.merge_asof(t, raw[['date', 'base', 'mktcap']].rename(columns={'base': 'ticker'}), left_on='conf', right_on='date',
                  by='ticker', direction='backward', tolerance=pd.Timedelta('10D'))
print(f"trades {len(m)}, with market cap {m.mktcap.notna().mean():.1%}")
m['cap'] = pd.cut(m.mktcap, [0, 300, 1000, 2000, 10000, 1e9], labels=['<300M', '300M-1B', '1-2B', '2-10B', '10B+'])

def st(g):
    r = g.sort_values('entry_date').realized_R.to_numpy(); n = len(r); s = np.sort(r)
    eq = np.cumsum(r); dd = (eq - np.maximum.accumulate(np.maximum(eq, 0))).min()
    return pd.Series({'n': n, 'win%': (r > 0).mean() * 100, 'EV': r.mean(),
                      'EV_ex10R': r[r < 10].mean(), 'EV_ex_top5%': s[:n - int(np.ceil(n * .05))].mean() if n >= 20 else np.nan,
                      '10R+': int((r >= 10).sum()), 'total': r.sum(), 'maxDD': dd})
pd.set_option('display.width', 200)
print('\nBY MARKET CAP (at confirmation)'); print(m.groupby('cap', observed=True).apply(st, include_groups=False).round(2).to_string())
print('\nBY PATTERN'); print(m.groupby('truth').apply(st, include_groups=False).round(2).sort_values('EV', ascending=False).to_string())
m['side'] = np.where(m.truth.isin(['Red HTF', 'Big Red Flag']), 'red', np.where(m.truth.str.startswith('unl'), 'unl', 'non-red'))
mm = m[m.side != 'unl']
print('\nCAP x RED/NON-RED: EV (n)')
ev = mm.pivot_table(index='cap', columns='side', values='realized_R', aggfunc='mean', observed=True).round(2)
n = mm.pivot_table(index='cap', columns='side', values='realized_R', aggfunc='size', observed=True)
print(ev.astype(str) + ' (' + n.astype(str) + ')')
print('\nCAP x PATTERN: EV (n)')
ev = mm.pivot_table(index='truth', columns='cap', values='realized_R', aggfunc='mean', observed=True).round(2)
n = mm.pivot_table(index='truth', columns='cap', values='realized_R', aggfunc='size', observed=True)
print((ev.astype(str) + ' (' + n.astype(str) + ')').to_string())
print('\nCAP x PATTERN: EV ex top 5%')
print(mm.groupby(['truth', 'cap'], observed=True).apply(lambda g: st(g)['EV_ex_top5%'], include_groups=False).unstack().round(2).to_string())
m['era'] = pd.cut(m.entry_date.str[:4].astype(int), [2004, 2014, 2019, 2026], labels=['2005-14', '2015-19', '2020-26'])
print('\nCAP x ERA: EV (n)')
ev = m.pivot_table(index='cap', columns='era', values='realized_R', aggfunc='mean', observed=True).round(2)
n = m.pivot_table(index='cap', columns='era', values='realized_R', aggfunc='size', observed=True)
print((ev.astype(str) + ' (' + n.astype(str) + ')').to_string())
print('\nCAP x ERA: EV ex top 5%')
print(m.groupby(['cap', 'era'], observed=True).apply(lambda g: st(g)['EV_ex_top5%'], include_groups=False).unstack().round(2).to_string())
m['cap2'] = np.where(m.mktcap < 2000, '<2B', '2B+')
print('\n<2B vs 2B+ by era'); print(m.groupby(['cap2', 'era'], observed=True).apply(st, include_groups=False).round(2).to_string())
rng = np.random.default_rng(0); a = m[m.cap2 == '<2B'].realized_R.to_numpy(); b = m[m.cap2 == '2B+'].realized_R.to_numpy()
d = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(5000)])
print(f"\n<2B minus 2B+ EV: {a.mean() - b.mean():+.3f}R  90% CI [{np.percentile(d, 5):+.3f}, {np.percentile(d, 95):+.3f}]")
