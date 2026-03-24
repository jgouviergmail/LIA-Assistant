# LLM Provider Parameter Constraints

> Technical reference for LLM parameter support across all providers.
> Used by `adapter.py`, `responses_adapter.py`, and `AdminLLMConfigSection.tsx`.

## Quick Reference Matrix

| Provider | temperature | top_p | freq_penalty | pres_penalty | reasoning_effort | max_tokens param |
|----------|:-----------:|:-----:|:------------:|:------------:|:----------------:|:----------------:|
| **OpenAI standard** (gpt-4o, gpt-4.1, gpt-4.1-mini/nano) | 0-2.0 | ✅ | -2 to 2 | -2 to 2 | — | `max_tokens` |
| **OpenAI reasoning** (gpt-5, gpt-5-mini/nano, o-series) | ❌ | ❌ | ❌ | ❌ | ✅ (varies) | `max_completion_tokens` |
| **OpenAI gpt-5.1/5.2 + effort=none** | 0-2.0 | ✅ | ❌ | ❌ | ✅ (incl. `none`) | `max_completion_tokens` |
| **OpenAI gpt-5.4, gpt-5.4-mini** (reasoning + vision) | ❌ | ❌ | ❌ | ❌ | ✅⁵ | `max_completion_tokens` |
| **Anthropic** (Claude 3.5+, 4.x) | 0-1.0 | ❌¹ | ❌ | ❌ | ✅ → `effort` | `max_tokens` |
| **Gemini** (2.0-flash, 2.5-flash/pro) | 0-2.0 | ✅ | ❌ | ❌ | ✅ → `thinking_level`² | `max_output_tokens` |
| **DeepSeek chat** (V3) | 0-2.0 | ✅ | ✅ | ✅ | — | `max_tokens` (cap 8192) |
| **DeepSeek reasoner** (R1) | ❌ | ❌ | ❌ | ❌ | — | `max_tokens` (cap 64000) |
| **Perplexity** (sonar, sonar-pro) | 0-2.0 | ✅ | 1.0-2.0³ | -2 to 2 | — | `max_tokens` |
| **Ollama** | 0-2.0 | ✅ | ~⁴ | ~⁴ | — | `max_tokens` |

⁵ gpt-5.4/gpt-5.4-mini: `reasoning_effort` is **NOT** sent when function tools are present in `/v1/chat/completions` — the two are mutually exclusive. `ResponsesLLM` automatically omits `reasoning_effort` when tools are bound.

¹ Anthropic: `top_p` technically supported but mutually exclusive with `temperature` (Claude 4.5+ rejects both together). Our adapter drops `top_p` defensively.

² Gemini: `reasoning_effort` mapped to `thinking_level` (only `low`/`high`; `medium` → `low`). Only Gemini 2.5+ support thinking. Frontend exposes dropdown with `low`/`medium`/`high`.

³ Perplexity: `frequency_penalty` uses multiplicative range (1.0 = no penalty, 2.0 = maximum). Different semantics from OpenAI's additive range.

⁴ Ollama: `frequency_penalty`/`presence_penalty` mapped internally to `repeat_penalty`. Behavior is model-dependent.

---

## Detailed Provider Constraints

### OpenAI — Standard Models

**Models**: `gpt-4o`, `gpt-4o-mini`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4-turbo`

All sampling parameters are fully supported. No restrictions.

**Backend**: passes all parameters through `init_chat_model` or `ResponsesLLM`.

### OpenAI — Reasoning Models

**Models**: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-5.4`, `gpt-5.4-mini`, `o1`, `o1-mini`, `o3`, `o3-mini`, `o4-mini`

Detected by: `REASONING_MODELS_PATTERN = r"^(o[0-9](-.*)?|gpt-5([.-].*)?)$"`

| Parameter | Behavior |
|-----------|----------|
| `temperature` | Must be omitted or 1.0 — API rejects other values |
| `top_p` | Not supported — silently ignored or error |
| `frequency_penalty` | Not supported |
| `presence_penalty` | Not supported |
| `max_tokens` | Use `max_completion_tokens` (Chat Completions) or `max_output_tokens` (Responses API) |
| `reasoning_effort` | Supported with model-specific values (see table below) |

**reasoning_effort options by model:**

| Model | Supported values |
|-------|-----------------|
| `o1-mini` | — (not supported) |
| `o1`, `o3`, `o3-mini`, `o4-mini` | `low`, `medium`, `high` |
| `gpt-5`, `gpt-5-mini` | `minimal`, `low`, `medium`, `high` |
| `gpt-5-nano` | `minimal`, `low`, `medium`, `high` |
| `gpt-5.1` | `none`, `low`, `medium`, `high` |
| `gpt-5.2` | `none`, `minimal`, `low`, `medium`, `high`, `xhigh` |
| `gpt-5.4`, `gpt-5.4-mini` | `low`, `medium`, `high` (omitted when tools are present — see §gpt-5.4 constraint below) |

