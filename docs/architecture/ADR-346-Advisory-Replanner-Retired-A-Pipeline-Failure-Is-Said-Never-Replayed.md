# ADR-346 — The advisory re-planner is retired: a pipeline failure is said, never replayed

- **Status**: Accepted
- **Date**: 2026-10-14
- **Supersedes**: [ADR-128](ADR-128-Adaptive-Replanner-Advisory-Only.md) (the
  advisory-only contract and the recovery loop « D4 » it deferred)
- **Amends**: [ADR-303](ADR-303-Tool-Failure-Restitution.md) (one failure
  predicate — the FOR_EACH aggregate it excludes is now marked by its producer)
- **Scope**: `orchestration/adaptive_replanner.py` (deleted),
  `nodes/task_orchestrator_node.py`, `orchestration/step_failure_metrics.py`,
  `infrastructure/observability/metrics_pipeline.py`,
  `diagnostics/failure_context.py`, `orchestration/parallel_executor.py`
  (`_aggregate_for_each_results`), `core/config/agents.py`, dashboard 07, the
  gettext catalogs, the public surfaces that described a recovery

## Context

ADR-128 kept an analyzer that ran after every failed pipeline plan, computed a
recovery decision (retry, re-plan, escalate, abort) and acted on none of it,
waiting for a recovery loop that was deferred. Measured before deciding, read
only, on production (2026-10-14):

| Fact | Value |
|---|---|
| Pipeline turns / ReAct turns, 30 days | 79 / 871 |
| Pipeline turns that executed a plan, 30 days | 47 |
| … with a recorded failure | 6, all on three days of connector testing; none on the 30 plans of the other days |
| Analyzer decisions, 7 days | 4, all `partial_failure → retry_same` (« transient ») |
| Their real causes, correlated by request id | two inactive connectors, one parameter the tool refused, one `$steps` reference unresolved before the call |
| Truly transient among them | 0 |

Why the analyzer was wrong, and why the loop it waited for would have been worse:

1. **It classified by the words of the error message**, never by the typed
   code the executor stores on every failed step. The substring-classification
   guard reads `str(e)` only, so it could not see these markers; the typed
   rewrite planned with ADR-303 was never shipped.
2. **Most of its vocabulary could not be produced.** With the attempt fixed at
   0, `ESCALATE_USER`, `ABORT` and `REPLAN_NEW` were unreachable, so were the
   reference, dependency, timeout and semantic triggers, and its seven user
   messages (in six languages) were never shown.
3. **It read success its own way** (a missing `success` key counted as one): a
   skipped conditional branch read as an empty result, and a clean plan whose
   step carries no data was advised to « broaden the search ».
4. **A transient provider failure is already retried where it happens**: the
   OAuth and API-key clients retry with backoff behind a circuit breaker. A
   plan-level retry would have been the fourth to sixth attempt on a service
   already failing.
5. **A failed act is not replayed under its key** (ADR-263): its claim is
   served, « not retried automatically ».
6. **An empty result is an answer** (the failures directive's first rule), and
   an account refusal cannot be planned away.
7. **The surfaces promised what never ran**: the FAQ, the How guide, two blog
   articles, the README and seven technical documents described a recovery, or
   metrics audit F017 had already deleted.

## Decision

1. **The analyzer goes**, with its two metrics, its two settings
   (`ADAPTIVE_REPLANNING_*`), its seven messages and its two test files. The
   orchestrator hands a failed step to the response, which states it through
   the runtime failures directive (ADR-303) — one channel.
2. **Each kind of failure is handled where it can be:**
   - transient (`TIMEOUT`, `EXTERNAL_API_ERROR`, `RATE_LIMIT_EXCEEDED`):
     retried inside the client that called the provider, within the step's own
     time limit, then said as the provider's failure (a rate limit with « try
     again in a few minutes »);
   - an account or a site refusing (`CONNECTOR_NOT_ACTIVATED`, `UNAUTHORIZED`,
     `FORBIDDEN`): said, with what fixes it when the directive knows;
   - caused by the plan: caught BEFORE execution where it can be, by the
     semantic validator's bounded re-plan loop (`planner_max_replans`); the
     ReAct mode, the person's choice, remains the self-correcting one (ADR-310);
   - empty: an answer.
