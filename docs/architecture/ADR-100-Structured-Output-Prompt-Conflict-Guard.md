# ADR-100: Native Structured Output vs "Output JSON" Prompt Conflict — Rescue Net + Prompt Convention

**Status**: ✅ IMPLEMENTED (2026-07-04)
**Author**: Claude Code (Fable 5)
**Related**: [ADR-084](ADR_INDEX.md) (Indexable vs Semantic), the Gemini 3.x list-content normalization (v1.20.13), [MESSAGE_WINDOWING_STRATEGY.md](../technical/MESSAGE_WINDOWING_STRATEGY.md)

## Context

A user request — "dessine moi le schema du cycle de l'eau" — that should have
produced an Excalidraw diagram instead hung ~2 minutes in "plan validation"
and then rendered a Google Map. The investigation surfaced five distinct
defects (D1–D5), one of which (D5) was a **systemic class**:

The semantic validator ran `get_structured_output()` (native, forced tool
call) against a versioned prompt that opened with **"Output JSON only."** plus
a ` ```json ` OUTPUT FORMAT block. On `deepseek-v4-flash` (reasoning OFF,
max_tokens 5000 — correctly configured) the model resolved the contradiction
between "call the tool" and "output JSON text" non-deterministically: **2 of 3
calls answered in raw JSON text**, so LangChain returned `None`, the helper
raised `StructuredOutputError`, and the validator failed **open** — the whole
semantic-validation layer was silently dead (100% failure over the observed
window), costing ~2.8 s per request and validating nothing. Ironically, a
working validator would have caught defect D2 (a plan whose `skill_name`
contradicted the request).

This is a class, not a one-off: any prompt that instructs JSON-text output
while the code forces a tool call is a latent, model-dependent failure.

## Decision

Two complementary guards.

### 1. Runtime rescue net (defense in depth)

`_get_native_structured_output` now invokes the buffered path through an
`include_raw=True` wrapper. When the model returns no parsed object but its
raw message carries a JSON object/array, `_rescue_structured_from_text`
salvages it (handles ` ```json ` fences, prose-embedded JSON, and Gemini 3.x
list-content via `coerce_content_to_text`) and logs
`structured_output_rescued_from_text`. If nothing is salvageable, the error
now carries the raw text (`raw_output`) for diagnosis instead of an opaque
"unexpected type". This protects **every** native structured-output consumer,
present and future, against the conflict — and against transient model
misbehavior.

### 2. Prompt convention (root cause)

Prompts consumed by native structured output MUST NOT instruct JSON-text
output. They state: *"Report your result exclusively through the structured
tool provided by the API — never answer in free text or raw JSON"*, and
describe field **semantics**, not a JSON shape. A full sweep of all versioned
prompts was performed:

- **Cleaned** (native structured output + conflicting instruction):
  `semantic_validator_prompt`, `memory_reference_extraction_prompt` (also had
  a bare-array example contradicting its `{references: [...]}` schema),
  `heartbeat_decision_prompt`, `hitl_classifier_prompt` (` ```json `
  OutputSchema). All four run on `deepseek-v4-flash`.
- **Left as-is** (legitimate — these parse JSON *manually* via
  `extract_json_from_llm_response` / `json.loads`, they do NOT use native
  structured output): `smart_planner_prompt`,
  `smart_planner_multi_domain_prompt`, `email_content_generation_prompt`,
  `email_subject_generation_prompt`, `skill_description_translation_prompt`.

The distinction is the parsing mechanism: **manual JSON parse → "output JSON"
is required; native `get_structured_output` → "output JSON" is a bug.**

## The other four defects (same incident, fixed in the same change)

- **D1 — MCP iterative step timeout too low.** `*_task` steps (MCP ReAct loop)
  were clamped by the generic 120 s ceiling; one diagram-generation LLM call
  alone takes ~105 s, so the agent was killed ~10 s from completion. Added a
  dedicated high-latency family in `_compute_step_timeout`
  (`mcp_react_step_timeout_seconds` 300 s floor /
  `mcp_react_step_max_timeout_seconds` 600 s ceiling) and raised the plan-wide
  soft budget 120 → 600 s so it dominates the longest step families.
- **D2 — Incoherent plan `skill_name`.** The planner LLM emitted
  `skill_name: interactive-map` for a diagram request whose steps targeted the
  Excalidraw MCP. `_resolve_plan_skill_name` now drops any `skill_name` that
  contradicts the authoritative QueryAnalyzer detection or is absent from the
  catalog; response_node then falls back to the detected skill.
- **D3 — Skill activation masking a failed plan.** When a plan totally fails,
  response_node no longer activates the plan's skill (which turned a timed-out
  action into a confident unrelated answer) — `_plan_execution_failed` gates it.
- **D4 — Dishonest replanner.** `RETRY_SAME` / `REPLAN_MODIFIED` were logged as
  if acted upon, but automatic recovery is not wired (TODOs); the branches also
  fabricated inline-French user messages that were never surfaced (dead code +
  i18n violation). Logs now state recovery is not wired; the dead messages and
  the misleading "Retrying" reasoning are removed/rephrased as assessments.

## Consequences

- The semantic validator works again (repro: 3/3 success after the prompt fix;
  it correctly rejects the incident plan). Memory-reference and HITL
  classification verified 3/3 each on the real model.
- New settings: `mcp_react_step_max_timeout_seconds` (+ raised defaults for the
  two existing timeouts). `.env.example` / `.env.prod.example` updated.
- The rescue net makes native structured output robust across all providers;
  the prompt convention prevents the wasteful text-answer path in the first
  place. New prompts on native structured output must follow the convention.
- No DB schema change, no migration.

## Validation (2026-07-04, dev container)

- Repro on real `deepseek-v4-flash`: validator 3/3, memory-reference 3/3, HITL
  3/3 — all SUCCESS, zero `None`.
- Unit: `_compute_step_timeout` MCP family (7 new), planner skill coherence (6),
  `_plan_execution_failed` (6), structured-output text-rescue (9). Broad suites:
  607 orchestration/planner + 412 validator/hitl/heartbeat/config, all green.
  Ruff / Black / mypy clean on all touched files.
- Live: API recreated with new env (floor 300 / ceiling 600 / plan budget 600),
  `_compute_step_timeout("excalidraw_task", …)` = 300/300/600.