**Backend enforcement** (`responses_adapter.py`):
- `_is_reasoning_model()` — detects model family via `REASONING_MODELS_PATTERN` regex
- `_supports_sampling_params()` — returns `False` for reasoning models, **except** gpt-5.1/5.2+ with `reasoning_effort="none"`
- `is_responses_api_eligible()` — pattern-based check using `_RESPONSES_API_PATTERN = r"^(gpt-4\.1|gpt-5|o[1-9])"` (not a hardcoded list). All GPT-4.1+, GPT-5.x (including gpt-5.4), and o-series models are eligible; legacy models (gpt-4o, gpt-4-turbo, gpt-3.5) are not.
- Responses API path: temperature/top_p conditionally included via `_supports_sampling_params()`
- Chat Completions fallback: same conditional + `max_completion_tokens` always for reasoning models
- **Default reasoning_effort fallback**: If a reasoning model has no `reasoning_effort` configured (NULL in DB, absent from `LLM_DEFAULTS`), the adapter defaults to `"low"` across all 6 code paths (sync/streaming × Responses API/Chat Completions/Structured Output). This prevents models from consuming the entire output token budget on internal thinking and producing empty visible text. A structured log `reasoning_effort_defaulted` is emitted when this fallback activates
- **gpt-5.4+ tools guard**: `reasoning_effort` is omitted from Chat Completions requests when function tools are present (`has_tools` check in both sync and streaming paths)

**Backend enforcement** (`adapter.py`):
- `is_gpt51_plus_none` — inline check skips sampling param filtering for gpt-5.1+ with effort=none
- `temperature_override = "__OMIT__"` sentinel — removes temperature entirely for other reasoning models

### OpenAI — gpt-5.1/5.2 with effort=none

**Special case**: When `reasoning_effort="none"` is set on gpt-5.1 or gpt-5.2, the model disables its reasoning process and behaves like a standard model. In this mode:

