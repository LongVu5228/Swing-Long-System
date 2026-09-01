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

import numpy as np
import pandas as pd

from . import calendar_utils, config, daily_bars, exits, minute_bars, trade_metrics
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

    trail_type: Optional[str] = None  # V2 only; None for V1 trades

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

    max_favorable_R: Optional[float] = None
    exit_efficiency: Optional[float] = None

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
    """
    Convenience path for a single (entry_type, stop_type): finds entry and computes the
    10SMA series itself. For batch runs across many stop types (or many entry types) on
    the same event, prefer find_entry()/exits.add_sma10() once up front and call
    simulate_with_entry() per combination instead -- see run_batch.run_all_72, which
    exists specifically because re-deriving the entry search (a per-bar Python loop) and
    the 10SMA rolling window on every one of 72 combinations made a full-universe run
    ~30x slower than necessary.
    """
    sessions = calendar_utils.sessions_from(d0, config.MAX_ENTRY_DAY_OFFSET + 1)

    if minute_df is None or minute_df.empty:
        result = TradeResult(
            ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type,
            strategy_id=_strategy_id(entry_type, stop_type),
            status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
            audit_log=[f"{ticker} EP Day 0 = {d0}", "No minute bars available -- MISSING_MINUTE_DATA"],
        )
        return result

    try:
        entry = find_entry(minute_df, d0, sessions, entry_type)
    except ValueError as exc:
        result = TradeResult(
            ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type,
            strategy_id=_strategy_id(entry_type, stop_type),
            status=config.STATUS_MISSING_MINUTE_DATA, entry_status=config.STATUS_MISSING_MINUTE_DATA,
            audit_log=[f"{ticker} EP Day 0 = {d0}", f"Entry search failed: {exc}"],
        )
        return result

    daily_sma = exits.add_sma10(daily_df)
    return simulate_with_entry(ticker, d0, adr14, entry_type, stop_type, entry, minute_df, daily_sma, sessions)


def simulate_with_entry(
    ticker: str,
    d0: date,
    adr14: Optional[float],
    entry_type: str,
    stop_type: str,
    entry: EntryResult,
    minute_df: pd.DataFrame,
    daily_sma: pd.DataFrame,
    sessions: list,
) -> TradeResult:
    """
    Runs stop -> position management -> R for an ALREADY-COMPUTED entry search and an
    already-SMA10-augmented daily frame. Both of those only depend on entry_type (not
    stop_type), so a caller sweeping all 12 stop types for one entry_type should compute
    them once and reuse them across all 12 calls.
    """
    log = []
    strategy_id = _strategy_id(entry_type, stop_type)
    result = TradeResult(
        ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type,
        strategy_id=strategy_id, status="", entry_status=entry.entry_status,
        or_high=entry.or_high, trigger=entry.trigger,
    )
    log.append(f"{ticker} EP Day 0 = {d0}, strategy = {strategy_id}")
    log.append(f"Entry-valid sessions D0..D+7: {sessions}")
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

    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date):
        result.status = config.STATUS_INELIGIBLE_NO_10SMA
        log.append("Fewer than 10 valid closes as of entry day -- INELIGIBLE_NO_10SMA_HISTORY")
        result.audit_log = log
        return result

    exit_ts, exit_ref_price, exit_reason = _run_position_management(
        minute_df, daily_sma, entry, stop.stop_price, sessions, log
    )
    result = _finalize_exit(result, entry, risk, exit_ts, exit_ref_price, exit_reason, log)
    return _attach_exit_efficiency(result, minute_df, daily_sma, entry, risk)


def _finalize_exit(result: TradeResult, entry: EntryResult, risk: float, exit_ts, exit_ref_price,
                    exit_reason, log: list) -> TradeResult:
    """Shared tail: turn a (exit_ts, exit_ref_price, exit_reason) triple into R + the
    rest of the TradeResult. Used by both V1's simulate_with_entry and V2's
    simulate_v2_with_entry -- they differ only in how the exit is found, not in how the
    exit is turned into R once found."""
    if exit_reason is None:
        result.status = "STILL_OPEN_AT_DATA_END"
        log.append("No exit condition fired before the end of available daily data -- STILL_OPEN_AT_DATA_END")
        result.audit_log = log
        return result

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


