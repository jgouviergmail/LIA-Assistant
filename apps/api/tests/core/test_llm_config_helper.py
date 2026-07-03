"""Unit tests for LLM Config Helper.

Tests the resolution flow: LLM_DEFAULTS (code) → DB override cache → Effective config.
The `settings` parameter is kept for backward compatibility but ignored.
"""

from unittest.mock import patch

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_all_llm_configs, get_llm_config_for_agent
from src.core.reasoning_types import ReasoningEffortEnum
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
    """Tests for get_llm_config_for_agent function (reads from LLM_DEFAULTS).

    Assertions are relative to LLM_DEFAULTS (the single source of truth): the
    tests verify the resolution mechanism, not frozen business values —
    hardcoded models/temperatures silently drift when defaults evolve.
    """

    @pytest.mark.parametrize(
        "agent_type",
        [
            "router",
            "response",
            "planner",
            "contacts_agent",
            "hitl_classifier",
            "hitl_question_generator",
        ],
    )
    def test_returns_defaults(self, agent_type):
        """Test config without override is exactly the LLM_DEFAULTS entry."""
        config = get_llm_config_for_agent(None, agent_type)

        assert isinstance(config, LLMAgentConfig)
        assert config == LLM_DEFAULTS[agent_type]

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
        assert config.provider == LLM_DEFAULTS["router"].provider  # From defaults
        assert config.temperature == LLM_DEFAULTS["router"].temperature  # From defaults

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
    """Tests for reasoning_effort parameter support in LLMAgentConfig.

    reasoning_effort is a discriminated union of pydantic models (enum /
    budget / toggle_budget shapes) stored as JSONB dicts in overrides —
    never a bare string.
    """

    def test_reasoning_effort_has_production_value(self):
        """Test reasoning_effort is set in LLM_DEFAULTS for reasoning-capable types."""
        config = get_llm_config_for_agent(None, "router")
        assert config.reasoning_effort is not None
        assert config.reasoning_effort == LLM_DEFAULTS["router"].reasoning_effort

    def test_reasoning_effort_none_for_non_reasoning_types(self):
        """Test reasoning_effort resolves to None for types without a reasoning default."""
        none_types = [k for k, v in LLM_DEFAULTS.items() if v.reasoning_effort is None]
        assert none_types, "expected at least one agent type without reasoning default"
        config = get_llm_config_for_agent(None, none_types[0])
        assert config.reasoning_effort is None

    def test_reasoning_effort_via_override(self):
        """Test reasoning_effort can be set via DB override (JSONB dict shape)."""
        with patch(
            "src.domains.llm_config.cache.LLMConfigOverrideCache.get_override",
            return_value={"reasoning_effort": {"effort": "medium"}, "model": "o3-mini"},
        ):
            config = get_llm_config_for_agent(None, "planner")

        assert config.reasoning_effort == ReasoningEffortEnum(effort="medium")
        assert config.model == "o3-mini"
