"""Response-time + message heatmap."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import plotly.express as px
import streamlit as st

from _db import q

st.set_page_config(page_title="Engagement", page_icon="💬", layout="wide")
st.title("💬 Engagement & Response Time")
st.caption("When are messages sent? How fast do humans reply?")

# ---- Response-time distribution ----
st.subheader("Response-time buckets")
rt = q("""
    SELECT ResponseBucket, COUNT(*) AS Convs
    FROM ghl.vw_ResponseTime
    GROUP BY ResponseBucket
    ORDER BY CASE ResponseBucket
        WHEN '<1min' THEN 1 WHEN '<5min' THEN 2 WHEN '<1hr' THEN 3
        WHEN '<1day' THEN 4 WHEN '>=1day' THEN 5 ELSE 6 END;
""")
total = rt["Convs"].sum()
rt["Pct"] = (rt["Convs"] / max(total, 1) * 100).round(1)
c1, c2 = st.columns([2, 1])
with c1:
    fig = px.bar(rt, x="ResponseBucket", y="Convs",
                 text=rt["Pct"].astype(str) + "%", height=320,
                 labels={"Convs": "Conversations"})
    st.plotly_chart(fig, use_container_width=True)
with c2:
    st.dataframe(rt, use_container_width=True, hide_index=True)

st.divider()

# ---- Heatmap ----
st.subheader("Message volume: hour × day-of-week")
direction = st.radio("Direction", ["outbound", "inbound"], horizontal=True)
mtype_options = q(f"""
    SELECT DISTINCT MessageType FROM ghl.vw_MessageHeatmap
    WHERE Direction = '{direction}'
    ORDER BY MessageType;
""")["MessageType"].tolist()
mtype = st.selectbox("Message type", ["(all)"] + mtype_options)

mtype_filter = "" if mtype == "(all)" else f"AND MessageType = '{mtype}'"
hm = q(f"""
    SELECT DayOfWeek, HourOfDay, SUM(MsgCount) AS Msgs
    FROM ghl.vw_MessageHeatmap
    WHERE Direction = '{direction}' {mtype_filter}
    GROUP BY DayOfWeek, HourOfDay
    ORDER BY DayOfWeek, HourOfDay;
""")

if not hm.empty:
    pivot = hm.pivot(index="DayOfWeek", columns="HourOfDay", values="Msgs").fillna(0)
    dow_labels = ["", "Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    pivot.index = [dow_labels[int(i)] for i in pivot.index]
    fig = px.imshow(
        pivot, aspect="auto", color_continuous_scale="Reds", height=320,
        labels={"x": "Hour (UTC)", "y": "Day", "color": "Msgs"},
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("No data for that direction/type.")

st.divider()

# ---- Hourly totals chart ----
st.subheader("Hourly totals (UTC)")
hourly = q(f"""
    SELECT HourOfDay, SUM(MsgCount) AS Msgs
    FROM ghl.vw_MessageHeatmap
    WHERE Direction = '{direction}' {mtype_filter}
    GROUP BY HourOfDay
    ORDER BY HourOfDay;
""")
if not hourly.empty:
    fig = px.bar(hourly, x="HourOfDay", y="Msgs", height=260)
    st.plotly_chart(fig, use_container_width=True)
