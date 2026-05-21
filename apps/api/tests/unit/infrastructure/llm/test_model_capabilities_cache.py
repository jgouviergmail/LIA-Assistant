"""Unit tests for ModelCapabilitiesCache.

Note on asyncio markers: this project sets ``asyncio_mode = "auto"`` in
``pyproject.toml`` — ``async def`` test functions are run automatically
without an explicit ``@pytest.mark.asyncio`` marker.
"""

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import CACHE_NAME_MODEL_CAPABILITIES
from src.domains.llm.models import (
    LLMModelKindEnum,
    LLMProviderEnum,
    LLMReasoningWidgetEnum,
)
from src.domains.llm.repository import LLMModelRepository
from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import ModelProfile

# Reasoning + sampling block required by create_model() since v1.20.1. These
# tests exercise the capability cache, not reasoning specifics, so uniform
# non-reasoning defaults are sufficient.
_NON_REASONING_DEFAULTS: dict[str, Any] = {
    "kind": LLMModelKindEnum.chat,
    "reasoning_widget": LLMReasoningWidgetEnum.none,
    "reasoning_enum_values": None,
    "reasoning_budget_range": None,
    "reasoning_doc_i18n_key": None,
    "supports_temperature": True,
    "supports_top_p": True,
    "supports_frequency_penalty": True,
    "supports_presence_penalty": True,
}


@pytest.fixture(autouse=True)
def reset_cache_between_tests() -> Generator[None, None, None]:
    """Avoid bleed-over: reset the singleton between tests."""
    ModelCapabilitiesCache.reset()
    yield
    ModelCapabilitiesCache.reset()


@pytest.mark.unit
async def test_load_from_db_populates_cache_with_active_models_only(
    async_session: AsyncSession,
) -> None:
    repo = LLMModelRepository(async_session)
    await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="cap-cache-1",
        max_input_tokens=12345,
        max_output_tokens=678,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=True,
        supports_streaming=True,
        supports_vision=True,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    inactive = await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="cap-cache-inactive",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=False,
        supports_structured_output=False,
        supports_strict_mode=False,
        supports_streaming=False,
        supports_vision=False,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await repo.deactivate_by_id(inactive.id)

    await ModelCapabilitiesCache.load_from_db(async_session)

    assert ModelCapabilitiesCache.is_loaded() is True
    assert ModelCapabilitiesCache.get("cap-cache-1") is not None
    assert ModelCapabilitiesCache.get("cap-cache-inactive") is None


@pytest.mark.unit
async def test_get_returns_model_profile_with_correct_fields(
    async_session: AsyncSession,
) -> None:
    repo = LLMModelRepository(async_session)
    await repo.create_model(
        provider=LLMProviderEnum.anthropic,
        model_name="cap-cache-2",
        max_input_tokens=200000,
        max_output_tokens=8192,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=True,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await ModelCapabilitiesCache.load_from_db(async_session)

    profile = ModelCapabilitiesCache.get("cap-cache-2")
    assert isinstance(profile, ModelProfile)
    assert profile.max_input_tokens == 200000
    assert profile.max_output_tokens == 8192
    assert profile.supports_tool_calling is True
    assert profile.supports_structured_output is True
    assert profile.supports_strict_mode is False
    assert profile.supports_streaming is True
    assert profile.supports_vision is True
    assert profile.is_reasoning_model is False


@pytest.mark.unit
def test_get_returns_none_for_unknown_model() -> None:
    assert ModelCapabilitiesCache.get("does-not-exist") is None


@pytest.mark.unit
async def test_get_provider_returns_provider_string(async_session: AsyncSession) -> None:
    repo = LLMModelRepository(async_session)
    await repo.create_model(
        provider=LLMProviderEnum.deepseek,
        model_name="cap-cache-deepseek",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await ModelCapabilitiesCache.load_from_db(async_session)

    assert ModelCapabilitiesCache.get_provider("cap-cache-deepseek") == "deepseek"
    assert ModelCapabilitiesCache.get_provider("does-not-exist") is None


@pytest.mark.unit
async def test_get_models_grouped_by_provider(async_session: AsyncSession) -> None:
    repo = LLMModelRepository(async_session)
    await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="grouped-openai-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=True,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="grouped-openai-2",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=True,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await repo.create_model(
        provider=LLMProviderEnum.gemini,
        model_name="grouped-gemini-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=True,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await ModelCapabilitiesCache.load_from_db(async_session)

    grouped = ModelCapabilitiesCache.get_models_grouped_by_provider()
    assert grouped["openai"] == ["grouped-openai-1", "grouped-openai-2"]
    assert grouped["gemini"] == ["grouped-gemini-1"]


@pytest.mark.unit
async def test_invalidate_and_reload_swaps_data_and_publishes(
    async_session: AsyncSession,
) -> None:
    """invalidate_and_reload must reload from DB AND publish on the right channel.

    Mocking ``publish_cache_invalidation`` keeps the test offline-safe and lets
    us assert the channel name is correct (otherwise other workers would log
    ``cache_invalidation_unknown_cache`` and serve stale data).
    """
    repo = LLMModelRepository(async_session)
    await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="reload-1",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )
    await ModelCapabilitiesCache.load_from_db(async_session)
    assert ModelCapabilitiesCache.get("reload-1") is not None

    await repo.create_model(
        provider=LLMProviderEnum.openai,
        model_name="reload-2",
        max_input_tokens=1,
        max_output_tokens=1,
        supports_tools=True,
        supports_structured_output=True,
        supports_strict_mode=False,
        supports_streaming=True,
        supports_vision=False,
        is_reasoning_model=False,
        **_NON_REASONING_DEFAULTS,
    )

    # Patch the source module — invalidate_and_reload imports it lazily inside
    # the method, so we cannot patch the local-namespace symbol.
    with patch(
        "src.infrastructure.cache.invalidation.publish_cache_invalidation",
        new_callable=AsyncMock,
    ) as mock_publish:
        await ModelCapabilitiesCache.invalidate_and_reload(async_session)
        mock_publish.assert_awaited_once_with(CACHE_NAME_MODEL_CAPABILITIES)

    assert ModelCapabilitiesCache.get("reload-1") is not None
    assert ModelCapabilitiesCache.get("reload-2") is not None


@pytest.mark.unit
def test_is_loaded_initial_state() -> None:
    assert ModelCapabilitiesCache.is_loaded() is False


@pytest.mark.unit
def test_reset_clears_state() -> None:
    ModelCapabilitiesCache._cache = {"x": ModelProfile()}
    ModelCapabilitiesCache._provider_by_model = {"x": "openai"}
    ModelCapabilitiesCache._loaded = True
    ModelCapabilitiesCache.reset()
    assert ModelCapabilitiesCache.is_loaded() is False
    assert ModelCapabilitiesCache.get("x") is None
    assert ModelCapabilitiesCache.get_provider("x") is None
