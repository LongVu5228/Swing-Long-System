"""
Stage 2 partial-taking engine (§12, EP spec §47-55): EP's multi-partial loop
(ep_backtest.multi_partial_taking.run_multi_partial_position_management) generalized so every
partial dimension can vary, while reusing EP's tested primitives unchanged -- the downside
scan (trailing stops, breakeven floor, gaps), find_target_reached (gap / multi-target
crossing), restrict_to_after / make_continuation_entry (point-in-time continuation) and
_stop_wins (same-day event ordering).

What EP's version can't do and this one adds:
  - kind="time": sell at the CLOSE every N sessions after entry (never on the entry day).
  - kind="none": no partials, the whole position rides the trail (== core 100%).
  - amount_mode="fixed": a fixed slice of the ORIGINAL position per sale, capped by the
    non-core left (EP's equal_depletion always re-derives the slice as non-core / n_targets,
    so "2.5% per rung" was not expressible). Unsold non-core keeps riding with the core.
  - breakeven=False: the floor stays at the initial stop after sales.

Regression guarantee: PartialCfg() (the Stage 1 reference: start20 ladder, equal_depletion,
core 50%, breakeven on) reproduces EP's simulate_multi_v3_with_entry trade-for-trade
(htf_backtest/tests/test_partials.py + the stage-1 replay check in run_stage2 --verify).
"""

from dataclasses import dataclass, field

import numpy as np
from typing import Optional

from . import config  # noqa: F401  (sets up the EP path)
from ep_backtest import calendar_utils, config as ep_config, exits, trade_metrics, trailing_stops  # noqa: E402
from ep_backtest.initial_stop import compute_initial_stop  # noqa: E402
from ep_backtest.multi_partial_taking import MultiPartialResult, Sale, _downside_scan, _next_sell_pct  # noqa: E402
from ep_backtest.partial_taking import (  # noqa: E402
    _day_of, _stop_wins, find_target_reached, is_gap_reason, make_continuation_entry, restrict_to_after)
from ep_backtest.simulate_trade import _slip_sub  # noqa: E402

START20 = [0.20, 0.275, 0.35, 0.425, 0.50]


@dataclass(frozen=True)
class PartialCfg:
    kind: str = "ladder"                    # ladder | time | extension | none   (single sale = a 1-rung ladder)
    targets: tuple = tuple(START20)         # ladder: levels above the entry fill, in target_unit;
                                            # extension: k levels (close >= SMA10 * (1 + k * ADR14))
    target_unit: str = "pct"                # ladder: pct (fraction of fill) | R (multiples of initial risk) | adr (ADR14 multiples)
    ext_basis: str = "sma10_adr"            # extension: sma10_adr (close vs SMA10 in ADRs) | bb20 (close vs SMA20 in 20-day std devs = Bollinger)
    every_n: int = 5                        # time: sessions between sales
    n_time_sales: int = 5                   # time: max number of sales
    amount_mode: str = "equal_depletion"    # equal_depletion | fixed | exponential
    amount: float = 0.10                    # fixed: share of original per sale; exponential: share of remaining non-core
    core_pct: float = 0.50
    breakeven: bool = True
    label: str = "ref"


@dataclass
class Result:
    status: str
    realized_R: Optional[float] = None
    n_sales: int = 0
    first_sale_reason: Optional[str] = None
    last_sale_reason: Optional[str] = None
    last_sale_timestamp: Optional[object] = None
    holding_days: Optional[int] = None
    max_favorable_R: Optional[float] = None
    exit_efficiency: Optional[float] = None
    audit_log: list = field(default_factory=list)
    sales: list = field(default_factory=list)          # [Sale] -- step 13 earnings post-processing
    stop_price: Optional[float] = None


def _time_events(minute_df, daily_sma, entry, cfg):
    """[(timestamp, close)] for the scheduled time sales: the close of every N-th session
    after the entry session. Inside the minute window the timestamp is the session's last
    minute bar (so _stop_wins orders it against intraday stops); after it, the plain date
    (daily-approximation phase, adverse priority on same-day collisions)."""
    days = daily_sma.date[daily_sma.date > entry.entry_session_date].tolist()
    picks = days[cfg.every_n - 1::cfg.every_n][:cfg.n_time_sales]
    out = []
    for d in picks:
        bars = minute_df[minute_df.session_date == d]
        if len(bars):
            out.append((bars.dt_et.iloc[-1], float(bars.close.iloc[-1])))
        else:
            out.append((d, float(daily_sma.loc[daily_sma.date == d, "close"].iloc[0])))
    return out


