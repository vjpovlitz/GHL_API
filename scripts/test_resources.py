"""Read-only test of contacts, conversations, and calendars resources.

Run with:  .venv/bin/python scripts/test_resources.py
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from ghl_api import GHLAPIError, GHLClient


def section(title: str) -> None:
    print(f"\n{'=' * 60}\n{title}\n{'=' * 60}")


def show(label: str, data, limit: int = 400) -> None:
    s = json.dumps(data, default=str, indent=2)
    if len(s) > limit:
        s = s[:limit] + f"\n... [truncated, {len(s)} chars total]"
    print(f"\n[{label}]\n{s}")


def try_call(label: str, fn, *args, **kwargs):
    try:
        result = fn(*args, **kwargs)
        print(f"OK  {label}")
        return result
    except GHLAPIError as e:
        print(f"ERR {label}  -> {e.status_code}: {e.payload}")
        return None
    except Exception as e:
        print(f"ERR {label}  -> {type(e).__name__}: {e}")
        return None


def main() -> None:
    client = GHLClient.from_env()
    print(f"Location: {client.default_location_id}")

    # ---------- Contacts ----------
    section("1. CONTACTS")

    listing = try_call("contacts.list(limit=3)", client.contacts.list, limit=3)
    contacts = (listing or {}).get("contacts", [])
    print(f"   -> {len(contacts)} returned")

    sample_contact_id = contacts[0]["id"] if contacts else None
    if sample_contact_id:
        detail = try_call(
            f"contacts.get({sample_contact_id})", client.contacts.get, sample_contact_id
        )
        if detail:
            show("contact detail", detail, limit=500)

    search_result = try_call(
        "contacts.search(pageLimit=2)",
        client.contacts.search,
        page_limit=2,
    )
    if search_result:
        total = search_result.get("total")
        hits = search_result.get("contacts", [])
        print(f"   -> total={total}, returned={len(hits)}")

    # ---------- Conversations ----------
    section("3. CONVERSATIONS")

    convs = try_call(
        "conversations.search(limit=3)", client.conversations.search, limit=3
    )
    conv_list = (convs or {}).get("conversations", [])
    print(f"   -> {len(conv_list)} returned (total={(convs or {}).get('total')})")

    if conv_list:
        cid = conv_list[0]["id"]
        msgs = try_call(
            f"conversations.messages({cid}, limit=3)",
            client.conversations.messages,
            cid,
            limit=3,
        )
        if msgs:
            inner = msgs.get("messages", {})
            mlist = inner.get("messages") if isinstance(inner, dict) else inner
            print(f"   -> {len(mlist or [])} messages in newest conversation")

    # ---------- Calendars ----------
    section("4. CALENDARS")

    cals = try_call("calendars.list()", client.calendars.list)
    cal_list = (cals or {}).get("calendars", [])
    print(f"   -> {len(cal_list)} calendars")
    for c in cal_list[:5]:
        print(f"      - {c.get('id')}  {c.get('name')}  ({c.get('calendarType')})")

    # Events for next 14 days, per calendar (endpoint requires userId/calendarId/groupId)
    now_ms = int(time.time() * 1000)
    end_ms = int((datetime.now(timezone.utc) + timedelta(days=14)).timestamp() * 1000)
    total_events = 0
    for c in cal_list:
        cal_id = c["id"]
        events = try_call(
            f"calendars.events(calendarId={cal_id[:8]}..., next 14d)",
            client.calendars.events,
            start_time=now_ms,
            end_time=end_ms,
            calendar_id=cal_id,
        )
        ev_list = (events or {}).get("events", [])
        total_events += len(ev_list)
        for e in ev_list[:2]:
            print(
                f"      - {e.get('id')}  {e.get('title')}  "
                f"{e.get('startTime')} -> {e.get('endTime')}"
            )
    print(f"   -> {total_events} total upcoming events across all calendars")

    # Free slots for the first calendar, next 7 days
    if cal_list:
        cid = cal_list[0]["id"]
        slots_end = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp() * 1000)
        slots = try_call(
            f"calendars.free_slots({cid}, next 7 days)",
            client.calendars.free_slots,
            cid,
            start_date=now_ms,
            end_date=slots_end,
        )
        if slots:
            day_count = len([k for k in slots.keys() if k != "traceId"])
            print(f"   -> free slot response covers {day_count} day buckets")
            show("free_slots sample", slots, limit=600)


if __name__ == "__main__":
    main()
