# Trip Risk UX — Live + Manual Modes (Design Spec)

**Date:** 2026-11-06
**Status:** Approved (Sections 1–3 approved in chat)
**Home app:** `dashboard.py` (extend, do not fork)
**Mode:** Safe in-memory simulation for Manual; Live unchanged

## 1. Intent and constraints

**Purpose:** Make trip-risk data graspable in a jiffy and let a user see how alerts are categorized, displayed, and produced by manually supplying hazard values — without risking live DB writes or email spam.

**What the requester said:** Improve UX for easy handling and fast comprehension; add two options — 1) live feed view, 2) manual data with values that trigger alerts — and in Manual, show how alerts are categorized, displayed, and how the whole working functions.

**Agreed decisions (from brainstorming questions):**
- Manual inputs = hazard-per-trip (type + severity + distance + date/duration) **plus** Watch/Act threshold sliders.
- Alert sorting = **Tier × Change together** (Green/Watch/Act plus Escalated / De-escalated / Closed / Unchanged, always legible together).
- Home = **extend `dashboard.py`** with a top toggle; `live_app.py` / `app.py` remain legacy and untouched.
- Manual = **simulation only** (no DB writes, no email).

**Success criteria:**
- A first-time user can explain within 30 seconds why a given trip is Act vs Watch by reading the summary strip and one alert card.
- Moving a severity slider or threshold instantly moves the tier and alert kind without a reload.
- All existing 29 tests plus new manual tests pass; `monitor.py`, `db.py`, `alerts.py`, `feeds.py` untouched.

## 2. UX layout (Section 1 — approved)

Single Streamlit page (`dashboard.py`, Harbor + Brass tokens retained) with a segmented toggle at the top:

- `● Live | ✎ Manual`
- **Live mode (default):** Exactly today's sections — KPI row → trip scores table + bar chart → map → 14-day outlook → alert feed → feed health — plus a new plain-language summary strip rendered in **both** modes (e.g., "8 legs scored · 1 needs review (Act) · 2 on watch").
- **Manual mode:** Same page skeleton, but:
  - Sidebar editor groups: (1) Pick trip/leg (selectbox from current scored legs), (2) Hazard inputs (type selectbox: earthquake, flood, cyclone, heatwave, unrest, eruption, wildfire, drought, storm, rain, default; severity slider 0–1; distance slider 0–1000 km; event date + duration days), (3) Threshold sliders — Watch 0.05–0.45, Act 0.15–0.90, with Act auto-clamped to be > Watch.
  - Persistent `Simulation only — what-if` banner so the safest path is obvious.
  - Main pane instantly shows recalculated leg score/tier, map highlight for the chosen leg, grouped alert cards, and a "How it works" expander.

Accessibility: emoji + text tier labels (never colour-alone), focus-visible outlines, ≥44 px targets, reduced-motion rule, and 320 px reflow retained from the existing design system.

## 3. Components and data flow (Section 2 — approved)

### 3.1 New simulator (reuses `scorer.py`)

New helper in `scorer.py` (~40 lines, unit-tested):

`simulate_manual(leg, hazard_type, severity, distance_km, event_date, thresholds) -> {score, tier, prev_tier, kind, driver_text}`

Flow:
1. `prev_tier` = current Live tier for that leg from DB (`db.get_score_row` / scored legs) or `Green` if absent.
2. `proximity` = `exp(-distance_km / RADIUS_KM[hazard_type])` (same formula as `scorer.proximity`, with the same 3×radius cutoff).
3. `risk = severity × proximity × time_overlap × confidence` (confidence defaults to the table value for that hazard source, e.g., 0.9 for disasters, 0.6 for weather/news).
4. `score = noisy_or([risk])`, `tier = tier_of(score, watch=thresholds.watch, act=thresholds.act)` using the **user-supplied** Watch/Act thresholds instead of the constants `WATCH=0.15` / `ACT=0.45`.
5. `kind`: `ESCALATED` if new tier rank > prev, `DE-ESCALATED` if <, `CLOSED` only if leg end < event date handling says leg finished, else `UNCHANGED`. The alert text reuses the same action-line map as `alerts.render_alert` ("Review now, consider buffer day / reroute, contact partners." / "Monitor closely." / "No action.").

Manual **never imports** `monitor`, `db` write paths, or `alerts.send_email`. Read of prev tier is the only DB access (via existing `_load()` in `dashboard.py`).

### 3.2 Alert display — Tier × Change grouped cards

Cards are grouped in this order inside Manual:
1. Act + Escalated
2. Watch + Escalated
3. De-escalated (→ Green or Watch)
4. Closed / Unchanged

Every card contains, in one glance:
- Tier chip: emoji + word (`🔴 Act`, `🟡 Watch`, `🟢 Green`) plus change chip (`↑ Escalated`, `↓ De-escalated`, `— Unchanged`, `✓ Closed`).
- Driver line: hazard type + title + severity (`cyclone Cyclone 90 km/h — Severity 0.72`).
- Score bar 0–1 with Watch/Act threshold lines and the numeric score.
- Action line identical to email wording, plus the source link if present.
- "Was Watch → now Act" line (`Leg risk: 0.72 → Act (was Watch)`).

A "How it works" expander below walks through, using the user's own numbers: proximity × time-overlap × severity → noisy-OR → tier → alert kind. No hidden steps.

### 3.3 Files touched

- `dashboard.py` — toggle, sidebar editors, summary strip, grouped cards, expander, simulation-only banner.
- `scorer.py` — ~40 lines for `simulate_manual` plus a `watch`/`act` parameter on `tier_of`.
- `tests/test_dashboard_manual.py` — new.
- `monitor.py`, `db.py`, `alerts.py`, `feeds.py`, `trips.csv` — **untouched**.

## 4. Error handling and bounds (Section 3 — approved)

- Sliders clamped: severity 0–1, distance 0–1000 km, Watch 0.05–0.45, Act 0.15–0.90; Act auto-clamps above Watch (if user drags Act below Watch, Watch snaps down — never an inverted range).
- Zero distance / missing dates / leg outside window: inline hint (`"Event is outside this leg's dates — score stays Green."`), never a crash; no empty Plotly frames (show `st.info` fallback like existing branches).
- Deterministic and instant: no network calls in Manual; map/timeline re-render from in-memory rows only.
- Live degradation preserved: DB unreachable still shows `st.error` banner and empty states; Manual remains available because it only needs the leg list (fallback: legs parsed directly from `trips.csv` in `dashboard.py` — read-only, no `monitor` import).

## 5. Testing

- **New unit tests** (`tests/test_dashboard_manual.py`):
  - Green → Watch → Act transitions as severity crosses the user thresholds.
  - Threshold reorder clamp (Act below Watch snaps; no tier inversion).
  - Tier × Change grouping order (Act+Escalated first).
  - No-DB-write guard: calling the simulator does not call `db.upsert_*` / `db.log_alert` / `send_email` (mock assert).
  - Proximity matches `scorer.proximity` for known distance/radius pairs.
- **Regression:** existing 29 tests must keep passing (`pytest -q` from repo root). Dashboard import test (`test_dashboard`) continues to pass.
- **Manual smoke:** `streamlit run dashboard.py`, toggle to Manual, drag severity 0→1, observe card move Green → Watch → Act with matching action line.

## 6. Non-goals

- No persistence of Manual inputs (session only); no DB schema change; no email/webhook; no multi-page wizard; no custom JS map editors; no change to the 30-minute `monitor` loop or scoring constants used by Live.
