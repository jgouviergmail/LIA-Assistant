# ADR-106: HITL Contract Coherence — Unified Confirmation Across Pipeline & ReAct

**Status**: ✅ IMPLEMENTED (2026-07-06)
**Author**: Claude Code (Opus 4.8)
**Related**: [ADR-044](ADR-044-Draft-HITL-Approval-Flow.md) (draft HITL flow), [ADR-070](ADR-070-ReAct-Execution-Mode.md) (ReAct execution mode), [ADR-085](ADR-085-Draft-Display-Registry.md) (draft display registry), [ADR-092](ADR-092-Replay-Safe-HITL-Interrupts.md) (replay-safe interrupts)

## Context

HITL confirmation had drifted into **two trigger mechanisms** that were wired
inconsistently across the two execution modes:

- **Output-driven** (post-execution): a tool returns `requires_confirmation=True`
  plus a `draft_type`; the graph routes it (pipeline `task_orchestrator` /
  ReAct draft handoff) → `hitl_dispatch` → an interrupt carrying
  `action_requests`. This path renders and resumes correctly in **both** modes
  (`draft_critique`, `for_each_confirmation`, `entity_disambiguation`,
  `tool_confirmation`).
- **Flag-driven** (pre-execution): `permissions.hitl_required=True` on a tool
  manifest. This flag is consumed **only** by `react_tool_selector` (the ReAct
  `hitl_map`); the pipeline never gates on it (`approval_gate_node` is a
  pass-through — confirmation is entirely output-driven there).

Three concrete defects fell out of this fragmentation:

1. **ReAct `react_tool_approval` was a dead-end dialect.** For a
   `hitl_required=True` tool, `react_execute_tools_node` raised
   `interrupt({"type": "react_tool_approval", ...})` — a value with **no
   `action_requests`**. The streaming service (`_handle_hitl_interrupt`) drops
   any interrupt without `action_requests`, so **nothing was rendered**: no
   question, no buttons — the graph suspended silently (a "silent hang").
   There was also no matching branch in `_parse_approval_decision`, so even if
   rendered the resume would not have mapped (`{"decision": ...}` vs the node's
   `.get("action")` check).
2. **Four delete/cancel tools carried a stale `hitl_required=True`.**
   `delete_email_tool`, `delete_event_tool`, `delete_label_tool` and
   `cancel_reminder_tool` are all **draft-based** (they return
   `requires_confirmation=True` → an `*_delete` draft → `draft_critique`),
   exactly like `delete_contact_tool` / `delete_task_tool` (which correctly had
   `hitl_required=False`). Their stale flag routed them to the broken
   `react_tool_approval` path — so deleting an email/event **in ReAct** silently
   hung (the manifest comment "has no draft_critique" was itself outdated).
3. **The batch `draft_critique` renderer hardcoded deletion wording.**
   `DraftCritiqueInteraction._generate_batch_critique` (used when ≥2 drafts of
   the same type are confirmed together, in **either** mode) always emitted
   `default_warning` ("this action is irreversible") + `confirm_question`
   ("do you confirm this deletion?"), even for a batch of **sends** — e.g.
   "send an email to A and B" in ReAct produced two identical `📧 Email :
   <subject>` rows under a *"Confirm sending"* title but a *"confirm this
   deletion?"* question, and never showed the recipient.

## Decision

**One HITL contract: every interrupt carries a type-tagged `action_requests`,
is rendered by its interaction, and resumes through its `_parse_approval_decision`
branch. ReAct has no bespoke dialect — its pre-execution mutation gate reuses
the shared `tool_confirmation` interaction, exactly like the pipeline.**

Four coordinated changes:

