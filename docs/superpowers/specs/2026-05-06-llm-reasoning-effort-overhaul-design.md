# LLM `reasoning_effort` overhaul — Design Specification

> **Status** : Approved (pending implementation)
> **Date** : 2026-05-06
> **Author** : LIA Team (jgouvier@gmail.com)
> **Scope** : Backend + Frontend + Database + Seeds + Migration
> **Implementation plan** : To be produced by `writing-plans` skill after spec approval.

---

## 1. Context & motivation

### 1.1 The triggering bug

A production user selected `reasoning_effort = "minimal"` for `gpt-5.2` in the
Configuration LLM admin UI. The value was offered by the dropdown, accepted by
the backend, persisted, and propagated to the API call — where the OpenAI API
rejected it (`gpt-5.2` does not support `minimal`, only `none / low / medium /
high / xhigh` per official model page).

### 1.2 Architectural diagnosis

Three structural problems compound:

1. **No source of truth for per-model reasoning options.** The list of accepted
   values per model is **hardcoded in TypeScript** in [`AdminLLMConfigSection.tsx::getModelConstraints()`](apps/web/src/components/settings/AdminLLMConfigSection.tsx),
   ~180 lines of regex on model name → string array. Drift from real API specs
   is invisible until production failure.
2. **Silent UI→API mappings spread across the backend.** `Gemini medium → low`,
   `Qwen low → 4096 budget tokens`, `DeepSeek V4 6-level UI → 2-level API`,
   `Anthropic effort → additional_kwargs` (which is the wrong LangChain field
   and is silently ignored). These coercions hide bugs and prevent the admin
   from knowing what the model actually receives.
3. **No backend validation of `reasoning_effort` against the model.** The
   service accepts any string. A bad value flows from admin UI → DB →
   `LLMConfigOverride` → adapter → external API call → 400 from provider.

### 1.3 Catalogue health audit (revealed during investigation)

- **5 sources of LLM configuration** discovered (`LLM_DEFAULTS`,
  `llm_config_seed.sql`, `llm_pricing_seed.sql`, runtime `LLMConfigOverride`,
  legacy Pydantic Settings).
- The `llm_config_seed.sql` already contains broken combinations (e.g.
  `vision_analysis` on `gpt-4.1-mini` with `reasoning_effort='low'` —
  `gpt-4.1-mini` is a non-reasoning model). Silently coerced today by the
  adapter; rejected once strict validation is in place.
- **7 fictional OpenAI model names** in the seed (`gpt-4.1-mini-mini` and
  variants — return 404 on every OpenAI documentation lookup, no community
  trace).
- **Anthropic catalogue contains** retired models (`claude-opus-3`,
  `claude-haiku-3`, `claude-sonnet-3-7`, etc.) and dash/dot duplicate entries
  (`claude-opus-4-5` ≡ `claude-opus-4.5`).

### 1.4 Goals

1. **One source of truth** for per-model reasoning capabilities, in the
   database, exposed via a single API contract.
2. **No silent mapping** between UI and API: the admin sees exactly what the
   API will accept (philosophy A — "raw truth").
3. **Strict backend validation**: any invalid `reasoning_effort` is rejected
   with HTTP 422 + structured error indicating allowed values.
4. **Catalogue cleanup**: remove fictional, retired, deprecated, and obsolete
   entries from DEV, PROD, and seeds.
5. **Per-widget UI**: dropdown for enum, numeric input for budget, toggle +
   numeric for hybrid — not "pretend it's a dropdown everywhere".
6. **No regression on existing functional behavior** for admin overrides that
   were already valid.

### 1.5 Non-goals

- Re-architecting the LLM type registry (`LLM_TYPES_REGISTRY`).
- Generalizing reasoning to non-LLM tooling (image gen, embeddings, TTS,
  audio, realtime models — explicitly classified as `kind ≠ chat` and
  excluded from reasoning UI).
- Custom UI for newer Anthropic features (`output_config.thinking` adaptive
  mode, custom budget for `thinking.budget_tokens > 0` on pre-4.5 models —
  the latter is moot after the aggressive Anthropic cleanup).
- I18n of the reasoning capability tooltip text (admin UI is intentionally
  English-only for these technical hints — consistent with non-translated
  LLM type names like `router`, `planner`, `response`).

---

## 2. Decisions

| # | Question | Decision |
|---|---|---|
| Q1 | UI philosophy | **A — raw truth**: dropdown shows exactly what the API accepts, no aliases |
| Q2 | Widget type per provider | **A3 — heterogeneous widgets**: enum dropdown / numeric budget / toggle+budget per model, dictated by API reality |
| Q3a | Anthropic cleanup scope | **Aggressive — modern only**: keep `claude-opus-4.5`, `claude-opus-4.6`, `claude-sonnet-4.6`, `claude-haiku-4.5`. Delete the other 17 entries (retired + deprecated + dash duplicates) |
| Q3b — fictionals | OpenAI fictional models | **Delete 7 entries** from `gpt-4.1-mini-mini*` family + `gpt-4.1-mini-{audio,realtime,search}-preview` (404 on OpenAI docs) |
| Q3b — duplicates | dash/dot duplicates | **Standardize on dot** (Anthropic official notation): delete the dash variants of remaining models |
| Q3b — non-chat | Non-chat models in `llm_models` | **Keep for pricing**, but **filter out of UI** via new `kind` enum column |
| Q4 | Validation policy | **Strict** — reject invalid values with HTTP 422 + structured error |
| Bonus | `is_image_model` field | **Delete** + introduce `required_kind` on `LLM_TYPES_REGISTRY` (cleaner, more general) |
| Bonus | `codex-mini-latest` | **Delete** (deprecated by OpenAI, only indirect signal for reasoning support) |
| Bonus | `gpt-5.3-chat-latest`, `computer-use-preview` | **`widget=none`** (truly UNVERIFIED after deep research) |
| Bonus | `gpt-5.2-chat-latest` | **`widget=enum, values=["medium"]`** (single forced option, mirrors `gpt-5-pro` pattern) |
| Bonus | Migration granularity | **One atomic Alembic migration** (rollback-safe) |
| Bonus | Downgrade policy | **Schema downgrade only**, deleted models NOT restored (admin re-seeds if needed). Documented in migration header |

