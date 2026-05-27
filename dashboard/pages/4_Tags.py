"""Tag taxonomy + engagement-by-tag analysis."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from _db import q

st.set_page_config(page_title="Tags", page_icon="🏷️", layout="wide")
st.title("🏷️ Tag Engagement")
st.caption("Which lead-source tags actually engage? Which are dead?")

min_contacts = st.slider("Min contacts per tag", 50, 5000, 500, step=50)

df = q(f"""
    SELECT TagSlug, Contacts, EngagedContacts,
           CAST(EngagedPct AS DECIMAL(5,2)) AS EngPct,
           WonOpps, WonValue
    FROM ghl.vw_TagEngagement
    WHERE Contacts >= {min_contacts}
    ORDER BY EngagedPct DESC;
""")

if df.empty:
    st.info(f"No tags with at least {min_contacts:,} contacts.")
    st.stop()

c1, c2, c3 = st.columns(3)
c1.metric("Tags shown", len(df))
c2.metric("Median engagement", f"{df['EngPct'].median():.1f}%")
c3.metric("Dead tags (0%)", int((df["EngPct"] == 0).sum()))

st.divider()

st.subheader("Engagement vs volume (bubble = engagement count)")
fig = px.scatter(
    df, x="Contacts", y="EngPct", size="EngagedContacts",
    hover_name="TagSlug", color="EngPct", color_continuous_scale="RdYlGn",
    log_x=True, height=420,
    labels={"Contacts": "Contacts (log)", "EngPct": "Engagement %"},
)
st.plotly_chart(fig, use_container_width=True)

st.subheader("Top performers")
st.dataframe(df.head(20), use_container_width=True, hide_index=True)

st.subheader("Dead lists (0% engagement)")
dead = df[df["EngPct"] == 0].sort_values("Contacts", ascending=False)
st.dataframe(dead, use_container_width=True, hide_index=True)