def _extension_events(minute_df, daily_sma, entry, cfg, adr):
    """[(timestamp, close)]: for each k in cfg.targets (ascending), the close of the first session
    after entry whose close is >= SMA10 * (1 + k * ADR14) -- "sell into extension" at the close.
    Later levels must come after earlier ones; each level fires once."""
    if cfg.ext_basis == "bb20":
        sd = daily_sma.close.rolling(20).std(ddof=0)            # Bollinger: population std of the last 20 closes
        z = (daily_sma.close - daily_sma.close.rolling(20).mean()) / sd
        d = daily_sma.assign(_z=z)[daily_sma.date > entry.entry_session_date]
        ext = d._z
    else:
        if not adr:
            return []
        d = daily_sma[daily_sma.date > entry.entry_session_date]
        ext = (d.close / d.sma10 - 1) / adr
    out, start = [], 0
    for k in sorted(cfg.targets):
        hit = np.where(ext.to_numpy()[start:] >= k)[0]
        if not len(hit):
            break
        i = start + int(hit[0])
        day = d.date.iloc[i]
        bars = minute_df[minute_df.session_date == day]
        out.append((bars.dt_et.iloc[-1], float(bars.close.iloc[-1])) if len(bars) else (day, float(d.close.iloc[i])))
        start = i + 1
    return out


def _after(ts_a, ts_b) -> bool:
    """True if event a happens strictly after event b (mixed date / timestamp safe)."""
    da, db = _day_of(ts_a), _day_of(ts_b)
    if da != db:
        return da > db
    if hasattr(ts_a, "date") and hasattr(ts_b, "date"):
        return ts_a > ts_b
    return False


def run_partials(minute_df, daily_sma, entry, initial_stop_price, trail_type, cfg: PartialCfg, sessions, log, adr=None,
                 force_exit=False):
    """force_exit: a delisted (^) ticker -- whatever is still open when the daily bars end is sold
    at the last daily close (reason DELISTED_LAST_BAR) instead of STILL_OPEN_AT_DATA_END."""
    entry_fill = entry.entry_fill
    risk = entry_fill - initial_stop_price
    core = 1.0 if cfg.kind == "none" else cfg.core_pct
    non_core = 1.0 - core
    total_sold = 0.0
    sales = []

    if cfg.kind == "ladder":
        if cfg.target_unit == "R":
            pending = sorted(entry_fill + k * risk for k in cfg.targets)
        elif cfg.target_unit == "adr":
            if not adr:
                return MultiPartialResult(status="NO_ADR", audit_log=log)
            pending = sorted(entry_fill * (1 + k * adr) for k in cfg.targets)
        else:
            pending = sorted(entry_fill * (1 + p) for p in cfg.targets)
        n_planned = len(pending)
    elif cfg.kind == "time":
        pending = _time_events(minute_df, daily_sma, entry, cfg)
        n_planned = len(pending)
    elif cfg.kind == "extension":
        pending = _extension_events(minute_df, daily_sma, entry, cfg, adr)
        n_planned = len(cfg.targets)        # size each sale as if every level could fire
    else:
        pending, n_planned = [], 0

    if cfg.amount_mode == "equal_depletion":
        sell_amount = non_core / n_planned if n_planned else 0.0
        style = "equal_depletion"
    elif cfg.amount_mode == "fixed":
        sell_amount, style = cfg.amount, "equal_depletion"     # EP's equal rule = min(amount, remaining)
    else:
        sell_amount, style = cfg.amount, "exponential_remaining"

    scan_df, scan_sessions, scan_entry = minute_df, sessions, entry
    floor, reference_price = initial_stop_price, entry_fill
    be_done, is_cont = False, False

    def close_out(ts, ref, reason, note):
        leftover = round(1.0 - total_sold, 6)
        fill = _slip_sub(ref)
        sales.append(Sale(ts, fill, leftover, reason))
        log.append(f"{ts}: {reason} at {fill:.4f} -- final sale of remaining {leftover*100:g}%{note}")

    def open_at_end():
        """None = position force-closed at the last bar (caller breaks); else the STILL_OPEN result."""
        if not force_exit:
            return MultiPartialResult(status="STILL_OPEN_AT_DATA_END", sales=sales, audit_log=log)
        last = daily_sma.iloc[-1]
        close_out(last.date, float(last.close), "DELISTED_LAST_BAR", " (daily bars end: ticker delisted)")
        return None

    while True:
        stop_ts, stop_ref, stop_reason = _downside_scan(
            scan_df, daily_sma, scan_entry, floor, reference_price, trail_type, scan_sessions, log,
            is_cont, entry.entry_session_date, original_entry_fill=entry_fill)
        if stop_ts == "INVALID":
            return MultiPartialResult(status=ep_config.STATUS_INVALID_STOP_GEOMETRY, audit_log=log)

        if not pending or non_core <= 1e-9:
            if stop_ts is None:
                res = open_at_end()
                if res is not None:
                    return res
                break
            close_out(stop_ts, stop_ref, stop_reason, "")
            break

        if cfg.kind == "ladder":
            ev_ts, ev_ref, ev_reason = find_target_reached(
                scan_df, daily_sma, scan_entry, pending[0], scan_sessions, log, is_continuation=is_cont)
        else:
            ev_ts, ev_ref = pending[0]
            ev_reason = "TIME_SALE_CLOSE" if cfg.kind == "time" else "EXTENSION_SALE_CLOSE"

        if stop_ts is None and ev_ts is None:
            res = open_at_end()
            if res is not None:
                return res
            break
        if _stop_wins(stop_ts, stop_reason, ev_ts):
            if stop_ts is None:
                res = open_at_end()
                if res is not None:
                    return res
                break
            close_out(stop_ts, stop_ref, stop_reason, " (no further targets reached)")
            break

        if cfg.kind == "ladder":
            is_gap = is_gap_reason(ev_reason)
            crossed = [tp for tp in pending if tp <= ev_ref + 1e-9]
            fills = [ev_ref if is_gap else tp for tp in crossed]
        else:
            crossed, fills = [pending[0]], [ev_ref]
        last_fill = None
        for i, lvl in enumerate(fills, start=1):
            if non_core <= 1e-9:
                break
            fill = _slip_sub(lvl)
            last_fill = fill
            pct = _next_sell_pct(style, sell_amount, non_core)
            sales.append(Sale(ev_ts, fill, pct, f"{ev_reason}_{i}of{len(fills)}"))
            total_sold += pct
            non_core -= pct
        log.append(f"{ev_ts}: {len(fills)} sale event(s), non-core remaining = {non_core*100:g}%")
        pending = pending[len(crossed):]
        # Breakeven only after a sale made in profit: ladder sales always are, but a time sale
        # can land below the entry, where a breakeven floor would sit above the price
        # (EP's geometry guard then voids the trade -- seen on the 2026-11-14 smoke run).
        if cfg.breakeven and not be_done and last_fill is not None and last_fill > entry_fill:
            floor, be_done = entry_fill, True
            log.append(f"Breakeven activated: floor = {entry_fill:.4f}")
        reference_price = last_fill if last_fill is not None else reference_price

        day = _day_of(ev_ts)
        scan_df, scan_sessions = restrict_to_after(minute_df, sessions, day, ev_ts)
        scan_entry = make_continuation_entry(entry, ev_ts, day, entry_fill)
        is_cont = True
        if cfg.kind in ("time", "extension"):
            # A close-based sale fires at the close; anything scheduled at or before it is spent.
            pending = [p for p in pending if _after(p[0], ev_ts)]

    realized = sum(s.pct_of_original * (s.price - entry_fill) for s in sales) / risk
    log.append(f"Weighted final R = {realized:.4f} across {len(sales)} sale(s)")
    return MultiPartialResult(status="OK", sales=sales, realized_R=realized, audit_log=log)


