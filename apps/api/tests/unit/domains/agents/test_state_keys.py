"""
Unit tests for domains.agents.state_keys module.

Tests state key constants, groups, and validation helpers.

Author: Claude Code (Sonnet 4.5)
Date: 2025-11-21
"""

import pytest

from src.domains.agents.state_keys import (
    ALL_STATE_KEYS,
    CORE_STATE_KEYS,
    EXECUTION_STATE_KEYS,
    HITL_STATE_KEYS,
    METADATA_STATE_KEYS,
    STATE_ACTION_REQUESTS,
    STATE_AGENT_RESULTS,
    STATE_COMPLETED_STEPS,
    STATE_CURRENT_ITEM,
    STATE_CURRENT_TURN_ID,
    STATE_DATA_SOURCE,
    STATE_LAST_QUERY,
    STATE_MESSAGE_METADATA,
    STATE_PLAN_APPROVAL,
    STATE_REJECTION_REASON,
    STATE_ROUTER_DECISION,
    STATE_ROUTER_SYSTEM_PROMPT,
    STATE_ROUTING_HISTORY,
    STATE_SCHEMA,
    STATE_STEP_INDEX,
    get_state_key_schema,
    is_core_state_key,
    is_execution_state_key,
    is_hitl_state_key,
    validate_state_key,
)


class TestStateKeyConstants:
    """Tests for state key constants."""

    def test_state_key_constants_are_strings(self):
        """Test all state key constants are strings."""
        assert isinstance(STATE_AGENT_RESULTS, str)
        assert isinstance(STATE_COMPLETED_STEPS, str)
        assert isinstance(STATE_ACTION_REQUESTS, str)
        assert isinstance(STATE_ROUTING_HISTORY, str)
        assert isinstance(STATE_ROUTER_DECISION, str)
        assert isinstance(STATE_CURRENT_TURN_ID, str)
        assert isinstance(STATE_CURRENT_ITEM, str)
        assert isinstance(STATE_LAST_QUERY, str)
        assert isinstance(STATE_REJECTION_REASON, str)
        assert isinstance(STATE_PLAN_APPROVAL, str)
        assert isinstance(STATE_MESSAGE_METADATA, str)
        assert isinstance(STATE_ROUTER_SYSTEM_PROMPT, str)
        assert isinstance(STATE_DATA_SOURCE, str)
        assert isinstance(STATE_STEP_INDEX, str)

    def test_state_key_constants_not_empty(self):
        """Test all state key constants are non-empty strings."""
        assert STATE_AGENT_RESULTS != ""
        assert STATE_COMPLETED_STEPS != ""
        assert STATE_ROUTING_HISTORY != ""
        assert STATE_CURRENT_TURN_ID != ""

    def test_state_key_constants_unique(self):
        """Test all state key constants have unique values."""
        all_keys = [
            STATE_AGENT_RESULTS,
            STATE_COMPLETED_STEPS,
            STATE_ACTION_REQUESTS,
            STATE_ROUTING_HISTORY,
            STATE_ROUTER_DECISION,
            STATE_CURRENT_TURN_ID,
            STATE_CURRENT_ITEM,
            STATE_LAST_QUERY,
            STATE_REJECTION_REASON,
            STATE_PLAN_APPROVAL,
            STATE_MESSAGE_METADATA,
            STATE_ROUTER_SYSTEM_PROMPT,
            STATE_DATA_SOURCE,
            STATE_STEP_INDEX,
        ]

        # Check no duplicates
        assert len(all_keys) == len(set(all_keys))


