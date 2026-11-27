"""
Quick backtest of the EP "4th chosen one" exit rules on the hand-annotated HTF flags,
using DAILY bars from the TradingView exports in chart_exports/.

Strategy (mirrors Files/EP/Backtesting/ep_backtest/run_4th_chosen_on_htf.py):
  entry  : break of R1. The chosen one buys a 60-minute opening-range-high break, which
           needs intraday bars; the free Massive tier only serves those back to ~late 2024,
           so this is the DAILY PROXY -- first session after setup_confirmed whose high
           trades through R1, filled at R1, or at the open if it gaps above R1 (an ORH break
           on a gap day fills higher too). Window: through final_flag_end. Entries start
           the session AFTER setup_confirmed because confirmation is judged on that day's
           close -- the framework doc's no-lookahead rule.
  stop   : entry * (1 - 0.5 * ADR14), ADR14 = (mean high - mean low) over the 14 sessions
           before entry, divided by the prior close (EP's adr14_pregap formula).
  targets: 10% of the original position sold at each of +20/27.5/35/42.5/50% (start20
           ladder, equal depletion, 50% non-core). Stop moves to breakeven after the first
           sale.
  core   : remaining position exits at the close of the first day that closes below the
           20-day SMA.
  costs  : 0.1% slippage on entry and every exit (EP config.SLIPPAGE_PCT).

Daily bars can't order events inside a day. Where one bar touches both the stop and a
target, the STOP is assumed first (pessimistic). The entry day is the hard case: a breakout
day usually opens BELOW R1 and rallies through it, so its low printed before the buy, and
a ~1 ADR range puts that pre-entry low under a 0.5 ADR stop most of the time. Checking it
naively stops out ~90% of trades on day 0 (verified 2026-10-09). --entry-day picks the
treatment:
  pessimistic: entry-day low counts (biased toward losses)
  mid        : low counts only on a gap above R1 (bought at the open, so the whole range is
               post-entry); on a break-through day only a close back under the stop counts
  optimistic : entry-day low ignored (biased toward wins)

    python quick_backtest_chosen_one.py                  # mid (default)
    python quick_backtest_chosen_one.py --entry-day pessimistic
"""
import argparse
import os

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
MASTER = os.path.join(HERE, "htf_annotations_master.csv")
EXPORTS = os.path.join(HERE, "chart_exports")
OUT = os.path.join(HERE, "quick_backtest_chosen_one_trades.csv")

SLIP = 0.001
STOP_ADR_MULT = 0.50
TARGETS = [0.20, 0.275, 0.35, 0.425, 0.50]
CORE_PCT = 0.50
SELL_PER_TARGET = (1 - CORE_PCT) / len(TARGETS)
# Charted on a different company than the scanner's (export prefix shows a foreign listing;
# daily returns don't track the P123 bars): AGN = Aegon (Euronext), not Allergan;
# ARCH = Oslo listing, not Arch Resources; ARNA = Indonesia (IDX), not Arena Pharmaceuticals;
# BKS = London listing, not Barnes & Noble; CUB = NSE India (City Union Bank), not Cubic Corp.;
# CNR = TSX (Canadian National Railway), not NYSE:CNR (Core Natural Resources, ex-CONSOL).
# (BMO's Toronto chart is the same company, kept; CIS/CIT/CSH on German listings and ATAI on
# CAPITALCOM have flag dates matching the scanner's hit windows, kept.)
EXCLUDE = {"AGN", "ARCH", "ARNA", "BKS", "CUB", "CNR"}
# Single flags the user re-reviewed as "not a flag" (code N in the Google Sheet), written by
# sync_sheet_reviews.py. Dropped from every backtest; flag numbers are not renumbered.
DROPPED = os.path.join(HERE, "htf_dropped_flags.csv")


def read_master() -> pd.DataFrame:
    """The annotations master minus wrong-listing tickers and dropped flags."""
    m = pd.read_csv(MASTER)
    m = m[~m["ticker"].isin(EXCLUDE)]
    if os.path.exists(DROPPED):
        d = pd.read_csv(DROPPED)
        gone = set(zip(d.ticker, d.flag_no))
        m = m[[k not in gone for k in zip(m.ticker, m.flag_no)]]
    return m


def load_bars(ticker: str) -> pd.DataFrame:
    f = [x for x in os.listdir(EXPORTS) if x.rsplit("_", 1)[0] == ticker]
    if not f:
        return None
    b = pd.read_csv(os.path.join(EXPORTS, sorted(f)[-1]))
    b["d"] = pd.to_datetime(b["time"], unit="s").dt.strftime("%Y%m%d").astype(int)
    b = b[["d", "open", "high", "low", "close"]].dropna().sort_values("d").reset_index(drop=True)
    b["sma20"] = b["close"].rolling(20).mean()
    return b


