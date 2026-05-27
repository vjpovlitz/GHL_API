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


# ---------- Opportunities ----------

OPPORTUNITY_COLUMNS: list[str] = [
    "OpportunityId",
    "LocationId",
    "PipelineId",
    "PipelineStageId",
    "ContactId",
    "AssignedToUserId",
    "Name",
    "Status",
    "MonetaryValue",
    "Source",
    "LostReasonId",
    "DateAddedUtc",
    "DateUpdatedUtc",
    "DateLastStageChangeUtc",
    "DateClosedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_opportunity(o: dict, *, extracted_at: str) -> dict:
    oid = clean_id(o.get("id"))
    contact = o.get("contact") or {}
    return {
        "OpportunityId": oid,
        "LocationId": clean_id(o.get("locationId")),
        "PipelineId": clean_id(o.get("pipelineId")),
        "PipelineStageId": clean_id(o.get("pipelineStageId") or o.get("stageId")),
        "ContactId": clean_id(o.get("contactId") or contact.get("id")),
        "AssignedToUserId": clean_id(o.get("assignedTo")),
        "Name": clean_text(o.get("name"), max_len=255),
        "Status": clean_text(o.get("status"), max_len=32),
        "MonetaryValue": clean_int(o.get("monetaryValue")),
        "Source": clean_text(o.get("source"), max_len=100),
        "LostReasonId": clean_id(o.get("lostReasonId")),
        "DateAddedUtc": clean_utc_ts(o.get("createdAt") or o.get("dateAdded")),
        "DateUpdatedUtc": clean_utc_ts(o.get("updatedAt") or o.get("dateUpdated")),
        "DateLastStageChangeUtc": clean_utc_ts(o.get("lastStageChangeAt") or o.get("lastStatusChangeAt")),
        "DateClosedUtc": clean_utc_ts(o.get("dateClosed") or o.get("closedAt")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": oid,
        "ExtractedAtUtc": extracted_at,
    }


# ---------- Pipelines (defs) ----------

PIPELINE_COLUMNS: list[str] = [
    "PipelineId",
    "LocationId",
    "Name",
    "DateAddedUtc",
    "DateUpdatedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]

PIPELINE_STAGE_COLUMNS: list[str] = [
    "PipelineStageId",
    "PipelineId",
    "LocationId",
    "Name",
    "Position",
    "ShowInFunnel",
    "ShowInPieChart",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_pipeline(p: dict, *, extracted_at: str) -> dict:
    pid = clean_id(p.get("id"))
    return {
        "PipelineId": pid,
        "LocationId": clean_id(p.get("locationId")),
        "Name": clean_text(p.get("name"), max_len=200),
        "DateAddedUtc": clean_utc_ts(p.get("dateAdded") or p.get("createdAt")),
        "DateUpdatedUtc": clean_utc_ts(p.get("dateUpdated") or p.get("updatedAt")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": pid,
        "ExtractedAtUtc": extracted_at,
    }


def map_pipeline_stage(s: dict, *, pipeline_id: str, location_id: str, extracted_at: str) -> dict:
    sid = clean_id(s.get("id"))
    return {
        "PipelineStageId": sid,
        "PipelineId": clean_id(pipeline_id),
        "LocationId": clean_id(location_id),
        "Name": clean_text(s.get("name"), max_len=200),
        "Position": clean_int(s.get("position") or s.get("order")),
        "ShowInFunnel": clean_bit(s.get("showInFunnel")),
        "ShowInPieChart": clean_bit(s.get("showInPieChart")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": sid,
        "ExtractedAtUtc": extracted_at,
    }


# ---------- Users (agents) ----------

USER_COLUMNS: list[str] = [
    "UserId",
    "LocationId",
    "FirstName",
    "LastName",
    "FullName",
    "Email",
    "Phone",
    "Role",
    "RoleType",
    "IsActive",
    "DateAddedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_user(u: dict, *, extracted_at: str) -> dict:
    uid = clean_id(u.get("id"))
    role_info = u.get("roles") or {}
    full = " ".join(filter(None, [u.get("firstName"), u.get("lastName")])).strip()
    return {
        "UserId": uid,
        "LocationId": clean_id(u.get("locationId")),
        "FirstName": clean_text(u.get("firstName"), max_len=100),
        "LastName": clean_text(u.get("lastName"), max_len=100),
        "FullName": clean_text(u.get("name") or full, max_len=200),
        "Email": clean_email(u.get("email"))[:254],
        "Phone": clean_phone(u.get("phone"))[:20],
        "Role": clean_text(role_info.get("role") if isinstance(role_info, dict) else u.get("role"), max_len=50),
        "RoleType": clean_text(role_info.get("type") if isinstance(role_info, dict) else u.get("type"), max_len=50),
        "IsActive": clean_bit(not u.get("deleted", False)),
        "DateAddedUtc": clean_utc_ts(u.get("dateAdded") or u.get("createdAt")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": uid,
        "ExtractedAtUtc": extracted_at,
    }


# ---------- Calendar Events / Appointments ----------

APPOINTMENT_COLUMNS: list[str] = [
    "AppointmentId",
    "LocationId",
    "CalendarId",
    "ContactId",
    "AssignedToUserId",
    "Title",
    "AppointmentStatus",
    "Source",
    "StartTimeUtc",
    "EndTimeUtc",
    "DateAddedUtc",
    "DateUpdatedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


CUSTOM_FIELD_COLUMNS: list[str] = [
    "CustomFieldId",
    "LocationId",
    "Model",
    "FieldKey",
    "Name",
    "DataType",
    "Placeholder",
    "Position",
    "IsRequired",
    "DateAddedUtc",
    "SourceSystem",
    "SourceSystemId",
    "ExtractedAtUtc",
]


def map_custom_field(cf: dict, *, location_id: str, extracted_at: str) -> dict:
    cid = clean_id(cf.get("id"))
    return {
        "CustomFieldId": cid,
        "LocationId": clean_id(cf.get("locationId") or location_id),
        "Model": clean_text(cf.get("model"), max_len=32),
        "FieldKey": clean_text(cf.get("fieldKey") or cf.get("key"), max_len=128),
        "Name": clean_text(cf.get("name"), max_len=255),
        "DataType": clean_text(cf.get("dataType"), max_len=32),
        "Placeholder": clean_text(cf.get("placeholder"), max_len=255),
        "Position": clean_int(cf.get("position")),
        "IsRequired": clean_bit(cf.get("isRequired")),
        "DateAddedUtc": clean_utc_ts(cf.get("dateAdded") or cf.get("createdAt")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": cid,
        "ExtractedAtUtc": extracted_at,
    }


def map_appointment(a: dict, *, extracted_at: str) -> dict:
    aid = clean_id(a.get("id"))
    users = a.get("users") or []
    assigned = ""
    if isinstance(users, list) and users:
        first = users[0]
        assigned = first if isinstance(first, str) else (first or {}).get("id", "")
    return {
        "AppointmentId": aid,
        "LocationId": clean_id(a.get("locationId")),
        "CalendarId": clean_id(a.get("calendarId")),
        "ContactId": clean_id(a.get("contactId")),
        "AssignedToUserId": clean_id(assigned or a.get("assignedUserId")),
        "Title": clean_text(a.get("title"), max_len=255),
        "AppointmentStatus": clean_text(a.get("appointmentStatus") or a.get("status"), max_len=32),
        "Source": clean_text(a.get("source"), max_len=100),
        "StartTimeUtc": clean_utc_ts(a.get("startTime")),
        "EndTimeUtc": clean_utc_ts(a.get("endTime")),
        "DateAddedUtc": clean_utc_ts(a.get("dateAdded") or a.get("createdAt")),
        "DateUpdatedUtc": clean_utc_ts(a.get("dateUpdated") or a.get("updatedAt")),
        "SourceSystem": SOURCE_SYSTEM,
        "SourceSystemId": aid,
        "ExtractedAtUtc": extracted_at,
    }
