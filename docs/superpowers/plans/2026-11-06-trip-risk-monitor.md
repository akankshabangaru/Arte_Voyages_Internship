# Trip Risk Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a clean, $0/month continuous trip-risk monitor (5 countries, Turso SQLite, Gmail alerts, Streamlit dashboard) that polls free feeds every 30 min and emails plain-text severities.

**Architecture:** Single-process `monitor.py` polls all free feeds → scores legs with noisy-OR → writes to Turso (SQLite) → emails via Gmail; `dashboard.py` reads Turso read-only. Local dev uses `file:events.db` with identical SQL.

**Tech Stack:** Python 3.12, libsql-client, sqlite3, requests, rapidfuzz, pandas, streamlit, plotly, pytest, GitHub Actions cron.

**Spec:** `C:\Users\chara\.opencode\plan\2026-11-06-trip-risk-design.md`

## Global Constraints

- Runtime is Python 3.12; install deps via `requirements.txt` only.
- Working directory `trip_risk` is not a git repo — run `git init` in Task 1 if `git status` fails.
- Total cost must stay $0/month: GitHub Actions 2,000 free min/mo, Turso 100 DBs/5 GB, Streamlit Community Cloud, Gmail ~500/day, USGS/GDACS/Open-Meteo (dev use)/GDELT/ReliefWeb no-key.
- Scope is the 5 countries only: India, Nepal, Bhutan, Sri Lanka, Maldives.
- Tiers are `Green < 0.15 | Watch 0.15–0.45 | Act ≥ 0.45`; trip tier is the worst leg tier.
- Scoring formula is `risk = severity × proximity × time_overlap × confidence` and `leg_score = 1 - Π(1 - risk_i)`.
- Radii (km): earthquake 300, cyclone 400, heatwave 300, drought 500, storm 200, flood 150, rain 100, eruption 100, wildfire 100, unrest 50, default 150; proximity is `0` beyond `3*radius` else `exp(-dist/radius)`.
- Severity mappings verbatim: USGS `min(1, (M-4.5)/4)`; GDACS Green 0.2/Orange 0.55/Red 0.9; Open-Meteo gusts ≥70/≥90 km/h → 0.55/0.9, rain ≥50/≥100 mm → 0.55/0.9, heat ≥40/≥42°C → 0.55/0.9; News `killed/evacuated/landfall/cyclone` 0.8, `warning/heavy rain/protest/outbreak` 0.55, else 0.35.
- Confidence: USGS 0.9, GDACS 0.9, weather 0.6, news 0.6 (0.84 if ≥2 articles agree).
- Tier rises immediately, falls only after 48h continuously below threshold; dedup key `(event_id, trip_id, leg_id)` re-emails only on escalation.
- Local DB is `file:events.db` via `TURSO_DATABASE_URL=file:events.db`; cloud is `libsql://…` — same SQL, no branch.
- GeoNames file `data/cities15000.txt` is used offline; never send traveller names to feeds, only rounded lat/lon (2 decimals) for weather.

## Review Focus

- Malformed `trips.csv` row (missing lat/lon, `end < start`) — expected: row skipped with warning, other legs still scored. Pinned in Task 6.
- Feed returns malformed JSON/XML or missing fields — expected: `feed_health` logged with error, other feeds continue that tick. Pinned in Task 3.
- Event outside the 5-country bounding boxes — expected: filtered out, never scored. Pinned in Task 3.
- Turso unreachable / DB write fails — expected: `monitor` exits non-zero for Actions visibility; re-fetch is idempotent via `events.id`. Pinned in Task 4.
- Email SMTP fails — expected: alert row still persisted in `alerts` table, retry next tick, error logged. Pinned in Tasks 5–6.

---

## File structure

Created at repo root (`trip_risk/`), leaving legacy `src/`, `app.py`, `live_app.py` untouched for V1:

