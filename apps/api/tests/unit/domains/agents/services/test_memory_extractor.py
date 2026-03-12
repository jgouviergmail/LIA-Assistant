"""
Unit tests for domains.agents.services.memory_extractor module.

Tests the LangMem memory extraction functionality for psychological profiling.

Key scenarios tested:
- LLMAgentConfig instantiation with all required fields
- JSON parsing of extraction results
- Message formatting for extraction
- Memory key generation

Author: Claude Code (Opus 4.5)
Date: 2025-12-21
"""

import json

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.llm_agent_config import LLMAgentConfig
from src.domains.agents.services.memory_extractor import (
    _format_messages_for_extraction,
    _generate_memory_key,
    _parse_extraction_result,
)
from src.domains.agents.tools.memory_tools import MemorySchema


class TestLLMAgentConfigForMemoryExtraction:
    """Tests for LLMAgentConfig instantiation in memory extraction context."""

    def test_llm_agent_config_requires_all_fields(self):
        """Test that LLMAgentConfig fails without required fields.

        This test documents the root cause of the memory extraction failure:
        LLMAgentConfig requires top_p, frequency_penalty, and presence_penalty.
        """
        # This should raise ValidationError without the required fields
        with pytest.raises(Exception):  # Pydantic ValidationError
            LLMAgentConfig(
                model="gpt-4.1-mini",
                temperature=0.3,
                max_tokens=1000,
                # Missing: top_p, frequency_penalty, presence_penalty
            )

    def test_llm_agent_config_with_all_required_fields(self):
        """Test that LLMAgentConfig succeeds with all required fields.

        This is the correct way to instantiate LLMAgentConfig for memory extraction.
        """
        config = LLMAgentConfig(
            model="gpt-4.1-mini",
            temperature=0.3,
            max_tokens=1000,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )

        assert config.model == "gpt-4.1-mini"
        assert config.temperature == 0.3
        assert config.max_tokens == 1000
        assert config.top_p == 1.0
        assert config.frequency_penalty == 0.0
        assert config.presence_penalty == 0.0

    def test_llm_agent_config_default_provider(self):
        """Test that LLMAgentConfig defaults to OpenAI provider."""
        config = LLMAgentConfig(
            model="gpt-4.1-mini",
            temperature=0.3,
            max_tokens=1000,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0,
        )

        assert config.provider == "openai"


class TestFormatMessagesForExtraction:
    """Tests for _format_messages_for_extraction function."""

    def test_format_human_messages(self):
        """Test formatting of human messages."""
        messages = [HumanMessage(content="Hello, how are you?")]
        result = _format_messages_for_extraction(messages)

        assert "USER: Hello, how are you?" in result

    def test_format_ai_messages(self):
        """Test formatting of AI messages."""
        messages = [AIMessage(content="I'm doing well, thank you!")]
        result = _format_messages_for_extraction(messages)

        assert "ASSISTANT: I'm doing well, thank you!" in result

    def test_format_mixed_conversation(self):
        """Test formatting of mixed human/AI conversation."""
        messages = [
            HumanMessage(content="Hello"),
            AIMessage(content="Hi there!"),
            HumanMessage(content="How are you?"),
            AIMessage(content="Great, thanks!"),
        ]
        result = _format_messages_for_extraction(messages)

        assert "USER: Hello" in result
        assert "ASSISTANT: Hi there!" in result
        assert "USER: How are you?" in result
        assert "ASSISTANT: Great, thanks!" in result

    def test_truncate_long_messages(self):
        """Test that messages longer than memory_extraction_message_max_chars are truncated.

        Default limit is 3000 chars, so we use 3500 to trigger truncation.
        """
        long_content = "x" * 3500
        messages = [HumanMessage(content=long_content)]
        result = _format_messages_for_extraction(messages)

        # Should be truncated to 3000 chars + "..." + "USER: " prefix
        # 3000 + 3 + 6 = 3009 chars max
        assert len(result) < 3500
        assert "..." in result


