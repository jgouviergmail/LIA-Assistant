# ADR-234 — Activity timeline: the proactive work becomes visible

**Date**: 2026-08-19
**Status**: Accepted
**Context**: LIA's proactive subsystems (heartbeat, interests, journal
extraction, habit detection, open loops, scheduled actions) each persist
their own audit rows, but no surface answered "what did LIA do for me?"
in one place. The notifications hub answers "what reached me?" — a
narrower question: journal writes, habit detections and loop lifecycle
events never reach the user at all. Invisible proactive work earns no
trust, and trust is the prerequisite for every further autonomy step of
the evolution program (Lot 1-A1).

## Decision

A read-only bounded context `domains/activity/` aggregates the existing
audit tables into one merged, paginated, newest-first timeline:

- **Briefing orchestration doctrine, not LangGraph**: parallel fetchers
  via `asyncio.gather`, each acquiring its own `AsyncSession` through
  `get_db_context()` (an `AsyncSession` is not concurrent-safe). No new
  table, no scheduler, no LLM, no Redis cache (pure local SQL is fast
  enough and fresher).
- **Sources v1** (7 event kinds): `heartbeat_notifications`,
  `interest_notifications` (nullable `content` honored — pre-2026-08-03
  rows render without a paragraph), `journal_entries` (ACTIVE +
  automatic sources only — manual entries are the user's own actions),
  `user_habits` (detection = `created_at`), `open_loops` (up to two
  lifecycle events per row: created, ended — `updated_at` is an honest
  end timestamp because a loop leaves OPEN exactly once), and
  `scheduled_actions` (ONE event per action anchored on
  `last_executed_at`; there is no runs table, and the payload never
  pretends otherwise).
- **Reminders are deliberately absent**: a delivered reminder is deleted
  the instant it fires (ephemeral doctrine). No persisted trace → no
  event, no count. Inventing a history would violate ADR-185.
- **ADR-185 counting doctrine end to end**: per-kind totals are exact
  `COUNT(*)` aggregates over the whole window; rows only are capped
  (`ACTIVITY_TIMELINE_SOURCE_CAP`) and a hit cap is surfaced as an
  explicit `truncated` flag. A failed source contributes NO total and is
  listed in `failed_kinds` — partial data is stated, never silently
  completed.
- **Statement builders are pure module-level functions** so unit tests
  assert the compiled SQL predicates (WHERE contracts) without a
  database — the ADR-232 `select(User)` doctrine.
- **API**: `GET /api/v1/activity/timeline?offset&limit`, flag-guarded
  router (`ACTIVITY_TIMELINE_ENABLED`, default true), structured events
  + stable `kind` identifiers resolved to labels client-side (label_key
  doctrine — no translated prose in payloads).
- **Frontend**: `/[lng]/dashboard/activity` — accumulating feed
  (`useActivityTimeline`: pages keyed by echoed offset, offset-0 payload
  resets, (kind, ref_id) dedup), local-day grouping, exact-total chips,
  partial-data warning, `EmptyState variant="page"` pointing to the
  proactivity settings. Entry doors: a hub-shortcut CTA on the
  notifications hub and a footer link on the « For you » briefing card —
  both gated on the config flag (ADR-061 gate-keeper), no new nav slot
  (the header row is saturated; see the ADR-229 nav-overflow trap).

## Consequences

- The timeline is a READ MODEL over other domains' tables. Those domains
  keep write ownership; a schema change on a source table must keep the
  activity statement builders in sync (their SQL-predicate tests pin the
  contracts).
- One event per scheduled action (latest run) is a stated v1 limit; a
  per-run history requires a runs table and stays out of scope until a
  feature needs it.
- The evolution program's later lots (A3 provenance, C2 agent inbox)
  gain a natural surface to land on.
