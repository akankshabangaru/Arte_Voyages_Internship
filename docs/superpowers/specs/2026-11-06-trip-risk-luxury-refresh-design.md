# Trip Risk Dashboard — Arte Voyages Light Luxury Refresh (Design Spec)

**Date:** 2026-11-06
**Status:** Approved (Sections 1–3 approved in chat)
**Home app:** `dashboard.py` (restyle in place)
**Companion spec:** `docs/superpowers/specs/2026-11-06-trip-risk-manual-ux-design.md` (Live/Manual functionality preserved)

## 1. Intent and constraints

**Purpose:** Make the Trip Risk Monitoring dashboard feel like Arte Voyages "quiet expertise" luxury (slow-travel, editorial, serif display) for internal ops + B2B readers, while keeping it scannable in a jiffy and fixing the map to English-only, India-centred.

**What the requester said:** Use the Arte Voyages 13-section luxury spec to redo UI/UX; why the map shows English + Arabic/Urdu country labels; want everything in English and the map centred at India.

**Agreed decisions:**
- Restyle dashboard only; no new marketing homepage, no enquiry form / testimonials / hero video / dark-mode toggle / language switcher (YAGNI for ops).
- Audience: internal ops + B2B buyers (partner agencies, corporate MICE). No traveller-facing copy; B2B "Our Approach / your clients and your brand" tone where copy is added.
- Keep Live/Manual toggle, scoring, alert taxonomy unchanged.

**Success criteria:**
- A first-time ops user reads the dashboard as calm luxury in 30 seconds without losing the KPI → scores → map → outlook → alerts → health scan.
- Both maps show English-only basemap labels with India centred.
- All 42 tests on master (30 committed + 12 legacy) plus new text assertions pass; `monitor.py`, `db.py`, `alerts.py`, `feeds.py`, `trips.csv`, `scorer.py` untouched.

## 2. Visual language + header rhythm (Section 1 — approved)

**Keep** Harbor+Brass tokens from `dashboard.py:21-34`:
- `primary "#1F3A4D"`, `secondary "#A68A56"`, `background "#FAF8F4"`, `surface "#FFFFFF"`, `text "#1B2630"`, `muted "#55626C"`, `border "#E4DED2"`.
- Playfair Display H1 / Source Sans body, brass 56px × 3px ornament (`h1::after`), WCAG AA (text 15.4:1, primary-on-white 11.9:1, muted 6.3:1), focus-visible outline, 44px touch rows, reduced-motion rule, 320px reflow.

**Add** Arte Voyages signature rhythm to every section in `dashboard.py` `_apply_design_system()` + `main()`:
- Eyebrow caption above each H2: e.g., `FIVE COUNTRIES · ONE TEAM` above Map, `OUR APPROACH` above 14-day outlook, plus KPI/scores/alert-feed/health equivalents.
- H2 in serif-adjacent sans 600 (existing), then centred ✦ brass ornament divider — extend the existing `h1::after` rule to `h2::after` so the eyebrow → H2 → ✦ → intro pattern repeats site-wide.
- One-line calm intro under each ornament in muted B2B quiet-expertise tone (e.g., "Read the legs your clients will travel — scored and explained.").
- Breathing room: increase `.block-container` top padding (1.2rem → 1.5rem) and KPI card vertical padding so the KPI row does not crowd; density otherwise unchanged (scores/outlook/alerts remain table-dense).

**Do not add:** dark-mode toggle, EN/ES/FR/DE/AR/HI language switcher, hero video/poster, Featured Journeys/Destinations/Our Approach/Testimonials/Enquiry sections, cookie banner, or "Plan Your Journey" form. Those are homepage-only (YAGNI).

## 3. Map fix (Section 2 — approved)

**Why mixing (answering the question):** `dashboard.py` uses `px.scatter_map(..., map_style="open-street-map", zoom=3)` (Live map ~:379; Manual map ~:318) with no `center`. OpenStreetMap tiles label places in the local script of the tile's area, so out to the Middle East/Asia/Europe you see Arabic («السعودية», «ايران»), Russian («Беларусь», «Україна»), Chinese, etc. Your own data is already English (`India`, trip/city names). The mixing is basemap labels, not your strings.

**Fix (both maps):**
- `map_style="carto-positron"` — CARTO light basemap, English transliteration only.
- `center=dict(lat=23.5, lon=78.5), zoom=4` — India centred, five countries fill the frame.
- Keep all other `scatter_map` args identical (lat/lon, `color="tier"` with `COLORS`, `hover_name="place"`, `hover_data=["trip_id","score","country"]`, `height`, `map_style` margin/template). No change to `simulate_manual`/scoring.

If CARTO tiles are unreachable offline, the existing `try/except → st.info(...)` fallback already covers it — no crash, same behaviour as today.

## 4. Error handling and bounds (Section 3 — approved)

- Tokens only; no hard-coded hex outside `TOKENS`/`COLORS`; tier never colour-alone (emoji + text preserved).
- Map change presentational only; no DB/schema/scoring change; no new network dependency beyond the same basemap fetch Streamlit already does.
- Empty-legs maps keep existing `st.info` / caption fallbacks; no empty Plotly frames.
- Responsive: mobile `@media (max-width: 768px)` padding retained; ornament/eyebrow collapses without overlapping charts.

## 5. Testing

- **New text assertions** in `tests/test_dashboard_manual.py`:
  - `map_style="carto-positron"` appears for both maps and `open-street-map` no longer appears.
  - `center=dict(lat=23.5` (or equivalent 23.x / 78.x) and `zoom=4` appear.
  - `✦` ornament + at least two eyebrow strings (e.g., `FIVE COUNTRIES`, `OUR APPROACH`) appear in `dashboard.py`.
  - `TOKENS` hex values unchanged.
- **Regression:** `pytest -q` from repo root must stay green (30 committed + 12 legacy = 42 passed).
- **Manual smoke:** `streamlit run dashboard.py` → both maps show English-only labels centred on India in Live and Manual; luxury-calm hierarchy visible without losing jiffy scanning.

## 6. Non-goals

- No dark-mode toggle, language switcher (with RTL), hero video, enquiry form/honeypot/reCAPTCHA, testimonials, cookie banner, or per-country deep links.
- No change to Live/Manual toggle semantics, threshold/scoring math, alert kinds, or the 30-minute `monitor` loop.
- No new files except test assertions; no `docs/` copy changes beyond this spec.
