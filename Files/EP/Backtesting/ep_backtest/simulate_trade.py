"""
Single-trade state machine: entry -> initial stop -> position management -> exit -> R.

Data-granularity note (a real design decision, not explicitly pinned down in the frozen
spec -- flagged here deliberately): the initial stop is defined as a hard intrabar
stop-market rule (Section 24), but per Section 78 we only fetch 1-minute bars for the
D0..D+7 entry-search window. For D0..D+7, this simulator checks the stop at 1-minute
resolution (as precise as the spec intends). For any day AFTER D+7 that a still-open
position survives into, there is no cached minute data, so the stop/exit check falls
back to daily-bar approximation (gap-through uses the day's open, trade-through uses
the day's low) -- the same logic, just at daily resolution. This only matters for
strategies whose entry lands late in the D0-D7 window on a stock that then keeps running
for a long time; it should be revisited if that turns out to matter empirically.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import pandas as pd

from . import calendar_utils, config, daily_bars, exits, minute_bars
from .entry import EntryResult, find_entry
from .initial_stop import StopResult, compute_initial_stop


@dataclass
class TradeResult:
    ticker: str
    event_date: date
    entry_type: str
    stop_type: str
    strategy_id: str

    status: str  # config.STATUS_* codes, or "OK" for a fully resolved trade
    entry_status: str

    or_high: Optional[float] = None
    trigger: Optional[float] = None
    entry_timestamp: Optional[object] = None
    entry_day_offset: Optional[int] = None
    entry_fill: Optional[float] = None
    fill_reason: Optional[str] = None

    initial_stop_price: Optional[float] = None
    initial_risk_per_share: Optional[float] = None

    exit_timestamp: Optional[object] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None

    realized_R: Optional[float] = None
    holding_days: Optional[int] = None

    audit_log: list = field(default_factory=list)


def _slip_add(ref_price: float) -> float:
    return ref_price * (1 + config.SLIPPAGE_PCT)


def _slip_sub(ref_price: float) -> float:
    return ref_price * (1 - config.SLIPPAGE_PCT)


def _strategy_id(entry_type: str, stop_type: str) -> str:
    return f"E{entry_type.upper()}__S{stop_type.upper()}"


def simulate_trade_from_data(
    ticker: str,
    d0: date,
    adr14: Optional[float],
    entry_type: str,
    stop_type: str,
    minute_df: pd.DataFrame,
    daily_df: pd.DataFrame,
) -> TradeResult:
    log = []
    strategy_id = _strategy_id(entry_type, stop_type)
    result = TradeResult(
        ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type,
        strategy_id=strategy_id, status="", entry_status="",
    )

    sessions = calendar_utils.sessions_from(d0, config.MAX_ENTRY_DAY_OFFSET + 1)
    log.append(f"{ticker} EP Day 0 = {d0}, strategy = {strategy_id}")
    log.append(f"Entry-valid sessions D0..D+7: {sessions}")

    if minute_df is None or minute_df.empty:
        result.status = config.STATUS_MISSING_MINUTE_DATA
        result.entry_status = config.STATUS_MISSING_MINUTE_DATA
        log.append("No minute bars available -- MISSING_MINUTE_DATA")
        result.audit_log = log
        return result

    try:
        entry = find_entry(minute_df, d0, sessions, entry_type)
    except ValueError as exc:
        result.status = config.STATUS_MISSING_MINUTE_DATA
        result.entry_status = config.STATUS_MISSING_MINUTE_DATA
        log.append(f"Entry search failed: {exc}")
        result.audit_log = log
        return result

    result.or_high = entry.or_high
    result.trigger = entry.trigger
    result.entry_status = entry.entry_status
    log.append(f"D0 {entry_type} OR high = {entry.or_high:.4f}, trigger = {entry.trigger:.4f}")

    if entry.entry_status == config.STATUS_NO_ENTRY:
        result.status = config.STATUS_NO_ENTRY
        log.append(f"No fill through {sessions[-1]} close -- NO_ENTRY")
        result.audit_log = log
        return result

    result.entry_timestamp = entry.entry_timestamp
    result.entry_day_offset = entry.entry_day_offset
    result.entry_fill = entry.entry_fill
    result.fill_reason = entry.fill_reason
    log.append(
        f"Entry: {entry.fill_reason} at {entry.entry_timestamp} "
        f"(day offset D+{entry.entry_day_offset}), fill = {entry.entry_fill:.4f}"
    )

    stop = compute_initial_stop(stop_type, entry, adr14)
    if not stop.valid:
        result.status = stop.reason or config.STATUS_INVALID_STOP_GEOMETRY
        log.append(f"Initial stop invalid: {stop.reason} (stop_price={stop.stop_price})")
        result.audit_log = log
        return result

    result.initial_stop_price = stop.stop_price
    risk = entry.entry_fill - stop.stop_price
    result.initial_risk_per_share = risk
    log.append(f"Initial stop ({stop_type}) = {stop.stop_price:.4f}, 1R/share = {risk:.4f}")

    daily_sma = exits.add_sma10(daily_df)
    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date):
        result.status = config.STATUS_INELIGIBLE_NO_10SMA
        log.append("Fewer than 10 valid closes as of entry day -- INELIGIBLE_NO_10SMA_HISTORY")
        result.audit_log = log
        return result

    exit_ts, exit_ref_price, exit_reason = _run_position_management(
        minute_df, daily_sma, entry, stop.stop_price, sessions, log
    )

    if exit_reason is None:
        result.status = "STILL_OPEN_AT_DATA_END"
        log.append("No exit condition fired before the end of available daily data -- STILL_OPEN_AT_DATA_END")
        result.audit_log = log
        return result

    if exit_reason == "SMA10_EXIT":
        exit_fill = _slip_sub(exit_ref_price)
    else:  # any STOPPED_* variant
        exit_fill = _slip_sub(exit_ref_price)

    result.exit_timestamp = exit_ts
    result.exit_price = round(exit_fill, 4)
    result.exit_reason = exit_reason

    net_pnl_per_share = exit_fill - entry.entry_fill
    result.realized_R = net_pnl_per_share / risk
    exit_date = exit_ts.date() if hasattr(exit_ts, "date") else exit_ts
    result.holding_days = len(calendar_utils.TRADING_DAYS[
        (calendar_utils.TRADING_DAYS.date >= entry.entry_session_date)
        & (calendar_utils.TRADING_DAYS.date <= exit_date)
    ]) - 1

    log.append(f"Exit: {exit_reason} at {exit_ts}, fill = {exit_fill:.4f}")
    log.append(f"Net P&L/share = {net_pnl_per_share:.4f}, Final R = {result.realized_R:.4f}")

    result.status = "OK"
    result.audit_log = log
    return result


def _run_position_management(minute_df, daily_sma, entry: EntryResult, stop_price, sessions, log):
    """Returns (exit_timestamp, exit_reference_price, exit_reason) or (None, None, None)."""
    remaining_days = [d for d in sessions if d >= entry.entry_session_date]

    for day in remaining_days:
        day_bars = minute_df[minute_df["session_date"] == day].sort_values("dt_et").reset_index(drop=True)
        if day == entry.entry_session_date:
            day_bars = day_bars[day_bars["dt_et"] >= entry.entry_timestamp].reset_index(drop=True)
            entry_bar_pos = 0
        else:
            entry_bar_pos = None

        for j, bar in day_bars.iterrows():
            if entry_bar_pos is not None and j == entry_bar_pos:
                if bar["low"] <= stop_price:
                    log.append(
                        f"{bar['dt_et']}: entry bar's own low ({bar['low']:.4f}) <= stop "
                        f"({stop_price:.4f}) -- same-bar ambiguity, adverse assumption applied"
                    )
                    return bar["dt_et"], stop_price, "STOPPED_SAME_BAR_AS_ENTRY"
                continue
            if bar["open"] <= stop_price:
                log.append(f"{bar['dt_et']}: session open ({bar['open']:.4f}) already through stop -- gap-through stop")
                return bar["dt_et"], bar["open"], "STOPPED_GAP_THROUGH"
            if bar["low"] <= stop_price:
                return bar["dt_et"], stop_price, "STOPPED_TRADE_THROUGH"

        drow = daily_sma[daily_sma["date"] == day]
        if drow.empty or pd.isna(drow["sma10"].iloc[0]):
            continue
        close, sma10 = float(drow["close"].iloc[0]), float(drow["sma10"].iloc[0])
        if close < sma10:
            log.append(f"{day}: close {close:.4f} < 10SMA {sma10:.4f} -- SMA10_EXIT")
            return day, close, "SMA10_EXIT"

    # Ran out of cached minute-bar coverage (past D+7) without a resolved exit --
    # fall back to daily-bar approximation. See module docstring.
    log.append(f"Position survived through {sessions[-1]} (end of cached minute window) -- switching to daily-bar approximation")
    after = daily_sma[daily_sma["date"] > sessions[-1]].sort_values("date")
    for _, row in after.iterrows():
        if row["open"] <= stop_price:
            return row["date"], row["open"], "STOPPED_GAP_THROUGH_DAILY_APPROX"
        if row["low"] <= stop_price:
            return row["date"], stop_price, "STOPPED_TRADE_THROUGH_DAILY_APPROX"
        if pd.notna(row["sma10"]) and row["close"] < row["sma10"]:
            return row["date"], row["close"], "SMA10_EXIT"

    return None, None, None


def simulate_trade(ticker: str, d0: date, adr14: Optional[float], entry_type: str, stop_type: str,
                    refresh: bool = False) -> TradeResult:
    """Convenience wrapper: pulls/caches data itself. Used for one-off verification."""
    minute_df = minute_bars.get_event_window_minute_bars(ticker, d0, refresh=refresh)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, d0, refresh=refresh)
    return simulate_trade_from_data(ticker, d0, adr14, entry_type, stop_type, minute_df, daily_df)
