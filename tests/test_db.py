import os
os.environ["TURSO_DATABASE_URL"] = "file::memory:"
def test_upsert_get_roundtrip():
    import db; db.init_db()
    con = db._connect()
    for t in ("events", "feed_health"):
        try:
            con.execute(f"DELETE FROM {t}")
        except Exception:
            pass
    try:
        con.commit()
    except Exception:
        pass
    from scorer import Event
    from datetime import date, datetime, timezone
    ev = Event("e1", date(2026,1,1), None, "Nepal", "earthquake", 0.5, 27.7, 85.3, 7, 0.9, "t", "u", "usgs")
    db.upsert_event(ev, datetime.now(timezone.utc))
    assert any(e.event_id == "e1" for e in db.get_events())
    db.upsert_health("usgs", True, "")
    assert any(h["feed"] == "usgs" for h in db.get_health())
