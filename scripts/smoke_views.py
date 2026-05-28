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
    pw = os.getenv("GHL_SQL_PASSWORD", "GhlDev_PassW0rd!")
    db = os.getenv("GHL_SQL_DATABASE", "dcr_warehouse")
    cs = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server};UID={user};PWD={pw};DATABASE={db};"
        f"TrustServerCertificate=yes;Encrypt=no;"
    )
    return pyodbc.connect(cs, autocommit=True)


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
