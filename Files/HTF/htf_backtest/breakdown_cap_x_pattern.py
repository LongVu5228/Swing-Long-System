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
m = m[m.mktcap.notna() & ~m.truth.isin(['Expanding HTF', 'unlabeled (DE..DK)'])].copy()
m['small'] = m.mktcap < 2000
m['Rw'] = m.realized_R.clip(upper=10)          # winsorized at 10R: same test with monsters capped
rng = np.random.default_rng(7)
B = 5000

def diff(a, b, col):
    return a[col].mean() - b[col].mean()

for col, lab in (('realized_R', 'RAW EV'), ('Rw', 'EV WITH WINNERS CAPPED AT 10R')):
    print(f'\n===== {lab}: small (<2B) minus large (2B+) =====')
    rows = []
    for p, g in m.groupby('truth'):
        a, b = g[g.small][col].to_numpy(), g[~g.small][col].to_numpy()
        bs = np.array([rng.choice(a, len(a)).mean() - rng.choice(b, len(b)).mean() for _ in range(B)])
        rows.append({'pattern': p, 'n_small': len(a), 'n_large': len(b), 'EV_small': a.mean(), 'EV_large': b.mean(),
                     'diff': a.mean() - b.mean(), 'ci90_lo': np.percentile(bs, 5), 'ci90_hi': np.percentile(bs, 95),
                     'P(diff<=0)': (bs <= 0).mean(), 'var': bs.var()})
    r = pd.DataFrame(rows)
    print(r.drop(columns='var').round(3).to_string(index=False))
    # Cochran-style heterogeneity of the per-pattern differences, null by permuting pattern labels within cap group
    def Q(df):
        d, w = [], []
        for p, g in df.groupby('truth'):
            a, b = g[g.small][col], g[~g.small][col]
            d.append(a.mean() - b.mean()); w.append(1 / (a.var() / len(a) + b.var() / len(b)))
        d, w = np.array(d), np.array(w)
        return (w * (d - (w * d).sum() / w.sum()) ** 2).sum()
    q0 = Q(m)
    perm = []
    for _ in range(2000):
        mm = m.copy()
        for s in (True, False):
            idx = mm.index[mm.small == s]
            mm.loc[idx, 'truth'] = rng.permutation(mm.loc[idx, 'truth'].to_numpy())
        perm.append(Q(mm))
    print(f'interaction across 6 patterns: Q = {q0:.2f}, permutation p = {(np.array(perm) >= q0).mean():.3f}')
    # red vs non-red difference-in-differences
    red = m.truth.isin(['Red HTF', 'Big Red Flag'])
    def did(df, rd):
        return diff(df[rd & df.small], df[rd & ~df.small], col) - diff(df[~rd & df.small], df[~rd & ~df.small], col)
    obs = did(m, red)
    bs = []
    for _ in range(B):
        i = rng.integers(0, len(m), len(m)); mm = m.iloc[i]; bs.append(did(mm, red.iloc[i].to_numpy()))
    bs = np.array(bs)
    print(f'red vs non-red: small-cap edge red {diff(m[red & m.small], m[red & ~m.small], col):+.3f}  '
          f'non-red {diff(m[~red & m.small], m[~red & ~m.small], col):+.3f}  '
          f'diff-in-diff {obs:+.3f}  90% CI [{np.percentile(bs, 5):+.3f}, {np.percentile(bs, 95):+.3f}]')
