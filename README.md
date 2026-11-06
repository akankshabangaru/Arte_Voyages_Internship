# Continuous Trip Risk Monitoring

> **Realtime, free, severity-aware trip monitoring for India, Nepal, Bhutan, Sri Lanka and Maldives — it watches free disaster/weather/news feeds every 30 minutes and emails you a plain-text alert when a booked trip leg is at risk.**

This repo is a clean rebuild (2026-11-06). It replaces the earlier prototype (`src/`, `app.py`, `live_app.py`) with a small, free-tier system: **6 Python files + 1 CSV**. The legacy prototype is kept untouched for reference but is not used by the new monitor.

**Cost to run: $0/month** (GitHub Actions free minutes, Turso free DB, Streamlit free hosting, Gmail, and no-key data feeds).

---

## Table of Contents

- [What is it?](#what-is-it)
- [Features](#features)
- [How it works](#how-it-works)
- [Free stack (all $0)](#free-stack-all-0)
- [Scoring & severity](#scoring--severity)
- [Data feeds](#data-feeds)
- [Text alerts + severity (the core requirement)](#text-alerts--severity-the-core-requirement)
- [Database (Turso SQLite)](#database-turso-sqlite)
- [Project structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Quick start — local (SQLite file)](#quick-start--local-sqlite-file)
- [Deploy to cloud — Turso + Actions + Streamlit ($0)](#deploy-to-cloud--turso--actions--streamlit-0)
- [Dashboard guide](#dashboard-guide)
- [Configuration](#configuration)
- [Tests](#tests)
- [Error handling](#error-handling)
- [Limitations & honest notes](#limitations--honest-notes)
- [Roadmap](#roadmap)
- [FAQ / Troubleshooting](#faq--troubleshooting)
- [Licences & sources](#licences--sources)

<a id="what-is-it"></a>

## What is it?

Organisers of tourism trips track hazards, advisories, weather and news by hand across many live trips. A risk to a traveller's leg can be noticed late.

This system does the watching automatically:

1. **Collects signals** — earthquakes, floods, cyclones, storms, eruptions, wildfires, severe weather, and news headlines — from free sources.
2. **Matches each signal** to the trip legs it could affect, by **place (lat/lon)** and **dates**.
3. **Scores risk** per leg and per trip (worst leg = trip score) and assigns a tier: **🟢 Green / 🟡 Watch / 🔴 Act**.
4. **Emails a plain-text alert** naming the driver, severity, source link and what to do. The same text appears in the dashboard.

**Who is it for?** Single operator monitoring demo trips (a travel manager's view). No team routing, no traveller messaging — every alert goes to a human who decides.

**Geographic scope (only these 5):** India 🇮🇳 · Nepal 🇳🇵 · Bhutan 🇧🇹 · Sri Lanka 🇱🇰 · Maldives 🇲🇻. Events outside bounding boxes for these countries are ignored.

<a id="features"></a>

## Features

- **Continuous polling every 30 min** via GitHub Actions cron — works even when your PC is off.
- **4 signal types in one pipeline:** natural disasters + severe weather + news headlines (advisories deferred).
- **Severity-aware scoring** — every alert carries an explicit severity (0–1 score + tier + emoji).
- **Plain-text alerts by email (Gmail SMTP) + dashboard feed** — no LLM, no paid services.
- **Anti-spam:** one alert per escalation, 48-hour downgrade cooldown, clustering so 10 articles about one event count as one.
- **Live dashboard:** trip scores, map, 14-day outlook, alert history, feed-health banner.
- **Resilient:** one feed failing never stops the tick; email failures retry next tick; DB failures go red in Actions.
- **Tested:** 29 tests (unit + integration) — run `pytest -q`, all green.

<a id="how-it-works"></a>

## How it works

```
trips.csv ──┐
            ├─> monitor.py ──> Turso DB (SQLite) ──> dashboard.py (Streamlit)
feeds ──────┘        │
                     └──> alerts.py → Gmail → operator inbox
```

**One tick (`python -m monitor`), every 30 minutes:**

1. Load `trips.csv`, keep trips where `start − 14 days ≤ today ≤ end`.
2. Poll each feed independently (`usgs`, `gdacs`, `weather`, `news`). Record `feed_health` per feed; a failing feed is logged and skipped.
3. Upsert new/updated events into Turso (keeps `first_seen`; re-fetch is idempotent via `events.id`).
4. Score every active leg against all stored events (present + 14-day forecast). Compare tier to the tier stored in DB.
5. On tier change → insert alert row, email it (email failure retries next tick). Update `trip_scores` snapshot for the dashboard.

> "Realtime" here means polling every 30 minutes, not streaming. That is sufficient for travel risk and fits free tiers.

<a id="free-stack-all-0"></a>

## Free stack (all $0)

| Layer | Service | Free limit | What you get |
|---|---|---|---|
| Cron scheduler | GitHub Actions (`*/30 * * * *`) | 2,000 min/mo (job <60s) | Runs `python -m monitor` 24/7 |
| Database | Turso (libSQL, SQLite-compatible) | 100 DBs, 5 GB | Real SQLite SQL, shared Actions ↔ dashboard |
| Dashboard | Streamlit Community Cloud | Free (sleeps idle) | Map, scores, alerts, outlook — DB is the source of truth |
| Earthquakes | USGS JSON feed | No key | M5+, past week |
| Disasters | GDACS RSS/API | No key | Flood/cyclone/volcano, Orange/Red |
| Weather | Open-Meteo | Free dev use | 14-day gusts/rain/heat per leg |
| News | GDELT DOC 2.1 + ReliefWeb JSON | No key | Country + hazard keywords, clustered |
| Place lookup | GeoNames `data/cities15000.txt` | CC BY 4.0 (confirm link) | Offline headline city → lat/lon |
| Email | Gmail SMTP (App Password) | ~500/day | Severity alerts in text |

> **Local vs cloud:** locally you use `TURSO_DATABASE_URL=file:events.db` (identical SQL). In cloud you use `libsql://…` + token. `db.py` switches automatically — no code branch.

<a id="scoring--severity"></a>

## Scoring & severity

```text
proximity     = exp(-dist_km / radius)   if dist < 3*radius else 0
time_overlap  = overlap_days / leg_days
risk          = severity × proximity × time_overlap × confidence
leg_score     = 1 - Π(1 - risk_i)        # noisy-OR, 0..1
trip_score    = max(leg_scores)
Tiers: Green < 0.15 | Watch 0.15–0.45 | Act ≥ 0.45
```

- **Severity (0–1)** is how strong the hazard is. **Confidence** is how much you trust the source. Both are explicit in code, not hidden.
- Multiple weak signals **add up** via noisy-OR without ever exceeding 1.
- **Tier rises immediately, falls only after 48h** continuously below the threshold (prevents flicker). Downgrade state (`tier_since`) is stored in DB, so it survives across Actions runs — no email storm.
- **Dedup key:** `(event_id, trip_id, leg_id)` — same event emails again only if the tier escalates.
- `CLOSED` is emitted once when a leg ends (tier forced to Green).

### Severity & confidence tables (verbatim from spec)

| Source | Severity | Confidence |
|---|---|---|
| USGS (M) | `min(1, (M-4.5)/4)` → M5=0.13, M6=0.38, M7=0.63, M8=0.88 | 0.9 |
| GDACS level | Green 0.2, Orange 0.55, Red 0.9 | 0.9 |
| Open-Meteo gust | ≥70 → 0.55, ≥90 km/h → 0.9 | 0.6 |
| Open-Meteo rain | ≥50 → 0.55, ≥100 mm/day → 0.9 | 0.6 |
| Open-Meteo heat | ≥40 → 0.55, ≥42°C → 0.9 | 0.6 |
| News keywords | `killed/evacuated/landfall/cyclone` 0.8; `warning/heavy rain/protest/outbreak` 0.55; else 0.35 | 0.6 |

### Radii (km)

Earthquake 300 · Cyclone 400 · Heatwave 300 · Drought 500 · Storm 200 · Flood 150 · Rain 100 · Eruption 100 · Wildfire 100 · Unrest 50 · Default 150.

Minimum active window: earthquake 7 days, eruption 14, cyclone 3, flood 3, else 1 — one quake disrupts days after it.

<a id="data-feeds"></a>

## Data feeds

Every fetcher returns the same `Event` shape (`scorer.Event`):

```python
Event(event_id, date, issued, country, type, severity, lat, lon,
      duration_days, confidence, title, url, source)
```

| Feed | File | Notes |
|---|---|---|
| USGS | `feeds.py: parse_usgs / usgs_feed` | M5+, JSON, 30-min poll |
| GDACS | `feeds.py: parse_gdacs / gdacs_feed` | RSS/XML, Orange/Red only |
| Open-Meteo | `feeds.py: weather_feed(legs)` | 14-day daily; leg coords rounded to 2 decimals before sending |
| GDELT + ReliefWeb | `feeds.py: parse_gdelt / parse_reliefweb / news_feed` | Title → GeoNames city match (substring + `rapidfuzz` typo tolerance), else skip |
| Geo filter | `feeds.py: in_scope(lat, lon)` | 5-country bounding boxes; smaller countries checked first (India box contains Nepal, so order matters) |
| Clustering | `feeds.py: cluster_events` | Same type + ≤150 km + ≤3 days → one event (max severity, merged links) |

> **Privacy:** traveller names/bookings are never sent to any feed. Only rounded lat/lon go to Open-Meteo.

<a id="text-alerts--severity-the-core-requirement"></a>

## Text alerts + severity (the core requirement)

Every alert is **plain text** with severity first, emailed and stored. Dashboard shows the identical text.

**Email subject:** `[ACT] 🔴 ACT — …` (tier + driver + severity)

**Body (exact template):**

```text
🔴 ACT — cyclone Cyclone 90 km/h — Severity 0.72
Trip: PARO-01 (Bhutan, Paro, 21–24 Aug) | Leg risk: 0.72 → ACT (was Watch)
Driver: Cyclone 90 km/h (cyclone)
Source: https://gdacs.org/…
Monitored: 06 Nov 10:30 UTC
Action: Review now, consider buffer day / reroute, contact partners.
```

| Tier | Meaning | Action line | When emailed |
|---|---|---|---|
| 🟢 Green | No action | `No action.` | Only as de-escalation/`CLOSED` |
| 🟡 Watch | Monitor closely | `Monitor closely.` | On entry from Green, on drop to Watch |
| 🔴 Act | Review now | `Review now, consider buffer day / reroute, contact partners.` | On Watch→Act immediately |

**Retry rule:** the alert row is written to DB *before* email. If SMTP fails, the tier in DB stays at the old value, so the next tick retries delivery — you never silently lose an Act email.

<a id="database-turso-sqlite"></a>

## Database (Turso SQLite)

Four tables (see `db.py` `SCHEMA`):

- `events` — all stored signals (`id, type, country, lat, lon, event_date, severity, title, source_url, first_seen, duration_days, confidence, issued`)
- `trip_scores` — current tier/score per leg + `tier_since` (48h cooldown state)
- `alerts` — full plain-text alert history (`trip_id, leg_id, kind, tier, prev_tier, text, created_at`)
- `feed_health` — last OK / last error per feed (dashboard banner)

Local file and Turso share SQL. `db.py` selects `sqlite3` for `file:` URLs and `libsql-client` for `libsql://` URLs.

<a id="project-structure"></a>

## Project structure

New MVP (root files — this is what you run):

| File | What it does |
|---|---|
| `scorer.py` | `Leg`/`Event` models + `haversine_km`, `proximity`, `time_overlap`, `noisy_or`, `tier_of`, `leg_signals`, `leg_score_from_signals` |
| `feeds.py` | Pure parsers (`parse_usgs`, `parse_gdacs`, `parse_openmeteo`, `parse_gdelt`, `parse_reliefweb`, `cluster_events`, `geocode_title`, `in_scope`) + network wrappers |
| `db.py` | Turso/sqlite helper (`init_db`, `upsert_event`, `get_events`, `update_score`, `get_score_row`, `log_alert`, `get_alerts`, `upsert_health`) |
| `alerts.py` | `render_alert` (severity template), `send_email` (Gmail SMTP), `notify` |
| `monitor.py` | `load_trips`, `fetch_all`, `poll_once`, `main` — the 30-min loop (`python -m monitor`) |
| `dashboard.py` | Streamlit app — scores, map, outlook, alert feed, health |
| `trips.csv` | Demo trips (8 legs, all 5 countries) — edit this to change what is monitored |
| `requirements.txt` | `pandas, numpy, streamlit, plotly, pytest, rapidfuzz, requests, libsql-client, python-dotenv, folium` |
| `.env.example` | Env template (never commit real `.env`) |
| `.github/workflows/monitor.yml` | Actions cron `*/30 * * * *` → `python -m monitor` |
| `tests/` | `test_scorer`, `test_feeds`, `test_db`, `test_alerts`, `test_monitor`, `test_dashboard`, `test_fixes`, `test_scaffold` (+ legacy `test_live`, `test_scoring` still pass) |

Legacy (kept, not used): `src/` (17-file prototype), `app.py`, `live_app.py`, `backtest.py`, `try_extract.py`, `data/`, `*.docx`, `*.xlsx`, `Architecture plan.txt`.

<a id="prerequisites"></a>

## Prerequisites

- **Python 3.12** (locally 3.14 also works; Actions pins 3.12)
- **Free accounts:** Turso, Gmail (App Password), GitHub (for Actions + Streamlit hosting)
- No API keys for the data feeds themselves (all no-key)

<a id="quick-start--local-sqlite-file"></a>

## Quick start — local (SQLite file)

**1. Install:**

```bash
pip install -r requirements.txt
```

**2. Configure env:**

```bash
cp .env.example .env
# Edit .env:
#   GMAIL_USER=you@gmail.com
#   GMAIL_APP_PASSWORD=<16-char app password>
#   ALERT_TO=you@gmail.com
#   TURSO_DATABASE_URL=file:events.db   (default, no Turso needed)
```

> Gmail App Password: Google Account → Security → 2-Step Verification → App passwords → create `Trip Risk Monitor`. Do **not** use your normal password.

**3. Run one tick:**

```bash
python -m monitor
```

This polls live feeds, writes `events.db`, scores legs, and emails on tier change. With no Gmail creds it still scores and stores alerts (email step warns and retries next tick).

**4. Check the dashboard:**

```bash
streamlit run dashboard.py
# http://localhost:8501
```

**5. Run tests:**

```bash
pytest -v
# 29 passed
```

**6. Edit trips** in `trips.csv` and re-run `python -m monitor`.

<a id="deploy-to-cloud--turso--actions--streamlit-0"></a>

## Deploy to cloud — Turso + Actions + Streamlit ($0)

### Step 1: Create Turso DB (free, 2 min)

1. Go to [turso.tech](https://turso.tech) → sign up → Create database.
2. Copy two values: **`TURSO_DATABASE_URL`** (starts `libsql://…`) and **`TURSO_AUTH_TOKEN`**.

### Step 2: Gmail App Password (free, 2 min)

Google Account → Security → 2-Step Verification (must be on) → App passwords → create one. You get a 16-char password — use it as `GMAIL_APP_PASSWORD`.

### Step 3: Push repo to GitHub

```bash
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin master
```

> The 30-min cron workflow is already in `.github/workflows/monitor.yml`.

### Step 4: Add GitHub secrets

Repo → Settings → Secrets and variables → Actions → New secret (add all 5):

| Secret | Value |
|---|---|
| `TURSO_DATABASE_URL` | from Step 1 |
| `TURSO_AUTH_TOKEN` | from Step 1 |
| `GMAIL_USER` | your Gmail address |
| `GMAIL_APP_PASSWORD` | 16-char app password |
| `ALERT_TO` | where alerts should land |

Then Actions → *monitor* → **Run workflow** to test once. After that it runs every 30 min automatically.

### Step 5: Deploy dashboard (Streamlit Cloud, free)

1. [share.streamlit.io](https://share.streamlit.io) → New app → pick repo → main file `dashboard.py`.
2. Add the same secret(s): `TURSO_DATABASE_URL` (+ `TURSO_AUTH_TOKEN`).
3. Deploy. Dashboard reads Turso only — no feed calls from the dashboard, so Streamlit sleeping is fine.

**Live URLs:** Actions run history shows each tick; Streamlit URL shows scores/alerts. Total cost: $0.

<a id="dashboard-guide"></a>

## Dashboard guide

`streamlit run dashboard.py` (or your Streamlit Cloud URL):

- **Top metrics:** legs scored, Act alert count, alert count.
- **Trip scores table:** per-leg tier/score/driver, worst leg highlighted next to trip score.
- **Risk bar chart:** per-leg score coloured by tier.
- **Map:** Plotly mapbox (OpenStreetMap) — legs coloured 🟢/🟡/🔴.
- **14-day outlook:** per-leg-day risk line (from stored forecast events) with Watch/Act thresholds.
- **Alert feed:** full plain-text alerts, filterable by tier and kind (ESCALATED / DE-ESCALATED / CLOSED).
- **Feed health table:** last OK + last error per feed (also shown as a warning banner).

<a id="configuration"></a>

## Configuration

| Env var | Required for | Default |
|---|---|---|
| `TURSO_DATABASE_URL` | DB (file or cloud) | `file:events.db` |
| `TURSO_AUTH_TOKEN` | Turso cloud only | — |
| `GMAIL_USER` | Email | — |
| `GMAIL_APP_PASSWORD` | Email | — |
| `ALERT_TO` | Email destination | — |

**`trips.csv` format** (`trip_id,country,city,lat,lon,start_date,end_date`) — one row = one leg:

```csv
trip_id,country,city,lat,lon,start_date,end_date
DELHI-01,India,Delhi,28.61,77.20,2026-12-10,2026-12-15
PARO-01,Bhutan,Paro,27.43,89.42,2026-12-21,2026-12-24
```

Rows with missing lat/lon or `end < start` are skipped with a `WARN` — the rest of the tick still runs.

<a id="tests"></a>

## Tests

```bash
pytest -v          # full suite (29 tests)
pytest tests/test_scorer.py -v    # single module
```

| File | Covers |
|---|---|
| `test_scorer` | noisy-OR math, tier thresholds, proximity |
| `test_feeds` | USGS severity + bbox filter, malformed XML → `[]` not crash |
| `test_fixes` | event round-trip (duration/confidence), cross-process dedup, email retry, per-item isolation, future trips, clustering, thresholds, out-of-scope, one-feed-raises |
| `test_db` | upsert/get round-trip, health upsert |
| `test_alerts` | severity + driver + source in text |
| `test_monitor` | bad CSV skipped, Act alert on cyclone, no duplicate, email failure persists |
| `test_scaffold`, `test_dashboard` | 5-country coverage, dashboard imports |

<a id="error-handling"></a>

## Error handling

- **Feed down/format change:** recorded in `feed_health`, dashboard banner, other feeds continue. Query-level failures mark the feed failed; per-item bad records are skipped without killing the batch; per-location weather failures skip that city only.
- **Bad `trips.csv` row:** skipped with warning, other legs scored.
- **Email failure:** alert row already persisted; tier not advanced, so next tick retries. Dashboard always has the text.
- **DB (Turso) failure:** `monitor` exits non-zero — Actions shows red — so outages are visible. Re-fetch is idempotent (`events.id` conflict-update), so a retry doesn't duplicate.
- **Leg in the past:** tier forced to Green, one `CLOSED` alert, excluded from scoring.

<a id="limitations--honest-notes"></a>

## Limitations & honest notes

- **Weights, radii, thresholds are starting guesses.** Only flood/cyclone severity was previously checked against real impact. Do not present scores as validated accuracy.
- **Open-Meteo free tier is non-commercial dev use** — check terms before any commercial/production use. Only rounded coordinates (2 decimals) are sent.
- **GDELT news is noisy** — clustering reduces but doesn't eliminate false alerts. GeoNames lookup (substring + `rapidfuzz`) can still miss unusual spellings.
- **The system never acts on its own** — it only alerts a human. It does not predict individual earthquakes and its outlook is a forecast, not certainty.
- **Single-user MVP:** no auth (unlisted dashboard URL), hand-edited CSV, no booking-system integration. Advisories, backtest tuning, and replay are deferred (Phase 3).

<a id="roadmap"></a>

## Roadmap

- **Done (this repo):** scoring + feeds (USGS/GDACS/weather/news) + Turso + Gmail + Actions cron + dashboard + map + outlook + cooldown/dedup + 29 tests.
- **Phase 2 polish:** hand-label 20 headlines to measure extraction accuracy; pin `requirements.txt` versions; read-only dashboard DB connection; per-leg-day outlook table export.
- **Phase 3 (not in MVP):** GOV.UK / US State advisories as baseline, backtest weight tuning, shared-link auth, commercial weather source decision, real itinerary integration.

Implemented from: `C:\Users\chara\.opencode\plan\2026-11-06-trip-risk-design.md` (spec) + `docs/superpowers/plans/2026-11-06-trip-risk-monitor.md` (plan), with a final review fix pass (DB-backed cooldown, event round-trip, email retry, feed hardening).

<a id="faq--troubleshooting"></a>

## FAQ / Troubleshooting

**`python -m monitor` scores nothing / dashboard empty.** Check `trips.csv` dates are in the future (`end >= today`). Ships with Dec 2026–Jan 2027 legs. Update them for your dates.

**Emails never arrive but dashboard shows alerts.** Gmail App Password wrong or 2-Step not on. Test `python -c "import os; from alerts import send_email; send_email('test','hi')"` with env set. Check spam folder; `ALERT_TO` must be a valid address.

**Dashboard says "Database unreachable".** Local: `TURSO_DATABASE_URL=file:events.db` (run `python -m monitor` once). Cloud: Streamlit secret `TURSO_DATABASE_URL` must be the full `libsql://…` URL + `TURSO_AUTH_TOKEN`.

**`import db` / `No module named 'monitor'` in tests.** Run tests from the `trip_risk` repo root so root modules are on `sys.path`.

**Feed shows error banner.** Open Feed health table — it names the feed and error. One bad record shouldn't blank the feed after the hardening fix; if a feed returns a completely new shape, parsers return `[]` or skip the item and health records it.

**Actions run is red.** Actions → run → logs. `TURSO_*` / `GMAIL_*` secrets missing or feed outage. Monitor exits non-zero only on DB failure; per-feed failures are yellow (warning) by design.

**Windows `UnicodeDecodeError` in tests.** Tests read files as UTF-8 explicitly; run `pytest` from repo root with Python ≥3.12.

<a id="licences--sources"></a>

## Licences & sources

- **GDACS:** https://gdacs.org — Global Disaster Events (historical CSVs + live RSS). Confirm exact licence link on the site before production.
- **USGS:** public-domain US government earthquake feed — https://earthquake.usgs.gov
- **Open-Meteo:** free non-commercial dev tier — https://open-meteo.com
- **GDELT DOC 2.1:** free news API — https://www.gdeltproject.org
- **ReliefWeb:** free humanitarian news API — https://reliefweb.int/api
- **GeoNames `data/cities15000.txt`:** believed CC BY 4.0 — confirm at https://geonames.org and add the exact link.
- **Turso / Streamlit / GitHub Actions / Gmail SMTP:** free tiers as described above; check terms for any commercial use.

---

*Built as a single-operator, free-tier monitor. Every alert goes to a human — the system watches, scores, and explains, it never decides.*
