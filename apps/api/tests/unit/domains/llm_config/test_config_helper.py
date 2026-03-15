"""Tests for the rewritten get_llm_config_for_agent (code = source of truth)."""

from unittest.mock import MagicMock

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.llm_config.cache import LLMConfigOverrideCache


class TestGetLLMConfigForAgent:
    """Tests for get_llm_config_for_agent with code defaults + cache overrides."""

    def setup_method(self) -> None:
        """Reset cache before each test."""
        LLMConfigOverrideCache.reset()

    def test_returns_code_defaults_when_no_override(self) -> None:
        """Should return LLM_DEFAULTS when no DB override exists."""
        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "router")

        assert isinstance(config, LLMAgentConfig)
        assert config.provider == "openai"
        assert config.model == "gpt-5-mini"
        assert config.temperature == 0.0
        assert config.max_tokens == 1000

    def test_applies_cache_override(self) -> None:
        """Should merge DB override on top of code defaults."""
        LLMConfigOverrideCache._overrides = {
            "router": {"model": "gpt-4.1-mini", "temperature": 0.5}
        }

        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "router")

        # Overridden fields
        assert config.model == "gpt-4.1-mini"
        assert config.temperature == 0.5
        # Non-overridden fields keep defaults
        assert config.provider == "openai"
        assert config.max_tokens == 1000
        assert config.top_p == 1.0

    def test_alias_resolution(self) -> None:
        """Aliases like 'contact_agent' should resolve to 'contacts_agent'."""
        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "contact_agent")

        assert isinstance(config, LLMAgentConfig)
        assert config.provider == "openai"

    def test_unknown_type_raises_error(self) -> None:
        """Should raise ValueError for unknown agent types."""
        settings = MagicMock()
        with pytest.raises(ValueError, match="Unknown agent_type"):
            get_llm_config_for_agent(settings, "nonexistent_type")

    def test_settings_parameter_not_used(self) -> None:
        """Settings parameter should not be accessed (code = source of truth)."""
        settings = MagicMock()
        get_llm_config_for_agent(settings, "router")

        # Settings should not have been accessed for any LLM config attribute
        assert not settings.router_llm_provider.called
        assert not settings.router_llm_model.called

    def test_all_34_types_resolve(self) -> None:
        """All 34 LLM types should resolve without error."""
        from src.domains.llm_config.constants import LLM_DEFAULTS

        settings = MagicMock()
        for llm_type in LLM_DEFAULTS:
            config = get_llm_config_for_agent(settings, llm_type)
            assert isinstance(config, LLMAgentConfig), f"Failed for type: {llm_type}"

    def test_special_types_resolve(self) -> None:
        """Previously special types should now resolve through the unified path."""
        settings = MagicMock()
        special_types = [
            "heartbeat_decision",
            "heartbeat_message",
            "mcp_excalidraw",
            "mcp_description",
            "memory_extraction",
            "interest_extraction",
            "interest_content",
        ]
        for llm_type in special_types:
            config = get_llm_config_for_agent(settings, llm_type)
            assert isinstance(config, LLMAgentConfig), f"Failed for type: {llm_type}"

    def test_partial_override_preserves_defaults(self) -> None:
        """Override with only temperature should preserve all other defaults."""
        LLMConfigOverrideCache._overrides = {"response": {"temperature": 0.9}}

        settings = MagicMock()
        config = get_llm_config_for_agent(settings, "response")

        assert config.temperature == 0.9
        assert config.model == "claude-sonnet-4-6"  # Default preserved
        assert config.max_tokens == 5000  # Default preserved
        assert config.provider == "anthropic"  # Default preserved
