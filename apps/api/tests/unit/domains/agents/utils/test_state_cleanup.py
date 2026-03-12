"""
Unit tests for state cleanup utilities.

Tests for maintaining bounded state sizes by cleaning up
old data from lists and dictionaries in MessagesState.
"""

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from src.domains.agents.utils.state_cleanup import (
    cleanup_dict_by_limit,
    cleanup_dict_by_turn_id,
    cleanup_list_by_limit,
    estimate_dict_memory_size,
)

# ============================================================================
# Test fixtures and helpers
# ============================================================================


@dataclass
class MockRouterOutput:
    """Mock RouterOutput for testing list cleanup."""

    decision: str
    turn_id: int


@dataclass
class MockAgentResult:
    """Mock AgentResult for testing dict cleanup."""

    agent_name: str
    data: dict


# ============================================================================
# Tests for cleanup_list_by_limit
# ============================================================================


class TestCleanupListByLimitBasic:
    """Tests for basic list cleanup functionality."""

    def test_list_under_limit_unchanged(self):
        """Test that list under limit is returned unchanged."""
        items = [1, 2, 3, 4, 5]
        result = cleanup_list_by_limit(items, max_items=10)

        assert result == items
        assert result is items  # Should return same reference

    def test_list_at_limit_unchanged(self):
        """Test that list exactly at limit is returned unchanged."""
        items = [1, 2, 3, 4, 5]
        result = cleanup_list_by_limit(items, max_items=5)

        assert result == items
        assert result is items

    def test_list_over_limit_truncated(self):
        """Test that list over limit keeps last N items."""
        items = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        result = cleanup_list_by_limit(items, max_items=5)

        assert result == [6, 7, 8, 9, 10]
        assert len(result) == 5

    def test_empty_list_returns_empty(self):
        """Test that empty list returns empty."""
        result = cleanup_list_by_limit([], max_items=10)
        assert result == []

    def test_max_items_one(self):
        """Test with max_items=1 keeps only last item."""
        items = [1, 2, 3, 4, 5]
        result = cleanup_list_by_limit(items, max_items=1)

        assert result == [5]

    def test_max_items_zero(self):
        """Test with max_items=0 returns full list (edge case - Python slice behavior).

        Note: items[-0:] returns full list in Python, so max_items=0 doesn't
        produce an empty result. This is implementation-specific behavior.
        """
        items = [1, 2, 3, 4, 5]
        result = cleanup_list_by_limit(items, max_items=0)

        # Python's items[-0:] returns full list, not empty
        assert result == items


class TestCleanupListByLimitTypes:
    """Tests for cleanup_list_by_limit with different types."""

    def test_with_strings(self):
        """Test list cleanup with strings."""
        items = ["a", "b", "c", "d", "e", "f"]
        result = cleanup_list_by_limit(items, max_items=3)

        assert result == ["d", "e", "f"]

    def test_with_dataclasses(self):
        """Test list cleanup with dataclass instances."""
        items = [
            MockRouterOutput("chat", 1),
            MockRouterOutput("planner", 2),
            MockRouterOutput("chat", 3),
            MockRouterOutput("planner", 4),
        ]
        result = cleanup_list_by_limit(items, max_items=2)

        assert len(result) == 2
        assert result[0].turn_id == 3
        assert result[1].turn_id == 4

    def test_with_dicts(self):
        """Test list cleanup with dictionaries."""
        items = [{"id": i} for i in range(10)]
        result = cleanup_list_by_limit(items, max_items=3)

        assert len(result) == 3
        assert result[0]["id"] == 7
        assert result[1]["id"] == 8
        assert result[2]["id"] == 9

    def test_with_mixed_types(self):
        """Test list cleanup with mixed types."""
        items: list[Any] = [1, "two", 3.0, None, {"key": "value"}]
        result = cleanup_list_by_limit(items, max_items=3)

        assert result == [3.0, None, {"key": "value"}]


