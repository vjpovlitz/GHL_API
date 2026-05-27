"""Agent / SMS-persona leaderboard."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from _db import q

st.set_page_config(page_title="Agents", page_icon="🧑‍💼", layout="wide")
st.title("🧑‍💼 Agent / SMS-persona Leaderboard")
st.caption("Each row = one Willow/Nieko/Tyler persona (a phone number, not a human).")

df = q("""
    SELECT
        U.FullName,
        U.Email,
        LB.LeadsAssigned,
        LB.LeadsLast7,
        LB.LeadsLast30,
        LB.MsgsOutbound,
        LB.MsgsInbound,
        LB.MsgsOutLast7,
        CAST(LB.ReplyRatePct AS DECIMAL(5,2)) AS ReplyRatePct,
        LB.ApptsBooked,
        LB.OppsTotal,
        LB.OppsWon,
        LB.PipelineValueWon
    FROM ghl.vw_AgentLeaderboard LB
    LEFT JOIN ghl.Users U ON U.UserId = LB.UserId
    ORDER BY LB.LeadsAssigned DESC;
""")

if df.empty:
    st.warning("No agents in the leaderboard.")
    st.stop()

# ---- Top tiles ----
c1, c2, c3, c4 = st.columns(4)
c1.metric("Personas", len(df))
c2.metric("Total leads assigned", f"{int(df['LeadsAssigned'].sum()):,}")
c3.metric("Outbound msgs (all-time)", f"{int(df['MsgsOutbound'].sum()):,}")
c4.metric("Outbound msgs (last 7d)", f"{int(df['MsgsOutLast7'].sum()):,}")

st.divider()

# ---- Outbound msgs in last 7d ----
st.subheader("Outbound msgs in the last 7 days")
top = df.nlargest(15, "MsgsOutLast7")
fig = px.bar(
    top, x="MsgsOutLast7", y="FullName", orientation="h",
    color="ReplyRatePct", color_continuous_scale="Viridis",
    labels={"MsgsOutLast7": "Outbound (7d)", "FullName": ""}, height=480,
)
fig.update_layout(yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig, use_container_width=True)

# ---- Reply rate scatter ----
st.subheader("Reply rate vs message volume")
fig2 = px.scatter(
    df, x="MsgsOutbound", y="ReplyRatePct", size="LeadsAssigned",
    color="OppsWon", hover_data=["FullName"], height=380,
    labels={"MsgsOutbound": "Outbound (all-time)", "ReplyRatePct": "Reply rate %"},
)
st.plotly_chart(fig2, use_container_width=True)

# ---- Table ----
st.subheader("Full leaderboard")
st.dataframe(df, use_container_width=True, hide_index=True)
