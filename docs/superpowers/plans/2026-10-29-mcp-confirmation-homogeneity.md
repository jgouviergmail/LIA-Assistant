# MCP Confirmation Homogeneity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** One confirmation rule for every MCP tool (administrator or personal, standard or iterative), applied by the effect gate in every mode; Pipeline confirms after the work is done and resumes the plan once the person approves.

**Architecture:** The manifest's derived `mutation_policy` is the single declaration; the effect gate reads the turn's offered manifest for any tool the global registry does not know; iterative sub-loops give every call its own ledger key, keep their drafts instead of losing them, and hand them up with a code-written record; the Pipeline holds the steps that need a pending result and routes back to the orchestrator once the drafts are confirmed; ReAct asks on one predicate; a routine may pre-approve servers.

**Tech Stack:** Python 3.14, FastAPI, LangGraph 1.x, LangChain 1.x, SQLAlchemy 2 (PostgreSQL), Pydantic 2, Next.js 16 / React 19, vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-10-29-mcp-confirmation-homogeneity-design.md`

## Global Constraints

- Owner rule: work in the working tree of `main`, **no git action of any kind** — every "commit" step of the template is replaced by a ledger line.
- File-size caps (`apps/api/tests/unit/file_size_baseline.json`, logical SLOC): `parallel_executor.py` 2 055 / 2 097, `agent_registry.py` 776 / 779, `hitl_dispatch_node.py` 672 / 686, `effects/runtime.py` 555 / 600, any new file < 600. Additions go to new modules; a touched frozen file shrinks where it safely can.
- No function at cyclomatic complexity ≥ 15; no new runtime import cycle (`task lint` ratchets).
- Model-facing text is technical English in a versioned `key|template` lines file under `apps/api/src/domains/agents/prompts/v1/`, read by `core/prompt_store.parse_prompt_sections`; never inline in `.py`.
- Every user-visible string in the six locales (en, fr, de, es, it, zh); `task lint:i18n` green.
- Any key a node writes is declared in `MessagesState`, reset by `draft_turn_reset()`, and covered by a round-trip test.
- A new Prometheus metric only if a panel, rule or alert reads it (`test_metric_coverage_ratchet_guard.py`); prefer existing counters.
- Tests never read a database for `LLM_DEFAULTS`, never hard-code a settings threshold, never skip on a missing key.
- End of every task: a cold adversarial review of every touched file (owner rule), then `task test:backend:unit:fast`; Task 7 runs every gate.
- The line C, verbatim (spec D5):
  `Queued for the person's approval: this call was NOT performed. The person will be asked to approve it right after this task. Do not call it again and do not try another way to achieve it. Continue with the rest of the task, and in your final answer list it as awaiting the person's approval: neither done nor failed.`
- The probes and the bench that proved the spec live in the session scratchpad (`probe_mcp_homogeneity/`); each task below turns its probe into a repository test that asserts the TARGET.

## Review Focus

1. **Replay after an interrupt.** LangGraph re-executes a node on resume: the resumed orchestrator, the response and the HITL dispatch must not perform an effect twice (one effect row per act). Test in Task 4.
2. **Concurrent inner calls.** A sub-loop's tool calls may run concurrently; each must get its own ledger key and its own pending-draft entry, none lost or duplicated. Test in Task 1 and Task 3.
3. **A server switched off between the card and the answer.** The replay must say « no longer available; nothing was performed », never act and never crash. Test in Task 3.
4. **Two accounts, the same 8-hex prefix.** No policy, manifest or draft may cross accounts. Test in Task 2.
5. **A routine's pre-approval widened by the agent.** No agent tool path may write `mcp_preapproved_servers`. Test in Task 6.

---

### Task 1: One ledger key per call inside an iterative sub-loop (spec D4)

**Files:**
- Modify: `apps/api/src/domains/agents/effects/scope.py` (add `sub_call_scope`)
- Modify: `apps/api/src/domains/agents/tools/mcp_react_tools.py` (`_MCPReActWrapper._to_args_and_kwargs`, `_MCPReActWrapper._arun`)
- Test: `apps/api/tests/unit/domains/agents/effects/test_sub_loop_call_keys.py`
- Test: `apps/api/tests/integration/domains/agents/effects/test_sub_loop_call_keys_db.py`

**Interfaces:**
- Produces: `sub_call_scope(parent: EffectScope | None, tool_call_id: str | None) -> EffectScope | None` — `None` when `parent` is `None`; otherwise `replace(parent, idempotency_key=f"{parent.idempotency_key}:sub:{tool_call_id or uuid4().hex}")`, every other field (run id, source, approval) unchanged.
- Produces: the call id travels IN THE CALL, never in shared state. `_MCPReActWrapper._to_args_and_kwargs(tool_input, tool_call_id)` returns the inner projection plus a private key `_SUB_CALL_ID_KWARG` (a module constant) holding `tool_call_id`; `_arun(**kwargs)` pops it and wraps `self._inner._arun(**rest)` in `effect_scope(sub_call_scope(current_scope(), call_id))`. Verified 2026-10-29 in langchain-core 1.5.6 (`BaseTool.arun`, lines 1218-1230): `_to_args_and_kwargs` runs BEFORE `set_config_context` copies the context, so a `ContextVar` set there would stay set in the caller's context after the call and leak a stale id into the next call — rejected for that reason.

- [ ] **Step 1: Write the failing tests** (from probe H4, target form)
  - `test_two_inner_reversible_calls_both_run` — two wrappers under one parent scope, `resolve_policy` patched to `"reversible"`, the unique-key fake ledger of the probe: assert both calls ran and `ledger.keys == {"step-1:sub:c1", "step-1:sub:c2"}`.
  - `test_concurrent_inner_calls_get_distinct_keys` — `asyncio.gather` of two `wrapper.ainvoke({"name":…, "args":…, "id": "cA"/"cB", "type": "tool_call"})`: two distinct keys, both performed (hypothesis Ha).
  - `test_no_stale_id_after_a_call` — `ainvoke` with id `cA`, then a direct `_arun(...)` in the same task: the second call's key is NOT `…:sub:cA`.
  - `test_the_private_key_never_reaches_the_server` — the inner adapter's `_call_server` receives no `_SUB_CALL_ID_KWARG`.
  - `test_child_inherits_approval_only_from_parent` — parent `approved=True` → child approved; parent `approved=False` → child not approved.
  - `test_no_parent_scope_publishes_none` — `sub_call_scope(None, "x") is None`.
  - Integration (PostgreSQL, `@pytest.mark.integration`): two inner `reversible` calls under one step scope write two `agent_effects` rows, both `SUCCEEDED`.
- [ ] **Step 2: Run** `cd apps/api && .venv/Scripts/pytest tests/unit/domains/agents/effects/test_sub_loop_call_keys.py -v` — Expected: FAIL (`sub_call_scope` not defined; second call not performed).
- [ ] **Step 3: Implement** `sub_call_scope` in `scope.py` and the ContextVar hand-off in the wrapper.
- [ ] **Step 4: Run** the unit file — Expected: PASS; then `task test:backend:integration -- tests/integration/domains/agents/effects/test_sub_loop_call_keys_db.py` (host + testcontainers, never inside `lia-api-dev`) — Expected: PASS.
- [ ] **Step 5: Cold review + `task test:backend:unit:fast`;** ledger line (no commit).

### Task 2: One manifest per MCP tool; the gate reads the offered manifest; every MCP callable gated (spec D1, D2, D3)

**Files:**
- Create: `apps/api/src/domains/agents/registry/reactive_manifests.py`
- Modify: `apps/api/src/infrastructure/mcp/admin_registration.py` (`_register_iterative_server`)
- Modify: `apps/api/src/domains/agents/registry/request_tool_identity.py` (`_reactive_manifest`)
- Modify: `apps/api/src/domains/agents/effects/runtime.py` (`resolve_policy`)
- Modify: `apps/api/src/infrastructure/mcp/user_context.py` (iterative registration: gate the task copy)
- Modify: `apps/api/src/infrastructure/mcp/gated_tool.py` (add `ungated_names`)
- Modify: `apps/api/tests/unit/domains/agents/effects/test_gate_on_mcp_adapters.py` (a real-resolution test beside the patched one)
- Test: `apps/api/tests/unit/domains/agents/effects/test_gate_reads_offered_mcp_manifest.py`
- Test: `apps/api/tests/unit/domains/agents/registry/test_reactive_individuals.py`
- Test: `apps/api/tests/unit/infrastructure/mcp/test_every_mcp_callable_is_gated.py`

**Interfaces:**
- Produces (`reactive_manifests.py`): `register_reactive_manifest(manifest: ToolManifest) -> None` (requires `mcp_origin == "admin"` and a `mcp_server_key`), `reactive_manifest(name: str) -> ToolManifest | None`, `reset_reactive_manifests() -> None`. Process-wide, written at MCP startup only.
- Changes: `_reactive_manifest(name, manifests, ctx)` admits a candidate from `ctx.reactive_tool_manifests` (origin `user`) OR `reactive_manifest(name)` (origin `admin`) when an offered task manifest has `delegates_execution`, the same origin and the same `mcp_server_key`.
- Changes: `resolve_policy(tool_name)` — global hit memoised as today; on `ToolManifestNotFound` returns `resolve_tool_manifest_named(tool_name)[0].mutation_policy` (validated against `MUTATION_POLICIES` like the global path) and memoises NOTHING.
- Produces: `ungated_names(instances: Mapping[str, BaseTool]) -> list[str]` (instances whose callable lacks `EFFECT_GATED_ATTR`). `user_context` drops such an instance from the context (fail closed) and logs `mcp_user_tool_ungated` with the count; outside production it raises `RuntimeError`.

- [ ] **Step 1: Write the failing tests** (probes H1, H2, H3, H5, P1, target form)
  - `test_personal_confirm_tool_becomes_a_draft_in_pipeline` — the probe's H2 set-up WITHOUT patching `resolve_policy`: the server is not reached; the result has `tool_metadata["requires_confirmation"] is True`.
  - `test_personal_policy_is_never_memoised` — same name, context 1 manifest `confirm`, then context 2 manifest `reversible`: the second call reads `reversible`.
  - `test_two_accounts_same_prefix_keep_their_own_policy` — two `UserMCPToolsContext` with colliding adapter names and different policies, read in two tasks: each reads its own (Review Focus 4).
  - `test_admin_iterative_individual_has_a_policy_and_replays` — after `_register_iterative_server` (fake ports), `resolve_policy(individual)` is the derived policy and, with the task offered, `resolve_tool_instance(individual)` returns the adapter (probe P1 admin).
  - `test_no_individual_reaches_the_turn_catalogue` — `build_request_tool_manifests(registry)` contains the task, no individual (hypothesis He).
  - `test_personal_task_tool_is_gated` — the named task copy's coroutine carries `EFFECT_GATED_ATTR` under its own name (probe H5).
  - `test_hitl_on_iterative_task_is_asked_once_and_covers_the_loop` — server `hitl_required=True`: the Pipeline call of its task returns one TOOL_CALL draft and reaches no server; replayed under `call:{draft_id}`, its inner calls run under child scopes (Task 1) that inherit the approval, none raising a draft.
  - `test_an_ungated_instance_is_dropped_in_production_and_raises_elsewhere`.
- [ ] **Step 2: Run** the three new files — Expected: FAIL on every test above.
- [ ] **Step 3: Implement** in the order of the Files list.
- [ ] **Step 4: Run** the new files and `tests/unit/domains/agents/effects/` — Expected: PASS; no existing test regresses.
- [ ] **Step 5: Cold review + `task test:backend:unit:fast`;** ledger line.

### Task 3: The work is done, confirmations wait for the end of the task; the record is the code's (spec D5, D6)

**Files:**
- Create: `apps/api/src/domains/agents/prompts/v1/mcp_sub_loop_lines.txt` (keys `pending_approval` = line C; `record_heading`, `record_performed`, `record_awaiting` — the code-written record, technical English, placeholders `{actions}`)
- Create: `apps/api/src/domains/agents/orchestration/step_drafts.py`
- Modify: `apps/api/src/domains/agents/tools/mcp_react_tools.py` (wrapper keeps drafts and performed acts; `_run_mcp_react_task` builds the output)
- Modify: `apps/api/src/domains/agents/tools/react_runner.py` (`ReactSubAgentResult.pending_drafts`, `performed_acts`, collector)
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py` (`_execute_tool` reads `drafts_of`; `ToolExecutionResult`/`StepResult` carry `draft_infos: list[dict]`; `_merge_single_step_result` extends) — the inline draft block moves to `step_drafts.py`, net SLOC ≤ 0
- Modify: `apps/api/src/domains/agents/nodes/react_drafts.py` (`extract_drafts` returns a list) and `react_call_execution.py` (`_draft_update`: first draft current, the rest in `pending_drafts_queue`, `pending_drafts_grouped=False`)
- Test: `apps/api/tests/unit/domains/agents/tools/test_mcp_sub_loop_pending_drafts.py`
- Test: `apps/api/tests/unit/domains/agents/orchestration/test_step_drafts.py`
- Test: `apps/api/tests/unit/domains/agents/nodes/test_react_draft_queue_from_one_call.py`
- Test: `apps/api/tests/unit/domains/agents/effects/test_individual_replay.py`

