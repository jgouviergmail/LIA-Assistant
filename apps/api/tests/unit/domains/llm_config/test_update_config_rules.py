"""Unit tests for the Anthropic-specific business rules in
``LLMConfigService.update_config``:

- the separate global ``effort`` validation against the model's ``effort_values``
  (HTTP 422 on an unsupported value), and
- the temperature/top_p lock when reasoning (extended thinking) is enabled on an
  Anthropic model (API constraint — sampling params are incompatible with
  thinking, so they are forced to ``None``).

No DB / no network: the ``AsyncSession`` and the in-memory caches are mocked; the
guards run before any persistence, so the assertions target the raised error or
the mutated ``update`` object directly.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.reasoning_types import ReasoningEffortEnum
from src.domains.llm_config.schemas import LLMTypeConfigUpdate
from src.domains.llm_config.service import LLMConfigService

_CAPS_GET = "src.infrastructure.llm.model_capabilities_cache.ModelCapabilitiesCache.get"
_CACHE_RELOAD = "src.domains.llm_config.service.LLMConfigOverrideCache.invalidate_and_reload"


def _make_service() -> tuple[LLMConfigService, AsyncMock]:
    """Build an ``LLMConfigService`` with a fully mocked session + side effects."""
    db = AsyncMock()
    exec_result = MagicMock()
    exec_result.scalar_one_or_none.return_value = None  # no existing override row
    db.execute = AsyncMock(return_value=exec_result)
    db.commit = AsyncMock()
    db.add = MagicMock()

    service = LLMConfigService(db)
    service._log_audit = MagicMock()  # type: ignore[method-assign]
    service.get_config = AsyncMock(return_value=MagicMock())  # type: ignore[method-assign]
    return service, db


def _enum_caps(model_id: str) -> SimpleNamespace:
    """Capabilities for an adaptive enum model (opus-4-6 shape), no separate effort."""
    return SimpleNamespace(
        model_id=model_id,
        effort_values=None,
        reasoning_widget="enum",
        reasoning_enum_values=["off", "low", "medium", "high", "max"],
        reasoning_budget_range=None,
    )


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateConfigEffortValidation:
    async def test_invalid_effort_rejected_422(self) -> None:
        """An effort not in the model's effort_values is rejected before any DB work."""
        service, db = _make_service()
        caps = _enum_caps("claude-opus-4-6")  # effort_values=None → no separate effort
        update = LLMTypeConfigUpdate(provider="anthropic", model="claude-opus-4-6", effort="xhigh")

        with patch(_CAPS_GET, return_value=caps):
            with pytest.raises(HTTPException) as exc:
                await service.update_config("planner", update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "invalid_effort"  # type: ignore[index]
        db.execute.assert_not_called()  # raised before persistence

    async def test_valid_effort_accepted(self) -> None:
        """A value present in effort_values passes and the update is persisted."""
        service, db = _make_service()
        caps = SimpleNamespace(
            model_id="claude-opus-4-5",
            effort_values=["low", "medium", "high"],
            reasoning_widget="toggle_budget",
            reasoning_enum_values=None,
            reasoning_budget_range={"min": 1024, "max": 16384},
        )
        update = LLMTypeConfigUpdate(provider="anthropic", model="claude-opus-4-5", effort="low")

        with patch(_CAPS_GET, return_value=caps), patch(_CACHE_RELOAD, new=AsyncMock()):
            await service.update_config("planner", update, uuid4(), MagicMock())

        db.commit.assert_awaited()  # completed without raising


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateConfigAnthropicTemperatureLock:
    async def test_thinking_locks_temperature_and_top_p(self) -> None:
        """Reasoning enabled on Anthropic → temperature/top_p forced to None."""
        service, _db = _make_service()
        caps = _enum_caps("claude-opus-4-6")
        update = LLMTypeConfigUpdate(
            provider="anthropic",
            model="claude-opus-4-6",
            reasoning_effort=ReasoningEffortEnum(effort="medium"),  # adaptive → thinking ON
            temperature=0.5,
            top_p=0.9,
        )

        with patch(_CAPS_GET, return_value=caps), patch(_CACHE_RELOAD, new=AsyncMock()):
            await service.update_config("planner", update, uuid4(), MagicMock())

        assert update.temperature is None  # locked by the Anthropic thinking rule
        assert update.top_p is None

    async def test_off_does_not_lock_temperature(self) -> None:
        """The 'off' sentinel means no thinking → sampling params are left untouched."""
        service, _db = _make_service()
        caps = _enum_caps("claude-opus-4-6")
        update = LLMTypeConfigUpdate(
            provider="anthropic",
            model="claude-opus-4-6",
            reasoning_effort=ReasoningEffortEnum(effort="off"),  # no thinking
            temperature=0.5,
            top_p=0.9,
        )

        with patch(_CAPS_GET, return_value=caps), patch(_CACHE_RELOAD, new=AsyncMock()):
            await service.update_config("planner", update, uuid4(), MagicMock())

        assert update.temperature == 0.5  # off → no thinking → no lock
        assert update.top_p == 0.9


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateConfigReasoningShapeWithoutModel:
    """The shape guard must run even when ``model`` is omitted from the update.

    Override semantics omit ``model`` when it equals the type default, and the
    guard used to be keyed on ``update.model is not None`` — so a wrong-shaped
    ``reasoning_effort`` persisted through exactly that path, then every GET
    degraded it at merge time (prod 2026-08-14: 363
    ``wrong_reasoning_effort_shape`` warnings in a single admin session). The
    target model of a model-less update IS the type default's model.
    """

    async def test_wrong_shape_rejected_even_without_model(self) -> None:
        service, db = _make_service()
        # The default model resolves to toggle_budget caps → the enum shape is wrong.
        caps = SimpleNamespace(
            model_id="whatever-default",
            effort_values=None,
            reasoning_widget="toggle_budget",
            reasoning_enum_values=None,
            reasoning_budget_range={"min": 0, "max": 32768},
        )
        update = LLMTypeConfigUpdate(reasoning_effort=ReasoningEffortEnum(effort="low"))

        with patch(_CAPS_GET, return_value=caps):
            with pytest.raises(HTTPException) as exc:
                await service.update_config("planner", update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "wrong_reasoning_effort_shape"  # type: ignore[index]
        db.commit.assert_not_awaited()  # nothing persisted

    async def test_wrong_effort_rejected_even_without_model(self) -> None:
        """Same hole, other field: the separate global `effort` (Anthropic)
        was only validated when `model` travelled with it."""
        service, db = _make_service()
        caps = SimpleNamespace(
            model_id="whatever-default",
            effort_values=None,  # the default model declares NO effort support
            reasoning_widget="none",
            reasoning_enum_values=None,
            reasoning_budget_range=None,
        )
        update = LLMTypeConfigUpdate(effort="high")

        with patch(_CAPS_GET, return_value=caps):
            with pytest.raises(HTTPException) as exc:
                await service.update_config("planner", update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "invalid_effort"  # type: ignore[index]
        db.commit.assert_not_awaited()

    async def test_unknown_default_model_does_not_block_a_modelless_update(self) -> None:
        """Boot already validates code defaults; an unavailable capabilities
        cache must not turn a legitimate model-less save into a 422."""
        service, db = _make_service()
        update = LLMTypeConfigUpdate(reasoning_effort=ReasoningEffortEnum(effort="low"))

        with patch(_CAPS_GET, return_value=None), patch(_CACHE_RELOAD, new=AsyncMock()):
            await service.update_config("planner", update, uuid4(), MagicMock())

        db.commit.assert_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateConfigEmptyStringNormalization:
    """An empty model string is never a choice (provider is fenced by its
    request Literal) — normalized to NULL at write time so it cannot override
    the default model at merge time and break LLM resolution."""

    async def test_empty_model_is_stored_as_null(self) -> None:
        service, db = _make_service()
        update = LLMTypeConfigUpdate(model="", temperature=0.3)

        with patch(_CACHE_RELOAD, new=AsyncMock()):
            await service.update_config("planner", update, uuid4(), MagicMock())

        added_row = db.add.call_args[0][0]
        assert added_row.model is None
        assert added_row.temperature == 0.3


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateConfigThinkingBudgetFloor:
    """Thinking × completion-budget coherence on the admin write path.

    Regression class (prod 2026-07-29): telephony_synthesis was switched to
    deepseek-v4-flash at effort=high with max_tokens left empty — the effective
    config inherited the pre-thinking default of 600 tokens, reasoning consumed
    all of it, and every post-call report degraded to the raw vendor summary.
    The validation runs on the EFFECTIVE (merged) config, before persistence.
    """

    @staticmethod
    def _deepseek_caps() -> SimpleNamespace:
        return SimpleNamespace(
            model_id="deepseek-v4-flash",
            effort_values=None,
            reasoning_widget="enum",
            reasoning_enum_values=["off", "high", "max"],
            reasoning_budget_range=None,
        )

    async def test_heavy_thinking_inheriting_small_default_rejected(self) -> None:
        """The exact incident shape: effort=high, max_tokens empty → inherited tiny cap."""
        from src.core.config import settings
        from src.domains.llm_config.constants import LLM_DEFAULTS

        floor = settings.llm_thinking_max_tokens_floor
        # Precondition, not an oracle: the scenario needs a type whose code
        # default is below the floor (briefing = a short-output, non-thinking
        # calibration). If this ever fails, pick another such type.
        assert LLM_DEFAULTS["briefing"].max_tokens < floor

        service, db = _make_service()
        update = LLMTypeConfigUpdate(
            provider="deepseek",
            model="deepseek-v4-flash",
            reasoning_effort=ReasoningEffortEnum(effort="high"),
        )

        with patch(_CAPS_GET, return_value=self._deepseek_caps()):
            with pytest.raises(HTTPException) as exc:
                await service.update_config("briefing", update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        detail = exc.value.detail
        assert detail["type"] == "thinking_budget_below_floor"  # type: ignore[index]
        assert detail["ctx"]["floor"] == floor  # type: ignore[index]
        assert detail["ctx"]["effective_max_tokens"] == (  # type: ignore[index]
            LLM_DEFAULTS["briefing"].max_tokens
        )
        db.execute.assert_not_called()  # raised before persistence

    async def test_heavy_thinking_with_raised_max_tokens_accepted(self) -> None:
        from src.core.config import settings

        service, db = _make_service()
        update = LLMTypeConfigUpdate(
            provider="deepseek",
            model="deepseek-v4-flash",
            reasoning_effort=ReasoningEffortEnum(effort="high"),
            max_tokens=settings.llm_thinking_max_tokens_floor,
        )

        with (
            patch(_CAPS_GET, return_value=self._deepseek_caps()),
            patch(_CACHE_RELOAD, new=AsyncMock()),
        ):
            await service.update_config("briefing", update, uuid4(), MagicMock())

        db.commit.assert_awaited()

    async def test_reasoning_off_keeps_small_budgets_legal(self) -> None:
        service, db = _make_service()
        update = LLMTypeConfigUpdate(
            provider="deepseek",
            model="deepseek-v4-flash",
            reasoning_effort=ReasoningEffortEnum(effort="off"),
            max_tokens=500,
        )

        with (
            patch(_CAPS_GET, return_value=self._deepseek_caps()),
            patch(_CACHE_RELOAD, new=AsyncMock()),
        ):
            await service.update_config("briefing", update, uuid4(), MagicMock())

        db.commit.assert_awaited()

    async def test_small_explicit_max_tokens_with_inherited_heavy_default_rejected(self) -> None:
        """The mirror shape: shrink max_tokens on a type whose DEFAULT thinks."""
        from src.domains.llm_config.constants import LLM_DEFAULTS

        # Precondition: compaction's code default enables Qwen thinking.
        default_reasoning = LLM_DEFAULTS["compaction"].reasoning_effort
        assert getattr(default_reasoning, "enabled", False) is True

        service, db = _make_service()
        update = LLMTypeConfigUpdate(max_tokens=800)  # model/effort untouched → inherited

        with pytest.raises(HTTPException) as exc:
            await service.update_config("compaction", update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "thinking_budget_below_floor"  # type: ignore[index]
        db.execute.assert_not_called()
