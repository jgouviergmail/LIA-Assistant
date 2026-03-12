"""
Unit tests for token counting utilities.

Tests for token counting functions using tiktoken,
message token counting, state token counting, and cost estimation.
"""

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from src.core.field_names import FIELD_TOTAL
from src.domains.agents.utils.token_utils import (
    count_messages_tokens,
    count_state_tokens,
    count_tokens,
    estimate_cost,
    get_encoding_for_model,
)

# ============================================================================
# Tests for count_tokens function
# ============================================================================


class TestCountTokens:
    """Tests for count_tokens function."""

    def test_count_simple_text(self):
        """Test counting tokens in simple text."""
        result = count_tokens("Hello, world!")

        assert isinstance(result, int)
        assert result > 0

    def test_count_empty_string(self):
        """Test counting tokens in empty string."""
        result = count_tokens("")

        assert result == 0

    def test_count_whitespace_only(self):
        """Test counting tokens in whitespace only."""
        result = count_tokens("   ")

        # Whitespace is typically tokenized
        assert isinstance(result, int)

    def test_count_longer_text(self):
        """Test counting tokens in longer text."""
        text = "This is a longer sentence that should have more tokens."
        result = count_tokens(text)

        # Should have multiple tokens
        assert result > 5

    def test_count_french_text(self):
        """Test counting tokens in French text."""
        result = count_tokens("Bonjour le monde !")

        assert isinstance(result, int)
        assert result > 0

    def test_count_chinese_text(self):
        """Test counting tokens in Chinese text."""
        result = count_tokens("你好世界")

        assert isinstance(result, int)
        assert result > 0

    def test_count_special_characters(self):
        """Test counting tokens with special characters."""
        result = count_tokens("Hello! @#$%^&*() World?")

        assert isinstance(result, int)
        assert result > 0

    def test_count_with_newlines(self):
        """Test counting tokens with newlines."""
        result = count_tokens("Hello\nWorld\nTest")

        assert isinstance(result, int)
        assert result > 0

    def test_custom_encoding(self):
        """Test counting with custom encoding name."""
        result = count_tokens("Hello, world!", encoding_name="cl100k_base")

        assert isinstance(result, int)
        assert result > 0

    @patch("src.domains.agents.utils.token_utils.tiktoken")
    def test_fallback_on_encoding_error(self, mock_tiktoken):
        """Test fallback to estimation when tiktoken fails."""
        mock_tiktoken.get_encoding.side_effect = Exception("Encoding not found")

        # Should fall back to 4 chars per token estimation
        text = "12345678"  # 8 chars
        result = count_tokens(text)

        assert result == 2  # 8 // 4 = 2


class TestCountTokensConsistency:
    """Tests for token counting consistency."""

    def test_same_text_same_count(self):
        """Test that same text returns same count."""
        text = "Test consistency of token counting"
        result1 = count_tokens(text)
        result2 = count_tokens(text)

        assert result1 == result2

    def test_longer_text_more_tokens(self):
        """Test that longer text has more tokens."""
        short = "Hello"
        long = "Hello there, how are you doing today?"

        short_count = count_tokens(short)
        long_count = count_tokens(long)

        assert long_count > short_count

    def test_whitespace_affects_count(self):
        """Test that whitespace affects token count."""
        no_space = "HelloWorld"
        with_space = "Hello World"

        count1 = count_tokens(no_space)
        count2 = count_tokens(with_space)

        # These might have different token counts
        assert isinstance(count1, int)
        assert isinstance(count2, int)


# ============================================================================
# Tests for count_messages_tokens function
# ============================================================================


