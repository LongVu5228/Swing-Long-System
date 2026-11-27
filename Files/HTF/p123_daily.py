"""
Live HTF scan feed: append the newest P123 days to raw_data_htf_v2/<year>.parquet with the exact formulas the backtest
used (scan_htf_universe_v2.FORMULAS, universe ApiUniverse). The screener (local_recorder/screener_data.py) rebuilds its
9 lists, graduates and backlog from those files, so new days appear there automatically.

Only the missing trading days are pulled, in one /data/universe call per year (first run backfills 2026-09-22 ->
the last close; afterwards one day per run). P123 loads a day's data overnight, so a day counts only once the next
morning has come (before 08:00 ET it stops at the day before yesterday's close).

    ../../.venv/Scripts/python.exe p123_daily.py --dry-run     # show which days would be pulled, no API call
    ../../.venv/Scripts/python.exe p123_daily.py               # pull + append (costs P123 API credits)
Credentials: P123_API_ID / P123_API_KEY from the .env next to Files/Buyable Gap Up/p123_client.py (never printed).
"""
import argparse
import os
import sys
from datetime import datetime

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scan_htf_universe_v2 as scan  # noqa: E402  (also puts Buyable Gap Up/ on the path for P123Client)


def last_ready_day():
    """Newest session P123 should have loaded: yesterday's close after ~08:00 ET, else the session before that."""
    import zoneinfo
    now = pd.Timestamp.now(tz=zoneinfo.ZoneInfo("America/New_York"))
    cut = now.normalize() - pd.Timedelta(days=1 if now.hour >= 8 else 2)
    import pandas_market_calendars as mcal
    sched = mcal.get_calendar("NYSE").schedule(start_date=(cut - pd.Timedelta(days=10)).date(), end_date=cut.date())
    return sched.index[-1].date()


def missing_days():
    """{year: [dates not yet in raw_data_htf_v2/<year>.parquet]} from the last stored day to last_ready_day()."""
    end = last_ready_day()
    out = {}
    for y in range(end.year - 1, end.year + 1):
        p = scan.raw_path(y)
        have = set()
        if os.path.exists(p):
            have = set(pd.read_parquet(p, columns=["date"]).date.astype(str).str[:10])
        if not have and y < end.year:
            continue
        last = max(have) if have else f"{y}-01-01"
        days = [d for d in scan.trading_days_in_year(y) if last < d.isoformat() <= end.isoformat()]
        if days:
            out[y] = days
    return out


def pull(dry=False, verbose=True):
    todo = missing_days()
    if not todo:
        if verbose:
            print("P123 feed up to date:", last_ready_day())
        return 0
    n = sum(len(v) for v in todo.values())
    if verbose:
        for y, ds in todo.items():
            print(f"{y}: {len(ds)} day(s) to pull, {ds[0]} -> {ds[-1]}")
    if dry:
        return n
    from p123_client import P123Client
    client = P123Client()
    for y, ds in todo.items():
        result = client.post("/data/universe", {"type": "Stock", "universe": scan.UNIVERSE_NAME, "formulas": scan.FORMULAS,
                                                "asOfDts": [d.isoformat() for d in ds]})
        new = pd.DataFrame(scan._records_from_result(result))
        if new.empty:
            print(f"{y}: P123 returned no rows (not loaded yet?)")
            continue
        p = scan.raw_path(y)
        old = pd.read_parquet(p) if os.path.exists(p) else pd.DataFrame(columns=new.columns)
        both = pd.concat([old, new], ignore_index=True)
        both["date"] = both.date.astype(str).str[:10]
        both = both.drop_duplicates(["date", "ticker"], keep="last").sort_values(["date", "ticker"])
        tmp = p + ".tmp"
        both.to_parquet(tmp, index=False)
        os.replace(tmp, p)
        if verbose:
            print(f"{y}: +{new.date.astype(str).str[:10].nunique()} day(s), {len(new):,} rows | API cost {result.get('cost')}"
                  f" | quota remaining {result.get('quotaRemaining')}")
    return n


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    print(datetime.now().isoformat(timespec="seconds"))
    pull(dry=a.dry_run)
