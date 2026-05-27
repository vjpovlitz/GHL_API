from __future__ import annotations

import time

from ghl_api.throttle import Throttle


def _hdrs(rem=None, mx=None, interval_ms=None, daily=None):
    h = {}
    if rem is not None:
        h["x-ratelimit-remaining"] = str(rem)
    if mx is not None:
        h["x-ratelimit-max"] = str(mx)
    if interval_ms is not None:
        h["x-ratelimit-interval-milliseconds"] = str(interval_ms)
    if daily is not None:
        h["x-ratelimit-daily-remaining"] = str(daily)
    return h


def test_observe_populates_state():
    t = Throttle()
    t.observe(_hdrs(rem=95, mx=100, interval_ms=10000, daily=199_000))
    assert t.burst_remaining == 95
    assert t.burst_max == 100
    assert t.burst_interval_s == 10.0
    assert t.daily_remaining == 199_000
    assert t.requests_total == 1


def test_observe_ignores_missing_headers():
    t = Throttle()
    t.observe({})
    assert t.burst_remaining is None
    assert t.daily_remaining is None
    assert t.requests_total == 1


def test_observe_ignores_garbage_values():
    t = Throttle()
    t.observe({"x-ratelimit-remaining": "not-a-number"})
    assert t.burst_remaining is None


def test_before_request_sleeps_to_min_interval():
    t = Throttle()
    t.before_request()  # first call: no prior ts -> no sleep
    start = time.monotonic()
    t.before_request()  # second call: should sleep close to _MIN_INTERVAL_S
    elapsed = time.monotonic() - start
    assert elapsed >= 0.10  # _MIN_INTERVAL_S is 0.12
    assert elapsed < 0.5


def test_burst_exhausted_waits_for_window():
    t = Throttle()
    t.observe(_hdrs(rem=0, interval_ms=200))  # tiny window so the test is fast
    # _wanted_interval should be the full window
    assert t._wanted_interval() == 0.2


def test_daily_low_triggers_slow_path():
    t = Throttle()
    t.observe(_hdrs(rem=80, daily=100))
    w = t._wanted_interval()
    assert w >= 0.5  # daily-low path kicks in


def test_burst_headroom_pad():
    t = Throttle()
    t.observe(_hdrs(rem=5, interval_ms=10000))
    w = t._wanted_interval()
    # With rem=5 < 20 headroom, padded interval should exceed min.
    assert w > 0.12
