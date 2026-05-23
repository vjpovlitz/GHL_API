"""Column definitions and API-row -> CSV-row mappers.

Single source of truth used by both the one-shot POC script and the
batch extractor. If you change a column here, you change it everywhere.
"""
from __future__ import annotations

from datetime import datetime, timezone

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

SOURCE_SYSTEM = "GoHighLevel"


def now_utc_iso() -> str:
    n = datetime.now(timezone.utc)
    return n.strftime("%Y-%m-%dT%H:%M:%S.") + f"{n.microsecond // 1000:03d}Z"


# ---------- Contacts ----------

CONTACT_COLUMNS: list[str] = [
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


def map_contact(c: dict, *, extracted_at: str) -> dict:
    full = " ".join(filter(None, [c.get("firstName"), c.get("lastName")])).strip()
    cid = clean_id(c.get("id"))
    return {
        "ContactId": cid,
        "LocationId": clean_id(c.get("locationId")),
        "FirstName": clean_text(c.get("firstName"), max_len=100),
        "LastName": clean_text(c.get("lastName"), max_len=100),
        "FullName": clean_text(c.get("contactName") or full, max_len=200),
        "Email": clean_email(c.get("email"))[:254],
        "Phone": clean_phone(c.get("phone"))[:20],
        "ContactType": clean_text(c.get("type"), max_len=32),
        "Source": clean_text(c.get("source"), max_len=100),
        "AssignedToUserId": clean_id(c.get("assignedTo")),
        "Address1": clean_text(c.get("address1"), max_len=255),
        "City": clean_text(c.get("city"), max_len=100),
        "State": clean_text(c.get("state"), max_len=50),
        "PostalCode": clean_text(c.get("postalCode"), max_len=20),
        "Country": clean_text(c.get("country"), max_len=8),
        "DateOfBirth": clean_date(c.get("dateOfBirth")),
        "Tags": clean_text(c.get("tags")),
        "DateAddedUtc": clean_utc_ts(c.get("dateAdded")),
        "DateUpdatedUtc": clean_utc_ts(c.get("dateUpdated")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": cid,
        "ExtractedAtUtc": extracted_at,
    }


# ---------- Conversations ----------

CONVERSATION_COLUMNS: list[str] = [
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


def map_conversation(c: dict, *, extracted_at: str) -> dict:
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
        "ContactName": clean_text(c.get("fullName") or c.get("contactName"), max_len=200),
        "ContactEmail": clean_email(c.get("email"))[:254],
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
        "ExtractedAtUtc": extracted_at,
    }


# ---------- Messages ----------

MESSAGE_COLUMNS: list[str] = [
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


def map_message(
    m: dict,
    *,
    conversation_id: str,
    contact_id: str,
    location_id: str,
    extracted_at: str,
) -> dict:
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
        "ExtractedAtUtc": extracted_at,
    }
