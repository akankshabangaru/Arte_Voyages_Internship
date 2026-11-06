# SDD ledger — plan: docs/superpowers/plans/2026-11-06-trip-risk-monitor.md
Spec: C:\Users\chara\.opencode\plan\2026-11-06-trip-risk-design.md
Pre-flight scan:
- Task 2 Produces Leg/Event -> Task 3 Consumes Event: signatures match (scorer.Event fields) — clean
- Task 2 Produces Leg/Event -> Task 4 Consumes Event for upsert/get: DB maps Event fields — clean
- Task 2 Produces Leg -> Task 5 Consumes Leg for render_alert: render signature (trip_id, leg, tier, prev_tier, score, sigs, monitored_at) consistent — clean
- Task 3 Produces list[Event] -> Task 6 Consumes fetch_all -> list[Event]: matches — clean
- Task 4 Produces get_alerts/get_health -> Task 7 Consumes in dashboard: names match — clean
- Task 5 Produces notify(alert:dict) -> Task 6 Consumes notifier callable: matches — clean
Setup note: workdir is not a git repo (git status fatal) — Ruling: work in place, git init in Task 1 per plan; skip worktree since no repo to worktree from — cost if wrong: tasks share one working tree (single session, no parallel subagents, so no conflict).
Python runtime is 3.14.3 vs plan 3.12 — Ruling: accept 3.14 locally, keep Actions pinned to 3.12 — cost if wrong: 3.14-only syntax would break Actions; will avoid 3.14-only features.
