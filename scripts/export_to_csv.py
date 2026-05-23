"""Extract Contacts, Conversations, and ConversationMessages to SQL-Server-shaped CSVs.

Run:
    .venv/bin/python scripts/export_to_csv.py

Output goes to data/exports/  (gitignored).
Implements the rules in DATA_RULES.md verbatim.
"""
from __future__ import annotations

import csv
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ghl_api import GHLClient
from ghl_api.sanitize import (
    clean_bit,
    clean_date,
    clean_email,
    clean_id,
    clean_int,
    clean_phone,
    clean_text,
    clean_utc_ts,
)

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"
SOURCE_SYSTEM = "GoHighLevel"
_NOW = datetime.now(timezone.utc)
EXTRACTED_AT_UTC = _NOW.strftime("%Y-%m-%dT%H:%M:%S.") + f"{_NOW.microsecond // 1000:03d}Z"

CONTACT_LIMIT = 100
CONVERSATION_LIMIT = 50
MESSAGES_PER_CONVERSATION = 20

# Per-column max length caps (applied during sanitization). Conservative defaults
# that match the NVARCHAR sizes in sql/create_tables.sql.
_MAXLEN_NAMES = 100
_MAXLEN_FULLNAME = 200
_MAXLEN_EMAIL = 254
_MAXLEN_SHORT = 100
_MAXLEN_MED = 255


# ---------- CSV writer (Rule 5) ----------

def write_csv(filename: str, columns: list[str], rows: Iterable[dict[str, Any]]) -> tuple[Path, int]:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = EXPORT_DIR / filename
    count = 0
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=columns,
            lineterminator="\r\n",
            quoting=csv.QUOTE_MINIMAL,
            extrasaction="ignore",
        )
        writer.writeheader()
        for row in rows:
            writer.writerow({c: row.get(c, "") for c in columns})
            count += 1
    return path, count


# ---------- Row mappers ----------

