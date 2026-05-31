# ADR-087: Native ChatOpenAI + Config-Driven Per-Provider Reasoning Strategy

**Status**: ✅ ACCEPTED (2026-05-31)
**Deciders**: Engineering (LIA LLM infrastructure), `jgouviergmail`
**Related**: ADR-078 (LLM Catalogue DB Source of Truth), ADR-026 (LLM Model Selection)

---

## Context and Problem Statement

Two coupled problems surfaced while wiring **live reasoning streaming** (showing an
agent's chain-of-thought in the progress UI) across all configured providers.

**1. The custom `ResponsesLLM` was a maintenance liability.** LIA shipped a
~1800-line `BaseChatModel` subclass that reimplemented, by hand, OpenAI message
conversion, streaming, structured output, tool calling and usage extraction — a
workaround for gaps in `langchain-openai` circa v1.0.0. Those gaps are gone in
`langchain-openai >= 1.1`: native `ChatOpenAI(use_responses_api=True,
output_version="responses/v1")` provides Responses-API caching, multi-turn, native
tool calls, structured output, **reasoning-summary streaming** and standard
`usage_metadata`. The custom class was also effectively sync-only, which blocked
reasoning streaming on OpenAI entirely.

**2. Reasoning is not uniform across providers, and the API constraints are hard.**
Verified against provider docs (2026-05):

- **OpenAI** streams a reasoning summary only on *free-form* generation; a **forced**
  `tool_choice` (what `with_structured_output` does under the hood) suppresses it,
  and the streaming `json_schema` path rejects non-strict schemas (HTTP 400).
- **Anthropic** *rejects* a forced `tool_choice` whenever extended thinking is enabled
  (`400: "Thinking may not be enabled when tool_choice forces tool use."`), and
  forbids a custom `temperature`/`top_p` while thinking is on. Thinking shape is
  per-model: opus-4-6 / sonnet-4-6 use **adaptive** (`thinking={type:adaptive}` +
  `effort`); opus-4-5 / haiku-4-5 use **manual** (`thinking={type:enabled,
  budget_tokens}`).
- **DeepSeek V4** emits `reasoning_content` natively but rejects forced `tool_choice`
  under thinking (handled via the JSON-mode fallback).
- **Gemini** computes thoughts but omits them unless `include_thoughts=True`.

An earlier iteration injected `thinking`/`include_thoughts` at stream time via
`.bind()`. That was an injection: it overrode the admin's per-agent config and
surfaced a "reasoning" block for agents the user had not enabled reasoning on.

**Question**: How do we stream reasoning across providers without (a) maintaining a
bespoke OpenAI client, (b) breaking structured-output nodes on the providers whose
APIs reject a forced tool under reasoning, and (c) injecting a reasoning display the
admin did not configure?

---

## Decision

**1. Remove the custom `ResponsesLLM`; use native `ChatOpenAI`.** The only custom
code retained is `ChatOpenAICached` — a ~1-method subclass overriding
`_get_request_payload` to inject LIA's static-prefix `prompt_cache_key` (the one
optimisation langchain cannot derive on its own). If that optimisation is ever
dropped, the module collapses to a plain `ChatOpenAI`.

**2. Reasoning is config-driven, never injected.** Reasoning is enabled *solely* by
the per-model kwargs built in the factory (`reasoning_builders.build_*_reasoning`)
from the admin "Configuration LLM" matrix. `reasoning_stream` no longer binds any
`thinking`/`include_thoughts`; it only streams what the configured model already
emits. A reasoning block therefore appears **only** for agents the admin enabled it
on (gating by construction).

**3. Structured output uses an auto-tool path where a forced tool breaks.** When the
model is OpenAI-with-reasoning or Anthropic-with-thinking, `get_structured_output`
binds the schema as a tool with `tool_choice="auto"` (the only API-supported
combination) plus a one-line directive `SystemMessage`, then validates the tool-call
args into the schema. On OpenAI a missing tool call falls back to the buffered
forced-tool path; on Anthropic-with-thinking there is **no** forced-tool fallback
(it would 400) — a `StructuredOutputError` is raised instead.