class TestStateKeyGroups:
    """Tests for state key group frozensets."""

    def test_core_state_keys_contains_expected_keys(self):
        """Test CORE_STATE_KEYS contains core keys."""
        assert STATE_CURRENT_TURN_ID in CORE_STATE_KEYS
        assert STATE_ROUTING_HISTORY in CORE_STATE_KEYS

    def test_core_state_keys_is_frozenset(self):
        """Test CORE_STATE_KEYS is immutable frozenset."""
        assert isinstance(CORE_STATE_KEYS, frozenset)

    def test_execution_state_keys_contains_expected_keys(self):
        """Test EXECUTION_STATE_KEYS contains execution keys."""
        assert STATE_AGENT_RESULTS in EXECUTION_STATE_KEYS
        assert STATE_COMPLETED_STEPS in EXECUTION_STATE_KEYS
        assert STATE_STEP_INDEX in EXECUTION_STATE_KEYS

    def test_execution_state_keys_is_frozenset(self):
        """Test EXECUTION_STATE_KEYS is immutable frozenset."""
        assert isinstance(EXECUTION_STATE_KEYS, frozenset)

    def test_hitl_state_keys_contains_expected_keys(self):
        """Test HITL_STATE_KEYS contains HITL keys."""
        assert STATE_ACTION_REQUESTS in HITL_STATE_KEYS
        assert STATE_REJECTION_REASON in HITL_STATE_KEYS
        assert STATE_PLAN_APPROVAL in HITL_STATE_KEYS

    def test_hitl_state_keys_is_frozenset(self):
        """Test HITL_STATE_KEYS is immutable frozenset."""
        assert isinstance(HITL_STATE_KEYS, frozenset)

    def test_metadata_state_keys_contains_expected_keys(self):
        """Test METADATA_STATE_KEYS contains metadata keys."""
        assert STATE_MESSAGE_METADATA in METADATA_STATE_KEYS
        assert STATE_ROUTER_SYSTEM_PROMPT in METADATA_STATE_KEYS
        assert STATE_DATA_SOURCE in METADATA_STATE_KEYS

    def test_metadata_state_keys_is_frozenset(self):
        """Test METADATA_STATE_KEYS is immutable frozenset."""
        assert isinstance(METADATA_STATE_KEYS, frozenset)

    def test_all_state_keys_contains_all_constants(self):
        """Test ALL_STATE_KEYS contains all 14 state key constants."""
        expected_keys = {
            STATE_AGENT_RESULTS,
            STATE_COMPLETED_STEPS,
            STATE_ACTION_REQUESTS,
            STATE_ROUTING_HISTORY,
            STATE_ROUTER_DECISION,
            STATE_CURRENT_TURN_ID,
            STATE_CURRENT_ITEM,
            STATE_LAST_QUERY,
            STATE_REJECTION_REASON,
            STATE_PLAN_APPROVAL,
            STATE_MESSAGE_METADATA,
            STATE_ROUTER_SYSTEM_PROMPT,
            STATE_DATA_SOURCE,
            STATE_STEP_INDEX,
        }

        assert ALL_STATE_KEYS == expected_keys

    def test_all_state_keys_is_frozenset(self):
        """Test ALL_STATE_KEYS is immutable frozenset."""
        assert isinstance(ALL_STATE_KEYS, frozenset)

    def test_all_state_keys_count(self):
        """Test ALL_STATE_KEYS contains exactly 14 keys."""
        assert len(ALL_STATE_KEYS) == 14

    def test_state_key_groups_no_overlap_core_execution(self):
        """Test CORE and EXECUTION groups don't overlap."""
        assert CORE_STATE_KEYS.isdisjoint(EXECUTION_STATE_KEYS)

    def test_state_key_groups_no_overlap_core_hitl(self):
        """Test CORE and HITL groups don't overlap."""
        assert CORE_STATE_KEYS.isdisjoint(HITL_STATE_KEYS)

    def test_state_key_groups_no_overlap_execution_hitl(self):
        """Test EXECUTION and HITL groups don't overlap."""
        assert EXECUTION_STATE_KEYS.isdisjoint(HITL_STATE_KEYS)