- `scorer.py` — `Leg`/`Event` dataclasses + proximity/time-overlap/noisy-OR (`haversine_km`, `proximity`, `time_overlap`, `noisy_or`, `tier_of`, `leg_signals`, `leg_score_from_signals`). Ports math from `src/scoring.py`, drops advisories.
- `feeds.py` — pure parsers `parse_usgs`, `parse_gdacs`, `parse_openmeteo`, `parse_gdelt`, `parse_reliefweb`, `cluster_events`, `in_scope` + network wrappers `usgs_feed`, `gdacs_feed`, `news_feed`, `weather_feed`.
- `db.py` — Turso/sqlite helper: `init_db`, `upsert_event`, `get_events`, `update_score`, `log_alert`, `get_alerts`, `upsert_health`, `get_health`.
- `alerts.py` — `render_alert`, `send_email`, `notify`.
- `monitor.py` — `load_trips`, `poll_once`, `main`; `python -m monitor` entry point.
- `dashboard.py` — Streamlit app (tables, map, outlook, feed health).
- `trips.csv`, `requirements.txt`, `.env.example`, `.github/workflows/monitor.yml`, `README.md`.
- Tests: `tests/test_scorer.py`, `tests/test_feeds.py`, `tests/test_db.py`, `tests/test_alerts.py`, `tests/test_monitor.py` (new files; namespaced so legacy `test_scoring.py`/`test_live.py` still run).

---

### Task 1: Scaffolding, trips.csv, deps

**Files:**
- Create: `trips.csv`
- Create: `requirements.txt` (overwrite)
- Create: `.env.example`
- Create: `.github/workflows/monitor.yml`