class TestCleanupListByLimitLogging:
    """Tests for logging in cleanup_list_by_limit."""

    def test_logs_debug_when_truncating(self):
        """Test that debug logging occurs when truncating."""
        items = list(range(10))

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_list_by_limit(items, max_items=5, label="test_items")

            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args
            assert call_args[0][0] == "cleanup_list_by_limit"
            assert call_args[1]["label"] == "test_items"
            assert call_args[1]["original_count"] == 10
            assert call_args[1]["kept_count"] == 5
            assert call_args[1]["removed"] == 5

    def test_no_logging_when_under_limit(self):
        """Test that no logging occurs when under limit."""
        items = [1, 2, 3]

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_list_by_limit(items, max_items=10)

            mock_logger.debug.assert_not_called()

    def test_custom_label_in_logging(self):
        """Test that custom label appears in log."""
        items = list(range(20))

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_list_by_limit(items, max_items=10, label="routing_history")

            call_args = mock_logger.debug.call_args
            assert call_args[1]["label"] == "routing_history"


# ============================================================================
# Tests for cleanup_dict_by_turn_id
# ============================================================================


class TestCleanupDictByTurnIdBasic:
    """Tests for basic turn-based dictionary cleanup."""

    def test_dict_under_limit_unchanged(self):
        """Test that dict under limit is returned unchanged."""
        results = {
            "1:contacts_agent": {"data": "contact1"},
            "1:emails_agent": {"data": "email1"},
        }
        result = cleanup_dict_by_turn_id(results, max_results=10)

        assert result == results
        assert result is results

    def test_dict_at_limit_unchanged(self):
        """Test that dict exactly at limit is returned unchanged."""
        results = {
            "1:contacts_agent": {"data": "contact1"},
            "1:emails_agent": {"data": "email1"},
        }
        result = cleanup_dict_by_turn_id(results, max_results=2)

        assert result == results

    def test_empty_dict_returns_empty(self):
        """Test that empty dict returns empty."""
        result = cleanup_dict_by_turn_id({}, max_results=10)
        assert result == {}

    def test_keeps_complete_turns_only(self):
        """Test that cleanup keeps complete turns (all agents of a turn)."""
        results = {
            "1:contacts_agent": {"data": "c1"},
            "1:emails_agent": {"data": "e1"},
            "2:contacts_agent": {"data": "c2"},
            "2:emails_agent": {"data": "e2"},
            "3:contacts_agent": {"data": "c3"},
            "3:emails_agent": {"data": "e3"},
        }
        # With max_results=4, we can fit 2 complete turns (4 results)
        result = cleanup_dict_by_turn_id(results, max_results=4)

        # Should keep turns 2 and 3 (most recent)
        assert len(result) == 4
        assert "2:contacts_agent" in result
        assert "2:emails_agent" in result
        assert "3:contacts_agent" in result
        assert "3:emails_agent" in result
        # Turn 1 should be removed
        assert "1:contacts_agent" not in result
        assert "1:emails_agent" not in result


class TestCleanupDictByTurnIdEdgeCases:
    """Tests for edge cases in turn-based cleanup."""

    def test_single_turn_exceeds_limit(self):
        """Test when a single turn has more results than limit."""
        results = {
            "1:agent_a": {"data": "a"},
            "1:agent_b": {"data": "b"},
            "1:agent_c": {"data": "c"},
            "1:agent_d": {"data": "d"},
            "1:agent_e": {"data": "e"},
        }
        # max_results=2, but single turn has 5 results
        result = cleanup_dict_by_turn_id(results, max_results=2)

        # Can't fit a complete turn, so should be empty
        assert result == {}

    def test_keeps_most_recent_turns(self):
        """Test that most recent turns are kept."""
        results = {
            "5:agent": {"turn": 5},
            "10:agent": {"turn": 10},
            "1:agent": {"turn": 1},
            "15:agent": {"turn": 15},
        }
        result = cleanup_dict_by_turn_id(results, max_results=2)

        # Should keep turns 10 and 15 (most recent)
        assert len(result) == 2
        assert "15:agent" in result
        assert "10:agent" in result

    def test_old_format_without_turn_id(self):
        """Test backward compatibility with old format keys."""
        results = {
            "contacts_agent": {"data": "old_format"},
            "1:emails_agent": {"data": "new_format"},
        }
        result = cleanup_dict_by_turn_id(results, max_results=10)

        # Both formats should be preserved
        assert "contacts_agent" in result
        assert "1:emails_agent" in result

    def test_old_format_counted_as_special_bucket(self):
        """Test old format keys are grouped in special bucket (-1)."""
        results = {
            "old_key1": {"data": 1},
            "old_key2": {"data": 2},
            "1:new_key": {"data": 3},
        }
        result = cleanup_dict_by_turn_id(results, max_results=10)

        assert len(result) == 3

    def test_invalid_turn_id_format(self):
        """Test handling of invalid composite key format."""
        # Need enough items to trigger cleanup path (exceed max_results)
        results = {
            "not_a_number:agent": {"data": "invalid"},
            "1:valid_agent": {"data": "valid1"},
            "2:valid_agent": {"data": "valid2"},
            "3:valid_agent": {"data": "valid3"},
        }

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            result = cleanup_dict_by_turn_id(results, max_results=2)

            # Warning should be logged for invalid format
            mock_logger.warning.assert_called()
            # Result should contain most recent turns
            assert len(result) <= 2


