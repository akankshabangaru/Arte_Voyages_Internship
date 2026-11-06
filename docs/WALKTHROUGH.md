# Trip Risk — Short Walkthrough

## APIs used (all free, no key, via `monitor.py` every 30 min)

| API | What it gives | Needs |
|---|---|---|
| `earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_week.geojson` | Earthquakes M5+ | None |
| `gdacs.org/xml/rss.xml` | Flood / cyclone / volcano (Orange/Red) | None |
| `api.open-meteo.com/v1/forecast` | 14-day gusts/rain/heat per leg | None (dev tier) |
| `api.gdeltproject.org/.../doc.json` + `api.reliefweb.int/v1/reports` | News headlines → `data/cities15000.txt` (Geonames, local file) | None |
| `smtp.gmail.com:587` (Gmail) | Plain-text alert emails | `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_TO` |
| `libsql://…` (Turso) or `file:events.db` (local SQLite) | Scores / alerts / health store | Turso URL+token only for cloud |
| **Map tiles (display only)** | `carto-positron` = English-only basemap; old `open-street-map` showed local scripts (Arabic/Russian/…) | Internet to draw |

Scope filter: only events inside the 5-country bounding boxes (India, Nepal, Bhutan, Sri Lanka, Maldives) are kept (`feeds.in_scope`).

## Scoring (one formula for every leg)

```
proximity = exp(-dist_km / radius)   (radius by type: quake 300km, cyclone 400km, flood 150km, unrest 50km…)
time_overlap = overlap_days / leg_days
risk = severity × proximity × time_overlap × confidence
score = 1 - Π(1 - risk_i)           (noisy-OR, 0–1, multiple signals add up)
Tier:  🟢 Green < 0.15  |  🟡 Watch 0.15–0.45  |  🔴 Act ≥ 0.45
```

Alerts fire only on tier change; de-escalation needs 48h below threshold (no flicker).

## Dashboard segments (top → bottom)

| Segment | Live | Manual |
|---|---|---|
| **Toggle + summary** | `● Live` — `8 legs scored · 0 need review (Act) · 0 on watch` | `✎ Manual` — same strip + `Simulation only — what-if` banner |
| **KPI row** | DB counts (legs scored / Act alerts / total) | Same (Live counts; sim lives in Trip scores below) |
| **Trip scores table + bar** | Live scores from DB | **Overwritten by simulation** (all 8 legs recomputed from your sidebar hazard; picked leg `★`) |
| **Map** | Live legs, CARTO English labels, centre India (23.5, 78.5) zoom 4 | Simulated legs, same style/centre |
| **14-day outlook** | Forecast risk per leg-day (stored events) | Same (Live forecast, not simulated) |
| **Alert feed** | Live alerts from DB; empty → `No alerts yet — ...` (only tier changes ever log) | `showing simulated alerts (Live DB untouched)` — same cards, filterable |
| **Feed health** | Last OK/error per feed | Same |

## How the pieces connect

```
feeds.py (4 APIs) ──► scorer.py (formula above) ──► db.py (events/scores/alerts/health)
                                                      ▲      │
monitor.py every 30 min: fetch → upsert → score → alert on tier change → Gmail + DB
                                                      │      ▼
                                              dashboard.py (reads DB only, never calls feeds)
```

**Manual mode** reuses `simulate_manual()` (same formula, your hazard + thresholds) and never writes DB or sends email — it just recomputes the same 8 legs from `trips.csv`/scores and shows them in Trip scores + cards + Alert feed. That's why picking an earthquake changes the table colours only after you set **Event date inside the leg** (e.g. Delhi Dec 10–15).

## Map language note

Your data is already English. Mixing came from the basemap: `open-street-map` tiles label in each area's local script. `carto-positron` transliterates everything to English — hence the fix.
