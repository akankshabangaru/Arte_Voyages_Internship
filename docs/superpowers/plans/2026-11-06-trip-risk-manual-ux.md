# Trip Risk Live + Manual Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe Live | Manual toggle to `dashboard.py` where Manual lets users set hazard values + Watch/Act thresholds and instantly see Tier × Change grouped alerts and the full scoring walkthrough.

**Architecture:** Keep Live exactly as today (DB-driven KPI → scores → map → outlook → alerts → health). Manual is a pure in-memory branch inside `dashboard.py` that reuses `scorer.py` math (`proximity` / `time_overlap` / `noisy_or` / `tier_of`) via one new helper `simulate_manual`; it never writes to DB or sends email.

**Tech Stack:** Python 3.12, Streamlit, Plotly, pandas, pytest

**Spec:** `docs/superpowers/specs/2026-11-06-trip-risk-manual-ux-design.md`

## Global Constraints

- Harbor + Brass tokens only (see `dashboard.py:21-30`); no hard-coded hex outside tokens
- Tier labels always emoji + text (`🟢 Green`, `🟡 Watch`, `🔴 Act`), never colour-alone
- Sliders: severity 0–1, distance 0–1000 km, Watch 0.05–0.45, Act 0.15–0.90, Act auto-clamps above Watch
- Manual never imports `monitor`, never calls `db.upsert_*` / `db.log_alert` / `db.update_score` / `alerts.send_email`; only read of prev tier via existing `_load()`
- `monitor.py`, `db.py`, `alerts.py`, `feeds.py`, `trips.csv` untouched
- Floating point: `score` in 0–1, thresholds inclusive (`>=` mirrors current `tier_of` at `scorer.py:71-72`)

## Review Focus

- **Act dragged below Watch (inverted range):** Expect Act to clamp above Watch and tier to stay valid — covered by `test_threshold_clamp_prevents_inversion` in Task 1.
- **Event date outside leg window:** Expect `time_overlap == 0` → `risk == 0` → Green + inline hint, not a crash — covered by `test_event_outside_window_stays_green` in Task 1.
- **Distance beyond 3×radius (e.g., flood r=150km, distance 900km):** Expect proximity 0 → Green — covered by `test_proximity_cutoff` in Task 1.
- **DB empty / unreachable while in Manual:** Expect fallback legs from `trips.csv` (read-only parse in dashboard, no `monitor` import) still allow simulation — covered by `test_fallback_legs_parse_without_monitor` in Task 3.
- **Zero severity with high distance:** Expect score 0.0 and `UNCHANGED` kind — covered by `test_zero_severity_unchanged` in Task 1.

---

## File Structure

- `scorer.py` — add `tier_of(..., watch, act)` param and `simulate_manual(...)` helper. Single responsibility: pure scoring math, no Streamlit/DB.
- `dashboard.py` — add toggle, sidebar editors, summary helper, grouped-card renderer, fallback loader. Single responsibility: presentation only. Live path calls `_load()` (`dashboard.py:83-91`) unchanged; Manual path calls `simulate_manual` and never writes.
- `tests/test_dashboard_manual.py` — new. Single responsibility: unit tests for `simulate_manual`, tier clamping, grouping order, and guard checks that the simulator performs no DB/email writes.

---

### Task 1: Custom tiers + `simulate_manual` helper

**Files:**
- Modify: `scorer.py:71-72` (`tier_of` signature), add function after `scorer.py:86-87`
- Create: `tests/test_dashboard_manual.py`

**Interfaces:**
- Consumes: `Leg`, `Event`, `RADIUS_KM` (`scorer.py:7-8`), `noisy_or` (`scorer.py:64-68`), `time_overlap` (`scorer.py:55-61`), `TIERS` (`scorer.py:11`)
- Produces: `tier_of(score: float, watch: float = 0.15, act: float = 0.45) -> str` and `simulate_manual(leg: Leg, hazard_type: str, severity: float, distance_km: float, event_date: date, duration_days: int, confidence: float, watch: float, act: float, prev_tier: str) -> dict` with keys `score: float`, `tier: str`, `prev_tier: str`, `kind: str` (one of `ESCALATED`/`DE-ESCALATED`/`CLOSED`/`UNCHANGED`), `driver: str`, `proximity: float`, `time_overlap: float`, `risk: float`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_dashboard_manual.py
import math
from datetime import date
from scorer import Leg, simulate_manual, tier_of

def _leg():
    return Leg(leg_id="PARO-01", trip_id="PARO-01", place="Paro", country="Bhutan",
               lat=27.43, lon=89.42, start=date(2026, 8, 10), end=date(2026, 8, 12))

