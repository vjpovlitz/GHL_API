"""Failure alerts for the refresh pipeline.

Channels are config-driven via .env (callers should load_dotenv first):
  ALERT_WEBHOOK_URL   Slack- or Discord-style incoming webhook. If set, POSTs the alert.
  ALERT_MACOS         "1"/"true"/"yes" forces a macOS banner; defaults on under macOS.

Best-effort by design: a failing alert channel must never mask the original
error, so each channel swallows its own exceptions and logs to stderr.
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys


def _macos_enabled() -> bool:
    raw = os.getenv("ALERT_MACOS")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes"}
    return platform.system() == "Darwin"


def _notify_macos(subject: str, body: str) -> None:
    first_line = body.splitlines()[0] if body else ""
    text = first_line.replace('"', "'")[:240]
    subj = subject.replace('"', "'")[:120]
    subprocess.run(
        ["osascript", "-e", f'display notification "{text}" with title "{subj}"'],
        check=False, capture_output=True, timeout=10,
    )


def _notify_webhook(url: str, subject: str, body: str) -> None:
    import httpx
    text = f"*{subject}*\n```\n{body[:1500]}\n```"
    # Slack reads "text", Discord reads "content"; send both so either accepts it.
    httpx.post(url, json={"text": text, "content": text}, timeout=10).raise_for_status()


def send_alert(subject: str, body: str = "") -> None:
    """Dispatch a failure alert to every configured channel. Never raises."""
    print(f"\n[alert] {subject}\n{body}", file=sys.stderr)

    if _macos_enabled():
        try:
            _notify_macos(subject, body)
        except Exception as e:  # noqa: BLE001
            print(f"[alert] macOS notification failed: {e}", file=sys.stderr)

    url = os.getenv("ALERT_WEBHOOK_URL", "").strip()
    if url:
        try:
            _notify_webhook(url, subject, body)
        except Exception as e:  # noqa: BLE001
            print(f"[alert] webhook POST failed: {e}", file=sys.stderr)
