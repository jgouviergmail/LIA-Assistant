"""Integration tests for LLM Config Refactoring."""

import pytest

from src.core.config import settings
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_all_llm_configs, get_llm_config_for_agent
from src.infrastructure.llm.factory import get_llm


class TestLLMConfigIntegration:
    """Integration tests for new LLM config pattern."""

    @pytest.mark.integration
    def test_get_llm_with_real_settings(self):
        """Test get_llm with real settings (no override)."""
        # This test uses actual settings from .env
        llm = get_llm("router")

        assert llm is not None
        assert hasattr(llm, "callbacks")
        # Note: Callbacks are added at invocation time via enrich_config_with_node_metadata,
        # not at LLM creation time. The factory may or may not add callbacks depending on config.
        # Just verify the LLM was created successfully.

    @pytest.mark.integration
    def test_helper_function_with_real_settings(self):
        """Test helper function with real settings."""
        config = get_llm_config_for_agent(settings, "response")

        assert isinstance(config, LLMAgentConfig)
        assert config.provider in ["openai", "anthropic", "deepseek", "perplexity", "ollama"]
        assert config.temperature >= 0.0 and config.temperature <= 2.0
        assert config.max_tokens > 0

    @pytest.mark.integration
    def test_all_agents_can_create_llm(self):
        """Test all 6 agents can create LLM instances."""
        agents = [
            "router",
            "response",
            "contacts_agent",
            "planner",
            "hitl_classifier",
            "hitl_question_generator",
        ]

        for agent in agents:
            llm = get_llm(agent)
            assert llm is not None, f"Failed to create LLM for {agent}"

    @pytest.mark.integration
    def test_config_override_with_new_pattern(self):
        """Test config override with LLMAgentConfig."""
        base_config = get_llm_config_for_agent(settings, "router")

        # Create override by copying base and modifying temperature
        base_dict = base_config.model_dump()
        base_dict["temperature"] = 0.9
        override_config = LLMAgentConfig(**base_dict)

        llm = get_llm("router", config_override=override_config)
        assert llm is not None

    @pytest.mark.integration
    def test_config_override_with_old_pattern(self):
        """Test config override with TypedDict (backward compat)."""
        override_config = {"temperature": 0.9, "max_tokens": 8000}

        llm = get_llm("router", config_override=override_config)
        assert llm is not None

    @pytest.mark.integration
    def test_get_all_llm_configs_with_real_settings(self):
        """Test get_all_llm_configs returns configs for all configured agents."""
        configs = get_all_llm_configs(settings)

        # Should have at least 6 agents (core agents), may have more as agents are added
        assert len(configs) >= 6
        assert all(isinstance(config, LLMAgentConfig) for config in configs.values())

    @pytest.mark.integration
    @pytest.mark.skip(
        reason="Callbacks are now added at invocation time via enrich_config_with_node_metadata, "
        "not at LLM creation. Factory creates LLM without callbacks."
    )
    def test_llm_has_metrics_callback_attached(self):
        """Test that created LLM has metrics callback."""
        llm = get_llm("router")

        assert llm.callbacks is not None
        assert len(llm.callbacks) >= 1
        # At least one callback should be MetricsCallbackHandler
        has_metrics = any("MetricsCallbackHandler" in str(type(cb)) for cb in llm.callbacks)
        assert has_metrics, "No MetricsCallbackHandler found in callbacks"

    @pytest.mark.integration
    def test_provider_selection_from_settings(self):
        """Test that provider is correctly selected from settings."""
        config = get_llm_config_for_agent(settings, "router")

        # Verify provider matches settings
        assert config.provider == settings.router_llm_provider

    @pytest.mark.integration
    def test_model_selection_from_settings(self):
        """Test that model is correctly selected from settings."""
        config = get_llm_config_for_agent(settings, "response")

        # Verify model matches settings
        assert config.model == settings.response_llm_model

    @pytest.mark.integration
    def test_all_configs_have_valid_parameters(self):
        """Test all configs have valid Pydantic-validated parameters."""
        configs = get_all_llm_configs(settings)

        for agent, config in configs.items():
            # Temperature should be in valid range
            assert 0.0 <= config.temperature <= 2.0, f"{agent} has invalid temperature"

            # Max tokens should be positive
            assert config.max_tokens > 0, f"{agent} has invalid max_tokens"

            # Top_p should be in valid range
            assert 0.0 <= config.top_p <= 1.0, f"{agent} has invalid top_p"

            # Penalties should be in valid range
            assert -2.0 <= config.frequency_penalty <= 2.0, f"{agent} has invalid frequency_penalty"
            assert -2.0 <= config.presence_penalty <= 2.0, f"{agent} has invalid presence_penalty"