class TestParseExtractionResult:
    """Tests for _parse_extraction_result function."""

    def test_parse_valid_json_array(self):
        """Test parsing of valid JSON array with memories."""
        json_result = json.dumps(
            [
                {
                    "content": "User prefers morning meetings",
                    "category": "preference",
                    "emotional_weight": 3,
                    "trigger_topic": "meetings",
                    "usage_nuance": "Schedule meetings in the morning when possible",
                    "importance": 0.7,
                }
            ]
        )

        memories = _parse_extraction_result(json_result)

        assert len(memories) == 1
        assert memories[0].content == "User prefers morning meetings"
        assert memories[0].category == "preference"
        assert memories[0].emotional_weight == 3

    def test_parse_empty_array(self):
        """Test parsing of empty JSON array (no new memories)."""
        json_result = "[]"
        memories = _parse_extraction_result(json_result)

        assert len(memories) == 0

    def test_parse_json_with_markdown_fences(self):
        """Test parsing of JSON wrapped in markdown code fences."""
        json_result = """```json
[
  {
    "content": "User likes coffee",
    "category": "preference",
    "emotional_weight": 5,
    "trigger_topic": "coffee",
    "usage_nuance": "Can mention coffee when appropriate",
    "importance": 0.5
  }
]
```"""

        memories = _parse_extraction_result(json_result)

        assert len(memories) == 1
        assert memories[0].content == "User likes coffee"

    def test_parse_invalid_json_returns_empty(self):
        """Test that invalid JSON returns empty list (graceful degradation)."""
        invalid_json = "not valid json at all"
        memories = _parse_extraction_result(invalid_json)

        assert len(memories) == 0

    def test_parse_non_array_returns_empty(self):
        """Test that non-array JSON returns empty list."""
        json_result = json.dumps({"content": "This is an object, not an array"})
        memories = _parse_extraction_result(json_result)

        assert len(memories) == 0

    def test_parse_array_with_invalid_items_skips_them(self):
        """Test that invalid items in array are skipped, valid ones are kept."""
        json_result = json.dumps(
            [
                {
                    "content": "Valid memory",
                    "category": "preference",
                    "emotional_weight": 0,
                    "trigger_topic": "",
                    "usage_nuance": "",
                    "importance": 0.5,
                },
                {
                    # Missing required fields
                    "invalid": "item"
                },
            ]
        )

        memories = _parse_extraction_result(json_result)

        # Only the valid memory should be parsed
        assert len(memories) == 1
        assert memories[0].content == "Valid memory"


class TestGenerateMemoryKey:
    """Tests for _generate_memory_key function."""

    def test_generate_memory_key_format(self):
        """Test that generated keys have correct format."""
        key = _generate_memory_key()

        assert key.startswith("mem_")
        assert len(key) == 16  # "mem_" + 12 hex chars

    def test_generate_memory_key_uniqueness(self):
        """Test that generated keys are unique."""
        keys = {_generate_memory_key() for _ in range(100)}

        # All keys should be unique
        assert len(keys) == 100


class TestMemorySchema:
    """Tests for MemorySchema validation."""

    def test_memory_schema_minimal(self):
        """Test MemorySchema with minimal required fields."""
        memory = MemorySchema(
            content="Test memory content",
            category="personal",
        )

        assert memory.content == "Test memory content"
        assert memory.category == "personal"
        # Defaults
        assert memory.emotional_weight == 0
        assert memory.trigger_topic == ""
        assert memory.usage_nuance == ""
        assert memory.importance == 0.7

    def test_memory_schema_full(self):
        """Test MemorySchema with all fields populated."""
        memory = MemorySchema(
            content="User's father is named Jean",
            category="relationship",
            emotional_weight=-3,
            trigger_topic="family",
            usage_nuance="Sensitive topic, approach with care",
            importance=0.9,
        )

        assert memory.content == "User's father is named Jean"
        assert memory.category == "relationship"
        assert memory.emotional_weight == -3
        assert memory.trigger_topic == "family"
        assert memory.usage_nuance == "Sensitive topic, approach with care"
        assert memory.importance == 0.9

    def test_memory_schema_emotional_weight_bounds(self):
        """Test that emotional_weight is bounded between -10 and 10."""
        # Valid bounds
        memory_min = MemorySchema(
            content="Test",
            category="personal",
            emotional_weight=-10,
        )
        memory_max = MemorySchema(
            content="Test",
            category="personal",
            emotional_weight=10,
        )

        assert memory_min.emotional_weight == -10
        assert memory_max.emotional_weight == 10

        # Out of bounds should fail
        with pytest.raises(Exception):
            MemorySchema(
                content="Test",
                category="personal",
                emotional_weight=-11,
            )

        with pytest.raises(Exception):
            MemorySchema(
                content="Test",
                category="personal",
                emotional_weight=11,
            )

    def test_memory_schema_importance_bounds(self):
        """Test that importance is bounded between 0.0 and 1.0."""
        # Valid bounds
        memory_min = MemorySchema(
            content="Test",
            category="personal",
            importance=0.0,
        )
        memory_max = MemorySchema(
            content="Test",
            category="personal",
            importance=1.0,
        )

        assert memory_min.importance == 0.0
        assert memory_max.importance == 1.0

        # Out of bounds should fail
        with pytest.raises(Exception):
            MemorySchema(
                content="Test",
                category="personal",
                importance=-0.1,
            )

        with pytest.raises(Exception):
            MemorySchema(
                content="Test",
                category="personal",
                importance=1.1,
            )

    def test_memory_schema_valid_categories(self):
        """Test all valid category values."""
        valid_categories = [
            "preference",
            "personal",
            "relationship",
            "event",
            "pattern",
            "sensitivity",
        ]

        for category in valid_categories:
            memory = MemorySchema(
                content="Test",
                category=category,
            )
            assert memory.category == category

    def test_memory_schema_invalid_category_fails(self):
        """Test that invalid category raises validation error."""
        with pytest.raises(Exception):
            MemorySchema(
                content="Test",
                category="invalid_category",
            )
