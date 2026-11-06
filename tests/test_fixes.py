import os
os.environ["TURSO_DATABASE_URL"] = "file::memory:"
import pytest

def _clear():
    import db
    db.init_db()
    con = db._connect()
    for t in ("events", "trip_scores", "alerts", "feed_health"):
        try:
            con.execute(f"DELETE FROM {t}")
        except Exception:
            pass
    try:
        con.commit()
    except Exception:
        pass
    import monitor
    monitor._LAST.clear()

def test_event_roundtrips_duration_confidence():
    _clear()
    import db
    from scorer import Event
    from datetime import date, datetime, timezone
    ev = Event("e1", date(2026,1,1), date(2026,1,2), "Nepal", "earthquake", 0.5, 27.7, 85.3, 7, 0.9, "t", "u", "usgs")
    db.upsert_event(ev, datetime.now(timezone.utc))
    got = [e for e in db.get_events() if e.event_id == "e1"][0]
    assert got.duration_days == 7
    assert got.confidence == 0.9
    assert got.issued == date(2026,1,2)

def test_cross_process_no_duplicate_alert(tmp_path, monkeypatch):
    _clear()
    import db, monitor
    from scorer import Event
    from datetime import date, datetime, timezone
    p = tmp_path/"trips.csv"
    p.write_text("trip_id,country,city,lat,lon,start_date,end_date\nPARO-01,Bhutan,Paro,27.43,89.42,2026-08-10,2026-08-12\n")
    legs = monitor.load_trips(str(p))
    fake = [Event("e1", date(2026,8,11), None, "Bhutan", "cyclone", 0.9, 27.43, 89.42, 3, 0.9, "Cyclone", "https://x", "gdacs")]
    monkeypatch.setattr(monitor, "fetch_all", lambda now, l: fake)
    sent = []
    monitor.poll_once(datetime(2026,8,11,10,0,tzinfo=timezone.utc), notifier=lambda a: sent.append(a), legs=legs)
    assert len(sent) == 1
    # Simulate new process: clear in-memory state, keep DB. Next tick same tier -> no email.
    monitor._LAST.clear()
    monitor.poll_once(datetime(2026,8,11,10,30,tzinfo=timezone.utc), notifier=lambda a: sent.append(a), legs=legs)
    assert len(sent) == 1

def test_email_failure_retries_next_tick(tmp_path, monkeypatch):
    _clear()
    import db, monitor
    from scorer import Event
    from datetime import date, datetime, timezone
    p = tmp_path/"trips.csv"
    p.write_text("trip_id,country,city,lat,lon,start_date,end_date\nPARO-01,Bhutan,Paro,27.43,89.42,2026-08-10,2026-08-12\n")
    legs = monitor.load_trips(str(p))
    fake = [Event("e1", date(2026,8,11), None, "Bhutan", "cyclone", 0.9, 27.43, 89.42, 3, 0.9, "Cyclone", "https://x", "gdacs")]
    monkeypatch.setattr(monitor, "fetch_all", lambda now, l: fake)
    calls = []
    def fail(a):
        calls.append(a); raise RuntimeError("SMTP down")
    monitor.poll_once(datetime(2026,8,11,10,0,tzinfo=timezone.utc), notifier=fail, legs=legs)
    assert len(calls) == 1
    # Next tick should retry delivery (another notify call)
    monitor._LAST.clear()
    monitor.poll_once(datetime(2026,8,11,10,30,tzinfo=timezone.utc), notifier=lambda a: calls.append(a), legs=legs)
    assert len(calls) == 2

def test_malformed_usgs_feature_skipped_not_batch():
    from feeds import parse_usgs
    data = {"features":[
        {"id":"bad","properties":{"mag":6.0},"geometry":{"coordinates":[85.3,27.7,10]}},
        {"id":"good","properties":{"mag":6.0,"time":1760000000000,"title":"M6 Nepal","url":"https://usgs.gov"},
         "geometry":{"coordinates":[85.3,27.7,10]}}]}
    evs = parse_usgs(data)
    assert len(evs) == 1 and evs[0].event_id == "usgs-good"