1. **`hitl_required` semantics, made explicit and enforced.** The flag means
   **"pre-execution confirmation for a genuinely non-draft mutation tool"** and
   nothing else. Draft-based tools are `hitl_required=False` (the draft *is* the
   confirmation, via `draft_critique`). The four stale delete/cancel flags were
   flipped to `False`, aligning them with `delete_contact`/`delete_task`.
   A boot/CI invariant locks it: `test_hitl_required_consistency.py` scans the
   full catalogue (95 tools) and asserts the set of `hitl_required=True` tools
   is a subset of an explicit allowlist (`{delegate_to_sub_agent_tool}` — the
   only genuinely non-draft built-in) plus, at runtime, user MCP mutation tools
   whose flag comes from server config. A draft tool re-acquiring the flag fails
   CI. Model: ADR-085 registry-completeness assert.
2. **ReAct mutation gate unified onto `tool_confirmation`.**
   `react_execute_tools_node` now raises an interrupt with the shared
   `action_requests: [{"type": "tool_confirmation", ...}]` shape
   (`hitl_type = HitlInteractionType.TOOL_CONFIRMATION.value`), so the streaming
   service renders it via the existing `ToolConfirmationInteraction` (question +
   buttons) **and persists it in Redis** — identical to the pipeline. The bare
   `react_tool_approval` value is removed.
3. **`tool_confirmation` resume branch.** `_parse_approval_decision` gained a
   `tool_confirmation` branch returning `{"action": "confirm"|"cancel"}` — the
   shape both `hitl_dispatch._handle_tool_confirmation` **and** the ReAct gate
   expect. This also repairs a latent **pipeline** gap: `tool_confirmation`
   previously fell through to the generic `{"decision": "APPROVE"}` path, which
   `_handle_tool_confirmation` (reading `.get("action")`) silently treated as
   "cancel". A mutation gate defaults to `cancel` on any non-approval (reject,
   ambiguous, classifier failure) — a mutation never executes without an
   explicit confirmation; ReAct correspondingly executes only on
   `action in {"confirm", "approve"}`.
4. **Batch `draft_critique` wording derives from the ADR-085 registry.**
   `_generate_batch_critique` computes `is_destructive` from
   `DraftDisplayConfig.verb_past_key == "deleted"` (the single source of truth):
   deletes keep the irreversible warning + deletion question; sends/creates/
   updates get no irreversible warning and the neutral FOR_EACH question
   (`get_for_each_confirm_translations`), consistent with the pipeline FOR_EACH
   flow. Send-type drafts (`email`/`email_reply`/`email_forward`) declare a new
   optional `item_recipient_field="to"`, so batch rows render
   `📧 Email à <recipient> : <subject>` — the recipient being the critical
   discriminating field the frontend has no card for (it renders only the
   streamed text + buttons). Zero new user-facing i18n strings: both existing
   6-language tables (`_DESTRUCTIVE_CONFIRM_UI`, `_FOR_EACH_CONFIRM_UI`) are
   reused, plus one localized `DRAFT_RECIPIENT_CONNECTOR` connector table.

## Consequences

- **Coherent HITL**: pipeline and ReAct use the same type, render and resume for
  every interaction. No mode-specific dialect; `react_tool_approval` is gone.
- **No more silent hang** on ReAct mutations; **safer default** (a gated
  mutation executes only on explicit confirmation).
- **Systemic bonus**: the `tool_confirmation` resume branch fixes the pipeline
  tool-confirmation path too, not just ReAct.
- **Regression-proofed**: the `hitl_required` invariant test turns a whole class
  of drift (a draft tool tagged `hitl_required=True`) into a CI failure instead
  of a production hang.
- **User MCP mutation tools** (`hitl_required=True` from server config,
  non-draft, ReAct-reachable) now get a real confirmation instead of hanging.
- No migration, no config change, no frontend change (`tool_confirmation` is an
  already-rendered `action_requests` type). Verified: 896+ unit tests green,
  ruff/black/mypy clean, container boot healthy, and the ReAct interrupt now
  emits a `hitl_interrupt_metadata` chunk (was 0 chunks before).

**Amends** [ADR-044](ADR-044-Draft-HITL-Approval-Flow.md) and
[ADR-070](ADR-070-ReAct-Execution-Mode.md); extends the ADR-085 registry with
`item_recipient_field`.
