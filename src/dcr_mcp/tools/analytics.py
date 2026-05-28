"""KPI tools backed by the ghl.vw_* analytics views (deterministic rollups)."""
from __future__ import annotations

from typing import Literal, get_args

from ..db import MAX_ROWS_CEILING
from .base import check_choice, check_date, curated, md

AgentSort = Literal[
    "OppsWon", "OppsLost", "OppsTotal", "PipelineValueWon", "PipelineValueOpen",
    "LeadsAssigned", "LeadsLast30", "MsgsOutbound", "ReplyRatePct", "ApptsBooked",
]


@curated
def agent_leaderboard(order_by: AgentSort = "OppsWon", limit: int = 20) -> str:
    """Per-agent performance leaderboard (with agent names).

    Use for "top agents by X", "who closed the most deals", "rep activity".
    Columns: agent, leads assigned/last-30, outbound msgs, reply rate, opps
    total/won/lost, open & won pipeline value. Sorted by `order_by` descending.
    """
    limit = max(1, min(limit, 100))
    order_by = check_choice(order_by, get_args(AgentSort), "order_by")
    sql = (
        "SELECT TOP (?) u.FullName AS Agent, a.UserId, a.LeadsAssigned, "
        "a.LeadsLast30, a.MsgsOutbound, a.ReplyRatePct, a.OppsTotal, a.OppsWon, "
        "a.OppsLost, a.PipelineValueOpen, a.PipelineValueWon "
        "FROM ghl.vw_AgentLeaderboard a "
        "LEFT JOIN ghl.Users u ON u.UserId = a.UserId "
        f"ORDER BY a.[{order_by}] DESC"
    )
    return md(sql, [limit], cap=limit)


SourceSort = Literal[
    "PipelineValueWon", "LeadsTotal", "LeadsLast30", "OppsWon",
    "WinRatePct", "EngagedPct", "AvgValuePerLead",
]


@curated
def lead_source_roi(
    order_by: SourceSort = "LeadsTotal", limit: int = 25, min_leads: int = 0
) -> str:
    """ROI by lead source: volume, engagement, win rate, won value, value/lead.

    Use for "which lead sources perform best", "where do our leads come from".
    `min_leads` filters out tiny/noisy sources. Sorted by `order_by` descending.
    """
    limit = max(1, min(limit, 200))
    order_by = check_choice(order_by, get_args(SourceSort), "order_by")
    sql = (
        "SELECT TOP (?) LeadSource, LeadsTotal, LeadsLast30, EngagedContacts, "
        "OppsCreatedContacts, OppsWon, PipelineValueWon, AvgValuePerLead, "
        "WinRatePct, EngagedPct FROM ghl.vw_LeadSourceROI WHERE LeadsTotal >= ? "
        f"ORDER BY [{order_by}] DESC"
    )
    return md(sql, [limit, max(0, min_leads)], cap=limit)


@curated
def daily_lead_funnel(
    since: str | None = None,
    until: str | None = None,
    source: str | None = None,
    limit: int = 100,
) -> str:
    """Daily funnel (leads -> engaged -> booked -> opps -> won) with percentages.

    Use for "lead funnel for last week", "daily conversion trend". `since`/`until`
    are ISO dates 'YYYY-MM-DD' (optional); `source` filters one lead source.
    Newest days first.
    """
    limit = max(1, min(limit, MAX_ROWS_CEILING))
    where = ["1 = 1"]
    params: list = [limit]
    if since:
        where.append("LeadDate >= ?")
        params.append(check_date(since, "since"))
    if until:
        where.append("LeadDate <= ?")
        params.append(check_date(until, "until"))
    if source:
        where.append("LeadSource = ?")
        params.append(source)
    sql = (
        "SELECT TOP (?) LeadDate, LeadSource, LeadsCreated, EngagedContacts, "
        "ApptsBooked, OppsCreated, OppsWon, EngagedPct, BookedPct, WonPct "
        f"FROM ghl.vw_DailyLeadFunnel WHERE {' AND '.join(where)} "
        "ORDER BY LeadDate DESC, LeadsCreated DESC"
    )
    return md(sql, params, cap=limit)


