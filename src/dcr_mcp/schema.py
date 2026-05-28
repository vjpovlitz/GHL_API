"""Schema introspection + a DCR business glossary.

The glossary is the single most important context for a local model: it explains
what the warehouse means (stages, statuses, which view answers which question)
so the model picks the right tool or writes correct T-SQL instead of guessing.
"""
from __future__ import annotations

from .db import run_readonly

GLOSSARY = """\
# DCR warehouse (SQL Server, schema `ghl`)

CRM data for Dana Capital Realty, extracted from GoHighLevel. All timestamps are
UTC (columns end in `Utc`). This connection is READ-ONLY. T-SQL dialect: use
`SELECT TOP (n)`, NOT `LIMIT`. Date math: `DATEADD`, `DATEDIFF`, `GETUTCDATE()`.

## Core tables
- `ghl.Contacts` (~252k) — leads/people. Key cols: ContactId (PK), FullName,
  Email, Phone, Source (lead source), AssignedToUserId (owning agent),
  Tags (pipe-delimited string), DateAddedUtc.
- `ghl.Opportunities` (~253k) — deals. PipelineId, PipelineStageId, ContactId,
  AssignedToUserId, Status ('open'|'won'|'lost'|'abandoned'), MonetaryValue,
  Source, DateAddedUtc, DateClosedUtc.
- `ghl.Conversations` (~213k) / `ghl.ConversationMessages` (~278k) — messaging.
  Messages have Direction ('inbound'|'outbound'), MessageType (SMS/Email/etc.),
  Body, DateAddedUtc.
- `ghl.Pipelines` (10) / `ghl.PipelineStages` (68) — sales pipeline definitions;
  join Opportunities.PipelineStageId -> PipelineStages.PipelineStageId for the
  human stage Name, ordered by Position.
- `ghl.Users` (17) — agents/staff. UserId (PK), FullName, Email, Role, IsActive.
- `ghl.Tags` (108) — tag catalog. `ghl.ContactTags` (~1.6M) — exploded fact:
  one row per (ContactId, TagSlug); prefer this over splitting Contacts.Tags.
- `ghl.CustomFields` (115) — field DEFINITIONS only (per-contact values not loaded).
- `ghl.Appointments` — EMPTY (this org doesn't use GHL calendar appointments).

## Analytics views (schema `ghl`, prefix `vw_`) — prefer these for KPIs
- `vw_AgentLeaderboard` — per-agent (UserId) rollup: leads, message volume,
  reply rate, appts, opps won/lost, open vs won pipeline value.
- `vw_LeadSourceROI` — per lead Source: volume, engagement, win rate, won value,
  avg value per lead.
- `vw_DailyLeadFunnel` — per (LeadDate, LeadSource): leads -> engaged -> booked
  -> opps -> won, with conversion percentages.
- `vw_FunnelCohort` — weekly cohorts (LeadWeek) with N-day conversion windows.
- `vw_ResponseTime` — per-conversation first inbound -> first outbound latency
  (ResponseSeconds) bucketed (ResponseBucket).
- `vw_MessageHeatmap` — message counts by Direction x DayOfWeek x HourOfDay.
- `vw_TagEngagement` — per TagSlug: contacts, engagement, won opps + value.
- `vw_ActivityDecay` — per contact: days since last activity + DecayBucket.

Note: appointment-related numbers are ~0 because Appointments is empty; "booked"
metrics in the funnel views derive from opportunity/stage signals, not calendar.
"""


def _ghl_objects() -> dict[str, str]:
    """Map of allowed object name -> 'BASE TABLE' | 'VIEW' in the ghl schema."""
    cols, rows, _ = run_readonly(
        "SELECT TABLE_NAME, TABLE_TYPE FROM INFORMATION_SCHEMA.TABLES "
        "WHERE TABLE_SCHEMA = 'ghl' ORDER BY TABLE_NAME",
        max_rows=500,
    )
    return {r[0]: r[1] for r in rows}


def describe_schema() -> str:
    """Glossary + a compact list of every queryable table/view in `ghl`."""
    objs = _ghl_objects()
    tables = [n for n, t in objs.items() if t == "BASE TABLE"]
    views = [n for n, t in objs.items() if t == "VIEW"]
    lines = [GLOSSARY, "\n## Queryable objects (call describe_table for columns)"]
    lines.append("Tables: " + ", ".join(f"ghl.{t}" for t in tables))
    lines.append("Views:  " + ", ".join(f"ghl.{v}" for v in views))
    return "\n".join(lines)


def describe_table(name: str) -> str:
    """Columns + types for one ghl table or view (name validated against schema)."""
    bare = name.split(".")[-1].strip().strip("[]")
    objs = _ghl_objects()
    if bare not in objs:
        avail = ", ".join(sorted(objs)) or "(none)"
        return f"Unknown object 'ghl.{bare}'. Available: {avail}"
    cols, rows, _ = run_readonly(
        "SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE, CHARACTER_MAXIMUM_LENGTH "
        "FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA = 'ghl' AND TABLE_NAME = ? ORDER BY ORDINAL_POSITION",
        params=[bare],
        max_rows=500,
    )
    out = [f"ghl.{bare} ({objs[bare].lower()}) — {len(rows)} columns:"]
    for cname, dtype, nullable, maxlen in rows:
        t = f"{dtype}({maxlen})" if maxlen and maxlen > 0 else dtype
        null = "" if nullable == "YES" else " NOT NULL"
        out.append(f"  {cname}  {t}{null}")
    return "\n".join(out)