- `temperature` and `top_p` become **available** again
- `frequency_penalty` and `presence_penalty` remain **unsupported**
- `max_completion_tokens` is still used (model family doesn't change)
- The `reasoning_effort="none"` value is explicitly sent to the API

**Frontend behavior**: The `getModelConstraints()` function accepts `reasoningEffort` as 3rd parameter. When `effort=none` is selected for gpt-5.1/5.2, temperature and top_p sliders dynamically appear.

**Frontend dropdown**: The reasoning_effort selector shows context-aware labels for the "unset" option:
- Models supporting `effort="none"` (gpt-5.1, gpt-5.2): displays "None (disabled)" — explicitly sends `none` to the API
- All other reasoning models (gpt-5, gpt-5-mini, o-series): displays "Default (model)" — sends NULL, backend defaults to `"low"`

**Tile display**: Shows `E:none + T:0.5` to indicate the hybrid state.

### OpenAI — gpt-5.4 / gpt-5.4-mini

**Models**: `gpt-5.4`, `gpt-5.4-mini`

These are reasoning models with **vision support** (image inputs accepted). They fall under `REASONING_MODELS_PATTERN` and behave like other gpt-5.x reasoning models, with one additional API-level constraint:

#### reasoning_effort + tools incompatibility

`gpt-5.4` and `gpt-5.4-mini` do **NOT** support `reasoning_effort` simultaneously with function tools in `/v1/chat/completions`. Sending both causes an API error.

**Backend enforcement** (`responses_adapter.py`):
- Both `_invoke_chat_completions()` and `_stream_chat_completions()` check `has_tools` before including `reasoning_effort`:
  ```python
  # IMPORTANT: gpt-5.4+ does NOT support reasoning_effort + function tools
  # in /v1/chat/completions — omit reasoning_effort when tools are present.
  if self._is_reasoning_model() and not has_tools:
      api_params["reasoning_effort"] = self.reasoning_effort or "low"
  ```
- This guard applies to **all** reasoning models (not only gpt-5.4) but is the primary motivation for the check.
- When `reasoning_effort` is omitted due to tools being present, no warning is logged — this is expected behaviour.

**Responses API path**: The Responses API does not have this restriction; `reasoning_effort` can coexist with tools. The constraint is specific to the `/v1/chat/completions` fallback path.

| Parameter | Behavior |
|-----------|----------|
| `temperature` | Not supported (reasoning model) |
| `top_p` | Not supported |
| `frequency_penalty` / `presence_penalty` | Not supported |
| `vision / image inputs` | **Supported** |
| `reasoning_effort` | Supported — omitted when tools are bound (Chat Completions only) |
| `max_tokens` | Use `max_completion_tokens` |

### Anthropic

**Models**: `claude-3-5-sonnet`, `claude-3-7-sonnet`, `claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`

| Parameter | Constraint |
|-----------|-----------|
| `temperature` | Range 0.0-1.0 (clamped server-side if > 1.0) |
| `top_p` | Supported by API but **removed** by adapter (mutual exclusion with temperature on Claude 4.5+) |
| `frequency_penalty` | Not supported — removed |
| `presence_penalty` | Not supported — removed |
| `reasoning_effort` | Mapped to Anthropic's native `effort` parameter: `low`/`medium`/`high` |

**Backend mapping** (`adapter.py` L651-670):
- `minimal` → `low`
- `low` → `low`
- `medium` → `medium`
- `high` → `high`
- `none` → ignored (not sent)

**Model-level thinking support**:
- `claude-3-5-sonnet`: **No** extended thinking — `effort` parameter NOT sent (backend guard + frontend hidden)
- `claude-3-7-sonnet`, `claude-opus-4`, `claude-sonnet-4`, `claude-haiku-4`: **Yes** — `effort` mapped from `reasoning_effort`

Anthropic also supports `budget_tokens` in the `thinking` block (separate from `effort`). Currently not exposed in admin UI.

### Gemini

**Models**: `gemini-2.0-flash`, `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3-pro-preview`

| Parameter | Constraint |
|-----------|-----------|
| `temperature` | Range 0.0-2.0 |
| `top_p` | Supported natively |
| `frequency_penalty` | Not supported — removed |
| `presence_penalty` | Not supported — removed |
| `reasoning_effort` | Mapped to `thinking_level`: `low`/`high` (only Gemini 2.5+ support thinking) |

**Backend mapping** (`adapter.py` L460-477):
- `minimal` → ignored
- `none` → ignored
- `low` → `low`
- `medium` → `low` (Gemini has no medium)
- `high` → `high`

**Model-level thinking support**:
- `gemini-2.0-flash`, `gemini-2.0-flash-lite`, `gemini-2.5-flash-lite`: **No** thinking — `thinking_level` NOT sent (backend guard + frontend hidden)
- `gemini-2.5-flash`, `gemini-2.5-pro`, `gemini-3-pro-preview`: **Yes** — `thinking_level` mapped from `reasoning_effort`

**Frontend**: Exposes reasoning_effort dropdown only for thinking-capable models. Note: `medium` is mapped to `low` by the backend since Gemini only supports two thinking levels.

### DeepSeek

**deepseek-chat (V3)**:
- All standard parameters supported
- `reasoning_effort` not applicable — removed
- `max_tokens` capped at 8192

**deepseek-reasoner (R1)**:
- Deterministic model — no sampling parameters
- `temperature`, `top_p`, `frequency_penalty`, `presence_penalty` all removed
- `reasoning_effort` not applicable — removed
- `max_tokens` capped at 64000
- Does NOT support tools or structured output

### Perplexity

**Models**: `sonar`, `sonar-pro`, `sonar-reasoning`, `sonar-reasoning-pro`

Uses OpenAI-compatible API (`base_url: https://api.perplexity.ai`).

| Parameter | Constraint |
|-----------|-----------|
| `temperature` | 0.0-2.0 (reduced effect on reasoning models) |
| `top_p` | Supported |
| `frequency_penalty` | Supported (range 1.0-2.0, multiplicative, NOT additive like OpenAI) |
| `presence_penalty` | Supported (range -2.0 to 2.0) |
| `reasoning_effort` | Not applicable — reasoning is model-intrinsic for sonar-reasoning variants |

### Ollama

Uses OpenAI-compatible API (custom `base_url`).

| Parameter | Constraint |
|-----------|-----------|
| `temperature` | Supported (passed to model options) |
| `top_p` | Supported |
| `frequency_penalty` | Partially supported (mapped to `repeat_penalty` internally) |
| `presence_penalty` | Partially supported (mapped internally, behavior model-dependent) |
| `reasoning_effort` | Not applicable |

---

## Implementation Files

| File | Role |
|------|------|
| [`adapter.py`](../../apps/api/src/infrastructure/llm/providers/adapter.py) | Main LLM factory — provider detection, constraint enforcement, Chat Completions |
| [`responses_adapter.py`](../../apps/api/src/infrastructure/llm/providers/responses_adapter.py) | OpenAI Responses API wrapper — `_is_reasoning_model()`, `_supports_sampling_params()` |
| [`constants.py`](../../apps/api/src/domains/llm_config/constants.py) | `LLM_DEFAULTS`, `REASONING_MODELS_PATTERN` |
| [`schemas.py`](../../apps/api/src/domains/llm_config/schemas.py) | Pydantic validation — `temperature: 0-2.0`, `reasoning_effort` Literal |
| [`AdminLLMConfigSection.tsx`](../../apps/web/src/components/settings/AdminLLMConfigSection.tsx) | Frontend constraints — `getModelConstraints()` |

## Key Patterns

### Adding a New Provider

1. Add constraint enforcement in `adapter.py` (`_prepare_provider_config` or dedicated method)
2. Add frontend constraints in `getModelConstraints()` switch case
3. Add provider to `LLMTypeConfigUpdate.provider` Literal in `schemas.py`
4. Update this document

### Adding a New Model Family

1. Check if it matches `REASONING_MODELS_PATTERN` — update regex if needed
2. If reasoning model with special modes (like gpt-5.1 effort=none), update:
   - `_supports_sampling_params()` in `responses_adapter.py`
   - `is_gpt51_plus_none` in `adapter.py`
   - `getModelConstraints()` in `AdminLLMConfigSection.tsx`
3. Update reasoning_effort options in frontend
4. Update this document
