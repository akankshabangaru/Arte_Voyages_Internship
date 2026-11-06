"""Free feed adapters (no key): USGS, GDACS, Open-Meteo, GDELT, ReliefWeb.
parse_* are pure and tested offline; *_feed(now) do network calls.
Only events inside the 5-country bounding boxes are kept."""
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from email.utils import parsedate_to_datetime

from scorer import Event, Leg, haversine_km

USGS_URL = "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson"
GDACS_URL = "https://www.gdacs.org/xml/rss.xml"
METEO_URL = "https://api.open-meteo.com/v1/forecast"
GDELT_URL = "https://api.gdeltproject.org/api/v2.1/doc/doc.json"
RELIEFWEB_URL = "https://api.reliefweb.int/v1/reports"
GDACS_TYPES = {"EQ": "earthquake", "TC": "cyclone", "FL": "flood", "VO": "eruption", "DR": "drought", "WF": "wildfire"}
LEVEL_SEVERITY = {"green": 0.2, "orange": 0.55, "red": 0.9}
MIN_DURATION = {"earthquake": 7, "eruption": 14, "cyclone": 3, "flood": 3}

# (lat_min, lat_max, lon_min, lon_max)
COUNTRY_BBOX = {
    "India": (6.5, 37.0, 68.0, 97.5),
    "Nepal": (26.0, 30.6, 80.0, 88.5),
    "Bhutan": (26.5, 28.5, 88.5, 92.5),
    "Sri Lanka": (5.5, 10.0, 79.5, 82.0),
    "Maldives": (-0.5, 7.5, 72.0, 74.5),
}
NEGATIVE_COUNTRIES = ["India", "Nepal", "Bhutan", "Sri Lanka", "Maldives"]
NEWS_KEYWORDS_HIGH = ["killed", "evacuated", "landfall", "cyclone"]
NEWS_KEYWORDS_MED = ["warning", "heavy rain", "protest", "outbreak"]


def in_scope(lat: float, lon: float) -> str | None:
    for country in ("Nepal", "Bhutan", "Sri Lanka", "Maldives", "India"):
        a, b, c, d = COUNTRY_BBOX[country]
        if a <= lat <= b and c <= lon <= d:
            return country
    return None


def _get(url, **kw):
    import requests
    r = requests.get(url, timeout=20, headers={"User-Agent": "trip-risk-monitor/1.0"}, **kw)
    r.raise_for_status()
    return r


def parse_usgs(data: dict, min_mag: float = 5.0) -> list[Event]:
    out = []
    try:
        features = data.get("features", []) or []
    except AttributeError:
        return []
    for f in features:
        try:
            p, (lon, lat, *_rest) = f["properties"], f["geometry"]["coordinates"]
        except (KeyError, TypeError, ValueError):
            continue
        if p.get("mag") is None or p["mag"] < min_mag:
            continue
        country = in_scope(lat, lon)
        if country is None:
            continue
        day = datetime.fromtimestamp(p["time"] / 1000, tz=timezone.utc).date()
        out.append(Event(event_id=f"usgs-{f['id']}", date=day, issued=day, country=country, type="earthquake",
                         severity=min(1.0, (p["mag"] - 4.5) / 4), lat=lat, lon=lon,
                         duration_days=MIN_DURATION["earthquake"], confidence=0.9,
                         title=p.get("title") or f"M{p['mag']} {p.get('place', '')}",
                         url=p.get("url", ""), source="usgs"))
    return out


def _txt(it, tag):
    el = it.find("{*}" + tag)
    return el.text.strip() if el is not None and el.text else None


