import os, sys, time, socket

SCRIPT_DIR = r"C:\Users\longv\Trading\Personal Wealth\Swing Long System\Files\EP\Automation\New Automation Scripts"
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)
import ep_long_daily as eng

print("*** This buys 2 real shares of SPY at market, then rests two sell-stop")
print("*** orders on them (one below the fill -- protective-stop direction, one")
print("*** above -- ladder-target direction) and leaves everything in place for")
print("*** you to inspect/cancel manually in DAS. Nothing is auto-canceled.\n")

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
    print("\nFAILED: no SPY price from DAS. Aborting before placing any order.")
    eng.send_line(sock, "QUIT")
    sock.close()
    sys.exit(1)

print(f"\nSPY last price ~= {last_price}. Buying 2 shares at MARKET via route SMAT...")
buy_token = int(time.time() * 1000) % 1000000
buy_cmd = f"NEWORDER {buy_token} B SPY SMAT 2 MKT TIF=DAY+"
print(f"SENDING: {buy_cmd}")
eng.send_line(sock, buy_cmd)

# %TRADE carries the DAS order id, not our client token, so matching it up here
# isn't worth the complexity for a one-off test -- just wait a moment for the
# market order to settle, then read the resulting position/avg-cost directly.
drain(3.0)

print("\n--- Checking position/fill via GET POSITIONS ---")
eng.send_line(sock, "GET POSITIONS")
pos_lines = drain(2.0)
avg_cost = None
for l in pos_lines:
    parts = [p for p in l.split() if p]
    # %POS/#POS field order: tag Symbol Type Quantity AvgCost ...
    if len(parts) >= 5 and parts[0].upper() in ("%POS", "#POS") and parts[1].upper() == "SPY":
        try:
            avg_cost = float(parts[4])
        except (ValueError, IndexError):
            pass

if avg_cost is None:
    print("\nCouldn't confirm the fill price from GET POSITIONS. Check DAS directly for your SPY")
    print("position/avg cost, then tell me the number and I'll compute the two stop prices for you.")
    eng.send_line(sock, "QUIT")
    sock.close()
    sys.exit(1)

below_price = round(avg_cost * 0.99, 2)
above_price = round(avg_cost * 1.01, 2)
print(f"\nConfirmed avg cost = {avg_cost}. Placing two 1-share sell-stops via route SMAT:")
print(f"  BELOW (protective-stop direction): ${below_price:.2f}")
print(f"  ABOVE  (ladder-target direction):  ${above_price:.2f}")

below_token = int(time.time() * 1000) % 1000000
below_cmd = f"NEWORDER {below_token} S SPY SMAT 1 STOPMKT {below_price:.2f} TIF=DAY+"
print(f"\nSENDING: {below_cmd}")
eng.send_line(sock, below_cmd)
drain(2.0)

above_token = int(time.time() * 1000) % 1000000
above_cmd = f"NEWORDER {above_token} S SPY SMAT 1 STOPMKT {above_price:.2f} TIF=DAY+"
print(f"\nSENDING: {above_cmd}")
eng.send_line(sock, above_cmd)
drain(2.0)

print("\n" + "=" * 60)
print("Done. You now hold 2 shares of SPY, with:")
print(f"  - a resting sell-stop BELOW at ${below_price:.2f} (token {below_token})")
print(f"  - a resting sell-stop ABOVE at ${above_price:.2f} (token {above_token})")
print("Check DAS's Orders window: did BOTH get Accepted? Did either fill/behave")
print("oddly (especially the ABOVE one -- that's the untested direction)?")
print("Nothing further will be sent by this script -- cancel/flatten manually")
print("whenever you're ready, or tell me what you see and I can send CANCEL.")
print("=" * 60)

eng.send_line(sock, "QUIT")
sock.close()