**Interfaces:**
- Consumes: Task 1 `sub_call_scope`; Task 2 admin/personal individual resolution.
- Produces (`step_drafts.py`): `drafts_of(result: StandardToolOutput | UnifiedToolOutput, tool_name: str, step_id: str | None) -> list[dict[str, Any]]` — today's single-draft keys, or the list under `tool_metadata["pending_drafts"]`; each dict has `draft_id, draft_type, draft_content, draft_summary, registry_ids, tool_name, step_id` (the `PendingDraftInfo` fields).
- Produces (`step_drafts.py`, extracted VERBATIM from `_execute_tool`'s registry block, lines 2731-2830 today): `project_tool_result(result: StandardToolOutput | UnifiedToolOutput, *, tool_name: str, step_id: str | None, turn_id: int | None, correlation_parent_id: str | None) -> ToolExecutionResult` — registry ids injected, correlated ids derived, structured data for Jinja, drafts read through `drafts_of`. `_execute_tool` calls it (the file shrinks); Task 4's resume calls it on a TOOL_CALL replay. A golden test pins its output against today's block on three fixtures (a plain result, a FOR_EACH-correlated one, a draft) BEFORE the extraction.
- Produces: `ReactSubAgentResult.pending_drafts: list[dict[str, Any]]`, `ReactSubAgentResult.performed_acts: list[str]` (labels from `readable_tool_name`, only for calls `explicit_success` reads as succeeded).
- Produces: the task output — `message` = final message + `\n\n` + record rendered from the lines file; `metadata` gains `requires_confirmation: True` and `pending_drafts: [...]` when any.
- Changes: `react_call_execution.Executed.draft: dict | None` becomes `drafts: list[dict[str, object]]` (empty = no draft); `react_drafts.extract_draft_info` becomes `extract_drafts(raw_result, tool_name) -> list[dict[str, Any]]` built on `drafts_of`; `react_egress_question.py` takes its first element.

- [ ] **Step 1: Write the failing tests** (probe H6 and bench, target form)
  - `test_wrapper_returns_line_c_and_keeps_the_draft` — the fake scripted model of the bench through the real `ReactSubAgentRunner`: the delete call's ToolMessage content equals line C; `result.pending_drafts` has one entry naming the individual; the server never reached for it; both archives performed.
  - `test_task_output_publishes_every_draft_and_the_record` — two pending deletes → `metadata["pending_drafts"]` length 2; the message ends with the record listing 2 performed and 2 awaiting, read back through `parse_prompt_sections`.
  - `test_one_step_with_two_drafts_queues_two` — `_execute_tool` on such an output → `draft_infos` length 2 → `ParallelExecutionResult.pending_drafts` length 2.
  - `test_react_queues_all_but_the_first` — `_draft_update` with two drafts: `pending_draft_critique` = first, `pending_drafts_queue` = [second], grouped False.
  - `test_confirmed_individual_replays_once` — `execute_tool_call_draft` for a personal and an admin individual: one call reaches the server under `call:{draft_id}`.
  - `test_server_gone_before_the_answer` — instance absent at replay: the result says « no longer available; nothing was performed » (Review Focus 3).
  - `test_concurrent_pending_drafts_none_lost` — two inner `confirm` calls gathered concurrently in one sub-loop: two entries in `pending_drafts`, distinct draft ids, none duplicated (Review Focus 2).
- [ ] **Step 2: Run** the four files — Expected: FAIL (ToolMessage is the French preview; no `pending_drafts`; single draft only).
- [ ] **Step 3: Implement** in the order of the Files list; verify `test_prompt_placeholders_are_produced.py` and the file-size guard still pass.
- [ ] **Step 4: Run** the four files + `tests/unit/domains/agents/orchestration/` + `tests/unit/domains/agents/nodes/` — Expected: PASS.
- [ ] **Step 5: Cold review + `task test:backend:unit:fast`;** ledger line.

### Task 4: A step needing a pending result waits; the plan resumes after approval (spec D7)

**Files:**
- Create: `apps/api/src/domains/agents/orchestration/held_steps.py`
- Create: `apps/api/src/domains/agents/orchestration/plan_resume.py`
- Modify: `apps/api/src/domains/agents/orchestration/parallel_executor.py` (held steps added to `excluded_steps`; `ParallelExecutionResult.held_steps`; `_check_plan_completion` gains the held set and computes required = all − skipped − held — without it a held step is logged as a dependency DEADLOCK, verified 2026-10-29) — net SLOC ≤ +10, compensated by Task 3's extraction
- Modify: `apps/api/src/domains/agents/models.py` (`held_plan`, `executed_drafts` declared; initial values)
- Modify: `apps/api/src/domains/agents/nodes/draft_sequence.py` (`draft_turn_reset()` resets both keys)
- Modify: `apps/api/src/domains/agents/nodes/routing.py` (`route_from_hitl_dispatch` → `NODE_TASK_ORCHESTRATOR` when a held step is resumable)
- Modify: `apps/api/src/domains/agents/graph.py` (mapping gains `NODE_TASK_ORCHESTRATOR`)
- Modify: `apps/api/src/domains/agents/nodes/task_orchestrator_node.py` (enters `resume_held_steps` when `held_plan` is set and the sequence settled)
- Modify: `apps/api/src/domains/agents/nodes/response_node.py` (lines 2077-2095, verified 2026-10-29): when the state carries `executed_drafts`, the node renders THOSE records (`render_execution_result` over each `to_agent_result()` dict, the same call as today) and executes nothing; and it COMPOSES them with the summary of the steps the resume ran (`held_plan["resumed"]`) instead of REPLACING the whole summary — today's replacement (« the user already saw intermediate results ») would drop the e-mail sent with the real link
- Modify: the response directives lines file that carries the failures directive (key `held_not_run`, rendered only when non-empty)
- Test: `apps/api/tests/unit/domains/agents/orchestration/test_held_steps.py`
- Test: `apps/api/tests/unit/domains/agents/orchestration/test_plan_resume.py`
- Test: `apps/api/tests/unit/domains/agents/nodes/test_response_reads_executed_drafts.py`
- Test: `apps/api/tests/unit/domains/agents/test_held_plan_state_roundtrip.py`
- Test: `apps/api/tests/integration/domains/agents/effects/test_plan_resume_db.py`

**Interfaces:**
- Produces (`held_steps.py`): `held_steps(plan: ExecutionPlan, pending: Mapping[str, list[str]]) -> dict[str, list[str]]` — `pending` maps a step id to its draft ids; returns every step whose parameters reference (via `for_each_utils.extract_step_references` over `json.dumps(step.parameters)`) a pending or held step, transitively, mapped to the draft ids it waits for. Ordering-only dependencies (`depends_on`, sequential chaining) never hold.
- Produces (`plan_resume.py`): `async resume_held_steps(state: MessagesState, config: RunnableConfig, run_id: str) -> dict[str, Any]` — executes the settled batch through `services/draft_executor.execute_draft_if_confirmed` (the one executor the response uses today), records `executed_drafts: {draft_id: result.to_agent_result()}` and clears `draft_action_result` (so the response executes nothing — the ledger would serve a record anyway, probe Hb), injects each confirmed-and-succeeded draft's result as its step's result in `completed_steps` — a TOOL_CALL replay through Task 3's `project_tool_result` (the tool's own `UnifiedToolOutput`, probe Hb showed the raw shape), a native draft through its `result_data` (top-level fields such as `event_id`, `calendar_draft_execution.py:141`) — drops held steps with a refused or failed blocker into `held_not_run`, and calls `execute_plan_parallel(..., initial_completed_steps=...)` for the rest. Returns the state update the orchestrator returns today, plus `held_plan` carrying `resumed: [step_id]`, cleared or carried for a new round.
- State: `held_plan: dict[str, Any] | None` (`{"plan_id": str, "held": {step_id: [draft_id]}, "resumed": [step_id]}`), `executed_drafts: dict[str, dict[str, Any]]` (values = `to_agent_result()` dicts, the shape the response renders).