def simulate(flag, bars: pd.DataFrame, entry_mode: str) -> dict:
    out = {"ticker": flag.ticker, "flag_no": flag.flag_no, "setup_type": flag.setup_type,
           "setup_confirmed": flag.setup_confirmed, "final_flag_end": flag.final_flag_end,
           "r1_price": flag.r1_price}
    if pd.isna(flag.r1_price):
        return {**out, "status": "NO_LEVEL"}

    r1 = float(flag.r1_price)
    window = bars[(bars["d"] > flag.setup_confirmed) & (bars["d"] <= flag.final_flag_end)]
    hit = window[window["high"] >= r1]
    if hit.empty:
        return {**out, "status": "NO_ENTRY"}

    i = int(hit.index[0])
    if i < 15:
        return {**out, "status": "NO_HISTORY"}
    entry_ref = max(r1, float(bars.at[i, "open"]))
    entry = entry_ref * (1 + SLIP)

    prior = bars.iloc[i - 14:i]
    adr = (prior["high"].mean() - prior["low"].mean()) / float(bars.at[i - 1, "close"])
    stop = entry * (1 - STOP_ADR_MULT * adr)
    risk = entry - stop
    out.update(entry_date=int(bars.at[i, "d"]), entry_fill=round(entry, 4),
               gapped_above=bool(bars.at[i, "open"] > r1), adr14=round(adr, 4),
               stop=round(stop, 4))

    targets = [entry * (1 + p) for p in TARGETS]
    floor = stop
    remaining, sales = 1.0, []
    breakeven_from = None   # bar index from which the floor sits at breakeven

    for j in range(i, len(bars)):
        o, h, l, c, sma = (float(bars.at[j, k]) for k in ("open", "high", "low", "close", "sma20"))
        if breakeven_from is not None and j >= breakeven_from:
            floor = max(floor, entry)
        entry_day = j == i

        if not entry_day and o <= floor:                               # gap through stop
            sales.append((o * (1 - SLIP), remaining, "STOP_GAP", j))
            remaining = 0
            break
        if entry_day and entry_mode == "mid" and o < r1:
            # Broke up through R1 intraday: the day's low most likely printed BEFORE the
            # buy, so only a close back under the stop counts as a same-day stop-out.
            stopped = c <= floor
        elif entry_day and entry_mode == "optimistic":
            stopped = False
        else:
            stopped = l <= floor                                         # assumed before targets
        if stopped:
            sales.append((floor * (1 - SLIP), remaining, "STOP", j))
            remaining = 0
            break

        crossed = [t for t in targets if h >= t]
        if crossed:
            gap = (not entry_day) and o >= crossed[0]
            for t in crossed:
                sell = min(SELL_PER_TARGET, remaining - CORE_PCT)
                if sell <= 1e-9:
                    break
                fill = (o if gap else t) * (1 - SLIP)
                sales.append((fill, sell, "TARGET_GAP" if gap else "TARGET", j))
                remaining -= sell
            targets = targets[len(crossed):]
            if breakeven_from is None:
                breakeven_from = j + 1

        if not pd.isna(sma) and c < sma:                               # 20-day SMA close exit
            sales.append((c * (1 - SLIP), remaining, "SMA20_CLOSE", j))
            remaining = 0
            break

    if remaining > 1e-9:
        last = float(bars.at[len(bars) - 1, "close"])
        mtm = sum(p * (px - entry) for px, p, _, _ in sales) + remaining * (last - entry)
        return {**out, "status": "STILL_OPEN", "open_R_mtm": round(mtm / risk, 3),
                "n_sales": len(sales)}

    realized = sum(p * (px - entry) for px, p, _, _ in sales) / risk
    peak = float(bars.loc[i:sales[-1][3], "high"].max())
    return {**out, "status": "OK", "realized_R": round(realized, 3),
            "exit_date": int(bars.at[sales[-1][3], "d"]), "exit_reason": sales[-1][2],
            "n_sales": len(sales), "holding_days": sales[-1][3] - i,
            "max_favorable_R": round((peak - entry) / risk, 3)}


def summarize(df: pd.DataFrame, label: str):
    ok = df[df["status"] == "OK"]
    n = len(ok)
    if n == 0:
        print(f"  {label}: no completed trades")
        return
    w, lo = ok[ok["realized_R"] > 0]["realized_R"], ok[ok["realized_R"] <= 0]["realized_R"]
    pf = w.sum() / abs(lo.sum()) if len(lo) and lo.sum() != 0 else float("inf")
    print(f"  {label:12s} n={n:3d}  win {len(w)/n*100:4.1f}%  avgW {w.mean():+.2f}R  "
          f"avgL {lo.mean():+.2f}R  PF {pf:4.2f}  EV {ok['realized_R'].mean():+.3f}R  "
          f"total {ok['realized_R'].sum():+6.1f}R  median {ok['realized_R'].median():+.2f}R")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry-day", choices=["pessimistic", "mid", "optimistic"], default="mid",
                    help="how the entry day's own low is treated -- daily bars can't tell whether "
                         "it printed before or after the buy")
    args = ap.parse_args()

    m = read_master()
    flags = m[(m["flag_no"] > 0) & (~m["ticker"].isin(EXCLUDE))]
    cache, rows = {}, []
    for f in flags.itertuples():
        if f.ticker not in cache:
            cache[f.ticker] = load_bars(f.ticker)
        bars = cache[f.ticker]
        rows.append({"ticker": f.ticker, "status": "NO_BARS"} if bars is None
                    else simulate(f, bars, args.entry_day))

    df = pd.DataFrame(rows)
    df.to_csv(OUT, index=False)
    print(f"{len(df)} flags | entry-day stop check: {args.entry_day}")
    print(f"status: {df['status'].value_counts().to_dict()}\n")
    summarize(df, "ALL")
    for t in ("HL_FLAG", "LL_RECLAIM"):
        summarize(df[df["setup_type"] == t], t)
    ok = df[df["status"] == "OK"]
    if len(ok):
        print(f"\n  exit reasons: {ok['exit_reason'].value_counts().to_dict()}")
        print(f"  median hold {int(ok['holding_days'].median())} sessions, "
              f"entries gapped above R1: {int(ok['gapped_above'].sum())}/{len(ok)}")
    op = df[df["status"] == "STILL_OPEN"]
    if len(op):
        print(f"  still open: {len(op)} (mark-to-market {op['open_R_mtm'].sum():+.1f}R, not in stats)")
    print(f"\ntrade log: {OUT}")


if __name__ == "__main__":
    main()
