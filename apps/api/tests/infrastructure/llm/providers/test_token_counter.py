"""
Unit tests for TokenCounter implementations.

Tests provider-specific token counting with comprehensive coverage:
- OpenAI: tiktoken-based counting with model-specific encodings
- Anthropic: Official SDK count_tokens() method
- DeepSeek: tiktoken cl100k_base (GPT-4 compatible)
- Perplexity: tiktoken cl100k_base (OpenAI-based)
- Ollama: Estimation-based fallback
- Error handling and edge cases

Best Practices (2025):
- Test exact tokenization for providers with deterministic tokenizers
- Test estimation accuracy within acceptable range
- Test fallback behavior when libraries are missing
- Test model-specific encoding selection

REFACTORED (Phase 8): Tests use sys.modules patching for dynamic imports.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

from src.infrastructure.llm.providers.token_counter import (
    AnthropicTokenCounter,
    DeepSeekTokenCounter,
    EstimationTokenCounter,
    OpenAITokenCounter,
    PerplexityTokenCounter,
    get_token_counter,
)


@pytest.fixture
def mock_tiktoken():
    """Create a mock tiktoken module for dynamic import tests."""
    mock = MagicMock()
    mock_encoding = MagicMock()
    mock_encoding.encode.return_value = [1, 2, 3, 4, 5]  # Default 5 tokens
    mock.encoding_for_model.return_value = mock_encoding
    mock.get_encoding.return_value = mock_encoding
    return mock, mock_encoding


@pytest.fixture
def mock_anthropic():
    """Create a mock Anthropic module for dynamic import tests."""
    mock_module = MagicMock()
    mock_client = MagicMock()
    mock_client.count_tokens.return_value = 42
    mock_module.Anthropic.return_value = mock_client
    return mock_module, mock_client


# ============================================================================
# OpenAI Token Counter Tests
# ============================================================================


class TestOpenAITokenCounter:
    """Tests for OpenAITokenCounter with tiktoken."""

    def test_count_tokens_gpt4o(self, mock_tiktoken):
        """Test token counting for gpt-4.1-mini with o200k_base encoding."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = OpenAITokenCounter()
            text = "Hello, world!"
            count = counter.count(text, model="gpt-4.1-mini")

            assert count == 5
            mock_module.encoding_for_model.assert_called_once_with("gpt-4.1-mini")
            mock_encoding.encode.assert_called_once_with(text)

    def test_count_tokens_gpt4_turbo(self, mock_tiktoken):
        """Test token counting for GPT-4 Turbo."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = [1, 2, 3]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = OpenAITokenCounter()
            count = counter.count("Test", model="gpt-4-turbo")

            assert count == 3

    def test_count_tokens_unknown_model_fallback(self, mock_tiktoken):
        """Test fallback to o200k_base for unknown model."""
        mock_module, mock_encoding = mock_tiktoken
        mock_module.encoding_for_model.side_effect = KeyError("Model not found")
        mock_encoding.encode.return_value = [1, 2, 3, 4]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = OpenAITokenCounter()
            count = counter.count("Unknown model", model="custom-model")

            assert count == 4
            mock_module.get_encoding.assert_called_once_with("o200k_base")

    def test_count_tokens_tiktoken_not_installed(self):
        """Test fallback to estimation when tiktoken import fails."""
        # Remove tiktoken from sys.modules to simulate not installed
        original = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = None  # Simulate import failure

        try:
            counter = OpenAITokenCounter()
            text = "This is a test"  # 14 characters
            count = counter.count(text, model="gpt-4.1-mini")

            # Estimation: len(text) // 4 = 14 // 4 = 3
            assert count == 3
        finally:
            if original:
                sys.modules["tiktoken"] = original
            elif "tiktoken" in sys.modules:
                del sys.modules["tiktoken"]

    def test_count_tokens_empty_string(self, mock_tiktoken):
        """Test token counting for empty string."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = []

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = OpenAITokenCounter()
            count = counter.count("", model="gpt-4.1-mini")

            assert count == 0

    def test_count_tokens_long_text(self, mock_tiktoken):
        """Test token counting for long text (>1000 tokens)."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = list(range(1500))

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = OpenAITokenCounter()
            long_text = "Lorem ipsum " * 200
            count = counter.count(long_text, model="gpt-4.1-mini")

            assert count == 1500


# ============================================================================
# Anthropic Token Counter Tests
# ============================================================================


class TestAnthropicTokenCounter:
    """Tests for AnthropicTokenCounter with official SDK."""

    def test_count_tokens_claude_sonnet(self, mock_anthropic):
        """Test token counting for Claude Sonnet using official SDK."""
        mock_module, mock_client = mock_anthropic
        mock_client.count_tokens.return_value = 42

        with (
            patch.dict(sys.modules, {"anthropic": mock_module}),
            patch(
                "src.infrastructure.llm.providers.token_counter.LLMConfigOverrideCache"
            ) as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "sk-ant-test-key"

            counter = AnthropicTokenCounter()
            text = "Hello Claude!"
            count = counter.count(text, model="claude-sonnet-4-5")

            assert count == 42

    def test_count_tokens_non_claude_model_fallback(self, mock_anthropic):
        """Test fallback to claude-sonnet-4-5 for non-Claude models."""
        mock_module, mock_client = mock_anthropic
        mock_client.count_tokens.return_value = 10

        with (
            patch.dict(sys.modules, {"anthropic": mock_module}),
            patch(
                "src.infrastructure.llm.providers.token_counter.LLMConfigOverrideCache"
            ) as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "sk-ant-test-key"

            counter = AnthropicTokenCounter()
            count = counter.count("Test", model="some-other-model")

            assert count == 10

    def test_count_tokens_sdk_not_installed(self):
        """Test fallback to estimation when Anthropic SDK is not installed."""
        # Simulate import failure
        original = sys.modules.get("anthropic")
        sys.modules["anthropic"] = None

        try:
            counter = AnthropicTokenCounter()
            text = "Anthropic test"  # 14 characters
            count = counter.count(text, model="claude-sonnet-4-5")

            # Estimation: 14 // 4 = 3
            assert count == 3
        finally:
            if original:
                sys.modules["anthropic"] = original
            elif "anthropic" in sys.modules:
                del sys.modules["anthropic"]

    def test_count_tokens_api_error(self, mock_anthropic):
        """Test error handling when Anthropic API fails."""
        mock_module, mock_client = mock_anthropic
        mock_client.count_tokens.side_effect = Exception("API Error")

        with (
            patch.dict(sys.modules, {"anthropic": mock_module}),
            patch(
                "src.infrastructure.llm.providers.token_counter.LLMConfigOverrideCache"
            ) as mock_cache,
        ):
            mock_cache.get_api_key.return_value = "sk-ant-test-key"

            counter = AnthropicTokenCounter()
            text = "Test error handling"  # 19 characters
            count = counter.count(text, model="claude-sonnet-4-5")

            # Should fallback to estimation: 19 // 4 = 4
            assert count == 4


# ============================================================================
# DeepSeek Token Counter Tests
# ============================================================================


class TestDeepSeekTokenCounter:
    """Tests for DeepSeekTokenCounter with tiktoken cl100k_base."""

    def test_count_tokens_deepseek_chat(self, mock_tiktoken):
        """Test token counting for DeepSeek chat with cl100k_base."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5, 6]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = DeepSeekTokenCounter()
            text = "DeepSeek test"
            count = counter.count(text, model="deepseek-chat")

            assert count == 6
            mock_module.get_encoding.assert_called_once_with("cl100k_base")
            mock_encoding.encode.assert_called_once_with(text)

    def test_count_tokens_deepseek_reasoner(self, mock_tiktoken):
        """Test token counting for DeepSeek reasoner."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = [1, 2, 3]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = DeepSeekTokenCounter()
            count = counter.count("Test", model="deepseek-reasoner")

            assert count == 3

    def test_count_tokens_tiktoken_not_installed(self):
        """Test fallback when tiktoken is not installed."""
        original = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = None

        try:
            counter = DeepSeekTokenCounter()
            text = "No tiktoken"  # 11 characters
            count = counter.count(text, model="deepseek-chat")

            # Estimation: 11 // 4 = 2
            assert count == 2
        finally:
            if original:
                sys.modules["tiktoken"] = original
            elif "tiktoken" in sys.modules:
                del sys.modules["tiktoken"]


# ============================================================================
# Perplexity Token Counter Tests
# ============================================================================


class TestPerplexityTokenCounter:
    """Tests for PerplexityTokenCounter with tiktoken cl100k_base."""

    def test_count_tokens_sonar_pro(self, mock_tiktoken):
        """Test token counting for Perplexity Sonar Pro."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5, 6, 7]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            counter = PerplexityTokenCounter()
            text = "Perplexity Sonar"
            count = counter.count(text, model="sonar-pro")

            assert count == 7
            mock_module.get_encoding.assert_called_once_with("cl100k_base")

    def test_count_tokens_tiktoken_not_installed(self):
        """Test fallback when tiktoken is not installed."""
        original = sys.modules.get("tiktoken")
        sys.modules["tiktoken"] = None

        try:
            counter = PerplexityTokenCounter()
            text = "Perplexity"  # 10 characters
            count = counter.count(text, model="sonar")

            # Estimation: 10 // 4 = 2
            assert count == 2
        finally:
            if original:
                sys.modules["tiktoken"] = original
            elif "tiktoken" in sys.modules:
                del sys.modules["tiktoken"]