@curated
def funnel_cohort(weeks: int = 12) -> str:
    """Weekly lead cohorts with N-day conversion windows (engaged/booked/won).

    Use for "cohort analysis", "how do leads convert over time by signup week".
    Returns the most recent `weeks` cohorts (by LeadWeek), newest first.
    """
    weeks = max(1, min(weeks, 104))
    sql = (
        "SELECT TOP (?) LeadWeek, LeadsInCohort, Engaged_7d, Engaged_30d, "
        "Booked_30d, Opp_30d, Opp_90d, Won_30d, Won_90d, Engaged_7d_Pct, "
        "Won_90d_Pct FROM ghl.vw_FunnelCohort ORDER BY LeadWeek DESC"
    )
    return md(sql, [weeks], cap=weeks)


@curated
def response_time_summary() -> str:
    """Distribution of first-response latency, aggregated by ResponseBucket.

    Use for "how fast do we respond to leads", "response time breakdown". Shows
    conversation count and avg/min/max response seconds per bucket (fastest first).
    """
    sql = (
        "SELECT ResponseBucket, COUNT(*) AS Conversations, "
        "AVG(CAST(ResponseSeconds AS BIGINT)) AS AvgSeconds, "
        "MIN(ResponseSeconds) AS MinSeconds, MAX(ResponseSeconds) AS MaxSeconds "
        "FROM ghl.vw_ResponseTime GROUP BY ResponseBucket ORDER BY AvgSeconds"
    )
    return md(sql, cap=50)


@curated
def message_heatmap(
    direction: Literal["inbound", "outbound"] | None = None, limit: int = 50
) -> str:
    """Message volume by Direction x DayOfWeek (1=Sun) x HourOfDay (UTC).

    Use for "when are we busiest", "best time of day for replies". Aggregated over
    message type. Optional `direction` filter. Busiest slots first.
    """
    limit = max(1, min(limit, MAX_ROWS_CEILING))
    where = ""
    params: list = [limit]
    if direction:
        where = "WHERE Direction = ? "
        params.append(direction)
    sql = (
        "SELECT TOP (?) Direction, DayOfWeek, HourOfDay, SUM(MsgCount) AS MsgCount "
        f"FROM ghl.vw_MessageHeatmap {where}"
        "GROUP BY Direction, DayOfWeek, HourOfDay ORDER BY MsgCount DESC"
    )
    return md(sql, params, cap=limit)


TagSort = Literal[
    "Contacts", "EngagedContacts", "OppsContacts", "WonOpps", "WonValue",
    "EngagedPct", "WinPct",
]


@curated
def tag_engagement(order_by: TagSort = "Contacts", limit: int = 25) -> str:
    """Per-tag engagement: contacts, engaged, opps, won opps + value, percentages.

    Use for "which tags convert best", "engagement by tag". Sorted by `order_by`
    descending.
    """
    limit = max(1, min(limit, 200))
    order_by = check_choice(order_by, get_args(TagSort), "order_by")
    sql = (
        "SELECT TOP (?) TagSlug, Contacts, EngagedContacts, OppsContacts, "
        "WonOpps, WonValue, EngagedPct, WinPct FROM ghl.vw_TagEngagement "
        f"ORDER BY [{order_by}] DESC"
    )
    return md(sql, [limit], cap=limit)


@curated
def activity_decay_summary() -> str:
    """How stale the contact base is: contact counts per DecayBucket.

    Use for "how stale is our list", "how many dormant contacts". Buckets ordered
    from most-recently-active to most-stale.
    """
    sql = (
        "SELECT DecayBucket, COUNT(*) AS Contacts, "
        "MIN(DaysSinceActivity) AS MinDays, MAX(DaysSinceActivity) AS MaxDays "
        "FROM ghl.vw_ActivityDecay GROUP BY DecayBucket ORDER BY MinDays"
    )
    return md(sql, cap=50)
