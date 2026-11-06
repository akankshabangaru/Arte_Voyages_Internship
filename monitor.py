"""Continuous monitor: load trips -> poll feeds -> upsert events -> score legs -> alert on tier change."""
import csv
from datetime import date, datetime, timedelta, timezone

import db
from alerts import notify
from alerts import notify as default_notify
from alerts import render_alert
from scorer import Leg, leg_score_from_signals, leg_signals, tier_of

COOLDOWN = timedelta(hours=48)
_LAST: dict[str, dict] = {}  # leg_id -> {"tier": str, "since": datetime|None}
_TIER_RANK = {"Green": 0, "Watch": 1, "Act": 2}


def load_trips(path: str = "trips.csv") -> list[Leg]:
    legs = []
    try:
        with open(path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    lat = float(row["lat"])
                    lon = float(row["lon"])
                    start = date.fromisoformat(row["start_date"].strip())
                    end = date.fromisoformat(row["end_date"].strip())
                    trip_id = (row["trip_id"] or "").strip()
                    if not trip_id or end < start:
                        print(f"WARN: skipping bad row {row!r}")
                        continue
                    legs.append(Leg(leg_id=trip_id, trip_id=trip_id, place=row["city"].strip(),
                                    country=row["country"].strip(), lat=lat, lon=lon, start=start, end=end))
                except (KeyError, TypeError, ValueError, AttributeError) as e:
                    print(f"WARN: skipping bad row {row!r}: {e}")
                    continue
    except FileNotFoundError:
        print(f"WARN: trips file not found: {path}")
        return []
    return legs


def fetch_all(now: datetime, legs: list[Leg]) -> list:
    import feeds
    out = []
    wrappers = [("usgs", feeds.usgs_feed), ("gdacs", feeds.gdacs_feed), ("news", feeds.news_feed),
                ("weather", feeds.weather_feed(legs))]
    for name, fn in wrappers:
        try:
            evs = fn(now)
            out += evs
            db.upsert_health(name, True, "")
        except Exception as e:
            print(f"WARN: feed {name} failed: {e}")
            db.upsert_health(name, False, str(e))
    try:
        from feeds import cluster_events
        out = cluster_events(out)
    except Exception:
        pass
    return out


def _tier_with_cooldown(leg_id: str, raw: str, now: datetime) -> str:
    st = _LAST.setdefault(leg_id, {"tier": "Green", "since": None})
    if _TIER_RANK[raw] >= _TIER_RANK[st["tier"]]:
        st["tier"], st["since"] = raw, None
    else:
        st["since"] = st["since"] or now
        if now - st["since"] >= COOLDOWN:
            st["tier"], st["since"] = raw, None
    return st["tier"]


def poll_once(now: datetime, feeds: dict = None, notifier=None, legs: list[Leg] = None) -> list[dict]:
    """Run one tick. `notifier` receives alert dicts; default is Gmail notify."""
    if legs is None:
        legs = load_trips()
    events = fetch_all(now, legs)
    for e in events:
        db.upsert_event(e, now)
    stored = db.get_events()
    today = now.date()
    alerts_out: list[dict] = []
    for leg in legs:
        if leg.end < today:
            continue
        # Only remaining days can still be affected for display, but score full leg (simpler, matches spec intent for MVP)
        sigs = leg_signals(leg, stored, today)
        score = leg_score_from_signals(sigs)
        raw = tier_of(score)
        tier = _tier_with_cooldown(leg.leg_id, raw, now)
        prev = _LAST.get(f"__prev_{leg.leg_id}", {}).get("tier", "Green") if False else _last_tier_db(leg)
        # Determine kind: escalation / de-escalation based on stored previous tier
        top = max(sigs, key=lambda s: s["risk"]) if sigs else None
        driver = top["title"][:80] if top else ""
        db.update_score(leg.trip_id, leg.leg_id, leg.place, leg.country, leg.lat, leg.lon,
                        leg.start, leg.end, score, tier, driver, now)
        prev_tier = _prev_tier(leg)
        if tier != prev_tier:
            kind = "ESCALATED" if _TIER_RANK[tier] > _TIER_RANK[prev_tier] else "DE-ESCALATED"
            text = render_alert(leg.trip_id, leg, tier, prev_tier, score, sigs, now)
            a = {"trip_id": leg.trip_id, "leg_id": leg.leg_id, "kind": kind, "tier": tier,
                 "prev_tier": prev_tier, "text": text, "created_at": now.isoformat()}
            try:
                db.log_alert(a)
            except Exception as e:
                print(f"WARN: log_alert failed: {e}")
            fn = notifier or notify
            try:
                fn(a)
            except Exception as e:
                print(f"WARN: notify failed (alert persisted): {e}")
            alerts_out.append(a)
        _store_prev_tier(leg, tier)
    return alerts_out


# Prev-tier persistence via trip_scores table (cooldown stays in-process for MVP)
def _last_tier_db(leg):
    try:
        for row in db.get_scores():
            if row["leg_id"] == leg.leg_id:
                return row["tier"]
    except Exception:
        pass
    return "Green"


def _prev_tier(leg):
    return _LAST.get(f"__prev__{leg.leg_id}", {}).get("tier", "Green")


def _store_prev_tier(leg, tier):
    _LAST[f"__prev__{leg.leg_id}"] = {"tier": tier}


def main():
    db.init_db()
    poll_once(datetime.now(timezone.utc).replace(tzinfo=None))


if __name__ == "__main__":
    main()
