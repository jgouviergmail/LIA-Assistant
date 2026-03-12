"""
Unit tests for token counter service.

Phase: Session 8 - Tests Services
Created: 2025-11-20

Focus: Token counting, fallback levels, safety checks
"""

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from src.domains.agents.services.token_counter_service import (
    TOKEN_THRESHOLD_CRITICAL,
    TOKEN_THRESHOLD_MAX,
    TOKEN_THRESHOLD_SAFE,
    TOKEN_THRESHOLD_WARNING,
    FallbackLevel,
    TokenCounterService,
    get_token_counter,
)


@pytest.fixture
def token_counter():
    """Provide TokenCounterService instance."""
    return TokenCounterService(model_name="gpt-4")


class TestFallbackLevel:
    def test_fallback_level_constants(self):
        """Test that fallback level constants are defined."""
        assert FallbackLevel.FULL_CATALOGUE == "full_catalogue"
        assert FallbackLevel.FILTERED_CATALOGUE == "filtered_catalogue"
        assert FallbackLevel.REDUCED_DESCRIPTIONS == "reduced_descriptions"
        assert FallbackLevel.PRIMARY_DOMAIN_ONLY == "primary_domain_only"
        assert FallbackLevel.SIMPLE_SEARCH == "simple_search"


class TestCountTokens:
    def test_count_tokens_empty_string(self, token_counter):
        """Test counting tokens for empty string."""
        count = token_counter.count_tokens("")
        assert count == 0

    def test_count_tokens_simple_text(self, token_counter):
        """Test counting tokens for simple text."""
        count = token_counter.count_tokens("Hello, world!")
        assert count > 0
        assert count < 10  # Should be a few tokens

    def test_count_tokens_longer_text(self, token_counter):
        """Test counting tokens for longer text."""
        text = "This is a longer text " * 100  # ~500 words
        count = token_counter.count_tokens(text)
        assert count > 100  # Should be many tokens


class TestCountMessageTokens:
    def test_count_message_tokens_human_message(self, token_counter):
        """Test counting tokens for human message."""
        message = HumanMessage(content="Hello, how are you?")
        count = token_counter.count_message_tokens(message)
        assert count > 0

    def test_count_message_tokens_system_message(self, token_counter):
        """Test counting tokens for system message."""
        message = SystemMessage(content="You are a helpful assistant.")
        count = token_counter.count_message_tokens(message)
        assert count > 0

    def test_count_message_tokens_empty_content(self, token_counter):
        """Test counting tokens for message with empty content."""
        message = HumanMessage(content="")
        count = token_counter.count_message_tokens(message)
        assert count >= 0  # May have overhead tokens


class TestCountMessagesTokens:
    def test_count_messages_tokens_empty_list(self, token_counter):
        """Test counting tokens for empty message list."""
        count = token_counter.count_messages_tokens([])
        assert count == 0

    def test_count_messages_tokens_single_message(self, token_counter):
        """Test counting tokens for single message."""
        messages = [HumanMessage(content="Hello")]
        count = token_counter.count_messages_tokens(messages)
        assert count > 0

    def test_count_messages_tokens_multiple_messages(self, token_counter):
        """Test counting tokens for multiple messages."""
        messages = [
            SystemMessage(content="You are helpful."),
            HumanMessage(content="What is Python?"),
            HumanMessage(content="Tell me more."),
        ]
        count = token_counter.count_messages_tokens(messages)
        assert count > 0


class TestIsSafePrompt:
    def test_is_safe_prompt_below_threshold(self, token_counter):
        """Test that token count below safe threshold is safe."""
        assert token_counter.is_safe_prompt(TOKEN_THRESHOLD_SAFE - 100) is True

    def test_is_safe_prompt_at_threshold(self, token_counter):
        """Test that token count at safe threshold is safe."""
        assert token_counter.is_safe_prompt(TOKEN_THRESHOLD_SAFE) is True

    def test_is_safe_prompt_above_threshold(self, token_counter):
        """Test that token count above safe threshold is unsafe."""
        assert token_counter.is_safe_prompt(TOKEN_THRESHOLD_SAFE + 1) is False

    def test_is_safe_prompt_with_custom_max_tokens(self, token_counter):
        """Test is_safe_prompt with custom max_tokens."""
        custom_max = 5000
        assert token_counter.is_safe_prompt(4999, max_tokens=custom_max) is True
        assert token_counter.is_safe_prompt(5001, max_tokens=custom_max) is False


