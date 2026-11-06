def test_parse_usgs_severity_and_filter():
    from feeds import parse_usgs, in_scope
    data = {"features":[{"id":"abc","properties":{"mag":6.0,"time":1760000000000,"title":"M6 Nepal","url":"https://usgs.gov"},
            "geometry":{"coordinates":[85.3,27.7,10]}}]}
    evs = parse_usgs(data)
    assert abs(evs[0].severity - 0.375) < 1e-6  # (6-4.5)/4
    assert evs[0].confidence == 0.9
    assert in_scope(27.7, 85.3) == "Nepal"
    assert in_scope(0, 0) is None

def test_bad_feed_is_empty_not_crash():
    from feeds import parse_gdacs
    assert parse_gdacs("<not gdacs><oops/></not>") == []
