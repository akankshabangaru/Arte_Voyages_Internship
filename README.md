# Continuous Trip Risk Monitoring

Realtime continuous monitoring for **India, Nepal, Bhutan, Sri Lanka, Maldives**. Polls free feeds every 30 minutes, scores each trip leg with severity, and emails plain-text alerts (`🟢 Green / 🟡 Watch / 🔴 Act`). This is the clean rebuild per `C:\Users\chara\.opencode\plan\2026-11-06-trip-risk-design.md`; legacy `src/`, `app.py`, `live_app.py` are kept for reference but are not used.

## Quick start (local, SQLite file)

```bash
pip install -r requirements.txt
cp .env.example .env   # set GMAIL_USER, GMAIL_APP_PASSWORD, ALERT_TO
# local default: TURSO_DATABASE_URL=file:events.db (no Turso needed)
python -m monitor
pytest -v
streamlit run dashboard.py
```

## Cloud (Turso + Actions + Streamlit, $0)

1. Create a Turso database (free) → copy `TURSO_DATABASE_URL` (`libsql://…`) and `TURSO_AUTH_TOKEN`.
2. Gmail: Google Account → Security → App passwords → create one for mail. No account passwords in repo.
3. GitHub repo → Settings → Secrets → Actions: add `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_TO`.
4. Push. `.github/workflows/monitor.yml` runs `python -m monitor` every 30 minutes.
5. Streamlit Community Cloud → New app → `dashboard.py`, add the same `TURSO_DATABASE_URL` secret. Dashboard reads Turso only.

## trips.csv

Edit `trips.csv` (columns: `trip_id,country,city,lat,lon,start_date,end_date`). Rows with missing lat/lon or `end < start` are skipped with a warning. One row = one leg.

## How scoring works

```text
risk = severity × proximity × time_overlap × confidence
leg_score = 1 - Π(1 - risk_i)   # noisy-OR
trip_score = max(leg_scores)
Green < 0.15 | Watch 0.15–0.45 | Act ≥ 0.45
```

Tiers rise immediately, fall only after 48h below threshold. One email per escalation; de-escalation (`Act→Watch`) and `CLOSED` (leg finished) email once.

## Feeds (all free, no key)

- Earthquakes: USGS JSON (`min(1, (M-4.5)/4)`, confidence 0.9)
- Disasters: GDACS RSS (Green 0.2 / Orange 0.55 / Red 0.9, confidence 0.9)
- Weather: Open-Meteo 14-day (gusts/rain/heat thresholds → 0.55/0.9, confidence 0.6)
- News: GDELT DOC + ReliefWeb JSON (keyword severity 0.8/0.55/0.35, confidence 0.6), clustered within 150 km / 3 days

Only events inside the 5-country bounding boxes are kept.

## Example alert

```text
🔴 ACT — cyclone Cyclone 90 km/h — Severity 0.72
Trip: PARO-01 (Bhutan, Paro, 10 Aug–12 Aug) | Leg risk: 0.72 -> Act (was Watch)
Driver: Cyclone 90 km/h (cyclone)
Source: https://gdacs.org/x
Monitored: 11 Aug 2026 10:00 UTC
Action: Review now, consider buffer day / reroute, contact partners.
```

## Honest limits

- Weights, radii, and thresholds are starting guesses. Do not present them as validated accuracy.
- Open-Meteo free tier is non-commercial dev use — check terms before any commercial use.
- GDELT news is noisy; clustering reduces but does not eliminate false alerts.
- The system never takes action; it only alerts a human. It does not predict individual earthquakes.
- Traveller names/bookings are never sent to any feed (only rounded lat/lons for weather).

## Licences / sources

- GDACS: https://gdacs.org (see site for terms; set the exact licence link here before production)
- GeoNames `data/cities15000.txt`: believed CC BY 4.0 — confirm at https://geonames.org and add the link
- Open-Meteo: https://open-meteo.com (non-commercial dev tier)
- USGS: public-domain US government earthquake feed
