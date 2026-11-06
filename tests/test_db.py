import os
os.environ["TURSO_DATABASE_URL"] = "file::memory:"
def test_upsert_get_roundtrip():
    import db; db.init_db()
    from scorer import Event
    from datetime import date, datetime, timezone
    ev = Event("e1", date(2026,1,1), None, "Nepal", "earthquake", 0.5, 27.7, 85.3, 7, 0.9, "t", "u", "usgs")
    db.upsert_event(ev, datetime.now(timezone.utc))
    assert db.get_events()[0].event_id == "e1"
    db.upsert_health("usgs", True, "")
    assert db.get_health()[0]["feed"] == "usgs"