class TestCleanupDictByTurnIdMixedTurns:
    """Tests for mixed turn scenarios."""

    def test_uneven_agents_per_turn(self):
        """Test with different number of agents per turn."""
        results = {
            "1:agent_a": {"data": "1a"},
            "1:agent_b": {"data": "1b"},
            "2:agent_a": {"data": "2a"},  # Turn 2 has only 1 agent
            "3:agent_a": {"data": "3a"},
            "3:agent_b": {"data": "3b"},
            "3:agent_c": {"data": "3c"},  # Turn 3 has 3 agents
        }
        # max_results=4, turn 3 has 3 + turn 2 has 1 = 4
        result = cleanup_dict_by_turn_id(results, max_results=4)

        assert len(result) == 4
        assert "3:agent_a" in result
        assert "3:agent_b" in result
        assert "3:agent_c" in result
        assert "2:agent_a" in result

    def test_partial_fit_stops_at_complete_turn(self):
        """Test that partial turns are not included."""
        results = {
            "1:agent_a": {"data": "1a"},
            "1:agent_b": {"data": "1b"},
            "2:agent_a": {"data": "2a"},
            "2:agent_b": {"data": "2b"},
            "3:agent_a": {"data": "3a"},
            "3:agent_b": {"data": "3b"},
        }
        # max_results=5, turn 3 (2) + turn 2 (2) = 4, can't add turn 1 (would be 6)
        result = cleanup_dict_by_turn_id(results, max_results=5)

        assert len(result) == 4
        # Turns 2 and 3 fit completely
        assert "2:agent_a" in result
        assert "2:agent_b" in result
        assert "3:agent_a" in result
        assert "3:agent_b" in result


class TestCleanupDictByTurnIdLogging:
    """Tests for logging in cleanup_dict_by_turn_id."""

    def test_logs_debug_when_cleaning(self):
        """Test that debug logging occurs when cleaning."""
        results = {f"{i}:agent": {"data": i} for i in range(10)}

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_dict_by_turn_id(results, max_results=5, label="agent_results")

            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args
            assert call_args[0][0] == "cleanup_dict_by_turn_id"
            assert call_args[1]["label"] == "agent_results"
            assert call_args[1]["original_count"] == 10

    def test_no_logging_when_under_limit(self):
        """Test that no logging occurs when under limit."""
        results = {"1:agent": {"data": 1}}

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_dict_by_turn_id(results, max_results=10)

            mock_logger.debug.assert_not_called()


# ============================================================================
# Tests for cleanup_dict_by_limit
# ============================================================================


class TestCleanupDictByLimitBasic:
    """Tests for basic dictionary cleanup by limit."""

    def test_dict_under_limit_unchanged(self):
        """Test that dict under limit is returned unchanged."""
        items = {"a": 1, "b": 2, "c": 3}
        result = cleanup_dict_by_limit(items, max_items=10)

        assert result == items
        assert result is items

    def test_dict_at_limit_unchanged(self):
        """Test that dict exactly at limit is returned unchanged."""
        items = {"a": 1, "b": 2, "c": 3}
        result = cleanup_dict_by_limit(items, max_items=3)

        assert result == items

    def test_dict_over_limit_truncated(self):
        """Test that dict over limit keeps last N items."""
        # Python 3.7+ preserves insertion order
        items = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}
        result = cleanup_dict_by_limit(items, max_items=3)

        assert len(result) == 3
        assert "c" in result
        assert "d" in result
        assert "e" in result
        assert "a" not in result
        assert "b" not in result

    def test_empty_dict_returns_empty(self):
        """Test that empty dict returns empty."""
        result = cleanup_dict_by_limit({}, max_items=10)
        assert result == {}

    def test_max_items_one(self):
        """Test with max_items=1 keeps only last item."""
        items = {"a": 1, "b": 2, "c": 3}
        result = cleanup_dict_by_limit(items, max_items=1)

        assert result == {"c": 3}

    def test_max_items_zero(self):
        """Test with max_items=0 returns full dict (edge case - Python slice behavior).

        Note: list(items.keys())[-0:] returns full list in Python, so max_items=0
        doesn't produce an empty result. This is implementation-specific behavior.
        """
        items = {"a": 1, "b": 2, "c": 3}
        result = cleanup_dict_by_limit(items, max_items=0)

        # Python's list[-0:] returns full list, not empty
        assert result == items


