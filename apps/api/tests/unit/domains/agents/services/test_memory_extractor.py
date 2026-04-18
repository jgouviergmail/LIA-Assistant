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
import time
from types import SimpleNamespace

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.core.llm_agent_config import LLMAgentConfig
from src.domains.agents.services.memory_extractor import (
    _cache_debug_result,
    _format_existing_memories_with_ids,
    _format_messages_for_extraction,
    _memory_extraction_debug_cache,
    _parse_extraction_result,
    get_memory_extraction_debug,
)
from src.domains.memories.schemas import ExtractedMemory


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


class TestExtractedMemorySchema:
    """Tests for ExtractedMemory validation (create/update/delete actions)."""

    def test_extracted_memory_create_defaults(self):
        """Test ExtractedMemory with create action (default)."""
        memory = ExtractedMemory(
            content="Test memory content",
            category="personal",
        )

        assert memory.action == "create"
        assert memory.memory_id is None
        assert memory.content == "Test memory content"
        assert memory.category == "personal"

    def test_extracted_memory_update(self):
        """Test ExtractedMemory with update action."""
        memory = ExtractedMemory(
            action="update",
            memory_id="abc-123",
            content="Updated content",
        )

        assert memory.action == "update"
        assert memory.memory_id == "abc-123"

    def test_extracted_memory_delete(self):
        """Test ExtractedMemory with delete action."""
        memory = ExtractedMemory(
            action="delete",
            memory_id="abc-123",
        )

        assert memory.action == "delete"
        assert memory.memory_id == "abc-123"
        assert memory.content is None

    def test_extracted_memory_backward_compat(self):
        """Test backward compatibility: no action field defaults to create."""
        memory = ExtractedMemory(
            content="Test",
            category="personal",
            emotional_weight=5,
            importance=0.8,
        )

        assert memory.action == "create"

    def test_extracted_memory_emotional_weight_bounds(self):
        """Test that emotional_weight is bounded between -10 and 10."""
        memory = ExtractedMemory(content="Test", category="personal", emotional_weight=-10)
        assert memory.emotional_weight == -10

        memory = ExtractedMemory(content="Test", category="personal", emotional_weight=10)
        assert memory.emotional_weight == 10

        with pytest.raises(Exception):
            ExtractedMemory(content="Test", category="personal", emotional_weight=-11)

        with pytest.raises(Exception):
            ExtractedMemory(content="Test", category="personal", emotional_weight=11)

    def test_extracted_memory_importance_bounds(self):
        """Test that importance is bounded between 0.0 and 1.0."""
        memory = ExtractedMemory(content="Test", category="personal", importance=0.0)
        assert memory.importance == 0.0

        memory = ExtractedMemory(content="Test", category="personal", importance=1.0)
        assert memory.importance == 1.0

        with pytest.raises(Exception):
            ExtractedMemory(content="Test", category="personal", importance=-0.1)

        with pytest.raises(Exception):
            ExtractedMemory(content="Test", category="personal", importance=1.1)


