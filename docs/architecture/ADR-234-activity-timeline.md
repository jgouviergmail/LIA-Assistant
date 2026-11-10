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
  `last_executed_at`; the separate routine run history is not projected
  into this timeline).
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
  per-run history is available in the routine domain and remains outside
  this timeline’s existing scope.
- The evolution program's later lots (A3 provenance, C2 agent inbox)
  gain a natural surface to land on.


## Amendment — filtered reads and stable ordering (2026-11-09)

The timeline accepts literal displayed-text search, registry-validated categories,
recent/oldest ordering, and an echoed upper instant (`as_of`). Later pages carry
the first page's instant. This excludes later insertions; it is not an immutable
historical snapshot: edits and deletions remain visible, and the client deduplicates
by kind and row id. Account or criteria changes retire all prior pages and requests.

Filtering precedes each source cap. An empty query uses a window count beside the
ordered rows in one statement. A text query streams the complete owned time window
in bounded batches through the canonical display normalizer, retaining only the
matching prefix and counting every match. This deliberately avoids an unproved
SQL collation substitute for the shared Unicode contract. It is linear in the
window's text, not in the returned page; a future indexed projection must preserve
that contract and be measured before replacing it. No extra relationship loads,
LLM, connector calls, content logs or new persistence are involved.

Creation and closure of an open loop have separate ordered pools and caps. All
orders end on the source primary key, with kind then id breaking merged date ties.
When a source is capped, the merge returns only the prefix whose complete order is
known: another source cannot jump past that source's unseen next event. Exact
filtered totals and truncation remain explicit; `has_more` describes only the known
prefix. A failing source contributes no count and is named as unavailable.

The shared native list toolbar wraps at narrow widths. Empty search results offer
filter reset, a failed refresh retains its rows with a warning, and account-timezone
day headings include the year. PostgreSQL source tests cover all seven kinds,
ownership, ordering, null text, source scope, caps and cursor cancellation; browser
journeys cover the toolbar, stable paging, error recovery and accessibility.