class TestCleanupDictByLimitTypes:
    """Tests for cleanup_dict_by_limit with different value types."""

    def test_with_string_values(self):
        """Test dict cleanup with string values."""
        items = {f"key{i}": f"value{i}" for i in range(10)}
        result = cleanup_dict_by_limit(items, max_items=3)

        assert len(result) == 3
        assert "key7" in result
        assert "key8" in result
        assert "key9" in result

    def test_with_nested_dicts(self):
        """Test dict cleanup with nested dictionary values."""
        items = {
            "first": {"nested": "value1"},
            "second": {"nested": "value2"},
            "third": {"nested": "value3"},
        }
        result = cleanup_dict_by_limit(items, max_items=2)

        assert len(result) == 2
        assert "second" in result
        assert "third" in result
        assert result["third"]["nested"] == "value3"

    def test_with_dataclass_values(self):
        """Test dict cleanup with dataclass values."""
        items = {
            "r1": MockAgentResult("agent1", {"data": 1}),
            "r2": MockAgentResult("agent2", {"data": 2}),
            "r3": MockAgentResult("agent3", {"data": 3}),
        }
        result = cleanup_dict_by_limit(items, max_items=2)

        assert len(result) == 2
        assert "r2" in result
        assert "r3" in result


class TestCleanupDictByLimitLogging:
    """Tests for logging in cleanup_dict_by_limit."""

    def test_logs_debug_when_truncating(self):
        """Test that debug logging occurs when truncating."""
        items = {f"k{i}": i for i in range(10)}

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_dict_by_limit(items, max_items=5, label="cache")

            mock_logger.debug.assert_called_once()
            call_args = mock_logger.debug.call_args
            assert call_args[0][0] == "cleanup_dict_by_limit"
            assert call_args[1]["label"] == "cache"
            assert call_args[1]["original_count"] == 10
            assert call_args[1]["kept_count"] == 5
            assert call_args[1]["removed"] == 5

    def test_no_logging_when_under_limit(self):
        """Test that no logging occurs when under limit."""
        items = {"a": 1}

        with patch("src.domains.agents.utils.state_cleanup.logger") as mock_logger:
            cleanup_dict_by_limit(items, max_items=10)

            mock_logger.debug.assert_not_called()


# ============================================================================
# Tests for estimate_dict_memory_size
# ============================================================================


class TestEstimateDictMemorySizeBasic:
    """Tests for basic memory size estimation."""

    def test_empty_dict_returns_positive(self):
        """Test that empty dict returns positive size (overhead)."""
        size = estimate_dict_memory_size({})
        assert size > 0

    def test_larger_dict_has_larger_size(self):
        """Test that larger dict has larger estimated size."""
        small = {"a": 1}
        large = {f"key{i}": i for i in range(100)}

        small_size = estimate_dict_memory_size(small)
        large_size = estimate_dict_memory_size(large)

        assert large_size > small_size

    def test_returns_integer(self):
        """Test that size is returned as integer."""
        size = estimate_dict_memory_size({"key": "value"})
        assert isinstance(size, int)


class TestEstimateDictMemorySizeTypes:
    """Tests for memory estimation with different types."""

    def test_with_string_values(self):
        """Test estimation with string values."""
        items = {"key": "a" * 1000}  # 1000 char string
        size = estimate_dict_memory_size(items)

        # String of 1000 chars should be at least 1000 bytes
        assert size >= 1000

    def test_with_nested_dict(self):
        """Test estimation with nested dictionary (shallow count only)."""
        items = {"outer": {"inner": {"deep": "value"}}}
        size = estimate_dict_memory_size(items)

        # Should count outer dict size, key size, and value size (which is inner dict ref)
        assert size > 0

    def test_with_list_values(self):
        """Test estimation with list values."""
        items = {"numbers": list(range(100))}
        size = estimate_dict_memory_size(items)

        # List reference counted, not deep
        assert size > 0

    def test_with_none_values(self):
        """Test estimation with None values."""
        items = {"null": None, "also_null": None}
        size = estimate_dict_memory_size(items)

        assert size > 0


