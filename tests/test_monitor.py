import os
os.environ["TURSO_DATABASE_URL"] = "file::memory:"
import pytest

@pytest.fixture(autouse=True)
def _reset():
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
    yield

def test_poll_once_creates_alert_and_skips_bad_csv(tmp_path, monkeypatch):
    import db
    import monitor
    p = tmp_path/"trips.csv"
    p.write_text("trip_id,country,city,lat,lon,start_date,end_date\n"
                 "BAD,India,Delhi,,,, \n"
                 "PARO-01,Bhutan,Paro,27.43,89.42,2026-08-10,2026-08-12\n")
    legs = monitor.load_trips(str(p))
    assert [l.leg_id for l in legs] == ["PARO-01"]  # bad row skipped
    # fake feeds: one Red cyclone at Paro → Act
    from scorer import Event
    from datetime import date, datetime, timezone
    fake = [Event("e1", date(2026,8,11), None, "Bhutan", "cyclone", 0.9, 27.43, 89.42, 3, 0.9, "Cyclone 90 km/h", "https://gdacs.org/x", "gdacs")]
    sent = []
    monkeypatch.setattr(monitor, "fetch_all", lambda now, l: fake)
    monkeypatch.setattr(monitor, "notify", lambda a: sent.append(a))
    alerts = monitor.poll_once(datetime(2026,8,11,10,0,tzinfo=timezone.utc), notifier=lambda a: sent.append(a), legs=legs)
    assert len(sent) == 1 and sent[0]["tier"] == "Act" and "🔴" in sent[0]["text"]
    # second tick same tier → no duplicate email
    alerts2 = monitor.poll_once(datetime(2026,8,11,10,30,tzinfo=timezone.utc), notifier=lambda a: sent.append(a), legs=legs)
    assert len(sent) == 1
def test_email_failure_still_persists(monkeypatch, tmp_path):
    import db
    import monitor
    from scorer import Event
    from datetime import date, datetime, timezone
    p = tmp_path/"trips.csv"
    p.write_text("trip_id,country,city,lat,lon,start_date,end_date\n"
                 "PARO-01,Bhutan,Paro,27.43,89.42,2026-08-10,2026-08-12\n")
    legs = monitor.load_trips(str(p))
    fake = [Event("e2", date(2026,8,11), None, "Bhutan", "cyclone", 0.9, 27.43, 89.42, 3, 0.9, "Cyclone", "https://gdacs.org/x", "gdacs")]
    monkeypatch.setattr(monitor, "fetch_all", lambda now, l: fake)
    def boom(a): raise RuntimeError("SMTP down")
    alerts = monitor.poll_once(datetime(2026,8,12,10,0,tzinfo=timezone.utc), notifier=boom, legs=legs)
    assert len(alerts) == 1 and len(db.get_alerts()) >= 1  # persisted despite email failure
