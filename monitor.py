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


def _tier_with_cooldown(prev_tier: str, prev_since, raw: str, now: datetime) -> tuple[str, datetime | None]:
    """DB-backed cooldown: rises immediately, falls only after 48h below."""
    if _TIER_RANK[raw] >= _TIER_RANK[prev_tier]:
        return raw, None
    since = prev_since
    if since is None:
        since = now
    # Normalize naive/aware mix (all times UTC)
    try:
        elapsed = now - since
    except TypeError:
        now_r = now.replace(tzinfo=None) if hasattr(now, "replace") else now
        since_r = since.replace(tzinfo=None) if hasattr(since, "replace") else since
        elapsed = now_r - since_r
    if elapsed >= COOLDOWN:
        return raw, None
    return prev_tier, since


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
        prev_row = db.get_score_row(leg.leg_id) or {"tier": "Green", "tier_since": None}
        prev_tier = prev_row.get("tier") or "Green"
        prev_since_raw = prev_row.get("tier_since")
        prev_since = None
        if prev_since_raw:
            try:
                prev_since = datetime.fromisoformat(prev_since_raw)
            except ValueError:
                prev_since = None
        if leg.end < today:
            if prev_tier != "Green":
                text = render_alert(leg.trip_id, leg, "Green", prev_tier, 0.0, [], now)
                a = {"trip_id": leg.trip_id, "leg_id": leg.leg_id, "kind": "CLOSED", "tier": "Green",
                     "prev_tier": prev_tier, "text": text, "created_at": now.isoformat()}
                db.log_alert(a)  # propagate: DB outage must go red in Actions
                fn = notifier or notify
                try:
                    fn(a)
                except Exception as e:
                    print(f"WARN: notify failed (alert persisted): {e}")
                    db.update_score(leg.trip_id, leg.leg_id, leg.place, leg.country, leg.lat, leg.lon,
                                    leg.start, leg.end, 0.0, prev_tier, "", now, tier_since=prev_since)
                else:
                    db.update_score(leg.trip_id, leg.leg_id, leg.place, leg.country, leg.lat, leg.lon,
                                    leg.start, leg.end, 0.0, "Green", "", now, tier_since=None)
                alerts_out.append(a)
                _LAST[leg.leg_id] = {"tier": "Green", "since": None}
            continue
        sigs = leg_signals(leg, stored, today)
        score = leg_score_from_signals(sigs)
        raw = tier_of(score)
        tier, tier_since = _tier_with_cooldown(prev_tier, prev_since, raw, now)
        top = max(sigs, key=lambda s: s["risk"]) if sigs else None
        driver = top["title"][:80] if top else ""
        if tier != prev_tier:
            kind = "ESCALATED" if _TIER_RANK[tier] > _TIER_RANK[prev_tier] else "DE-ESCALATED"
            text = render_alert(leg.trip_id, leg, tier, prev_tier, score, sigs, now)
            a = {"trip_id": leg.trip_id, "leg_id": leg.leg_id, "kind": kind, "tier": tier,
                 "prev_tier": prev_tier, "text": text, "created_at": now.isoformat()}
            db.log_alert(a)  # propagate: DB outage must go red in Actions
            fn = notifier or notify
            try:
                fn(a)
            except Exception as e:
                print(f"WARN: notify failed (alert persisted, will retry): {e}")
                # Do NOT advance tier, so next tick retries delivery
                db.update_score(leg.trip_id, leg.leg_id, leg.place, leg.country, leg.lat, leg.lon,
                                leg.start, leg.end, score, prev_tier, driver, now, tier_since=prev_since)
            else:
                db.update_score(leg.trip_id, leg.leg_id, leg.place, leg.country, leg.lat, leg.lon,
                                leg.start, leg.end, score, tier, driver, now, tier_since=tier_since)
            alerts_out.append(a)
        else:
            db.update_score(leg.trip_id, leg.leg_id, leg.place, leg.country, leg.lat, leg.lon,
                            leg.start, leg.end, score, tier, driver, now, tier_since=tier_since)
        _LAST[leg.leg_id] = {"tier": tier, "since": tier_since}
    return alerts_out


def main():
    db.init_db()
    poll_once(datetime.now(timezone.utc).replace(tzinfo=None))


if __name__ == "__main__":
    main()
