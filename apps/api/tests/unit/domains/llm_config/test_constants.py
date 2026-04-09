"""Tests for LLM config constants (LLM_TYPES_REGISTRY + LLM_DEFAULTS)."""

import pytest

from src.core.llm_agent_config import LLMAgentConfig
from src.domains.llm_config.constants import (
    LLM_CATEGORIES_ORDER,
    LLM_DEFAULTS,
    LLM_PROVIDERS,
    LLM_TYPES_REGISTRY,
    LLMTypeMetadata,
)


class TestLLMDefaults:
    """Tests for LLM_DEFAULTS dictionary."""

    def test_all_registry_types_have_defaults(self) -> None:
        """Every type in the registry must have a corresponding default config."""
        for llm_type in LLM_TYPES_REGISTRY:
            assert (
                llm_type in LLM_DEFAULTS
            ), f"LLM_TYPES_REGISTRY has '{llm_type}' but LLM_DEFAULTS does not"

    def test_all_defaults_have_registry_entry(self) -> None:
        """Every default config must have a corresponding registry entry."""
        for llm_type in LLM_DEFAULTS:
            assert (
                llm_type in LLM_TYPES_REGISTRY
            ), f"LLM_DEFAULTS has '{llm_type}' but LLM_TYPES_REGISTRY does not"

    def test_defaults_are_llm_agent_config(self) -> None:
        """All defaults must be LLMAgentConfig instances."""
        for llm_type, config in LLM_DEFAULTS.items():
            assert isinstance(
                config, LLMAgentConfig
            ), f"LLM_DEFAULTS['{llm_type}'] is {type(config)}, expected LLMAgentConfig"

    def test_default_count(self) -> None:
        """Should have 48 LLM types (including memory_reference_extraction)."""
        assert len(LLM_DEFAULTS) == 48

    @pytest.mark.parametrize(
        "llm_type,expected_provider,expected_model",
        [
            ("router", "openai", "gpt-5-mini"),
            ("response", "qwen", "qwen3.5-plus"),
            ("planner", "qwen", "qwen3.5-plus"),
            ("mcp_app_react_agent", "qwen", "qwen3.6-plus"),
            ("subagent", "qwen", "qwen3.5-plus"),
        ],
    )
    def test_key_defaults(self, llm_type: str, expected_provider: str, expected_model: str) -> None:
        """Verify key default values."""
        config = LLM_DEFAULTS[llm_type]
        assert config.provider == expected_provider
        assert config.model == expected_model

    def test_planner_has_timeout(self) -> None:
        """Planner should have a 30s timeout."""
        assert LLM_DEFAULTS["planner"].timeout_seconds == 30

    def test_mcp_app_react_agent_has_timeout(self) -> None:
        """MCP App ReAct agent should have a 60s timeout."""
        assert LLM_DEFAULTS["mcp_app_react_agent"].timeout_seconds == 60


class TestLLMTypesRegistry:
    """Tests for LLM_TYPES_REGISTRY."""

    def test_registry_entries_are_metadata(self) -> None:
        """All entries should be LLMTypeMetadata instances."""
        for llm_type, meta in LLM_TYPES_REGISTRY.items():
            assert isinstance(meta, LLMTypeMetadata)
            assert meta.llm_type == llm_type

    def test_all_categories_in_order(self) -> None:
        """All categories used in registry should be in LLM_CATEGORIES_ORDER."""
        used_categories = {m.category for m in LLM_TYPES_REGISTRY.values()}
        for cat in used_categories:
            assert (
                cat in LLM_CATEGORIES_ORDER
            ), f"Category '{cat}' used in registry but not in LLM_CATEGORIES_ORDER"


class TestLLMProviders:
    """Tests for LLM_PROVIDERS."""

    def test_known_providers(self) -> None:
        """Should have all 7 known providers."""
        expected = {"openai", "anthropic", "deepseek", "perplexity", "ollama", "gemini", "qwen"}
        assert set(LLM_PROVIDERS.keys()) == expected
