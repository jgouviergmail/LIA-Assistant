# LLM `reasoning_effort` Overhaul — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the regex-based, frontend-driven `reasoning_effort` UI with a DB-driven matrix exposing exactly what each model's API accepts; add strict backend validation; clean up 25 obsolete model entries from DB + seeds; preserve runtime behavior for valid configurations.

**Architecture:** New columns on `llm_models` (`kind`, `reasoning_widget`, `reasoning_enum_values`, `reasoning_budget_range`, `reasoning_doc_i18n_key`) become the single source of truth, exposed via `GET /llm-config/metadata` and consumed by a new `ReasoningWidget` React component. Backend validates strictly with HTTP 422 + structured error context. Migration is one atomic Alembic file; downgrade reverses schema only (deleted models not restored — documented).

**Tech Stack:** FastAPI 0.135+ • Pydantic v2 • SQLAlchemy 2.x • PostgreSQL JSONB • Alembic • React 19 • TypeScript 5 • Vitest • pytest • LangGraph 1.x • langchain-anthropic 1.3.5

**Spec reference:** [docs/superpowers/specs/2026-05-06-llm-reasoning-effort-overhaul-design.md](docs/superpowers/specs/2026-05-06-llm-reasoning-effort-overhaul-design.md)

---

## File Structure

### Files to create

| Path | Responsibility |
|---|---|
| `apps/api/alembic/versions/2026_05_06_XXXX-llm_reasoning_overhaul.py` | One atomic migration: schema + backfill + cleanup + deletions |
| `apps/api/src/domains/llm_config/reasoning_validation.py` | Strict service-level validation function (`_validate_reasoning_effort`) — used by service AND bootstrap |
| `apps/api/src/infrastructure/llm/providers/reasoning_builders.py` | Per-provider `_build_<provider>_reasoning(value, model)` translators (no coercion) |
| `apps/api/tests/unit/domains/llm_config/test_reasoning_validation.py` | Parametrized matrix: every reasoning model × valid/invalid values |
| `apps/api/tests/unit/domains/llm_config/test_llm_defaults_compliance.py` | LLM_DEFAULTS sanity check (mirrors boot-time validation) |
| `apps/web/src/components/settings/llm-config/ReasoningWidget.tsx` | React component dispatching by widget type (4 shapes) |
| `apps/web/src/components/settings/llm-config/reasoningDocText.ts` | English-only constant table (no i18n keys) |
| `apps/web/src/components/settings/llm-config/__tests__/ReasoningWidget.test.tsx` | Vitest tests for the 4 widget shapes |

### Files to modify

| Path | What |
|---|---|
| `apps/api/src/domains/llm/models.py` | Add `LLMModelKindEnum`, `LLMReasoningWidgetEnum`, 5 new columns on `LLMModel` |
| `apps/api/src/domains/llm_config/models.py` | Change `reasoning_effort` storage from `String(20)` to `JSONB` |
| `apps/api/src/domains/llm_config/schemas.py` | Add `ReasoningBudgetRange`, `ReasoningEffort{Enum,Budget,ToggleBudget}`, extend `ModelCapabilities`, **remove `is_image_model`** |
| `apps/api/src/domains/llm_config/service.py` | Wire `_validate_reasoning_effort` in `upsert_override`; remove obsolete `auto_clearing_reasoning_effort`; populate `kind` in `get_models_metadata` |
| `apps/api/src/domains/llm_config/router.py` | Add `?kinds=` query param to `/metadata` endpoint |
| `apps/api/src/domains/llm_config/constants.py` | Add `required_kind` to `LLMTypeMetadata`; rewrite `LLM_DEFAULTS` with new `ReasoningEffortValue` shape |
| `apps/api/src/core/llm_agent_config.py` | Change `reasoning_effort` from `str | None` to `ReasoningEffortValue` |
| `apps/api/src/core/bootstrap.py` | Add `validate_llm_defaults_against_matrix()`; call it in startup |
| `apps/api/src/main.py` | Wire bootstrap validation in lifespan after `ModelCapabilitiesCache.load()` |
| `apps/api/src/infrastructure/llm/factory.py` | Pass new reasoning kwargs from validated config |
| `apps/api/src/infrastructure/llm/providers/adapter.py` | Remove all 4 silent coercions (Gemini/DeepSeek/Qwen/Anthropic); delegate to `reasoning_builders.py` |
| `apps/api/src/infrastructure/llm/model_capabilities_cache.py` | Cache new `kind`/`reasoning_*` fields |
| `infrastructure/database/seeds/llm_pricing_seed.sql` | Delete 25 entries; add 5 new columns; populate matrix |
| `infrastructure/database/seeds/llm_config_seed.sql` | Delete invalid entries; convert to JSONB; clean broken combos |
| `apps/web/src/types/llm-config.ts` | Add `kind`, `reasoning_*` fields; remove `is_image_model`; add `required_kind` to `LLMTypeInfo` |
| `apps/web/src/components/settings/AdminLLMConfigSection.tsx` | Delete `getModelConstraints()` + regex consts; replace with `ReasoningWidget`; remove `is_image_model` filter (replaced by backend `?kinds=`) |
| `apps/web/src/hooks/useApiQuery.ts` (or call site) | Pass `kinds=` query param when fetching `/llm-config/metadata` |

### Files to delete

None — all changes are additive or in-place modifications. Deleted database rows happen via migration data, not file deletion.

---

## Phase 1 — Data model foundation

### Task 1: Add reasoning enums to llm/models.py

**Files:**
- Modify: `apps/api/src/domains/llm/models.py`

- [ ] **Step 1: Read current LLMProviderEnum and LLMModel class**

Run: `cat apps/api/src/domains/llm/models.py | head -100` to confirm current structure (already known from spec § 4.1).

- [ ] **Step 2: Add the two new enums above LLMModel class**

```python
class LLMModelKindEnum(str, enum.Enum):
    """Classifies a model's nature for UI filtering and capability surface.

    A given LLM type ('router', 'image_generation', ...) requires a specific
    kind via LLMTypeMetadata.required_kind. The Configuration LLM admin UI
    filters its model dropdown via the GET /llm-config/metadata?kinds= query
    parameter so the admin only sees models compatible with the LLM type
    being edited.
    """
    chat = "chat"
    image = "image"
    audio = "audio"
    realtime = "realtime"
    tts = "tts"
    embedding = "embedding"


class LLMReasoningWidgetEnum(str, enum.Enum):
    """Drives the frontend rendering of the reasoning_effort selector.

    Single source of truth: each row of llm_models declares which widget the
    Configuration LLM dialog must render for this model. The frontend has no
    regex / hardcoded list — it dispatches purely on this value.
    """
    none = "none"            # model does not accept reasoning_effort
    enum = "enum"            # API accepts a string enum (use reasoning_enum_values)
    budget_int = "budget_int"        # API accepts only a numeric budget (use reasoning_budget_range)
    toggle_budget = "toggle_budget"  # API accepts boolean toggle + numeric budget (Qwen3 hybrid)
```

- [ ] **Step 3: Add the 5 new columns to LLMModel after `is_reasoning_model`**

```python
    # NEW (2026-05-06): model classification + reasoning UI driver.
    # See docs/superpowers/specs/2026-05-06-llm-reasoning-effort-overhaul-design.md
    kind: Mapped[LLMModelKindEnum] = mapped_column(
        SQLEnum(
            LLMModelKindEnum,
            name="llm_model_kind_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=LLMModelKindEnum.chat,
        comment="Model nature (chat / image / audio / realtime / tts / embedding)",
    )

    reasoning_widget: Mapped[LLMReasoningWidgetEnum] = mapped_column(
        SQLEnum(
            LLMReasoningWidgetEnum,
            name="llm_reasoning_widget_enum",
            create_constraint=True,
            create_type=True,
            values_callable=lambda enum_cls: [m.value for m in enum_cls],
        ),
        nullable=False,
        default=LLMReasoningWidgetEnum.none,
        comment="UI widget shape for reasoning_effort selection",
    )

    reasoning_enum_values: Mapped[list[str] | None] = mapped_column(
        JSONB,
        nullable=True,
        comment="Ordered list of accepted reasoning_effort string values (when reasoning_widget='enum')",
    )

    reasoning_budget_range: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment='{"min":int,"max":int,"off_sentinel":int|null,"dynamic_sentinel":int|null} when reasoning_widget in ("budget_int","toggle_budget")',
    )

    reasoning_doc_i18n_key: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
        comment="Frontend lookup key in REASONING_DOC_TEXT constant table (English-only)",
    )
```

Add `from sqlalchemy.dialects.postgresql import JSONB` to imports if missing.

- [ ] **Step 4: Run mypy + ruff on the file**

Run from `apps/api/`:
```bash
.venv/Scripts/mypy src/domains/llm/models.py
.venv/Scripts/ruff check src/domains/llm/models.py
```
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/llm/models.py
git commit -m "feat(llm): add kind + reasoning_widget columns to LLMModel"
```

---

### Task 2: Switch llm_config_overrides.reasoning_effort to JSONB ORM-side

**Files:**
- Modify: `apps/api/src/domains/llm_config/models.py`

- [ ] **Step 1: Locate current reasoning_effort field declaration**

Run: `grep -n "reasoning_effort" apps/api/src/domains/llm_config/models.py`. Expected: one `Mapped[str | None]` declaration.

- [ ] **Step 2: Replace with JSONB**

```python
    reasoning_effort: Mapped[dict | None] = mapped_column(
        JSONB,
        nullable=True,
        comment=(
            "Reasoning effort override stored as JSONB. Discriminated by the "
            "associated model's reasoning_widget: "
            '{"effort": "<str>"} for widget=enum, '
            '{"budget": <int>} for widget=budget_int, '
            '{"enabled": <bool>, "budget": <int|null>} for widget=toggle_budget. '
            "NULL = no override (use LLM_DEFAULTS or model default)."
        ),
    )
