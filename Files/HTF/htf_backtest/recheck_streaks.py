"""Re-check every list row's daily bars against P123's 1-month return AROUND ITS SCANNER STREAKS only
(streak start - 63 sessions .. streak end + 21). The puller's check took the median over the whole history,
so a reused symbol (ES = EnergySolutions 2007-13, Eversource after the NU rename) passed on its good years.

    ../../.venv/Scripts/python.exe -m htf_backtest.recheck_streaks      # -> backtest_data/streak_check.csv
"""
import glob
import os

import numpy as np
import pandas as pd

from . import config
from .delisted_bars import LIST, RAW, safe

TOL = 0.05


def main():
    L = pd.read_csv(LIST)
    L["list_row"] = np.arange(2, len(L) + 2)
    want = set(L.ticker)
    p = []
    for f in sorted(glob.glob(os.path.join(RAW, "*.parquet"))):
        r = pd.read_parquet(f, columns=["date", "ticker", "ret_1m"])
        p.append(r[r.ticker.isin(want)])
    p = pd.concat(p)
    p["date"] = pd.to_datetime(p.date)
    P = {t: g.set_index("date").ret_1m for t, g in p.groupby("ticker")}
    out = []
    for r in L.itertuples():
        d_dir = "delisted_daily" if "^" in r.ticker else "list_daily"
        fp = os.path.join(config.DATA_DIR, d_dir, safe(r.ticker) + ".parquet")
        row = {"list_row": r.list_row, "ticker": r.ticker}
        if not os.path.exists(fp) or r.ticker not in P:
            out.append({**row, "streak_status": "NO_DATA" if not os.path.exists(fp) else "NO_P123"})
            continue
        b = pd.read_parquet(fp)
        if b.empty:
            out.append({**row, "streak_status": "NO_DATA"})
            continue
        s = b.assign(date=pd.to_datetime(b.date)).set_index("date").close
        ret = s / s.shift(22) - 1   # P123 ret_1m = 22 sessions (21 fails fast movers: QUBT 11% vs 5%)
        res = []
        for span in str(r.streak_spans).split(";"):
            if ".." not in span:
                continue
            a, e = (pd.Timestamp(x.strip()) for x in span.split(".."))
            pp = P[r.ticker][(P[r.ticker].index >= a - pd.Timedelta(days=92)) & (P[r.ticker].index <= e + pd.Timedelta(days=31))]
            j = pd.concat([pp.rename("p"), ret.rename("b")], axis=1, join="inner").dropna()
            cov = s.index.isin(pp.index).sum() / max(len(pp), 1)
            med = float((np.log1p(j.p) - np.log1p(j.b)).abs().median()) if len(j) >= 10 else np.nan
            res.append((span.strip(), med, cov, len(j)))
        meds = [m for _, m, _, _ in res if m == m]
        bad = [sp for sp, m, c, n in res if (m == m and m > TOL) or n < 10]
        out.append({**row, "n_streaks": len(res), "worst_streak_diff": max(meds) if meds else np.nan,
                    "bad_streaks": len(bad), "bad_spans": "; ".join(bad),
                    "streak_status": "OK" if not bad else ("ALL_BAD" if len(bad) == len(res) else "SOME_BAD")})
    o = pd.DataFrame(out)
    o.to_csv(os.path.join(config.DATA_DIR, "streak_check.csv"), index=False)
    o["kind"] = np.where(o.ticker.str.contains("^", regex=False), "delisted", "active")
    print(o.groupby(["kind", "streak_status"]).size().to_string())
    print("\nto-do range (row > 1216 or delisted not yet charted):")
    print(o[(o.list_row > 1216)].groupby(["kind", "streak_status"]).size().to_string())


if __name__ == "__main__":
    main()
