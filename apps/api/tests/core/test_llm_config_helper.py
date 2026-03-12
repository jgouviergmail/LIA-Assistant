"""Unit tests for LLM Config Helper.

Tests the resolution flow: LLM_DEFAULTS (code) → DB override cache → Effective config.
The `settings` parameter is kept for backward compatibility but ignored.
"""

from unittest.mock import patch

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_all_llm_configs, get_llm_config_for_agent
from src.domains.llm_config.constants import LLM_DEFAULTS


@pytest.fixture(autouse=True)
def _no_cache_overrides():
    """Ensure no cache overrides interfere with tests."""
    with patch(
        "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
        return_value=None,
    ):
        yield


class TestGetLLMConfigForAgent:
    """Tests for get_llm_config_for_agent function (reads from LLM_DEFAULTS)."""

    def test_router_returns_defaults(self):
        """Test router config comes from LLM_DEFAULTS."""
        config = get_llm_config_for_agent(None, "router")

        assert isinstance(config, LLMAgentConfig)
        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.temperature == 0.0
        assert config.max_tokens == 1000
        assert config.reasoning_effort == "minimal"

    def test_response_returns_defaults(self):
        """Test response config comes from LLM_DEFAULTS."""
        config = get_llm_config_for_agent(None, "response")

        assert config.provider == "openai"
        assert config.model == "gpt-4.1-mini"
        assert config.temperature == 0.5
        assert config.max_tokens == 5000
        assert config.frequency_penalty == 0.1

    def test_planner_returns_defaults(self):
        """Test planner config comes from LLM_DEFAULTS."""
        config = get_llm_config_for_agent(None, "planner")

        assert config.provider == "openai"
        assert config.model == "gpt-5.1"
        assert config.temperature == 0.0
        assert config.timeout_seconds == 30
        assert config.max_tokens == 20000
        assert config.reasoning_effort == "low"

    def test_contacts_agent_returns_defaults(self):
        """Test contacts_agent config comes from LLM_DEFAULTS."""
        config = get_llm_config_for_agent(None, "contacts_agent")

        assert config.provider == "openai"
        assert config.model == "gpt-5-nano"
        assert config.temperature == 0.0
        assert config.reasoning_effort == "minimal"

    def test_hitl_classifier_returns_defaults(self):
        """Test hitl_classifier config comes from LLM_DEFAULTS."""
        config = get_llm_config_for_agent(None, "hitl_classifier")

        assert config.provider == "openai"
        assert config.model == "gpt-5-nano"
        assert config.temperature == 0.0
        assert config.reasoning_effort == "minimal"

    def test_hitl_question_generator_returns_defaults(self):
        """Test hitl_question_generator config comes from LLM_DEFAULTS."""
        config = get_llm_config_for_agent(None, "hitl_question_generator")

        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.temperature == 0.5
        assert config.frequency_penalty == 0.7
        assert config.presence_penalty == 0.3

    def test_all_registered_types_supported(self):
        """Test all LLM_DEFAULTS types return valid configs."""
        for agent_type in LLM_DEFAULTS:
            config = get_llm_config_for_agent(None, agent_type)
            assert isinstance(config, LLMAgentConfig), f"{agent_type} failed"

    def test_invalid_agent_type_raises_error(self):
        """Test invalid agent type raises ValueError."""
        with pytest.raises(ValueError, match="Unknown agent_type 'invalid'"):
            get_llm_config_for_agent(None, "invalid")

    def test_alias_contact_agent(self):
        """Test alias 'contact_agent' → 'contacts_agent'."""
        config = get_llm_config_for_agent(None, "contact_agent")
        expected = get_llm_config_for_agent(None, "contacts_agent")
        assert config == expected

    def test_alias_email_agent(self):
        """Test alias 'email_agent' → 'emails_agent'."""
        config = get_llm_config_for_agent(None, "email_agent")
        expected = get_llm_config_for_agent(None, "emails_agent")
        assert config == expected

    def test_settings_parameter_is_ignored(self):
        """Test settings parameter is accepted but ignored."""
        config_none = get_llm_config_for_agent(None, "router")
        config_obj = get_llm_config_for_agent(object(), "router")
        assert config_none == config_obj


class TestCacheOverrideMerge:
    """Tests for DB override merging via LLMConfigOverrideCache."""

    def test_override_model_only(self):
        """Test partial override (only model) merges with defaults."""
        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
            return_value={"model": "gpt-4.1-mini"},
        ):
            config = get_llm_config_for_agent(None, "router")

        assert config.model == "gpt-4.1-mini"  # Overridden
        assert config.provider == "openai"  # From defaults
        assert config.temperature == 0.0  # From defaults

    def test_override_multiple_fields(self):
        """Test multiple field overrides merge correctly."""
        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
            return_value={
                "model": "claude-sonnet-4-5",
                "provider": "anthropic",
                "temperature": 0.7,
            },
        ):
            config = get_llm_config_for_agent(None, "router")

        assert config.model == "claude-sonnet-4-5"
        assert config.provider == "anthropic"
        assert config.temperature == 0.7
        assert config.top_p == 1.0  # From defaults

    def test_no_override_returns_defaults(self):
        """Test None override returns pure defaults."""
        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
            return_value=None,
        ):
            config = get_llm_config_for_agent(None, "router")

        assert config == LLM_DEFAULTS["router"]


class TestGetAllLLMConfigs:
    """Tests for get_all_llm_configs function."""

    def test_returns_all_registered_types(self):
        """Test returns dict with all LLM_DEFAULTS types."""
        configs = get_all_llm_configs(None)

        assert len(configs) == len(LLM_DEFAULTS)
        for agent_type in LLM_DEFAULTS:
            assert agent_type in configs

    def test_all_configs_are_llm_agent_config_instances(self):
        """Test all values are LLMAgentConfig instances."""
        configs = get_all_llm_configs(None)

        for agent, config in configs.items():
            assert isinstance(config, LLMAgentConfig), f"{agent} not LLMAgentConfig"

    def test_configs_serialize_to_dict(self):
        """Test configs can be serialized to dict."""
        configs = get_all_llm_configs(None)

        for _agent, config in configs.items():
            config_dict = config.model_dump()
            assert isinstance(config_dict, dict)
            assert "provider" in config_dict
            assert "model" in config_dict
            assert "temperature" in config_dict


class TestReasoningEffortSupport:
    """Tests for reasoning_effort parameter support in LLMAgentConfig."""

    def test_reasoning_effort_has_production_value(self):
        """Test reasoning_effort is set in LLM_DEFAULTS for reasoning-capable types."""
        config = get_llm_config_for_agent(None, "router")
        assert config.reasoning_effort == "minimal"

    def test_reasoning_effort_none_for_non_reasoning_types(self):
        """Test reasoning_effort is None for types without reasoning (heartbeat, etc.)."""
        config = get_llm_config_for_agent(None, "heartbeat_decision")
        assert config.reasoning_effort is None

    def test_reasoning_effort_via_override(self):
        """Test reasoning_effort can be set via DB override."""
        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
            return_value={"reasoning_effort": "medium", "model": "o3-mini"},
        ):
            config = get_llm_config_for_agent(None, "planner")

        assert config.reasoning_effort == "medium"
        assert config.model == "o3-mini"
