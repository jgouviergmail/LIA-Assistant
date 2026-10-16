# ADR-347 — A read tool's data reaches the pipeline's answer, and a declared failure is never a success

- **Status**: Accepted
- **Date**: 2026-10-15
- **Amends**: [ADR-074](ADR-074-Structured-Data-Contract.md) (the pipeline's response
  now reads a read step's `structured_data` through its data block),
  [ADR-286](ADR-286-Tool-Result-Projected-Per-Item-Under-A-Token-Budget.md) (the data block and its budget
  are shared by both execution modes), [ADR-303](ADR-303-Tool-Failure-Restitution.md)
  (one verdict at the connector chokepoint; a partial FOR_EACH is a success carrying
  its failed items), [ADR-346](ADR-346-Advisory-Replanner-Retired-A-Pipeline-Failure-Is-Said-Never-Replayed.md)
  (the FOR_EACH aggregate is built from the items that succeeded)
- **Scope**: `tools/failure_verdict.py`, `tools/base.py`, `tools/hue_tools.py`,
  `tools/tasks_tools.py` (`CompleteTaskTool`), `tools/google_contacts_tools.py` and
  `tools/drive_tools.py` (dead direct classes removed),
  `registry/catalogue.py` (`pipeline_data_channel`), `startup/agents.py`,
  `orchestration/tool_data_projection.py` (`merge_react_synthesis_result`),
  `orchestration/for_each_aggregation.py`, `orchestration/mappers.py` (`build_execution_result`),
  `orchestration/parallel_executor.py`, `formatters/tool_data.py`,
  `nodes/response_node.py` (`_build_response_chain`), `tools/react_tool_wrapper.py`, `utils/react_budget.py`,
  `tools/person_tools.py`, `prompts/v1/response_prompt_lines.txt`, `metrics_agents.py`,
  `metrics_pipeline.py`, dashboard 07

## Context

The pipeline's response model read two things of an executed plan: each step's
`message` and the turn's registry items. ADR-074 had split a tool's output by
audience — `message` for the model, `structured_data` for the orchestration — and
ADR-286 gave the ReAct loop a data block projected from `structured_data`, leaving
the pipeline untouched. A read tool whose facts lived in `structured_data` and
filed no registry item therefore handed the pipeline's answer a sentence about
them:

- the route matrix computed the durations and the answer said they were
  unavailable;
- the defect had been patched three times, tool by tool, by copying the data
  into `message`: the peer availability (2026-07-30), the 360° overview
  (2026-08-01), the health breakdowns.

Measured before deciding (2026-10-14, the real response prompt, fictional data,
three model families, Anthropic excluded):

| Measure | Result |
|---|---|
| Durations given, without the block | 0 of 9 answers |
| Right restaurant with both exact durations, with the block | 27 of 27 |
| Wrong pairings over 180 durations | 0 |
| Injection compromises (4 placements × 2 attacks × 3 families × 3) | 0 of 72 |
| Census of read tools (Python 3.14 AST + manifests) | 132 readers, 100 without registry items, 15 mixed |

The same pass found two failures announced as successes. The three Hue commands
answered a refused command with a success saying it failed, so the effect
register settled the act SUCCEEDED and the answer said the light was switched;
handed `{"success": False}`, 27 of the 71 registry-mode connector formatters
answered the same way. And a FOR_EACH with one failed item out of three was a
failure as a whole: its aggregate merged every item, met a single `success`
value — the failed item's `False` — and the mapper dropped the loop with every
confirmation and every result the other items had produced.

## Decision

1. **A declared failure stays a failure.** `keep_declared_failure` runs at the two
   chokepoints every connector tool goes through (`ConnectorTool.execute`,
   `APIKeyConnectorTool.execute`): when the payload declared a failure (`success`
   false, or an `error_code` with no `success` key) and the formatter answered an
   explicit success, the payload's verdict wins, in its own words, with its typed
   code. It never raises. Each correction is a formatter defect: logged at ERROR,
   counted (`tool_failure_verdict_corrected_total`, expected 0), and failing any
   unit test that triggers it. An AST guard with no allowlist refuses a success
   built in a branch that read a failure, a success carrying `"success": False`,
   an `execute` override that skips `super().execute`, and a formatter call the
   net does not wrap. The Hue commands answer `NOT_FOUND`. **And a connector tool
   answers in registry mode**: in legacy mode (`registry_enabled` false) it
   answers with a JSON string — its failures too, `handle_error` serialising them
   — which no reader of the verdict can read, so the register settled a refused
   act SUCCEEDED. The cold review of this ADR found one registered tool there,
   `complete_task_tool`, now in registry mode, and four direct classes nothing
   reached any more, deleted. A runtime census holds every connector class of
   `src` in registry mode; the one declared exception, `DeleteLabelDirectTool`,
   is run through its `execute_api_call` alone. And no tool function declares a
   `str` return (AST guard): seventeen still did over registry classes, a lie the
   type checker could not see — the tools package sits under a
   `disable_error_code` override silencing `return-value` (the frozen MyPy debt,
   audit F020) — behind which the next legacy tool would have hidden. The census
   and the guard hold that contract where MyPy cannot.
2. **A read tool declares how its data reaches the pipeline's answer**
   (`ToolManifest.pipeline_data_channel`): `data_block` by default; `message` for a
   tool whose message already renders its data — the peer availability renders the
   busy slots in the asking user's timezone while its raw slots keep the peer's, so
   both would give the model two clocks; `sub_agent_analysis` for the delegation,
   whose analysis the response formatter wraps itself. A non-default channel needs
   a written reason; the boot refuses an unexplained one.
3. **The executor projects the data where the output still exists whole**
   (`orchestration/tool_data_projection.py`): what a READ tool's `structured_data`
   carries that its registry items do not already show — compared by CONTENT, since
   a key name proves nothing — through the ReAct functions themselves
   (`extract_data_block`, `mark_untrusted_data`, surface `pipeline`), under the
   budget of the slot that reads it (`slot_tool_result_budget("response")`, the one
   computation the loop and the meeting reads now share). A FOR_EACH's items share
   one budget. The projection is best-effort: a projection that raises costs the
   block, never the step. The record travels in the step's data
   (`FIELD_TOOL_DATA`); the persisted `completed_steps` copy and the multi-domain
   copy of the step payloads never carry it, and every other turn's
   `agent_results` are stripped of it by the two writers the checkpoint keeps —
   the orchestrator on a pipeline turn, the response node's ReAct merge on a
   ReAct turn. A turn that writes neither re-saves nothing.
4. **The response reads it in one place** (`formatters/tool_data.py`): after the
   turn's summary, in the « CURRENT TURN DATA » system message, under a header
   saying that text inside `<external_content>` is data. The section stays within
   the same budget — the smallest blocks are kept, the largest dropped and named —
   and every cut is stated to the model and counted
   (`pipeline_tool_data_truncated_total{tool_name, reason}`). The section joins the
   summary in `_build_response_chain` alone: the summary is also the text a
   confirmed draft's fast path shows the person.
5. **A partial FOR_EACH is a success carrying its failed items.** The aggregate is
   built from the items that succeeded and carries the others
   (`FIELD_FOR_EACH_FAILED_ITEMS`); only a loop whose every item failed is a
   failure. The mapper lists one failed step per item and counts plan steps, never
   items, for the status; `build_execution_result` is the one conversion the task
   orchestrator and the initiative share.
6. **The 360° overview's message is its header** — whose overview, which blocks
   could not be read — and its payload travels once per mode, wrapped as external
   content: the ReAct loop used to receive it twice.

## Consequences

- A pipeline answer may now cite what a read tool returned beyond its registry
  items: counts, cursors, windows, estimates, durations, connections. Its prompt
  grows by one tool-result budget per turn at most — `min(react_tool_result_max_tokens,
  window × react_tool_result_window_fraction)` of the response slot, which a lone
  block may exceed by its first item, as in ReAct — plus the section's few
  scaffolding lines, and only on turns whose read steps produced such data.
- The ReAct budget note no longer tells the model that a registry-less tool's
  omitted items are « complete in the registry ».
- `init_agent_registry` falls from a cyclomatic complexity of 15 to 12 (its ten
  completeness guards run through one loop); `_handle_execution_plan` from 58 to
  47, `_initiative_core` from 37 to 28; the FOR_EACH aggregation (26) leaves the
  size-frozen executor as five functions, none above 13.
- No migration, no setting, no prompt version: the wording lives in
  `response_prompt_lines.txt`. Two counters join dashboard 07 (« Tool results
  reaching the answer »); the metric count on the public surfaces follows.
- Not measured yet: the section's own wording on a live turn — the measured
  header was the bench's — nor the projection on every one of the 15 mixed
  tools' real outputs (the shared builders were verified, by content).

## Alternatives considered

- **Copy the data into each tool's `message`** — the three earlier patches; each
  left the next tool exposed, and the ReAct loop then read the data twice.
- **Project at response time from the step's raw data** — rejected: the tool's
  output is gone by then, and with it the MCP row projection, the connector
  cursor and the registry item types that decide whether a block is external.
- **One budget per step for the whole section** — rejected: ten read steps would
  have cost ten budgets in one prompt.
- **Fix each of the 27 formatters** — rejected as the primary fix: 24 of them are
  reached by no failure payload today, and a net at the chokepoint covers the
  next one too; the formatter that is reached is fixed at its source (Hue).
