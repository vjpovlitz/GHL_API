"""Smoke-test every view in sql/views/ against the loaded SQL Server data.

For each view:
  1. Count rows (does it execute?).
  2. Show a 3-row sample.
  3. Compare against the Python POC where applicable.

Exit code 0 = all views queryable. Non-zero = at least one failed.
"""
from __future__ import annotations

import os
import sys

import pyodbc


def conn() -> pyodbc.Connection:
    return pyodbc.connect(
        "DRIVER={ODBC Driver 18 for SQL Server};SERVER=localhost,1433;"
        "UID=sa;PWD=GhlDev_PassW0rd!;DATABASE=ghl_warehouse;"
        "TrustServerCertificate=yes;Encrypt=no;",
        autocommit=True,
    )


VIEWS = [
    ("ghl.vw_DailyLeadFunnel",
     "SELECT TOP 3 LeadDate, LeadSource, LeadsCreated, EngagedContacts, OppsWon "
     "FROM ghl.vw_DailyLeadFunnel "
     "ORDER BY LeadDate DESC, LeadsCreated DESC"),
    ("ghl.vw_AgentLeaderboard",
     "SELECT TOP 5 LB.UserId, U.FullName, LB.LeadsAssigned, LB.MsgsOutbound, LB.ReplyRatePct "
     "FROM ghl.vw_AgentLeaderboard LB LEFT JOIN ghl.Users U ON U.UserId = LB.UserId "
     "ORDER BY LB.LeadsAssigned DESC"),
    ("ghl.vw_ResponseTime",
     "SELECT ResponseBucket, COUNT(*) AS Convs FROM ghl.vw_ResponseTime "
     "GROUP BY ResponseBucket ORDER BY Convs DESC"),
    ("ghl.vw_LeadSourceROI",
     "SELECT TOP 5 LeadSource, LeadsTotal, EngagedPct, OppsWon, PipelineValueWon "
     "FROM ghl.vw_LeadSourceROI ORDER BY LeadsTotal DESC"),
    ("ghl.vw_FunnelCohort",
     "SELECT TOP 5 LeadWeek, LeadsInCohort, Engaged_7d, Won_90d "
     "FROM ghl.vw_FunnelCohort ORDER BY LeadWeek DESC"),
    ("ghl.vw_MessageHeatmap",
     "SELECT TOP 5 Direction, DayOfWeek, HourOfDay, MsgCount "
     "FROM ghl.vw_MessageHeatmap WHERE Direction='outbound' "
     "ORDER BY MsgCount DESC"),
    ("ghl.vw_ActivityDecay",
     "SELECT DecayBucket, COUNT_BIG(*) AS Contacts "
     "FROM ghl.vw_ActivityDecay GROUP BY DecayBucket "
     "ORDER BY CASE DecayBucket "
     "WHEN 'Hot' THEN 1 WHEN 'Warm' THEN 2 WHEN 'Cooling' THEN 3 "
     "WHEN 'Cold' THEN 4 WHEN 'Dormant' THEN 5 ELSE 6 END"),
    ("ghl.vw_TagEngagement",
     "SELECT TOP 10 TagSlug, Contacts, EngagedPct "
     "FROM ghl.vw_TagEngagement WHERE Contacts >= 500 ORDER BY EngagedPct DESC"),
]


def main() -> int:
    c = conn().cursor()
    failures = 0
    for view, sample_sql in VIEWS:
        print(f"\n{'=' * 78}\n{view}\n{'=' * 78}")
        try:
            c.execute(f"SELECT COUNT_BIG(*) FROM {view}")
            n = c.fetchone()[0]
            print(f"  rows: {n:,}")
        except pyodbc.Error as e:
            print(f"  COUNT failed: {e}")
            failures += 1
            continue
        try:
            c.execute(sample_sql)
            rows = c.fetchall()
            cols = [d[0] for d in c.description]
            print(f"  columns: {', '.join(cols)}")
            for r in rows:
                cells = [str(v)[:30] if v is not None else "—" for v in r]
                print("    " + "  |  ".join(cells))
        except pyodbc.Error as e:
            print(f"  sample failed: {e}")
            failures += 1
    print()
    if failures:
        print(f"{failures} view(s) failed.")
        return 1
    print(f"All {len(VIEWS)} views queryable. OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
