"""Quick probe of supplementary endpoints we plan to backfill.

Run AFTER messages backfill is complete (to avoid throttle contention).
Verifies which endpoints work under our PIT, prints sample responses so
we can confirm field names before building extractor logic.

    .venv/bin/python scripts/probe_supp_endpoints.py
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from ghl_api import GHLClient  # noqa: E402
from ghl_api.exceptions import GHLAPIError  # noqa: E402


def show(label: str, fn) -> dict | None:
    print(f"\n=== {label} ===")
    try:
        resp = fn()
    except GHLAPIError as e:
        print(f"  ERROR {e.status_code}: {e}")
        if e.payload:
            print(f"  payload: {json.dumps(e.payload)[:400]}")
        return None
    if isinstance(resp, dict):
        # Print top-level keys + sample of the largest list value
        print(f"  keys: {list(resp.keys())}")
        for k, v in resp.items():
            if isinstance(v, list) and v:
                print(f"  {k}: {len(v)} items. First item keys: {list(v[0].keys())[:25]}")
                print(f"    sample: {json.dumps(v[0], default=str)[:600]}")
                break
        else:
            print(f"  sample: {json.dumps(resp, default=str)[:600]}")
    else:
        print(f"  type={type(resp).__name__} value={str(resp)[:400]}")
    return resp


def main() -> int:
    client = GHLClient.from_env()
    loc = client.require_location_id()
    print(f"Location: {loc}")

    # 1. Pipelines (small)
    pipelines_resp = show("Pipelines", lambda: client.pipelines.list())

    # 2. Opportunities (1 row)
    show("Opportunities (limit=1)", lambda: client.opportunities.search(limit=1))

    # 3. Users
    show("Users (skip=0 limit=5)", lambda: client.users.search(limit=5))

    # 4. Calendar events (last 7 days)
    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(days=7)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)
    # First we need a calendarId. Pull calendars list.
    cals_resp = show("Calendars list", lambda: client.calendars.list())
    cal_id = None
    if cals_resp:
        cals = cals_resp.get("calendars") or []
        if cals:
            cal_id = cals[0].get("id")
            print(f"  -> using calendarId={cal_id}")
    if cal_id:
        show(
            f"Calendar events (cal={cal_id[:8]}, last 7d)",
            lambda: client.calendars.events(
                start_time=start_ms, end_time=end_ms, calendar_id=cal_id
            ),
        )

    print("\n--- throttle ---")
    print(client.throttle.stats())
    return 0


if __name__ == "__main__":
    sys.exit(main())
