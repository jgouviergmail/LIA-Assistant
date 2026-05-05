"""Unit tests for get_model_profile (cache-driven lookup).

Note on asyncio markers: this project sets ``asyncio_mode = "auto"`` in
``pyproject.toml`` — ``async def`` test functions are run automatically
without an explicit ``@pytest.mark.asyncio`` marker.
"""

from collections.abc import Generator
from unittest.mock import patch

import pytest

from src.infrastructure.llm.model_capabilities_cache import ModelCapabilitiesCache
from src.infrastructure.llm.model_profiles import (
    CONSERVATIVE_DEFAULT,
    ModelProfile,
    get_model_profile,
)


@pytest.fixture(autouse=True)
def reset_cache_between_tests() -> Generator[None, None, None]:
    ModelCapabilitiesCache.reset()
    yield
    ModelCapabilitiesCache.reset()


@pytest.mark.unit
def test_get_model_profile_returns_cache_hit() -> None:
    """When the cache has the model, return its ModelProfile."""
    cached = ModelProfile(max_input_tokens=12345, max_output_tokens=678)
    ModelCapabilitiesCache._cache = {"gpt-cached": cached}
    ModelCapabilitiesCache._loaded = True

    profile = get_model_profile(None, "openai", "gpt-cached")

    assert profile is cached
    assert profile.max_input_tokens == 12345
    assert profile.max_output_tokens == 678


@pytest.mark.unit
def test_get_model_profile_falls_back_to_normalized_name() -> None:
    """If the raw name misses, retry with normalize_model_name() (date suffixes)."""
    cached = ModelProfile(max_input_tokens=999, max_output_tokens=99)
    ModelCapabilitiesCache._cache = {"gpt-4.1-mini": cached}
    ModelCapabilitiesCache._loaded = True

    # Name with ISO date suffix should normalize to the cached key.
    profile = get_model_profile(None, "openai", "gpt-4.1-mini-2025-04-14")
    assert profile is cached


@pytest.mark.unit
def test_get_model_profile_returns_conservative_default_when_unknown() -> None:
    """No cache hit AND no native profile → CONSERVATIVE_DEFAULT."""
    ModelCapabilitiesCache._cache = {}
    ModelCapabilitiesCache._loaded = True

    profile = get_model_profile(None, "unknown-provider", "totally-unknown-model")

    assert profile is CONSERVATIVE_DEFAULT


@pytest.mark.unit
def test_get_model_profile_priorities_native_llm_profile_over_cache() -> None:
    """If the LLM exposes a .profile attribute (LangChain 1.1+), it wins over the cache."""

    class FakeNativeProfile:
        context_window = 65536
        max_tokens = 4096
        supports_structured_output = True
        supports_tool_calling = True
        supports_strict_mode = False
        supports_streaming = True
        supports_vision = False
        is_reasoning_model = False
        cost_per_1m_input = 1.0
        cost_per_1m_output = 5.0

    class FakeLLM:
        profile = FakeNativeProfile()

    # Cache has a different profile — must NOT win.
    ModelCapabilitiesCache._cache = {
        "test-model": ModelProfile(max_input_tokens=999, max_output_tokens=999)
    }
    ModelCapabilitiesCache._loaded = True

    profile = get_model_profile(FakeLLM(), "openai", "test-model")
    # Came from native profile, not the cache.
    assert profile.max_input_tokens == 65536
    assert profile.max_output_tokens == 4096


@pytest.mark.unit
def test_get_model_profile_treats_none_native_profile_as_absent() -> None:
    """If llm.profile is None, fall through to cache."""

    class LLMWithNoneProfile:
        profile = None

    cached = ModelProfile(max_input_tokens=42, max_output_tokens=7)
    ModelCapabilitiesCache._cache = {"x": cached}
    ModelCapabilitiesCache._loaded = True

    profile = get_model_profile(LLMWithNoneProfile(), "openai", "x")
    assert profile is cached


@pytest.mark.unit
def test_get_model_profile_logs_warning_when_falling_back_to_default() -> None:
    """Conservative-default fallback emits a warning so ops can spot misconfigured models."""
    ModelCapabilitiesCache._cache = {}
    ModelCapabilitiesCache._loaded = True

    with patch("src.infrastructure.llm.model_profiles.logger.warning") as mock_warning:
        get_model_profile(None, "openai", "missing-model")
    mock_warning.assert_called_once()
    args, kwargs = mock_warning.call_args
    assert "missing-model" in str(kwargs)
