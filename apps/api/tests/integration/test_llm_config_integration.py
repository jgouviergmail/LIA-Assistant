"""Integration tests for LLM Config Refactoring."""

import pytest

from src.core.config import settings
from src.core.llm_agent_config import LLMAgentConfig
from src.core.llm_config_helper import get_all_llm_configs, get_llm_config_for_agent
from src.domains.llm_config.constants import LLM_TYPES_REGISTRY
from src.infrastructure.llm.factory import get_llm

#: A slot that exists, taken FROM the registry rather than written by hand.
#:
#: These tests named ``router`` in six places until ADR-244 removed it (no
#: ``get_llm()`` caller anywhere), along with its ``router_llm_provider``
#: setting. Substituting another literal would only move the breakage to the
#: next removal; deriving it cannot go stale. Sorted so the choice is stable
#: between runs rather than dependent on dict ordering.
_A_SLOT = sorted(LLM_TYPES_REGISTRY)[0]


class TestLLMConfigIntegration:
    """Integration tests for new LLM config pattern."""

    @pytest.mark.integration
    def test_get_llm_with_real_settings(self):
        """Test get_llm with real settings (no override)."""
        # This test uses actual settings from .env
        llm = get_llm(_A_SLOT)

        assert llm is not None
        assert hasattr(llm, "callbacks")
        # Note: Callbacks are added at invocation time via enrich_config_with_node_metadata,
        # not at LLM creation time. The factory may or may not add callbacks depending on config.
        # Just verify the LLM was created successfully.

    @pytest.mark.integration
    def test_helper_function_with_real_settings(self):
        """Test helper function with real settings."""
        from typing import get_args

        from src.infrastructure.llm.providers.adapter import ProviderType

        config = get_llm_config_for_agent(settings, "response")

        # Drive the allowlist from the canonical `ProviderType` Literal so the
        # assertion automatically tracks any new provider added there (Gemini,
        # Qwen, etc.) instead of silently going stale.
        supported_providers = list(get_args(ProviderType))

        assert isinstance(config, LLMAgentConfig)
        assert config.provider in supported_providers
        assert config.temperature >= 0.0 and config.temperature <= 2.0
        assert config.max_tokens > 0

    @pytest.mark.integration
    def test_every_llm_backed_slot_can_create_an_llm(self):
        """Every slot backed by an LLM provider, not a hand-kept sample of six.

        The list used to be written by hand and led with ``router``; when that
        slot was removed the test failed for the one reason it was never meant
        to catch. Deriving it cannot go stale.

        "Every slot" would be too strong: the registry also holds slots served
        by providers that are not LLMs at all -- ``voice_tts`` runs on
        ElevenLabs -- and ``get_llm`` refuses those on purpose. The contract is
        therefore drawn against ``ProviderType``, the canonical Literal.
        """
        from typing import get_args

        from src.infrastructure.llm.providers.adapter import ProviderType

        llm_providers = set(get_args(ProviderType))
        checked = 0
        for agent in sorted(LLM_TYPES_REGISTRY):
            config = get_llm_config_for_agent(settings, agent)
            if config.provider not in llm_providers:
                continue
            llm = get_llm(agent)
            assert llm is not None, f"Failed to create LLM for {agent}"
            checked += 1

        assert checked >= 6, f"only {checked} LLM-backed slots found — the registry looks empty"

    @pytest.mark.integration
    def test_config_override_with_new_pattern(self):
        """Test config override with LLMAgentConfig."""
        base_config = get_llm_config_for_agent(settings, _A_SLOT)

        # Create override by copying base and modifying temperature
        base_dict = base_config.model_dump()
        base_dict["temperature"] = 0.9
        override_config = LLMAgentConfig(**base_dict)

        llm = get_llm(_A_SLOT, config_override=override_config)
        assert llm is not None

    @pytest.mark.integration
    def test_config_override_with_old_pattern(self):
        """Test config override with TypedDict (backward compat)."""
        override_config = {"temperature": 0.9, "max_tokens": 8000}

        llm = get_llm(_A_SLOT, config_override=override_config)
        assert llm is not None

    @pytest.mark.integration
    def test_get_all_llm_configs_with_real_settings(self):
        """Test get_all_llm_configs returns configs for all configured agents."""
        configs = get_all_llm_configs(settings)

        # Should have at least 6 agents (core agents), may have more as agents are added
        assert len(configs) >= 6
        assert all(isinstance(config, LLMAgentConfig) for config in configs.values())

    @pytest.mark.integration
    def test_metrics_callback_attached_at_invocation_boundary(self):
        """Metrics callbacks attach PER-INVOCATION, not at LLM creation.

        The factory deliberately creates callback-less LLMs; every node calls
        ``enrich_config_with_node_metadata`` before invoking, which injects a
        fresh ``MetricsCallbackHandler`` carrying the node name (dynamic
        node_name tracking is impossible with creation-time callbacks) and
        stamps ``metadata["langgraph_node"]``.
        """
        from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
        from src.infrastructure.observability.callbacks import MetricsCallbackHandler

        # Creation time: no callbacks, by design.
        llm = get_llm(_A_SLOT)
        assert not llm.callbacks

        # Invocation boundary: the enriched config carries the metrics handler
        # with the node name, and preserves pre-existing metadata.
        enriched = enrich_config_with_node_metadata({"metadata": {"run_id": "t-1"}}, _A_SLOT)

        callbacks = enriched.get("callbacks") or []
        metrics_handlers = [cb for cb in callbacks if isinstance(cb, MetricsCallbackHandler)]
        assert len(metrics_handlers) == 1, "exactly one MetricsCallbackHandler per invocation"
        assert metrics_handlers[0].node_name == _A_SLOT

        metadata = enriched.get("metadata") or {}
        assert metadata.get("langgraph_node") == _A_SLOT
        assert metadata.get("run_id") == "t-1"

    @pytest.mark.integration
    def test_provider_selection_from_settings(self):
        """The resolved provider is the one the matching setting declares.

        Read through ``getattr`` on the slot's own field rather than a literal
        ``settings.router_llm_provider``: that attribute went with the slot,
        and an AttributeError is a poor way to learn a registry changed.
        """
        config = get_llm_config_for_agent(settings, _A_SLOT)

        declared = getattr(settings, f"{_A_SLOT}_llm_provider", None)
        if declared is not None:
            assert config.provider == declared

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