```

Add JSONB import if not present.

- [ ] **Step 3: Run mypy**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/llm_config/models.py`
Expected: 0 errors.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/domains/llm_config/models.py
git commit -m "feat(llm-config): switch reasoning_effort to JSONB"
```

---

### Task 3: Add ReasoningEffortValue Pydantic types

**Files:**
- Modify: `apps/api/src/domains/llm_config/schemas.py`

- [ ] **Step 1: Add the discriminated union types above ModelCapabilities**

```python
# === Reasoning effort discriminated union ===
# Stored in LLMConfigOverride.reasoning_effort (JSONB) and in
# LLMAgentConfig.reasoning_effort (Pydantic). Shape is determined by the
# model's reasoning_widget on llm_models.
class ReasoningEffortEnum(BaseModel):
    """Used when the model's reasoning_widget == 'enum'."""
    model_config = ConfigDict(extra="forbid")
    effort: str


class ReasoningEffortBudget(BaseModel):
    """Used when the model's reasoning_widget == 'budget_int'."""
    model_config = ConfigDict(extra="forbid")
    budget: int = Field(..., ge=-1, description="-1 = dynamic, 0 = off (model-dependent), N = exact budget")


class ReasoningEffortToggleBudget(BaseModel):
    """Used when the model's reasoning_widget == 'toggle_budget' (Qwen3 hybrid)."""
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    budget: int | None = Field(None, ge=0, description="None = model default max")


ReasoningEffortValue = (
    ReasoningEffortEnum
    | ReasoningEffortBudget
    | ReasoningEffortToggleBudget
    | None
)


class ReasoningBudgetRange(BaseModel):
    """Numeric range for budget-based reasoning widgets."""
    model_config = ConfigDict(extra="forbid")
    min: int = Field(..., ge=0)
    max: int = Field(..., ge=0)
    off_sentinel: int | None = None
    dynamic_sentinel: int | None = None
```

- [ ] **Step 2: Modify ModelCapabilities — add new fields, remove is_image_model**

```python
class ModelCapabilities(BaseModel):
    """Capabilities metadata for a single model.

    Source of truth: llm_models DB row, exposed via GET /llm-config/metadata.
    """
    model_id: str
    kind: Literal["chat", "image", "audio", "realtime", "tts", "embedding"]
    max_output_tokens: int
    supports_tools: bool
    supports_structured_output: bool
    supports_vision: bool
    is_reasoning_model: bool

    # NEW (2026-05-06): reasoning UI driver
    reasoning_widget: Literal["none", "enum", "budget_int", "toggle_budget"]
    reasoning_enum_values: list[str] | None = None
    reasoning_budget_range: ReasoningBudgetRange | None = None
    reasoning_doc_i18n_key: str | None = None

    cost_input: float | None = None
    cost_output: float | None = None
```

Note the explicit removal of `is_image_model: bool = False`. The frontend usage is migrated in Task 19.

- [ ] **Step 3: Add `from typing import Literal` if missing; run mypy**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/llm_config/schemas.py`
Expected: 0 errors. If errors mention missing `Literal`, add the import.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/domains/llm_config/schemas.py
git commit -m "feat(llm-config): add ReasoningEffortValue + extend ModelCapabilities"
```

---

### Task 4: Update LLMAgentConfig.reasoning_effort type

**Files:**
- Modify: `apps/api/src/core/llm_agent_config.py`

- [ ] **Step 1: Read current LLMAgentConfig class**

Run: `cat apps/api/src/core/llm_agent_config.py`. Note current `reasoning_effort: str | None` field.

- [ ] **Step 2: Replace with new type**

```python
from src.domains.llm_config.schemas import ReasoningEffortValue

class LLMAgentConfig(BaseModel):
    # ... existing fields ...
    reasoning_effort: ReasoningEffortValue = None
```

- [ ] **Step 3: Add `Field(default=None, description=...)` if other fields use Field**

For consistency:
```python
reasoning_effort: ReasoningEffortValue = Field(
    default=None,
    description=(
        "Reasoning effort override. Shape depends on the model's "
        "reasoning_widget. None = no override (model default applies)."
    ),
)
```

- [ ] **Step 4: Run mypy on the entire api/src/**

Run: `cd apps/api && .venv/Scripts/mypy src/`
Expected: 0 errors. If existing call sites use `reasoning_effort` as str, **note them** for fix in Task 14 (LLM_DEFAULTS rewrite).

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/core/llm_agent_config.py
git commit -m "feat(llm-config): switch LLMAgentConfig.reasoning_effort to ReasoningEffortValue"
```

---

## Phase 2 — Backend validation

### Task 5: Reasoning validation module (TDD)

**Files:**
- Create: `apps/api/src/domains/llm_config/reasoning_validation.py`
- Create: `apps/api/tests/unit/domains/llm_config/test_reasoning_validation.py`

- [ ] **Step 1: Write failing test for widget=enum valid value**

```python
# tests/unit/domains/llm_config/test_reasoning_validation.py
import pytest
from fastapi import HTTPException

from src.domains.llm_config.reasoning_validation import validate_reasoning_effort
from src.domains.llm_config.schemas import (
    ReasoningEffortEnum,
    ReasoningEffortBudget,
    ReasoningEffortToggleBudget,
)


@pytest.fixture
def fake_caps_factory():
    """Builds an in-memory fake of ModelCapabilities for validation tests."""
    from types import SimpleNamespace

    def _make(**kwargs):
        defaults = {
            "model_id": "test-model",
            "reasoning_widget": "none",
            "reasoning_enum_values": None,
            "reasoning_budget_range": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)
    return _make


@pytest.mark.unit
def test_validate_enum_widget_accepts_value_in_list(fake_caps_factory):
    caps = fake_caps_factory(
        model_id="gpt-5.2",
        reasoning_widget="enum",
        reasoning_enum_values=["none", "low", "medium", "high", "xhigh"],
    )
    # Should not raise.
    validate_reasoning_effort(caps, ReasoningEffortEnum(effort="high"))


@pytest.mark.unit
def test_validate_enum_widget_rejects_value_not_in_list(fake_caps_factory):
    """Regression: gpt-5.2 + 'minimal' was the original prod bug."""
    caps = fake_caps_factory(
        model_id="gpt-5.2",
        reasoning_widget="enum",
        reasoning_enum_values=["none", "low", "medium", "high", "xhigh"],
    )
    with pytest.raises(HTTPException) as exc:
        validate_reasoning_effort(caps, ReasoningEffortEnum(effort="minimal"))
    assert exc.value.status_code == 422
    assert exc.value.detail["type"] == "invalid_reasoning_effort"
    assert exc.value.detail["ctx"]["model"] == "gpt-5.2"
    assert exc.value.detail["ctx"]["provided"] == "minimal"
    assert exc.value.detail["ctx"]["allowed"] == ["none", "low", "medium", "high", "xhigh"]
    assert exc.value.detail["ctx"]["widget"] == "enum"
    assert "gpt-5.2" in exc.value.detail["msg"]
    assert "minimal" in exc.value.detail["msg"]
```