def _attach_exit_efficiency(result: TradeResult, minute_df: pd.DataFrame, daily_sma: pd.DataFrame,
                             entry: EntryResult, risk: float) -> TradeResult:
    """Shared tail for V1/V2: post-hoc MFE / exit-efficiency, no effect on the exit
    decision itself. Only meaningful for a fully resolved ("OK") trade."""
    if result.status != "OK":
        return result

    result.max_favorable_R = trade_metrics.compute_max_favorable_r(
        minute_df, daily_sma, entry.entry_timestamp, entry.entry_session_date, result.exit_timestamp,
        entry.entry_fill, risk,
    )
    result.exit_efficiency = trade_metrics.compute_exit_efficiency(result.realized_R, result.max_favorable_R)
    return result


def simulate_v2_with_entry(
    ticker: str,
    d0: date,
    adr14: Optional[float],
    entry_type: str,
    stop_type: str,
    trail_type: str,
    entry: EntryResult,
    minute_df: pd.DataFrame,
    daily_sma: pd.DataFrame,
    sessions: list,
) -> TradeResult:
    """
    V2 counterpart to simulate_with_entry: same entry/initial-stop handling, but position
    management is one of the 6 Section 43 trailing-stop types instead of the fixed
    close-below-10SMA rule. daily_sma must already have both sma10 and sma20 columns
    (exits.add_sma10 provides both).
    """
    from . import trailing_stops  # local import: avoids a module-level cycle risk if
    # trailing_stops ever needs anything from simulate_trade in the future.

    log = []
    strategy_id = f"{_strategy_id(entry_type, stop_type)}__T{trail_type.upper()}"
    result = TradeResult(
        ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type,
        strategy_id=strategy_id, trail_type=trail_type, status="", entry_status=entry.entry_status,
        or_high=entry.or_high, trigger=entry.trigger,
    )
    log.append(f"{ticker} EP Day 0 = {d0}, strategy = {strategy_id}")
    log.append(f"Entry-valid sessions D0..D+7: {sessions}")
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

    ma_window = trailing_stops.ma_window_for(trail_type)
    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date, window=ma_window):
        result.status = config.STATUS_INELIGIBLE_NO_10SMA
        log.append(f"Fewer than {ma_window} valid closes as of entry day -- INELIGIBLE_NO_MA_HISTORY")
        result.audit_log = log
        return result

    if trailing_stops.is_close_based(trail_type):
        exit_ts, exit_ref_price, exit_reason = _run_position_management(
            minute_df, daily_sma, entry, stop.stop_price, sessions, log,
            ma_col=trailing_stops.ma_column_for(trail_type),
        )
    else:
        level_series = trailing_stops.level_series_for(
            trail_type, daily_sma, stop.stop_price, entry.entry_session_date, reference_price=entry.entry_fill
        )

        # Same invalid-geometry guard Section 31 already applies to the initial stop
        # (stop >= entry_fill is nonsensical), extended to the trailing level actually
        # in force on the entry day. Needed because "touch" uses the prior day's
        # finalized MA (Section 44) -- after a steep enough decline, that MA can still
        # sit ABOVE the entry price (it hasn't caught down to the crash yet), which
        # produced a real bug: the same-bar-adverse rule then used that unreachable
        # level as an exit FILL PRICE, fabricating gains at a price the stock never
        # actually traded (confirmed on CCL 2020-03-20: entry $12.22, fabricated "exit"
        # at $25.64 -- the prior day's 20MA, still elevated from the pre-crash price).
        entry_day_level = level_series[daily_sma["date"] == entry.entry_session_date]
        if not entry_day_level.empty and float(entry_day_level.iloc[0]) >= entry.entry_fill:
            result.status = config.STATUS_INVALID_STOP_GEOMETRY
            log.append(
                f"Trailing level on entry day ({float(entry_day_level.iloc[0]):.4f}) >= "
                f"entry fill ({entry.entry_fill:.4f}) -- INVALID_STOP_GEOMETRY"
            )
            result.audit_log = log
            return result

        exit_ts, exit_ref_price, exit_reason = trailing_stops.run_level_based_position_management(
            minute_df, daily_sma, entry, level_series, sessions, log
        )

    result = _finalize_exit(result, entry, risk, exit_ts, exit_ref_price, exit_reason, log)
    return _attach_exit_efficiency(result, minute_df, daily_sma, entry, risk)


