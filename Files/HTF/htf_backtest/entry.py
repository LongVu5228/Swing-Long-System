"""
HTF entry search -- all 9 entry types (§12), each returned as ep_backtest's EntryResult so EP's
tested position management (trailing stops, staged partials, MFE) runs on it unchanged.

Window: sessions strictly after setup_confirmed (confirmation is judged on that day's close --
no-lookahead rule from the daily backtest) through final_flag_end, R1 = the flag's line of
least resistance. Unlike EP (one fixed D0 opening range), HTF has no event day, so every
session in the window gets its OWN opening range.

Opening-range entries (1m..60m): trigger = round_tick(max(that session's OR high + 1 tick, R1)).
  Fills only strictly after the OR window closes (EP Section 16), at the trigger or at the bar's
  open if it gaps over (EP Section 15). The first session that fills is the entry.
r1_cross: a buy-stop resting at R1 + 1 tick from the first eligible session's open -- the first
  1-minute bar to trade through it (or gap over it) fills. No opening-range wait.
close_above_r1: the first eligible session that CLOSES above R1; filled at that close (modeled
  as the last regular-session minute bar, so it flows through the same minute-based engine).
next_open_after_close: the session after the first close above R1; filled at its open.

Every EntryResult carries lod_known_at_entry and trigger_candle_low_known_at_entry computed only
from bars up to and including the entry bar (EP Sections 21-22, 79). For the two daily entries:
close entry -> both = that session's full low (known at the close); next-open entry -> both =
the signal session's low (the open bar alone would put the stop at the entry price).
"""

from typing import Optional

import pandas as pd

from . import config
from ep_backtest.entry import EntryResult  # noqa: E402  (path set up by config)
from ep_backtest import config as ep_config  # noqa: E402

VALID, NO_ENTRY = ep_config.STATUS_VALID_TRADE, ep_config.STATUS_NO_ENTRY


def round_tick(price: float) -> float:
    return round(round(price / config.TICK_SIZE) * config.TICK_SIZE, 2)


def _session_open(day_bars: pd.DataFrame, session_date) -> pd.Timestamp:
    return pd.Timestamp(session_date).tz_localize(config.ET) + pd.Timedelta(hours=9, minutes=30)


def _fill(bar, trigger: float):
    """(reference price, reason) if this bar fills a buy-stop at trigger, else None."""
    if bar.open > trigger:
        return float(bar.open), "gap_through"
    if bar.high >= trigger:
        return trigger, "normal_trade_through"
    return None