3. **`pipeline_step_failures_total{error_code}`** (`metrics_pipeline.py`)
   counts every failed step of an executed plan through the directive's own
   predicate (`failed_step_codes`), its label a `ToolErrorCode` member or
   `unclassified`. It is the only Prometheus view of a failure that happens
   before the tool is called (no tool metric and no register row sees one).
   Dashboard 07, row « Pipeline Step Failures ».
4. **The FOR_EACH aggregate is marked by its producer**
   (`FIELD_FOR_EACH_AGGREGATE`). Its reader excluded it while no writer wrote
   it: the aggregate inherits `success: false` from a failed item, and the
   directive announced one failure more than happened (measured on the real
   aggregation: one failed item read as two, two as three).

## Consequences

- `_handle_execution_plan` falls from a cyclomatic complexity of 71 to 58, the
  orchestrator from 659 to 581 logical lines (out of the frozen list), and one
  function at or above complexity 15 disappears.
- No state key, register, migration or prompt changes; no model is called, so
  no token or quota changes either.
- An `ADAPTIVE_REPLANNING_*` line left in an operator's `.env` is ignored
  (`extra="ignore"`).
- The metric count published on the public surfaces moves with the code
  (`task release:sync-counts`).

### Reopening an automatic recovery after execution

A « correct and exploit » design was drawn up and weighed with the owner on
2026-10-14, then deferred for want of failures to repair. Reopening needs all
of these:

- `pipeline_step_failures_total` shows plan-caused failures the validator could
  not see before execution, at a rate that justifies a model call;
- a decision by typed code, never by message;
- repairs limited to read and draft steps — an act would otherwise run again
  with parameters a model changed and no card to show them;
- one pass, bounded by its own setting and reset every turn
  (`react_turn_reset()` is the pattern); successful steps carried over, never
  re-run; the repaired plan validated again.

## Amendment 2026-10-14 — the plan DSL declares only the step types that run

The same doctrine reached the plan language. `StepType` declared four types and
the executor ran two (`_execute_single_step_async` dispatches `TOOL` and
`CONDITIONAL`; anything else fails as « Unsupported step type »):

- `REPLAN` (« Phase 2 ») was refused by the validator (`NOT_IMPLEMENTED`), and
  `HUMAN` accepted — it set `requires_hitl` on a pass-through gate — then failed
  at execution. The LLM planner never produced either (it builds every step as
  `TOOL`); only a skill template could carry one, and none does on production
  (16 skills, 7 templates, no `step_type` declared — read only).
- Four copies published four vocabularies: the skill guide offered `REPLAN` and
  `HUMAN` in six languages, the skill generator's specification and validator
  `PARALLEL` and `RESPONSE` (not even members), `SKILLS_INTEGRATION.md`
  `CONDITIONAL` and `REPLAN`, the blog all four. A template carries a TOOL
  step's fields alone (`condition`, `on_success`, `on_fail` are never read), so
  a CONDITIONAL template step could not run either.

Decision: `REPLAN` and `HUMAN` leave the enum, the validator and the tests; a
test holds `StepType` equal to the executor's dispatch. `TEMPLATE_STEP_TYPES`
(`skill_bypass.py`, `{TOOL}`) is the one statement of what a template runs: any
other type refuses the template before execution and the request falls through
to the LLM planner. The generator's validator and its specification are held
to that set (`test_name_contract_parity.py`), and so is the skill guide in six
languages — by its own guard, which compared it with the ENUM and is the very
reason it advertised `REPLAN` and `HUMAN` (`test_skill_guide_step_types_sync.py`).
`ToolErrorCode.NOT_IMPLEMENTED` stays: a member of the general taxonomy, worded
by `plan_blockers` and typed from a third party's code. Left open on purpose:
no production code produces a `CONDITIONAL` step either — the DSL keeps it, as
its executor exists.

## Alternatives considered

- **Wire « D4 » as ADR-128 described it** — rejected for the reasons above.
- **Correct and exploit** (a typed repair pass through the existing re-plan
  channel) — designed, deferred: see the reopening conditions.
- **Keep the analyzer advisory but typed** — rejected: advice nobody reads.
