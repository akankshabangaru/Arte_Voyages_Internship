"""Streamlit dashboard — reads Turso/sqlite only, never calls feeds directly."""
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    import db
except Exception:
    db = None

COLORS = {"Green": "#2e7d32", "Watch": "#f9a825", "Act": "#c62828"}
ICON = {"Green": "🟢", "Watch": "🟡", "Act": "🔴"}


def _load():
    if db is None:
        return [], [], []
    try:
        db.init_db()
        return db.get_scores(), db.get_alerts(100), db.get_health()
    except Exception as e:
        st.error(f"Database unreachable: {e}")
        return [], [], []


def main():
    st.set_page_config(page_title="Trip Risk Monitor", layout="wide")
    st.title("🌍 Continuous Trip Risk Monitoring")
    st.caption("Follows India, Nepal, Bhutan, Sri Lanka, Maldives — severities from free feeds, alerts by Gmail.")

    scores, alerts, health = _load()

    if health:
        bad = [f"{h['feed']}: {h['last_error']}" for h in health if h["last_error"]]
        if bad:
            st.warning("Feed problem: " + " | ".join(bad[:3]))

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Legs scored", len(scores))
    with c2:
        st.metric("Act alerts", len([a for a in alerts if a.get("tier") == "Act"]))
    with c3:
        st.metric("Alerts (100)", len(alerts))

    st.subheader("Trip scores")
    if scores:
        df = pd.DataFrame(scores)
        df["icon"] = df["tier"].map(lambda t: f"{ICON.get(t, '⚪')} {t}")
        st.dataframe(df[["trip_id", "place", "country", "start", "end", "score", "icon", "driver"]], use_container_width=True)
        fig = px.bar(df, x="trip_id", y="score", color="tier", color_discrete_map=COLORS,
                     title="Leg risk (worst leg drives trip)")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No scores yet — run `python -m monitor` once.")

    st.subheader("Map")
    if scores:
        mdf = pd.DataFrame([s for s in scores if s["lat"] is not None])
        if not mdf.empty:
            fig2 = px.scatter_mapbox(mdf, lat="lat", lon="lon", color="tier", color_discrete_map=COLORS,
                                     hover_name="place", hover_data=["trip_id", "score", "country"],
                                     zoom=3, height=420)
            fig2.update_layout(mapbox_style="open-street-map", margin=dict(t=10, b=10, l=10, r=10))
            st.plotly_chart(fig2, use_container_width=True)

    st.subheader("14-day outlook note")
    st.caption("Outlook is the Open-Meteo forecast window rendered per leg-day in monitor scoring; per-day chart follows once forecast events are stored (Phase 2 polish).")

    st.subheader("Alert feed")
    tier_filter = st.selectbox("Filter by tier", ["All", "Green", "Watch", "Act"])
    kind_filter = st.selectbox("Filter by kind", ["All", "ESCALATED", "DE-ESCALATED", "CLOSED"])
    shown = alerts
    if tier_filter != "All":
        shown = [a for a in shown if a.get("tier") == tier_filter]
    if kind_filter != "All":
        shown = [a for a in shown if a.get("kind") == kind_filter]
    for a in shown[:50]:
        st.markdown(f"**{a.get('created_at','')[:16]}** · {a.get('kind','')} · {a.get('prev_tier','')} → **{a.get('tier','')}**")
        st.code(a.get("text", ""))

    st.subheader("Feed health")
    if health:
        st.dataframe(pd.DataFrame(health), use_container_width=True)
    else:
        st.caption("No health rows yet.")


if __name__ == "__main__":
    main()