**Interfaces:**
- Consumes: none.
- Produces: `trips.csv` columns `trip_id,country,city,lat,lon,start_date,end_date`; `requirements.txt` with pinned deps; workflow runs `python -m monitor` every `*/30 * * * *`; `.env.example` keys `TURSO_DATABASE_URL`, `TURSO_AUTH_TOKEN`, `GMAIL_USER`, `GMAIL_APP_PASSWORD`, `ALERT_TO`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_scaffold.py
import csv, pathlib
def test_trips_csv_has_all_five_countries():
    rows = list(csv.DictReader(open("trips.csv")))
    assert {r["country"] for r in rows} == {"India", "Nepal", "Bhutan", "Sri Lanka", "Maldives"}
    assert all(r["trip_id"] and r["lat"] and r["lon"] and r["start_date"] < r["end_date"] for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scaffold.py -v`
Expected: FAIL — `FileNotFoundError: trips.csv`

- [ ] **Step 3: Create `trips.csv` with 8–10 legs covering all 5 countries**

Use header above plus rows for Delhi, Kathmandu, Paro, Colombo, Male (as in spec) plus Jaipur, Kandy, Udaipur for coverage. Dates are future relative to test run so legs are active.

- [ ] **Step 4: Create `requirements.txt`, `.env.example`, workflow**

`requirements.txt`: `pandas`, `numpy`, `streamlit`, `plotly`, `pytest`, `rapidfuzz`, `requests`, `libsql-client`, `python-dotenv`, `folium`. `.env.example` lists the 5 secrets above with `TURSO_DATABASE_URL=file:events.db`. Workflow YAML per spec (checkout, setup-python 3.12, pip install, `python -m monitor` with secrets).

- [ ] **Step 5: Run test to verify it passes**

Run: `pytest tests/test_scaffold.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git init 2>$null; git add trips.csv requirements.txt .env.example .github/workflows/monitor.yml tests/test_scaffold.py
git commit -m "feat: scaffold trips.csv, deps, Actions cron"
```

---

### Task 2: scorer.py (TDD)

**Files:**
- Create: `scorer.py`
- Test: `tests/test_scorer.py`

**Interfaces:**
- Consumes: none.
- Produces: `Leg`, `Event` dataclasses; `RADIUS_KM`, `WATCH=0.15`, `ACT=0.45`, `TIERS`, `MIN_DURATION`; `haversine_km(lat1,lon1,lat2,lon2)->float`, `proximity(event,leg)->float`, `time_overlap(event,leg)->float`, `noisy_or(values)->float`, `tier_of(score)->str`, `leg_signals(leg,events,as_of:date)->list[dict{"kind","title","url","risk"}]`, `leg_score_from_signals(sigs)->float`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_scorer.py -v`
Expected: FAIL — `ModuleNotFoundError: scorer`

- [ ] **Step 3: Implement `scorer.py`**

Port `haversine_km`, `proximity`, `time_overlap`, `noisy_or`, `tier_of` from `src/scoring.py` verbatim including `RADIUS_KM` and `MIN_DURATION = {"earthquake":7,"eruption":14,"cyclone":3,"flood":3}`; add `@dataclass` `Leg`/`Event` with fields above; `leg_signals` skips events with `(issued or date) > as_of` and returns only `r > 0`; `leg_score_from_signals` is `noisy_or`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_scorer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scorer.py tests/test_scorer.py
git commit -m "feat: scorer with noisy-OR and tiers"
```

---

### Task 3: feeds.py (TDD)

**Files:**
- Create: `feeds.py`
- Test: `tests/test_feeds.py`

**Interfaces:**
- Consumes: `Event` from `scorer.py`.
- Produces: `COUNTRY_BBOX: dict[str,tuple[float,float,float,float]]` (lat_min,lat_max,lon_min,lon_max), `in_scope(lat,lon)->str|None`, parsers `parse_usgs(data:dict,min_mag=5.0)`, `parse_gdacs(xml_text:str)`, `parse_openmeteo(data:dict,lat,lon,place,today:date)`, `parse_gdelt(data:dict)`, `parse_reliefweb(data:dict)`, `cluster_events(events)->list[Event]`, network wrappers `usgs_feed(now)`, `gdacs_feed(now)`, `news_feed(now)`, `weather_feed(legs)->callable`.

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_feeds.py -v`
Expected: FAIL — `ModuleNotFoundError: feeds`

- [ ] **Step 3: Implement `feeds.py`**

Port parsers from `src/feeds.py` (USGS, GDACS, Open-Meteo with thresholds above); define `COUNTRY_BBOX` for the 5 countries per spec and `in_scope` to return country or `None`; apply `in_scope` filtering inside each `parse_*` and `_feed` (drop out-of-scope); implement `parse_gdelt` (GDELT DOC `ArtList`: extract title/date/url, lat/lon if present else `None`→skip) and `parse_reliefweb` (`data` list: title/date/url) with news severity mapping above; implement `cluster_events` (same type + haversine ≤150 km + date diff ≤3 days → keep max severity, merge URLs). Wrappers use `requests` timeout 20s, `User-Agent: trip-risk-monitor/1.0`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_feeds.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add feeds.py tests/test_feeds.py
git commit -m "feat: free feeds with geo filter and clustering"
```

---

### Task 4: db.py Turso/SQLite (TDD)

**Files:**
- Create: `db.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `Event` from `scorer.py`.
- Produces: `init_db()`, `upsert_event(ev:Event, first_seen:datetime)`, `get_events()->list[Event]`, `update_score(trip_id,leg_id,place,country,lat,lon,start,end,score,tier,driver,updated_at)`, `log_alert(d:dict{trip_id,leg_id,kind,tier,prev_tier,text,created_at})`, `get_alerts(limit=50)->list[dict]`, `upsert_health(feed:str,ok:bool,error:str)`, `get_health()->list[dict]`. Local: `sqlite3` when URL is `file:`; cloud: `libsql-client` when `libsql://`.

- [ ] **Step 1: Write the failing test**

```python
import os, datetime
os.environ["TURSO_DATABASE_URL"] = "file::memory:"
def test_upsert_get_roundtrip():
    import db; db.init_db()
    from scorer import Event
    from datetime import date, datetime, timezone
    ev = Event("e1", date(2026,1,1), None, "Nepal", "earthquake", 0.5, 27.7, 85.3, 7, 0.9, "t", "u", "usgs")
    db.upsert_event(ev, datetime.now(timezone.utc))
    assert db.get_events()[0].event_id == "e1"
    db.upsert_health("usgs", True, "")
    assert db.get_health()[0]["feed"] == "usgs"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: db`

- [ ] **Step 3: Implement `db.py`**

`_url()` reads `TURSO_DATABASE_URL` default `file:events.db`; `_connect()` returns `sqlite3.connect(":memory:" or path)` for `file:` and `libsql_client.client(url, token)` otherwise; `init_db()` executes the spec schema (`events`, `trip_scores`, `alerts`, `feed_health` + indexes) with `CREATE TABLE IF NOT EXISTS`; each function uses `?` placeholders and commits. `get_events` maps rows back to `Event`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_db.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add db.py tests/test_db.py
git commit -m "feat: Turso/sqlite storage layer"
```

---

### Task 5: alerts.py text + Email (TDD)

**Files:**
- Create: `alerts.py`
- Test: `tests/test_alerts.py`

**Interfaces:**
- Consumes: `Leg` from `scorer.py`.
- Produces: `EMOJI={"Green":"🟢","Watch":"🟡","Act":"🔴"}`, `render_alert(trip_id:str, leg:Leg, tier:str, prev_tier:str, score:float, sigs:list[dict], monitored_at:datetime)->str`, `send_email(subject:str, body:str)->None`, `notify(alert:dict)->None` (formats subject, calls `send_email`).

- [ ] **Step 1: Write the failing test**

```python
def test_render_contains_severity_and_source(monkeypatch):
    from datetime import date, datetime, timezone
    from scorer import Leg; from alerts import render_alert
    leg = Leg("l1","PARO-01","Paro","Bhutan",27.43,89.42,date(2026,8,21),date(2026,8,24))
    txt = render_alert("PARO-01", leg, "Act", "Watch", 0.72,
        [{"kind":"cyclone","title":"Cyclone 90 km/h","url":"https://gdacs.org/x","risk":0.72}],
        datetime(2026,8,21,10,30,tzinfo=timezone.utc))
    assert "🔴 ACT" in txt and "Severity" in txt and "https://gdacs.org/x" in txt
    assert "Paro" in txt and "0.72" in txt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_alerts.py -v`
Expected: FAIL — `ModuleNotFoundError: alerts`

- [ ] **Step 3: Implement `alerts.py`**

`render_alert` builds the spec template (emoji + tier + title, trip line, driver line with top-risk signal, source line, `Monitored: %d %b %Y %H:%M UTC`, action line: Act → "Review now, consider buffer day / reroute, contact partners.", Watch → "Monitor closely.", Green/De-escalated → "Monitor closely." / "No action."). `send_email` uses `smtplib` + `EmailMessage` to `smtp.gmail.com:587` with `GMAIL_USER`/`GMAIL_APP_PASSWORD`/`ALERT_TO` env; raises `RuntimeError` if env missing. `notify` formats subject `[TIER] place (country) — title — Severity X` and calls `send_email`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_alerts.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add alerts.py tests/test_alerts.py
git commit -m "feat: severity text alerts + gmail sender"
```

---

### Task 6: monitor.py + Actions wiring (TDD)

**Files:**
- Create: `monitor.py`
- Test: `tests/test_monitor.py`

**Interfaces:**
- Consumes: `load_trips` output `list[Leg]`; `feeds` wrappers; `scorer` functions; `db` functions; `alerts.render_alert/notify`.
- Produces: `load_trips(path="trips.csv")->list[Leg]` (skips bad rows with warning); `fetch_all(now:datetime, legs:list[Leg])->list[Event]` (internally calls each wrapper with try/except per feed); `poll_once(now:datetime, feeds:dict=None, notifier=None)->list[dict]` returns alerts inserted; `main()->None`; `COOLDOWN=datetime.timedelta(hours=48)`.

- [ ] **Step 1: Write the failing test**

```python
import os; os.environ["TURSO_DATABASE_URL"] = "file::memory:"
def test_poll_once_creates_alert_and_skips_bad_csv(tmp_path, monkeypatch):
    import db; db.init_db()
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
    alerts = monitor.poll_once(datetime(2026,8,11,10,0,tzinfo=timezone.utc), notifier=lambda a: sent.append(a))
    assert len(sent) == 1 and sent[0]["tier"] == "Act" and "🔴" in sent[0]["text"]
    # second tick same tier → no duplicate email
    alerts2 = monitor.poll_once(datetime(2026,8,11,10,30,tzinfo=timezone.utc), notifier=lambda a: sent.append(a))
    assert len(sent) == 1
def test_email_failure_still_persists(monkeypatch):
    import db
    import monitor
    from scorer import Event
    from datetime import date, datetime, timezone
    fake = [Event("e2", date(2026,8,11), None, "Bhutan", "cyclone", 0.9, 27.43, 89.42, 3, 0.9, "Cyclone", "https://gdacs.org/x", "gdacs")]
    monkeypatch.setattr(monitor, "fetch_all", lambda now, l: fake)
    def boom(a): raise RuntimeError("SMTP down")
    alerts = monitor.poll_once(datetime(2026,8,12,10,0,tzinfo=timezone.utc), notifier=boom)
    assert len(alerts) == 1 and len(db.get_alerts()) >= 1  # persisted despite email failure
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_monitor.py -v`
Expected: FAIL — `ModuleNotFoundError: monitor`

- [ ] **Step 3: Implement `monitor.py`**

`load_trips` parses CSV, skips rows with missing lat/lon or `end < start` (prints warning). `fetch_all(now, legs)` calls `usgs_feed`, `gdacs_feed`, `weather_feed(legs)`, `news_feed` independently with try/except per feed (logs to `feed_health` on error, continues). `poll_once` upserts clustered events, loads last tiers from `trip_scores`, scores each active leg via `leg_signals`+`leg_score_from_signals`+`tier_of` with 48h downgrade cooldown, updates scores, and for tier changes builds `render_alert` text, `db.log_alert`, and `notify` inside try/except (SMTP failure does not rollback DB). `main()` calls `init_db()` then `poll_once(datetime.now(timezone.utc))`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_monitor.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add monitor.py tests/test_monitor.py
git commit -m "feat: continuous monitor loop"
```

---

### Task 7: dashboard.py + README

**Files:**
- Create: `dashboard.py`
- Create: `README.md`

**Interfaces:**
- Consumes: `db.get_alerts`, `db.get_health`, `db` score table query (`SELECT * FROM trip_scores ORDER BY score DESC`).
- Produces: Streamlit app (`streamlit run dashboard.py`): trip table (tier/score/dates), Plotly/Folium map of legs+recent events, alert feed filterable by tier/kind/country, 14-day outlook chart, feed-health banner. No feed calls from dashboard.

- [ ] **Step 1: Write the failing test**

```python
import pathlib
def test_dashboard_imports_without_network():
    assert pathlib.Path("dashboard.py").exists()
    assert "streamlit" in pathlib.Path("dashboard.py").read_text()
    assert "get_alerts" in pathlib.Path("dashboard.py").read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py -v`
Expected: FAIL — `FileNotFoundError: dashboard.py` (write this as `tests/test_dashboard.py` in Task 1 style; keep it network-free)

- [ ] **Step 3: Implement `dashboard.py` + `README.md`**

Dashboard pages per spec; README covers Turso setup, Gmail App Password, GitHub secrets (the 5 keys), `trips.csv` editing, local `python -m monitor` + `streamlit run dashboard.py`, licence links for GDACS/GeoNames/Natural Earth, and honest-limits section (guessed weights, Open-Meteo dev-use only, no earthquake prediction).

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py -v && pytest -q`
Expected: PASS (full suite green, legacy `test_scoring.py`/`test_live.py` untouched)

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard.py README.md
git commit -m "feat: dashboard and deploy docs"
```