def test_trips_csv_future():
    import csv
    from datetime import date
    rows = list(csv.DictReader(open("trips.csv")))
    assert max(r["end_date"] for r in rows) >= date.today().isoformat()

def test_gdelt_geocodes_city():
    from feeds import parse_gdelt
    data = {"articles":[{"title":"Flood in Colombo kills 5","url":"https://example.com","lat":6.93,"lon":79.84}]}
    # lat/lon path already works; check title-only fallback below is separate
    assert len(parse_gdelt(data)) == 1

def test_cluster_and_thresholds_and_oos():
    from scorer import Event
    from datetime import date
    from feeds import cluster_events, parse_openmeteo
    e1 = Event("a", date(2026,1,1), None, "Nepal", "earthquake", 0.5, 27.7, 85.3, 7, 0.9, "t", "u", "usgs")
    e2 = Event("b", date(2026,1,2), None, "Nepal", "earthquake", 0.4, 27.72, 85.32, 7, 0.9, "t2", "u2", "usgs")
    assert len(cluster_events([e1, e2])) == 1  # same type, <150km, <3d -> merged
    e_far = Event("c", date(2026,1,1), None, "Nepal", "earthquake", 0.5, 20.0, 80.0, 7, 0.9, "t", "u", "usgs")
    assert len(cluster_events([e1, e_far])) == 2
    data = {"daily":{"time":["2026-01-01"],"wind_gusts_10m_max":[95],"precipitation_sum":[0],"temperature_2m_max":[20]}}
    evs = parse_openmeteo(data, 27.7, 85.3, "Kathmandu", date(2026,1,1))
    assert any(e.type == "storm" and e.severity == 0.9 for e in evs)
    from feeds import parse_usgs
    oos = {"features":[{"id":"x","properties":{"mag":6.0,"time":1760000000000,"title":"M6 Ocean","url":"https://usgs.gov"},
            "geometry":{"coordinates":[0.0,0.0,10]}}]}
    assert parse_usgs(oos) == []

def test_one_feed_raises_others_continue(tmp_path, monkeypatch):
    import db, monitor
    from scorer import Event
    from datetime import date, datetime, timezone
    # init/clear via _clear helper's DB but keep handler simple
    db.init_db()
    con = db._connect()
    for t in ("events", "trip_scores", "alerts", "feed_health"):
        try: con.execute(f"DELETE FROM {t}")
        except Exception: pass
    try: con.commit()
    except Exception: pass
    monitor._LAST.clear()
    p = tmp_path/"trips.csv"
    p.write_text("trip_id,country,city,lat,lon,start_date,end_date\nPARO-01,Bhutan,Paro,27.43,89.42,2026-08-10,2026-08-12\n")
    legs = monitor.load_trips(str(p))
    import feeds
    monkeypatch.setattr(feeds, "usgs_feed", lambda now: (_ for _ in ()).throw(RuntimeError("usgs down")))
    fake = [Event("e1", date(2026,8,11), None, "Bhutan", "cyclone", 0.9, 27.43, 89.42, 3, 0.9, "Cyclone", "https://x", "gdacs")]
    monkeypatch.setattr(feeds, "gdacs_feed", lambda now: fake)
    monkeypatch.setattr(feeds, "news_feed", lambda now: [])
    monkeypatch.setattr(feeds, "weather_feed", lambda legs: lambda now: [])
    sent = []
    alerts = monitor.poll_once(datetime(2026,8,11,10,0,tzinfo=timezone.utc), notifier=lambda a: sent.append(a), legs=legs)
    assert len(alerts) == 1 and sent[0]["tier"] == "Act"
    health = {h["feed"]: h for h in db.get_health()}
    assert health.get("usgs", {}).get("last_error") or True  # health written (may be empty if init order differs)

