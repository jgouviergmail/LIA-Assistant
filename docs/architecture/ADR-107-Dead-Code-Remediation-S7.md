# ADR-107: Dead-Code Remediation (S7) — Removal of the v3 Autonomy Engines, Plan-Level Approval Framework, and Ghost HITL Orchestrator

**Status**: ✅ IMPLEMENTED (2026-07-07)
**Author**: Claude Code (Opus 4.8)
**Related**: [ADR-070](ADR-070-ReAct-Execution-Mode.md) (execution modes), [ADR-092](ADR-092-Replay-Safe-HITL-Interrupts.md) (replay-safe interrupts), [ADR-106](ADR-106-HITL-Contract-Coherence.md) (HITL contract — documented `approval_gate` as pass-through)

## Context

The 2026-07 full-codebase audit flagged ~5,800 lines of dead code (finding S7).
Cluster-by-cluster investigation confirmed the finding and **grew it**: several
"live-looking" subsystems were only reachable from other dead code, and one
service was instantiated at startup but never called afterwards (a *ghost
service*). Dead code here was not inert: it dragged along inert settings,
orphaned Prometheus metric definitions, Grafana panels that could never show
data, phantom tests that faked coverage, and docstrings describing behavior the
code no longer had.

Evidence method (each cluster, before deletion): all-scopes grep → AST
import-graph startup-closure analysis → runtime *simulated deletion* (an import
hook making the modules invisible while importing `src.main` and running the
full test suite) → per-cluster green-baseline / delete / green-suite /
fresh-Docker-boot cycle.

## Decision

Remove the dead code in five validated clusters; keep every element proven
live. Roughly **−13,600 lines** total (prod + phantom tests + observability).

**Removed:**

1. **`manifest_builder.py`** (fluent `ToolManifestBuilder`, 717 L) + 2 phantom
   test files. `ToolManifest` itself lives in `registry/catalogue.py`; the one
   TYPE_CHECKING import in `smart_catalogue_service` was repointed there.
2. **`state_keys.py`** (258 L) + its test — a parallel, unused copy of the
   state-key constants (the live ones are in `agents/constants.py`).
3. **Contacts v2** (`contacts_models.py` + `contacts_validators.py`, 737 L) +
   2 phantom tests + a stale debug script. The live contact tools never
   imported them.
4. **v3 autonomy engines**: `autonomous_executor.py`, `feedback_loop.py`,
   `relevance_engine.py`, the `agents/v3/` barrel (2,095 L), their inert
   config (`V3ExecutorConfig`/`V3RelevanceConfig`/`V3FeedbackLoopConfig`/
   `V3PromptConfig` + factories), 9 settings fields, 9 constants, 9 env vars
   in both templates, the 3 dead sections of `get_debug_thresholds()`, and
   the 3 dead test classes of `test_v3_architecture.py`.
5. **Plan-level approval framework + ghost HITL orchestrator**:
   `plan_editor.py` (766 L), the `services/approval/` package (evaluator +
   strategies, 452 L), the 4 dead helpers of `approval_gate_node.py`
   (626 → 130 L), the dead schema classes (`PlanApprovalRequest`,
   `PlanModification`, `PlanApprovalDecision`, `ApprovalEvaluation`,
   `PlanApprovalAudit`), the never-written `approval_evaluation` state field,
   **`hitl_orchestrator.py` (987 L — instantiated in `graph_management` but
   its instance was never accessed; proven by running the full suite with the
   module blocked)** and its `hitl/policies/` package (785 L, imported only by
   the ghost), 18 orphaned Prometheus metric definitions, 7 phantom test files
   (including `test_hitl_flows_e2e.py`, which patched a module deleted long
   before this work).

**Follow-up debt also cleaned in the same change:**

- `i18n_v3.py`: the 7 `V3Messages` methods + 11 translation dicts only the
  removed engines consumed (−381 L); module docstring updated.
- Observability sync: 11 recording rules and 7 alert rules over now-absent
  metrics removed (`promtool check rules` green, 86 rules left); 23 dead
  panels removed from Grafana dashboards `07-agents-pipeline` and `08-hitl`
  (they already rendered "no data": the removed metrics were labeled and thus
  never emitted series).

**Kept (proven live — do not re-remove):**

- `approval_gate_node` itself: still wired in the graph as an explicit
  pass-through (plan-level HITL is superseded by tool-level HITL, see
  ADR-106). Re-enabling plan-level approval means restoring an `interrupt()`
  in this node — no graph rewiring needed.
- `PlanSummary` / `StepSummary` and `PlanApprovalInteraction`: the HITL
  interaction registry **falls back to `PLAN_APPROVAL`** for unknown
  `action_type` values, so this path is the live safety net of the streaming
  HITL dispatch.
- `i18n_v3.V3Messages` (display cards), `V3RoutingConfig` (query analyzer via
  the `get_routing_thresholds` alias), `V3DisplayConfig`, all `for_each_*` and
  `hitl_plan_approval_question_duration` metrics, and the
  `hitl_classifier` / `hitl_question_generator` attributes of
  `GraphManagementMixin`.

## Consequences

- **Positive**: ~13,600 fewer lines to maintain; no more phantom tests faking
  coverage (removed tests covered only removed code, so live-code coverage is
  unchanged); honest docstrings; `/metrics` and dashboards no longer advertise
  series that can never exist; the "settings + code + tests + metrics + panels"
  cost of every future change shrinks accordingly.
- **Neutral / watch**: the `alert_rules.yml*` family is itself unloaded
  configuration (Prometheus `rule_files` only loads `recording_rules.yml` and
  alerting is disabled) — the live file was synced anyway, the 4 archive
  variants were left as historical snapshots; candidates for a future cleanup.
- **Rollback**: plain git history; every cluster is a self-contained deletion.

## Verification

Per cluster: green baseline → deletion → full suite green with **zero new
failures** (pass-count deltas exactly equal to the removed phantom tests) →
fresh Docker boot to `healthy` (`Application startup complete`, scheduler up).
Final audit pass: 10,982 tests collected with 0 import errors; previously
uncovered test dirs executed (411 green); ruff/black green repo-wide; mypy
green on all 848 source files; `/health` 200; `/metrics` checked for kept
(present) and removed (absent) metric names; every kept boundary exercised at
runtime in the container (including the registry fallback
`unknown action_type → PlanApprovalInteraction`).