@pytest.mark.unit
class TestFormatExistingMemoriesWithIds:
    """Tests for _format_existing_memories_with_ids — PINNED tag behavior."""

    def _make_memory(self, **overrides):
        defaults = {
            "id": "uuid-xyz",
            "content": "I work as an accountant",
            "category": "personal",
            "importance": 0.8,
            "pinned": False,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_unpinned_memory_no_pinned_tag(self):
        memory = self._make_memory(pinned=False)
        result = _format_existing_memories_with_ids([(memory, 0.85)])

        assert "[PINNED]" not in result
        assert "uuid-xyz" in result
        assert "I work as an accountant" in result

    def test_pinned_memory_includes_pinned_tag(self):
        memory = self._make_memory(pinned=True)
        result = _format_existing_memories_with_ids([(memory, 0.85)])

        assert "[PINNED]" in result
        assert "uuid-xyz" in result

    def test_mixed_pinned_and_unpinned_memories(self):
        pinned = self._make_memory(id="pinned-uuid", pinned=True, content="pinned fact")
        unpinned = self._make_memory(id="normal-uuid", pinned=False, content="normal fact")
        result = _format_existing_memories_with_ids([(pinned, 0.9), (unpinned, 0.8)])

        lines = result.splitlines()
        assert len(lines) == 2
        pinned_line = next(line for line in lines if "pinned-uuid" in line)
        normal_line = next(line for line in lines if "normal-uuid" in line)
        assert "[PINNED]" in pinned_line
        assert "[PINNED]" not in normal_line

    def test_empty_list_returns_none_string(self):
        assert _format_existing_memories_with_ids([]) == "None"


@pytest.mark.unit
class TestMemoryExtractionDebugCache:
    """Tests for the debug cache used by Memory Detection in the debug panel."""

    def setup_method(self):
        """Clear the cache before each test to avoid cross-contamination."""
        _memory_extraction_debug_cache.clear()

    def teardown_method(self):
        """Clear the cache after each test."""
        _memory_extraction_debug_cache.clear()

    def test_cache_and_retrieve_debug_data(self):
        """Test that debug data can be cached and retrieved by run_id."""
        debug_data = {
            "enabled": True,
            "extracted_memories": [{"content": "User likes hiking", "category": "preference"}],
            "existing_similar": [],
            "llm_metadata": {"model": "gpt-4.1-mini", "input_tokens": 100},
            "skipped_reason": None,
        }

        _cache_debug_result("run-123", debug_data)
        result = get_memory_extraction_debug("run-123")

        assert result is not None
        assert result["enabled"] is True
        assert len(result["extracted_memories"]) == 1
        assert result["extracted_memories"][0]["content"] == "User likes hiking"

    def test_retrieve_consumes_entry(self):
        """Test that retrieval removes the entry from the cache (consume semantics)."""
        _cache_debug_result("run-456", {"enabled": True, "extracted_memories": []})

        # First retrieval succeeds
        result = get_memory_extraction_debug("run-456")
        assert result is not None

        # Second retrieval returns None (already consumed)
        result2 = get_memory_extraction_debug("run-456")
        assert result2 is None

    def test_retrieve_unknown_run_id_returns_none(self):
        """Test that retrieving a non-existent run_id returns None."""
        result = get_memory_extraction_debug("non-existent-run-id")
        assert result is None

    def test_ttl_eviction(self):
        """Test that stale entries are evicted based on TTL."""
        # Insert an entry with a manually backdated timestamp
        _memory_extraction_debug_cache["old-run"] = (
            time.monotonic() - 300.0,  # 5 minutes ago (well past 120s TTL)
            {"enabled": True, "extracted_memories": []},
        )

        # Insert a fresh entry
        _cache_debug_result("fresh-run", {"enabled": True, "extracted_memories": []})

        # Retrieve fresh entry (triggers lazy eviction of old entry)
        result = get_memory_extraction_debug("fresh-run")
        assert result is not None

        # Old entry should have been evicted
        assert "old-run" not in _memory_extraction_debug_cache

    def test_max_size_eviction(self):
        """Test that oldest entries are evicted when cache exceeds max size."""
        from src.domains.agents.services.memory_extractor import _MEMORY_DEBUG_CACHE_MAX_SIZE

        # Fill cache to max
        for i in range(_MEMORY_DEBUG_CACHE_MAX_SIZE):
            _cache_debug_result(f"run-{i}", {"enabled": True, "index": i})

        assert len(_memory_extraction_debug_cache) == _MEMORY_DEBUG_CACHE_MAX_SIZE

        # Adding one more should evict the oldest
        _cache_debug_result("run-overflow", {"enabled": True, "index": "overflow"})

        assert len(_memory_extraction_debug_cache) == _MEMORY_DEBUG_CACHE_MAX_SIZE
        # The overflow entry should be present
        assert "run-overflow" in _memory_extraction_debug_cache