CONTACT_COLUMNS = [
    "ContactId",
    "LocationId",
    "FirstName",
    "LastName",
    "FullName",
    "Email",
    "Phone",
    "ContactType",
    "Source",
    "AssignedToUserId",
    "Address1",
    "City",
    "State",
    "PostalCode",
    "Country",
    "DateOfBirth",
    "Tags",
    "DateAddedUtc",
    "DateUpdatedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_contact(c: dict) -> dict:
    full = " ".join(filter(None, [c.get("firstName"), c.get("lastName")])).strip()
    cid = clean_id(c.get("id"))
    return {
        "ContactId": cid,
        "LocationId": clean_id(c.get("locationId")),
        "FirstName": clean_text(c.get("firstName"), max_len=_MAXLEN_NAMES),
        "LastName": clean_text(c.get("lastName"), max_len=_MAXLEN_NAMES),
        "FullName": clean_text(c.get("contactName") or full, max_len=_MAXLEN_FULLNAME),
        "Email": clean_email(c.get("email"))[:_MAXLEN_EMAIL],
        "Phone": clean_phone(c.get("phone"))[:20],
        "ContactType": clean_text(c.get("type"), max_len=32),
        "Source": clean_text(c.get("source"), max_len=_MAXLEN_SHORT),
        "AssignedToUserId": clean_id(c.get("assignedTo")),
        "Address1": clean_text(c.get("address1"), max_len=_MAXLEN_MED),
        "City": clean_text(c.get("city"), max_len=_MAXLEN_SHORT),
        "State": clean_text(c.get("state"), max_len=50),
        "PostalCode": clean_text(c.get("postalCode"), max_len=20),
        "Country": clean_text(c.get("country"), max_len=8),
        "DateOfBirth": clean_date(c.get("dateOfBirth")),
        "Tags": clean_text(c.get("tags")),
        "DateAddedUtc": clean_utc_ts(c.get("dateAdded")),
        "DateUpdatedUtc": clean_utc_ts(c.get("dateUpdated")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": cid,
        "ExtractedAtUtc": EXTRACTED_AT_UTC,
    }


CONVERSATION_COLUMNS = [
    "ConversationId",
    "LocationId",
    "ContactId",
    "ContactName",
    "ContactEmail",
    "ContactPhone",
    "LastMessageType",
    "LastMessageBody",
    "LastMessageDateUtc",
    "LastMessageDirection",
    "IsUnread",
    "IsStarred",
    "UnreadCount",
    "ConversationType",
    "DateAddedUtc",
    "DateUpdatedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_conversation(c: dict) -> dict:
    cid = clean_id(c.get("id"))
    unread_count = c.get("unreadCount")
    is_unread = None
    if unread_count is not None:
        try:
            is_unread = int(unread_count) > 0
        except (TypeError, ValueError):
            is_unread = None
    return {
        "ConversationId": cid,
        "LocationId": clean_id(c.get("locationId")),
        "ContactId": clean_id(c.get("contactId")),
        "ContactName": clean_text(c.get("fullName") or c.get("contactName"), max_len=_MAXLEN_FULLNAME),
        "ContactEmail": clean_email(c.get("email"))[:_MAXLEN_EMAIL],
        "ContactPhone": clean_phone(c.get("phone"))[:20],
        "LastMessageType": clean_text(c.get("lastMessageType"), max_len=64),
        "LastMessageBody": clean_text(c.get("lastMessageBody")),
        "LastMessageDateUtc": clean_utc_ts(c.get("lastMessageDate")),
        "LastMessageDirection": clean_text(c.get("lastMessageDirection"), max_len=16),
        "IsUnread": clean_bit(is_unread),
        "IsStarred": clean_bit(c.get("starred")),
        "UnreadCount": clean_int(unread_count),
        "ConversationType": clean_text(c.get("type"), max_len=32),
        "DateAddedUtc": clean_utc_ts(c.get("dateAdded")),
        "DateUpdatedUtc": clean_utc_ts(c.get("dateUpdated")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": cid,
        "ExtractedAtUtc": EXTRACTED_AT_UTC,
    }


MESSAGE_COLUMNS = [
    "MessageId",
    "ConversationId",
    "ContactId",
    "LocationId",
    "Direction",
    "MessageType",
    "Status",
    "Body",
    "HasAttachment",
    "DateAddedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_message(m: dict, conversation_id: str, contact_id: str, location_id: str) -> dict:
    atts = m.get("attachments") or []
    mid = clean_id(m.get("id"))
    return {
        "MessageId": mid,
        "ConversationId": clean_id(m.get("conversationId") or conversation_id),
        "ContactId": clean_id(m.get("contactId") or contact_id),
        "LocationId": clean_id(m.get("locationId") or location_id),
        "Direction": clean_text(m.get("direction"), max_len=16),
        "MessageType": clean_text(m.get("messageType") or m.get("type"), max_len=64),
        "Status": clean_text(m.get("status"), max_len=32),
        "Body": clean_text(m.get("body")),
        "HasAttachment": clean_bit(bool(atts)),
        "DateAddedUtc": clean_utc_ts(m.get("dateAdded")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": mid,
        "ExtractedAtUtc": EXTRACTED_AT_UTC,
    }


# ---------- Main ----------

def main() -> None:
    print("=" * 70)
    print("GHL -> CSV extraction (POC)")
    print(f"Extracted at: {EXTRACTED_AT_UTC}")
    print(f"Output dir:   {EXPORT_DIR}")
    print("=" * 70)

    client = GHLClient.from_env()
    location_id = client.default_location_id
    print(f"Location:     {location_id}")

    # --- Contacts ---
    print(f"\n[1/3] Pulling {CONTACT_LIMIT} contacts...")
    resp = client.contacts.list(limit=CONTACT_LIMIT)
    contacts = resp.get("contacts", [])
    rows = [map_contact(c) for c in contacts]
    path, n = write_csv("Contacts.csv", CONTACT_COLUMNS, rows)
    print(f"      wrote {n} rows -> {path.name}")

    # --- Conversations ---
    print(f"\n[2/3] Pulling {CONVERSATION_LIMIT} conversations...")
    resp = client.conversations.search(limit=CONVERSATION_LIMIT)
    conversations = resp.get("conversations", [])
    rows = [map_conversation(c) for c in conversations]
    path, n = write_csv("Conversations.csv", CONVERSATION_COLUMNS, rows)
    print(f"      wrote {n} rows -> {path.name}")

    # --- Messages ---
    print(f"\n[3/3] Pulling up to {MESSAGES_PER_CONVERSATION} messages per conversation...")
    all_messages: list[dict] = []
    for c in conversations:
        cid = c.get("id")
        if not cid:
            continue
        try:
            msg_resp = client.conversations.messages(cid, limit=MESSAGES_PER_CONVERSATION)
        except Exception as e:
            print(f"      WARN skip {cid}: {e}")
            continue
        inner = msg_resp.get("messages", {})
        msgs = inner.get("messages") if isinstance(inner, dict) else inner
        for m in (msgs or []):
            all_messages.append(
                map_message(m, cid, c.get("contactId", ""), c.get("locationId", ""))
            )
    path, n = write_csv("ConversationMessages.csv", MESSAGE_COLUMNS, all_messages)
    print(f"      wrote {n} rows -> {path.name}")

    # --- Summary ---
    print("\n" + "=" * 70)
    print("File summary:")
    print("=" * 70)
    for fn in ["Contacts.csv", "Conversations.csv", "ConversationMessages.csv"]:
        p = EXPORT_DIR / fn
        if p.exists():
            size_kb = p.stat().st_size / 1024
            print(f"  {fn:30}  {size_kb:8.1f} KB   {p}")

    # --- Self-validation gate: run audit, fail extract if any issues ---
    print("\n" + "=" * 70)
    print("Running audit gate...")
    print("=" * 70)
    audit_script = Path(__file__).resolve().parent / "audit_csv.py"
    result = subprocess.run(
        [sys.executable, str(audit_script)],
        check=False,
    )
    if result.returncode != 0:
        print("\nAUDIT FAILED — see issues above. Extraction did NOT pass gate.")
        sys.exit(2)
    print("\nAudit gate PASSED — files are SQL-Server safe.")


if __name__ == "__main__":
    main()