- [ ] **Step 2: Run tests to verify they fail (module doesn't exist yet)**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_reasoning_validation.py -v --no-cov`
Expected: ImportError on `reasoning_validation` module.

- [ ] **Step 3: Create the validation module**

```python
# apps/api/src/domains/llm_config/reasoning_validation.py
"""Strict validation of reasoning_effort against a model's reasoning_widget.

Used by:
- LLMConfigService.upsert_override (admin API write path)
- bootstrap.validate_llm_defaults_against_matrix (boot-time fail-fast)

Raises HTTPException(422) with structured ctx so the frontend can surface
helpful "did you mean" hints in the error toast.
"""

from __future__ import annotations

from typing import Any, Protocol

from fastapi import HTTPException

from src.domains.llm_config.schemas import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
    ReasoningEffortValue,
)


class _CapsLike(Protocol):
    """Duck-typed model capabilities — allows fakes in tests."""

    model_id: str
    reasoning_widget: str
    reasoning_enum_values: list[str] | None
    reasoning_budget_range: dict | Any | None


def validate_reasoning_effort(
    caps: _CapsLike,
    value: ReasoningEffortValue,
) -> None:
    """Validate that `value` matches what `caps` accepts.

    Raises HTTPException(422) with structured detail when invalid.
    """
    widget = caps.reasoning_widget

    if widget == "none":
        if value is not None:
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "reasoning_not_supported",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} does not accept reasoning_effort. "
                        f"Set reasoning_effort to null."
                    ),
                    "input": _serialize(value),
                    "ctx": {"model": caps.model_id, "widget": "none"},
                },
            )
        return

    if widget == "enum":
        if not isinstance(value, ReasoningEffortEnum):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "wrong_reasoning_effort_shape",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} expects an enum value "
                        f'(shape: {{"effort": "<string>"}}).'
                    ),
                    "input": _serialize(value),
                    "ctx": {
                        "model": caps.model_id,
                        "widget": "enum",
                        "expected_shape": {"effort": "<str>"},
                    },
                },
            )
        allowed = caps.reasoning_enum_values or []
        if value.effort not in allowed:
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "invalid_reasoning_effort",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Reasoning effort {value.effort!r} is not supported by "
                        f"{caps.model_id}. Allowed values: {', '.join(allowed)}."
                    ),
                    "input": value.effort,
                    "ctx": {
                        "model": caps.model_id,
                        "provided": value.effort,
                        "allowed": list(allowed),
                        "widget": "enum",
                    },
                },
            )
        return

    if widget == "budget_int":
        if not isinstance(value, ReasoningEffortBudget):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "wrong_reasoning_effort_shape",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} expects a numeric budget "
                        f'(shape: {{"budget": <int>}}).'
                    ),
                    "input": _serialize(value),
                    "ctx": {
                        "model": caps.model_id,
                        "widget": "budget_int",
                        "expected_shape": {"budget": "<int>"},
                    },
                },
            )
        rng = caps.reasoning_budget_range or {}
        sentinels = {rng.get("off_sentinel"), rng.get("dynamic_sentinel")} - {None}
        if value.budget in sentinels:
            return
        lo = rng.get("min", 0)
        hi = rng.get("max", 0)
        if not (lo <= value.budget <= hi):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "invalid_reasoning_budget",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Reasoning budget {value.budget} for {caps.model_id} is "
                        f"out of range [{lo}, {hi}] and not a sentinel."
                    ),
                    "input": value.budget,
                    "ctx": {
                        "model": caps.model_id,
                        "provided": value.budget,
                        "range": {"min": lo, "max": hi},
                        "sentinels": sorted(sentinels),
                        "widget": "budget_int",
                    },
                },
            )
        return

    if widget == "toggle_budget":
        if not isinstance(value, ReasoningEffortToggleBudget):
            raise HTTPException(
                status_code=422,
                detail={
                    "type": "wrong_reasoning_effort_shape",
                    "loc": ["body", "reasoning_effort"],
                    "msg": (
                        f"Model {caps.model_id} expects a toggle+budget "
                        f'(shape: {{"enabled": <bool>, "budget": <int|null>}}).'
                    ),
                    "input": _serialize(value),
                    "ctx": {
                        "model": caps.model_id,
                        "widget": "toggle_budget",
                        "expected_shape": {"enabled": "<bool>", "budget": "<int|null>"},
                    },
                },
            )
        if value.enabled and value.budget is not None:
            rng = caps.reasoning_budget_range or {}
            lo = rng.get("min", 0)
            hi = rng.get("max", 0)
            if not (lo <= value.budget <= hi):
                raise HTTPException(
                    status_code=422,
                    detail={
                        "type": "invalid_reasoning_budget",
                        "loc": ["body", "reasoning_effort"],
                        "msg": (
                            f"Reasoning budget {value.budget} for {caps.model_id} "
                            f"is out of range [{lo}, {hi}]."
                        ),
                        "input": value.budget,
                        "ctx": {
                            "model": caps.model_id,
                            "provided": value.budget,
                            "range": {"min": lo, "max": hi},
                            "widget": "toggle_budget",
                        },
                    },
                )
        return

    # Unreachable when llm_models migration is in place.
    raise RuntimeError(f"Unknown reasoning_widget: {widget!r}")


def _serialize(value: ReasoningEffortValue) -> Any:
    if value is None:
        return None
    return value.model_dump()
```

- [ ] **Step 4: Run tests — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_reasoning_validation.py -v --no-cov`
Expected: 2/2 PASS.

- [ ] **Step 5: Add the full parametrized matrix test**

Append to the test file. **Cover the entire matrix from spec § 8.1**:

```python
@pytest.mark.unit
@pytest.mark.parametrize("model_name,widget,enum_values,range_,valid_cases,invalid_cases", [
    # OpenAI o-series
    ("o1", "enum", ["low", "medium", "high"], None,
     [{"effort": "low"}, {"effort": "medium"}, {"effort": "high"}],
     [{"effort": "minimal"}, {"effort": "none"}, {"effort": "xhigh"}]),
    ("o1-mini", "none", None, None, [None], [{"effort": "low"}]),
    ("o3-mini", "enum", ["low", "medium", "high"], None,
     [{"effort": "high"}], [{"effort": "minimal"}]),
    # GPT-5 family
    ("gpt-5", "enum", ["minimal", "low", "medium", "high"], None,
     [{"effort": "minimal"}, {"effort": "high"}],
     [{"effort": "none"}, {"effort": "xhigh"}]),
    ("gpt-5-pro", "enum", ["high"], None,
     [{"effort": "high"}], [{"effort": "low"}, {"effort": "medium"}]),
    # GPT-5.2 — the original prod-bug case
    ("gpt-5.2", "enum", ["none", "low", "medium", "high", "xhigh"], None,
     [{"effort": "none"}, {"effort": "xhigh"}],
     [{"effort": "minimal"}]),  # ← reproduces the prod bug
    ("gpt-5.2-pro", "enum", ["medium", "high", "xhigh"], None,
     [{"effort": "medium"}], [{"effort": "low"}, {"effort": "minimal"}]),
    ("gpt-5.2-chat-latest", "enum", ["medium"], None,
     [{"effort": "medium"}], [{"effort": "low"}, {"effort": "high"}]),
    # GPT-4 family
    ("gpt-4.1", "none", None, None, [None], [{"effort": "low"}]),
    ("gpt-4o", "none", None, None, [None], [{"effort": "low"}]),
    # Anthropic 4.5+
    ("claude-opus-4.5", "enum", ["low", "medium", "high"], None,
     [{"effort": "high"}], [{"effort": "max"}, {"effort": "minimal"}]),
    ("claude-opus-4.6", "enum", ["low", "medium", "high", "max"], None,
     [{"effort": "max"}], [{"effort": "xhigh"}]),
    ("claude-sonnet-4.6", "enum", ["low", "medium", "high"], None,
     [{"effort": "high"}], [{"effort": "max"}]),
    ("claude-haiku-4.5", "none", None, None, [None], [{"effort": "low"}]),
    # DeepSeek V4
    ("deepseek-v4-flash", "enum", ["off", "high", "max"], None,
     [{"effort": "off"}, {"effort": "max"}],
     [{"effort": "low"}, {"effort": "medium"}, {"effort": "minimal"}]),
    # Gemini 2.5 (budget_int)
    ("gemini-2.5-flash", "budget_int", None,
     {"min": 1, "max": 24576, "off_sentinel": 0, "dynamic_sentinel": -1},
     [{"budget": 0}, {"budget": -1}, {"budget": 16384}, {"budget": 24576}],
     [{"budget": 24577}, {"budget": -2}, {"budget": -100}]),
    ("gemini-2.5-pro", "budget_int", None,
     {"min": 128, "max": 32768, "dynamic_sentinel": -1},
     [{"budget": -1}, {"budget": 128}, {"budget": 32768}],
     [{"budget": 0}, {"budget": 127}, {"budget": 32769}]),
    # Gemini 3.x (enum)
    ("gemini-3-pro-preview", "enum", ["low", "medium", "high"], None,
     [{"effort": "high"}], [{"effort": "minimal"}]),
    ("gemini-3-flash-preview", "enum", ["minimal", "low", "medium", "high"], None,
     [{"effort": "minimal"}], [{"effort": "xhigh"}]),
    # Qwen3 (toggle_budget)
    ("qwen3.5-plus", "toggle_budget", None, {"min": 0, "max": 32768},
     [{"enabled": False}, {"enabled": True, "budget": 4096},
      {"enabled": True, "budget": None}],
     [{"enabled": True, "budget": 32769}]),
    # Perplexity
    ("sonar-deep-research", "enum", ["low", "medium", "high"], None,
     [{"effort": "low"}], [{"effort": "minimal"}]),
    ("sonar-pro", "none", None, None, [None], [{"effort": "low"}]),
])
def test_validate_matrix(model_name, widget, enum_values, range_, valid_cases, invalid_cases, fake_caps_factory):
    """Exhaustive matrix per spec § 8.1. The original prod bug is at gpt-5.2."""
    caps = fake_caps_factory(
        model_id=model_name,
        reasoning_widget=widget,
        reasoning_enum_values=enum_values,
        reasoning_budget_range=range_,
    )

    for case in valid_cases:
        validate_reasoning_effort(caps, _build_value(case))

    for case in invalid_cases:
        with pytest.raises(HTTPException) as exc:
            validate_reasoning_effort(caps, _build_value(case))
        assert exc.value.status_code == 422
        assert exc.value.detail["ctx"]["model"] == model_name


def _build_value(case):
    if case is None:
        return None
    if "effort" in case:
        return ReasoningEffortEnum(**case)
    if "enabled" in case:
        return ReasoningEffortToggleBudget(**case)
    if "budget" in case:
        return ReasoningEffortBudget(**case)
    raise ValueError(f"Cannot infer shape from {case}")
```

- [ ] **Step 6: Run all matrix tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_reasoning_validation.py -v --no-cov`
Expected: All cases pass (~30+ parametrized cases).

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/domains/llm_config/reasoning_validation.py apps/api/tests/unit/domains/llm_config/test_reasoning_validation.py
git commit -m "feat(llm-config): strict reasoning_effort validation with matrix tests"
```

---

### Task 6: Wire validation into LLMConfigService

**Files:**
- Modify: `apps/api/src/domains/llm_config/service.py`

- [ ] **Step 1: Locate `upsert_override` method**

Run: `grep -n "def upsert_override" apps/api/src/domains/llm_config/service.py`. Note its current `auto_clearing_reasoning_effort` block (lines ~263-289 from spec investigation).

- [ ] **Step 2: Remove old auto-clearing logic and add new validation call**

Replace the `auto_clearing_reasoning_effort` block. Before the DB write, add:

```python
from src.domains.llm_config.reasoning_validation import validate_reasoning_effort
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

# ... inside upsert_override(), AFTER target.model is finalized ...

if target.model:
    caps = ModelCapabilitiesCache.get(target.model)
    if caps is None:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=422,
            detail={
                "type": "unknown_model",
                "msg": f"Model {target.model!r} is not in the catalogue.",
                "ctx": {"model": target.model},
            },
        )
    validate_reasoning_effort(caps, target.reasoning_effort)
