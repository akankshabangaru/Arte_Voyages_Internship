def test_noisy_or_and_tiers():
    from scorer import noisy_or, tier_of, Event, Leg, proximity
    from datetime import date
    assert noisy_or([]) == 0.0
    assert noisy_or([0.5, 0.5]) == 0.75
    assert tier_of(0.1) == "Green"
    assert tier_of(0.15) == "Watch"
    assert tier_of(0.45) == "Act"
    e = Event(event_id="e1", date=date(2026,8,10), issued=None, country="Bhutan",
              type="cyclone", severity=0.9, lat=27.43, lon=89.42, duration_days=3,
              confidence=0.9, title="t", url="u", source="gdacs")
    leg = Leg(leg_id="l1", trip_id="PARO-01", place="Paro", country="Bhutan",
              lat=27.43, lon=89.42, start=date(2026,8,10), end=date(2026,8,12))
    assert proximity(e, leg) == 1.0
