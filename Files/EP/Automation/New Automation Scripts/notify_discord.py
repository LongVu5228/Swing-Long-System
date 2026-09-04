"""
Discord incoming-webhook alerts. Set environment variable:

  DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...

Create a webhook: Server Settings -> Integrations -> Webhooks -> New Webhook.
If the variable is unset, notify() is a no-op (scripts keep running).

Rate-limit hardening (cross-process):
  - A Windows file lock in %TEMP% serializes all sends across every script that
    imports this module (short-side Day1/Day2/4AM/Launcher AND this long-side
    engine all share the same limiter, since Discord's rate limit is per-webhook
    or per-IP, not per-process).
  - A shared timestamp file enforces a minimum gap between sends.
  - Small random jitter reduces collision probability on simultaneous wakeups.
  - 429 and 5xx responses trigger automatic retry with the Discord-supplied retry_after.
  - All lock/file errors fall back to a direct send so trading code is never blocked.

Identical copy of Old Swing Short Scripts/Algo/algo/notify_discord.py -- kept
byte-for-byte the same on purpose so both automation folders share one proven
implementation. If you fix a bug here, port it to the other copy too.
"""

from __future__ import annotations

import json
import msvcrt
import os
import random
import tempfile
import time
import urllib.error
import urllib.request

WEBHOOK_ENV = "DISCORD_WEBHOOK_URL"
_TIMEOUT_SEC = 12
_MAX_RETRIES = 4
_DEFAULT_RETRY_SEC = 1.0

# Minimum time between successive webhook sends (cross-process).
_MIN_SEND_GAP_SEC = 0.45

# Random jitter added before each send to reduce thundering-herd collisions.
_JITTER_MIN_SEC = 0.05
_JITTER_MAX_SEC = 0.15

# Lock/state files written to %TEMP% at runtime (never touch trading folder).
_LOCK_FILE  = os.path.join(tempfile.gettempdir(), "discord_notify.lock")
_STATE_FILE = os.path.join(tempfile.gettempdir(), "discord_notify_state.json")

# Maximum time to wait for the cross-process lock before giving up and sending anyway.
_LOCK_WAIT_SEC = 6.0

# Discord/Cloudflare may return 403 if User-Agent is missing or blocked.
_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (compatible; TradingAutomation/1.0; +https://example.invalid)",
}


def _webhook_url() -> str:
    u = (os.environ.get(WEBHOOK_ENV) or "").strip()
    if len(u) >= 2 and u[0] == u[-1] and u[0] in "\"'":
        u = u[1:-1].strip()
    return u


def _read_last_send_ts() -> float:
    try:
        with open(_STATE_FILE, "r") as f:
            return float(json.load(f).get("last_send_ts", 0.0))
    except Exception:
        return 0.0


def _write_last_send_ts(ts: float) -> None:
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump({"last_send_ts": ts}, f)
    except Exception:
        pass


def _acquire_lock(handle) -> bool:
    """Try to acquire a Windows byte-range lock; return True on success."""
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        return True
    except OSError:
        return False


def _release_lock(handle) -> None:
    try:
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    except Exception:
        pass


def _send_request(req: urllib.request.Request) -> None:
    """Send with 429/5xx retry + backoff. Raises on final failure."""
    for attempt in range(_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=_TIMEOUT_SEC) as resp:
                if resp.status >= 400:
                    print(f"[notify_discord] HTTP {resp.status}")
            return
        except urllib.error.HTTPError as e:
            detail = ""
            retry_after = None
            try:
                body_text = e.read().decode("utf-8", errors="replace")[:500]
                if body_text.strip():
                    detail = f" | body: {body_text.strip()}"
                parsed = json.loads(body_text) if body_text.strip().startswith("{") else {}
                retry_after = parsed.get("retry_after")
            except Exception:
                pass

            should_retry = e.code == 429 or (500 <= e.code <= 599)
            if should_retry and attempt < _MAX_RETRIES:
                wait_sec = _DEFAULT_RETRY_SEC * (2 ** attempt)
                try:
                    if retry_after is not None:
                        wait_sec = max(float(retry_after), 0.05)
                except Exception:
                    pass
                time.sleep(wait_sec)
                continue

            print(f"[notify_discord] HTTP error {e.code}: {e.reason}{detail}")
            return
        except Exception as exc:
            if attempt < _MAX_RETRIES:
                time.sleep(_DEFAULT_RETRY_SEC * (2 ** attempt))
                continue
            print(f"[notify_discord] failed: {exc}")
            return


def notify(message: str, title: str | None = None, *, color: int = 0x3498DB) -> None:
    """Post to Discord. Uses an embed when `title` is set, else plain content."""
    url = _webhook_url()
    if not url:
        return

    if "/api/webhooks/" not in url:
        print(
            "[notify_discord] DISCORD_WEBHOOK_URL must be a webhook "
            "(copy URL from Integrations -> Webhooks; it must contain /api/webhooks/)."
        )
        return

    text = (message or "").strip()
    if not text:
        return

    if title:
        payload = {
            "embeds": [
                {
                    "title": str(title)[:256],
                    "description": text[:4096],
                    "color": int(color) & 0xFFFFFF,
                }
            ]
        }
    else:
        payload = {"content": text[:2000]}

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers=dict(_HEADERS),
        method="POST",
    )

    # --- Cross-process serialization + rate-gap enforcement ---
    lock_handle = None
    lock_acquired = False
    try:
        lock_handle = open(_LOCK_FILE, "a+")
        deadline = time.monotonic() + _LOCK_WAIT_SEC
        while time.monotonic() < deadline:
            if _acquire_lock(lock_handle):
                lock_acquired = True
                break
            time.sleep(0.05)

        if lock_acquired:
            # Enforce minimum gap between sends.
            last_ts = _read_last_send_ts()
            elapsed = time.time() - last_ts
            if elapsed < _MIN_SEND_GAP_SEC:
                time.sleep(_MIN_SEND_GAP_SEC - elapsed)

        # Jitter to reduce simultaneous-wakeup collisions.
        time.sleep(random.uniform(_JITTER_MIN_SEC, _JITTER_MAX_SEC))

        _send_request(req)

        if lock_acquired:
            _write_last_send_ts(time.time())

    except Exception:
        # Safety fallback: if anything in the locking path fails, send directly.
        try:
            _send_request(req)
        except Exception:
            pass
    finally:
        if lock_acquired and lock_handle:
            _release_lock(lock_handle)
        if lock_handle:
            try:
                lock_handle.close()
            except Exception:
                pass