class TestGetFallbackLevel:
    def test_get_fallback_level_safe(self, token_counter):
        """Test fallback level for safe token count."""
        level = token_counter.get_fallback_level(TOKEN_THRESHOLD_SAFE - 100)
        assert level == FallbackLevel.FULL_CATALOGUE

    def test_get_fallback_level_warning(self, token_counter):
        """Test fallback level for warning token count (6000-7000)."""
        level = token_counter.get_fallback_level(
            TOKEN_THRESHOLD_SAFE + 1000
        )  # Between SAFE and WARNING
        assert level == FallbackLevel.FILTERED_CATALOGUE

    def test_get_fallback_level_critical(self, token_counter):
        """Test fallback level for critical token count (7000-8000)."""
        level = token_counter.get_fallback_level(
            TOKEN_THRESHOLD_WARNING + 1000
        )  # Between WARNING and CRITICAL
        assert level == FallbackLevel.REDUCED_DESCRIPTIONS

    def test_get_fallback_level_max(self, token_counter):
        """Test fallback level for max token count (8000-9000)."""
        level = token_counter.get_fallback_level(
            TOKEN_THRESHOLD_CRITICAL + 1000
        )  # Between CRITICAL and MAX
        assert level == FallbackLevel.PRIMARY_DOMAIN_ONLY

    def test_get_fallback_level_overflow(self, token_counter):
        """Test fallback level for extreme overflow."""
        level = token_counter.get_fallback_level(TOKEN_THRESHOLD_MAX + 5000)  # Way over limit
        assert level == FallbackLevel.SIMPLE_SEARCH


class TestShouldTriggerFallback:
    def test_should_trigger_fallback_safe(self, token_counter):
        """Test that safe token count doesn't trigger fallback."""
        should_trigger, level = token_counter.should_trigger_fallback(TOKEN_THRESHOLD_SAFE - 100)
        assert should_trigger is False
        assert level == FallbackLevel.FULL_CATALOGUE

    def test_should_trigger_fallback_warning(self, token_counter):
        """Test that warning token count triggers fallback."""
        should_trigger, level = token_counter.should_trigger_fallback(
            TOKEN_THRESHOLD_WARNING + 1000
        )  # In WARNING range
        assert should_trigger is True
        assert level == FallbackLevel.REDUCED_DESCRIPTIONS

    def test_should_trigger_fallback_critical(self, token_counter):
        """Test that critical token count triggers fallback."""
        should_trigger, level = token_counter.should_trigger_fallback(
            TOKEN_THRESHOLD_CRITICAL + 1000
        )  # In CRITICAL range
        assert should_trigger is True
        assert level == FallbackLevel.PRIMARY_DOMAIN_ONLY


class TestClearCache:
    def test_clear_cache_does_not_crash(self, token_counter):
        """Test that clear_cache executes without error."""
        # Count some tokens to populate cache
        token_counter.count_tokens("Hello")

        # Clear cache
        token_counter.clear_cache()

        # Should still work after clearing
        count = token_counter.count_tokens("Hello again")
        assert count > 0


class TestGetTokenCounter:
    def test_get_token_counter_returns_instance(self):
        """Test that get_token_counter returns TokenCounterService instance."""
        counter = get_token_counter()
        assert isinstance(counter, TokenCounterService)

    def test_get_token_counter_returns_singleton(self):
        """Test that get_token_counter returns same instance."""
        counter1 = get_token_counter()
        counter2 = get_token_counter()
        assert counter1 is counter2


class TestModelName:
    def test_default_model_name(self):
        """Test that default model name is gpt-4."""
        counter = TokenCounterService()
        assert counter.model_name == "gpt-4"

    def test_custom_model_name(self):
        """Test that custom model name is used."""
        counter = TokenCounterService(model_name="gpt-3.5-turbo")
        assert counter.model_name == "gpt-3.5-turbo"


class TestCountCatalogueTokens:
    def test_count_catalogue_tokens_empty_dict(self, token_counter):
        """Test counting tokens for empty catalogue."""
        count = token_counter.count_catalogue_tokens({})
        assert count >= 0  # Empty JSON still has {} characters

    def test_count_catalogue_tokens_simple_catalogue(self, token_counter):
        """Test counting tokens for simple catalogue."""
        catalogue = {
            "tools": [
                {"name": "search", "description": "Search for information"},
                {"name": "calculate", "description": "Perform calculations"},
            ]
        }
        count = token_counter.count_catalogue_tokens(catalogue)
        assert count > 0

    def test_count_catalogue_tokens_large_catalogue(self, token_counter):
        """Test counting tokens for large catalogue."""
        catalogue = {
            "tools": [
                {"name": f"tool_{i}", "description": f"Description {i}" * 10} for i in range(100)
            ]
        }
        count = token_counter.count_catalogue_tokens(catalogue)
        assert count > 1000  # Should be many tokens