@dataclass
class TradeResultV3:
    ticker: str
    event_date: date
    entry_type: str
    stop_type: str
    trail_type: str
    target_pct: float
    core_pct: float
    strategy_id: str

    status: str
    entry_status: str

    entry_timestamp: Optional[object] = None
    entry_day_offset: Optional[int] = None
    entry_fill: Optional[float] = None
    initial_stop_price: Optional[float] = None
    initial_risk_per_share: Optional[float] = None

    partial_timestamp: Optional[object] = None
    partial_price: Optional[float] = None
    partial_reason: Optional[str] = None

    core_exit_timestamp: Optional[object] = None
    core_exit_price: Optional[float] = None
    core_exit_reason: Optional[str] = None

    realized_R: Optional[float] = None
    holding_days: Optional[int] = None

    max_favorable_R: Optional[float] = None
    exit_efficiency: Optional[float] = None

    audit_log: list = field(default_factory=list)


def _strategy_id_v3(entry_type: str, stop_type: str, trail_type: str, target_pct: float, core_pct: float) -> str:
    return f"{_strategy_id(entry_type, stop_type)}__T{trail_type.upper()}__X{target_pct*100:g}__C{core_pct*100:g}"


def simulate_v3_with_entry(
    ticker: str, d0: date, adr14: Optional[float], entry_type: str, stop_type: str, trail_type: str,
    target_pct: float, core_pct: float, entry: EntryResult, minute_df: pd.DataFrame, daily_sma: pd.DataFrame,
    sessions: list,
) -> TradeResultV3:
    """V3: entry/initial-stop exactly like V1/V2, then partial_taking.run_v3_position_management
    for the two-phase (partial + core) position management."""
    from . import partial_taking, trailing_stops  # local import: avoids a module import cycle

    log = []
    strategy_id = _strategy_id_v3(entry_type, stop_type, trail_type, target_pct, core_pct)
    result = TradeResultV3(
        ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type, trail_type=trail_type,
        target_pct=target_pct, core_pct=core_pct, strategy_id=strategy_id, status="", entry_status=entry.entry_status,
    )
    log.append(f"{ticker} EP Day 0 = {d0}, strategy = {strategy_id}")

    if entry.entry_status == config.STATUS_NO_ENTRY:
        result.status = config.STATUS_NO_ENTRY
        result.audit_log = log
        return result

    result.entry_timestamp = entry.entry_timestamp
    result.entry_day_offset = entry.entry_day_offset
    result.entry_fill = entry.entry_fill
    log.append(f"Entry: {entry.fill_reason} at {entry.entry_timestamp}, fill = {entry.entry_fill:.4f}")

    stop = compute_initial_stop(stop_type, entry, adr14)
    if not stop.valid:
        result.status = stop.reason or config.STATUS_INVALID_STOP_GEOMETRY
        log.append(f"Initial stop invalid: {stop.reason}")
        result.audit_log = log
        return result

    result.initial_stop_price = stop.stop_price
    result.initial_risk_per_share = entry.entry_fill - stop.stop_price
    log.append(f"Initial stop ({stop_type}) = {stop.stop_price:.4f}")

    ma_window = trailing_stops.ma_window_for(trail_type)
    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date, window=ma_window):
        result.status = config.STATUS_INELIGIBLE_NO_10SMA
        log.append(f"Fewer than {ma_window} valid closes as of entry day -- INELIGIBLE_NO_MA_HISTORY")
        result.audit_log = log
        return result

    v3 = partial_taking.run_v3_position_management(
        minute_df, daily_sma, entry, stop.stop_price, entry.entry_fill, trail_type, target_pct, core_pct,
        sessions, log,
    )

    result.status = v3.status
    result.partial_timestamp = v3.partial_timestamp
    result.partial_price = v3.partial_price
    result.partial_reason = v3.partial_reason
    result.core_exit_timestamp = v3.core_exit_timestamp
    result.core_exit_price = v3.core_exit_price
    result.core_exit_reason = v3.core_exit_reason
    result.realized_R = v3.realized_R
    result.audit_log = log + v3.audit_log

    if result.status == "OK" and result.core_exit_timestamp is not None:
        exit_date = result.core_exit_timestamp.date() if hasattr(result.core_exit_timestamp, "date") \
            else result.core_exit_timestamp
        result.holding_days = len(calendar_utils.TRADING_DAYS[
            (calendar_utils.TRADING_DAYS.date >= entry.entry_session_date)
            & (calendar_utils.TRADING_DAYS.date <= exit_date)
        ]) - 1

        result.max_favorable_R = trade_metrics.compute_max_favorable_r(
            minute_df, daily_sma, entry.entry_timestamp, entry.entry_session_date, result.core_exit_timestamp,
            entry.entry_fill, result.initial_risk_per_share,
        )
        result.exit_efficiency = trade_metrics.compute_exit_efficiency(result.realized_R, result.max_favorable_R)

    return result