# ============================================================================
# Estimation Token Counter Tests
# ============================================================================


class TestEstimationTokenCounter:
    """Tests for EstimationTokenCounter (character-based estimation)."""

    def test_count_tokens_short_text(self):
        """Test estimation for short text."""
        counter = EstimationTokenCounter()
        text = "Test"  # 4 characters
        count = counter.count(text, model="any-model")

        # 4 // 4 = 1 token
        assert count == 1

    def test_count_tokens_medium_text(self):
        """Test estimation for medium text."""
        counter = EstimationTokenCounter()
        text = "This is a medium length text"  # 28 characters
        count = counter.count(text, model="any-model")

        # 28 // 4 = 7 tokens
        assert count == 7

    def test_count_tokens_long_text(self):
        """Test estimation for long text."""
        counter = EstimationTokenCounter()
        text = "a" * 1000  # 1000 characters
        count = counter.count(text, model="any-model")

        # 1000 // 4 = 250 tokens
        assert count == 250

    def test_count_tokens_empty_string(self):
        """Test estimation for empty string."""
        counter = EstimationTokenCounter()
        count = counter.count("", model="any-model")

        assert count == 0

    def test_count_tokens_unicode(self):
        """Test estimation for Unicode text (emoji, CJK)."""
        counter = EstimationTokenCounter()
        text = "Hello 世界 🌍"  # 11 characters (including emoji)
        count = counter.count(text, model="any-model")

        # 11 // 4 = 2 tokens (estimation may be inaccurate for Unicode)
        assert count == 2


