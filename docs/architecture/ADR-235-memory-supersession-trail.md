# ADR-235 — Memory supersession trail: automated corrections preserve history

**Date**: 2026-08-19
**Status**: Accepted
**Context**: The extraction pipeline already detects contradictions — the
LLM receives existing memories with their IDs and emits update/delete
actions — and the consolidation job already merges near-duplicates. But
both paths were DESTRUCTIVE: `update_memory` overwrote in place and the
merge hard-deleted the loser. A superseded fact ("he lives in Paris")
vanished the moment its successor arrived, leaving no trail for the
continuity features of the evolution program (D1: "tu me disais avant…")
and no audit of what the assistant once believed. This is the Graphiti /
temporal-knowledge-graph insight applied to LIA's existing memory store —
without adopting a new engine.

## Decision

- **Two nullable columns on `memories`** (migration `7f8a9b0c1d2e`, no
  backfill — every existing row is active by definition):
  `invalidated_at` (when the fact left the active set) and
  `superseded_by_id` (FK to the successor, `ON DELETE SET NULL`).
  The active-set index `ix_memories_user_invalidated` is declared in the
  model's `__table_args__` AND the migration (ADR-228 trap).
- **Automated paths supersede; manual paths keep their authority.**
  Extraction `update` → `MemoryService.supersede_with_update` (a NEW row
  inherits unspecified fields, embeddings regenerate; the old row points
  at its successor). Extraction `delete` → `invalidate_memory` (soft, no
  successor). Consolidation merge → the loser is superseded by the
  survivor (`_apply_merge`). The manual API PATCH/DELETE semantics are
  deliberately unchanged: a user correction is an authority, not an
  evolution to be historized against them.
- **Every retrieval serves the active set only**: a central `_active()`
  predicate filters search, listings, counts, name mentions and
  consolidation pairing. The oracle is a captured-statement test that
  compiles each repository method's SQL and asserts the
  `invalidated_at IS NULL` predicate (ADR-232 WHERE-assert doctrine).
- **The trail is a trail, not an archive**: the nightly cleanup job purges
  invalidated rows older than `MEMORY_INVALIDATED_RETENTION_DAYS`
  (default 90) — successors carry the live facts.

## Consequences

- D1 (conversational continuity) can now cite what changed and when,
  reading a fact's predecessors via `superseded_by_id` — without ever
  re-serving a stale fact in search.
- Pinned memories keep their existing protections (extraction skips them,
  consolidation excludes them at SQL level) — supersession never touches
  a user-locked fact.
- GDPR deletion paths (`delete_all_for_user`) hard-delete regardless of
  invalidation state — the trail is user data like any other.
- The CC ratchet stays untouched: the cleanup purge and the initiative
  motivation handoff were extracted as helpers rather than growing the
  `cleanup_memories` / SSE hotspots (decompose, never raise the cap).