@dataclass
class TradeResultMultiV3:
    ticker: str
    event_date: date
    entry_type: str
    stop_type: str
    trail_type: str
    sell_style: str
    target_ladder: str
    core_pct: float
    strategy_id: str

    status: str
    entry_status: str

    entry_timestamp: Optional[object] = None
    entry_day_offset: Optional[int] = None
    entry_fill: Optional[float] = None
    initial_stop_price: Optional[float] = None

    n_sales: int = 0
    first_sale_timestamp: Optional[object] = None
    first_sale_price: Optional[float] = None
    first_sale_reason: Optional[str] = None
    last_sale_timestamp: Optional[object] = None
    last_sale_price: Optional[float] = None
    last_sale_reason: Optional[str] = None
    last_sale_pct: Optional[float] = None

    realized_R: Optional[float] = None
    holding_days: Optional[int] = None
    max_favorable_R: Optional[float] = None
    exit_efficiency: Optional[float] = None
    audit_log: list = field(default_factory=list)


def _strategy_id_multi_v3(entry_type: str, stop_type: str, trail_type: str, sell_style: str,
                           target_ladder: str, core_pct: float) -> str:
    return (f"{_strategy_id(entry_type, stop_type)}__T{trail_type.upper()}__{sell_style.upper()}"
            f"__L{target_ladder.upper()}__C{core_pct*100:g}")


def simulate_multi_v3_with_entry(
    ticker: str, d0: date, adr14: Optional[float], entry_type: str, stop_type: str, trail_type: str,
    target_pcts: list, sell_style: str, sell_amount: float, target_ladder: str, core_pct: float,
    entry: EntryResult, minute_df: pd.DataFrame, daily_sma: pd.DataFrame, sessions: list,
) -> TradeResultMultiV3:
    """V3b: entry/initial-stop exactly like V1/V2/V3, then
    multi_partial_taking.run_multi_partial_position_management for the staged
    multi-target sell-down. target_ladder is just a label (e.g. "early_start" /
    "late_start") distinguishing which target_pcts list this run used, for output/
    strategy-id purposes -- it has no effect on the simulation itself."""
    from . import multi_partial_taking  # local import: avoids a module import cycle

    log = []
    strategy_id = _strategy_id_multi_v3(entry_type, stop_type, trail_type, sell_style, target_ladder, core_pct)
    result = TradeResultMultiV3(
        ticker=ticker, event_date=d0, entry_type=entry_type, stop_type=stop_type, trail_type=trail_type,
        sell_style=sell_style, target_ladder=target_ladder, core_pct=core_pct, strategy_id=strategy_id,
        status="", entry_status=entry.entry_status,
    )
    log.append(f"{ticker} EP Day 0 = {d0}, strategy = {strategy_id}")

    if entry.entry_status == config.STATUS_NO_ENTRY:
        result.status = config.STATUS_NO_ENTRY
        result.audit_log = log
        return result

    result.entry_timestamp = entry.entry_timestamp
    result.entry_day_offset = entry.entry_day_offset
    result.entry_fill = entry.entry_fill
    log.append(f"Entry: {entry.fill_reason} at {entry.entry_timestamp}, fill = {entry.entry_fill:.4f}")

    stop = compute_initial_stop(stop_type, entry, adr14)
    if not stop.valid:
        result.status = stop.reason or config.STATUS_INVALID_STOP_GEOMETRY
        log.append(f"Initial stop invalid: {stop.reason}")
        result.audit_log = log
        return result

    result.initial_stop_price = stop.stop_price
    log.append(f"Initial stop ({stop_type}) = {stop.stop_price:.4f}")

    from . import trailing_stops
    ma_window = trailing_stops.ma_window_for(trail_type)
    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date, window=ma_window):
        result.status = config.STATUS_INELIGIBLE_NO_10SMA
        log.append(f"Fewer than {ma_window} valid closes as of entry day -- INELIGIBLE_NO_MA_HISTORY")
        result.audit_log = log
        return result

    mp = multi_partial_taking.run_multi_partial_position_management(
        minute_df, daily_sma, entry, stop.stop_price, entry.entry_fill, trail_type, target_pcts,
        sell_style, sell_amount, core_pct, sessions, log,
    )

    result.status = mp.status
    result.realized_R = mp.realized_R
    result.n_sales = len(mp.sales)
    result.audit_log = log + mp.audit_log

    if mp.sales:
        first, last = mp.sales[0], mp.sales[-1]
        result.first_sale_timestamp = first.timestamp
        result.first_sale_price = first.price
        result.first_sale_reason = first.reason
        result.last_sale_timestamp = last.timestamp
        result.last_sale_price = last.price
        result.last_sale_reason = last.reason
        result.last_sale_pct = last.pct_of_original

    if result.status == "OK" and mp.sales:
        exit_ts = mp.sales[-1].timestamp
        exit_date = exit_ts.date() if hasattr(exit_ts, "date") else exit_ts
        result.holding_days = len(calendar_utils.TRADING_DAYS[
            (calendar_utils.TRADING_DAYS.date >= entry.entry_session_date)
            & (calendar_utils.TRADING_DAYS.date <= exit_date)
        ]) - 1

        risk = entry.entry_fill - stop.stop_price
        result.max_favorable_R = trade_metrics.compute_max_favorable_r(
            minute_df, daily_sma, entry.entry_timestamp, entry.entry_session_date, exit_ts,
            entry.entry_fill, risk,
        )
        result.exit_efficiency = trade_metrics.compute_exit_efficiency(result.realized_R, result.max_favorable_R)

    return result


