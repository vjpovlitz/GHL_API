"""POC: which tags correlate with engagement (replied) and conversion (won)?

Reads Contacts + Conversations + Messages CSVs and rolls up by tag.
Mirrors sql/views/vw_TagEngagement.sql.

Run:
    .venv/bin/python scripts/poc_tag_engagement.py [--min-contacts 200]
"""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"


def _iter_csv(glob: str):
    for p in sorted(EXPORT_DIR.glob(glob)):
        with p.open(encoding="utf-8-sig", newline="") as f:
            yield from csv.DictReader(f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-contacts", type=int, default=200,
                    help="Only show tags with at least this many contacts.")
    ap.add_argument("--top", type=int, default=30,
                    help="Top N rows by engaged-pct.")
    args = ap.parse_args()

    # 1. Contact -> tag set (slug form)
    contact_tags: dict[str, set[str]] = {}
    for r in _iter_csv("Contacts_part_*.csv"):
        cid = r.get("ContactId") or ""
        tags_raw = r.get("Tags") or ""
        if not cid or not tags_raw:
            continue
        contact_tags[cid] = {t.strip().lower() for t in tags_raw.split("|") if t.strip()}

    # 2. conv -> contact
    conv_to_contact: dict[str, str] = {}
    for r in _iter_csv("Conversations_part_*.csv"):
        cid = r.get("ConversationId") or ""
        contact = r.get("ContactId") or ""
        if cid and contact:
            conv_to_contact[cid] = contact

    # 3. engaged contacts (have inbound message)
    engaged: set[str] = set()
    for r in _iter_csv("ConversationMessages_part_*.csv"):
        if r.get("Direction") != "inbound":
            continue
        conv = r.get("ConversationId") or ""
        contact = conv_to_contact.get(conv) or r.get("ContactId") or ""
        if contact:
            engaged.add(contact)

    # 4. Roll up by tag
    tag_contacts: dict[str, int] = defaultdict(int)
    tag_engaged: dict[str, int] = defaultdict(int)
    for cid, tags in contact_tags.items():
        is_eng = cid in engaged
        for tag in tags:
            tag_contacts[tag] += 1
            if is_eng:
                tag_engaged[tag] += 1

    rows = []
    for tag, count in tag_contacts.items():
        if count < args.min_contacts:
            continue
        eng = tag_engaged.get(tag, 0)
        pct = (100.0 * eng / count) if count else 0
        rows.append((tag, count, eng, pct))

    print(f"Tags with >= {args.min_contacts} contacts: {len(rows):,}")
    print()
    print(f"Top {args.top} by engagement %:")
    print(f"{'EngPct':>7}  {'Engaged':>7}  {'Contacts':>8}  Tag")
    print("-" * 72)
    rows.sort(key=lambda r: -r[3])
    for tag, count, eng, pct in rows[:args.top]:
        print(f"{pct:>6.1f}%  {eng:>7,}  {count:>8,}  {tag}")

    print()
    print(f"Bottom {args.top} by engagement % (most ignored):")
    print(f"{'EngPct':>7}  {'Engaged':>7}  {'Contacts':>8}  Tag")
    print("-" * 72)
    rows.sort(key=lambda r: r[3])
    for tag, count, eng, pct in rows[:args.top]:
        print(f"{pct:>6.1f}%  {eng:>7,}  {count:>8,}  {tag}")

    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