def simulate(ticker, entry, ep_stop_type, trail_type, cfg: PartialCfg, minute_df, daily_sma, sessions,
             force_exit=False) -> Result:
    """simulate_multi_v3_with_entry's wrapper logic (initial stop, MA-history guard, holding
    days, MFE, exit efficiency) around run_partials."""
    log = [f"{ticker} {cfg.label} entry {entry.entry_timestamp} fill {entry.entry_fill:.4f}"]
    stop = compute_initial_stop(ep_stop_type, entry, None)
    if not stop.valid:
        return Result(status=stop.reason or ep_config.STATUS_INVALID_STOP_GEOMETRY, audit_log=log)
    if not exits.has_sufficient_history(daily_sma, entry.entry_session_date,
                                        window=trailing_stops.ma_window_for(trail_type)):
        return Result(status=ep_config.STATUS_INELIGIBLE_NO_10SMA, audit_log=log)
    from .stops import adr14
    mp = run_partials(minute_df, daily_sma, entry, stop.stop_price, trail_type, cfg, sessions, log,
                      adr=adr14(daily_sma, entry.entry_session_date), force_exit=force_exit)
    r = Result(status=mp.status, realized_R=mp.realized_R, n_sales=len(mp.sales), audit_log=log + mp.audit_log,
               sales=list(mp.sales), stop_price=stop.stop_price)
    if mp.sales:
        r.first_sale_reason = mp.sales[0].reason
        r.last_sale_reason, r.last_sale_timestamp = mp.sales[-1].reason, mp.sales[-1].timestamp
    if r.status == "OK" and mp.sales:
        exit_ts = mp.sales[-1].timestamp
        exit_date = exit_ts.date() if hasattr(exit_ts, "date") else exit_ts
        td = calendar_utils.TRADING_DAYS
        r.holding_days = len(td[(td.date >= entry.entry_session_date) & (td.date <= exit_date)]) - 1
        risk = entry.entry_fill - stop.stop_price
        r.max_favorable_R = trade_metrics.compute_max_favorable_r(
            minute_df, daily_sma, entry.entry_timestamp, entry.entry_session_date, exit_ts, entry.entry_fill, risk)
        r.exit_efficiency = trade_metrics.compute_exit_efficiency(r.realized_R, r.max_favorable_R)
    return r


