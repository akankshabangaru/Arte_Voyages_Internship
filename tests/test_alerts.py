def test_render_contains_severity_and_source(monkeypatch):
    from datetime import date, datetime, timezone
    from scorer import Leg; from alerts import render_alert
    leg = Leg("l1","PARO-01","Paro","Bhutan",27.43,89.42,date(2026,8,21),date(2026,8,24))
    txt = render_alert("PARO-01", leg, "Act", "Watch", 0.72,
        [{"kind":"cyclone","title":"Cyclone 90 km/h","url":"https://gdacs.org/x","risk":0.72}],
        datetime(2026,8,21,10,30,tzinfo=timezone.utc))
    assert "🔴 ACT" in txt and "Severity" in txt and "https://gdacs.org/x" in txt
    assert "Paro" in txt and "0.72" in txt