---

## 3. Architecture

### 3.1 Component overview

```
┌─────────────────────────────────────────┐
│   llm_pricing_seed.sql (source of       │
│   truth: kind + reasoning_widget +      │
│   reasoning_enum_values + budget_range) │
└──────────────┬──────────────────────────┘
               │ INSERT at boot / migration
               ▼
┌─────────────────────────────────────────┐
│   llm_models (DB table)                 │  ◀── New columns:
│   row per model with full capabilities  │      kind, reasoning_widget,
└──────────────┬──────────────────────────┘      reasoning_enum_values,
               │ load_into                       reasoning_budget_range,
               ▼                                 reasoning_doc_i18n_key
┌─────────────────────────────────────────┐
│   ModelCapabilitiesCache (in-memory)    │
│   refreshed at boot + on admin update   │
└──────┬──────────────────┬───────────────┘
       │                  │
       │ via              │ via
       │ /llm-config/     │ direct read
       │ metadata API     │ in adapter.py
       ▼                  ▼
┌──────────────┐    ┌─────────────────────┐
│ Frontend     │    │ Backend adapters    │
│ ReasoningWidget   │ build LLM client    │
│ (3-shape UI) │    │ from validated cfg  │
└──────────────┘    └─────────────────────┘
       │                  │
       │ admin POST       │ runtime call
       ▼                  ▼
┌─────────────────────────────────────────┐
│   LLMConfigOverride (DB table)          │
│   reasoning_effort: JSONB               │
│   - {"effort": "high"}                  │
│   - {"budget": 16384}                   │
│   - {"enabled": true, "budget": 16384}  │
│   - null                                │
└─────────────────────────────────────────┘
       ▲
       │ before write: strict validation
       │ via _validate_reasoning_effort()
```

### 3.2 The 4 reasoning widget types

| Widget | When | UI rendering | Storage shape |
|---|---|---|---|
| `none` | Model doesn't support reasoning_effort, or UNVERIFIED | (hidden — section not rendered) | `null` |
| `enum` | API accepts a string enum (OpenAI o-series, gpt-5.x, Gemini 3.x, Anthropic 4.5+, DeepSeek V4, Perplexity sonar-deep-research, Ollama) | Dropdown with `enum_values` | `{"effort": "<string>"}` |
| `budget_int` | API accepts only an integer budget (Gemini 2.5) | Select with presets `Off / Dynamic / Custom` + numeric input when Custom | `{"budget": <int>}` |
| `toggle_budget` | API accepts boolean toggle + integer budget (Qwen3 hybrid) | Switch + conditional numeric input | `{"enabled": <bool>, "budget": <int|null>}` |

---

## 4. Data model

### 4.1 `llm_models` schema additions

[`apps/api/src/domains/llm/models.py`](apps/api/src/domains/llm/models.py)

```python
class LLMModelKindEnum(str, enum.Enum):
    chat = "chat"           # text chat-completions / responses
    image = "image"         # image generation
    audio = "audio"         # audio I/O via chat-completions
    realtime = "realtime"   # realtime API (voice agents)
    tts = "tts"             # text-to-speech only
    embedding = "embedding" # embeddings only

class LLMReasoningWidgetEnum(str, enum.Enum):
    none = "none"
    enum = "enum"
    budget_int = "budget_int"
    toggle_budget = "toggle_budget"

class LLMModel(Base, UUIDMixin, TimestampMixin):
    # ... existing fields unchanged ...

    # NEW: model classification
    kind: Mapped[LLMModelKindEnum] = mapped_column(
        SQLEnum(LLMModelKindEnum, name="llm_model_kind_enum", ...),
        nullable=False,
        default=LLMModelKindEnum.chat,
        comment="Model nature (chat / image / audio / realtime / tts / embedding)",
    )

    # NEW: reasoning UI driver
    reasoning_widget: Mapped[LLMReasoningWidgetEnum] = mapped_column(
        SQLEnum(LLMReasoningWidgetEnum, name="llm_reasoning_widget_enum", ...),
        nullable=False,
        default=LLMReasoningWidgetEnum.none,
        comment="UI widget shape for reasoning_effort selection",
    )

    # NEW: enum values when reasoning_widget == "enum" (NULL otherwise)
    reasoning_enum_values: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Ordered list of accepted reasoning_effort string values",
    )

    # NEW: numeric range when reasoning_widget in ("budget_int", "toggle_budget")
    reasoning_budget_range: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='{"min": int, "max": int, "off_sentinel": int|null, "dynamic_sentinel": int|null}',
    )

    # NEW: tooltip text key (English-only constant table on the frontend)
    reasoning_doc_i18n_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Frontend lookup key for English explanation of this model's reasoning shape",
    )
```