def _run_position_management(minute_df, daily_sma, entry: EntryResult, stop_price, sessions, log, ma_col="sma10",
                              is_continuation=False):
    """
    Returns (exit_timestamp, exit_reference_price, exit_reason) or (None, None, None).

    Vectorized rather than a per-bar/per-day Python loop -- an earlier row-by-row
    version (`for j, bar in day_bars.iterrows(): ...`) was the dominant cost of a
    full-universe run: this step reruns per STOP TYPE (12x per event, since the stop
    price differs each time and can be crossed at a different bar), over up to ~3,000
    cached minute bars, so a slow per-row Python loop here is paid 12x per event no
    matter how much the entry search and 10SMA computation get hoisted out above it.

    ma_col defaults to "sma10" for V1's standardized exit; V2's close_below_20ma trail
    type (trailing_stops.is_close_based) reuses this exact function with ma_col="sma20"
    rather than duplicating it, since the mechanics are otherwise identical.

    is_continuation=True is for V3's Phase 2 (partial_taking.py): the core position was
    already open before this scan starts (it's resuming after a partial sale, not a
    fresh entry), so the Section 23 same-bar-adverse rule -- which exists specifically
    because an ENTRY order's own fill and a stop touch can be ambiguously ordered within
    one bar -- doesn't apply to its first bar. Without this flag, Phase 2 was wrongly
    treating its first considered bar as if a brand-new entry order had just fired
    there, spuriously applying the adverse-assumption exemption from the gap check.
    """
    remaining_days = [d for d in sessions if d >= entry.entry_session_date]

    bars = minute_df[
        minute_df["session_date"].isin(remaining_days) & (minute_df["dt_et"] >= entry.entry_timestamp)
    ].sort_values("dt_et").reset_index(drop=True)

    stop_ts = stop_day = stop_ref = stop_reason = None
    if not bars.empty:
        is_entry_bar = np.zeros(len(bars), dtype=bool)
        if not is_continuation:
            is_entry_bar[0] = True  # bars are sorted from entry_timestamp onward -> row 0 is the entry bar
        low = bars["low"].to_numpy()
        open_ = bars["open"].to_numpy()
        gap_cond = (~is_entry_bar) & (open_ <= stop_price)  # Section 16: entry bar itself never gap-checked
        trade_cond = low <= stop_price  # for the entry bar this IS the Section 23 same-bar-adverse check
        stop_hit = gap_cond | trade_cond
        if stop_hit.any():
            idx = int(stop_hit.argmax())  # first True, chronologically (bars are sorted)
            stop_ts = bars["dt_et"].iloc[idx]
            stop_day = bars["session_date"].iloc[idx]
            if is_entry_bar[idx]:
                stop_reason, stop_ref = "STOPPED_SAME_BAR_AS_ENTRY", stop_price
                log.append(
                    f"{stop_ts}: entry bar's own low ({low[idx]:.4f}) <= stop ({stop_price:.4f}) "
                    "-- same-bar ambiguity, adverse assumption applied"
                )
            elif gap_cond[idx]:
                stop_reason, stop_ref = "STOPPED_GAP_THROUGH", float(open_[idx])
                log.append(f"{stop_ts}: session open ({stop_ref:.4f}) already through stop -- gap-through stop")
            else:
                stop_reason, stop_ref = "STOPPED_TRADE_THROUGH", stop_price

    exit_label = "SMA10_EXIT" if ma_col == "sma10" else "SMA20_EXIT"

    # Close-exit only matters on days strictly before any stop-out day -- once a stop
    # fires intrabar, that day's close is never reached (Section 24 vs 26 priority).
    day_frame = daily_sma[daily_sma["date"].isin(remaining_days)].sort_values("date")
    if stop_day is not None:
        day_frame = day_frame[day_frame["date"] < stop_day]
    sma_cond = day_frame[ma_col].notna() & (day_frame["close"] < day_frame[ma_col])
    if sma_cond.any():
        row = day_frame.iloc[int(sma_cond.to_numpy().argmax())]
        log.append(f"{row['date']}: close {row['close']:.4f} < {ma_col} {row[ma_col]:.4f} -- {exit_label}")
        return row["date"], row["close"], exit_label

    if stop_ts is not None:
        return stop_ts, stop_ref, stop_reason

    # Ran out of cached minute-bar coverage (past D+7) without a resolved exit --
    # fall back to daily-bar approximation. See module docstring.
    #
    # This can walk forward through YEARS of subsequent daily bars for a position that
    # rides its 10SMA a long time (V1 has no max holding period, Section 57) -- a plain
    # Python `for _, row in after.iterrows()` loop measured as the dominant cost of a
    # full-universe run (each such trade took ~70-100ms, vs. <1ms for the rest of the
    # simulation combined). Vectorized below: find the first day any exit condition is
    # true with numpy comparisons instead of a per-row Python loop.
    log.append(f"Position survived through {sessions[-1]} (end of cached minute window) -- switching to daily-bar approximation")
    after = daily_sma[daily_sma["date"] > sessions[-1]].sort_values("date").reset_index(drop=True)

    gap_through = after["open"] <= stop_price
    trade_through = after["low"] <= stop_price
    sma_exit = (after[ma_col].notna()) & (after["close"] < after[ma_col])
    any_exit = gap_through | trade_through | sma_exit
    if not any_exit.any():
        return None, None, None

    pos = int(any_exit.to_numpy().argmax())  # first True
    row = after.iloc[pos]
    # Priority matches the original day-by-day order: gap-through, then trade-through,
    # then the MA close check -- all three are evaluated on the SAME day here, so
    # preserve that same priority when more than one is true on the winning day.
    if gap_through.iloc[pos]:
        return row["date"], row["open"], "STOPPED_GAP_THROUGH_DAILY_APPROX"
    if trade_through.iloc[pos]:
        return row["date"], stop_price, "STOPPED_TRADE_THROUGH_DAILY_APPROX"
    return row["date"], row["close"], exit_label


def simulate_trade(ticker: str, d0: date, adr14: Optional[float], entry_type: str, stop_type: str,
                    refresh: bool = False) -> TradeResult:
    """Convenience wrapper: pulls/caches data itself. Used for one-off verification."""
    minute_df = minute_bars.get_event_window_minute_bars(ticker, d0, refresh=refresh)
    daily_df = daily_bars.pull_ticker_daily_bars(ticker, d0, refresh=refresh)
    return simulate_trade_from_data(ticker, d0, adr14, entry_type, stop_type, minute_df, daily_df)