def stage2a_variants() -> list:
    """One partial dimension changed at a time from the Stage 1 reference (§12)."""
    v = [PartialCfg()]
    for n in (3, 5, 10):
        v.append(PartialCfg(kind="time", every_n=n, label=f"time_every{n}"))
    for p in (0.10, 0.15, 0.20, 0.30, 0.50):
        v.append(PartialCfg(targets=(p,), label=f"single_{int(p*100)}"))
    v.append(PartialCfg(kind="none", label="none_core100"))
    for s in (0.10, 0.30, 0.40):                                          # ladder start, 7.5% spacing
        v.append(PartialCfg(targets=tuple(round(s + 0.075 * i, 4) for i in range(5)), label=f"start{int(s*100)}"))
    for sp in (0.05, 0.10, 0.15, 0.20):                                   # spacing from +20%
        v.append(PartialCfg(targets=tuple(round(0.20 + sp * i, 4) for i in range(5)),
                            label=f"spacing{int(sp*100)}"))
    v.append(PartialCfg(targets=tuple(round(0.20 + 0.10 * i, 4) for i in range(9)), label="to100_9rungs"))
    for a in (0.025, 0.05):
        v.append(PartialCfg(amount_mode="fixed", amount=a, label=f"fixed{a*100:g}pts"))
    for a in (0.05, 0.10, 0.20):
        v.append(PartialCfg(amount_mode="exponential", amount=a, label=f"expo{int(a*100)}pct"))
    for c in (0.0, 0.30, 0.70):
        v.append(PartialCfg(core_pct=c, label=f"core{int(c*100)}"))
    v.append(PartialCfg(breakeven=False, label="no_breakeven"))
    return v


def stage2b_variants() -> list:
    """First-sale level x rung spacing, 5 rungs, everything else at the reference (§21 item 1)."""
    return [PartialCfg(targets=tuple(round(st + sp * i, 4) for i in range(5)),
                       label=f"s{int(st*100)}_sp{sp*100:g}")
            for st in (0.20, 0.30, 0.40) for sp in (0.075, 0.15, 0.20)]


def stage2c_variants() -> list:
    """Profit-taking alternatives (2026-11-19): target units (pct / R / ADR), Qullamaggie's single
    time partial, selling into extension above the 10-day MA, and pure trail. 5 rungs, equal depletion,
    core 50%, breakeven after a profitable sale unless noted."""
    lad = lambda st, sp: tuple(round(st + sp * i, 4) for i in range(5))
    v = [PartialCfg(), PartialCfg(targets=lad(0.30, 0.075), label="s30_sp7.5"),
         PartialCfg(kind="none", label="none_core100")]
    for st, sp in ((3, 1), (5, 2), (8, 2)):
        v.append(PartialCfg(targets=lad(st, sp), target_unit="R", label=f"R{st}_sp{sp}"))
    for st, sp in ((3, 1), (5, 2), (8, 2)):
        v.append(PartialCfg(targets=lad(st, sp), target_unit="adr", label=f"ADR{st}_sp{sp}"))
    for n in (3, 5):                       # Qullamaggie: sell 1/3-1/2 after 3-5 days, then breakeven
        for a in (0.33, 0.50):
            v.append(PartialCfg(kind="time", every_n=n, n_time_sales=1, amount_mode="fixed", amount=a,
                                core_pct=round(1 - a, 4), label=f"Q_day{n}_{int(a * 100)}pct"))
    for ks in ((2, 3, 4, 5, 6), (4, 5, 6, 7, 8)):
        v.append(PartialCfg(kind="extension", targets=ks, label=f"EXT{ks[0]}to{ks[-1]}adr"))
    # Bollinger (20, k sigma): sell into closes above the upper band; 2 sigma alone fires constantly in trends
    for ks in ((2.5, 3.0, 3.5, 4.0, 4.5), (3.0, 3.5, 4.0, 4.5, 5.0)):
        v.append(PartialCfg(kind="extension", ext_basis="bb20", targets=ks, label=f"BB{ks[0]:g}to{ks[-1]:g}sd"))
    v.append(PartialCfg(kind="extension", ext_basis="bb20", targets=(3.0,), label="BB3sd_single"))
    return v
