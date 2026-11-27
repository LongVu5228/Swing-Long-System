"""
True intraday-entry version of quick_backtest_chosen_one.py, on the flags recent enough for
the free Massive tier's intraday history (~2024-10-10 onward).

The daily proxy's result hinged on an assumption daily bars can't settle: whether the entry
day's low printed before or after the buy (EV swung -0.43R to +1.29R on it). This measures it.

Entry (EP-style, per session in the window): trigger = max(that session's 60-minute
opening-range high + 1 tick, R1). EP fixes one ORH on its event day; HTF has no event day,
so each session gets its own. Fills start strictly after 10:30 ET (no fill inside the
defining range), at the trigger, or at the bar's open if it gaps over. Window and every
exit rule match the daily version: sessions after setup_confirmed through final_flag_end,
0.5 ADR stop, 10% at each of +20/27.5/35/42.5/50%, breakeven after the first sale, core out
on a close below the 20-day SMA, 0.1% slippage.

The ENTRY DAY is walked in 5-minute bars in time order, which is the point -- stop vs target
ordering on that day is now observed, not assumed. Later days use daily bars from the
TradingView export exactly as the daily version does. Also re-runs the daily proxy on the
same flags for an apples-to-apples comparison.

    python quick_backtest_hourly.py
"""
import json
import os
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pandas as pd
import requests
from dotenv import load_dotenv

import quick_backtest_chosen_one as daily

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.join(HERE, "..", "..", "..")
CACHE = os.path.join(HERE, "data_cache_intraday")
OUT = os.path.join(HERE, "quick_backtest_hourly_trades.csv")
load_dotenv(os.path.join(REPO, ".env"))
KEY = os.getenv("POLYGON_API_KEY")
ET = ZoneInfo("America/New_York")

COVERAGE_START = 20241010     # free tier's intraday floor, measured 2026-10-09
TICK = 0.01
CALL_GAP_S = 13               # free tier allows 5 calls/minute


def ymd_to_date(x: int) -> date:
    return datetime.strptime(str(int(x)), "%Y%m%d").date()


_last_call = [0.0]


def fetch_5min(ticker: str, start: date, end: date) -> pd.DataFrame:
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, f"{ticker}_{start:%Y%m%d}_{end:%Y%m%d}.json")
    if os.path.exists(path):
        rows = json.load(open(path))
    else:
        rows, url = [], (f"https://api.polygon.io/v2/aggs/ticker/{ticker}/range/5/minute/"
                         f"{start}/{end}?adjusted=true&sort=asc&limit=50000")
        while url:
            wait = CALL_GAP_S - (time.time() - _last_call[0])
            if wait > 0:
                time.sleep(wait)
            r = requests.get(url + (f"&apiKey={KEY}" if "apiKey" not in url else ""), timeout=60)
            _last_call[0] = time.time()
            if r.status_code == 429:
                time.sleep(60)
                continue
            if r.status_code != 200:
                break
            j = r.json()
            rows += j.get("results", [])
            url = j.get("next_url")
        json.dump(rows, open(path, "w"))
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df["dt"] = pd.to_datetime(df["t"], unit="ms", utc=True).dt.tz_convert(ET)
    df = df[(df["dt"].dt.time >= datetime.strptime("09:30", "%H:%M").time())
            & (df["dt"].dt.time < datetime.strptime("16:00", "%H:%M").time())]
    df["d"] = df["dt"].dt.strftime("%Y%m%d").astype(int)
    return df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close"})[
        ["dt", "d", "open", "high", "low", "close"]].reset_index(drop=True)


def find_entry(intra: pd.DataFrame, r1: float):
    for d, day in intra.groupby("d", sort=True):
        start = day["dt"].iloc[0].normalize() + pd.Timedelta(hours=9, minutes=30)
        or_end = start + pd.Timedelta(minutes=60)
        first_hour = day[day["dt"] < or_end]
        if first_hour.empty:
            continue
        orh = float(first_hour["high"].max())
        trigger = round(max(orh + TICK, r1), 4)
        after = day[day["dt"] >= or_end]
        for k, bar in after.iterrows():
            if bar["open"] > trigger:
                return d, k, float(bar["open"]), trigger, orh, "gap_through"
            if bar["high"] >= trigger:
                return d, k, trigger, trigger, orh, "trade_through"
    return None


