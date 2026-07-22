# Lot 2 — Open Loops / Commitments Ledger (P5)

**Program**: [Interdomain Intelligence Program](2026-07-21-interdomain-intelligence-program.md) · **Status**: SPEC (2026-07-22) → implementation
**ADR**: ADR-139 (to write at delivery) · **Flag**: `OPEN_LOOPS_ENABLED` (default false)
**Arbitrated (D3)**: v1 closure = conversational + soft expiry. NO email-thread scanning (v2).

## Goal

Track commitments surfaced in conversation — things the user owes someone
("je dois rappeler le plombier") and things the user is waiting on
("Marie doit m'envoyer le devis") — and nudge at the right time through the
heartbeat. The "assistant that never forgets" pillar.

## Scope v1

- **Extraction**: a 5th post-response background extraction (pattern:
  `memory_extractor`), gated by `OPEN_LOOPS_ENABLED` + non-trivial +
  non-automated-source. One structured LLM pass sees the conversation tail
  AND the user's current open loops → emits `open` items and `close` items
  (conversational closure: "c'est fait, j'ai rappelé le plombier").
- **Nudging**: new heartbeat source `open_loops` — fetches loops that are
  *nudge-worthy* (due within `open_loops_nudge_due_hours`, overdue, or stale
  ≥ `open_loops_nudge_stale_days`) AND outside the per-loop cooldown
  (`last_nudged_at` older than `open_loops_nudge_cooldown_days`). Decision
  prompt rule 19; source label `OPEN_LOOPS`. After a notification that used
  the source, `proactive_task` bumps `last_nudged_at`/`nudge_count` (same
  post-notify spot as the ADR-135 interest ledger bump).
- **Soft expiry**: lazily in the fetcher — loops stale beyond
  `open_loops_expiry_days` are flipped to `EXPIRED` (atomic UPDATE) instead
  of being nudged. No new scheduler job in v1.
- **API minimal** (flag-guarded router): `GET /open-loops` (list, filter by
  status) + `POST /open-loops/{id}/close`. Frontend surface comes with
  Lot 4 (briefing section).

## Out of scope v1 (recorded)

Email-reply closure (v2 — API cost of thread scans), per-user toggle (the
proactive surface is already bounded by the per-user heartbeat opt-in +
windows; extraction is global-flagged — revisit with the Lot 4 UI), vector
dedup (the extractor prompt receives current open loops and dedups in-pass,
like the memory extractor's existing-memories block).

## New bounded context `src/domains/open_loops/`

- `models.py` — `OpenLoop`: UUIDMixin + TimestampMixin; `user_id` FK
  CASCADE; `subject` (Text); `counterparty` (Text, nullable);
  `direction` ∈ {`user_owes`, `waiting_on_other`}; `due_hint`
  (DateTime tz, nullable, UTC); `source_kind` = `conversation` (enum,
  v1 single value); `source_ref` (thread id, nullable); `status` ∈
  {`open`, `closed`, `expired`} default open (+ partial index
  `(user_id, status)` WHERE status='open'); `closed_reason` nullable
  (`user_confirmed` | `conversational` | `expired` | `api`);
  `last_nudged_at` nullable; `nudge_count` int default 0.
- `repository.py` — `BaseRepository[OpenLoop]`: `list_for_user(status)`,
  `list_open_for_user(limit)`, `close(id, reason)` (atomic conditional
  UPDATE open→closed), `expire_stale(user_id, cutoff)` (atomic UPDATE …
  WHERE status='open' AND updated_at < cutoff), `bump_nudged(ids)`.
- `schemas.py` — response/request models; `router.py` — 2 endpoints,
  `get_current_active_session` + ownership.

## Extractor `agents/services/open_loop_extractor.py`

- `extract_open_loops_background(user_id, messages, session_id, run_id)`;
  structured output `OpenLoopExtraction {items: [{action: open|close,
  subject, counterparty?, direction, due_hint_iso?, loop_id? (for close)}]}`.
- Prompt: versioned `open_loop_extraction_prompt.txt` (v1) + `PromptName`
  Literal. Existing open loops rendered with ids (closure targets).
- LLM type: reuse decision on implementation — dedicated `open_loop_extraction`
  entry if `LLM_TYPES_REGISTRY` requires one (mirror `memory_extraction`).
- Token persistence mirrors `_persist_memory_tokens` (task_type
  `open_loop_extraction`).
- Wire as 5th block in `_schedule_post_response_extractions` (same guards,
  `safe_fire_and_forget`).

## Heartbeat integration

- `context_sources.fetch_open_loops_context(db?, user_id, settings)` →
  `HeartbeatContext.open_loops: list[dict] | None` ({subject, counterparty,
  direction, due_hint_local, days_open}) + ids kept on the context for the
  post-notify bump. Section `OPEN LOOPS`; label `OPEN_LOOPS`; rule 19
  (nudge tone: helpful reminder, direction-aware phrasing, never nag —
  one loop per notification max, combine with related calendar/email
  signals per rule 13).

## Settings (module `core/config/open_loops.py`, added to Settings MRO)

`open_loops_enabled` (False) · `open_loops_max_open_per_user` (30, extraction
refuses beyond) · `open_loops_nudge_due_hours` (48) ·
`open_loops_nudge_stale_days` (7) · `open_loops_nudge_cooldown_days` (3) ·
`open_loops_expiry_days` (21) · `open_loops_extraction_max_items` (5).
Defaults in `core/constants.py`; `.env.example` + `.env.prod.example`.

## Integration checklist (CLAUDE.md numbered points)

1. Config module in Settings MRO + flag + env examples
2. Constants centralized
3. Models registered ×3 (alembic/env.py, registry.py, startup/registries.py)
4. Migration + `task db:migrate:replay-check` (single head)
5. Router wired in api/v1/routes.py under flag guard
6. No lifespan step needed (no cache/registry)
7. No scheduler job (lazy expiry)
8. Prompt file + PromptName Literal
9. No new agent/tool (extraction is a background service)
10. Frontend deferred (Lot 4)
11. Backend i18n: none user-visible in v1 (LLM writes in user language;
    API returns raw data) — recheck at review
12. Observability v1 = structured log events (`open_loop_extraction_completed`
    with opened/closed/skipped counters, `open_loops_expired`,
    `open_loops_nudge_bumped`) + token billing via `track_proactive_tokens`
    (task_type `open_loop_extraction`). Prometheus counters arrive with the
    Grafana panels at the J+14 measurement (avoids touching
    `metrics_registry.py`, concurrently modified by the widgets workstream)
13. Exceptions: centralized raisers for the router
14. No new dependency
15. Rate limiting: standard router guards
16. Docs: ADR-139 + ADR_INDEX + INDEX.md + HEARTBEAT_AUTONOME.md source table

## Test plan (TDD, RED first per unit)

Model/enum defaults · repository atomic close (open→closed only once) ·
lazy expiry idempotent · extractor parsing (open/close/malformed/cap) ·
extractor guards (flag off, trivial, automated) · closure targets validated
against the user's own loops · heartbeat fetcher (nudge-worthiness matrix:
due soon/overdue/stale/cooldown/none) · schema render + label ·
post-notify bump only when `OPEN_LOOPS` in sources_used · router ownership +
flag-off 404 · migration replay-check.
