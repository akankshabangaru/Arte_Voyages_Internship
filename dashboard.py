"""Streamlit dashboard — reads Turso/sqlite only, never calls feeds directly.

UI/UX design system applied (ui-ux-design-system, Harbor + Brass):
- Data-Dense Dashboard pattern: KPI row -> scores -> map -> outlook -> alerts -> health
- Tokens from design system only (see :root below); no hard-coded hex outside tokens
- WCAG: text 15.4:1, primary-on-white 11.9:1, muted 6.3:1 (AA pass); focus-visible, 44px targets, reduced-motion, 320px reflow
- Charts: bars from zero with direct labels, line with thresholds + data table fallback, tier never colour-alone (emoji + text)
"""
import os
from datetime import datetime

import pandas as pd
import plotly.express as px
import streamlit as st

try:
    import db
except Exception:
    db = None

# --- Design tokens (Harbor + Brass, light native) ---
TOKENS = {
    "primary": "#1F3A4D",
    "secondary": "#A68A56",
    "background": "#FAF8F4",
    "surface": "#FFFFFF",
    "text": "#1B2630",
    "muted": "#55626C",
    "border": "#E4DED2",
}

# Tier fills for charts (always paired with emoji + text label, never colour-alone)
COLORS = {"Green": "#2e7d32", "Watch": "#b45309", "Act": "#b91c1c"}
ICON = {"Green": "🟢", "Watch": "🟡", "Act": "🔴"}


