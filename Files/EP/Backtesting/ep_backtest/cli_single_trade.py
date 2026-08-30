"""Hand-verification CLI: simulate one (ticker, event_date, entry_type, stop_type) and
print the audit trail, matching the debug-mode format in Section 69 of the frozen spec.

Usage:
    python -m ep_backtest.cli_single_trade GRPN 2012-05-15 15m 0.50adr
"""

import argparse
from datetime import date

from .load_events import load_ep_v5
from .simulate_trade import simulate_trade


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("ticker")
    parser.add_argument("event_date", help="YYYY-MM-DD")
    parser.add_argument("entry_type", choices=["1m", "5m", "10m", "15m", "30m", "60m"])
    parser.add_argument("stop_type")
    parser.add_argument("--refresh", action="store_true")
    args = parser.parse_args()

    d0 = date.fromisoformat(args.event_date)

    events = load_ep_v5()
    row = events[(events["ticker"] == args.ticker) & (events["reaction_date"] == d0)]
    adr14 = float(row["adr14"].iloc[0]) if not row.empty else None
    if row.empty:
        print(f"WARNING: {args.ticker} @ {d0} not found in EP V5 -- adr14 unavailable, ADR-based stops will be invalid")
    else:
        print(f"adr14 (pre-gap, decimal) = {adr14:.4f}")

    result = simulate_trade(args.ticker, d0, adr14, args.entry_type, args.stop_type, refresh=args.refresh)

    print("\n" + "\n".join(result.audit_log))
    print(f"\nstatus = {result.status}")
    if result.status == "OK":
        print(f"realized_R = {result.realized_R:.4f}")
        print(f"holding_days = {result.holding_days}")


if __name__ == "__main__":
    main()