`is_reasoning_model` (existing column) is **kept**, derived from
`reasoning_widget != 'none'` at insert/update time. Used by other parts of the
runtime that don't care about widget specifics.

### 4.2 `llm_config_overrides.reasoning_effort` storage migration

Currently `Mapped[str | None]` (`String(20)`). Migrated to JSONB:

| Old value (str) | New value (JSONB) |
|---|---|
| `NULL` | `NULL` |
| `"minimal"` | `{"effort": "minimal"}` |
| `"low"` (any provider) | `{"effort": "low"}` for enum-widget models, **then cleaned to NULL** if invalid for the model |

Post-conversion, the validation step (Section 9.1 step 5 of `upgrade()`) sets
incompatible rows to `NULL` and logs a structured count.

---

## 5. API contract

### 5.1 Schema changes

[`apps/api/src/domains/llm_config/schemas.py`](apps/api/src/domains/llm_config/schemas.py)

```python
class ReasoningBudgetRange(BaseModel):
    min: int = Field(..., ge=0)
    max: int = Field(..., ge=0)
    off_sentinel: int | None = None
    dynamic_sentinel: int | None = None

class ModelCapabilities(BaseModel):
    model_id: str
    kind: Literal["chat", "image", "audio", "realtime", "tts", "embedding"]
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    is_reasoning_model: bool

    reasoning_widget: Literal["none", "enum", "budget_int", "toggle_budget"]
    reasoning_enum_values: list[str] | None = None
    reasoning_budget_range: ReasoningBudgetRange | None = None
    reasoning_doc_i18n_key: str | None = None

    cost_input: float | None = None
    cost_output: float | None = None
```

**`is_image_model: bool` is deleted** from this schema. Frontend usages (2
files) are migrated to `kind === "image"` in the same PR.

```python
# Discriminated union for reasoning_effort storage / validation
class ReasoningEffortEnum(BaseModel):
    effort: str

class ReasoningEffortBudget(BaseModel):
    budget: int = Field(..., ge=-1)  # -1 sentinel for "dynamic"

class ReasoningEffortToggleBudget(BaseModel):
    enabled: bool
    budget: int | None = Field(None, ge=0)

ReasoningEffortValue = (
    ReasoningEffortEnum
    | ReasoningEffortBudget
    | ReasoningEffortToggleBudget
    | None
)
```

`LLMTypeConfigUpdate.reasoning_effort` accepts `ReasoningEffortValue`.

### 5.2 Endpoint signature

`GET /llm-config/metadata` adds a query parameter:

```
GET /llm-config/metadata?kinds=chat                  # default
GET /llm-config/metadata?kinds=chat&capability=vision
GET /llm-config/metadata?kinds=image
GET /llm-config/metadata?kinds=chat,image,realtime
```

Default `kinds=chat`. The frontend `AdminLLMConfigSection` passes
`kinds={LLM_TYPES_REGISTRY[llm_type].required_kind}` based on the new
`required_kind: LLMModelKindEnum` field added to `LLMTypeMetadata`.

### 5.3 Strict validation error format (HTTP 422)

```json
{
  "detail": [
    {
      "type": "invalid_reasoning_effort",
      "loc": ["body", "reasoning_effort"],
      "msg": "Reasoning effort 'minimal' is not supported by gpt-5.2. Allowed values: none, low, medium, high, xhigh.",
      "input": "minimal",
      "ctx": {
        "model": "gpt-5.2",
        "provided": "minimal",
        "allowed": ["none", "low", "medium", "high", "xhigh"],
        "widget": "enum"
      }
    }
  ]
}
```

For `widget=budget_int` / `toggle_budget`, `ctx` contains
`range: {min, max, off_sentinel?, dynamic_sentinel?}` instead of `allowed`.

---

## 6. Frontend rendering

### 6.1 Deletions

- `getModelConstraints()` (~180 lines, regex-based) — **fully removed**.
- `OPENAI_REASONING_PATTERN`, `OPENAI_O1_MINI_PATTERN` — **removed**.
- `is_image_model` field — **removed** from TypeScript types
  (`types/llm-config.ts`, local replication in `AdminLLMConfigSection.tsx`).
- Filter lines `m.is_image_model` (lines 587-588) — **removed**, replaced
  by backend filtering via `?kinds=` query param.

### 6.2 New component

[`apps/web/src/components/settings/llm-config/ReasoningWidget.tsx`](apps/web/src/components/settings/llm-config/ReasoningWidget.tsx) (new file):

```tsx
type ReasoningWidgetType = 'none' | 'enum' | 'budget_int' | 'toggle_budget';

type ReasoningEffortValue =
  | { effort: string }
  | { budget: number }
  | { enabled: boolean; budget?: number }
  | null;

interface ReasoningWidgetProps {
  widget: ReasoningWidgetType;
  enumValues?: string[];
  budgetRange?: { min: number; max: number; off_sentinel?: number; dynamic_sentinel?: number };
  docI18nKey?: string;  // looked up in REASONING_DOC_TEXT (constant table, English-only)
  value: ReasoningEffortValue;
  onChange: (next: ReasoningEffortValue) => void;
  disabled?: boolean;
}
```

Dispatch by `widget`:

