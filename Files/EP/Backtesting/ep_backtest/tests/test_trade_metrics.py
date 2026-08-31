"""trade_metrics.py unit tests -- MFE / exit efficiency, pure-function so no fixtures needed."""

from datetime import date, datetime, timedelta

import pandas as pd

from .. import config
from ..trade_metrics import compute_exit_efficiency, compute_max_favorable_r


def _minute_bar(d, hhmm, high, session_date=None):
    hh, mm = divmod(hhmm, 100)
    dt = datetime.combine(session_date or d, datetime.min.time(), tzinfo=config.ET).replace(hour=hh, minute=mm)
    return {"dt_et": dt, "session_date": session_date or d, "high": high}


def test_mfe_ignores_bars_before_entry_on_entry_day():
    d0 = date(2024, 1, 2)
    entry_ts = datetime.combine(d0, datetime.min.time(), tzinfo=config.ET).replace(hour=9, minute=45)
    minute_df = pd.DataFrame([
        _minute_bar(d0, 930, 200),   # BEFORE entry -- a spike here must not count
        _minute_bar(d0, 945, 100),   # the entry bar itself
        _minute_bar(d0, 950, 105),   # after entry -- this is the real peak
    ])
    daily_sma = pd.DataFrame(columns=["date", "high"])

    mfe = compute_max_favorable_r(minute_df, daily_sma, entry_ts, d0, d0, entry_fill=100.0, risk=5.0)
    assert abs(mfe - 1.0) < 1e-9, "peak must be 105 (from AFTER entry), not the pre-entry 200 spike"


def test_mfe_uses_daily_highs_for_days_after_entry():
    d0 = date(2024, 1, 2)
    d1 = date(2024, 1, 3)
    d2 = date(2024, 1, 4)
    entry_ts = datetime.combine(d0, datetime.min.time(), tzinfo=config.ET).replace(hour=9, minute=31)
    minute_df = pd.DataFrame([_minute_bar(d0, 931, 101)])
    daily_sma = pd.DataFrame([
        {"date": d0, "high": 101},   # entry day's daily high -- ignored, minute bars used instead
        {"date": d1, "high": 120},
        {"date": d2, "high": 150},   # the true peak
    ])

    mfe = compute_max_favorable_r(minute_df, daily_sma, entry_ts, d0, d2, entry_fill=100.0, risk=5.0)
    assert abs(mfe - 10.0) < 1e-9  # (150-100)/5


def test_mfe_stops_looking_after_exit_date():
    d0 = date(2024, 1, 2)
    d1 = date(2024, 1, 3)
    d2 = date(2024, 1, 4)  # exit happens ON d1 -- d2's huge high must not count
    entry_ts = datetime.combine(d0, datetime.min.time(), tzinfo=config.ET).replace(hour=9, minute=31)
    minute_df = pd.DataFrame([_minute_bar(d0, 931, 101)])
    daily_sma = pd.DataFrame([
        {"date": d0, "high": 101},
        {"date": d1, "high": 110},
        {"date": d2, "high": 500},  # after the exit -- irrelevant
    ])

    mfe = compute_max_favorable_r(minute_df, daily_sma, entry_ts, d0, d1, entry_fill=100.0, risk=5.0)
    assert abs(mfe - 2.0) < 1e-9  # (110-100)/5, NOT influenced by day d2's 500 high


def test_exit_efficiency_full_capture_and_partial_giveback():
    assert abs(compute_exit_efficiency(realized_R=5.0, max_favorable_R=5.0) - 1.0) < 1e-9
    assert abs(compute_exit_efficiency(realized_R=2.0, max_favorable_R=10.0) - 0.2) < 1e-9
    # gave back everything and then some -- negative efficiency is a valid, meaningful signal
    assert compute_exit_efficiency(realized_R=-1.0, max_favorable_R=8.0) < 0


def test_exit_efficiency_undefined_when_no_real_peak():
    assert compute_exit_efficiency(realized_R=-1.0, max_favorable_R=0.0) is None
    assert compute_exit_efficiency(realized_R=-1.0, max_favorable_R=None) is None
    assert compute_exit_efficiency(realized_R=None, max_favorable_R=5.0) is None


if __name__ == "__main__":
    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failures = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"\n{len(tests) - failures}/{len(tests)} passed")
    if failures:
        raise SystemExit(1)
