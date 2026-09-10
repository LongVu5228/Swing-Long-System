import os, sys, time, socket

SCRIPT_DIR = r"C:\Users\longv\Trading\Personal Wealth\Swing Long System\Files\EP\Automation\New Automation Scripts"
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)
import ep_long_daily as eng

print("*** Buys 3 real shares of SPY at market, then calls the ACTUAL production")
print("*** functions from ep_long_daily.py -- place_protective_stop() once for all")
print("*** 3 shares, and place_ladder_rung() three times (1 share each) at three")
print("*** small targets above the fill. Nothing auto-cancels; left for you to")
print("*** inspect/clean up manually in DAS.\n")

print(f"Connecting to {eng.DAS_HOST}:{eng.DAS_PORT} ...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2.0)
sock.connect((eng.DAS_HOST, eng.DAS_PORT))
eng.send_line(sock, f"LOGIN {eng.DAS_USER} {eng.DAS_PASS} {eng.DAS_ACCT}")
time.sleep(1.0)
eng.send_line(sock, "ReturnFullLv1 YES")

buf = b""


def drain(seconds):
    global buf
    deadline = time.time() + seconds
    seen = []
    while time.time() < deadline:
        lines, buf = eng.recv_lines(sock, buf)
        for l in lines:
            print("  <-", l)
            seen.append(l)
        time.sleep(0.05)
    return seen


drain(2.0)

print(f"\n--- Confirming account {eng.DAS_ACCT} ---")
equity = eng.fetch_equity_snapshot(sock, timeout_sec=5.0)
print(f"Equity: {equity}")
if equity is None:
    print("FAILED to fetch equity -- aborting before touching orders.")
    sys.exit(1)

print("\n--- Subscribing to SPY Lv1 quote ---")
eng.send_line(sock, "SB SPY Lv1")
last_price = None
deadline = time.time() + 8.0
while time.time() < deadline and last_price is None:
    lines, buf = eng.recv_lines(sock, buf)
    for l in lines:
        print("  <-", l)
        if l.upper().startswith("$QUOTE") and "SPY" in l.upper():
            m = eng.QUOTE_LAST_RE.search(l)
            if m:
                last_price = float(m.group(1))
    time.sleep(0.05)

if last_price is None:
    print("\nFAILED: no SPY price from DAS. Aborting.")
    eng.send_line(sock, "QUIT")
    sock.close()
    sys.exit(1)

print(f"\nSPY last price ~= {last_price}. Buying 3 shares at MARKET via route {eng.ROUTE_ENTRY}...")
buy_token = int(time.time() * 1000) % 1000000
buy_cmd = f"NEWORDER {buy_token} B SPY {eng.ROUTE_ENTRY} 3 MKT TIF=DAY+"
print(f"SENDING: {buy_cmd}")
eng.send_line(sock, buy_cmd)
drain(4.0)

print("\n--- Confirming fill via GET POSITIONS ---")
eng.send_line(sock, "GET POSITIONS")
pos_lines = drain(2.0)
avg_cost = None
qty_held = 0
for l in pos_lines:
    parts = [p for p in l.split() if p]
    if len(parts) >= 5 and parts[0].upper() in ("%POS", "#POS") and parts[1].upper() == "SPY":
        try:
            qty_held = int(float(parts[3]))
            avg_cost = float(parts[4])
        except (ValueError, IndexError):
            pass

if avg_cost is None or qty_held < 3:
    print(f"\nCouldn't confirm a 3-share fill (qty_held={qty_held}). Check DAS directly before proceeding.")
    eng.send_line(sock, "QUIT")
    sock.close()
    sys.exit(1)

print(f"\nConfirmed: {qty_held} shares @ avg cost {avg_cost}")

stop_price = round(avg_cost * 0.99, 2)
rung_pcts = [0.003, 0.006, 0.009]  # small, close-in targets -- just a mechanics test, not the real strategy's spacing
rung_prices = [round(avg_cost * (1 + p), 2) for p in rung_pcts]

print(f"\nPlacing protective stop via place_protective_stop(): {qty_held}sh @ ${stop_price:.2f}")
stop_token = eng.place_protective_stop(sock, "SPY", qty_held, stop_price)
print(f"  -> token {stop_token}")
drain(2.0)

for idx, price in enumerate(rung_prices):
    print(f"\nPlacing ladder rung {idx+1}/3 via place_ladder_rung(): 1sh @ ${price:.2f}")
    rung_token = eng.place_ladder_rung(sock, "SPY", 1, price, idx)
    print(f"  -> token {rung_token}")
    drain(2.0)

print("\n" + "=" * 60)
print(f"Done. You hold {qty_held} shares of SPY (avg ${avg_cost:.2f}). Resting orders:")
print(f"  - protective STOP (below):  {qty_held}sh @ ${stop_price:.2f}")
for price in rung_prices:
    print(f"  - ladder LIMIT sell (above): 1sh @ ${price:.2f}")
print("\nCheck DAS's Orders window: 1 stop + 3 limit sells, all Accepted, none")
print("firing immediately. Nothing further sent by this script -- clean up")
print("manually whenever you're ready.")
print("=" * 60)

eng.send_line(sock, "QUIT")
sock.close()
