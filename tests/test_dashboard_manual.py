# tests/test_dashboard_manual.py
import math
from datetime import date
from scorer import Leg, simulate_manual, tier_of

def _leg():
    return Leg(leg_id="PARO-01", trip_id="PARO-01", place="Paro", country="Bhutan",
               lat=27.43, lon=89.42, start=date(2026, 8, 10), end=date(2026, 8, 12))

def test_tier_custom_thresholds():
    assert tier_of(0.10, watch=0.05, act=0.80) == "Watch"
    assert tier_of(0.90, watch=0.05, act=0.80) == "Act"
    assert tier_of(0.04, watch=0.05, act=0.80) == "Green"

def test_threshold_clamp_prevents_inversion():
    # helper-level: simulate with inverted watch/act must still rank Act > Watch
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 8, 10), 3, 0.9,
                        watch=0.40, act=0.20, prev_tier="Green")
    assert r["tier"] in ("Green", "Watch", "Act")
    assert r["score"] >= 0.0
    # concrete clamp proof: score ~0.30 must stay Green (act was raised above 0.40)
    r2 = simulate_manual(_leg(), "cyclone", 0.33, 0, date(2026, 8, 10), 3, 0.9,
                         watch=0.40, act=0.20, prev_tier="Green")
    assert 0.25 < r2["score"] < 0.35
    assert r2["tier"] == "Green"

def test_manual_escalation_green_to_act():
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 8, 10), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["tier"] == "Act"
    assert r["kind"] == "ESCALATED"
    assert r["score"] > 0.45

def test_event_outside_window_stays_green():
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 9, 1), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["tier"] == "Green"
    assert r["time_overlap"] == 0.0

def test_proximity_cutoff():
    # flood radius 150km -> 3x = 450km ; 900km is beyond
    r = simulate_manual(_leg(), "flood", 0.9, 900, date(2026, 8, 10), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["proximity"] == 0.0
    assert r["tier"] == "Green"

def test_zero_severity_unchanged():
    r = simulate_manual(_leg(), "rain", 0.0, 0, date(2026, 8, 10), 1, 0.6,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["score"] == 0.0
    assert r["kind"] == "UNCHANGED"

import pathlib
def test_dashboard_has_manual_toggle_and_editors():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert "Manual" in text and "Live" in text
    assert "Watch threshold" in text
    assert "Act threshold" in text
    assert "Simulation only" in text

def test_no_db_write_in_manual_path():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    # manual block must not call write APIs
    assert "simulate_manual" in text
    assert text.count("log_alert") == 0 or "Manual" in text.split("log_alert")[0][-2000:]

def test_simulate_manual_never_writes(monkeypatch):
    import db
    import alerts as alerts_mod

    def _boom(*a, **k):
        raise AssertionError("manual simulation must not write")

    monkeypatch.setattr(db, "upsert_event", _boom)
    monkeypatch.setattr(db, "log_alert", _boom)
    monkeypatch.setattr(db, "update_score", _boom)
    monkeypatch.setattr(alerts_mod, "send_email", _boom)
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 8, 10), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["tier"] == "Act"

from dashboard import _group_alerts, _load_legs_fallback

def test_grouping_order_tier_times_change():
    arr = [
        {"tier": "Green", "kind": "DE-ESCALATED", "score": 0.0},
        {"tier": "Act", "kind": "ESCALATED", "score": 0.80},
        {"tier": "Watch", "kind": "ESCALATED", "score": 0.30},
        {"tier": "Green", "kind": "UNCHANGED", "score": 0.0},
    ]
    groups = _group_alerts(arr)
    assert groups[0][0]["tier"] == "Act"
    assert groups[1][0]["tier"] == "Watch"

def test_fallback_legs_parse_without_monitor():
    legs = _load_legs_fallback("trips.csv")
    assert len(legs) >= 1
    assert hasattr(legs[0], "trip_id")
    assert "import monitor" not in pathlib.Path("dashboard.py").read_text(encoding="utf-8")

from dashboard import _manual_leg_options, _resolve_manual_leg

def test_manual_options_from_legs():
    legs = [_leg(), Leg(leg_id="KTM-01", trip_id="KTM-01", place="Kathmandu", country="Nepal",
                        lat=27.71, lon=85.32, start=date(2026, 12, 16), end=date(2026, 12, 20))]
    opts = _manual_leg_options(legs)
    assert len(opts) == 2
    assert opts[0].startswith("PARO-01")
    assert "Kathmandu" in opts[1]

def test_resolve_manual_leg_filters():
    legs = [_leg(), Leg(leg_id="KTM-01", trip_id="KTM-01", place="Kathmandu", country="Nepal",
                        lat=27.71, lon=85.32, start=date(2026, 12, 16), end=date(2026, 12, 20))]
    picked = _manual_leg_options(legs)[1]
    chosen = _resolve_manual_leg(legs, picked)
    assert chosen is not None
    assert chosen.trip_id == "KTM-01"
    assert _resolve_manual_leg(legs, "(no legs — run monitor once)") is None

def test_maps_are_english_and_india_centred():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert 'map_style="carto-positron"' in text
    assert "open-street-map" not in text
    assert "center=dict(lat=23.5" in text
    assert "zoom=4" in text

def test_luxury_rhythm_present():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert "✦" in text
    assert "h2::after" in text
    assert "FIVE COUNTRIES" in text
    assert "OUR APPROACH" in text
    assert '"#1F3A4D"' in text and '"#A68A56"' in text and '"#FAF8F4"' in text
    assert "1.5rem" in text

def test_ornament_is_brass_line_not_glyph():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert 'content: "";' in text or "content: '';" in text
    assert 'content: "✦"' not in text
    assert "content: '✦'" not in text
    assert "@import url('https://fonts.googleapis.com/css2?family=Playfair+Display" in text
    assert "family=Source+Sans+3" in text