def parse_gdacs(xml_text: str) -> list[Event]:
    out = []
    try:
        root = ET.fromstring(xml_text)
    except (ET.ParseError, TypeError, ValueError):
        return []
    for it in root.iter("item"):
        etype = GDACS_TYPES.get((_txt(it, "eventtype") or "").upper())
        level = (_txt(it, "alertlevel") or "").lower()
        lat_s, lon_s = _txt(it, "lat"), _txt(it, "long")
        if not etype or level not in LEVEL_SEVERITY or lat_s is None or lon_s is None:
            continue
        try:
            lat, lon = float(lat_s), float(lon_s)
        except ValueError:
            continue
        country = in_scope(lat, lon) or (_txt(it, "country") or "")
        if in_scope(lat, lon) is None:
            continue
        try:
            frm = parsedate_to_datetime(_txt(it, "fromdate") or _txt(it, "pubDate")).date()
        except (TypeError, ValueError):
            continue
        to = _txt(it, "todate")
        try:
            dur = (parsedate_to_datetime(to).date() - frm).days if to else 3
        except (TypeError, ValueError):
            dur = 3
        out.append(Event(event_id=f"gdacs-{etype}-{_txt(it, 'eventid') or _txt(it, 'guid') or len(out)}", date=frm,
                         issued=frm, country=country, type=etype, severity=LEVEL_SEVERITY[level],
                         lat=lat, lon=lon, duration_days=max(MIN_DURATION.get(etype, 1), min(60, dur)),
                         confidence=0.9, title=_txt(it, "title") or etype, url=_txt(it, "link") or "",
                         source="gdacs"))
    return out


def parse_openmeteo(data: dict, lat: float, lon: float, place: str, today: date) -> list[Event]:
    try:
        d = data["daily"]
    except (KeyError, TypeError):
        return []
    country = in_scope(lat, lon) or ""
    out = []
    rules = (("storm", "wind_gusts_10m_max", "km/h", [(90, 0.9), (70, 0.55)]),
             ("rain", "precipitation_sum", "mm", [(100, 0.9), (50, 0.55)]),
             ("heatwave", "temperature_2m_max", "C", [(42, 0.9), (40, 0.55)]))
    try:
        times = d["time"]
    except (KeyError, TypeError):
        return []
    for i, day in enumerate(times):
        for kind, key, unit, steps in rules:
            try:
                val = d[key][i]
            except (KeyError, IndexError, TypeError):
                continue
            sev = next((s for thr, s in steps if val is not None and val >= thr), None)
            if sev:
                out.append(Event(event_id=f"wx-{place}-{kind}-{day}", date=date.fromisoformat(day), issued=today,
                                 country=country, type=kind, severity=sev, lat=lat, lon=lon, duration_days=1,
                                 confidence=0.6, title=f"Forecast {kind} at {place}: {val} {unit} on {day}",
                                 url="https://open-meteo.com", source="open-meteo"))
    return out


def _news_severity(title: str) -> float:
    t = title.lower()
    if any(k in t for k in NEWS_KEYWORDS_HIGH):
        return 0.8
    if any(k in t for k in NEWS_KEYWORDS_MED):
        return 0.55
    return 0.35


def parse_gdelt(data: dict) -> list[Event]:
    out = []
    try:
        arts = (data.get("articles") or [])
    except AttributeError:
        return []
    for a in arts:
        title = (a.get("title") or "").strip()
        url = a.get("url") or ""
        if not title:
            continue
        # GDELT DOC ArtList has no lat/lon; use url country hints or skip geo-less headlines
        # (city matching via GeoNames is deferred to avoid noisy geo guesses).
        lat = a.get("lat") or a.get("latitude")
        lon = a.get("lon") or a.get("longitude")
        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (ValueError, TypeError):
            continue
        country = in_scope(lat, lon)
        if country is None:
            continue
        try:
            day = datetime.fromisoformat((a.get("seendate") or a.get("date") or "")[:10]).date() if (a.get("seendate") or a.get("date")) else datetime.now(timezone.utc).date()
        except ValueError:
            day = datetime.now(timezone.utc).date()
        out.append(Event(event_id=f"gdelt-{len(out)}-{url[-12:]}", date=day, issued=day, country=country,
                         type="news", severity=_news_severity(title), lat=lat, lon=lon, duration_days=1,
                         confidence=0.6, title=title, url=url, source="gdelt"))
    return out


