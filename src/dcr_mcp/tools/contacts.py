"""Contact lookup over ghl.Contacts."""
from __future__ import annotations

from .base import curated, md


@curated
def find_contact(query: str, limit: int = 10) -> str:
    """Find contacts by partial match on name, email, or phone.

    Use for "look up John Smith", "find the contact with email x@y.com",
    "who is 555-1234". Returns name, email, phone, lead source, city/state, and
    the owning agent. Newest contacts first.
    """
    limit = max(1, min(limit, 100))
    like = f"%{query.strip()}%"
    sql = (
        "SELECT TOP (?) c.FullName, c.Email, c.Phone, c.Source, c.City, c.State, "
        "u.FullName AS Agent, c.DateAddedUtc FROM ghl.Contacts c "
        "LEFT JOIN ghl.Users u ON u.UserId = c.AssignedToUserId "
        "WHERE c.FullName LIKE ? OR c.Email LIKE ? OR c.Phone LIKE ? "
        "ORDER BY c.DateAddedUtc DESC"
    )
    return md(sql, [limit, like, like, like], cap=limit)