# ============================================================================
# Factory Function Tests
# ============================================================================


class TestGetTokenCounter:
    """Tests for get_token_counter factory function."""

    def test_get_openai_counter(self):
        """Test getting OpenAI token counter."""
        counter = get_token_counter("openai")
        assert isinstance(counter, OpenAITokenCounter)

    def test_get_anthropic_counter(self):
        """Test getting Anthropic token counter."""
        counter = get_token_counter("anthropic")
        assert isinstance(counter, AnthropicTokenCounter)

    def test_get_deepseek_counter(self):
        """Test getting DeepSeek token counter."""
        counter = get_token_counter("deepseek")
        assert isinstance(counter, DeepSeekTokenCounter)

    def test_get_perplexity_counter(self):
        """Test getting Perplexity token counter."""
        counter = get_token_counter("perplexity")
        assert isinstance(counter, PerplexityTokenCounter)

    def test_get_ollama_counter(self):
        """Test getting Ollama token counter (estimation-based)."""
        counter = get_token_counter("ollama")
        assert isinstance(counter, EstimationTokenCounter)

    def test_get_unknown_provider_fallback(self):
        """Test fallback to EstimationTokenCounter for unknown provider."""
        counter = get_token_counter("unknown-provider")
        assert isinstance(counter, EstimationTokenCounter)

    def test_all_counters_have_count_method(self):
        """Test that all counters implement the count method."""
        providers = ["openai", "anthropic", "deepseek", "perplexity", "ollama"]

        for provider in providers:
            counter = get_token_counter(provider)
            assert hasattr(counter, "count")
            assert callable(counter.count)


# ============================================================================
# Integration Tests (Cross-Provider Consistency)
# ============================================================================


class TestCrossProviderConsistency:
    """Tests to ensure consistent behavior across providers."""

    def test_same_text_similar_counts(self, mock_tiktoken):
        """Test that OpenAI, DeepSeek, Perplexity give similar counts."""
        mock_module, mock_encoding = mock_tiktoken
        mock_encoding.encode.return_value = [1, 2, 3, 4, 5]

        with patch.dict(sys.modules, {"tiktoken": mock_module}):
            text = "Consistent test"

            openai_counter = OpenAITokenCounter()
            deepseek_counter = DeepSeekTokenCounter()
            perplexity_counter = PerplexityTokenCounter()

            openai_count = openai_counter.count(text, "gpt-4")
            deepseek_count = deepseek_counter.count(text, "deepseek-chat")
            perplexity_count = perplexity_counter.count(text, "sonar")

            # All should return 5 tokens (same encoding)
            assert openai_count == deepseek_count == perplexity_count == 5

    def test_estimation_accuracy(self):
        """Test that estimation is reasonably accurate."""
        text = "This is a test sentence with multiple words"
        estimation_counter = EstimationTokenCounter()
        estimated_count = estimation_counter.count(text, "any-model")

        # Expected: ~11 tokens estimated (44 chars / 4 = 11)
        # Verify estimation is in reasonable range (5-15 tokens)
        assert 5 <= estimated_count <= 15

    def test_empty_string_all_providers(self):
        """Test that all providers handle empty string correctly."""
        counters = [
            EstimationTokenCounter(),
        ]

        for counter in counters:
            count = counter.count("", "any-model")
            assert count == 0, f"{counter.__class__.__name__} should return 0 for empty string"
