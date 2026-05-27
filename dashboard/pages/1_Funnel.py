"""Daily Lead Funnel — engagement & conversion by lead date."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from _db import q

st.set_page_config(page_title="Funnel", page_icon="🪜", layout="wide")
st.title("🪜 Daily Lead Funnel")
st.caption("Stages: Lead → Engaged → Opp Created → Won. Source attribution.")

# ---- Filters ----
col1, col2 = st.columns([1, 3])
days = col1.selectbox("Window", [7, 14, 30, 60, 90, 180], index=2)
group_by_source = col1.checkbox("Break out by source", value=False)

# ---- Pull data ----
where_date = f"LeadDate >= DATEADD(DAY, -{days}, GETUTCDATE())"
if group_by_source:
    sql = f"""
        SELECT LeadDate, LeadSource,
               SUM(LeadsCreated) AS Leads,
               SUM(EngagedContacts) AS Engaged,
               SUM(OppsCreated) AS Opps,
               SUM(OppsWon) AS Won
        FROM ghl.vw_DailyLeadFunnel
        WHERE {where_date}
        GROUP BY LeadDate, LeadSource
        ORDER BY LeadDate DESC, Leads DESC;
    """
else:
    sql = f"""
        SELECT LeadDate,
               SUM(LeadsCreated) AS Leads,
               SUM(EngagedContacts) AS Engaged,
               SUM(OppsCreated) AS Opps,
               SUM(OppsWon) AS Won
        FROM ghl.vw_DailyLeadFunnel
        WHERE {where_date}
        GROUP BY LeadDate
        ORDER BY LeadDate;
    """
df = q(sql)

if df.empty:
    st.info(f"No funnel rows in last {days} days.")
    st.stop()

# ---- Totals ----
totals = df[["Leads", "Engaged", "Opps", "Won"]].sum()
c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Leads", f"{int(totals['Leads']):,}")
c2.metric("Engaged", f"{int(totals['Engaged']):,}",
          f"{100*totals['Engaged']/max(totals['Leads'],1):.1f}%")
c3.metric("Opps Created", f"{int(totals['Opps']):,}",
          f"{100*totals['Opps']/max(totals['Leads'],1):.1f}%")
c4.metric("Won", f"{int(totals['Won']):,}",
          f"{100*totals['Won']/max(totals['Leads'],1):.2f}%")
c5.metric("Days", f"{df['LeadDate'].nunique()}")

st.divider()

# ---- Chart ----
if group_by_source:
    st.subheader("Leads by source (stacked)")
    fig = px.bar(df, x="LeadDate", y="Leads", color="LeadSource", height=380)
    st.plotly_chart(fig, use_container_width=True)
else:
    st.subheader("Daily funnel")
    fig = px.line(
        df.melt(id_vars=["LeadDate"], value_vars=["Leads", "Engaged", "Opps", "Won"],
                var_name="Stage", value_name="Count"),
        x="LeadDate", y="Count", color="Stage", height=380,
    )
    st.plotly_chart(fig, use_container_width=True)

# ---- Table ----
st.subheader("Raw funnel rows")
st.dataframe(df, use_container_width=True, hide_index=True)
