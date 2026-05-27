"""POC: executive summary of what's in the warehouse so far.

Reads all available *_part_*.csv shards in data/exports/ and prints:
  - Totals per entity
  - Date coverage
  - Lead source top-N
  - Geographic top-N (state)
  - Message direction split + media types
  - Engagement % overall

Run:
    .venv/bin/python scripts/poc_exec_summary.py
"""
from __future__ import annotations

import csv
from collections import Counter
from datetime import datetime
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


def _iter_csv(glob: str):
    for p in sorted(EXPORT_DIR.glob(glob)):
        with p.open(encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)


def section(title: str):
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def main() -> int:
    # ---- Contacts ----
    section("CONTACTS")
    n = 0
    src_counter: Counter[str] = Counter()
    state_counter: Counter[str] = Counter()
    type_counter: Counter[str] = Counter()
    assigned: Counter[str] = Counter()
    date_min: str = "9999"
    date_max: str = "0000"

    for r in _iter_csv("Contacts_part_*.csv"):
        n += 1
        src_counter[r.get("Source") or "(unknown)"] += 1
        st = r.get("State") or ""
        if st:
            state_counter[st.upper()[:50]] += 1
        type_counter[r.get("ContactType") or "(unknown)"] += 1
        a = r.get("AssignedToUserId") or ""
        if a:
            assigned[a] += 1
        d = r.get("DateAddedUtc") or ""
        if d:
            if d < date_min:
                date_min = d
            if d > date_max:
                date_max = d

    print(f"  Total contacts:        {n:,}")
    print(f"  Date range:            {date_min[:10]}  ->  {date_max[:10]}")
    print(f"  Unique sources:        {len(src_counter):,}")
    print(f"  Unique states:         {len(state_counter):,}")
    print(f"  Assigned to agents:    {sum(assigned.values()):,} contacts across {len(assigned)} agents")
    print(f"\n  Top 10 sources:")
    for s, c in src_counter.most_common(10):
        print(f"    {c:>7,}  {s[:50]}")
    print(f"\n  Top 10 states:")
    for s, c in state_counter.most_common(10):
        print(f"    {c:>7,}  {s}")
    print(f"\n  Top 10 agents (by contact assignment):")
    for a, c in assigned.most_common(10):
        print(f"    {c:>7,}  {a}")

    # ---- Conversations ----
    section("CONVERSATIONS")
    nc = 0
    ctype_counter: Counter[str] = Counter()
    unread_total = 0
    starred_total = 0
    last_msg_min: str = "9999"
    last_msg_max: str = "0000"
    for r in _iter_csv("Conversations_part_*.csv"):
        nc += 1
        ctype_counter[r.get("ConversationType") or "(unknown)"] += 1
        try:
            unread_total += int(r.get("UnreadCount") or "0")
        except ValueError:
            pass
        if (r.get("IsStarred") or "") == "1":
            starred_total += 1
        d = r.get("LastMessageDateUtc") or ""
        if d:
            if d < last_msg_min:
                last_msg_min = d
            if d > last_msg_max:
                last_msg_max = d

    print(f"  Total conversations:   {nc:,}")
    print(f"  Last message range:    {last_msg_min[:10]}  ->  {last_msg_max[:10]}")
    print(f"  Total unread count:    {unread_total:,}")
    print(f"  Starred:               {starred_total:,}")
    print(f"\n  Conversation types:")
    for t, c in ctype_counter.most_common():
        print(f"    {c:>7,}  {t}")

    # ---- Messages ----
    section("MESSAGES")
    nm = 0
    dir_counter: Counter[str] = Counter()
    mtype_counter: Counter[str] = Counter()
    status_counter: Counter[str] = Counter()
    has_att = 0
    msg_date_min: str = "9999"
    msg_date_max: str = "0000"
    by_hour: Counter[int] = Counter()
    by_dow: Counter[int] = Counter()
    convs_with_inbound: set[str] = set()

    for r in _iter_csv("ConversationMessages_part_*.csv"):
        nm += 1
        d = r.get("Direction") or "(unknown)"
        dir_counter[d] += 1
        mtype_counter[r.get("MessageType") or "(unknown)"] += 1
        status_counter[r.get("Status") or "(unknown)"] += 1
        if (r.get("HasAttachment") or "") == "1":
            has_att += 1
        ds = r.get("DateAddedUtc") or ""
        if ds:
            if ds < msg_date_min:
                msg_date_min = ds
            if ds > msg_date_max:
                msg_date_max = ds
            try:
                dt = datetime.fromisoformat(ds.replace("Z", "+00:00"))
                by_hour[dt.hour] += 1
                by_dow[dt.weekday()] += 1
            except ValueError:
                pass
        if d == "inbound":
            convs_with_inbound.add(r.get("ConversationId") or "")

    print(f"  Total messages:        {nm:,}")
    print(f"  Date range:            {msg_date_min[:10]}  ->  {msg_date_max[:10]}")
    print(f"  Messages with attach:  {has_att:,}")
    print(f"  Convs with ≥1 inbound: {len(convs_with_inbound):,}  ({100.0 * len(convs_with_inbound) / max(nc, 1):.1f}% of all convs)")
    print(f"\n  Direction split:")
    for d, c in dir_counter.most_common():
        pct = 100.0 * c / nm
        print(f"    {c:>9,}  ({pct:5.1f}%)  {d}")
    print(f"\n  Top message types:")
    for t, c in mtype_counter.most_common(8):
        print(f"    {c:>9,}  {t}")
    print(f"\n  Top statuses:")
    for s, c in status_counter.most_common(8):
        print(f"    {c:>9,}  {s}")

    print(f"\n  By hour-of-day (UTC):")
    if by_hour:
        max_h = max(by_hour.values())
        for h in range(24):
            c = by_hour[h]
            bar = "#" * int(40 * c / max_h)
            print(f"    {h:02d}:00  {c:>8,}  {bar}")

    DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    print(f"\n  By day-of-week:")
    if by_dow:
        max_d = max(by_dow.values())
        for d in range(7):
            c = by_dow[d]
            bar = "#" * int(40 * c / max_d)
            print(f"    {DOW[d]}  {c:>9,}  {bar}")

    section("SUMMARY")
    print(f"  {n:,} contacts  |  {nc:,} conversations  |  {nm:,} messages")
    print(f"  Engagement rate: {100.0 * len(convs_with_inbound) / max(nc, 1):.1f}% of conversations got at least one inbound reply")
    print(f"  Source diversity: {len(src_counter)} sources (top = '{src_counter.most_common(1)[0][0] if src_counter else 'n/a'}')")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
