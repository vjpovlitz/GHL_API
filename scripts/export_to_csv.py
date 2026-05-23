"""Extract Contacts, Conversations, and ConversationMessages to SQL-Server-shaped CSVs.

Run:
    .venv/bin/python scripts/export_to_csv.py

Output goes to data/exports/  (gitignored).
Implements the rules in DATA_RULES.md verbatim.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ghl_api import GHLClient

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "exports"
SOURCE_SYSTEM = "GoHighLevel"
EXTRACTED_AT_UTC = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"

CONTACT_LIMIT = 100
CONVERSATION_LIMIT = 50
MESSAGES_PER_CONVERSATION = 20


# ---------- Rule enforcement helpers ----------

def to_str(v: Any) -> str:
    """Rule 3: missing -> empty string, never 'None'/'null'/'NaN'."""
    if v is None:
        return ""
    if isinstance(v, bool):  # bools serialized separately; if seen here, coerce
        return "1" if v else "0"
    if isinstance(v, (list, tuple)):
        return "|".join(str(x) for x in v if x is not None and x != "")
    if isinstance(v, dict):
        return json.dumps(v, separators=(",", ":"), ensure_ascii=False)
    s = str(v).strip()
    return "" if s.lower() in ("none", "null", "nan") else s


def to_bit(v: Any) -> str:
    """Rule 2: BIT -> '1' or '0' (empty if unknown)."""
    if v is None:
        return ""
    return "1" if bool(v) else "0"


def to_utc_ts(v: Any) -> str:
    """Rule 2: timestamps -> ISO 8601 UTC with Z. Empty if missing/unparseable.

    Accepts: ISO 8601 strings, epoch seconds, epoch milliseconds.
    """
    if v is None or v == "":
        return ""
    # Numeric: GHL Conversations API returns epoch ms here
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.strip().isdigit()):
        n = int(v)
        # >= 10^12 -> ms (year ~2001+); else seconds
        if n >= 10**12:
            n //= 1000
        dt = datetime.fromtimestamp(n, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
    s = str(v).strip()
    if s.endswith("Z") and "T" in s:
        return s
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"
    except ValueError:
        return ""  # Rule 3: bad input -> empty, not garbage


def to_date(v: Any) -> str:
    """Rule 2: DATE -> YYYY-MM-DD. Empty if missing."""
    if not v:
        return ""
    s = str(v).strip()
    return s[:10] if len(s) >= 10 else ""


def mask(v: str) -> str:
    """Rule 7: mask PII in console output after the 4th char."""
    if not v or len(v) <= 4:
        return v or ""
    return v[:4] + "*" * (len(v) - 4)


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
    return {
        "ContactId": to_str(c.get("id")),
        "LocationId": to_str(c.get("locationId")),
        "FirstName": to_str(c.get("firstName")),
        "LastName": to_str(c.get("lastName")),
        "FullName": to_str(c.get("contactName") or full),
        "Email": to_str(c.get("email")),
        "Phone": to_str(c.get("phone")),
        "ContactType": to_str(c.get("type")),
        "Source": to_str(c.get("source")),
        "AssignedToUserId": to_str(c.get("assignedTo")),
        "Address1": to_str(c.get("address1")),
        "City": to_str(c.get("city")),
        "State": to_str(c.get("state")),
        "PostalCode": to_str(c.get("postalCode")),
        "Country": to_str(c.get("country")),
        "DateOfBirth": to_date(c.get("dateOfBirth")),
        "Tags": to_str(c.get("tags")),
        "DateAddedUtc": to_utc_ts(c.get("dateAdded")),
        "DateUpdatedUtc": to_utc_ts(c.get("dateUpdated")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": to_str(c.get("id")),
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
    return {
        "ConversationId": to_str(c.get("id")),
        "LocationId": to_str(c.get("locationId")),
        "ContactId": to_str(c.get("contactId")),
        "ContactName": to_str(c.get("fullName") or c.get("contactName")),
        "ContactEmail": to_str(c.get("email")),
        "ContactPhone": to_str(c.get("phone")),
        "LastMessageType": to_str(c.get("lastMessageType")),
        "LastMessageBody": to_str(c.get("lastMessageBody")),
        "LastMessageDateUtc": to_utc_ts(c.get("lastMessageDate")),
        "LastMessageDirection": to_str(c.get("lastMessageDirection")),
        "IsUnread": to_bit(c.get("unreadCount", 0) > 0 if c.get("unreadCount") is not None else None),
        "IsStarred": to_bit(c.get("starred")),
        "UnreadCount": to_str(c.get("unreadCount")),
        "ConversationType": to_str(c.get("type")),
        "DateAddedUtc": to_utc_ts(c.get("dateAdded")),
        "DateUpdatedUtc": to_utc_ts(c.get("dateUpdated")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": to_str(c.get("id")),
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
    return {
        "MessageId": to_str(m.get("id")),
        "ConversationId": to_str(m.get("conversationId") or conversation_id),
        "ContactId": to_str(m.get("contactId") or contact_id),
        "LocationId": to_str(m.get("locationId") or location_id),
        "Direction": to_str(m.get("direction")),
        "MessageType": to_str(m.get("messageType") or m.get("type")),
        "Status": to_str(m.get("status")),
        "Body": to_str(m.get("body")),
        "HasAttachment": to_bit(bool(atts)),
        "DateAddedUtc": to_utc_ts(m.get("dateAdded")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": to_str(m.get("id")),
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
    print("Done. File summary:")
    print("=" * 70)
    for fn in ["Contacts.csv", "Conversations.csv", "ConversationMessages.csv"]:
        p = EXPORT_DIR / fn
        if p.exists():
            size_kb = p.stat().st_size / 1024
            print(f"  {fn:30}  {size_kb:8.1f} KB   {p}")


if __name__ == "__main__":
    main()