```

The old regex-based auto-clearing block is **deleted entirely** — the new validation handles the same case (widget=none rejecting non-null) plus catches all other invalid combinations.

- [ ] **Step 3: Run existing service tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/ -v --no-cov`
Expected: existing tests pass; new validation tests pass.

- [ ] **Step 4: Add integration test for upsert path**

Append to `tests/unit/domains/llm_config/test_service.py` (or create if absent):

```python
@pytest.mark.unit
@pytest.mark.asyncio
async def test_upsert_override_rejects_invalid_reasoning_effort(...):
    """End-to-end: upsert with gpt-5.2 + minimal must raise 422."""
    # ... mock ModelCapabilitiesCache with gpt-5.2 caps ...
    # ... call service.upsert_override(... reasoning_effort={"effort":"minimal"}) ...
    # ... assert HTTPException(422) ...
```

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/llm_config/service.py apps/api/tests/unit/domains/llm_config/test_service.py
git commit -m "feat(llm-config): wire strict validation in upsert_override"
```

---

### Task 7: Per-provider reasoning builders (TDD)

**Files:**
- Create: `apps/api/src/infrastructure/llm/providers/reasoning_builders.py`
- Create: `apps/api/tests/unit/infrastructure/llm/providers/test_reasoning_builders.py`
- Modify: `apps/api/src/infrastructure/llm/providers/adapter.py` (delete old coercions)

- [ ] **Step 1: Write failing tests for each provider's builder**

Create test file with 7 tests, one per provider. Verify:
- OpenAI enum → `{"reasoning_effort": "high"}`
- Anthropic enum → `{"effort": "high"}` (constructor kwarg, NOT additional_kwargs — verified spec § 7.1)
- DeepSeek V4 `{"effort": "off"}` → `{"extra_body": {"thinking": {"type": "disabled"}}}`
- DeepSeek V4 `{"effort": "high"}` → `{"extra_body": {"thinking": {"type": "enabled"}}, "reasoning_effort": "high"}`
- Gemini budget_int → `{"thinking_budget": 16384}`
- Qwen toggle_budget → `{"extra_body": {"enable_thinking": true, "thinking_budget": 4096}}`
- Perplexity enum → `{"reasoning_effort": "low"}`

(Full test code body — for brevity, follow same TDD pattern as Task 5 step 1.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/providers/test_reasoning_builders.py -v --no-cov`
Expected: ImportError.

- [ ] **Step 3: Create reasoning_builders.py**

```python
"""Per-provider translators from validated ReasoningEffortValue to provider
constructor kwargs. NO coercion — validation already happened upstream
(N1+N2). Any shape mismatch here is a bug elsewhere; raise RuntimeError.
"""

from __future__ import annotations

from typing import Any

from src.domains.llm_config.schemas import (
    ReasoningEffortBudget,
    ReasoningEffortEnum,
    ReasoningEffortToggleBudget,
    ReasoningEffortValue,
)


def build_openai_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(f"OpenAI {model}: expected enum, got {type(value).__name__}")
    return {"reasoning_effort": value.effort}


def build_anthropic_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Returns ChatAnthropic constructor kwargs.
    Verified: langchain-anthropic 1.3.5/chat_models.py:1186-1197 maps the
    `effort` constructor kwarg to native output_config.effort.
    """
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(f"Anthropic {model}: expected enum, got {type(value).__name__}")
    return {"effort": value.effort}


def build_deepseek_v4_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Maps {off, high, max} → DeepSeek API shape."""
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(f"DeepSeek V4 {model}: expected enum, got {type(value).__name__}")
    if value.effort == "off":
        return {"extra_body": {"thinking": {"type": "disabled"}}}
    return {
        "extra_body": {"thinking": {"type": "enabled"}},
        "reasoning_effort": value.effort,  # "high" or "max"
    }


def build_gemini_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    """Gemini 2.5 = budget_int; Gemini 3.x = enum (thinking_level)."""
    if value is None:
        return {}
    if isinstance(value, ReasoningEffortBudget):
        return {"thinking_budget": value.budget}
    if isinstance(value, ReasoningEffortEnum):
        return {"thinking_level": value.effort}
    raise RuntimeError(f"Gemini {model}: unexpected shape {type(value).__name__}")


def build_qwen_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortToggleBudget):
        raise RuntimeError(f"Qwen {model}: expected toggle_budget, got {type(value).__name__}")
    extra: dict[str, Any] = {"enable_thinking": value.enabled}
    if value.enabled and value.budget is not None:
        extra["thinking_budget"] = value.budget
    return {"extra_body": extra}


def build_perplexity_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(f"Perplexity {model}: expected enum, got {type(value).__name__}")
    return {"reasoning_effort": value.effort}


def build_ollama_reasoning(value: ReasoningEffortValue, model: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, ReasoningEffortEnum):
        raise RuntimeError(f"Ollama {model}: expected enum, got {type(value).__name__}")
    return {"reasoning_effort": value.effort}
```

- [ ] **Step 4: Run tests — should pass**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/providers/test_reasoning_builders.py -v --no-cov`
Expected: 7/7 PASS.

- [ ] **Step 5: Delete old coercions in adapter.py**

Open `apps/api/src/infrastructure/llm/providers/adapter.py` and remove:
- Gemini `medium → low` mapping (~line 569)
- DeepSeek V4 6→2 mapping (~lines 437-450)
- Qwen `budget_mapping` (~lines 682-690)
- Anthropic `effort_mapping` + `additional_kwargs["effort"]` (~lines 832-841)

Replace each with calls to the corresponding `build_<provider>_reasoning(value, model)` from `reasoning_builders.py`. Apply the returned kwargs to the `ChatXxx` constructor (e.g., `ChatAnthropic(**common_kwargs, **reasoning_kwargs)`).

For DeepSeek V4 specifically: where the old code did `kwargs.pop("reasoning_effort", None)` early, now read the validated `cfg.reasoning_effort` (a `ReasoningEffortValue`) and call `build_deepseek_v4_reasoning(...)` to construct `extra_body` + `reasoning_effort` cleanly.

- [ ] **Step 6: Run full unit suite + adapter tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/infrastructure/llm/ -v --no-cov`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/api/src/infrastructure/llm/providers/reasoning_builders.py \
        apps/api/tests/unit/infrastructure/llm/providers/test_reasoning_builders.py \
        apps/api/src/infrastructure/llm/providers/adapter.py
git commit -m "feat(llm): per-provider reasoning builders + remove silent coercions"
```

---

### Task 8: Bootstrap fail-fast validation

**Files:**
- Modify: `apps/api/src/core/bootstrap.py`
- Modify: `apps/api/src/main.py`
- Create: `apps/api/tests/unit/core/test_bootstrap_reasoning.py`

- [ ] **Step 1: Write failing test for boot validation**

```python
import pytest
from src.core.bootstrap import validate_llm_defaults_against_matrix

@pytest.mark.unit
def test_validate_llm_defaults_passes_for_valid_matrix(monkeypatch):
    """Valid LLM_DEFAULTS pass without raising."""
    # Mock ModelCapabilitiesCache + LLM_DEFAULTS with valid config.
    # Should not raise.
    validate_llm_defaults_against_matrix()  # current LLM_DEFAULTS post-Task 14

@pytest.mark.unit
def test_validate_llm_defaults_raises_on_drift(monkeypatch):
    """If LLM_DEFAULTS drifts from matrix, validation raises with detail."""
    # Inject an invalid default (e.g. gpt-5.2 + reasoning="minimal").
    # Assert RuntimeError with model name in message.
```

- [ ] **Step 2: Add validate_llm_defaults_against_matrix() in bootstrap.py**

```python
async def validate_llm_defaults_against_matrix() -> None:
    """Sanity check at boot: every LLM_DEFAULTS entry must be compatible
    with its model's reasoning_widget. Fail-fast at startup if any drift
    has been introduced (e.g. by a future LLM_DEFAULTS edit that didn't
    update the matrix).

    Reuses the same validate_reasoning_effort function as the admin write
    path, ensuring N1+N2 coverage by the test parametrized matrix also
    covers boot-time validation.
    """
    from fastapi import HTTPException
    from src.domains.llm_config.constants import LLM_DEFAULTS
    from src.domains.llm_config.reasoning_validation import validate_reasoning_effort
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache

    errors: list[str] = []
    for llm_type, cfg in LLM_DEFAULTS.items():
        caps = ModelCapabilitiesCache.get(cfg.model)
        if caps is None:
            errors.append(f"  - {llm_type}: model {cfg.model!r} not in catalogue")
            continue
        try:
            validate_reasoning_effort(caps, cfg.reasoning_effort)
        except HTTPException as e:
            errors.append(f"  - {llm_type} (model={cfg.model}): {e.detail.get('msg', e.detail)}")

    if errors:
        raise RuntimeError(
            "LLM_DEFAULTS contains entries incompatible with the model "
            "catalogue:\n" + "\n".join(errors) + "\n"
            "Update LLM_DEFAULTS in apps/api/src/domains/llm_config/constants.py "
            "to match the matrix in llm_pricing_seed.sql / llm_models."
        )

    logger.info(
        "llm_defaults_matrix_validated",
        total_types=len(LLM_DEFAULTS),
    )
```

- [ ] **Step 3: Wire in main.py lifespan**

Locate `ModelCapabilitiesCache.load()` call in `main.py` lifespan startup. Add right after:

```python
await validate_llm_defaults_against_matrix()
```

- [ ] **Step 4: Run tests**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/core/test_bootstrap_reasoning.py -v --no-cov`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/core/bootstrap.py apps/api/src/main.py \
        apps/api/tests/unit/core/test_bootstrap_reasoning.py
