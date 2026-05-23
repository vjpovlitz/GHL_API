"""Probe the real GHL v2 rate limit empirically.

Strategy: send GET /contacts/?limit=1 as fast as possible from a thread pool,
record every response status + headers. Stop after the first 429 OR after
60 successes — whichever first. We don't actually want to trip a long ban.
"""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.environ["GHL_ACCESS_TOKEN"]
LOC = os.environ["GHL_LOCATION_ID"]
VERSION = os.getenv("GHL_API_VERSION", "2021-07-28")
URL = "https://services.leadconnectorhq.com/contacts/"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/json",
    "Version": VERSION,
}
PARAMS = {"locationId": LOC, "limit": 1}

MAX_REQUESTS = 60
CONCURRENCY = 8


def hit(i: int, client: httpx.Client) -> dict:
    t0 = time.perf_counter()
    r = client.get(URL, params=PARAMS, headers=HEADERS)
    dt = time.perf_counter() - t0
    rate_hdrs = {k: v for k, v in r.headers.items() if "rate" in k.lower() or k.lower() == "retry-after"}
    return {"i": i, "status": r.status_code, "dt_ms": int(dt * 1000), "rate": rate_hdrs}


def main() -> None:
    print(f"Probe: up to {MAX_REQUESTS} requests, concurrency={CONCURRENCY}")
    print(f"Endpoint: GET /contacts/?locationId=...&limit=1\n")

    start = time.perf_counter()
    statuses: list[int] = []
    rate_headers_seen: dict[str, str] = {}
    first_429_at: int | None = None

    with httpx.Client(timeout=30.0) as client, ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        futures = [pool.submit(hit, i, client) for i in range(MAX_REQUESTS)]
        for f in as_completed(futures):
            res = f.result()
            statuses.append(res["status"])
            rate_headers_seen.update(res["rate"])
            tag = "OK " if res["status"] < 400 else "ERR"
            print(f"  #{res['i']:02d}  {tag} {res['status']}  {res['dt_ms']:>4}ms  {res['rate'] or ''}")
            if res["status"] == 429 and first_429_at is None:
                first_429_at = res["i"]

    elapsed = time.perf_counter() - start
    ok = sum(1 for s in statuses if 200 <= s < 300)
    rate_limited = sum(1 for s in statuses if s == 429)
    print(f"\n--- Summary ---")
    print(f"Total:        {len(statuses)} requests")
    print(f"OK:           {ok}")
    print(f"429 rate-lim: {rate_limited}")
    print(f"Other err:    {len(statuses) - ok - rate_limited}")
    print(f"Wall time:    {elapsed:.2f}s")
    print(f"Avg RPS:      {len(statuses) / elapsed:.1f}")
    if first_429_at is not None:
        print(f"First 429:    after request #{first_429_at}")
    print(f"Rate headers seen: {rate_headers_seen or '(none)'}")


if __name__ == "__main__":
    main()