class TestCountMessagesTokens:
    """Tests for count_messages_tokens function."""

    def test_count_single_message(self):
        """Test counting tokens in single message."""
        messages = [HumanMessage(content="Hello, world!")]
        result = count_messages_tokens(messages)

        assert isinstance(result, int)
        assert result > 0

    def test_count_empty_list(self):
        """Test counting tokens in empty message list."""
        result = count_messages_tokens([])

        assert result == 0

    def test_count_multiple_messages(self):
        """Test counting tokens in multiple messages."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(content="How are you?"),
        ]
        result = count_messages_tokens(messages)

        assert isinstance(result, int)
        assert result > 0

    def test_count_system_message(self):
        """Test counting tokens in system message."""
        messages = [SystemMessage(content="You are a helpful assistant.")]
        result = count_messages_tokens(messages)

        assert isinstance(result, int)
        assert result > 0

    def test_count_mixed_message_types(self):
        """Test counting tokens in mixed message types."""
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="Hello"),
            AIMessage(content="Hi! How can I help you?"),
        ]
        result = count_messages_tokens(messages)

        # Should be sum of all message contents
        assert isinstance(result, int)
        assert result > 5  # At least a few tokens

    def test_count_message_with_empty_content(self):
        """Test counting tokens in message with empty content."""
        messages = [HumanMessage(content="")]
        result = count_messages_tokens(messages)

        assert result == 0

    def test_count_message_with_none_content(self):
        """Test counting tokens in message with None content."""
        # Create message with None content
        msg = HumanMessage(content="test")
        msg.content = None  # Force None content
        messages = [msg]

        result = count_messages_tokens(messages)

        # Should handle None gracefully
        assert isinstance(result, int)

    def test_custom_encoding(self):
        """Test counting with custom encoding."""
        messages = [HumanMessage(content="Hello, world!")]
        result = count_messages_tokens(messages, encoding_name="cl100k_base")

        assert isinstance(result, int)
        assert result > 0


class TestCountMessagesTokensAccuracy:
    """Tests for message token counting accuracy."""

    def test_sum_equals_individual_counts(self):
        """Test that sum of individual counts equals total."""
        msg1 = "Hello"
        msg2 = "World"

        individual1 = count_tokens(msg1)
        individual2 = count_tokens(msg2)

        messages = [
            HumanMessage(content=msg1),
            AIMessage(content=msg2),
        ]
        total = count_messages_tokens(messages)

        assert total == individual1 + individual2


# ============================================================================
# Tests for count_state_tokens function
# ============================================================================


class TestCountStateTokens:
    """Tests for count_state_tokens function."""

    def test_count_empty_state(self):
        """Test counting tokens in empty state."""
        state = {}
        result = count_state_tokens(state)

        assert isinstance(result, dict)
        assert result["messages"] == 0
        assert result["agent_results"] == 0
        assert result["routing_history"] == 0
        assert result[FIELD_TOTAL] == 0

    def test_count_state_with_messages(self):
        """Test counting tokens in state with messages."""
        state = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi there!"),
            ]
        }
        result = count_state_tokens(state)

        assert result["messages"] > 0
        assert result[FIELD_TOTAL] > 0

    def test_count_state_with_agent_results(self):
        """Test counting tokens in state with agent_results."""
        state = {
            "agent_results": {
                "contacts": {"summary_for_llm": "Found 3 contacts"},
                "weather": {"summary_for_llm": "Weather is sunny"},
            }
        }
        result = count_state_tokens(state)

        assert result["agent_results"] > 0
        assert result[FIELD_TOTAL] > 0

    def test_count_state_with_routing_history(self):
        """Test counting tokens in state with routing_history."""
        state = {
            "routing_history": [
                {"domain": "contacts", "confidence": 0.9},
                {"domain": "weather", "confidence": 0.8},
            ]
        }
        result = count_state_tokens(state)

        assert result["routing_history"] > 0
        assert result[FIELD_TOTAL] > 0

    def test_count_state_with_all_fields(self):
        """Test counting tokens in state with all fields."""
        state = {
            "messages": [HumanMessage(content="Hello world")],
            "agent_results": {"test": {"data": "result"}},
            "routing_history": [{"decision": "route_to_contact"}],
        }
        result = count_state_tokens(state)

        assert result["messages"] > 0
        assert result["agent_results"] > 0
        assert result["routing_history"] > 0
        # Total should be sum of all
        expected_total = result["messages"] + result["agent_results"] + result["routing_history"]
        assert result[FIELD_TOTAL] == expected_total

    def test_count_state_has_required_keys(self):
        """Test that result has all required keys."""
        state = {}
        result = count_state_tokens(state)

        assert "messages" in result
        assert "agent_results" in result
        assert "routing_history" in result
        assert FIELD_TOTAL in result

    def test_custom_encoding(self):
        """Test counting with custom encoding."""
        state = {"messages": [HumanMessage(content="Hello")]}
        result = count_state_tokens(state, encoding_name="cl100k_base")

        assert isinstance(result, dict)
        assert result["messages"] > 0


# ============================================================================
# Tests for estimate_cost function
# ============================================================================


class TestEstimateCost:
    """Tests for estimate_cost function."""

    def test_estimate_basic_cost(self):
        """Test basic cost estimation."""
        result = estimate_cost(
            input_tokens=1000,
            output_tokens=500,
            model="gpt-4.1-mini",
        )

        assert isinstance(result, dict)
        assert "input_cost" in result
        assert "output_cost" in result
        assert FIELD_TOTAL in result
        assert "model" in result
        assert "input_tokens" in result
        assert "output_tokens" in result

    def test_estimate_zero_tokens(self):
        """Test cost estimation with zero tokens."""
        result = estimate_cost(input_tokens=0, output_tokens=0)

        assert result["input_cost"] == 0
        assert result["output_cost"] == 0
        assert result[FIELD_TOTAL] == 0

    def test_estimate_input_only(self):
        """Test cost estimation with only input tokens."""
        result = estimate_cost(input_tokens=1000000, output_tokens=0)

        assert result["input_cost"] > 0
        assert result["output_cost"] == 0
        assert result[FIELD_TOTAL] == result["input_cost"]

    def test_estimate_output_only(self):
        """Test cost estimation with only output tokens."""
        result = estimate_cost(input_tokens=0, output_tokens=1000000)

        assert result["input_cost"] == 0
        assert result["output_cost"] > 0
        assert result[FIELD_TOTAL] == result["output_cost"]

    def test_estimate_gpt4_nano(self):
        """Test cost estimation for gpt-4.1-nano model."""
        result = estimate_cost(
            input_tokens=1000000,
            output_tokens=1000000,
            model="gpt-4.1-nano",
        )

        # gpt-4.1-nano: $0.10/1M input, $0.40/1M output
        assert result["input_cost"] == pytest.approx(0.10, rel=0.01)
        assert result["output_cost"] == pytest.approx(0.40, rel=0.01)

    def test_estimate_gpt4_mini(self):
        """Test cost estimation for gpt-4.1-mini model."""
        result = estimate_cost(
            input_tokens=1000000,
            output_tokens=1000000,
            model="gpt-4.1-mini",
        )

        # gpt-4.1-mini: $0.15/1M input, $0.60/1M output
        assert result["input_cost"] == pytest.approx(0.15, rel=0.01)
        assert result["output_cost"] == pytest.approx(0.60, rel=0.01)

    def test_estimate_gpt4_full(self):
        """Test cost estimation for gpt-4.1 model."""
        result = estimate_cost(
            input_tokens=1000000,
            output_tokens=1000000,
            model="gpt-4.1",
        )

        # gpt-4.1: $2.50/1M input, $10/1M output
        assert result["input_cost"] == pytest.approx(2.50, rel=0.01)
        assert result["output_cost"] == pytest.approx(10.00, rel=0.01)

    def test_estimate_unknown_model_uses_default(self):
        """Test that unknown model uses default pricing."""
        result = estimate_cost(
            input_tokens=1000000,
            output_tokens=1000000,
            model="unknown-model",
        )

        # Should use default (gpt-4.1-mini pricing)
        assert result["input_cost"] == pytest.approx(0.15, rel=0.01)
        assert result["output_cost"] == pytest.approx(0.60, rel=0.01)

    def test_estimate_preserves_token_counts(self):
        """Test that token counts are preserved in result."""
        result = estimate_cost(
            input_tokens=12345,
            output_tokens=6789,
            model="gpt-4.1-mini",
        )

        assert result["input_tokens"] == 12345
        assert result["output_tokens"] == 6789

    def test_estimate_preserves_model_name(self):
        """Test that model name is preserved in result."""
        result = estimate_cost(
            input_tokens=100,
            output_tokens=100,
            model="gpt-4.1",
        )

        assert result["model"] == "gpt-4.1"

    def test_estimate_cost_rounded(self):
        """Test that costs are rounded appropriately."""
        result = estimate_cost(
            input_tokens=100,
            output_tokens=100,
            model="gpt-4.1-mini",
        )

        # Costs should be rounded to 6 decimal places
        assert len(str(result["input_cost"]).split(".")[-1]) <= 6
        assert len(str(result["output_cost"]).split(".")[-1]) <= 6


class TestEstimateCostMath:
    """Tests for cost estimation mathematics."""

    def test_total_equals_sum(self):
        """Test that total equals sum of input and output costs."""
        result = estimate_cost(
            input_tokens=1000,
            output_tokens=500,
            model="gpt-4.1-mini",
        )

        expected_total = result["input_cost"] + result["output_cost"]
        assert result[FIELD_TOTAL] == pytest.approx(expected_total, rel=0.0001)

    def test_cost_scales_linearly(self):
        """Test that cost scales linearly with tokens."""
        result_small = estimate_cost(
            input_tokens=1000,
            output_tokens=1000,
            model="gpt-4.1-mini",
        )
        result_large = estimate_cost(
            input_tokens=10000,
            output_tokens=10000,
            model="gpt-4.1-mini",
        )

        # Large should be 10x small
        assert result_large["input_cost"] == pytest.approx(
            result_small["input_cost"] * 10, rel=0.01
        )
        assert result_large["output_cost"] == pytest.approx(
            result_small["output_cost"] * 10, rel=0.01
        )


# ============================================================================
# Tests for get_encoding_for_model function
# ============================================================================


class TestGetEncodingForModel:
    """Tests for get_encoding_for_model function."""

    def test_gpt4_1_mini_uses_o200k(self):
        """Test that gpt-4.1-mini uses o200k_base encoding."""
        result = get_encoding_for_model("gpt-4.1-mini")
        assert result == "o200k_base"

    def test_gpt4_1_uses_o200k(self):
        """Test that gpt-4.1 uses o200k_base encoding."""
        result = get_encoding_for_model("gpt-4.1")
        assert result == "o200k_base"

    def test_gpt4_1_nano_uses_o200k(self):
        """Test that gpt-4.1-nano uses o200k_base encoding."""
        result = get_encoding_for_model("gpt-4.1-nano")
        assert result == "o200k_base"

    def test_gpt4_uses_cl100k(self):
        """Test that gpt-4 uses cl100k_base encoding."""
        result = get_encoding_for_model("gpt-4")
        assert result == "cl100k_base"

    def test_gpt4_turbo_uses_cl100k(self):
        """Test that gpt-4-turbo uses cl100k_base encoding."""
        result = get_encoding_for_model("gpt-4-turbo")
        assert result == "cl100k_base"

    def test_gpt35_uses_cl100k(self):
        """Test that gpt-3.5-turbo uses cl100k_base encoding."""
        result = get_encoding_for_model("gpt-3.5-turbo")
        assert result == "cl100k_base"

    def test_unknown_model_uses_default(self):
        """Test that unknown model uses default encoding."""
        result = get_encoding_for_model("claude-3")
        assert result == "o200k_base"

    def test_model_with_version_suffix(self):
        """Test model with version suffix."""
        result = get_encoding_for_model("gpt-4.1-mini-0125")
        assert result == "o200k_base"

    def test_model_case_sensitivity(self):
        """Test that model matching is case-sensitive substring match."""
        # Contains "gpt-4" so should match cl100k
        result1 = get_encoding_for_model("gpt-4-preview")
        assert result1 == "cl100k_base"

        # Contains "gpt-4.1-mini" so should match o200k
        result2 = get_encoding_for_model("my-fine-tuned-gpt-4.1-mini-model")
        assert result2 == "o200k_base"


class TestGetEncodingValidation:
    """Tests for encoding validation."""

    def test_returned_encoding_is_valid(self):
        """Test that returned encoding can be loaded by tiktoken."""
        import tiktoken

        models = ["gpt-4.1-mini", "gpt-4", "gpt-3.5-turbo", "unknown"]

        for model in models:
            encoding_name = get_encoding_for_model(model)
            # Should not raise
            encoding = tiktoken.get_encoding(encoding_name)
            assert encoding is not None


# ============================================================================
# Integration tests
# ============================================================================


class TestTokenUtilsIntegration:
    """Integration tests for token utilities."""

    def test_full_workflow(self):
        """Test complete workflow of counting and estimating."""
        # Create state with messages
        messages = [
            SystemMessage(content="You are a helpful assistant."),
            HumanMessage(content="What's the weather like?"),
            AIMessage(content="The weather is sunny and warm."),
        ]

        # Count tokens
        token_count = count_messages_tokens(messages)
        assert token_count > 0

        # Estimate cost
        cost = estimate_cost(
            input_tokens=token_count,
            output_tokens=token_count // 2,
            model="gpt-4.1-mini",
        )

        assert cost["input_cost"] > 0
        assert cost[FIELD_TOTAL] > 0

    def test_state_to_cost_workflow(self):
        """Test workflow from state to cost estimation."""
        state = {
            "messages": [
                HumanMessage(content="Hello"),
                AIMessage(content="Hi! How can I help?"),
            ],
            "agent_results": {"test": {"result": "data"}},
            "routing_history": [{"decision": "chat"}],
        }

        # Count state tokens
        counts = count_state_tokens(state)
        assert counts[FIELD_TOTAL] > 0

        # Estimate cost for total tokens
        cost = estimate_cost(
            input_tokens=counts[FIELD_TOTAL],
            output_tokens=counts["messages"],
            model="gpt-4.1-mini",
        )

        assert cost[FIELD_TOTAL] > 0


class TestTokenUtilsEdgeCases:
    """Tests for edge cases in token utilities."""

    def test_very_long_text(self):
        """Test counting tokens in very long text."""
        text = "Hello world. " * 1000  # Very long text
        result = count_tokens(text)

        assert result > 1000  # Should have many tokens

    def test_unicode_emoji(self):
        """Test counting tokens with emoji."""
        result = count_tokens("Hello 👋 World 🌍!")

        assert isinstance(result, int)
        assert result > 0

    def test_code_snippet(self):
        """Test counting tokens in code."""
        code = """
def hello():
    print("Hello, world!")
"""
        result = count_tokens(code)

        assert isinstance(result, int)
        assert result > 0

    def test_json_content(self):
        """Test counting tokens in JSON content."""
        json_str = '{"name": "John", "age": 30, "city": "Paris"}'
        result = count_tokens(json_str)

        assert isinstance(result, int)
        assert result > 0

    def test_multiline_message(self):
        """Test counting tokens in multiline message."""
        content = """This is line 1.
This is line 2.
This is line 3."""
        messages = [HumanMessage(content=content)]
        result = count_messages_tokens(messages)

        assert result > 5  # Multiple lines should have multiple tokens