| `widget` | Render |
|---|---|
| `"none"` | Returns `null` — section hidden in dialog |
| `"enum"` | `<Select>` with `enumValues` options. Invalid current value → visible warning |
| `"budget_int"` | Preset `<Select>` (`Off` / `Dynamic` / `Custom`) + conditional `<input type=number>` clamped to range |
| `"toggle_budget"` | `<Switch>` "Enable thinking" + conditional `<input type=number>` for budget |

### 6.3 English documentation table

[`apps/web/src/components/settings/llm-config/reasoningDocText.ts`](apps/web/src/components/settings/llm-config/reasoningDocText.ts) (new file, constant only — no i18n keys):

```ts
export const REASONING_DOC_TEXT: Record<string, string> = {
  openai_o_series: "OpenAI o-series: low / medium / high. Cannot be disabled.",
  openai_gpt5: "GPT-5: minimal / low / medium / high (default medium).",
  openai_gpt5_pro: "GPT-5 Pro: reasoning is forced to high (no other value accepted).",
  openai_gpt5_1: "GPT-5.1: none / low / medium / high (default none).",
  openai_gpt5_2: "GPT-5.2: none / low / medium / high / xhigh. Note: minimal is NOT supported.",
  openai_gpt5_2_codex: "GPT-5.2 codex: low / medium / high / xhigh.",
  openai_gpt5_2_pro: "GPT-5.2 Pro: medium / high / xhigh.",
  openai_gpt5_2_chat_latest: "GPT-5.2 chat-latest: reasoning forced to medium (no admin control).",
  openai_gpt5_codex: "GPT-5 codex: low / medium / high.",
  openai_gpt5_3_codex: "GPT-5.3 codex: low / medium / high / xhigh.",
  openai_gpt5_4: "GPT-5.4: none / low / medium / high / xhigh.",
  openai_gpt5_4_mini: "GPT-5.4 mini: none / low / medium / high / xhigh.",
  openai_gpt5_codex: "GPT-5 codex: low / medium / high.",
  openai_gpt5_1_codex: "GPT-5.1 codex / codex-mini: low / medium / high.",
  openai_gpt5_1_codex_max: "GPT-5.1 codex-max: low / medium / high / xhigh.",
  gemini_2_5: "Gemini 2.5 Flash: thinking budget in tokens. 0 = off, -1 = auto, 1–24576 = custom.",
  gemini_2_5_lite: "Gemini 2.5 Flash Lite: thinking budget in tokens. 0 = off, -1 = auto, 512–24576.",
  gemini_2_5_pro: "Gemini 2.5 Pro: thinking budget in tokens, 128–32768. CANNOT be disabled.",
  gemini_3_x_flash: "Gemini 3.x Flash: minimal / low / medium / high.",
  gemini_3_x_pro: "Gemini 3.x Pro: low / medium / high (no minimal). CANNOT be disabled.",
  anthropic_4_5: "Claude Opus 4.5: low / medium / high effort enum.",
  anthropic_4_6: "Claude Opus 4.6: low / medium / high / max effort enum.",
  anthropic_sonnet_4_6: "Claude Sonnet 4.6: low / medium / high effort enum (max is Opus 4.6 only).",
  deepseek_v4: "DeepSeek V4: off / high / max. (low / medium are silently mapped to high by the API.)",
  qwen3_max: "Qwen3-max: hybrid thinking, disabled by default. Toggle on + budget in tokens (0–32768).",
  qwen3_5: "Qwen3.5 plus / flash: hybrid thinking, enabled by default. Toggle + budget in tokens (0–32768).",
  perplexity_deep: "Perplexity Sonar Deep Research: low / medium / high.",
};
```

### 6.4 Tile compact display

The compact tile (line 226 of `AdminLLMConfigSection.tsx`) reads
`caps.is_reasoning_model` + `caps.reasoning_widget` directly and formats:

```ts
formatReasoningValue(value, widget) =>
  widget === 'enum' ? value.effort
  : widget === 'budget_int' ?
      (value.budget === 0 ? 'off' :
       value.budget === -1 ? 'auto' :
       `${value.budget}t`)
  : widget === 'toggle_budget' ?
      (value.enabled ? `on/${value.budget ?? 'max'}` : 'off')
  : '-';
```

### 6.5 Client-side validation (defense in depth)

The widget refuses save (toast + disabled button) when:
- `enum`: `value.effort ∉ enumValues`
- `budget_int`: `value.budget` out of range AND not a sentinel
- `toggle_budget`: enabled with budget out of range

Backend re-validates strictly (Section 7.3) — no bypass possible.

### 6.6 Tests

`apps/web/src/components/settings/llm-config/ReasoningWidget.test.tsx`
(new file, Vitest):
- 4 widgets × valid + invalid + sentinels
- Transition (changing widget mid-edit resets value cleanly)
- Disabled state
- i18n doc text rendered correctly per `docI18nKey`

---

## 7. Backend validation

### 7.1 Coercion removal — runtime adapters

[`apps/api/src/infrastructure/llm/providers/adapter.py`](apps/api/src/infrastructure/llm/providers/adapter.py):