- [ ] **Step 1: Write the failing tests** (probe « dependents », target form)
  - `test_data_reference_holds_ordering_does_not` — s2 references `$steps.s1.x` → held; s3 `depends_on=["s1"]` without reference → not held; s4 references s2 → held transitively; Jinja `{{ steps.s1.x }}` holds too.
  - `test_held_step_never_runs_on_a_placeholder` — the probe's chain on the real executor: s2 not executed, not failed, listed in `held_steps`.
  - `test_confirmed_blocker_resumes_with_the_real_result` — s1 confirmed: `resume_held_steps` executes s1 once, s2 receives the tool's own `deleted_id` (hypothesis Hc) through `$steps` and Jinja.
  - `test_refused_or_failed_blocker_leaves_the_step_unrun_and_said` — refused → `held_not_run` names s2; failed → same, with the failure through the ADR-303 channel.
  - `test_new_drafts_in_a_resume_start_a_new_round_and_each_step_runs_once`.
  - `test_response_executes_nothing_twice` — after a resume, the response node's draft path returns `executed_drafts` and the executor is not called (hypothesis Hb).
  - `test_response_composes_executed_drafts_with_resumed_results` — the summary holds the executed draft's card AND the resumed step's result; the pre-resume intermediate results stay out as today.
  - `test_held_step_inside_an_expanded_for_each_branch` — a FOR_EACH child referencing its drafted parent's result is held under its EXPANDED id; its siblings run.
  - `test_held_plan_round_trips` — msgpack checkpoint round-trip equality over both keys; `draft_turn_reset()` clears them.
  - Integration (PostgreSQL): a resumed plan replayed twice (node re-execution) leaves exactly one `agent_effects` row per act (hypothesis Hg, Review Focus 1).
