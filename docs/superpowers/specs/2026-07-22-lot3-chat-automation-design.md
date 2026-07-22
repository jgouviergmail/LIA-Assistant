# Lot 3 — Automation from Chat (P11) + Recurrence Suggestion (P12)

**Program**: [Interdomain Intelligence Program](2026-07-21-interdomain-intelligence-program.md) · **Status**: SPEC (2026-07-22) → implementation
**ADR**: ADR-140 (to write at delivery) · **Arbitrated (D4)**: creation = confirmable HITL draft.
**D2 re-arbitrated at spec time**: P13 (contextual skill suggestion) is DETACHED from
this lot — P11+P12 alone are already L-sized; P13 moves to the Lot 6 window.

## P11 — Scheduled actions piloted from chat

**Gap**: no agent tool exists for scheduled actions (UI-only). "Fais-moi ça tous
les matins à 8 h" cannot succeed, although the executor already runs the full
pipeline (`scheduled_action_executor`).

### Design (verified integration surfaces)

- **New routable domain `automation`** in `DOMAIN_REGISTRY` (result_key
  `automations`, provider internal, `requires_hitl: True` metadata) +
  `automation_agent` registered in `startup/agents.py::init_agent_registry` +
  new manifest package `src/domains/agents/automation/catalogue_manifests.py`
  (pattern: `agents/reminders/`).
- **Three tools** in `agents/tools/automation_tools.py`:
  - `create_scheduled_action_tool` (`@write_tool`) — args: title,
    action_prompt (the free-text instruction executed by the pipeline),
    days_of_week (list[int] 0-6), trigger_hour/minute; validates via the
    existing `ScheduledActionCreate` schema rules; returns a
    **`DraftType.SCHEDULED_ACTION` draft** (requires_confirmation) — pattern:
    `_create_phone_call_draft` (draft shape owned by the tool module).
  - `list_scheduled_actions_tool` (read) — id, title, schedule human string,
    is_enabled, last/next run; feeds toggle by exposing real ids.
  - `toggle_scheduled_action_tool` (`@write_tool`, direct — reversible switch,
    no draft) — enable/disable by id (ownership enforced by the service).
  - Deletion stays UI-only in v1 (toggle-off covers the need reversibly);
    documented in the ADR.
- **Draft plumbing** (each is boot-asserted or CI-guarded):
  `DraftType.SCHEDULED_ACTION` · `DRAFT_DISPLAY_REGISTRY` entry (⏰,
  item_label_fields=("title",), detail fields title/schedule/action_prompt,
  noun/verb keys) · `i18n_drafts` noun/verb strings ×6 ·
  `execute_scheduled_action_draft` registered in
  `draft_executor._ensure_executors_registered()` → creates via
  `ScheduledActionService.create` (computes next_trigger_at) on the user's
  timezone.
- **Flag**: reuse none — scheduled actions are always wired (CLAUDE.md:
  no SCHEDULED_ACTIONS_ENABLED exists; do NOT invent one). The domain rides
  the standard catalogue.

### Tests (TDD)

Draft creation content shape · schedule validation (bad hour/day rejected
with friendly ToolErrorModel) · executor creates action with user timezone +
next_trigger computed · display-registry completeness stays green (boot
assert) · i18n noun/verb parity ×6 · taxonomy/agent/catalogue registration
smoke (tool_registry smoke test picks the new tools automatically) ·
list/toggle behavior incl. ownership.

## P12 — Recurrence detection → automation suggestion

**Gap**: nothing observes that a user asks the same thing every morning.
`PlanPatternLearner` stores GLOBAL tool-sequence stats without per-user
occurrence timestamps (verified) — unusable for recurrence.

### Design

- **Recurrence ledger (Redis, no new table)**: key
  `recurrence:{user_id}:{signature}`; signature =
  `primary_domain+sorted(secondary)` + coarse local-hour bucket (3 h);
  value = capped list of epoch timestamps + `suggested_at`. Written
  fire-and-forget as a **6th post-response block** in
  `post_response_extractions` (no LLM, pure Redis append; automated
  sources and trivial turns excluded — same guards).
- **Suggestion surface**: the initiative node's existing
  `STATE_KEY_INITIATIVE_SUGGESTION` slot. Deterministic check (no LLM):
  signature with hits on ≥ `RECURRENCE_MIN_DISTINCT_DAYS` distinct days
  within `RECURRENCE_WINDOW_DAYS` and no suggestion within
  `RECURRENCE_SUGGESTION_COOLDOWN_DAYS` → localized suggestion text
  ("Tu me demandes ça chaque matin — veux-tu que je l'automatise ?")
  via `core.i18n_*` (×6), then `suggested_at` stamped (one-shot per
  cooldown). The user's yes flows through P11's create tool naturally.
- **Settings module** `core/config/automation.py`: thresholds
  (`RECURRENCE_*`), all env-tunable; defaults in constants.

### Tests

Signature stability (same intent/hours bucket → same key) · distinct-days
rule (3 same-day asks ≠ recurrence) · cooldown one-shot · suggestion text
localized ×6 · ledger caps · guards (automated/trivial excluded).

## Out of scope (recorded)

P13 detached (see header). Deletion tool (v2). Frontend surfaces (Lot 4
briefing digest deep-links).

## Gates

`task lint` · `task test:backend:unit:fast` · i18n parity ×6 (backend tables
via their own tests; no frontend keys expected) · no migration · runtime
proof: container boot (display-registry assert passes) + in-container smoke
(draft create → executor path dry, taxonomy/agent/catalogue resolution).