| Provider | Old behavior | New behavior |
|---|---|---|
| Gemini | `medium → low` (line 569) | **Removed**. UI never offers "medium" if invalid |
| DeepSeek V4 | 6→2 mapping (lines 437-450) | **Removed**. UI exposes only `off / high / max` |
| Qwen | enum→budget (lines 682-690) | **Removed**. Direct passthrough of `{enabled, budget}` |
| Anthropic | `additional_kwargs["effort"]` (line 836) | **Fixed**. `ChatAnthropic(effort=...)` constructor kwarg (verified mapping in `langchain_anthropic 1.3.5/chat_models.py:1186-1197` → maps to native `output_config.effort`) |
| OpenAI | passthrough | Unchanged shape, but fed by validated values only |
| Perplexity | not yet implemented for reasoning | New: passthrough enum for `sonar-deep-research` only |
| Ollama | passthrough | Unchanged |

### 7.2 Adapter shape per provider

Each provider gets a typed `_build_<provider>_reasoning(value: dict | None, model: str) -> dict` function. Returns kwargs to be merged into the LLM constructor (or `extra_body` where appropriate). Raises `RuntimeError` on shape mismatch (last-resort safety; should be unreachable thanks to N1+N2 validation).

### 7.3 Service-level validation (N2)

[`apps/api/src/domains/llm_config/service.py`](apps/api/src/domains/llm_config/service.py)::`upsert_override()` calls `_validate_reasoning_effort()` BEFORE the DB write. The function:

1. Looks up `caps = ModelCapabilitiesCache.get(model_name)`.
2. Dispatches by `caps.reasoning_widget`:
   - `none`: `reasoning_effort` must be `None`
   - `enum`: `value.effort` must be in `caps.reasoning_enum_values`
   - `budget_int`: `value.budget` must be in `[min, max]` OR equal a sentinel
   - `toggle_budget`: shape match; budget in range when enabled
3. Raises `HTTPException(422, ...)` with structured `ctx` per Section 5.3.

### 7.4 Boot-time validation (fail-fast)

[`apps/api/src/core/bootstrap.py`](apps/api/src/core/bootstrap.py) gains `validate_llm_defaults_against_matrix()`:

```python
async def validate_llm_defaults_against_matrix() -> None:
    """Sanity check: every LLM_DEFAULTS entry must be compatible with its
    model's reasoning_widget. Fail-fast at boot if any drift exists.
    """
    errors = []
    for llm_type, cfg in LLM_DEFAULTS.items():
        try:
            _validate_reasoning_effort_static(cfg.model, cfg.reasoning_effort)
        except ValueError as e:
            errors.append(f"  - {llm_type} → model={cfg.model}: {e}")
    if errors:
        raise RuntimeError(
            "LLM_DEFAULTS contains entries incompatible with the model "
            "catalogue:\n" + "\n".join(errors) + "\n"
            "Update LLM_DEFAULTS in apps/api/src/domains/llm_config/constants.py."
        )
```

Called in `main.py` lifespan startup, immediately after `ModelCapabilitiesCache.load()`. Aborts startup before the first request is served if a regression is introduced.

### 7.5 Backend tests

`apps/api/tests/unit/domains/llm_config/test_reasoning_validation.py` (new file):
- `@pytest.mark.parametrize` covering every reasoning model in the matrix × valid + invalid values
- ~50+ cases — includes the production-bug case (`gpt-5.2 + minimal → 422`)
- Validates the structured error `ctx` format

`apps/api/tests/unit/domains/llm_config/test_llm_defaults_compliance.py` (new file):
- Iterates over `LLM_DEFAULTS` at test-time
- Ensures every entry is compatible with the matrix (mirrors the boot-time check)
- CI fails before merge if a future `LLM_DEFAULTS` edit is incompatible

---

## 8. Seed strategy

### 8.1 Reasoning matrix — the canonical content

Below is the exhaustive matrix to embed in the migration AND in
`llm_pricing_seed.sql`. It is the single source of truth (after Section 8.2
deletions). Models present in the catalogue but not listed below default to
`kind=chat, reasoning_widget=none`.

#### OpenAI (52 entries kept after deletions)

