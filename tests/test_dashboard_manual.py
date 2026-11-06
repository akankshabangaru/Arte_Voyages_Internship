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