git commit -m "feat(bootstrap): fail-fast validation of LLM_DEFAULTS against matrix"
```

---

## Phase 3 — Catalogue cleanup + matrix population

### Task 9: Add required_kind to LLMTypeMetadata

**Files:**
- Modify: `apps/api/src/domains/llm_config/constants.py`
- Modify: `apps/api/src/domains/llm_config/schemas.py` (LLMTypeInfo)

- [ ] **Step 1: Add field to LLMTypeMetadata dataclass**

```python
from src.domains.llm.models import LLMModelKindEnum

@dataclass(frozen=True)
class LLMTypeMetadata:
    # ... existing fields ...
    required_kind: LLMModelKindEnum = LLMModelKindEnum.chat
    """The kind of model this LLM type expects. Frontend filters /llm-config/metadata
    by this kind. Defaults to 'chat' (most common)."""
```

- [ ] **Step 2: Set required_kind for non-default types in LLM_TYPES_REGISTRY**

Identify all entries where the LLM type is for image / audio / realtime / etc. **Confirmed cases:**
- `image_generation` → `required_kind=LLMModelKindEnum.image`

If no other LLM type targets a non-chat kind, document it explicitly with a comment near the registry: `# All other LLM types use kind='chat' (default).`

- [ ] **Step 3: Add required_kind to LLMTypeInfo Pydantic schema**

```python
class LLMTypeInfo(BaseModel):
    # ... existing fields ...
    required_kind: Literal["chat", "image", "audio", "realtime", "tts", "embedding"] = "chat"
```

- [ ] **Step 4: Run mypy**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/llm_config/`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/llm_config/constants.py apps/api/src/domains/llm_config/schemas.py
git commit -m "feat(llm-config): add required_kind to LLMTypeMetadata + LLMTypeInfo"
```

---

### Task 10: Rewrite LLM_DEFAULTS

**Files:**
- Modify: `apps/api/src/domains/llm_config/constants.py`
- Create: `apps/api/tests/unit/domains/llm_config/test_llm_defaults_compliance.py`

- [ ] **Step 1: Write the compliance test (will fail until Task 10 step 2 lands)**

```python
import pytest
from src.domains.llm_config.constants import LLM_DEFAULTS

@pytest.mark.unit
@pytest.mark.parametrize("llm_type", list(LLM_DEFAULTS.keys()))
def test_llm_default_is_matrix_compliant(llm_type, llm_models_loaded_fixture):
    """Every LLM_DEFAULTS entry must validate against ModelCapabilitiesCache.

    This mirrors the boot-time check (bootstrap.py) so that CI catches
    LLM_DEFAULTS drift before merge.
    """
    from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
    from src.domains.llm_config.reasoning_validation import validate_reasoning_effort

    cfg = LLM_DEFAULTS[llm_type]
    caps = ModelCapabilitiesCache.get(cfg.model)
    assert caps is not None, f"{llm_type}: model {cfg.model} not in catalogue"
    validate_reasoning_effort(caps, cfg.reasoning_effort)  # raises if invalid
```

The fixture `llm_models_loaded_fixture` populates the cache from a test-only matrix (see conftest.py).

- [ ] **Step 2: Rewrite each LLM_DEFAULTS entry per spec § 8.3 conversion table**

For every entry with `reasoning_effort=...`:
- If the model is non-reasoning per matrix → set `reasoning_effort=None`.
- If the model is Qwen → use the Qwen mapping table from spec § 8.3.
- Otherwise → wrap in `ReasoningEffortEnum(effort=...)` if value ∈ matrix's enum_values, else `None`.

Example transformations:
```python
# Before:
"context_resolver": LLMAgentConfig(provider="openai", model="gpt-5-mini",
    ..., reasoning_effort="minimal"),
# After:
"context_resolver": LLMAgentConfig(provider="openai", model="gpt-5-mini",
    ..., reasoning_effort=ReasoningEffortEnum(effort="minimal")),

# Before (broken):
"vision_analysis": LLMAgentConfig(provider="openai", model="gpt-4.1-mini",
    ..., reasoning_effort="low"),
# After (option a — clear):
"vision_analysis": LLMAgentConfig(provider="openai", model="gpt-4.1-mini",
    ..., reasoning_effort=None),

# Before (Qwen):
"planner": LLMAgentConfig(provider="qwen", model="qwen3.5-plus",
    ..., reasoning_effort="none"),
# After:
"planner": LLMAgentConfig(provider="qwen", model="qwen3.5-plus",
    ..., reasoning_effort=ReasoningEffortToggleBudget(enabled=False)),
```

Process all ~30 entries with reasoning_effort set.

- [ ] **Step 3: Run the compliance test**

Run: `cd apps/api && .venv/Scripts/pytest tests/unit/domains/llm_config/test_llm_defaults_compliance.py -v --no-cov`
Expected: 51/51 PASS (one per entry in LLM_DEFAULTS).

- [ ] **Step 4: Run mypy on constants.py**

Run: `cd apps/api && .venv/Scripts/mypy src/domains/llm_config/constants.py`
Expected: 0 errors.

- [ ] **Step 5: Commit**

```bash
git add apps/api/src/domains/llm_config/constants.py apps/api/tests/unit/domains/llm_config/test_llm_defaults_compliance.py
git commit -m "feat(llm-config): rewrite LLM_DEFAULTS with ReasoningEffortValue + compliance test"
```

---

### Task 11: Rewrite llm_pricing_seed.sql

**Files:**
- Modify: `infrastructure/database/seeds/llm_pricing_seed.sql`

- [ ] **Step 1: Add the 5 new columns to the catalogue INSERT**

Schema update at the top of the seed:
```sql
-- LLM models catalogue (capabilities + reasoning UI driver)
INSERT INTO llm_models (
    id, provider, model_name,
    max_input_tokens, max_output_tokens,
    supports_tools, supports_structured_output, supports_strict_mode,
    supports_streaming, supports_vision, is_reasoning_model,
    is_active,
    kind, reasoning_widget, reasoning_enum_values,
    reasoning_budget_range, reasoning_doc_i18n_key
) VALUES
    -- OpenAI gpt-5 family
    (gen_random_uuid(), 'openai', 'gpt-5', 8192, 4096, true, true, false, true, false, true, true,
     'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'openai_gpt5'),
    (gen_random_uuid(), 'openai', 'gpt-5-mini', 8192, 4096, true, true, false, true, false, true, true,
     'chat', 'enum', '["minimal","low","medium","high"]'::jsonb, NULL, 'openai_gpt5'),
    -- ... 95 entries total per spec § 8.1 ...
ON CONFLICT (model_name) DO UPDATE SET
    kind = EXCLUDED.kind,
    reasoning_widget = EXCLUDED.reasoning_widget,
    reasoning_enum_values = EXCLUDED.reasoning_enum_values,
    reasoning_budget_range = EXCLUDED.reasoning_budget_range,
    reasoning_doc_i18n_key = EXCLUDED.reasoning_doc_i18n_key;
```

- [ ] **Step 2: Remove the 25 deleted entries**

Delete (via removal of the INSERT lines, not via DELETE statement — the seed is for fresh installs):
- 8 OpenAI: `gpt-4.1-mini-mini`, `gpt-4.1-mini-mini-audio-preview`, `gpt-4.1-mini-mini-realtime-preview`, `gpt-4.1-mini-mini-search-preview`, `gpt-4.1-mini-realtime-preview`, `gpt-4.1-mini-audio-preview`, `gpt-4.1-mini-search-preview`, `codex-mini-latest`
- 17 Anthropic: per spec § 8.2

- [ ] **Step 3: Confirm pricing INSERTs reference only kept models**

After model removal, verify that no `llm_model_pricing` entry references a deleted model_name. If it does, remove that pricing INSERT too.

- [ ] **Step 4: Apply seed on dev database (round-trip test)**

Run from project root:
```bash
docker exec lia-postgres-dev psql -U lia -d lia_db -c "TRUNCATE llm_model_pricing, llm_models RESTART IDENTITY CASCADE;"
docker exec lia-api-dev sh -c "psql $DATABASE_URL -f /infrastructure/database/seeds/llm_pricing_seed.sql"
docker exec lia-postgres-dev psql -U lia -d lia_db -c "SELECT COUNT(*) FROM llm_models;"
```
Expected: 95 rows (60-8 = 52 OpenAI + 4 Anthropic + 4 DeepSeek + 25 Gemini + 4 Qwen + 4 Perplexity + 2 Ollama).

- [ ] **Step 5: Commit**

```bash
git add infrastructure/database/seeds/llm_pricing_seed.sql
git commit -m "feat(seeds): rewrite llm_pricing_seed with kind+reasoning_widget matrix"
```

---

### Task 12: Rewrite llm_config_seed.sql

**Files:**
- Modify: `infrastructure/database/seeds/llm_config_seed.sql`

- [ ] **Step 1: Convert all reasoning_effort VARCHAR values to JSONB literals**

Examples:
```sql
-- Before:
(gen_random_uuid(), 'context_resolver', 'openai', 'gpt-5-mini', 0.2, NULL, 'minimal', NOW(), NOW()),
-- After:
(gen_random_uuid(), 'context_resolver', 'openai', 'gpt-5-mini', 0.2, NULL, '{"effort":"minimal"}'::jsonb, NOW(), NOW()),

-- Before (broken combo):
(gen_random_uuid(), 'vision_analysis', NULL, 'gpt-4.1-mini', NULL, NULL, 'low', NOW(), NOW()),
-- After (option a — clear):
(gen_random_uuid(), 'vision_analysis', NULL, 'gpt-4.1-mini', NULL, NULL, NULL, NOW(), NOW()),
```

