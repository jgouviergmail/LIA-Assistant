# ADR-128: Adaptive Re-Planner is Advisory-Only — Committed Contract, D4 Recovery Deferred

**Status**: ✅ ACCEPTED (2026-07-13)
**Author**: Claude Code (Opus 4.8)
**Related**: audit finding F017; `orchestration/adaptive_replanner.py`, `nodes/task_orchestrator_node.py`

## Context

After a plan executes, `task_orchestrator_node` runs `AdaptiveRePlanner.analyze_and_decide()`
on the completed steps. The analyzer is a fast (<10 ms), rule-based component that
classifies a failure and emits a **decision** (`PROCEED` / `RETRY_SAME` /
`REPLAN_MODIFIED` / `ESCALATE_USER` / `ABORT`) plus a recovery strategy.

Crucially, **the orchestrator never acts on that decision** — it only logs it and
lets the failed-step results flow to `response_node`, which surfaces the failure to
the user. There is no conditional edge back to the executor or planner, so no retry
or re-plan is ever executed and the attempt counter never advances past 0.

Two problems flagged by audit F017:

1. **Honesty** — earlier revisions counted `attempts` and `recovery_success`
   metrics and passed a fabricated `replan_attempt` state, implying an active
   recovery loop that does not exist.
2. **Provenance** — code comments justified the advisory contract by citing
   "ADR-100 / D4", but ADR-100 is an unrelated decision (Structured-Output prompt
   conflict guard). There was no ADR actually recording this contract.

## Decision

The adaptive re-planner is **advisory-only** and this is the committed product
contract for now:

- The orchestrator calls the analyzer for its **observability signal** (which
  failure pattern occurred, what recovery *would* be advisable) and for the
  failure message surfaced to the user. It performs **no automatic recovery**.
- Metrics are limited to what is genuinely observed: `adaptive_replanner_triggers_total`
  and `adaptive_replanner_decisions_total`. The `attempts` / `recovery_success`
  counters were removed — nothing retries, so counting attempts would lie.
- The call site fixes `replan_attempt = 0` (first and only pass) and does **not**
  read it from a state key, because none is written. No phantom "retry state"
  persists across the checkpoint reducer.

### Why the analyzer keeps its bounded-attempt design

`AdaptiveRePlanner` retains `replan_attempt` / `max_attempts` and the
`attempt >= max_attempts → ABORT` guard. This is **not dead scaffolding**: it is a
tested (`test_abort_on_max_attempts_exceeded`) safety bound that belongs to the
reusable analyzer, so that the deferred recovery loop below cannot spin unbounded
the day it is wired. The advisory caller simply exercises the analyzer in its
single-pass (`attempt = 0`) mode. Keeping the bound is intentional YAGNI-safety,
recorded here so it is not mistaken for an accidental unused field.

## Deferred: D4 automatic recovery loop

Wiring true recovery is a genuine, deliberately deferred feature (not a bug). It
requires LangGraph builder restructuring:

- `RETRY_SAME` → conditional edge `task_orchestrator → parallel_executor`, re-running
  only failed step(s), bounded by `settings.planner_max_replans`, with a persisted
  `retry_attempt` **declared in `MessagesState`** (undeclared keys are dropped by the
  checkpoint reducer).
- `REPLAN_MODIFIED` → conditional edge back to `planner_node_v3` with
  `modified_parameters` + `recovery_strategy` fed into the prompt, then re-validate.
- `ESCALATE_USER` / `ABORT` → write `user_message` to a state key `response_node`
  renders, instead of only logging it.

Until D4 is wired, every branch in the orchestrator stays HONEST: it must not claim
an action it does not perform, nor fabricate a user message nothing renders.

## Consequences

- The contract is now recorded in an accurate ADR; the misleading "ADR-100 / D4"
  code references are corrected to point here.
- No user-facing, config, or dashboard surface advertises automatic replanning
  (`adaptive_replanning_max_attempts` is internal-only, not exposed in `.env`).
- Re-opening recovery is a scoped, ADR-superseding change, not a silent edit.
