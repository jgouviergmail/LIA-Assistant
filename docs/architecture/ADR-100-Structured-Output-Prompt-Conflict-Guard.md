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

**Amendment 2026-09-20 — a call the PARSER refused is not « no call ».** The
rescue net read two shapes of a rejected tool call (a schema refusal, an answer
in text) and missed a third: a call whose ARGUMENTS are not valid JSON.
LangChain then files it under `invalid_tool_calls` with `tool_calls` empty, and
the door read « no tool call, empty answer » — a wrong diagnosis of a complete
answer (`finish_reason = tool_calls`, nothing truncated). Measured on
`deepseek-flash`: `"primary_domain": mcp`, a bare word where a string belongs,
on 11 then 14 of 24 query-analyzer replays on dev, and **4 of 26 query analyses
lost in 48 h of production** — every one of them a whole turn degraded to a
bare conversation, because the analyzer's fallback is `intent = conversation,
confidence = 0` and nothing retries. The repair is mechanical and structural
(ADR-184: what is mechanically repairable is repaired before validation):
`tool_call_rescue.quote_bare_values` quotes a bare token in VALUE position
outside any string, and nothing else moves — JSON's own literals, numbers, a
colon inside a string and a token not followed by the end of its value are
left alone. It runs AFTER ADR-275's truncation verdict and BEFORE the text
rescue, logs `structured_output_invalid_call_repaired`, and when it cannot
help the reason names the parser's verdict (« tool call arguments not valid
JSON (…) ») and the exception carries the refused arguments as `raw_output`.
Every native call now lands on ONE series,
`llm_structured_output_outcomes_total{provider, schema, outcome}` (`parsed`,
the three rescues, `truncated`, `rejected`), drawn on dashboard 05 — a rescue
is a repair, not a success, and 15 % of lost analyses had no series to show
them. Replayed through the door after the change: 24 of 24 analyses settled,
14 repaired.

**Amendment 2026-10-22 — one repair chain for every door, and an undeclared key
that says nothing.** « Every native call » was false: the net lived inside the
forced-tool call alone. A Claude that refuses a forced tool (thinking on, or a
generation that refuses forcing — ADR-306) has ONE door, the auto-tool call,
and that door validated the tool call raw: no repair, and no outcome on the
series. Read on production (read-only, seven days): the auto-tool door carried
about 1,100 structured calls against about 300 for the forced one, and its 7
refusals reached no dashboard — none of them mechanical (a value outside an
enum, a string where a list belongs, a missing required field), so they stay
refusals. Measured on dev the same day, on a real ReAct turn: Haiku 5.5 with
thinking answered a complete query analysis with `"source_quote_note": ""`
inside a requested outcome; `GoalRequirement` forbids extras, the analysis was
refused whole and the turn fell back to a bare conversation without its tools
(1 auto-tool call of 13 in that session). The new shape is structural
(ADR-184): on a model that FORBIDS extras, an undeclared key whose value is
null, blank or an empty collection is dropped, since nothing could read it; a
key that says something stays, because it may be a declared field misspelled
and dropping it would let a default replace what the model meant. It joins the
defaulted nulls as one walk, `drop_absent_values`, whose two counts are logged
on `structured_output_absent_values_dropped` (the outcome `nulls_defaulted`
became `absent_values_dropped`). The chain is ONE function,
`tool_call_rescue.repair_refused_answer` — absent values, bare words, an object
written as text — called by both native doors after ADR-275's verdict, and the
JSON-mode door repairs absent values too. The auto-tool door counts `parsed`,
its repairs and `truncated`; a miss is counted once, by whoever settles it (the
buffered fallback, or `rejected` on a Claude's last door), and its log line
names the schema paths, never a refused value. Logging that verdict on a second
door found a leak in it (ADR-317): a parser error with no « Received » verdict
was quoted whole — the first 120 characters of the model's arguments, at
WARNING. The function now quotes the parser's verdict or nothing, and is named
`refusal_verdict`: `rejection_reason` is the name of the words a person types
to reject a plan, and the log guard rightly read it that way. Measured on the real API after
the change: 40 query analyses on the dev slot, 40 settled through the
auto-tool door and counted, none needing a repair. Left out on purpose, and
provider-specific: Claude's strict tool use (`strict: true`, documented as
compatible with thinking) would constrain the auto-tool arguments at the
source; it must be measured on LIA's own schemas before it is trusted.

**Amendment 2026-10-23 — a failed call is said as itself, and retried by one
layer.** Production, 2026-10-22 20:35 UTC: a proactive discussion's context
call (`discussion_context`, a Claude that refuses a forced tool) met an HTTP
503 `overloaded_error` — two independent log lines with the provider's request
id, no incident on the vendor's status page. The auto-tool door caught it,
returned « nothing usable », and the caller raised « produced no valid tool
call »: the provider's error and its headers were gone, the outcome was counted
`rejected` as if the model had answered badly, and the discussion's backoff
(`retry_deadline`, ADR-360), which reads a 429 or a `Retry-After` through the
cause chain, read nothing. Reproduced offline on the real path against a local
fake of the API: a 503, a 529, a 500, a 429 and a refused connection all became
that same cause-less error; a 400 alone kept its class. The other doors already
chained their cause; the gap was the last door's `return None`. A failed CALL
is now `StructuredOutputCallError`, a `StructuredOutputError` subclass — so no
handler changes: every caller of the door, followed two to three levels up in
the syntax tree, catches the base class or `Exception` — raised `from` what the
call raised by the three doors where a call fails (auto-tool last door, forced
tool, JSON mode), built once (`call_failure`, after the deterministic-refusal
check) and counted `call_failed` by the native doors. The retry wrapper no
longer re-retries such a failure when the client retries by itself
(`client_retries_by_itself`, the public `max_retries` LangChain hands to the
vendor SDK): measured the same day, LIA's factory-built Anthropic and
OpenAI-wire clients already send three requests for one 503 (twice, with
backoff and `Retry-After`, as Anthropic's errors page documents), and the
wrapper's three immediate passes on top made it nine. An unusable ANSWER is
still the wrapper's to retry (it recovered three self-diagnoses in a week), and
a client with no retry of its own — Ollama, or a slot set to zero — keeps the
wrapper's loop as its only one. Left as measured, for decision: the discussion
phases switch the SDK's retries off on purpose (ADR-360) and hold a failed
call's upper bound as uncertain spend (1.32 USD of a 5 USD day for that 503);
the LangChain `ModelRetryMiddleware` that `base_agent_builder` installs retries
any exception on top of the SDK (its default `retry_on`, read, not simulated);
the ReAct node's stream-then-buffered fallback sends a second round (six
requests for one persistent 503, simulated).

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