| model_name | kind | widget | enum_values / range | doc_key |
|---|---|---|---|---|
| gpt-5 | chat | enum | `["minimal","low","medium","high"]` | `openai_gpt5` |
| gpt-5-mini | chat | enum | `["minimal","low","medium","high"]` | `openai_gpt5` |
| gpt-5-nano | chat | enum | `["minimal","low","medium","high"]` | `openai_gpt5` |
| gpt-5-pro | chat | enum | `["high"]` | `openai_gpt5_pro` |
| gpt-5-codex | chat | enum | `["low","medium","high"]` | `openai_gpt5_codex` |
| gpt-5-chat-latest | chat | none | — | — |
| gpt-5-search-api | chat | none | — | — |
| gpt-5.1 | chat | enum | `["none","low","medium","high"]` | `openai_gpt5_1` |
| gpt-5.1-codex | chat | enum | `["low","medium","high"]` | `openai_gpt5_1_codex` |
| gpt-5.1-codex-max | chat | enum | `["low","medium","high","xhigh"]` | `openai_gpt5_1_codex_max` |
| gpt-5.1-codex-mini | chat | enum | `["low","medium","high"]` | `openai_gpt5_1_codex` |
| gpt-5.1-chat-latest | chat | none | — | — |
| gpt-5.2 | chat | enum | `["none","low","medium","high","xhigh"]` | `openai_gpt5_2` |
| gpt-5.2-codex | chat | enum | `["low","medium","high","xhigh"]` | `openai_gpt5_2_codex` |
| gpt-5.2-pro | chat | enum | `["medium","high","xhigh"]` | `openai_gpt5_2_pro` |
| gpt-5.2-chat-latest | chat | enum | `["medium"]` | `openai_gpt5_2_chat_latest` |
| gpt-5.3-codex | chat | enum | `["low","medium","high","xhigh"]` | `openai_gpt5_3_codex` |
| gpt-5.3-chat-latest | chat | none | — | — |
| gpt-5.4 | chat | enum | `["none","low","medium","high","xhigh"]` | `openai_gpt5_4` |
| gpt-5.4-mini | chat | enum | `["none","low","medium","high","xhigh"]` | `openai_gpt5_4_mini` |
| o1 | chat | enum | `["low","medium","high"]` | `openai_o_series` |
| o1-mini | chat | none | — | — |
| o1-pro | chat | enum | `["low","medium","high"]` | `openai_o_series` |
| o3 | chat | enum | `["low","medium","high"]` | `openai_o_series` |
| o3-mini | chat | enum | `["low","medium","high"]` | `openai_o_series` |
| o3-pro | chat | enum | `["low","medium","high"]` | `openai_o_series` |
| o3-deep-research | chat | none | — | — |
| o4-mini | chat | enum | `["low","medium","high"]` | `openai_o_series` |
| o4-mini-deep-research | chat | none | — | — |
| gpt-4o, gpt-4o-2024-05-13, gpt-4o-mini | chat | none | — | — |
| gpt-4o-audio-preview, gpt-4o-mini-audio-preview | audio | none | — | — |
| gpt-4o-realtime-preview, gpt-4o-mini-realtime-preview | realtime | none | — | — |
| gpt-4o-search-preview, gpt-4o-mini-search-preview | chat | none | — | — |
| gpt-4.1, gpt-4.1-mini, gpt-4.1-nano | chat | none | — | — |
| gpt-realtime, gpt-realtime-1.5, gpt-realtime-mini | realtime | none | — | — |
| gpt-audio, gpt-audio-1.5, gpt-audio-mini | audio | none | — | — |
| computer-use-preview | chat | none | — | — |
| chatgpt-image-latest | image | none | — | — |
| text-embedding-3-large, text-embedding-3-small, text-embedding-ada-002 | embedding | none | — | — |

#### Anthropic (4 entries kept)

| model_name | kind | widget | enum_values | doc_key |
|---|---|---|---|---|
| claude-opus-4.5 | chat | enum | `["low","medium","high"]` | `anthropic_4_5` |
| claude-opus-4.6 | chat | enum | `["low","medium","high","max"]` | `anthropic_4_6` |
| claude-sonnet-4.6 | chat | enum | `["low","medium","high"]` | `anthropic_sonnet_4_6` |
| claude-haiku-4.5 | chat | none | — | — |

#### DeepSeek (4 entries)

| model_name | kind | widget | enum_values | doc_key |
|---|---|---|---|---|
| deepseek-chat | chat | none | — | — |
| deepseek-reasoner | chat | none | — | — (always-on, no level) |
| deepseek-v4-flash | chat | enum | `["off","high","max"]` | `deepseek_v4` |
| deepseek-v4-pro | chat | enum | `["off","high","max"]` | `deepseek_v4` |

#### Gemini (25 entries)

| model_name | kind | widget | enum_values / range | doc_key |
|---|---|---|---|---|
| gemini-2.0-flash, -001, -exp, -lite, -lite-001, -live-001 | chat | none | — | — |
| gemini-2.0-flash-preview-image-generation | image | none | — | — |
| gemini-2.5-flash | chat | budget_int | `{min:1, max:24576, off_sentinel:0, dynamic_sentinel:-1}` | `gemini_2_5` |
| gemini-2.5-flash-preview-09-2025 | chat | none | — | — (UNVERIFIED) |
| gemini-2.5-flash-lite | chat | budget_int | `{min:512, max:24576, off_sentinel:0, dynamic_sentinel:-1}` | `gemini_2_5_lite` |
| gemini-2.5-flash-lite-preview-09-2025 | chat | none | — | — (UNVERIFIED) |
| gemini-2.5-flash-image, -image-preview | image | none | — | — |
| gemini-2.5-flash-native-audio-preview-09-2025 | audio | none | — | — |
| gemini-2.5-flash-preview-tts, gemini-2.5-pro-preview-tts | tts | none | — | — |
| gemini-2.5-pro | chat | budget_int | `{min:128, max:32768, dynamic_sentinel:-1}` (no off_sentinel) | `gemini_2_5_pro` |
| gemini-3-flash-preview | chat | enum | `["minimal","low","medium","high"]` | `gemini_3_x_flash` |
| gemini-3-pro-preview | chat | enum | `["low","medium","high"]` | `gemini_3_x_pro` |
| gemini-3-pro-image-preview | image | none | — | — |
| gemini-3.1-flash-lite-preview | chat | enum | `["minimal","low","medium","high"]` | `gemini_3_x_flash` |
| gemini-3.1-pro-preview | chat | enum | `["low","medium","high"]` | `gemini_3_x_pro` |
| embedding-001, gemini-embedding-001, text-embedding-004 | embedding | none | — | — |

#### Qwen (4 entries)