def test_tier_custom_thresholds():
    assert tier_of(0.10, watch=0.05, act=0.80) == "Watch"
    assert tier_of(0.90, watch=0.05, act=0.80) == "Act"
    assert tier_of(0.04, watch=0.05, act=0.80) == "Green"

def test_threshold_clamp_prevents_inversion():
    # helper-level: simulate with inverted watch/act must still rank Act > Watch
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 8, 10), 3, 0.9,
                        watch=0.40, act=0.20, prev_tier="Green")
    assert r["tier"] in ("Green", "Watch", "Act")
    assert r["score"] >= 0.0

def test_manual_escalation_green_to_act():
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 8, 10), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["tier"] == "Act"
    assert r["kind"] == "ESCALATED"
    assert r["score"] > 0.45

def test_event_outside_window_stays_green():
    r = simulate_manual(_leg(), "cyclone", 0.9, 0, date(2026, 9, 1), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["tier"] == "Green"
    assert r["time_overlap"] == 0.0

def test_proximity_cutoff():
    # flood radius 150km -> 3x = 450km ; 900km is beyond
    r = simulate_manual(_leg(), "flood", 0.9, 900, date(2026, 8, 10), 3, 0.9,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["proximity"] == 0.0
    assert r["tier"] == "Green"

def test_zero_severity_unchanged():
    r = simulate_manual(_leg(), "rain", 0.0, 0, date(2026, 8, 10), 1, 0.6,
                        watch=0.15, act=0.45, prev_tier="Green")
    assert r["score"] == 0.0
    assert r["kind"] == "UNCHANGED"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_manual.py -v`
Expected: FAIL with `ImportError` / `TypeError` (no `simulate_manual` yet, `tier_of` takes one arg)

- [ ] **Step 3: Implement `tier_of(..., watch, act)` and `simulate_manual(...)` in `scorer.py`**

Update `tier_of` to accept `watch`/`act` defaults `0.15`/`0.45` and compare with those values. Add `simulate_manual` that: (a) clamps severity 0–1 and distance 0–1000, (b) computes `RADIUS_KM.get(hazard_type, RADIUS_KM["default"])` and `proximity = 0.0 if distance_km > 3*r else math.exp(-distance_km / r)`, (c) builds a throwaway `Event`+`time_overlap` with the leg/dates given, (d) `risk = severity * proximity * time_overlap * confidence`, `score = noisy_or([risk])`, `tier = tier_of(score, watch, act)`, (e) derives `kind` from rank comparison of `tier` vs `prev_tier` using `TIERS.index`, with `CLOSED` only when `leg.end < event_date`, else `UNCHANGED` when equal, (f) sets `driver = f"{hazard_type} (severity {severity:.2f})"`. Clamp inverted thresholds so valid `act > watch` always holds (if `act <= watch`, set `act = watch + 0.01` capped at 0.90).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_manual.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Commit**

```bash
git add scorer.py tests/test_dashboard_manual.py
git commit -m "feat: scorer custom tiers + simulate_manual"
```

---

### Task 2: Sidebar editors, toggle, and summary strip

**Files:**
- Modify: `dashboard.py:94-100` (`main()` start + toggle), `dashboard.py:32-34` (reuse `ICON`/`COLORS`), add `_summary_text()` helper near `dashboard.py:82`
- Modify: `tests/test_dashboard_manual.py` (extend)

**Interfaces:**
- Consumes: `simulate_manual` from Task 1; existing `_load()` (`dashboard.py:83-91`), `TOKENS`/`COLORS`/`ICON` (`dashboard.py:21-34`); prev tier read from `scores` rows (`db.get_scores()` dicts)
- Produces: `_summary_text(scores: list[dict], alerts: list[dict]) -> str`, and `main()` with `st.segmented_control`/`st.radio` labelled `● Live | ✎ Manual` plus sidebar widgets labelled `Pick trip`, `Hazard type`, `Severity`, `Distance (km)`, `Watch threshold`, `Act threshold`

- [ ] **Step 1: Write the failing dashboard structure test**

```python
# append to tests/test_dashboard_manual.py
import pathlib
def test_dashboard_has_manual_toggle_and_editors():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert "Manual" in text and "Live" in text
    assert "Watch threshold" in text
    assert "Act threshold" in text
    assert "Simulation only" in text

def test_no_db_write_in_manual_path():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    # manual block must not call write APIs
    assert "simulate_manual" in text
    assert text.count("log_alert") == 0 or "Manual" in text.split("log_alert")[0][-2000:]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_manual.py::test_dashboard_has_manual_toggle_and_editors -v`
Expected: FAIL (`Watch threshold` not present)

- [ ] **Step 3: Add `_summary_text` + toggle + sidebar editors in `dashboard.py`**

In `main()`, right after `st.caption(...)` (`dashboard.py:98`), add `mode = st.segmented_control("Mode", ["● Live", "✎ Manual"], default="● Live")` (fallback to `st.radio` if segmented control unavailable in installed Streamlit version). Render `_summary_text(scores, alerts)` as `st.info`. In the sidebar, when mode is Manual, add `st.selectbox("Pick trip", ...)`, `st.selectbox("Hazard type", [...])`, `st.slider("Severity", 0.0, 1.0, 0.5)`, `st.slider("Distance (km)", 0, 1000, 50)`, `st.date_input`, `st.number_input` for duration, and `st.slider("Watch threshold", 0.05, 0.45, 0.15)` + `st.slider("Act threshold", 0.15, 0.90, 0.45)`. Show `st.caption("Simulation only — what-if; no DB write, no email.")`. When Live, keep today's body unchanged.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_manual.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard_manual.py
git commit -m "feat: dashboard Live/Manual toggle + sidebar editors + summary"
```

---

### Task 3: Tier × Change grouped cards + How-it-works + fallback legs

**Files:**
- Modify: `dashboard.py:115-194` (scores/map/outlook/alert sections get a Manual branch), add `_group_alerts()` and `_render_manual_result()` helpers near `_summary_text`
- Modify: `tests/test_dashboard_manual.py` (extend)

**Interfaces:**
- Consumes: Tasks 1–2 outputs; `Leg` dataclass; `trips.csv` columns `trip_id,country,city,lat,lon,start_date,end_date`
- Produces: `_group_alerts(alert_dicts: list[dict]) -> list[list[dict]]` ordered `[Act+Escalated, Watch+Escalated, De-escalated, Closed/Unchanged]`, `_render_manual_result(sim: dict, thresholds: dict) -> None` (renders chips, score bar via `st.progress` or Plotly bar with threshold lines, and action line), `_load_legs_fallback(path: str = "trips.csv") -> list[Leg]` (direct `csv` parse, no `monitor` import)

- [ ] **Step 1: Write the failing grouping + fallback tests**

```python
# append to tests/test_dashboard_manual.py
from dashboard import _group_alerts, _load_legs_fallback

def test_grouping_order_tier_times_change():
    arr = [
        {"tier": "Green", "kind": "DE-ESCALATED", "score": 0.0},
        {"tier": "Act", "kind": "ESCALATED", "score": 0.80},
        {"tier": "Watch", "kind": "ESCALATED", "score": 0.30},
        {"tier": "Green", "kind": "UNCHANGED", "score": 0.0},
    ]
    groups = _group_alerts(arr)
    assert groups[0][0]["tier"] == "Act"
    assert groups[1][0]["tier"] == "Watch"

def test_fallback_legs_parse_without_monitor():
    legs = _load_legs_fallback("trips.csv")
    assert len(legs) >= 1
    assert hasattr(legs[0], "trip_id")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard_manual.py::test_grouping_order_tier_times_change -v`
Expected: FAIL (`ImportError: cannot import name '_group_alerts'`)

- [ ] **Step 3: Implement `_group_alerts`, `_render_manual_result`, `_load_legs_fallback` in `dashboard.py`**

`_group_alerts` buckets by `(tier, kind)` in the spec order. `_render_manual_result` renders one card per alert: emoji+text tier chip, change chip (`↑ Escalated` etc.), driver line, `st.progress(score)` with caption showing `Watch x.xx | Act y.yy`, and the action map line (`Act → Review now...`, `Watch → Monitor closely.`, `Green → No action.`). Inline hint when `time_overlap == 0` (`"Event is outside this leg's dates — score stays Green."`). `_load_legs_fallback` parses `trips.csv` with `csv.DictReader` into `Leg` objects (same column mapping as `monitor.load_trips` but no import of `monitor`). Add a `st.expander("How it works")` in Manual that prints the four steps with the current sim's `proximity`, `time_overlap`, `risk`, `score`, and chosen thresholds substituted.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard_manual.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard_manual.py
git commit -m "feat: manual Tier x Change grouped cards + how-it-works"
```

---

### Task 4: Full regression and manual smoke

**Files:**
- Test: all `tests/`

**Interfaces:**
- Consumes: Tasks 1–3 deliverables
- Produces: green suite, no product-code changes

- [ ] **Step 1: Run the full suite**

Run: `pytest -q` (from repo root)
Expected: PASS (existing 29 + 10 new = 39 tests)

- [ ] **Step 2: Smoke the dashboard**

Run: `streamlit run dashboard.py`
Expected: toggle appears; dragging Severity 0→1 moves the Manual card Green → Watch → Act with matching action line; Live sections match yesterday

- [ ] **Step 3: Commit (only if a fix was needed)**

```bash
git add -A
git commit -m "fix: manual UX regression pass"
```