**4. Anthropic sampling lock.** When reasoning enables thinking on Anthropic, the
admin UI locks `temperature`/`top_p`, the service forces them to `None`, and the
factory omits them at call time (defense in depth, three layers, all config-driven).

**5. A separate global `effort` for opus-4-5.** Anthropic `output_config.effort` is,
on opus-4-5 only, an orthogonal global token-spend control (distinct from the
thinking budget). Modeled as `llm_models.effort_values` +
`llm_config_overrides.effort` and exposed as an optional dropdown in Configuration
LLM. 4.6+ fold effort into their adaptive `reasoning_effort` enum and do not get this
separate field.

---

## Architecture

```
Configuration LLM (admin)  ->  llm_models matrix (reasoning_widget, effort_values)
                                      |
        get_llm(agent) --> reasoning_builders.build_{openai,anthropic,gemini,deepseek}_reasoning
                                      |  (per-model kwargs: thinking / effort / include_thoughts)
                                      v
                    ProviderAdapter.create_llm  -->  native ChatOpenAI / ChatAnthropic / ...
                                      |
   get_structured_output --> forced tool (default)  OR  auto-tool path
                                                         (OpenAI+reasoning, Anthropic+thinking)
                                      v
              reasoning_stream.stream_reasoning_events  (streams ONLY what the model emits)
```

---

## Consequences

### Positive

- ~1800 lines of bespoke OpenAI code deleted; behaviour now tracks `langchain-openai`.
- Live reasoning on the highest-latency paths (response synthesis, ReAct loop,
  planner) where it most helps perceived latency.
- No injection: reasoning display is gated by the admin config, per the product rule
  "show a thought only if there is one".
- Anthropic structured nodes no longer 400 under thinking.

### Negative / Trade-offs

- The auto-tool path prepends one `SystemMessage` (minor prompt-shape change vs the
  forced tool) and, under `tool_choice="auto"`, the model *could* decline the tool —
  mitigated by the directive and, on OpenAI, a buffered fallback; on Anthropic it
  fails loud.
- Structured-output nodes do not stream reasoning on Anthropic (forced/auto tool both
  suppress it there) — accepted, consistent with the provider's behaviour.
- `effort_values` is not exposed in the LLM Pricing CRUD (legacy opus-4-5 only) — a
  documented, assumed edge-case (recovery is a one-line SQL UPDATE).

---

## Alternatives Considered

- **Keep `ResponsesLLM`, add async streaming to it** — rejected: re-investing in a
  workaround the upstream library has obsoleted.
- **Inject `thinking` at stream time via `.bind()`** — rejected: overrides admin
  config and forces a reasoning display the user did not enable.
- **Disable thinking for structured nodes** — rejected: `.bind(thinking=disabled)`
  does not override construction (still 400s); and it would silently drop a
  capability the admin enabled.
- **Two-pass (free-form reason -> parse)** — rejected: doubles latency/tokens.

---

## References

- `apps/api/src/infrastructure/llm/providers/responses_adapter.py` (`ChatOpenAICached`, `create_responses_llm`)
- `apps/api/src/infrastructure/llm/providers/reasoning_builders.py` (`build_*_reasoning`)
- `apps/api/src/infrastructure/llm/structured_output.py` (`_structured_via_auto_tool`, `_anthropic_thinking_on`)
- `apps/api/src/infrastructure/llm/reasoning_stream.py` (no-injection streaming)
- `apps/api/alembic/versions/2026_05_31_0001-anthropic_thinking_config.py`, `…0002-anthropic_global_effort.py`
- `docs/technical/LLM_PROVIDER_CONSTRAINTS.md`
- Anthropic docs: extended-thinking, adaptive-thinking, effort (platform.claude.com, 2026-05)
- ADR-078 (LLM Catalogue DB Source of Truth)
