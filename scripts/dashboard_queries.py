"""Executive dashboard queries — what a brokerage owner would ask.

Each query:
  - Prints the question
  - Runs the SQL
  - Renders top-N rows with sensible column widths

Run:
    .venv/bin/python scripts/dashboard_queries.py
    .venv/bin/python scripts/dashboard_queries.py --only N    # only query #N
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import pyodbc

# Load .env so GHL_SQL_* are picked up without shell exports.
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass


def conn() -> pyodbc.Connection:
    server = os.getenv("GHL_SQL_SERVER", "localhost,1433")
    user = os.getenv("GHL_SQL_USER", "sa")
    pw = os.environ["GHL_SQL_PASSWORD"]
    db = os.getenv("GHL_SQL_DATABASE", "dcr_warehouse")
    cs = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};UID={user};PWD={pw};DATABASE={db};"
        f"TrustServerCertificate=yes;Encrypt=no;"
    )
    return pyodbc.connect(cs, autocommit=True)


QUERIES = [
    {
        "title": "Q1 — Today's pipeline snapshot: opportunities by pipeline + status",
        "sql": """
            SELECT
                P.Name AS Pipeline,
                O.Status,
                COUNT_BIG(*) AS Opps,
                SUM(CASE WHEN O.DateAddedUtc >= DATEADD(DAY, -7,  GETUTCDATE()) THEN 1 ELSE 0 END) AS AddedLast7d
            FROM ghl.Opportunities O
            LEFT JOIN ghl.Pipelines P ON P.PipelineId = O.PipelineId
            GROUP BY P.Name, O.Status
            ORDER BY COUNT_BIG(*) DESC;
        """,
    },
    {
        "title": "Q2 — Top 10 stages by opp count (bottleneck identification)",
        "sql": """
            SELECT TOP 10
                P.Name  AS Pipeline,
                S.Name  AS Stage,
                COUNT_BIG(*) AS Opps
            FROM ghl.Opportunities O
            JOIN ghl.PipelineStages S ON S.PipelineStageId = O.PipelineStageId
            JOIN ghl.Pipelines     P ON P.PipelineId      = O.PipelineId
            GROUP BY P.Name, S.Name, S.Position
            ORDER BY Opps DESC;
        """,
    },
    {
        "title": "Q3 — This-week lead source attribution (by Tag, since Source is empty)",
        "sql": """
            SELECT TOP 15
                CT.TagSlug,
                COUNT_BIG(DISTINCT C.ContactId) AS NewLeadsThisWeek
            FROM ghl.Contacts C
            CROSS APPLY STRING_SPLIT(ISNULL(C.Tags, ''), '|') AS s
            CROSS APPLY (VALUES (LTRIM(RTRIM(LOWER(s.value))))) AS CT(TagSlug)
            WHERE CT.TagSlug <> ''
              AND C.DateAddedUtc >= DATEADD(DAY, -7, GETUTCDATE())
            GROUP BY CT.TagSlug
            ORDER BY NewLeadsThisWeek DESC;
        """,
    },
    {
        "title": "Q4 — Agent leaderboard: outbound msgs this week & reply rate",
        "sql": """
            SELECT TOP 10
                U.FullName,
                LB.LeadsAssigned,
                LB.MsgsOutLast7,
                LB.ReplyRatePct
            FROM ghl.vw_AgentLeaderboard LB
            LEFT JOIN ghl.Users U ON U.UserId = LB.UserId
            ORDER BY LB.MsgsOutLast7 DESC;
        """,
    },
    {
        "title": "Q5 — Response-time SLA: convs replied <5min vs the rest",
        "sql": """
            SELECT
                ResponseBucket,
                COUNT(*) AS Convs,
                CAST(100.0 * COUNT(*) / SUM(COUNT(*)) OVER () AS DECIMAL(5,2)) AS Pct
            FROM ghl.vw_ResponseTime
            GROUP BY ResponseBucket
            ORDER BY CASE ResponseBucket
                WHEN '<1min' THEN 1 WHEN '<5min' THEN 2 WHEN '<1hr' THEN 3
                WHEN '<1day' THEN 4 WHEN '>=1day' THEN 5 ELSE 6 END;
        """,
    },
    {
        "title": "Q6 — Stale lead cleanup candidates (per agent: cold + dormant)",
        "sql": """
            SELECT TOP 10
                U.FullName,
                SUM(CASE WHEN DecayBucket = 'Cold'    THEN 1 ELSE 0 END) AS Cold,
                SUM(CASE WHEN DecayBucket = 'Dormant' THEN 1 ELSE 0 END) AS Dormant,
                COUNT_BIG(*) AS TotalAssigned
            FROM ghl.vw_ActivityDecay AD
            LEFT JOIN ghl.Users U ON U.UserId = AD.AssignedToUserId
            WHERE AD.AssignedToUserId IS NOT NULL AND AD.AssignedToUserId <> ''
            GROUP BY U.FullName
            ORDER BY (SUM(CASE WHEN DecayBucket IN ('Cold','Dormant') THEN 1 ELSE 0 END)) DESC;
        """,
    },
    {
        "title": "Q7 — Highest-engagement tags (min 500 contacts) — best vendor lists",
        "sql": """
            SELECT TOP 10
                TagSlug,
                Contacts,
                EngagedContacts,
                CAST(EngagedPct AS DECIMAL(5,2)) AS EngPct
            FROM ghl.vw_TagEngagement
            WHERE Contacts >= 500
            ORDER BY EngagedPct DESC;
        """,
    },
    {
        "title": "Q8 — Dead lists (min 1000 contacts, 0% engagement)",
        "sql": """
            SELECT TagSlug, Contacts, EngagedContacts
            FROM ghl.vw_TagEngagement
            WHERE Contacts >= 1000 AND EngagedPct = 0
            ORDER BY Contacts DESC;
        """,
    },
    {
        "title": "Q9 — Cohort progression: weekly funnel last 8 weeks",
        "sql": """
            SELECT TOP 8
                LeadWeek,
                LeadsInCohort,
                Engaged_7d,
                Engaged_30d,
                Opp_30d,
                Won_90d
            FROM ghl.vw_FunnelCohort
            ORDER BY LeadWeek DESC;
        """,
    },
    {
        "title": "Q10 — Hourly outbound SMS volume (when's the blast?)",
        "sql": """
            SELECT HourOfDay, SUM(MsgCount) AS Msgs
            FROM ghl.vw_MessageHeatmap
            WHERE Direction = 'outbound' AND MessageType = 'TYPE_SMS'
            GROUP BY HourOfDay
            ORDER BY HourOfDay;
        """,
    },
    {
        "title": "Q11 — Hot leads waiting for human reply (inbound w/o outbound follow-up, last 24h)",
        "sql": """
            WITH last_outbound AS (
                SELECT ConversationId, MAX(DateAddedUtc) AS LastOutboundUtc
                FROM ghl.ConversationMessages
                WHERE Direction = 'outbound'
                GROUP BY ConversationId
            ),
            last_inbound AS (
                SELECT ConversationId, MAX(DateAddedUtc) AS LastInboundUtc
                FROM ghl.ConversationMessages
                WHERE Direction = 'inbound'
                GROUP BY ConversationId
            )
            SELECT TOP 25
                C.ConversationId,
                C.ContactName,
                LI.LastInboundUtc,
                DATEDIFF(HOUR, LI.LastInboundUtc, GETUTCDATE()) AS HoursSinceReply,
                U.FullName AS AssignedTo
            FROM ghl.Conversations C
            JOIN last_inbound  LI ON LI.ConversationId = C.ConversationId
            LEFT JOIN last_outbound LO ON LO.ConversationId = C.ConversationId
            LEFT JOIN ghl.Contacts CT ON CT.ContactId = C.ContactId
            LEFT JOIN ghl.Users   U  ON U.UserId = CT.AssignedToUserId
            WHERE LI.LastInboundUtc >= DATEADD(HOUR, -24, GETUTCDATE())
              AND (LO.LastOutboundUtc IS NULL OR LO.LastOutboundUtc < LI.LastInboundUtc)
            ORDER BY LI.LastInboundUtc DESC;
        """,
    },
    {
        "title": "Q12 — Stale opps in Initial Engagement (haven't moved in 30+ days)",
        "sql": """
            SELECT TOP 15
                P.Name AS Pipeline,
                S.Name AS Stage,
                COUNT_BIG(*) AS StaleOpps,
                AVG(DATEDIFF(DAY, O.DateLastStageChangeUtc, GETUTCDATE())) AS AvgDaysSinceMove
            FROM ghl.Opportunities O
            JOIN ghl.Pipelines     P ON P.PipelineId = O.PipelineId
            JOIN ghl.PipelineStages S ON S.PipelineStageId = O.PipelineStageId
            WHERE O.Status = 'open'
              AND O.DateLastStageChangeUtc < DATEADD(DAY, -30, GETUTCDATE())
            GROUP BY P.Name, S.Name
            ORDER BY StaleOpps DESC;
        """,
    },
    {
        "title": "Q13 — Daily lead trend (last 30 days)",
        "sql": """
            SELECT
                CAST(DateAddedUtc AS DATE) AS LeadDate,
                COUNT_BIG(*) AS NewContacts
            FROM ghl.Contacts
            WHERE DateAddedUtc >= DATEADD(DAY, -30, GETUTCDATE())
            GROUP BY CAST(DateAddedUtc AS DATE)
            ORDER BY LeadDate DESC;
        """,
    },
    {
        "title": "Q14 — Reply-rate by lead source (tag-based)",
        "sql": """
            SELECT TOP 20
                CT.TagSlug AS Source,
                COUNT_BIG(DISTINCT C.ContactId) AS Leads,
                SUM(CASE WHEN E.ContactId IS NOT NULL THEN 1 ELSE 0 END) AS Engaged,
                CAST(100.0 * SUM(CASE WHEN E.ContactId IS NOT NULL THEN 1 ELSE 0 END)
                     / NULLIF(COUNT_BIG(DISTINCT C.ContactId), 0) AS DECIMAL(5,2)) AS EngPct
            FROM ghl.ContactTags CT
            JOIN ghl.Contacts C ON C.ContactId = CT.ContactId
            LEFT JOIN (
                SELECT DISTINCT C2.ContactId
                FROM ghl.Conversations C2
                JOIN ghl.ConversationMessages M ON M.ConversationId = C2.ConversationId
                WHERE M.Direction = 'inbound'
            ) E ON E.ContactId = C.ContactId
            WHERE CT.TagSlug IN (
                'reisift','datasift','propstream','leadsonar','pinpoint',
                'baltimore city','maryland','washington dc','pg county','anne arundel county',
                'preforclosure','financial distress','senior absentee','vacants','stacked owner occupant'
            )
            GROUP BY CT.TagSlug
            ORDER BY EngPct DESC;
        """,
    },
    {
        "title": "Q15 — Conversation throughput by agent (msgs/day, last 7d)",
        "sql": """
            SELECT TOP 10
                U.FullName AS Agent,
                COUNT_BIG(DISTINCT M.ConversationId) AS Convs,
                SUM(CASE WHEN M.Direction = 'outbound' THEN 1 ELSE 0 END) AS Outbound7d,
                SUM(CASE WHEN M.Direction = 'inbound'  THEN 1 ELSE 0 END) AS Inbound7d,
                CAST(SUM(CASE WHEN M.Direction = 'outbound' THEN 1 ELSE 0 END) / 7.0
                     AS DECIMAL(8,1)) AS AvgOutboundPerDay
            FROM ghl.ConversationMessages M
            JOIN ghl.Conversations         CV ON CV.ConversationId = M.ConversationId
            JOIN ghl.Contacts              C  ON C.ContactId       = CV.ContactId
            JOIN ghl.Users                 U  ON U.UserId          = C.AssignedToUserId
            WHERE M.DateAddedUtc >= DATEADD(DAY, -7, GETUTCDATE())
            GROUP BY U.FullName
            ORDER BY Outbound7d DESC;
        """,
    },
    {
        "title": "Q16 — Wins ledger (every won opp, with assigned agent + days-to-close)",
        "sql": """
            SELECT
                O.OpportunityId,
                O.Name,
                U.FullName AS Agent,
                P.Name AS Pipeline,
                DATEDIFF(DAY, O.DateAddedUtc, O.DateClosedUtc) AS DaysToClose,
                O.DateClosedUtc
            FROM ghl.Opportunities O
            LEFT JOIN ghl.Users     U ON U.UserId = O.AssignedToUserId
            LEFT JOIN ghl.Pipelines P ON P.PipelineId = O.PipelineId
            WHERE O.Status = 'won'
            ORDER BY O.DateClosedUtc DESC;
        """,
    },
    {
        "title": "Q17 — Conversion stage map (Initial → Seller → Closed by pipeline)",
        "sql": """
            SELECT
                P.Name AS Pipeline,
                COUNT_BIG(*) AS TotalOpps,
                SUM(CASE WHEN S.Name LIKE '%Sold%' OR S.Name LIKE '%Closed%' OR S.Name LIKE '%Won%' THEN 1 ELSE 0 END) AS ClosedStage,
                SUM(CASE WHEN S.Name LIKE '%Appointment%' THEN 1 ELSE 0 END) AS AppointmentStage,
                SUM(CASE WHEN S.Name LIKE '%Respond%' OR S.Name LIKE '%Reply%' THEN 1 ELSE 0 END) AS RespondStage,
                SUM(CASE WHEN S.Name LIKE '%SMS%' THEN 1 ELSE 0 END) AS SMSStage
            FROM ghl.Opportunities O
            JOIN ghl.Pipelines     P ON P.PipelineId = O.PipelineId
            JOIN ghl.PipelineStages S ON S.PipelineStageId = O.PipelineStageId
            GROUP BY P.Name
            ORDER BY TotalOpps DESC;
        """,
    },
    {
        "title": "Q18 — Phone-data quality: contacts with missing or invalid phone",
        "sql": """
            SELECT
                SUM(CASE WHEN Phone IS NULL OR Phone = '' THEN 1 ELSE 0 END) AS NoPhone,
                SUM(CASE WHEN Phone IS NOT NULL AND Phone <> '' AND LEN(Phone) < 10 THEN 1 ELSE 0 END) AS InvalidShort,
                SUM(CASE WHEN Phone LIKE '+1%' THEN 1 ELSE 0 END) AS E164USFormat,
                SUM(CASE WHEN Phone NOT LIKE '+%' AND Phone <> '' THEN 1 ELSE 0 END) AS NonE164,
                COUNT_BIG(*) AS Total
            FROM ghl.Contacts;
        """,
    },
    {
        "title": "Q19 — Tag co-occurrence: top pairs (which tags appear together?)",
        "sql": """
            SELECT TOP 15
                A.TagSlug AS TagA,
                B.TagSlug AS TagB,
                COUNT_BIG(*) AS BothCount
            FROM ghl.ContactTags A
            JOIN ghl.ContactTags B
              ON A.ContactId = B.ContactId
             AND A.TagSlug < B.TagSlug
            GROUP BY A.TagSlug, B.TagSlug
            HAVING COUNT_BIG(*) >= 1000
            ORDER BY BothCount DESC;
        """,
    },
    {
        "title": "Q20 — Multi-touch contacts (how many SMS each contact got)",
        "sql": """
            SELECT
                CASE
                    WHEN MsgCount = 0 THEN '0_no_msgs'
                    WHEN MsgCount = 1 THEN '1_msg'
                    WHEN MsgCount BETWEEN 2 AND 3  THEN '2_3_msgs'
                    WHEN MsgCount BETWEEN 4 AND 5  THEN '4_5_msgs'
                    WHEN MsgCount BETWEEN 6 AND 10 THEN '6_10_msgs'
                    ELSE 'over_10'
                END AS Bucket,
                COUNT_BIG(*) AS Contacts
            FROM (
                SELECT C.ContactId, COUNT_BIG(M.MessageId) AS MsgCount
                FROM ghl.Contacts C
                LEFT JOIN ghl.Conversations CV ON CV.ContactId = C.ContactId
                LEFT JOIN ghl.ConversationMessages M ON M.ConversationId = CV.ConversationId
                    AND M.Direction = 'outbound' AND M.MessageType = 'TYPE_SMS'
                GROUP BY C.ContactId
            ) x
            GROUP BY CASE
                WHEN MsgCount = 0 THEN '0_no_msgs'
                WHEN MsgCount = 1 THEN '1_msg'
                WHEN MsgCount BETWEEN 2 AND 3  THEN '2_3_msgs'
                WHEN MsgCount BETWEEN 4 AND 5  THEN '4_5_msgs'
                WHEN MsgCount BETWEEN 6 AND 10 THEN '6_10_msgs'
                ELSE 'over_10' END
            ORDER BY MIN(MsgCount);
        """,
    },
]


def render(c: pyodbc.Cursor) -> None:
    cols = [d[0] for d in c.description]
    rows = c.fetchall()
    if not rows:
        print("  (no rows)")
        return
    widths = [
        max(len(cols[i]), max(len(str(r[i])[:32]) for r in rows))
        for i in range(len(cols))
    ]
    print("  " + "  ".join(c.ljust(w) for c, w in zip(cols, widths)))
    print("  " + "  ".join("-" * w for w in widths))
    for r in rows:
        print("  " + "  ".join(str(v)[:32].ljust(w) for v, w in zip(r, widths)))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", type=int, default=None, help="Run only one query (1..N)")
    args = ap.parse_args()

    c = conn().cursor()
    total = 0.0
    for i, q in enumerate(QUERIES, start=1):
        if args.only is not None and args.only != i:
            continue
        print(f"\n{'=' * 78}\n{q['title']}\n{'=' * 78}")
        t0 = time.monotonic()
        c.execute(q["sql"])
        render(c)
        dt = time.monotonic() - t0
        total += dt
        print(f"  ({dt*1000:.0f} ms)")
    print(f"\nTotal time: {total*1000:.0f} ms")
    return 0


if __name__ == "__main__":
    sys.exit(main())
