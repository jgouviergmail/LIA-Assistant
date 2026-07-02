# ADR-092: Replay-Safe HITL Interrupts — One Interrupt Per Node Execution

**Status**: ✅ IMPLEMENTED (2026-07-02)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-022](ADR-022-LangGraph-State-Checkpointing.md) (checkpointing), [ADR-044](ADR-044-Draft-HITL-Approval-Flow.md) (draft HITL flow), [ADR-070](ADR-070-ReAct-Execution-Mode.md) (ReAct idempotence pattern)

## Context

LangGraph's resume semantics re-execute the **entire node** containing an
`interrupt()`: past interrupts return their cached resume values, but every
other statement — LLM calls, provider API calls — runs live again. Two HITL
flows looped around `interrupt()` *inside* a node and therefore replayed their
side effects on every user decision:

1. **Draft critique** (`hitl_dispatch_node._handle_draft_critique`): an
   internal while-loop re-ran every past `DraftModificationService.modify()`
   LLM call (non-deterministic) on each resume. After two edits and a confirm,
   the content actually sent could differ from the last version the user saw
   and approved.
2. **FOR_EACH bulk confirmation** (inside `task_orchestrator_node`): each
   resume re-ran the provider pre-execution (real API calls — latency, quota,
   preview drift) and every past LLM item-filter call. The item list executed
   could diverge from the list the user last confirmed.

The `clarify` action of draft critique additionally never displayed its
generated question (it was computed after the payload had been built).

## Decision

Normative pattern for every HITL node in the graph:

> **One `interrupt()` per node execution. All loop state travels through the
> graph state via the node's `return` (checkpointed), and iteration happens
> through a conditional self-loop edge — never through an in-node loop around
> `interrupt()`.**

Applied twice:

- **Draft critique** — `_handle_draft_critique` is single-pass. `edit` /
  `replan` / `clarify` run their (single) LLM mutation, persist the updated
  draft plus loop keys (`pending_draft_critique`, `draft_edit_iteration`,
  `draft_clarification_question`) and return; `route_from_hitl_dispatch`
  self-loops while `pending_draft_critique` is truthy, so the next node
  execution presents the updated draft in a NEW interrupt. Terminal decisions
  (`confirm`/`cancel`) reset the loop keys. Safety guard:
  `draft_edit_iteration >= settings.api_max_items_per_request` → cancel.
- **FOR_EACH confirmation** — extracted to the dedicated
  `for_each_confirm_node`. `task_orchestrator` pre-executes providers ONCE,
  persists the full context in `for_each_hitl_ctx`
  (`pre_executed_steps`, `pre_exec_registry`, `item_previews`,
  cumulative `filtered_indices`, `plan_id`/`turn_id` guards) and routes to the
  confirm node. APPROVE flips `ctx.approved` and routes back to the
  orchestrator, which resumes from the persisted context with **no re-fetch**;
  EDIT runs the LLM item filter once, persists cumulative indices (always
  mapping back to the ORIGINAL pre-executed items) and self-loops; REJECT /
  all-excluded / max-iterations produce the historical cancel result
  (`draft_action_result` with `action="cancel"`). The ctx is guarded by
  `plan_id` + `turn_id` (a ctx from an abandoned turn never matches) and
  purged in the orchestrator's final result.

**Invariant delivered by both flows: the content/item list the user last saw
is EXACTLY what gets executed, and no LLM or provider side effect ever runs
more than once per user decision.**

Every state key written by these nodes is declared in `MessagesState`
(LangGraph silently drops updates to undeclared keys — this migration
surfaced and fixed two historically dropped keys, `for_each_cancelled` and
`cancellation_reason`).

## Consequences

- Proven by compiled replay harnesses (real nodes + real routers +
  `InMemorySaver` + `Command(resume=...)` sequences):
  `tests/unit/domains/agents/nodes/test_hitl_dispatch_replay.py` and
  `test_for_each_confirm_replay.py`.
- ReAct mode is unaffected structurally: its draft hand-off already targets
  the shared `hitl_dispatch` node (ADR-070) and inherits the single-pass
  semantics; its tool-level interrupts already used the idempotence pattern.
- Any future HITL interaction MUST follow this pattern instead of looping
  around `interrupt()` inside a node.

Documentation: `docs/technical/HITL.md` (v8.5), `docs/ARCHITECTURE_LANGRAPH.md`
(§2.6, §2.8).