class TestEstimateDictMemorySizeConsistency:
    """Tests for consistency of memory estimation."""

    def test_same_content_same_estimate(self):
        """Test that same content gives same estimate."""
        items1 = {"key": "value", "num": 123}
        items2 = {"key": "value", "num": 123}

        size1 = estimate_dict_memory_size(items1)
        size2 = estimate_dict_memory_size(items2)

        assert size1 == size2

    def test_different_keys_different_sizes(self):
        """Test that different key lengths affect size."""
        short_keys = {"a": 1, "b": 2}
        long_keys = {"long_key_name_1": 1, "long_key_name_2": 2}

        short_size = estimate_dict_memory_size(short_keys)
        long_size = estimate_dict_memory_size(long_keys)

        # Long keys should result in larger size
        assert long_size > short_size


# ============================================================================
# Tests for module interface
# ============================================================================


class TestModuleInterface:
    """Tests for module exports and interface."""

    def test_all_functions_exported(self):
        """Test that __all__ contains all public functions."""
        from src.domains.agents.utils import state_cleanup

        expected_exports = [
            "cleanup_dict_by_limit",
            "cleanup_dict_by_turn_id",
            "cleanup_list_by_limit",
            "estimate_dict_memory_size",
        ]

        for export in expected_exports:
            assert export in state_cleanup.__all__
            assert hasattr(state_cleanup, export)

    def test_functions_are_callable(self):
        """Test that all exported functions are callable."""
        from src.domains.agents.utils import state_cleanup

        for name in state_cleanup.__all__:
            func = getattr(state_cleanup, name)
            assert callable(func)


# ============================================================================
# Integration-style tests
# ============================================================================


class TestCleanupIntegration:
    """Integration tests combining multiple cleanup functions."""

    def test_list_and_dict_cleanup_together(self):
        """Test using both list and dict cleanup in sequence."""
        # Simulate a state with both list and dict fields
        routing_history = [{"decision": "chat", "turn": i} for i in range(50)]
        agent_results = {f"{i}:contacts_agent": {"data": i} for i in range(30)}

        # Clean both
        cleaned_history = cleanup_list_by_limit(
            routing_history, max_items=20, label="routing_history"
        )
        cleaned_results = cleanup_dict_by_turn_id(
            agent_results, max_results=15, label="agent_results"
        )

        assert len(cleaned_history) == 20
        assert len(cleaned_results) == 15
        # History keeps last items
        assert cleaned_history[0]["turn"] == 30
        # Results keep most recent turns
        assert "29:contacts_agent" in cleaned_results

    def test_memory_estimate_before_and_after_cleanup(self):
        """Test memory size changes after cleanup."""
        large_dict = {f"key{i}": {"data": "x" * 100} for i in range(100)}

        before_size = estimate_dict_memory_size(large_dict)
        cleaned = cleanup_dict_by_limit(large_dict, max_items=10)
        after_size = estimate_dict_memory_size(cleaned)

        # After cleanup should be significantly smaller
        assert after_size < before_size
        # Roughly 10x smaller (not exact due to dict overhead)
        assert after_size < before_size * 0.2

    def test_realistic_agent_state_cleanup(self):
        """Test cleanup with realistic agent state structure."""
        # Simulate 20 turns with 3 agents each
        agent_results = {}
        for turn in range(1, 21):
            for agent in ["contacts", "emails", "calendar"]:
                key = f"{turn}:{agent}_agent"
                agent_results[key] = {
                    "agent_name": f"{agent}_agent",
                    "turn_id": turn,
                    "data": {"items": [1, 2, 3]},
                }

        # Clean to keep ~10 turns worth (30 results)
        cleaned = cleanup_dict_by_turn_id(agent_results, max_results=30)

        # Should have exactly 30 results (10 complete turns)
        assert len(cleaned) == 30

        # Should keep turns 11-20 (most recent)
        for turn in range(11, 21):
            for agent in ["contacts", "emails", "calendar"]:
                assert f"{turn}:{agent}_agent" in cleaned

        # Turns 1-10 should be removed
        for turn in range(1, 11):
            for agent in ["contacts", "emails", "calendar"]:
                assert f"{turn}:{agent}_agent" not in cleaned