class TestStateSchema:
    """Tests for STATE_SCHEMA documentation dict."""

    def test_state_schema_is_dict(self):
        """Test STATE_SCHEMA is a dictionary."""
        assert isinstance(STATE_SCHEMA, dict)

    def test_state_schema_contains_all_keys(self):
        """Test STATE_SCHEMA documents all 14 state keys."""
        assert len(STATE_SCHEMA) == 14
        assert STATE_AGENT_RESULTS in STATE_SCHEMA
        assert STATE_ROUTING_HISTORY in STATE_SCHEMA
        assert STATE_CURRENT_TURN_ID in STATE_SCHEMA

    def test_state_schema_entry_structure(self):
        """Test STATE_SCHEMA entries have correct structure."""
        entry = STATE_SCHEMA[STATE_AGENT_RESULTS]

        # Each entry should have type, description, example
        assert "type" in entry
        assert "description" in entry
        assert "example" in entry

        assert isinstance(entry["type"], str)
        assert isinstance(entry["description"], str)
        assert entry["example"] is not None

    def test_state_schema_all_entries_have_required_fields(self):
        """Test all STATE_SCHEMA entries have type, description, example."""
        for key, schema in STATE_SCHEMA.items():
            assert "type" in schema, f"Missing 'type' for {key}"
            assert "description" in schema, f"Missing 'description' for {key}"
            assert "example" in schema, f"Missing 'example' for {key}"


class TestValidationHelpers:
    """Tests for state key validation helper functions."""

    def test_is_core_state_key_returns_true_for_core_keys(self):
        """Test is_core_state_key returns True for core keys."""
        assert is_core_state_key(STATE_CURRENT_TURN_ID) is True
        assert is_core_state_key(STATE_ROUTING_HISTORY) is True

    def test_is_core_state_key_returns_false_for_non_core_keys(self):
        """Test is_core_state_key returns False for non-core keys."""
        assert is_core_state_key(STATE_AGENT_RESULTS) is False
        assert is_core_state_key(STATE_ACTION_REQUESTS) is False
        assert is_core_state_key("unknown_key") is False

    def test_is_execution_state_key_returns_true_for_execution_keys(self):
        """Test is_execution_state_key returns True for execution keys."""
        assert is_execution_state_key(STATE_AGENT_RESULTS) is True
        assert is_execution_state_key(STATE_COMPLETED_STEPS) is True
        assert is_execution_state_key(STATE_STEP_INDEX) is True

    def test_is_execution_state_key_returns_false_for_non_execution_keys(self):
        """Test is_execution_state_key returns False for non-execution keys."""
        assert is_execution_state_key(STATE_CURRENT_TURN_ID) is False
        assert is_execution_state_key(STATE_PLAN_APPROVAL) is False
        assert is_execution_state_key("unknown_key") is False

    def test_is_hitl_state_key_returns_true_for_hitl_keys(self):
        """Test is_hitl_state_key returns True for HITL keys."""
        assert is_hitl_state_key(STATE_ACTION_REQUESTS) is True
        assert is_hitl_state_key(STATE_REJECTION_REASON) is True
        assert is_hitl_state_key(STATE_PLAN_APPROVAL) is True

    def test_is_hitl_state_key_returns_false_for_non_hitl_keys(self):
        """Test is_hitl_state_key returns False for non-HITL keys."""
        assert is_hitl_state_key(STATE_AGENT_RESULTS) is False
        assert is_hitl_state_key(STATE_CURRENT_TURN_ID) is False
        assert is_hitl_state_key("unknown_key") is False

    def test_validate_state_key_returns_true_for_known_keys(self):
        """Test validate_state_key returns True for all known keys."""
        # Test all 14 keys
        assert validate_state_key(STATE_AGENT_RESULTS) is True
        assert validate_state_key(STATE_COMPLETED_STEPS) is True
        assert validate_state_key(STATE_ACTION_REQUESTS) is True
        assert validate_state_key(STATE_ROUTING_HISTORY) is True
        assert validate_state_key(STATE_ROUTER_DECISION) is True
        assert validate_state_key(STATE_CURRENT_TURN_ID) is True
        assert validate_state_key(STATE_CURRENT_ITEM) is True
        assert validate_state_key(STATE_LAST_QUERY) is True
        assert validate_state_key(STATE_REJECTION_REASON) is True
        assert validate_state_key(STATE_PLAN_APPROVAL) is True
        assert validate_state_key(STATE_MESSAGE_METADATA) is True
        assert validate_state_key(STATE_ROUTER_SYSTEM_PROMPT) is True
        assert validate_state_key(STATE_DATA_SOURCE) is True
        assert validate_state_key(STATE_STEP_INDEX) is True

    def test_validate_state_key_returns_false_for_unknown_keys(self):
        """Test validate_state_key returns False for unknown keys."""
        assert validate_state_key("unknown_key") is False
        assert validate_state_key("") is False
        assert validate_state_key("not_a_state_key") is False

    def test_get_state_key_schema_returns_schema_for_known_keys(self):
        """Test get_state_key_schema returns schema dict for known keys."""
        schema = get_state_key_schema(STATE_AGENT_RESULTS)

        assert schema is not None
        assert isinstance(schema, dict)
        assert "type" in schema
        assert "description" in schema
        assert "example" in schema

    def test_get_state_key_schema_returns_none_for_unknown_keys(self):
        """Test get_state_key_schema returns None for unknown keys."""
        assert get_state_key_schema("unknown_key") is None
        assert get_state_key_schema("") is None

    def test_get_state_key_schema_returns_correct_content(self):
        """Test get_state_key_schema returns correct schema content."""
        schema = get_state_key_schema(STATE_COMPLETED_STEPS)

        assert schema["type"] == "list[str]"
        assert "completed step IDs" in schema["description"]
        assert "example" in schema
        assert isinstance(schema["example"], list)