| model_name | kind | widget | range | doc_key |
|---|---|---|---|---|
| qwen2.5 | chat | none | — | — |
| qwen3-max | chat | toggle_budget | `{min:0, max:32768}` (default disabled) | `qwen3_max` |
| qwen3.5-plus | chat | toggle_budget | `{min:0, max:32768}` (default enabled) | `qwen3_5` |
| qwen3.5-flash | chat | toggle_budget | `{min:0, max:32768}` (default enabled) | `qwen3_5` |

#### Perplexity (4 entries)

| model_name | kind | widget | enum_values | doc_key |
|---|---|---|---|---|
| sonar, sonar-pro, sonar-reasoning-pro | chat | none | — | — |
| sonar-deep-research | chat | enum | `["low","medium","high"]` | `perplexity_deep` |

#### Ollama (2 entries)

| model_name | kind | widget |
|---|---|---|
| llama3.2, mistral | chat | none |

### 8.2 Deletions list (25 models)

#### OpenAI (8)

Fictionals (404 on docs):
- `gpt-4.1-mini-mini`
- `gpt-4.1-mini-mini-audio-preview`
- `gpt-4.1-mini-mini-realtime-preview`
- `gpt-4.1-mini-mini-search-preview`
- `gpt-4.1-mini-realtime-preview`
- `gpt-4.1-mini-audio-preview`
- `gpt-4.1-mini-search-preview`

Deprecated:
- `codex-mini-latest`

#### Anthropic (17)

Retired:
- `claude-opus-3`, `claude-haiku-3`, `claude-haiku-3-5`, `claude-haiku-3.5`,
  `claude-3-5-haiku-latest`, `claude-sonnet-3-7`, `claude-sonnet-3.7`

Deprecated (retire 2026-06-15):
- `claude-opus-4`, `claude-sonnet-4`

Out of aggressive scope (no effort enum):
- `claude-opus-4-1`, `claude-opus-4.1`, `claude-sonnet-4-5`, `claude-sonnet-4.5`

Dash duplicates (kept dot variant):
- `claude-opus-4-5`, `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5`

### 8.3 `LLM_DEFAULTS` rewrites

[`apps/api/src/domains/llm_config/constants.py`](apps/api/src/domains/llm_config/constants.py)::`LLM_DEFAULTS` (~30 entries with reasoning_effort) get type migration `str | None → ReasoningEffortValue`. Conversion table for legacy values, **resolved per `(model, widget)` — Qwen rules take precedence on Qwen models**:

**For Qwen models (widget=`toggle_budget`):**

| Legacy `reasoning_effort` (str) | New value | Source |
|---|---|---|
| `"none"` | `{"enabled": false}` | preserves `enable_thinking=False` |
| `"minimal"` | `{"enabled": true, "budget": 2048}` | matches `adapter.py:683` |
| `"low"` | `{"enabled": true, "budget": 4096}` | matches `adapter.py:683` |
| `"medium"` | `{"enabled": true, "budget": 16384}` | matches `adapter.py:683` |
| `"high"` / `"xhigh"` | `{"enabled": true}` (no budget = model default max) | matches legacy "no budget passed" |

**For all other providers (widget=`enum`):**

| Legacy `reasoning_effort` (str) | New value | Condition |
|---|---|---|
| `"none"` | `None` | (`"none"` is enum value only on gpt-5.1/5.2/5.4 — keep as `{"effort": "none"}` for those) |
| `"minimal"`, `"low"`, `"medium"`, `"high"`, `"xhigh"` | `{"effort": "<value>"}` | if value ∈ `caps.reasoning_enum_values` for the target model |
| any value | `None` | if model has `widget=none` OR value not in `enum_values` (broken legacy default — option (a) acted) |

