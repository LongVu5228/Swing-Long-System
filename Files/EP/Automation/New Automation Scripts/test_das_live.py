import os, sys, time, socket

SCRIPT_DIR = r"C:\Users\longv\Trading\Personal Wealth\Swing Long System\Files\EP\Automation\New Automation Scripts"
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)
import ep_long_daily as eng

print(f"Connecting to {eng.DAS_HOST}:{eng.DAS_PORT} ...")
# Local-only diagnostic -- stays on your screen, never sent anywhere. Checks for
# stray whitespace/hidden characters from a copy-paste into .env. Password length
# only (not the value) so you can sanity-check it without exposing it here.
print(f"DAS_USER repr = {eng.DAS_USER!r} (len={len(eng.DAS_USER)})")
print(f"DAS_ACCT repr = {eng.DAS_ACCT!r} (len={len(eng.DAS_ACCT)})")
print(f"DAS_PASS length = {len(eng.DAS_PASS)} chars (value not shown)")
login_line = f"LOGIN {eng.DAS_USER} {eng.DAS_PASS} {eng.DAS_ACCT}"
print(f"LOGIN line length = {len(login_line)} chars")

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2.0)
sock.connect((eng.DAS_HOST, eng.DAS_PORT))
eng.send_line(sock, login_line)
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


print("\n--- LOGIN response ---")
drain(2.0)

print(f"\n--- Fetching account equity (GET AccountInfo) -- confirming account {eng.DAS_ACCT} ---")
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
    print("\nNo Last price (L:) from $Quote yet -- trying time&sales as a fallback ...")
    eng.send_line(sock, "SB SPY tms")
    deadline = time.time() + 8.0
    while time.time() < deadline and last_price is None:
        lines, buf = eng.recv_lines(sock, buf)
        for l in lines:
            print("  <-", l)
            if l.upper().startswith("$T&S"):
                parts = l.split()
                try:
                    last_price = float(parts[2])
                except (ValueError, IndexError):
                    pass
        time.sleep(0.05)

if last_price is None:
    print("\nFAILED: could not get any SPY price from DAS within the timeout. Aborting before placing an order.")
    eng.send_line(sock, "QUIT")
    sock.close()
    sys.exit(1)

trigger = round(last_price * 1.01, 2)
print(f"\nSPY last price = {last_price} -> trigger price ${trigger:.2f} (1% above) for every route tried below.")

# Try candidate routes one at a time, stopping at the first one that isn't
# rejected outright. PRO20 already confirmed rejected ("Can't Find Route![RGEL]")
# in the prior run -- trying the next-most-likely broker-wide/generic routes.
candidate_routes = ["SMAT", "REB25", "SMRTL"]
winning_route = None

for route in candidate_routes:
    token = int(time.time() * 1000) % 1000000
    order_cmd = f"NEWORDER {token} B SPY {route} 1 STOPMKT {trigger:.2f} TIF=DAY+"
    print(f"\n--- Trying route={route} ---")
    print(f"SENDING: {order_cmd}")
    eng.send_line(sock, order_cmd)

    lines = drain(2.0)
    rejected = any("Send_Rej" in l or "Can't Find Route" in l for l in lines)
    accepted_order_id = None
    for l in lines:
        if l.startswith("%ORDER"):
            parts = l.split()
            if len(parts) > 2 and parts[2] == str(token):
                accepted_order_id = parts[1]

    if rejected:
        print(f"  -> REJECTED for route={route}.")
        continue
    if accepted_order_id:
        print(f"  -> ACCEPTED for route={route}! Order id={accepted_order_id}. Canceling the test order now...")
        eng.send_line(sock, f"CANCEL {accepted_order_id}")
        drain(2.0)
        winning_route = route
        break
    print(f"  -> No clear accept/reject signal yet for route={route} -- check DAS Orders window manually, "
          f"and if it's resting there, note the route AND remember to cancel it yourself.")

if winning_route:
    print(f"\n{'='*60}\nWINNING ROUTE: {winning_route}\n{'='*60}")
    print(f"Update ROUTE_ENTRY (and consider ROUTE_ADJUST/ROUTE_LADDER/ROUTE_EXIT) in ep_long_daily.py to '{winning_route}'.")
else:
    print("\nNone of the candidate routes were clearly accepted. Check DAS Trader Pro's Orders window directly,")
    print("and/or open a manual order ticket in the GUI for this account to see its Route dropdown.")

eng.send_line(sock, "QUIT")
sock.close()