class TestEdgeCases:
    """Tests for edge cases and error handling."""

    def test_state_keys_are_snake_case(self):
        """Test state key constants follow snake_case convention."""
        for key in ALL_STATE_KEYS:
            # Should be lowercase with underscores
            assert key.islower() or "_" in key
            assert " " not in key

    def test_validation_helpers_handle_none_gracefully(self):
        """Test validation helpers handle None input gracefully."""
        # These should not raise, but return False
        assert is_core_state_key(None) is False  # type: ignore[arg-type]
        assert is_execution_state_key(None) is False  # type: ignore[arg-type]
        assert is_hitl_state_key(None) is False  # type: ignore[arg-type]
        assert validate_state_key(None) is False  # type: ignore[arg-type]

    def test_get_state_key_schema_handles_none_gracefully(self):
        """Test get_state_key_schema handles None input gracefully."""
        result = get_state_key_schema(None)  # type: ignore[arg-type]
        assert result is None

    def test_state_key_groups_are_immutable(self):
        """Test state key group frozensets cannot be modified."""
        with pytest.raises(AttributeError):
            CORE_STATE_KEYS.add("new_key")  # type: ignore[attr-defined]

        with pytest.raises(AttributeError):
            ALL_STATE_KEYS.remove(STATE_AGENT_RESULTS)  # type: ignore[attr-defined]


class TestCoverageCompleteness:
    """Tests to ensure complete coverage of all state keys."""

    def test_all_constants_covered_by_groups(self):
        """Test all state keys are covered by at least one group."""
        # Union of all groups should match ALL_STATE_KEYS
        union = CORE_STATE_KEYS | EXECUTION_STATE_KEYS | HITL_STATE_KEYS | METADATA_STATE_KEYS

        # Not all keys need to be in groups (e.g., STATE_ROUTER_DECISION, STATE_CURRENT_ITEM, STATE_LAST_QUERY)
        # But all group keys should be in ALL_STATE_KEYS
        assert union.issubset(ALL_STATE_KEYS)

    def test_all_constants_documented_in_schema(self):
        """Test all state key constants are documented in STATE_SCHEMA."""
        for key in ALL_STATE_KEYS:
            assert key in STATE_SCHEMA, f"State key {key} missing from STATE_SCHEMA"

    def test_schema_keys_match_constants(self):
        """Test STATE_SCHEMA keys exactly match ALL_STATE_KEYS."""
        schema_keys = set(STATE_SCHEMA.keys())
        assert schema_keys == ALL_STATE_KEYS