def parse_reliefweb(data: dict) -> list[Event]:
    out = []
    try:
        items = (data.get("data") or [])
    except AttributeError:
        return []
    for it in items:
        try:
            fields = it.get("fields", {}) or {}
        except AttributeError:
            continue
        title = (fields.get("title") or "").strip()
        url = fields.get("url") or ""
        if not title:
            continue
        lat = fields.get("lat")
        lon = fields.get("lon")
        if lat is None or lon is None:
            continue
        try:
            lat, lon = float(lat), float(lon)
        except (ValueError, TypeError):
            continue
        country = in_scope(lat, lon)
        if country is None:
            continue
        try:
            day = datetime.fromisoformat((fields.get("date") or "")[:10]).date()
        except ValueError:
            day = datetime.now(timezone.utc).date()
        out.append(Event(event_id=f"reliefweb-{it.get('id', len(out))}", date=day, issued=day, country=country,
                         type="news", severity=_news_severity(title), lat=lat, lon=lon, duration_days=1,
                         confidence=0.6, title=title, url=url, source="reliefweb"))
    return out


def cluster_events(events: list[Event]) -> list[Event]:
    grouped: list[Event] = []
    for e in events:
        merged = False
        for g in grouped:
            if g.type == e.type and abs((e.date - g.date).days) <= 3 and haversine_km(e.lat, e.lon, g.lat, g.lon) <= 150:
                if e.severity > g.severity:
                    g.severity = e.severity
                    g.title = e.title
                if e.url and e.url != g.url:
                    g.url = f"{g.url} | {e.url}"
                merged = True
                break
        if not merged:
            grouped.append(e)
    return grouped


def usgs_feed(now) -> list[Event]:
    return cluster_events(parse_usgs(_get(USGS_URL).json()))


def gdacs_feed(now) -> list[Event]:
    return cluster_events(parse_gdacs(_get(GDACS_URL).text))


def news_feed(now) -> list[Event]:
    out: list[Event] = []
    try:
        out += parse_gdelt(_get(GDELT_URL, params={"query": "India OR Nepal OR Bhutan OR \"Sri Lanka\" OR Maldives", "mode": "ArtList", "maxrecords": 75, "format": "json"}).json())
    except Exception:
        pass
    try:
        out += parse_reliefweb(_get(RELIEFWEB_URL, params={"appname": "trip-risk-monitor", "limit": 50, "filter[column_fields]": "title,url,date,lat,lon"}).json())
    except Exception:
        pass
    # Boost confidence if two reports agree (same type/day within 150km is handled by clustering)
    return cluster_events(out)


def weather_feed(trips):
    locs = {(round(l.lat, 2), round(l.lon, 2), l.place) for t in trips for l in t} if trips and trips and isinstance(trips[0], list) else set()
    # Accept list[Leg] (new monitor) or list[Trip] (legacy) defensively
    if trips and len(trips) > 0 and hasattr(trips[0], "lat"):
        locs = {(round(l.lat, 2), round(l.lon, 2), l.place) for l in trips}
    elif trips and len(trips) > 0 and hasattr(trips[0], "legs"):
        locs = {(round(l.lat, 2), round(l.lon, 2), l.place) for t in trips for l in t.legs}

    def fetch(now) -> list[Event]:
        out = []
        for lat, lon, place in locs:
            r = _get(METEO_URL, params={"latitude": lat, "longitude": lon, "forecast_days": 14, "timezone": "auto",
                                        "daily": "precipitation_sum,wind_gusts_10m_max,temperature_2m_max"}).json()
            out += parse_openmeteo(r, lat, lon, place, now.date())
        return out

    fetch.replaces = "wx-"
    fetch.name = "weather_feed"
    return fetch