def _result(entry_type, sessions, day_bars, k, bar, ref, reason, or_high, trigger, minutes) -> EntryResult:
    so_far = day_bars[day_bars.dt_et <= bar.dt_et]
    lod = float(so_far.low.min())
    open_ts = _session_open(day_bars, bar.session_date)
    bucket = int((bar.dt_et - open_ts).total_seconds() // 60 // minutes)
    b0 = open_ts + pd.Timedelta(minutes=bucket * minutes)
    tc = so_far[so_far.dt_et >= b0]
    return EntryResult(
        entry_status=VALID, or_high=or_high, trigger=trigger, entry_timestamp=bar.dt_et,
        entry_day_offset=sessions.index(bar.session_date), entry_session_date=bar.session_date,
        entry_fill=round(ref * (1 + config.SLIPPAGE_PCT), 4), fill_reason=reason, entry_bar_index=k,
        lod_known_at_entry=lod, trigger_candle_low_known_at_entry=float(tc.low.min()),
    )


def find_entry(entry_type: str, minute_df: pd.DataFrame, daily_sma: pd.DataFrame, r1: float,
               setup_confirmed, final_flag_end) -> EntryResult:
    """minute_df: regular-session 1-min bars (dt_et, session_date, ...) covering the window.
    daily_sma: EP-schema daily frame (date as datetime.date). Dates passed as datetime.date."""
    elig = sorted(d for d in minute_df.session_date.unique() if setup_confirmed < d <= final_flag_end)
    sessions = list(sorted(minute_df.session_date.unique()))
    none = EntryResult(entry_status=NO_ENTRY, or_high=float("nan"), trigger=round_tick(r1 + config.TICK_SIZE))
    if not elig:
        return none

    if entry_type in config.ORB_ABOVE_MINUTES:
        # user's rule (2026-11-22): this session's N-min opening range; ONLY if its high is above R1,
        # buy-stop at OR high + 1 tick, live until the close. OR high <= R1 -> no order that day.
        minutes = config.ORB_ABOVE_MINUTES[entry_type]
        for d in elig:
            day = minute_df[minute_df.session_date == d]
            open_ts = _session_open(day, d)
            rng = day[day.dt_et < open_ts + pd.Timedelta(minutes=minutes)]
            if rng.empty:
                continue
            or_high = float(rng.high.max())
            if or_high <= r1:
                continue
            trigger = round_tick(or_high + config.TICK_SIZE)
            cand = day[day.dt_et >= open_ts + pd.Timedelta(minutes=minutes)]
            hit = (cand.open.to_numpy() > trigger) | (cand.high.to_numpy() >= trigger)
            if hit.any():
                k = cand.index[int(hit.argmax())]
                bar = day.loc[k]
                ref, reason = _fill(bar, trigger)
                return _result(entry_type, sessions, day, k, bar, ref, reason, or_high, trigger, minutes)
        return none

    if entry_type in config.XCROSS_MINUTES:
        # user idea (2026-11-24): each session, the first N-min candle (buckets from 9:30) that trades above R1 is the
        # signal candle; after it closes, buy-stop at its high + 1 tick, live until the close. No fill -> the next
        # session starts fresh with its own first candle above R1. A cross in the day's last candle cannot fill.
        minutes = config.XCROSS_MINUTES[entry_type]
        for d in elig:
            day = minute_df[minute_df.session_date == d]
            open_ts = _session_open(day, d)
            above = day[day.high > r1]
            if above.empty:
                continue
            b0 = open_ts + pd.Timedelta(minutes=int((above.dt_et.iloc[0] - open_ts).total_seconds() // 60 // minutes) * minutes)
            b1 = b0 + pd.Timedelta(minutes=minutes)
            sig_high = float(day[(day.dt_et >= b0) & (day.dt_et < b1)].high.max())
            trigger = round_tick(sig_high + config.TICK_SIZE)
            cand = day[day.dt_et >= b1]
            hit = (cand.open.to_numpy() > trigger) | (cand.high.to_numpy() >= trigger)
            if hit.any():
                k = cand.index[int(hit.argmax())]
                bar = day.loc[k]
                ref, reason = _fill(bar, trigger)
                return _result(entry_type, sessions, day, k, bar, ref, reason, sig_high, trigger, minutes)
        return none

    if entry_type in config.BARCLOSE_MINUTES:
        # original idea: the first N-min bar (buckets from 9:30) that CLOSES above R1, any time of day,
        # any session in the window -> bought at that bar's close. The fill happens at the bar's END, so
        # the entry timestamp is the last minute + 1 min: the engine scans stops from entry_timestamp on,
        # and that bar's earlier low must not count against the stop.
        minutes = config.BARCLOSE_MINUTES[entry_type]
        for d in elig:
            day = minute_df[minute_df.session_date == d]
            open_ts = _session_open(day, d)
            b = ((day.dt_et - open_ts).dt.total_seconds() // 60 // minutes).astype(int)
            last_close = day.groupby(b.to_numpy()).close.last()
            above = last_close[last_close > r1]
            if above.empty:
                continue
            bk = int(above.index[0])
            k = day.index[b.to_numpy() == bk][-1]
            bar = day.loc[k]
            res = _result(entry_type, sessions, day, k, bar, float(bar.close), "bar_close", float("nan"),
                          round_tick(r1), minutes)
            res.entry_timestamp = bar.dt_et + pd.Timedelta(minutes=1)
            return res
        return none

    if entry_type in config.OR_MINUTES or entry_type == "r1_cross":
        minutes = config.OR_MINUTES.get(entry_type, 1)
        for d in elig:
            day = minute_df[minute_df.session_date == d]
            open_ts = _session_open(day, d)
            if entry_type == "r1_cross":
                or_high, trigger, start = float("nan"), round_tick(r1 + config.TICK_SIZE), open_ts
            else:
                rng = day[day.dt_et < open_ts + pd.Timedelta(minutes=minutes)]
                if rng.empty:
                    continue
                or_high = float(rng.high.max())
                trigger = round_tick(max(or_high + config.TICK_SIZE, r1 + config.TICK_SIZE))
                start = open_ts + pd.Timedelta(minutes=minutes)
            cand = day[day.dt_et >= start]
            hit = (cand.open.to_numpy() > trigger) | (cand.high.to_numpy() >= trigger)   # vectorized
            if hit.any():
                k = cand.index[int(hit.argmax())]
                bar = day.loc[k]
                ref, reason = _fill(bar, trigger)
                return _result(entry_type, sessions, day, k, bar, ref, reason, or_high, trigger, minutes)
        return none

    # daily entries: first eligible session closing above R1
    closes = daily_sma.set_index("date").close
    signal = next((d for d in elig if d in closes.index and closes[d] > r1), None)
    if signal is None:
        return none
    if entry_type == "close_above_r1":
        day = minute_df[minute_df.session_date == signal]
        k = day.index[-1]
        bar = day.loc[k]
        res = _result(entry_type, sessions, day, k, bar, float(closes[signal]), "close_above_r1",
                      float("nan"), round_tick(r1), 390)
        res.lod_known_at_entry = res.trigger_candle_low_known_at_entry = float(day.low.min())
        return res
    # next_open_after_close
    later = [d for d in sessions if d > signal]
    if not later:
        return none
    day = minute_df[minute_df.session_date == later[0]]
    k = day.index[0]
    bar = day.loc[k]
    sig_low = float(minute_df[minute_df.session_date == signal].low.min())
    res = _result(entry_type, sessions, day, k, bar, float(bar.open), "next_open", float("nan"), round_tick(r1), 1)
    res.lod_known_at_entry = res.trigger_candle_low_known_at_entry = sig_low
    return res
