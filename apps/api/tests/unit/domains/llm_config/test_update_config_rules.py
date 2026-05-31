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