def simulate(flag, bars: pd.DataFrame, intra: pd.DataFrame) -> dict:
    out = {"ticker": flag.ticker, "flag_no": flag.flag_no, "setup_type": flag.setup_type,
           "setup_confirmed": flag.setup_confirmed, "r1_price": flag.r1_price}
    r1 = float(flag.r1_price)
    win = intra[(intra["d"] > flag.setup_confirmed) & (intra["d"] <= flag.final_flag_end)]
    found = find_entry(win, r1) if not win.empty else None
    if found is None:
        return {**out, "status": "NO_ENTRY"}
    d, k, ref, trigger, orh, how = found

    idx = bars.index[bars["d"] == d]
    if len(idx) == 0 or idx[0] < 15:
        return {**out, "status": "NO_DAILY_ALIGN"}
    i = int(idx[0])
    entry = ref * (1 + daily.SLIP)
    prior = bars.iloc[i - 14:i]
    adr = (prior["high"].mean() - prior["low"].mean()) / float(bars.at[i - 1, "close"])
    stop = entry * (1 - daily.STOP_ADR_MULT * adr)
    risk = entry - stop
    out.update(entry_date=d, entry_time=str(intra.at[k, "dt"].time()), entry_fill=round(entry, 4),
               fill_above_r1_pct=round((ref / r1 - 1) * 100, 2), orh=round(orh, 4),
               fill_reason=how, adr14=round(adr, 4), stop=round(stop, 4))

    targets = [entry * (1 + p) for p in daily.TARGETS]
    floor, remaining, sales = stop, 1.0, []
    breakeven = False

    # Entry day, walked bar by bar from the entry bar on -- the ordering daily bars can't see.
    day = intra[(intra["d"] == d) & (intra.index >= k)]
    for n, (_, bar) in enumerate(day.iterrows()):
        if breakeven:
            floor = max(floor, entry)
        o, h, l = float(bar["open"]), float(bar["high"]), float(bar["low"])
        if n > 0 and o <= floor:
            sales.append((o * (1 - daily.SLIP), remaining, "STOP_GAP", i)); remaining = 0; break
        if l <= floor:
            sales.append((floor * (1 - daily.SLIP), remaining, "STOP", i)); remaining = 0; break
        crossed = [t for t in targets if h >= t]
        for t in crossed:
            sell = min(daily.SELL_PER_TARGET, remaining - daily.CORE_PCT)
            if sell <= 1e-9:
                break
            sales.append((t * (1 - daily.SLIP), sell, "TARGET", i)); remaining -= sell
        targets = targets[len(crossed):]
        if crossed:
            breakeven = True
    if remaining > 1e-9:
        c, sma = float(bars.at[i, "close"]), bars.at[i, "sma20"]
        if not pd.isna(sma) and c < sma:
            sales.append((c * (1 - daily.SLIP), remaining, "SMA20_CLOSE", i)); remaining = 0

    # Later days: daily bars, identical to the daily version (stop assumed before targets).
    j = i + 1
    while remaining > 1e-9 and j < len(bars):
        if breakeven:
            floor = max(floor, entry)
        o, h, l, c, sma = (float(bars.at[j, x]) for x in ("open", "high", "low", "close", "sma20"))
        if o <= floor:
            sales.append((o * (1 - daily.SLIP), remaining, "STOP_GAP", j)); remaining = 0; break
        if l <= floor:
            sales.append((floor * (1 - daily.SLIP), remaining, "STOP", j)); remaining = 0; break
        crossed = [t for t in targets if h >= t]
        if crossed:
            gap = o >= crossed[0]
            for t in crossed:
                sell = min(daily.SELL_PER_TARGET, remaining - daily.CORE_PCT)
                if sell <= 1e-9:
                    break
                sales.append(((o if gap else t) * (1 - daily.SLIP), sell, "TARGET", j)); remaining -= sell
            targets = targets[len(crossed):]
            breakeven = True
        if not pd.isna(sma) and c < sma:
            sales.append((c * (1 - daily.SLIP), remaining, "SMA20_CLOSE", j)); remaining = 0; break
        j += 1

    if remaining > 1e-9:
        last = float(bars.at[len(bars) - 1, "close"])
        mtm = sum(p * (px - entry) for px, p, _, _ in sales) + remaining * (last - entry)
        return {**out, "status": "STILL_OPEN", "open_R_mtm": round(mtm / risk, 3)}
    realized = sum(p * (px - entry) for px, p, _, _ in sales) / risk
    return {**out, "status": "OK", "realized_R": round(realized, 3),
            "exit_reason": sales[-1][2], "holding_days": sales[-1][3] - i}


def main():
    m = daily.read_master()
    flags = m[(m["flag_no"] > 0) & (~m["ticker"].isin(daily.EXCLUDE)) & m["r1_price"].notna()
              & (m["setup_confirmed"] >= COVERAGE_START)]
    print(f"{len(flags)} flags, {flags['ticker'].nunique()} tickers in intraday coverage")

    rows, prox, bars_cache = [], [], {}
    for n, f in enumerate(flags.itertuples(), 1):
        if f.ticker not in bars_cache:
            bars_cache[f.ticker] = daily.load_bars(f.ticker)
        bars = bars_cache[f.ticker]
        if bars is None:
            continue
        start = ymd_to_date(f.setup_confirmed) + timedelta(days=1)
        end = ymd_to_date(f.final_flag_end)
        intra = fetch_5min(f.ticker, start, end) if end >= start else pd.DataFrame()
        rows.append(simulate(f, bars, intra) if not intra.empty
                    else {"ticker": f.ticker, "flag_no": f.flag_no, "status": "NO_INTRADAY"})
        prox.append(daily.simulate(f, bars, "mid"))
        if n % 10 == 0:
            print(f"  {n}/{len(flags)}")

    hourly, proxy = pd.DataFrame(rows), pd.DataFrame(prox)
    hourly.to_csv(OUT, index=False)
    print(f"\nhourly status: {hourly['status'].value_counts().to_dict()}")
    print("\n--- 60m ORH entry (real intraday) ---")
    daily.summarize(hourly, "ALL")
    for t in ("HL_FLAG", "LL_RECLAIM"):
        daily.summarize(hourly[hourly["setup_type"] == t], t)
    print("\n--- daily proxy (mid), SAME flags ---")
    daily.summarize(proxy, "ALL")
    for t in ("HL_FLAG", "LL_RECLAIM"):
        daily.summarize(proxy[proxy["setup_type"] == t], t)

    ok = hourly[hourly["status"] == "OK"]
    if len(ok):
        print(f"\nentry fill vs R1: median {ok['fill_above_r1_pct'].median():+.2f}%, "
              f"mean {ok['fill_above_r1_pct'].mean():+.2f}%  (daily proxy fills AT R1 unless gapped)")
        print(f"fills: {ok['fill_reason'].value_counts().to_dict()}")
        print(f"exits: {ok['exit_reason'].value_counts().to_dict()}")
        print(f"stopped out on the entry day: {int((ok['holding_days'] == 0).sum())}/{len(ok)}")
    print(f"\ntrade log: {OUT}")


if __name__ == "__main__":
    main()