Process all 45 entries.

- [ ] **Step 2: Remove entries referencing deleted models**

If any override targets a model in the 25-deletion list, delete the line.

- [ ] **Step 3: Apply seed on dev database**

```bash
docker exec lia-api-dev sh -c "psql $DATABASE_URL -f /infrastructure/database/seeds/llm_config_seed.sql"
docker exec lia-postgres-dev psql -U lia -d lia_db -c "SELECT COUNT(*) FROM llm_config_overrides;"
```
Expected: matches the count of remaining entries.

- [ ] **Step 4: Commit**

```bash
git add infrastructure/database/seeds/llm_config_seed.sql
git commit -m "feat(seeds): rewrite llm_config_seed with JSONB reasoning_effort + cleanup broken combos"
```

---

## Phase 4 — Migration

### Task 13: Alembic migration (atomic)

**Files:**
- Create: `apps/api/alembic/versions/2026_05_06_XXXX-llm_reasoning_overhaul.py`

- [ ] **Step 1: Generate migration skeleton**

```bash
cd apps/api && .venv/Scripts/alembic revision -m "llm_reasoning_overhaul"
```
Note the revision ID printed; rename file with the date prefix per convention.

- [ ] **Step 2: Implement upgrade()**

```python
"""LLM reasoning_effort overhaul.

Schema:
- Adds llm_models.kind, reasoning_widget, reasoning_enum_values,
  reasoning_budget_range, reasoning_doc_i18n_key.
- Converts llm_config_overrides.reasoning_effort: VARCHAR(20) → JSONB.

Data:
- Backfills new columns on existing rows from REASONING_MATRIX (embedded).
- Cleans incompatible reasoning_effort values from llm_config_overrides
  to NULL (admin reconfigures via UI post-deploy).
- Deletes 25 obsolete model rows (and their pricing + override entries
  via FK-aware ordering).

Downgrade limitation:
- Schema changes are reversible.
- Deleted models are NOT restored. Re-running the seeds (or restoring
  from backup) is the only recovery path.
"""

import json
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "<auto-generated>"
down_revision = "<previous>"
branch_labels = None
depends_on = None


# Embedded matrix — kept here so the migration is self-contained and
# reproducible across environments. Mirrors llm_pricing_seed.sql.
# Format: model_name → (widget, enum_values_or_None, budget_range_or_None, doc_key)
REASONING_MATRIX: dict = {
    # OpenAI gpt-5 family
    "gpt-5":      ("enum", ["minimal","low","medium","high"], None, "openai_gpt5"),
    "gpt-5-mini": ("enum", ["minimal","low","medium","high"], None, "openai_gpt5"),
    # ... 95 entries total per spec § 8.1 ...
}

DELETED_MODELS = [
    # OpenAI fictional + deprecated (8)
    "gpt-4.1-mini-mini", "gpt-4.1-mini-mini-audio-preview",
    "gpt-4.1-mini-mini-realtime-preview", "gpt-4.1-mini-mini-search-preview",
    "gpt-4.1-mini-realtime-preview", "gpt-4.1-mini-audio-preview",
    "gpt-4.1-mini-search-preview", "codex-mini-latest",
    # Anthropic aggressive scope (17) — per spec § 8.2
    "claude-opus-3", "claude-opus-4", "claude-opus-4-1", "claude-opus-4.1",
    "claude-opus-4-5", "claude-opus-4-6",
    "claude-sonnet-3-7", "claude-sonnet-3.7", "claude-sonnet-4",
    "claude-sonnet-4-5", "claude-sonnet-4.5", "claude-sonnet-4-6",
    "claude-haiku-3", "claude-haiku-3-5", "claude-haiku-3.5",
    "claude-3-5-haiku-latest", "claude-haiku-4-5",
]


def upgrade() -> None:
    # 1. Create new enum types in PostgreSQL
    op.execute("CREATE TYPE llm_model_kind_enum AS ENUM ('chat','image','audio','realtime','tts','embedding')")
    op.execute("CREATE TYPE llm_reasoning_widget_enum AS ENUM ('none','enum','budget_int','toggle_budget')")

    # 2. Add new columns (nullable for backfill)
    op.add_column("llm_models",
        sa.Column("kind", sa.Enum(name="llm_model_kind_enum", create_type=False), nullable=True))
    op.add_column("llm_models",
        sa.Column("reasoning_widget", sa.Enum(name="llm_reasoning_widget_enum", create_type=False), nullable=True))
    op.add_column("llm_models", sa.Column("reasoning_enum_values", JSONB, nullable=True))
    op.add_column("llm_models", sa.Column("reasoning_budget_range", JSONB, nullable=True))
    op.add_column("llm_models", sa.Column("reasoning_doc_i18n_key", sa.String(100), nullable=True))

    # 3. Backfill kind via name patterns (default = chat)
    op.execute("""
        UPDATE llm_models SET kind =
            CASE
                WHEN model_name LIKE '%-tts%' OR model_name LIKE '%-tts-%' THEN 'tts'::llm_model_kind_enum
                WHEN model_name LIKE '%-realtime%' THEN 'realtime'::llm_model_kind_enum
                WHEN model_name LIKE '%-audio%' AND model_name NOT LIKE '%-realtime%' THEN 'audio'::llm_model_kind_enum
                WHEN model_name LIKE '%-image%' OR model_name LIKE '%-image-%' OR model_name = 'chatgpt-image-latest' THEN 'image'::llm_model_kind_enum
                WHEN model_name LIKE '%embedding%' OR model_name LIKE 'text-embedding%' THEN 'embedding'::llm_model_kind_enum
                ELSE 'chat'::llm_model_kind_enum
            END;
    """)

    # 4. Backfill reasoning_widget + values from REASONING_MATRIX
    for model_name, (widget, enum_values, budget_range, doc_key) in REASONING_MATRIX.items():
        op.execute(sa.text("""
            UPDATE llm_models SET
                reasoning_widget = CAST(:widget AS llm_reasoning_widget_enum),
                reasoning_enum_values = CAST(:enum_values AS jsonb),
                reasoning_budget_range = CAST(:budget_range AS jsonb),
                reasoning_doc_i18n_key = :doc_key
            WHERE model_name = :name
        """).bindparams(
            widget=widget,
            enum_values=json.dumps(enum_values) if enum_values else None,
            budget_range=json.dumps(budget_range) if budget_range else None,
            doc_key=doc_key,
            name=model_name,
        ))

    # 5. Default unmatched rows (e.g. seeded entries not in REASONING_MATRIX) to widget=none
    op.execute("UPDATE llm_models SET reasoning_widget = 'none' WHERE reasoning_widget IS NULL;")

    # 6. Convert llm_config_overrides.reasoning_effort: VARCHAR → JSONB
    op.execute("""
        ALTER TABLE llm_config_overrides
        ALTER COLUMN reasoning_effort TYPE jsonb
        USING CASE
            WHEN reasoning_effort IS NULL THEN NULL
            ELSE jsonb_build_object('effort', reasoning_effort)
        END;
    """)

    # 7. Cleanup: NULL out reasoning_effort for invalid combinations
    # 7a. Models with widget=none — any non-NULL reasoning_effort is invalid
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'none'
          AND lco.reasoning_effort IS NOT NULL;
    """)
    # 7b. Models with widget=enum — value must be in enum_values
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'enum'
          AND lco.reasoning_effort IS NOT NULL
          AND NOT (lco.reasoning_effort->>'effort' = ANY(
              SELECT jsonb_array_elements_text(lm.reasoning_enum_values)));
    """)
    # 7c. Models with widget=budget_int — budget must be in range or sentinel
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'budget_int'
          AND lco.reasoning_effort IS NOT NULL
          AND NOT (
              (lco.reasoning_effort->>'budget')::int = COALESCE((lm.reasoning_budget_range->>'off_sentinel')::int, -999)
              OR (lco.reasoning_effort->>'budget')::int = COALESCE((lm.reasoning_budget_range->>'dynamic_sentinel')::int, -999)
              OR ((lco.reasoning_effort->>'budget')::int BETWEEN
                  (lm.reasoning_budget_range->>'min')::int AND
                  (lm.reasoning_budget_range->>'max')::int)
          );
    """)
    # 7d. Models with widget=toggle_budget — shape match required
    op.execute("""
        UPDATE llm_config_overrides AS lco
        SET reasoning_effort = NULL
        FROM llm_models AS lm
        WHERE lm.model_name = lco.model
          AND lm.reasoning_widget = 'toggle_budget'
          AND lco.reasoning_effort IS NOT NULL
          AND (
              NOT (lco.reasoning_effort ? 'enabled')
              OR (
                  (lco.reasoning_effort->>'enabled')::boolean = true
                  AND lco.reasoning_effort ? 'budget'
                  AND (lco.reasoning_effort->>'budget') IS NOT NULL
                  AND NOT ((lco.reasoning_effort->>'budget')::int BETWEEN
                      (lm.reasoning_budget_range->>'min')::int AND
                      (lm.reasoning_budget_range->>'max')::int)
              )
          );
    """)

    # 8. Delete obsolete models (FK-aware order)
    bind = op.get_bind()
    bind.execute(sa.text(
        "DELETE FROM llm_config_overrides WHERE model = ANY(:m)"
    ).bindparams(m=DELETED_MODELS))
    bind.execute(sa.text("""
        DELETE FROM llm_model_pricing
        WHERE model_id IN (SELECT id FROM llm_models WHERE model_name = ANY(:m))
    """).bindparams(m=DELETED_MODELS))
    bind.execute(sa.text(
        "DELETE FROM llm_models WHERE model_name = ANY(:m)"
    ).bindparams(m=DELETED_MODELS))

    # 9. NOT NULL the new columns post-backfill
    op.alter_column("llm_models", "kind", nullable=False)
    op.alter_column("llm_models", "reasoning_widget", nullable=False)


def downgrade() -> None:
    """Schema downgrade only. Deleted models are NOT restored.

    Re-running seeds (or restoring DB from backup) is the only recovery
    path for the 25 obsolete models removed by upgrade(). This is
    intentional: none of those models was in active use.
    """
    # Reverse JSONB → VARCHAR
    op.execute("""
        ALTER TABLE llm_config_overrides
        ALTER COLUMN reasoning_effort TYPE varchar(20)
        USING reasoning_effort->>'effort';
    """)
    # Drop columns
    op.drop_column("llm_models", "reasoning_doc_i18n_key")
    op.drop_column("llm_models", "reasoning_budget_range")
    op.drop_column("llm_models", "reasoning_enum_values")
    op.drop_column("llm_models", "reasoning_widget")
    op.drop_column("llm_models", "kind")
    # Drop enum types
    op.execute("DROP TYPE llm_reasoning_widget_enum")
    op.execute("DROP TYPE llm_model_kind_enum")
```

