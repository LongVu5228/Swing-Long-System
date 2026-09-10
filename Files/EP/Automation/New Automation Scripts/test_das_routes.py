import os, sys, time, socket

SCRIPT_DIR = r"C:\Users\longv\Trading\Personal Wealth\Swing Long System\Files\EP\Automation\New Automation Scripts"
sys.path.insert(0, SCRIPT_DIR)
os.chdir(SCRIPT_DIR)
import ep_long_daily as eng

print(f"Connecting to {eng.DAS_HOST}:{eng.DAS_PORT} ...")
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.settimeout(2.0)
sock.connect((eng.DAS_HOST, eng.DAS_PORT))
eng.send_line(sock, f"LOGIN {eng.DAS_USER} {eng.DAS_PASS} {eng.DAS_ACCT}")
time.sleep(1.0)
eng.send_line(sock, "ReturnFullLv1 YES")

buf = b""


def drain(seconds, label=None):
    global buf
    if label:
        print(f"\n--- {label} ---")
    deadline = time.time() + seconds
    lines_seen = []
    while time.time() < deadline:
        lines, buf = eng.recv_lines(sock, buf)
        for l in lines:
            print("  <-", l)
            lines_seen.append(l)
        time.sleep(0.05)
    return lines_seen


drain(2.0, "LOGIN response")

# Read-only, no orders touched. Confirms which routes DAS reports as usable
# for THIS account before we trust ROUTE_ENTRY/ROUTE_STOP/ROUTE_ADJUST/
# ROUTE_LADDER/ROUTE_EXIT (currently all guesses -- PRO20 already confirmed
# rejected with "Can't Find Route![RGEL]").
print(f"\nCurrently configured (unconfirmed) routes in ep_long_daily.py:")
print(f"  ROUTE_ENTRY  = {eng.ROUTE_ENTRY!r}")
print(f"  ROUTE_STOP   = {eng.ROUTE_STOP!r}")
print(f"  ROUTE_ADJUST = {eng.ROUTE_ADJUST!r}")
print(f"  ROUTE_LADDER = {eng.ROUTE_LADDER!r}")
print(f"  ROUTE_EXIT   = {eng.ROUTE_EXIT!r}")

eng.send_line(sock, "GET RouteStatus")
lines = drain(3.0, "GET RouteStatus response (bare, no argument)")
if not any(l.upper().startswith("$ROUTESTATUS") for l in lines):
    print("\nNo $RouteStatus lines came back for the bare command -- it may require")
    print("a specific route name argument instead of listing all routes. Trying a")
    print("few common/plausible ones as a probe (harmless -- read-only query):")
    for probe in ["SMAT", "ARCA", "PRO20", "REB25", "RGEL", "SMRTL", "TWP5"]:
        eng.send_line(sock, f"GET RouteStatus {probe}")
        drain(1.0)

print("\nDone -- no orders were placed by this script. Report back whatever")
print("$RouteStatus lines (if any) printed above, and/or open a manual order")
print("ticket in the DAS GUI for this account and tell me what routes appear")
print("in its Route dropdown -- that's the most reliable source of truth.")

eng.send_line(sock, "QUIT")
sock.close()
