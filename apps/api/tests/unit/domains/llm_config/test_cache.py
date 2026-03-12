"""Tests for LLMConfigOverrideCache."""

from src.domains.llm_config.cache import LLMConfigOverrideCache


class TestLLMConfigOverrideCache:
    """Tests for the in-memory LLM config cache."""

    def setup_method(self) -> None:
        """Reset cache before each test."""
        LLMConfigOverrideCache.reset()

    def test_initial_state(self) -> None:
        """Cache should start empty and not loaded."""
        assert not LLMConfigOverrideCache.is_loaded()
        assert LLMConfigOverrideCache.get_override("router") is None
        assert LLMConfigOverrideCache.get_api_key("openai") is None

    def test_get_override_returns_none_when_empty(self) -> None:
        """get_override should return None for unknown types."""
        assert LLMConfigOverrideCache.get_override("nonexistent") is None

    def test_get_api_key_returns_none_when_empty(self) -> None:
        """get_api_key should return None for unknown providers."""
        assert LLMConfigOverrideCache.get_api_key("openai") is None

    def test_reset_clears_state(self) -> None:
        """reset() should clear all data."""
        # Simulate loaded state by directly setting internals
        LLMConfigOverrideCache._overrides = {"router": {"model": "test"}}
        LLMConfigOverrideCache._provider_keys = {"openai": "sk-test"}
        LLMConfigOverrideCache._loaded = True

        LLMConfigOverrideCache.reset()

        assert not LLMConfigOverrideCache.is_loaded()
        assert LLMConfigOverrideCache.get_override("router") is None
        assert LLMConfigOverrideCache.get_api_key("openai") is None

    def test_sync_reads(self) -> None:
        """get_override and get_api_key should be synchronous (no await)."""
        # These should work without event loop — they're dict lookups
        LLMConfigOverrideCache._overrides = {"router": {"model": "gpt-4.1-mini"}}
        LLMConfigOverrideCache._provider_keys = {"openai": "sk-test123"}

        assert LLMConfigOverrideCache.get_override("router") == {"model": "gpt-4.1-mini"}
        assert LLMConfigOverrideCache.get_api_key("openai") == "sk-test123"