- [ ] **Step 3: Test migration round-trip on DEV**

```bash
cd apps/api && .venv/Scripts/alembic upgrade head
.venv/Scripts/alembic downgrade -1
.venv/Scripts/alembic upgrade head
```
Expected: each command exits 0; final state matches post-upgrade.

- [ ] **Step 4: Verify deletion counts**

```bash
docker exec lia-postgres-dev psql -U lia -d lia_db -c \
  "SELECT count(*) FROM llm_models WHERE model_name LIKE 'gpt-4.1-mini-mini%' OR model_name = 'codex-mini-latest';"
```
Expected: 0.

- [ ] **Step 5: Commit**

```bash
git add apps/api/alembic/versions/2026_05_06_*-llm_reasoning_overhaul.py
git commit -m "feat(db): atomic migration for reasoning_effort overhaul + 25 model cleanup"
```

---

## Phase 5 — Frontend

### Task 14: Update TypeScript types

**Files:**
- Modify: `apps/web/src/types/llm-config.ts`

- [ ] **Step 1: Add new fields, remove is_image_model**

```ts
export interface ReasoningBudgetRange {
  min: number;
  max: number;
  off_sentinel?: number;
  dynamic_sentinel?: number;
}

export type ReasoningEffortValue =
  | { effort: string }
  | { budget: number }
  | { enabled: boolean; budget?: number }
  | null;

export type ReasoningWidget = 'none' | 'enum' | 'budget_int' | 'toggle_budget';

export interface ModelCapabilities {
  model_id: string;
  kind: 'chat' | 'image' | 'audio' | 'realtime' | 'tts' | 'embedding';
  max_output_tokens: number;
  supports_tools: boolean;
  supports_structured_output: boolean;
  supports_vision: boolean;
  is_reasoning_model: boolean;
  reasoning_widget: ReasoningWidget;
  reasoning_enum_values: string[] | null;
  reasoning_budget_range: ReasoningBudgetRange | null;
  reasoning_doc_i18n_key: string | null;
  cost_input: number | null;
  cost_output: number | null;
}

export interface LLMTypeInfo {
  // ... existing fields ...
  required_kind: 'chat' | 'image' | 'audio' | 'realtime' | 'tts' | 'embedding';
}
```

**Delete** `is_image_model?: boolean` from the schema.

- [ ] **Step 2: Run tsc**

Run: `docker exec lia-web-dev sh -c "cd /monorepo/apps/web && pnpm tsc --noEmit"`
Expected: errors point to obsolete `is_image_model` usages — to fix in Task 16.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/types/llm-config.ts
git commit -m "feat(web): update LLM-config types (add kind+reasoning_*, remove is_image_model)"
```

---

### Task 15: Create ReasoningWidget component (TDD)

**Files:**
- Create: `apps/web/src/components/settings/llm-config/reasoningDocText.ts`
- Create: `apps/web/src/components/settings/llm-config/ReasoningWidget.tsx`
- Create: `apps/web/src/components/settings/llm-config/__tests__/ReasoningWidget.test.tsx`

- [ ] **Step 1: Create the doc-text constants file**

Per spec § 6.3 — copy verbatim from REASONING_DOC_TEXT (English-only, no i18n keys).

- [ ] **Step 2: Write failing tests for the 4 widgets**

```tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ReasoningWidget } from '../ReasoningWidget';

