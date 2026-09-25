import os, sys, time, socket

SCRIPT_DIR = r"C:\Users\longv\Trading\Personal Wealth\Swing Long System\Files\EP\Automation\New Automation Scripts"
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)
import ep_long_daily as eng

print("*** Uses the 1 SPY share you already hold. Places ONE resting LIMIT sell")
print("*** order above market (the FIXED ladder-rung mechanism -- plain limit,")
print("*** not a stop) via route SMAT. Nothing auto-cancels -- left for you to")
print("*** inspect in DAS. Your existing below-market protective stop is left alone.\n")

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

print(f"\n--- Confirming account {eng.DAS_ACCT} and current SPY position ---")
equity = eng.fetch_equity_snapshot(sock, timeout_sec=5.0)
print(f"Equity: {equity}")

eng.send_line(sock, "GET POSITIONS")
pos_lines = drain(2.0)
held_qty = 0
avg_cost = None
for l in pos_lines:
    parts = [p for p in l.split() if p]
    if len(parts) >= 5 and parts[0].upper() in ("%POS", "#POS") and parts[1].upper() == "SPY":
        try:
            held_qty = int(float(parts[3]))
            avg_cost = float(parts[4])
        except (ValueError, IndexError):
            pass

print(f"\nCurrent SPY position: {held_qty} share(s), avg cost {avg_cost}")
if held_qty < 1:
    print("You don't appear to hold any SPY right now -- nothing to test this way. Aborting.")
    eng.send_line(sock, "QUIT")
    sock.close()
    sys.exit(1)

print("\n--- Getting a fresh live SPY quote ---")
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

limit_price = round(last_price * 1.01, 2)
print(f"\nSPY last price = {last_price} -> resting LIMIT sell at ${limit_price:.2f} (1% above) for 1 share via SMAT")

token = int(time.time() * 1000) % 1000000
# Exactly what place_ladder_rung() sends in production -- plain limit, no STOPMKT keyword.
order_cmd = f"NEWORDER {token} S SPY SMAT 1 {limit_price:.2f} TIF=GTC+"
print(f"SENDING: {order_cmd}")
eng.send_line(sock, order_cmd)

print("\n--- Order response ---")
drain(3.0)

print("\n" + "=" * 60)
print(f"Done. Check DAS's Orders window for a resting LIMIT sell on SPY @ ${limit_price:.2f}.")
print("It should NOT fire immediately (unlike the earlier sell-stop-above-market test) --")
print("it should just sit there until/unless price actually rises to that level.")
print("Nothing further sent by this script. Your other resting order (the protective")
print("stop below market from the earlier test) is untouched. Clean up both whenever ready.")
print("=" * 60)

eng.send_line(sock, "QUIT")
sock.close()