- [ ] **Step 2: Run** the five files — Expected: FAIL.
- [ ] **Step 3: Implement** in the order of the Files list.
- [ ] **Step 4: Run** the five files + `task test:backend:agents` — Expected: PASS.
- [ ] **Step 5: Cold review + `task test:backend:unit:fast`;** ledger line.

### Task 5: ReAct asks on one predicate; admin iterative servers expanded (spec D8)

**Files:**
- Create: `apps/api/src/domains/agents/registry/confirmation_rule.py`
- Modify: `apps/api/src/domains/agents/services/react_tool_selector.py` (`_manifest_tools`, `_expand_iterative_user_mcp` → `_expand_iterative_mcp`)
- Test: `apps/api/tests/unit/domains/agents/services/test_react_confirmation_rule.py`

**Interfaces:**
- Produces: `requires_confirmation(manifest: ToolManifest) -> bool` = `bool(permissions and permissions.hitl_required) or manifest.mutation_policy == "confirm"`. Read for every manifest in `_manifest_tools`; for an expanded individual, read on its own manifest (personal: `ctx.reactive_tool_manifests`; admin: Task 2's store).
- Changes: expansion applies to any iterative task manifest (`delegates_execution`, origin user or admin) whose server is not an MCP App, under the existing `react_mcp_expand_iterative_enabled` flag.

- [ ] **Step 1: Write the failing tests** (probe H7, target form)
  - `test_standard_destructive_tool_is_asked_with_confirmation_off`.
  - `test_admin_iterative_server_is_expanded_and_its_destructive_tool_asked`.
  - `test_mcp_app_server_keeps_its_task_tool`.
  - `test_native_tools_unchanged` — a native read tool and a native `draft` tool keep their current `hitl` values (no native declares `confirm`).
  - `test_an_asked_call_is_ledgered_once_and_not_asked_twice` — `react_call_scope(approved=True)` → the gate LEDGERs, no draft.
- [ ] **Step 2: Run** — Expected: FAIL on the first two.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the file + `tests/unit/domains/agents/services/` — Expected: PASS.
- [ ] **Step 5: Cold review + `task test:backend:unit:fast`;** ledger line.

### Task 6: A routine may pre-approve servers (spec D9)

**Files:**
- Create: Alembic migration (`task db:migrate:create -- "scheduled actions mcp preapproved servers"`): `scheduled_actions.mcp_preapproved_servers` JSONB nullable
- Modify: `apps/api/src/domains/scheduled_actions/models.py` (`JSONB(none_as_null=True)`), `schemas.py` (create/update/response, strict validator), `service.py` (validates keys against the account's personal servers and the administrator servers not disabled for it), the REST router (routine form only)
- Create: `apps/api/src/domains/agents/effects/preapproval.py` (`ContextVar` + `is_preapproved(tool_name: str) -> bool`)
- Modify: `apps/api/src/infrastructure/scheduler/out_of_turn_run.py` (`StreamRequest.preapproved_mcp_servers: frozenset[str]`, published around the stream) and `scheduled_action_executor.py:645` (passes the routine's set)
- Modify: `apps/api/src/domains/agents/effects/gate.py` / `runtime.py` (unattended `confirm` + `is_preapproved` → approved scope, `approval_kind="routine_preapproval"`, `approval_ref` = routine id) and `nodes/react_call_execution.py::_approve` (same predicate before refusing)
- Modify: the agent routine tools' schemas (`tools/automation_tools.py`, `tools/application_routine_tools.py` / `RoutineUpdateRequest`) — the field absent; the confirmation card's rendering shows the stored value
- Create: `apps/web/src/components/settings/RoutineMcpPreapprovalField.tsx` (+ test), wired in `ScheduledActionsSettings.tsx`; keys in the six `apps/web/locales/*/translation.json`
- Test: `apps/api/tests/unit/domains/scheduled_actions/test_mcp_preapproval.py`, `apps/api/tests/unit/domains/agents/effects/test_routine_preapproval_gate.py`, `apps/api/tests/unit/domains/agents/tools/test_agent_cannot_preapprove.py`, `apps/api/tests/integration/domains/scheduled_actions/test_mcp_preapproval_db.py`, `apps/web/src/components/settings/__tests__/RoutineMcpPreapprovalField.test.tsx`

**Interfaces:**
- Produces: `is_preapproved(tool_name: str) -> bool` — true iff the run published a set and the tool's resolved manifest (`resolve_tool_manifest_named`) has an `mcp_server_key` in it.
- Produces: REST field `mcp_preapproved_servers: list[str] | None` on the routine's create/update/response schemas.

- [ ] **Step 1: Write the failing tests**
  - `test_preapproved_server_runs_its_confirm_tool_in_a_routine` — the effect row carries `approval_kind="routine_preapproval"` and the routine id.
  - `test_unlisted_server_is_still_refused_and_named`.
  - `test_react_routine_uses_the_same_predicate`.
  - `test_write_refuses_an_unknown_or_foreign_server_key` (400, translated) and reads a stored stale key forgivingly.
  - `test_agent_cannot_preapprove` — the agent tools' schemas have no such field; a Studio update draft never changes it; its card shows it (Review Focus 5).
  - `test_form_lists_exactly_what_the_routine_can_call` (hypothesis Hf) — frontend: personal enabled servers + admin servers not disabled; keyboard, accessible name, six locales.
  - Integration: `JSONB none_as_null` — a routine without pre-approval stores SQL NULL (`IS NULL` matches); migration replay.
- [ ] **Step 2: Run** — Expected: FAIL.
- [ ] **Step 3: Implement** in the order of the Files list.
- [ ] **Step 4: Run** the files, `task db:migrate:replay-check`, `task test:frontend` — Expected: PASS.
- [ ] **Step 5: Cold review + `task test:backend:unit:fast`;** ledger line.

### Task 7: Documentation and the full proof (spec D10, hypothesis Hd)

**Files:**
- Modify: `docs/architecture/ADR-263-Execution-Authority-Chain-And-Effect-Register.md` (amendment 2026-10-29), `docs/architecture/ADR-322-One-Clock-Per-Routine.md` (amendment), `docs/knowledge/11_mcp_servers.md` (target behaviour), the routines knowledge page, `docs/technical/` MCP page, FAQ « readable name / confirmation » and the MCP blog article in `apps/web/locales/*/translation.json`, CLAUDE.md (≤ 3 lines) + `task docs:sync-agents`

- [ ] **Step 1: Docs** as listed; `task lint:docs`, `task lint:i18n` — Expected: green (ADR-366 link findings excepted only while that file is unindexed, owned by another programme).
- [ ] **Step 2: Announce the budget** for the full-turn measure (Hd) and wait for the owner's go.
- [ ] **Step 3: Proof on Docker dev** (proof account `six-needs.proof@proof-lia.dev`, never the owner's): Pipeline turn over the in-process fake notes server — cards after the task, refusal and approval, a held step resumed with the real result; ReAct turn — in-loop question; routine with and without pre-approval; « Actions menées » rows; the final answer measured across five families (claims done / pending / refused stated) under the announced budget.
- [ ] **Step 4: Every gate:** `task lint`, `task test:backend:unit:fast`, `task test:backend:coverage`, `task test:backend:diff-coverage`, `task test:backend:agents`, `task test:backend:integration`, `task test:frontend:coverage`, `task test:e2e`, `task ci:fast` — record commands, exit codes, counts.
- [ ] **Step 5: Final whole-programme cold review;** ledger; report to the owner (no git action).
