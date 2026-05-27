"""GHL Warehouse Dashboard — Streamlit entry point.

Launch:
    .venv/bin/streamlit run dashboard/app.py
"""
from __future__ import annotations

import streamlit as st

from _db import q

st.set_page_config(
    page_title="DCR GHL Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("📊 DCR GoHighLevel Warehouse")
st.caption("Live KPIs across contacts, conversations, opportunities, and engagement.")

# ---- Top tiles ----
totals = q("""
    SELECT
        (SELECT COUNT_BIG(*) FROM ghl.Contacts)              AS Contacts,
        (SELECT COUNT_BIG(*) FROM ghl.Conversations)         AS Conversations,
        (SELECT COUNT_BIG(*) FROM ghl.ConversationMessages)  AS Messages,
        (SELECT COUNT_BIG(*) FROM ghl.Opportunities)         AS Opportunities,
        (SELECT COUNT_BIG(*) FROM ghl.Opportunities WHERE Status = 'won') AS Won,
        (SELECT COUNT_BIG(*) FROM ghl.Contacts WHERE DateAddedUtc >= DATEADD(DAY, -7, GETUTCDATE())) AS NewLeads7d
""").iloc[0]

col1, col2, col3, col4, col5, col6 = st.columns(6)
col1.metric("Contacts",       f"{totals['Contacts']:,}")
col2.metric("Conversations",  f"{totals['Conversations']:,}")
col3.metric("Messages",       f"{totals['Messages']:,}")
col4.metric("Opportunities",  f"{totals['Opportunities']:,}")
col5.metric("Won (all-time)", f"{int(totals['Won']):,}")
col6.metric("New leads (7d)", f"{int(totals['NewLeads7d']):,}")

st.divider()

# ---- Daily lead trend ----
st.subheader("Daily new leads — last 60 days")
trend = q("""
    SELECT
        CAST(DateAddedUtc AS DATE) AS LeadDate,
        COUNT_BIG(*) AS NewLeads
    FROM ghl.Contacts
    WHERE DateAddedUtc >= DATEADD(DAY, -60, GETUTCDATE())
    GROUP BY CAST(DateAddedUtc AS DATE)
    ORDER BY LeadDate;
""")
if not trend.empty:
    st.bar_chart(trend.set_index("LeadDate")["NewLeads"], height=260)
else:
    st.info("No leads in the last 60 days.")

# ---- Engagement summary ----
st.subheader("Engagement at a glance")
col_a, col_b = st.columns(2)

with col_a:
    st.caption("Response-time bucket distribution")
    rt = q("""
        SELECT ResponseBucket, COUNT(*) AS Convs
        FROM ghl.vw_ResponseTime
        GROUP BY ResponseBucket
        ORDER BY CASE ResponseBucket
            WHEN '<1min' THEN 1 WHEN '<5min' THEN 2 WHEN '<1hr' THEN 3
            WHEN '<1day' THEN 4 WHEN '>=1day' THEN 5 ELSE 6 END;
    """)
    st.bar_chart(rt.set_index("ResponseBucket")["Convs"], height=260)

with col_b:
    st.caption("Activity decay (lifecycle freshness)")
    decay = q("""
        SELECT DecayBucket, COUNT_BIG(*) AS Contacts
        FROM ghl.vw_ActivityDecay
        GROUP BY DecayBucket
        ORDER BY CASE DecayBucket
            WHEN 'Hot' THEN 1 WHEN 'Warm' THEN 2 WHEN 'Cooling' THEN 3
            WHEN 'Cold' THEN 4 WHEN 'Dormant' THEN 5 ELSE 6 END;
    """)
    st.bar_chart(decay.set_index("DecayBucket")["Contacts"], height=260)

st.divider()
st.caption("Use the sidebar to drill into Funnel · Agents · Engagement · Tags · Pipelines.")
