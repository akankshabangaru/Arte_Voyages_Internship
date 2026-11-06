# Trip Risk Luxury Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle `dashboard.py` with Arte Voyages light luxury rhythm and fix both maps to English-only, India-centred.

**Architecture:** Keep Harbor+Brass tokens and Live/Manual logic untouched; add CSS ornament/rhythm + eyebrow/intro copy; swap `map_style`/`center`/`zoom` in the two `px.scatter_map` calls.

**Tech Stack:** Python 3.12, Streamlit, Plotly, pandas, pytest

**Spec:** `docs/superpowers/specs/2026-11-06-trip-risk-luxury-refresh-design.md`

## Global Constraints

- Harbor+Brass TOKENS only (primary "#1F3A4D", secondary "#A68A56", background "#FAF8F4", surface "#FFFFFF", text "#1B2630", muted "#55626C", border "#E4DED2"); no hard-coded hex outside TOKENS/COLORS
- Tier labels always emoji + text; WCAG AA, focus-visible, 44px targets, reduced-motion, 320px reflow retained
- Map style `carto-positron` (English-only), `center=dict(lat=23.5, lon=78.5), zoom=4` (India centred) on both Live and Manual maps
- `monitor.py`, `db.py`, `alerts.py`, `feeds.py`, `trips.csv`, `scorer.py` untouched; no new files except test assertions
- Baseline: 42 passed on master (30 committed + 12 legacy); suite must stay green

## Review Focus

- **Empty legs with Manual picked (no scores, fallback CSV missing/corrupt):** Expect `st.info` fallback, no empty Plotly crash — pinned by Task 1's fallback assertions.
- **Offline / CARTO tiles unreachable:** Expect `st.info` fallback, no crash — pinned by Task 1's map-style assertions plus existing try/except.
- **Single-leg Manual map (picked leg only):** Expect India-centred single-point map still renders at zoom 4 — pinned by Task 1's `center/zoom` assertions.
- **User CSS tweak in working tree (`header[data-testid="stHeader"]` line):** Expect merge to preserve it (stash/pop) — pinned by Task 3's post-merge `git diff` check.
- **Threshold slider inverted (Act below Watch):** Expect scorer clamp still holds (unchanged) — pinned by Task 3's full suite (test_threshold_clamp_prevents_inversion).

---

## File Structure

- `dashboard.py` — only presentation: `_apply_design_system()` CSS (block padding, h2 ornament), `main()` section headers (eyebrows/intros), two `px.scatter_map` calls (style/center/zoom). No logic change.
- `tests/test_dashboard_manual.py` — new text assertions only (map style/center/zoom, ornament/eyebrow presence, TOKENS unchanged). No logic change.

---

### Task 1: Map fix — English-only, India-centred

**Files:**
- Modify: `dashboard.py:308-319` (Manual map), `dashboard.py:377-382` (Live map)
- Test: `tests/test_dashboard_manual.py`

**Interfaces:**
- Consumes: `px.scatter_map` existing args (lat/lon, `color="tier"`, `COLORS`); `sim_df`/`mdf` DataFrames
- Produces: both maps render with `map_style="carto-positron", center=dict(lat=23.5, lon=78.5), zoom=4`; `open-street-map` absent from file

- [ ] **Step 1: Write the failing test**

```python
import pathlib
def test_maps_are_english_and_india_centred():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert 'map_style="carto-positron"' in text
    assert "open-street-map" not in text
    assert "center=dict(lat=23.5" in text
    assert "zoom=4" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_manual.py::test_maps_are_english_and_india_centred -v`
Expected: FAIL (`assert 'map_style="carto-positron"' in ...` — currently `open-street-map`)

- [ ] **Step 3: Swap both `px.scatter_map` calls in `dashboard.py`**

In Manual map (`~:308`) and Live map (`~:377`): change `map_style="open-street-map"` to `map_style="carto-positron"`, change `zoom=3` to `zoom=4`, add `center=dict(lat=23.5, lon=78.5)`. Touch nothing else in those calls.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_manual.py::test_maps_are_english_and_india_centred -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard_manual.py
git commit -m "fix: maps English-only via carto-positron, centred on India"
```

---

### Task 2: Luxury rhythm — ✦ ornament, eyebrows, breathing room

**Files:**
- Modify: `dashboard.py:37-80` (`_apply_design_system`), `dashboard.py:195-196` (H1 stack), `dashboard.py:359-438` (section headers)
- Test: `tests/test_dashboard_manual.py`

**Interfaces:**
- Consumes: `TOKENS` (`dashboard.py:21-30`), existing `h1::after` ornament rule
- Produces: `h2::after` brass ornament, eyebrow captions (`FIVE COUNTRIES`, `OUR APPROACH`, etc.) above each H2, one-line B2B intro per section, `.block-container` padding `1.5rem`, KPI padding `14px`; TOKENS unchanged

- [ ] **Step 1: Write the failing test**

```python
def test_luxury_rhythm_present():
    text = pathlib.Path("dashboard.py").read_text(encoding="utf-8")
    assert "✦" in text
    assert "h2::after" in text
    assert "FIVE COUNTRIES" in text
    assert "OUR APPROACH" in text
    assert '"#1F3A4D"' in text and '"#A68A56"' in text and '"#FAF8F4"' in text
    assert "1.5rem" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard_manual.py::test_luxury_rhythm_present -v`
Expected: FAIL (`assert "✦" in ...`)

- [ ] **Step 3: Add ornament, eyebrows, intros, and padding in `dashboard.py`**

Extend `h1::after` selector to `h1::after, h2::after` (same 56px×3px brass rule); change `.block-container` `padding-top: 1.2rem` to `1.5rem` and KPI `[data-testid="stMetric"]` padding from `10px 14px` to `14px`. In `main()`, add `st.caption("FIVE COUNTRIES · ONE TEAM")` + one-line B2B intro above each of the five section H2s (Map, Trip scores, 14-day outlook, Alert feed, Feed health), and extend the H1 `st.caption` to the Arte sub-label `Curated Luxury Journeys Across India & Beyond ✦` if needed to satisfy the ornament assertion. TOKENS hex values untouched.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard_manual.py::test_luxury_rhythm_present -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add dashboard.py tests/test_dashboard_manual.py
git commit -m "feat: Arte luxury rhythm (eyebrows, ornament, breathing room)"
```

---

### Task 3: Full regression and manual smoke

**Files:**
- Test: all `tests/`

**Interfaces:**
- Consumes: Tasks 1–2 deliverables
- Produces: green suite, no product-code changes

- [ ] **Step 1: Run the full suite**

Run: `pytest -q` (from repo root)
Expected: PASS (32 committed including 15 manual-file tests + 12 legacy = 44 passed)

- [ ] **Step 2: Smoke the dashboard**

Run: `streamlit run dashboard.py`
Expected: both maps show English-only labels centred on India in Live and Manual; sections read luxury-calm (eyebrow → H2 → ✦ → intro) without losing jiffy scanning

- [ ] **Step 3: Commit (only if a fix was needed)**

```bash
git add -A
git commit -m "fix: luxury refresh smoke pass"
```