describe('ReasoningWidget', () => {
  it('renders nothing when widget=none', () => {
    const { container } = render(
      <ReasoningWidget widget="none" value={null} onChange={vi.fn()} />
    );
    expect(container).toBeEmptyDOMElement();
  });

  it('renders enum dropdown with options', () => {
    render(
      <ReasoningWidget
        widget="enum"
        enumValues={['none', 'low', 'medium', 'high', 'xhigh']}
        value={{ effort: 'medium' }}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('combobox')).toHaveValue('medium');
    expect(screen.getAllByRole('option').map(o => o.textContent)).toEqual(
      ['none', 'low', 'medium', 'high', 'xhigh']
    );
  });

  it('shows warning when current enum value is invalid', () => {
    render(
      <ReasoningWidget
        widget="enum"
        enumValues={['none', 'low', 'medium', 'high']}
        value={{ effort: 'minimal' }} // ← gpt-5.2 + minimal regression
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('alert')).toHaveTextContent(/invalid/i);
  });

  it('renders budget_int with Off/Dynamic/Custom presets + numeric input', () => {
    const onChange = vi.fn();
    render(
      <ReasoningWidget
        widget="budget_int"
        budgetRange={{ min: 1, max: 24576, off_sentinel: 0, dynamic_sentinel: -1 }}
        value={{ budget: 16384 }}
        onChange={onChange}
      />
    );
    // Custom is selected; numeric input visible with value 16384
    expect(screen.getByRole('spinbutton')).toHaveValue(16384);
    // Switch to Off
    fireEvent.click(screen.getByText('Off'));
    expect(onChange).toHaveBeenCalledWith({ budget: 0 });
  });

  it('renders toggle_budget with switch + conditional input', () => {
    render(
      <ReasoningWidget
        widget="toggle_budget"
        budgetRange={{ min: 0, max: 32768 }}
        value={{ enabled: true, budget: 4096 }}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole('switch')).toBeChecked();
    expect(screen.getByRole('spinbutton')).toHaveValue(4096);
  });

  it('hides budget input when toggle_budget enabled=false', () => {
    render(
      <ReasoningWidget
        widget="toggle_budget"
        budgetRange={{ min: 0, max: 32768 }}
        value={{ enabled: false }}
        onChange={vi.fn()}
      />
    );
    expect(screen.queryByRole('spinbutton')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
docker exec lia-web-dev sh -c "cd /monorepo/apps/web && pnpm test ReasoningWidget"
```
Expected: ImportError on `ReasoningWidget`.

- [ ] **Step 4: Implement ReasoningWidget.tsx**

```tsx
'use client';

import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { AlertCircle } from 'lucide-react';
import type { ReasoningWidget as ReasoningWidgetType, ReasoningEffortValue, ReasoningBudgetRange } from '@/types/llm-config';
import { REASONING_DOC_TEXT } from './reasoningDocText';

interface Props {
  widget: ReasoningWidgetType;
  enumValues?: string[];
  budgetRange?: ReasoningBudgetRange;
  docI18nKey?: string;
  value: ReasoningEffortValue;
  onChange: (next: ReasoningEffortValue) => void;
  disabled?: boolean;
}

export function ReasoningWidget({
  widget, enumValues, budgetRange, docI18nKey, value, onChange, disabled
}: Props) {
  const docText = docI18nKey ? REASONING_DOC_TEXT[docI18nKey] : undefined;

  if (widget === 'none') return null;

  if (widget === 'enum') {
    const allowed = enumValues ?? [];
    const current = value && 'effort' in value ? value.effort : '';
    const isInvalid = current !== '' && !allowed.includes(current);
    return (
      <div className="space-y-1">
        <Select value={current} onValueChange={(v) => onChange({ effort: v })} disabled={disabled}>
          <SelectTrigger><SelectValue /></SelectTrigger>
          <SelectContent>
            {allowed.map(v => <SelectItem key={v} value={v}>{v}</SelectItem>)}
          </SelectContent>
        </Select>
        {isInvalid && (
          <p role="alert" className="flex items-center gap-1 text-xs text-destructive">
            <AlertCircle className="h-3 w-3" /> Invalid: {current!r} not in {allowed.join(', ')}
          </p>
        )}
        {docText && <p className="text-xs text-muted-foreground">{docText}</p>}
      </div>
    );
  }

  if (widget === 'budget_int') {
    // Implementation with Off/Dynamic/Custom presets + conditional input.
    // ... (full body — handles off_sentinel/dynamic_sentinel) ...
  }

  if (widget === 'toggle_budget') {
    // Implementation with Switch + conditional Input.
    // ... (full body) ...
  }

  return null;
}
```

(Full implementation per spec § 6.2; the test file above describes the exact behaviors.)

- [ ] **Step 5: Run tests — should pass**

```bash
docker exec lia-web-dev sh -c "cd /monorepo/apps/web && pnpm test ReasoningWidget"
```
Expected: all 6 tests pass.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/settings/llm-config/
git commit -m "feat(web): ReasoningWidget component + doc text + tests"
```

---

### Task 16: Wire ReasoningWidget + delete getModelConstraints

**Files:**
- Modify: `apps/web/src/components/settings/AdminLLMConfigSection.tsx`

- [ ] **Step 1: Delete getModelConstraints + regex constants**

Remove lines 259-453 (the entire function + regex constants) per spec § 6.1.

- [ ] **Step 2: Replace tile-compact display logic**

In the Tile component (~line 226), replace `tileConstraints.isReasoningModel` / `tileConstraints.supportsTemperature` reads with direct reads from `caps`:

```tsx
const caps = config.effective_capabilities; // from API
{caps.is_reasoning_model
  ? `E:${formatReasoningValue(config.effective.reasoning_effort, caps.reasoning_widget)}`
  : `T:${config.effective.temperature}`}
```

Add `formatReasoningValue` per spec § 6.4.

- [ ] **Step 3: Replace dialog reasoning section with ReasoningWidget**

```tsx
<ReasoningWidget
  widget={selectedModelCapabilities?.reasoning_widget ?? 'none'}
  enumValues={selectedModelCapabilities?.reasoning_enum_values ?? undefined}
  budgetRange={selectedModelCapabilities?.reasoning_budget_range ?? undefined}
  docI18nKey={selectedModelCapabilities?.reasoning_doc_i18n_key ?? undefined}
  value={form.reasoning_effort}
  onChange={(v) => setForm({ ...form, reasoning_effort: v })}
/>
```

- [ ] **Step 4: Remove is_image_model filter, replace by backend kinds=**

Lines 587-588 (the `m.is_image_model` filter) — delete. Replace by passing `kinds=` to the metadata fetch URL per Task 18.

For now, delete the filter and rely on the backend (Task 17 default `?kinds=chat`) — verify in Task 18.

- [ ] **Step 5: Run lint + tsc**

```bash
docker exec lia-web-dev sh -c "cd /monorepo/apps/web && pnpm lint --max-warnings=0 && pnpm tsc --noEmit"
```
Expected: 0 errors. If `is_image_model` is still referenced anywhere → grep + clean.

- [ ] **Step 6: Commit**

```bash
git add apps/web/src/components/settings/AdminLLMConfigSection.tsx
git commit -m "feat(web): wire ReasoningWidget + delete getModelConstraints + remove is_image_model"
```

---

### Task 17: Backend metadata endpoint kinds= filter

**Files:**
- Modify: `apps/api/src/domains/llm_config/router.py`
- Modify: `apps/api/src/domains/llm_config/service.py` (`get_models_metadata`)

- [ ] **Step 1: Add query param to router**

```python
@router.get("/metadata", response_model=ProviderModelsMetadata)
async def get_metadata(
    kinds: str = Query(default="chat", description="Comma-separated list of model kinds to include"),
    capability: str | None = Query(default=None, description="Optional capability filter (e.g. 'vision')"),
) -> ProviderModelsMetadata:
    kind_list = [k.strip() for k in kinds.split(",") if k.strip()]
    return await LLMConfigService.get_models_metadata(kinds=kind_list, capability=capability)
```

- [ ] **Step 2: Update service to honor filter**

```python
async def get_models_metadata(
    kinds: list[str] | None = None,
    capability: str | None = None,
) -> ProviderModelsMetadata:
    kind_set = set(kinds) if kinds else None
    # ... iterate ModelCapabilitiesCache and ImageOptionsCache, filter by:
    #     - cap.kind in kind_set (if set)
    #     - cap.supports_<capability> if capability provided
```

Replace the old `is_image_model=True` setter (line 400) with `kind=LLMModelKindEnum.image`.

- [ ] **Step 3: Add unit test for the filter**

Test that `?kinds=image` returns only image kind, `?kinds=chat&capability=vision` filters by both.

- [ ] **Step 4: Commit**

```bash
git add apps/api/src/domains/llm_config/router.py apps/api/src/domains/llm_config/service.py
git commit -m "feat(llm-config): /metadata kinds= filter + remove is_image_model setter"
```

---

### Task 18: Frontend metadata fetch passes kinds=

**Files:**
- Modify: `apps/web/src/components/settings/AdminLLMConfigSection.tsx` (or hook file)

- [ ] **Step 1: Pass kinds query param**

Identify the `useApiQuery('/llm-config/metadata')` call. Modify:

```tsx
const requiredKind = config?.info.required_kind ?? 'chat';
const { data: metadata } = useApiQuery<ProviderModelsMetadata>(
  `/llm-config/metadata?kinds=${requiredKind}`,
  { ... }
);
```

For LLM types with `required_capabilities=["vision"]`, also append `&capability=vision` (read from `config.info.required_capabilities`).

- [ ] **Step 2: Run lint + tsc**

Same as Task 16.

- [ ] **Step 3: Commit**

```bash
git add apps/web/src/components/settings/AdminLLMConfigSection.tsx
git commit -m "feat(web): pass kinds= to /llm-config/metadata based on required_kind"
```

---

## Phase 6 — Final integration

### Task 19: Run full CI + Docker round-trip

- [ ] **Step 1: Run full backend lint + tests**

```bash
cd apps/api
.venv/Scripts/black --check src/ tests/
.venv/Scripts/ruff check src/ tests/
.venv/Scripts/mypy src/
.venv/Scripts/pytest tests/unit tests/services -m "not integration and not slow and not benchmark and not multiprocess and not e2e" --no-cov -q
```
Expected: all green. Tests count > 7500 (increased from baseline 7496 by ~80 new test cases).

- [ ] **Step 2: Run frontend lint + tsc**

```bash
docker exec lia-web-dev sh -c "cd /monorepo/apps/web && pnpm lint --max-warnings=0 && pnpm tsc --noEmit && pnpm test"
```
Expected: all green.

- [ ] **Step 3: Restart API container, verify boot validation passes**

```bash
docker restart lia-api-dev
docker logs lia-api-dev 2>&1 | grep -E "Application startup|llm_defaults_matrix_validated|RuntimeError"
```
Expected: `Application startup complete` + `llm_defaults_matrix_validated`. No RuntimeError on LLM_DEFAULTS.

- [ ] **Step 4: Verify catalog state via psql**

```bash
docker exec lia-postgres-dev psql -U lia -d lia_db -c "
SELECT
    COUNT(*) FILTER (WHERE kind = 'chat') AS chat_count,
    COUNT(*) FILTER (WHERE reasoning_widget = 'enum') AS enum_count,
    COUNT(*) FILTER (WHERE reasoning_widget = 'budget_int') AS budget_count,
    COUNT(*) FILTER (WHERE reasoning_widget = 'toggle_budget') AS toggle_count,
    COUNT(*) FILTER (WHERE reasoning_widget = 'none') AS none_count
FROM llm_models;"
```
Expected counts match spec § 8.1 (~33 enum, 3 budget_int, 3 toggle_budget, ~56 none, kind=chat majority).

- [ ] **Step 5: Visual frontend check (manual)**

Open Configuration LLM in dev container; click on different LLM types:
- `router` (gpt-5-mini default) → ReasoningWidget shows enum dropdown with `[minimal, low, medium, high]`.
- `image_generation` → only image kinds appear in model dropdown.
- Select `gpt-5.2` for some chat type → ReasoningWidget enum shows `[none, low, medium, high, xhigh]`. **`minimal` is NOT offered (the original prod bug fix).**
- Select `gemini-2.5-flash` → ReasoningWidget shows budget_int with Off/Dynamic/Custom.
- Select `qwen3.5-plus` → ReasoningWidget shows toggle + conditional budget input.
- Save a config → verify it persists; reopen → verify state round-trips correctly.

- [ ] **Step 6: Final commit**

```bash
git add -A
git commit -m "test(llm-config): integration validation post-overhaul"
```

---

## Self-Review Checklist (executed after writing this plan)

**1. Spec coverage:**
- §3.1 Architecture overview ✅ Tasks 1-13 implement
- §3.2 4 widget types ✅ Task 15
- §4 Data model ✅ Tasks 1-4, 13
- §5 API contract ✅ Tasks 3, 17
- §6 Frontend ✅ Tasks 14-16, 18
- §7 Backend validation ✅ Tasks 5-8
- §8 Seed strategy + matrix ✅ Tasks 11, 12
- §9 Migration & rollout ✅ Task 13, 19
- §10 Out of scope ✅ Not implemented (correctly)

**2. Placeholder scan:** Tasks 7, 11, 13 reference "all 95 entries" / "all 45 entries" — these reference the spec § 8.1 / § 8.2 matrices for verbatim content. The spec is the source; the migration / seed file produced by the engineer must transcribe the matrix completely. Acceptable because the spec contains the exhaustive list and is referenced verbatim.

**3. Type consistency:**
- `ReasoningEffortEnum`, `ReasoningEffortBudget`, `ReasoningEffortToggleBudget` consistent across Tasks 3, 4, 5, 7, 10.
- `LLMModelKindEnum`, `LLMReasoningWidgetEnum` consistent across Tasks 1, 9, 13.
- `validate_reasoning_effort()` signature consistent across Tasks 5, 6, 8, 10.

No drift identified. Plan is ready for execution.

---

## Notes for the implementing agent

- **Order matters**: Phases 1-6 must execute sequentially. Within a phase, individual tasks may parallelize.
- **TDD strict** for Tasks 5, 7, 8, 10, 15. Other tasks are mechanical (schema/seed/refactor).
- **Frequent commits**: each task ends with a commit. Do not batch.
- **i18n parity**: this PR introduces 0 new i18n keys (per Section 3 decision — English-only constants). Pre-commit hook will not fail on this dimension.
- **No skipping `--no-verify`**: fix issues, don't bypass.
- **Anthropic effort fix**: when implementing Task 7 step 5 (adapter rewrite), pay extra attention to the Anthropic builder — the bug fix changes `additional_kwargs["effort"]` to `ChatAnthropic(effort=...)` constructor kwarg. Verify the constructor receives it correctly by checking `ChatAnthropic` instance has `.effort` attribute set after build.
