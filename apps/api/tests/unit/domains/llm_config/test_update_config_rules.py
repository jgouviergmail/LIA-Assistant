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

from src.core.reasoning_intent import ReasoningIntent
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
class TestTheSeparateEffortFieldIsGone:
    """``LLMTypeConfigUpdate.effort`` and its validation were removed (ADR-245).

    It produced the same Anthropic kwarg as ``reasoning_effort``, and
    ``additional_kwargs.update()`` decided which one silently won. Measured at
    removal: no configured slot set it, so nothing changed behaviour.
    """

    def test_the_field_no_longer_exists(self) -> None:
        assert "effort" not in LLMTypeConfigUpdate.model_fields

    def test_the_catalogue_column_travelled_with_it(self) -> None:
        """``llm_models.effort_values`` fed only that field."""
        from src.domains.llm.models import LLMModel

        assert "effort_values" not in LLMModel.__table__.columns


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
            reasoning_effort=ReasoningIntent(level="medium"),  # adaptive → thinking ON
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
            reasoning_effort=ReasoningIntent(level="none"),  # no thinking
            temperature=0.5,
            top_p=0.9,
        )

        with patch(_CAPS_GET, return_value=caps), patch(_CACHE_RELOAD, new=AsyncMock()):
            await service.update_config("planner", update, uuid4(), MagicMock())

        assert update.temperature == 0.5  # off → no thinking → no lock
        assert update.top_p == 0.9


@pytest.mark.unit
@pytest.mark.asyncio
class TestUpdateConfigReasoningWithoutModel:
    """The guard must run even when ``model`` is omitted from the update.

    Override semantics omit ``model`` when it equals the type default, and the
    guard used to be keyed on ``update.model is not None`` — so an invalid
    ``reasoning_effort`` persisted through exactly that path, then every GET
    degraded it at merge time (prod 2026-08-14: 363 warnings in a single admin
    session). The target model of a model-less update IS the type default's
    model, and since ADR-245 the target PROVIDER is the default's provider too:
    without it the family cannot be derived and the guard would be inert.

    Both tests below resolve their slot FROM ``LLM_DEFAULTS`` and assert what
    the resolved ladder actually offers before submitting. A hard-coded slot
    would go vacuous the day the default moves to another model — which is how
    the previous version of this file ended up pointing at a provider no slot
    used any more.
    """

    @staticmethod
    def _slot_with_a_ladder() -> tuple[str, str, str, list[str]]:
        """Return (slot, provider, model, ladder) for a reasoning code default."""
        from src.domains.llm_config.constants import LLM_DEFAULTS
        from src.infrastructure.llm.reasoning.profiles import resolve_reasoning_profile

        for name, cfg in LLM_DEFAULTS.items():
            profile = resolve_reasoning_profile(cfg.provider, cfg.model)
            if profile.levels:
                return name, cfg.provider, cfg.model, list(profile.levels)
        raise AssertionError("no code default resolves to a reasoning family")

    def _caps_for(self, model: str) -> SimpleNamespace:
        """What ``ModelCapabilitiesCache.get`` returns for that default model."""
        return SimpleNamespace(
            model_id=model,
            reasoning_widget="enum",
            reasoning_enum_values=None,
            reasoning_budget_range=None,
            max_output_tokens=32768,
        )

    async def test_a_level_the_default_model_refuses_is_rejected(self) -> None:
        service, db = _make_service()
        slot, _provider, model, ladder = self._slot_with_a_ladder()
        refused = next(lvl for lvl in ("max", "xhigh", "minimal") if lvl not in ladder)

        update = LLMTypeConfigUpdate(reasoning_effort=ReasoningIntent(level=refused))

        with patch(_CAPS_GET, return_value=self._caps_for(model)):
            with pytest.raises(HTTPException) as exc:
                await service.update_config(slot, update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        detail = exc.value.detail
        assert detail["type"] == "invalid_reasoning_effort"  # type: ignore[index]
        assert detail["ctx"]["submitted"] == refused  # type: ignore[index]
        db.execute.assert_not_called()

    async def test_a_level_the_default_model_offers_is_accepted(self) -> None:
        service, db = _make_service()
        slot, _provider, model, ladder = self._slot_with_a_ladder()
        offered = next(lvl for lvl in ("high", "medium", "low") if lvl in ladder)

        # max_tokens is explicit: an accepted heavy level with an inherited
        # small default is the OTHER guard's job (the 2026-07-29 incident), and
        # this test must not accidentally assert that one.
        update = LLMTypeConfigUpdate(
            reasoning_effort=ReasoningIntent(level=offered), max_tokens=50000
        )

        with (
            patch(_CAPS_GET, return_value=self._caps_for(model)),
            patch(_CACHE_RELOAD, new=AsyncMock()),
        ):
            await service.update_config(slot, update, uuid4(), MagicMock())

        db.commit.assert_awaited()


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
            reasoning_effort=ReasoningIntent(level="high"),
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
            reasoning_effort=ReasoningIntent(level="high"),
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
            reasoning_effort=ReasoningIntent(level="none"),
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

        # Precondition: compaction's code default asks for thinking.
        default_reasoning = LLM_DEFAULTS["compaction"].reasoning_effort
        assert default_reasoning is not None
        assert default_reasoning.budget_tokens is not None or default_reasoning.level not in (
            "provider_default",
            "none",
            "minimal",
            "low",
        )

        service, db = _make_service()
        update = LLMTypeConfigUpdate(max_tokens=800)  # model/effort untouched → inherited

        with pytest.raises(HTTPException) as exc:
            await service.update_config("compaction", update, uuid4(), MagicMock())

        assert exc.value.status_code == 422
        assert exc.value.detail["type"] == "thinking_budget_below_floor"  # type: ignore[index]
        db.execute.assert_not_called()
