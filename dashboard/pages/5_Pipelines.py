"""Opportunity pipeline + stage analysis."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from _db import q

st.set_page_config(page_title="Pipelines", page_icon="🪈", layout="wide")
st.title("🪈 Opportunity Pipelines")
st.caption("Where are opps stuck? Which pipelines are converting?")

# ---- Pipeline summary ----
summary = q("""
    SELECT
        P.Name AS Pipeline,
        COUNT_BIG(*) AS Opps,
        SUM(CASE WHEN O.Status = 'open' THEN 1 ELSE 0 END) AS Open_,
        SUM(CASE WHEN O.Status = 'lost' THEN 1 ELSE 0 END) AS Lost,
        SUM(CASE WHEN O.Status = 'won'  THEN 1 ELSE 0 END) AS Won
    FROM ghl.Opportunities O
    LEFT JOIN ghl.Pipelines P ON P.PipelineId = O.PipelineId
    GROUP BY P.Name
    ORDER BY Opps DESC;
""")
st.subheader("Pipelines")
st.dataframe(summary, use_container_width=True, hide_index=True)

st.divider()

# ---- Stage drill-down ----
st.subheader("Stage distribution")
pipelines = summary["Pipeline"].dropna().tolist()
choice = st.selectbox("Pipeline", pipelines, index=0)

stages = q(f"""
    SELECT
        S.Position,
        S.Name AS Stage,
        COUNT_BIG(*) AS Opps,
        AVG(DATEDIFF(DAY, O.DateLastStageChangeUtc, GETUTCDATE())) AS AvgDaysIdle
    FROM ghl.Opportunities O
    JOIN ghl.PipelineStages S ON S.PipelineStageId = O.PipelineStageId
    JOIN ghl.Pipelines P     ON P.PipelineId = O.PipelineId
    WHERE P.Name = ?
    GROUP BY S.Position, S.Name
    ORDER BY S.Position;
""", (choice,))

if stages.empty:
    st.info("No opps in this pipeline.")
else:
    fig = px.funnel(stages, x="Opps", y="Stage", height=400)
    st.plotly_chart(fig, use_container_width=True)
    st.dataframe(stages, use_container_width=True, hide_index=True)

st.divider()

# ---- Wins ----
st.subheader("Wins ledger")
wins = q("""
    SELECT
        O.OpportunityId,
        O.Name,
        U.FullName AS Agent,
        P.Name AS Pipeline,
        O.DateAddedUtc,
        O.DateClosedUtc
    FROM ghl.Opportunities O
    LEFT JOIN ghl.Users     U ON U.UserId = O.AssignedToUserId
    LEFT JOIN ghl.Pipelines P ON P.PipelineId = O.PipelineId
    WHERE O.Status = 'won'
    ORDER BY ISNULL(O.DateClosedUtc, O.DateAddedUtc) DESC;
""")
st.metric("Total wins", len(wins))
st.dataframe(wins, use_container_width=True, hide_index=True)
