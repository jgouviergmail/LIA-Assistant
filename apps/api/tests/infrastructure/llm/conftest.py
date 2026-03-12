"""
Shared fixtures for LLM infrastructure tests.
"""

import pytest


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

        # Provider-specific config fields (JSON strings)
        router_llm_provider_config = "{}"
        response_llm_provider_config = "{}"
        contacts_agent_llm_provider_config = "{}"
        planner_llm_provider_config = "{}"
        hitl_classifier_llm_provider_config = "{}"

    return MockSettings()
