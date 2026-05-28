"""Conversation + message tools over ghl.Conversations / ghl.ConversationMessages."""
from __future__ import annotations

from typing import Literal

from .base import curated, md


@curated
def recent_conversations(limit: int = 10) -> str:
    """Most recent conversations (who you last talked to), newest first.

    Use for "who is the latest conversation with?", "show recent chats",
    "most recent messages by conversation". Returns contact name/email/phone,
    last message direction/type/time, and a snippet of the last message body.
    """
    limit = max(1, min(limit, 100))
    sql = (
        "SELECT TOP (?) ContactName, ContactEmail, ContactPhone, "
        "LastMessageDirection, LastMessageType, LastMessageDateUtc, LastMessageBody "
        "FROM ghl.Conversations ORDER BY LastMessageDateUtc DESC"
    )
    return md(sql, [limit], cap=limit)


@curated
def recent_messages(
    limit: int = 20, direction: Literal["inbound", "outbound"] | None = None
) -> str:
    """Most recent individual messages across all conversations, newest first.

    Use for "latest messages", "what came in recently", "last few texts".
    Optional `direction` filter (inbound = from the lead, outbound = from us).
    Joins the contact name; message body is truncated.
    """
    limit = max(1, min(limit, 200))
    where = ""
    params: list = [limit]
    if direction:
        where = "WHERE m.Direction = ? "
        params.append(direction)
    sql = (
        "SELECT TOP (?) m.DateAddedUtc, m.Direction, m.MessageType, "
        "c.FullName AS Contact, m.Body FROM ghl.ConversationMessages m "
        "LEFT JOIN ghl.Contacts c ON c.ContactId = m.ContactId "
        f"{where}ORDER BY m.DateAddedUtc DESC"
    )
    return md(sql, params, cap=limit)
