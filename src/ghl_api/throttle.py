"""Adaptive throttle for the GHL v2 API.

Watches `x-ratelimit-*` headers on every response and sleeps before the
next request to keep us under the 100/10s burst limit and the 200k/day
limit. Designed to be a polite citizen — leaves headroom for other API
users on the same Private Integration Token.

Headers we read (empirically observed; see CLAUDE.md §5):
    x-ratelimit-max                       e.g. "100"
    x-ratelimit-interval-milliseconds     e.g. "10000"
    x-ratelimit-remaining                 burst window remaining
    x-ratelimit-daily-remaining           per-day remaining

Usage:
    throttle = Throttle()
    throttle.before_request()
    resp = http.get(...)
    throttle.observe(resp.headers)
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Mapping


# Floor we never drop below — keeps us at a polite sustained rate even
# when the server says we have plenty of headroom.
_MIN_INTERVAL_S = 0.12  # ~8 RPS ceiling

# When burst-remaining drops below this, we start padding the interval.
_BURST_HEADROOM = 20

# When daily-remaining drops below this, we slow down aggressively.
_DAILY_LOW_WATER = 5_000


@dataclass
class Throttle:
    burst_remaining: int | None = None
    burst_max: int | None = None
    burst_interval_s: float = 10.0
    daily_remaining: int | None = None
    last_request_ts: float = 0.0
    sleeps_total_s: float = 0.0
    requests_total: int = 0
    _history: list[float] = field(default_factory=list)  # not used yet, future

    def observe(self, headers: Mapping[str, str]) -> None:
        """Update internal state from a response's rate-limit headers."""
        self.requests_total += 1
        rem = _get_int(headers, "x-ratelimit-remaining")
        if rem is not None:
            self.burst_remaining = rem
        mx = _get_int(headers, "x-ratelimit-max")
        if mx is not None:
            self.burst_max = mx
        interval_ms = _get_int(headers, "x-ratelimit-interval-milliseconds")
        if interval_ms is not None and interval_ms > 0:
            self.burst_interval_s = interval_ms / 1000.0
        daily = _get_int(headers, "x-ratelimit-daily-remaining")
        if daily is not None:
            self.daily_remaining = daily

    def before_request(self) -> float:
        """Sleep enough to stay polite. Returns seconds slept."""
        now = time.monotonic()
        gap = now - self.last_request_ts if self.last_request_ts else 1e9
        wanted = self._wanted_interval()
        slept = 0.0
        if gap < wanted:
            slept = wanted - gap
            time.sleep(slept)
            self.sleeps_total_s += slept
        self.last_request_ts = time.monotonic()
        return slept

    def _wanted_interval(self) -> float:
        base = _MIN_INTERVAL_S
        # Burst-window pressure: as remaining drops, stretch the interval.
        if self.burst_remaining is not None and self.burst_remaining <= 0:
            # We've eaten the window. Wait for the full interval to reset.
            return self.burst_interval_s
        if self.burst_remaining is not None and self.burst_remaining < _BURST_HEADROOM:
            # Linear ramp: at headroom -> base, at 0 -> interval/headroom.
            scarcity = (_BURST_HEADROOM - self.burst_remaining) / _BURST_HEADROOM
            padded = base + scarcity * (self.burst_interval_s / max(_BURST_HEADROOM, 1))
            base = max(base, padded)
        # Daily-window pressure: if we're running low on the day, slow way down.
        if self.daily_remaining is not None and self.daily_remaining < _DAILY_LOW_WATER:
            # 0.5s floor when daily is tight; further degrade as it gets worse.
            scarcity = 1.0 - (max(self.daily_remaining, 0) / _DAILY_LOW_WATER)
            base = max(base, 0.5 + scarcity * 1.5)
        return base

    def stats(self) -> dict:
        return {
            "requests_total": self.requests_total,
            "sleeps_total_s": round(self.sleeps_total_s, 3),
            "burst_remaining": self.burst_remaining,
            "burst_max": self.burst_max,
            "burst_interval_s": self.burst_interval_s,
            "daily_remaining": self.daily_remaining,
        }


def _get_int(headers: Mapping[str, str], key: str) -> int | None:
    # httpx Headers is case-insensitive; dict-style isn't. Try both.
    raw = None
    if hasattr(headers, "get"):
        raw = headers.get(key) or headers.get(key.lower()) or headers.get(key.upper())
    if raw is None:
        return None
    try:
        return int(float(raw))
    except (TypeError, ValueError):
        return None