The Qwen mapping preserves runtime behavior identical to the legacy
[adapter.py:683](apps/api/src/infrastructure/llm/providers/adapter.py#L683)
`budget_mapping`.

### 8.4 `llm_config_seed.sql` rewrites

- All entries referencing deleted models → **removed**.
- All `reasoning_effort: VARCHAR` → JSONB `{"effort": "..."}` or `{"enabled": ..., "budget": ...}` per matrix.
- Broken combinations (e.g. `vision_analysis` + `gpt-4.1-mini` + `reasoning_effort='low'`) → `reasoning_effort = NULL` (model kept). Admin reconfigures via UI post-deploy.

### 8.5 `llm_pricing_seed.sql` rewrites

- INSERTs for the 25 deleted models → **removed**.
- 5 new columns (`kind`, `reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range`, `reasoning_doc_i18n_key`) populated per matrix on every INSERT.

---

## 9. Migration & rollout

### 9.1 One atomic Alembic migration

File: `apps/api/alembic/versions/2026_05_06_XXXX-llm_reasoning_overhaul.py`

```python
"""LLM reasoning_effort overhaul.

Schema:
    - Adds llm_models.kind, reasoning_widget, reasoning_enum_values,
      reasoning_budget_range, reasoning_doc_i18n_key.
    - Converts llm_config_overrides.reasoning_effort: VARCHAR(20) → JSONB.

Data:
    - Backfills new columns on existing rows from the embedded matrix
      (matches llm_pricing_seed.sql).
    - Cleans incompatible reasoning_effort values from llm_config_overrides
      to NULL (will be reconfigured by admin via UI post-deploy).
    - Deletes 25 obsolete model rows (and their pricing + override entries
      via FK-aware ordering).

Downgrade limitation:
    - Schema changes are reversible.
    - Deleted models are NOT restored. Re-running the seeds (or restoring
      from backup) is the only recovery path. Documented intentionally:
      none of the deleted models is in active use.
"""

revision = "..."
down_revision = "..."

def upgrade() -> None:
    # 1. Add new columns
    # 2. Backfill kind via regex on model_name
    # 3. Backfill reasoning_widget + values from REASONING_MATRIX (Python dict)
    # 4. ALTER llm_config_overrides.reasoning_effort TYPE jsonb USING ...
    # 5. UPDATE llm_config_overrides SET reasoning_effort = NULL WHERE invalid
    # 6. DELETE FROM llm_config_overrides WHERE model IN (DELETED_MODELS)
    # 7. DELETE FROM llm_model_pricing WHERE model_id IN (...)  -- FK RESTRICT order
    # 8. DELETE FROM llm_models WHERE model_name IN (DELETED_MODELS)
    # 9. ALTER COLUMN ... NOT NULL on new required columns

def downgrade() -> None:
    # Reverse JSONB → VARCHAR (extract effort)
    # Drop the 5 new columns
    # No restore of deleted models — see header
```

### 9.2 Rollout sequence

| Phase | Action | Validation |
|---|---|---|
| 1 | This spec doc — review + approval | User sign-off |
| 2 | Implementation plan via `writing-plans` skill | Plan reviewed |
| 3 | Single PR: backend + frontend + migration + seeds + tests + LLM_DEFAULTS | `task ci` complete |
| 4 | Migration tested on DEV copy: `alembic upgrade head` → smoke test → `alembic downgrade -1` → `alembic upgrade head` | Full round-trip clean |
| 5 | Visual frontend validation in Docker dev (all 4 widgets, all critical models) | Manual checklist |
| 6 | Merge → deploy DEV → admin reconfigures models via UI | `briefing_synthesis_*` style metrics monitored |
| 7 | Tag release → deploy PROD | Migration auto-applies; boot-time validation passes |
| 8 | Post-deploy: monitor `reasoning_effort_validation_rejected` Prometheus counter | Spike = UI/i18n issue, alert |

### 9.3 Risks & mitigations

| Risk | Likelihood | Mitigation |
|---|---|---|
| Migration data fails on PROD volume | low | Atomic transaction; tested on DEV copy first; rollback safe at schema level |
| Boot-time validation blocks startup | medium (intentional) | Fail-fast IS the goal. Structured logs make root cause obvious |
| Forgotten frontend usage of `getModelConstraints` | low | TypeScript compiler catches all references; exhaustive grep done in spec |
| UNVERIFIED model that should support reasoning, hidden from UI | low | Admin can still configure model without reasoning. Zero functional loss. Re-classification via future seed update |
| Cache stale post-migration | medium | `ModelCapabilitiesCache.refresh()` called at boot AND after every admin update + `LLMConfigOverrideCache.invalidate()` mirror |
| Admin loses an override after data cleanup (NULL) | medium | Logged structured event; admin reconfigures via UI (per Q3a/Q4 decision) |

---

## 10. Out of scope / future work

- Re-architecting `LLM_TYPES_REGISTRY` beyond the new `required_kind` field.
- Generalizing reasoning to non-LLM tooling (image gen UI, embeddings UI — kept on dedicated tables).
- Anthropic adaptive thinking mode (`thinking={type:"adaptive"}`) — not exposed in admin UI for now (only manual + effort enum). Future iteration.
- Anthropic `output_config.thinking.budget_tokens` numeric on pre-4.5 models — moot after aggressive scope cleanup.
- DeepSeek `low/medium → high` mapping recovery for backwards compatibility — abandoned by design (philosophy A).
- I18n of `REASONING_DOC_TEXT` — explicitly scoped out (English-only admin UI).
- Backlog : chat error message duplicate display bug (separate investigation, post-merge).

---

## 11. References

- Investigation transcript : conversation 2026-05-06 between user and assistant.
- OpenAI reasoning guide : https://developers.openai.com/api/docs/guides/reasoning
- OpenAI model pages : https://developers.openai.com/api/docs/models/{name}
- OpenAI compatibility matrix (community) : https://community.openai.com/t/request-for-compatibility-matrix-reasoning-effort-sampling-parameters-across-gpt-5-series/1371738
- Anthropic extended thinking : https://platform.claude.com/docs/en/docs/build-with-claude/extended-thinking
- Anthropic effort parameter : https://platform.claude.com/docs/en/build-with-claude/effort
- Anthropic models overview : https://platform.claude.com/docs/en/about-claude/models/overview
- DeepSeek thinking_mode : https://api-docs.deepseek.com/guides/thinking_mode
- DeepSeek V4 release notes : https://api-docs.deepseek.com/news/news260424
- Gemini thinking : https://ai.google.dev/gemini-api/docs/thinking
- Gemini 3 dev guide : https://ai.google.dev/gemini-api/docs/gemini-3
- Alibaba DashScope deep thinking : https://www.alibabacloud.com/help/en/model-studio/deep-thinking
- Perplexity API reference : https://docs.perplexity.ai/api-reference/chat-completions-post
- Perplexity changelog : https://docs.perplexity.ai/changelog/changelog
- Ollama OpenAI bridge : https://docs.ollama.com/openai
- Ollama API : https://github.com/ollama/ollama/blob/main/docs/api.md
- LangChain Anthropic source : `apps/api/.venv/Lib/site-packages/langchain_anthropic/chat_models.py:899-1197` (verified `effort` constructor → `output_config.effort` mapping)
