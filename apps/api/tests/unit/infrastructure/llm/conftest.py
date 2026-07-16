"""
Shared fixtures for LLM infrastructure tests.
"""

from unittest.mock import patch

import pytest

# Deterministic provider keys for tests. Provider API keys are resolved from
# the DB-backed LLMConfigOverrideCache (Admin UI) since the key migration —
# NOT from settings — so tests must stub the cache lookup, not settings.
TEST_PROVIDER_KEYS = {
    "openai": "sk-test-openai-key",
    "anthropic": "sk-test-anthropic-key",
    "deepseek": "sk-test-deepseek-key",
    "perplexity": "pplx-test-key",
    # For Ollama the DB-stored "key" IS the base URL (see _ENV_FALLBACK)
    "ollama": "http://localhost:11434/v1",
}


@pytest.fixture(autouse=True)
def mock_provider_api_keys():
    """Stub LLMConfigOverrideCache.get_api_key with deterministic test keys.

    Autouse for the whole LLM infrastructure test tree: harmless for tests
    that mock ProviderAdapter entirely (the lookup is never reached) and for
    tests that patch the cache locally (their patch takes precedence).
    """
    from src.domains.llm_config.cache import LLMConfigOverrideCache

    with patch.object(
        LLMConfigOverrideCache,
        "get_api_key",
        side_effect=lambda provider: TEST_PROVIDER_KEYS.get(provider),
    ):
        yield


@pytest.fixture
def mock_settings_class():
    """Mock settings class with all provider credentials and config fields."""

    class MockSettings:
        # Provider credentials
        openai_api_key = "sk-test-openai-key"
        anthropic_api_key = "sk-test-anthropic-key"
        deepseek_api_key = "sk-test-deepseek-key"
        perplexity_api_key = "pplx-test-key"
        ollama_base_url = "http://localhost:11434/v1"
        # Must be a real string: a bare MagicMock here is truthy AND fails
        # pydantic validation when passed to ChatOpenAI(organization=...)
        openai_organization_id = ""

        # Provider-specific config fields (JSON strings)
        router_llm_provider_config = "{}"
        response_llm_provider_config = "{}"
        contacts_agent_llm_provider_config = "{}"
        planner_llm_provider_config = "{}"
        hitl_classifier_llm_provider_config = "{}"

    return MockSettings()