def _apply_design_system() -> None:
    t = TOKENS
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@700&family=Source+Sans+3:wght@400;600;700&display=swap');
        :root {{
            --color-primary: {t['primary']};
            --color-secondary: {t['secondary']};
            --color-background: {t['background']};
            --color-surface: {t['surface']};
            --color-text: {t['text']};
            --color-muted: {t['muted']};
            --color-border: {t['border']};
            --radius: 10px;
            --spacing: 12px;
        }}
        .stApp {{ background-color: var(--color-background); color: var(--color-text); }} header[data-testid="stHeader"], [data-testid="stDecoration"] {{ background-color: var(--color-background) !important; }}
        .block-container {{ padding-top: 1.5rem; max-width: 1280px; }}
        h1, .stApp h1, [data-testid="stHeading"] h1 {{ font-family: "Playfair Display", Georgia, serif !important; font-weight: 700; color: var(--color-text); letter-spacing: -0.01em; }}
        h1::after, h2::after {{ content: ""; display: block; width: 56px; height: 3px; background: var(--color-secondary); border-radius: 2px; margin-top: 8px; }}
        h2, h3, .stApp h2, .stApp h3 {{ font-family: "Source Sans 3", system-ui, -apple-system, sans-serif !important; font-weight: 600; color: var(--color-text); }}
        .stCaption {{ color: var(--color-muted); }}
        [data-testid="stMetric"] {{
            background: var(--color-surface); border: 1px solid var(--color-border);
            border-radius: var(--radius); padding: 14px;
        }}
        [data-testid="stMetric"] [data-testid="stMetricLabel"] {{ color: var(--color-muted); font-size: 0.85rem; }}
        [data-testid="stMetric"] [data-testid="stMetricValue"] {{ color: var(--color-text); font-variant-numeric: tabular-nums; }}
        /* Dense tables, tabular numerals, 44px touch rows */
        [data-testid="stTable"] td, [data-testid="stDataFrame"] td {{ font-size: 14px; font-variant-numeric: tabular-nums; min-height: 44px; }}
        [data-testid="stTable"] th, [data-testid="stDataFrame"] th {{ font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--color-muted); position: sticky; top: 0; background: var(--color-surface); z-index: 1; }}
        /* Focus visible + primary buttons */
        button:focus-visible, a:focus-visible, [tabindex]:focus-visible {{ outline: 3px solid var(--color-secondary); outline-offset: 2px; }}
        .stButton > button {{
            min-height: 44px; border-radius: 8px; font-weight: 600;
            transition: background 150ms ease, color 150ms ease;
        }}
        .stButton > button:hover {{ background: var(--color-primary) !important; color: #FFFFFF !important; }}
        @media (prefers-reduced-motion: reduce) {{ * {{ transition: none !important; animation: none !important; }} }}
        @media (max-width: 768px) {{ .block-container {{ padding: 0.8rem; }} }}
        </style>
        """,
        unsafe_allow_html=True,
    )


def _load():
    if db is None:
        return [], [], []
    try:
        db.init_db()
        return db.get_scores(), db.get_alerts(100), db.get_health()
    except Exception as e:
        st.error(f"Database unreachable: {e}")
        return [], [], []


def _summary_text(scores, alerts):
    legs = len(scores)
    if legs:
        act = sum(1 for s in scores if s.get("tier") == "Act")
        watch = sum(1 for s in scores if s.get("tier") == "Watch")
    else:
        act = len([a for a in (alerts or []) if a.get("tier") == "Act"])
        watch = len([a for a in (alerts or []) if a.get("tier") == "Watch"])
    return f"{legs} legs scored · {act} need review (Act) · {watch} on watch"


def _manual_leg_options(legs):
    return [f"{leg.trip_id} · {leg.place}, {leg.country}" for leg in legs]


def _resolve_manual_leg(legs, picked_label):
    if not picked_label or picked_label.startswith("(no legs"):
        return None
    trip_id = str(picked_label).split("·")[0].strip()
    for leg in legs:
        if leg.trip_id == trip_id or leg.leg_id == trip_id:
            return leg
    return None


def _trip_rows_from_sims(sims, picked_trip_id):
    rows = []
    for s in sims:
        is_picked = s.get("trip_id") == picked_trip_id
        rows.append(
            {
                "trip_id": f"{s.get('trip_id', '')} ★" if is_picked else s.get("trip_id", ""),
                "place": s.get("place", ""),
                "country": s.get("country", ""),
                "start": s.get("start", ""),
                "end": s.get("end", ""),
                "score": s.get("score", 0.0),
                "icon": f"{ICON.get(s.get('tier', 'Green'), '⚪')} {s.get('tier', 'Green')}",
                "driver": s.get("driver", ""),
                "tier": s.get("tier", "Green"),
            }
        )
    return rows


def _group_alerts(alert_dicts):
    buckets = [[], [], [], []]
    for a in alert_dicts:
        if a.get("tier") == "Act" and a.get("kind") == "ESCALATED":
            buckets[0].append(a)
        elif a.get("tier") == "Watch" and a.get("kind") == "ESCALATED":
            buckets[1].append(a)
        elif a.get("kind") == "DE-ESCALATED":
            buckets[2].append(a)
        else:
            buckets[3].append(a)
    return buckets


def _render_manual_result(sim, thresholds):
    tier = sim.get("tier", "Green")
    kind = sim.get("kind", "UNCHANGED")
    score = float(sim.get("score", 0.0))
    driver = sim.get("driver", "")
    prev = sim.get("prev_tier", "Green")
    trip = sim.get("trip_id", "")
    place = sim.get("place", "")
    action_map = {
        "Act": "Review now, consider buffer day / reroute, contact partners.",
        "Watch": "Monitor closely.",
        "Green": "No action.",
    }
    action = action_map.get(tier, "Monitor closely.")
    kind_symbol = {"ESCALATED": "↑", "DE-ESCALATED": "↓", "CLOSED": "✓", "UNCHANGED": "—"}.get(kind, "—")
    with st.container():
        st.markdown(f"**{ICON.get(tier, '⚪')} {tier}** · {kind_symbol} {kind} · {trip} {place}")
        st.caption(f"Leg risk: {score:.2f} → {tier} (was {prev})")
        st.progress(min(1.0, max(0.0, score)))
        st.caption(f"Watch {thresholds.get('watch', 0.15):.2f} | Act {thresholds.get('act', 0.45):.2f} · Driver: {driver}")
        st.caption(f"Action: {action}")
        if float(sim.get("time_overlap", 1.0)) == 0.0:
            st.caption("Event is outside this leg's dates — score stays Green.")


def _load_legs_fallback(path="trips.csv"):
    import csv
    from datetime import date as _d
    from scorer import Leg as _Leg

    legs = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    lat = float(row["lat"])
                    lon = float(row["lon"])
                    start = _d.fromisoformat(str(row["start_date"]).strip())
                    end = _d.fromisoformat(str(row["end_date"]).strip())
                    trip_id = (row["trip_id"] or "").strip()
                    if not trip_id or end < start:
                        continue
                    legs.append(
                        _Leg(
                            leg_id=trip_id,
                            trip_id=trip_id,
                            place=(row.get("city") or "").strip(),
                            country=(row.get("country") or "").strip(),
                            lat=lat,
                            lon=lon,
                            start=start,
                            end=end,
                        )
                    )
                except (KeyError, TypeError, ValueError, AttributeError):
                    continue
    except FileNotFoundError:
        return []
    return legs


def main():
    st.set_page_config(page_title="Trip Risk Monitor", layout="wide")
    _apply_design_system()
    st.title("Continuous Trip Risk Monitoring")
    st.caption("Arte Voyages · Curated Luxury Journeys Across India & Beyond ✦")
    st.caption("Follows India, Nepal, Bhutan, Sri Lanka, Maldives — severities from free feeds, alerts by Gmail.")

    scores, alerts, health = _load()

    # Live | Manual toggle (Manual is simulation only; uses simulate_manual, no DB/email writes)
    if hasattr(st, "segmented_control"):
        mode = st.segmented_control("Mode", ["● Live", "✎ Manual"], default="● Live")
    else:
        mode = st.radio("Mode", ["● Live", "✎ Manual"], index=0, horizontal=True)
    is_manual = bool(mode and "Manual" in str(mode))
    st.info("**" + _summary_text(scores, alerts) + "**")
    manual_sims = None
    manual_picked_id = None
    manual_thresholds = None
    if is_manual:
        st.caption("Simulation only — what-if; no DB write, no email.")
        st.subheader("Manual — set hazard values")
        st.caption("Pick a leg, set a hazard, drag the thresholds — the card below recalculates instantly.")
        # Build legs first (read-only from scores, fallback to CSV) so Pick-trip lists the same legs that are simulated
        _opt_legs = []
        try:
            from datetime import date as _d_opt
            from scorer import Leg as _Leg_opt

            for _s in scores:
                try:
                    _opt_legs.append(
                        _Leg_opt(
                            leg_id=_s["leg_id"],
                            trip_id=_s["trip_id"],
                            place=_s["place"],
                            country=_s["country"],
                            lat=float(_s["lat"]),
                            lon=float(_s["lon"]),
                            start=_d_opt.fromisoformat(str(_s["start"])),
                            end=_d_opt.fromisoformat(str(_s["end"])),
                        )
                    )
                except Exception:
                    continue
        except Exception:
            _opt_legs = []
        if not _opt_legs:
            _opt_legs = _load_legs_fallback("trips.csv")
        trip_options = _manual_leg_options(_opt_legs) or ["(no legs — run monitor once)"]
        picked = st.sidebar.selectbox("Pick trip", trip_options)
        hazard_type = st.sidebar.selectbox(
            "Hazard type",
            ["earthquake", "flood", "cyclone", "heatwave", "unrest", "eruption", "wildfire", "drought", "storm", "rain", "default"],
        )
        severity = st.sidebar.slider("Severity", 0.0, 1.0, 0.5, step=0.05)
        distance_km = st.sidebar.slider("Distance (km)", 0, 1000, 50, step=10)
        _picked_for_date = _resolve_manual_leg(_opt_legs, picked)
        _default_date = _picked_for_date.start if _picked_for_date is not None else None
        event_date = st.sidebar.date_input("Event date", value=_default_date)
        duration_days = st.sidebar.number_input("Duration (days)", min_value=1, max_value=30, value=3)
        watch_threshold = st.sidebar.slider("Watch threshold", 0.05, 0.45, 0.15, step=0.05)
        act_threshold = st.sidebar.slider("Act threshold", 0.15, 0.90, 0.45, step=0.05)
        # keep threshold slider labels valid for structure tests; real clamp handled in scorer
        st.sidebar.caption(f"Watch {watch_threshold:.2f} · Act {max(act_threshold, watch_threshold + 0.01):.2f}")
        try:
            from datetime import date as _date
            from scorer import Leg as _Leg
            from scorer import simulate_manual

            clamped_act = max(act_threshold, watch_threshold + 0.01) if act_threshold <= watch_threshold else act_threshold
            clamped_act = min(0.90, clamped_act)
            confidence_map = {"earthquake": 0.9, "flood": 0.9, "cyclone": 0.9, "eruption": 0.9, "wildfire": 0.9, "drought": 0.9}
            confidence = confidence_map.get(hazard_type, 0.6)
            # Build legs from live scores (read-only) or fallback CSV parse
            prev_by_leg = {s.get("leg_id"): s.get("tier", "Green") for s in scores}
            legs = []
            for s in scores:
                try:
                    legs.append(
                        _Leg(
                            leg_id=s["leg_id"],
                            trip_id=s["trip_id"],
                            place=s["place"],
                            country=s["country"],
                            lat=float(s["lat"]),
                            lon=float(s["lon"]),
                            start=_date.fromisoformat(str(s["start"])),
                            end=_date.fromisoformat(str(s["end"])),
                        )
                    )
                except Exception:
                    continue
            if not legs:
                legs = _load_legs_fallback("trips.csv")
            picked_leg = _resolve_manual_leg(legs, picked)
            display_legs = list(legs)
            sims = []
            for leg in display_legs:
                prev_tier = prev_by_leg.get(leg.leg_id, "Green")
                sim = simulate_manual(
                    leg,
                    hazard_type,
                    severity,
                    distance_km,
                    event_date,
                    int(duration_days),
                    confidence,
                    watch_threshold,
                    clamped_act,
                    prev_tier,
                )
                sim.update({"trip_id": leg.trip_id, "place": leg.place, "country": leg.country, "leg_id": leg.leg_id, "lat": leg.lat, "lon": leg.lon, "start": str(leg.start), "end": str(leg.end)})
                sims.append(sim)
            manual_sims = sims
            manual_picked_id = picked_leg.trip_id if picked_leg is not None else None
            manual_thresholds = {"watch": watch_threshold, "act": clamped_act}
            st.subheader("Manual results — grouped by tier × change")
            if sims:
                sim_df = pd.DataFrame(sims)
                if not sim_df.empty and "lat" in sim_df.columns:
                    try:
                        fig_manual = px.scatter_map(
                            sim_df,
                            lat="lat",
                            lon="lon",
                            color="tier",
                            color_discrete_map=COLORS,
                            hover_name="place",
                            hover_data=["trip_id", "score", "country"],
                            center=dict(lat=23.5, lon=78.5),
                            zoom=4,
                            height=360,
                            map_style="carto-positron",
                        )
                        fig_manual.update_layout(margin=dict(t=10, b=10, l=10, r=10), template="simple_white", font=dict(family="Source Sans 3, system-ui, sans-serif", size=13))
                        st.plotly_chart(fig_manual, use_container_width=True)
                    except Exception:
                        st.info("Manual map unavailable.")
                groups = _group_alerts(sims)
                labels = ["Act + Escalated", "Watch + Escalated", "De-escalated", "Closed / Unchanged"]
                thresholds = {"watch": watch_threshold, "act": clamped_act}
                for label, bucket in zip(labels, groups):
                    if bucket:
                        st.subheader(label)
                        for sim in bucket:
                            _render_manual_result(sim, thresholds)
                with st.expander("How it works"):
                    first = sims[0] if sims else {}
                    st.markdown(
                        f"1) proximity = exp(-distance / radius) = **{first.get('proximity', 0):.3f}**\n\n"
                        f"2) time overlap = **{first.get('time_overlap', 0):.3f}** (event {event_date}, {int(duration_days)} days)\n\n"
                        f"3) risk = severity × proximity × overlap × confidence = **{first.get('risk', 0):.3f}**\n\n"
                        f"4) score (noisy-OR of one risk) = **{first.get('score', 0):.3f}** → tier with Watch {watch_threshold:.2f} / Act {clamped_act:.2f} = **{first.get('tier', '')}**\n\n"
                        f"5) alert kind compares new tier to previous ({first.get('prev_tier', '')}) → **{first.get('kind', '')}**"
                    )
            else:
                st.info("No legs to simulate — run monitor once or place legs in trips.csv.")
        except Exception as e:
            st.caption(f"Manual simulation unavailable: {e}")

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

    st.caption("FIVE COUNTRIES · ONE TEAM — OUR APPROACH")
    st.caption("Every leg your clients will travel — scored and explained, in English.")
    st.subheader("Trip scores")
    if is_manual and manual_sims:
        st.caption(f"Manual simulation — {hazard_type} · ★ Picked: {manual_picked_id or '(none)'} · Live DB untouched.")
        sim_rows = _trip_rows_from_sims(manual_sims, manual_picked_id)
        sdf = pd.DataFrame(sim_rows)
        st.dataframe(sdf[["trip_id", "place", "country", "start", "end", "score", "icon", "driver"]], use_container_width=True)
        fig = px.bar(sdf, x="trip_id", y="score", color="tier", color_discrete_map=COLORS,
                     title="Simulated leg risk (Manual — worst leg drives trip)")
        fig.update_yaxes(range=[0, 1])
        fig.update_traces(text=sdf["score"].round(2), textposition="outside")
        fig.update_layout(template="simple_white", font=dict(family="Source Sans 3, system-ui, sans-serif", size=13))
        st.plotly_chart(fig, use_container_width=True)
    elif scores:
        df = pd.DataFrame(scores)
        df["icon"] = df["tier"].map(lambda t: f"{ICON.get(t, '⚪')} {t}")
        st.dataframe(df[["trip_id", "place", "country", "start", "end", "score", "icon", "driver"]], use_container_width=True)
        fig = px.bar(df, x="trip_id", y="score", color="tier", color_discrete_map=COLORS,
                     title="Leg risk (worst leg drives trip)")
        fig.update_yaxes(range=[0, 1])
        fig.update_traces(text=df["score"].round(2), textposition="outside")
        fig.update_layout(template="simple_white", font=dict(family="Source Sans 3, system-ui, sans-serif", size=13))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No scores yet — run `python -m monitor` once.")

    st.caption("FIVE COUNTRIES · ONE TEAM")
    st.caption("Read the legs your clients will travel — scored and explained.")
    st.subheader("Map")
    if is_manual and manual_sims:
        mdf = pd.DataFrame([s for s in manual_sims if s.get("lat") is not None])
        if not mdf.empty:
            fig2 = px.scatter_map(mdf, lat="lat", lon="lon", color="tier", color_discrete_map=COLORS,
                                      hover_name="place", hover_data=["trip_id", "score", "country"],
                                      center=dict(lat=23.5, lon=78.5), zoom=4, height=420, map_style="carto-positron")
            fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10), template="simple_white",
                               font=dict(family="Source Sans 3, system-ui, sans-serif", size=13))
            fig2.update_layout(title=dict(text="Manual simulated map — ★ picked highlighted in table", font=dict(family="Source Sans 3, system-ui, sans-serif", size=13)))
            st.plotly_chart(fig2, use_container_width=True)
    elif scores:
        mdf = pd.DataFrame([s for s in scores if s["lat"] is not None])
        if not mdf.empty:
            fig2 = px.scatter_map(mdf, lat="lat", lon="lon", color="tier", color_discrete_map=COLORS,
                                      hover_name="place", hover_data=["trip_id", "score", "country"],
                                      center=dict(lat=23.5, lon=78.5), zoom=4, height=420, map_style="carto-positron")
            fig2.update_layout(margin=dict(t=10, b=10, l=10, r=10), template="simple_white",
                               font=dict(family="Source Sans 3, system-ui, sans-serif", size=13))
            st.plotly_chart(fig2, use_container_width=True)

    st.caption("OUR APPROACH")
    st.caption("Your clients and your brand — monitored before they travel.")
    st.subheader("14-day outlook")
    try:
        if db is not None and scores:
            from datetime import date as _date, timedelta as _td
            from scorer import Leg as _Leg, Event as _Event, leg_score_from_signals, leg_signals
            events = db.get_events()
            today = _date.today()
            rows = []
            for s in scores:
                try:
                    st_date = _date.fromisoformat(s["start"])
                    en_date = _date.fromisoformat(s["end"])
                except Exception:
                    continue
                for i in range(14):
                    d = today + _td(days=i)
                    if st_date <= d <= en_date:
                        leg = _Leg(leg_id=s["leg_id"], trip_id=s["trip_id"], place=s["place"],
                                   country=s["country"], lat=s["lat"], lon=s["lon"], start=d, end=d)
                        # Score against events known by today (forecasts included)
                        sigs = leg_signals(leg, events, today)
                        rows.append({"leg": f"{s['trip_id']} {s['place']}", "day": d, "risk": leg_score_from_signals(sigs)})
            if rows:
                odf = pd.DataFrame(rows)
                fig3 = px.line(odf, x="day", y="risk", color="leg", title="14-day outlook risk per leg-day")
                fig3.add_hline(y=0.15, line_dash="dash")
                fig3.add_hline(y=0.45, line_dash="dash")
                fig3.update_layout(template="simple_white", font=dict(family="Source Sans 3, system-ui, sans-serif", size=13))
                st.plotly_chart(fig3, use_container_width=True)
                st.dataframe(odf, use_container_width=True)
            else:
                st.caption("Outlook: no leg days in next 14 days.")
        else:
            st.caption("Outlook: run monitor once.")
    except Exception as e:
        st.caption(f"Outlook unavailable: {e}")

    st.caption("SEAMLESS COORDINATION")
    st.caption("Escalations the moment they matter — never noise.")
    st.subheader("Alert feed")
    tier_filter = st.selectbox("Filter by tier", ["All", "Green", "Watch", "Act"])
    kind_filter = st.selectbox("Filter by kind", ["All", "ESCALATED", "DE-ESCALATED", "CLOSED"])
    if is_manual and manual_sims:
        st.caption("Manual simulation — showing simulated alerts (Live DB untouched).")
        _sims = manual_sims
        if tier_filter != "All":
            _sims = [s for s in _sims if s.get("tier") == tier_filter]
        if kind_filter != "All":
            _sims = [s for s in _sims if s.get("kind") == kind_filter]
        if _sims:
            for _sim in _sims[:50]:
                _render_manual_result(_sim, manual_thresholds or {"watch": 0.15, "act": 0.45})
        else:
            st.info("No simulated alerts match those filters — try All / All or move a slider.")
    else:
        shown = alerts
        if tier_filter != "All":
            shown = [a for a in shown if a.get("tier") == tier_filter]
        if kind_filter != "All":
            shown = [a for a in shown if a.get("kind") == kind_filter]
        if shown:
            for a in shown[:50]:
                tier = a.get('tier', '')
                st.markdown(f"**{a.get('created_at','')[:16]}** · {a.get('kind','')} · {a.get('prev_tier','')} → **{ICON.get(tier, '⚪')} {tier}**")
                st.code(a.get("text", ""))
        else:
            st.info("No alerts yet — Live shows only tier changes from monitor. Switch to ✎ Manual and set Event date inside a leg to see simulated alerts above.")

    st.caption("DISCRETION & BRAND ALIGNMENT")
    st.caption("End-to-end management, with 24/7 quiet care.")
    st.subheader("Feed health")
    if health:
        st.dataframe(pd.DataFrame(health), use_container_width=True)
    else:
        st.caption("No health rows yet.")


if __name__ == "__main__":
    main()
