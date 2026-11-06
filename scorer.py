"""Scorer: severity x proximity x time overlap x confidence, combined by noisy-OR."""
import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

RADIUS_KM = {"earthquake": 300, "flood": 150, "cyclone": 400, "heatwave": 300, "unrest": 50,
             "eruption": 100, "wildfire": 100, "drought": 500, "storm": 200, "rain": 100, "default": 150}
MIN_DURATION = {"earthquake": 7, "eruption": 14, "cyclone": 3, "flood": 3}
WATCH, ACT = 0.15, 0.45
TIERS = ["Green", "Watch", "Act"]


@dataclass
class Leg:
    leg_id: str
    trip_id: str
    place: str
    country: str
    lat: float
    lon: float
    start: date
    end: date


@dataclass
class Event:
    event_id: str
    date: date
    issued: date | None
    country: str
    type: str
    severity: float
    lat: float
    lon: float
    duration_days: int
    confidence: float
    title: str
    url: str
    source: str


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(a))


def proximity(event: Event, leg: Leg) -> float:
    r = RADIUS_KM.get(event.type, RADIUS_KM["default"])
    dist = haversine_km(event.lat, event.lon, leg.lat, leg.lon)
    return 0.0 if dist > 3 * r else math.exp(-dist / r)


def time_overlap(event: Event, leg: Leg) -> float:
    ev_end = event.date + timedelta(days=event.duration_days)
    lo, hi = max(event.date, leg.start), min(ev_end, leg.end)
    leg_days = (leg.end - leg.start).days + 1
    if leg_days <= 0:
        return 0.0
    return max(0, (hi - lo).days + 1) / leg_days


def noisy_or(values) -> float:
    p = 1.0
    for v in values:
        p *= 1 - v
    return 1 - p


def tier_of(score: float, watch: float = 0.15, act: float = 0.45) -> str:
    return "Act" if score >= act else "Watch" if score >= watch else "Green"


def leg_signals(leg: Leg, events: list[Event], as_of: date) -> list[dict]:
    sigs = []
    for e in events:
        if (e.issued or e.date) > as_of:
            continue
        r = e.severity * proximity(e, leg) * time_overlap(e, leg) * e.confidence
        if r > 0:
            sigs.append({"kind": e.type, "title": e.title, "url": e.url, "risk": r})
    return sigs


def leg_score_from_signals(sigs: list[dict]) -> float:
    return noisy_or(s["risk"] for s in sigs)


def simulate_manual(
    leg: Leg,
    hazard_type: str,
    severity: float,
    distance_km: float,
    event_date: date,
    duration_days: int,
    confidence: float,
    watch: float,
    act: float,
    prev_tier: str,
) -> dict:
    severity = min(1.0, max(0.0, float(severity)))
    distance_km = min(1000.0, max(0.0, float(distance_km)))
    if act <= watch:
        act = min(0.90, watch + 0.01)
    r = RADIUS_KM.get(hazard_type, RADIUS_KM["default"])
    proximity_value = 0.0 if distance_km > 3 * r else math.exp(-distance_km / r)
    event = Event(
        event_id="manual",
        date=event_date,
        issued=None,
        country=leg.country,
        type=hazard_type,
        severity=severity,
        lat=leg.lat,
        lon=leg.lon,
        duration_days=int(duration_days),
        confidence=float(confidence),
        title=f"{hazard_type} (severity {severity:.2f})",
        url="",
        source="manual",
    )
    overlap = time_overlap(event, leg)
    risk = severity * proximity_value * overlap * float(confidence)
    score = noisy_or([risk])
    tier = tier_of(score, watch=watch, act=act)
    if leg.end < event_date:
        kind = "CLOSED"
    else:
        prev_rank = TIERS.index(prev_tier) if prev_tier in TIERS else 0
        new_rank = TIERS.index(tier)
        if new_rank > prev_rank:
            kind = "ESCALATED"
        elif new_rank < prev_rank:
            kind = "DE-ESCALATED"
        else:
            kind = "UNCHANGED"
    return {
        "score": score,
        "tier": tier,
        "prev_tier": prev_tier,
        "kind": kind,
        "driver": f"{hazard_type} (severity {severity:.2f})",
        "proximity": proximity_value,
        "time_overlap": overlap,
        "risk": risk,
    }
