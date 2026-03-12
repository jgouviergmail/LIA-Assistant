"""
Unit tests for registry filtering utilities.

Tests for filtering data registry to relevant items
for display and response generation.
"""

from dataclasses import dataclass
from typing import Any
from unittest.mock import patch

from src.domains.agents.utils.registry_filtering import (
    build_registry_payload_index,
    filter_registry_by_current_turn,
    filter_registry_by_relevant_ids,
    parse_relevant_ids_from_response,
)

# ============================================================================
# Test fixtures and helpers
# ============================================================================


@dataclass
class MockRegistryItem:
    """Mock RegistryItem for testing."""

    payload: dict[str, Any]
    turn_id: int = 1


# ============================================================================
# Tests for build_registry_payload_index
# ============================================================================


class TestBuildRegistryPayloadIndexBasic:
    """Tests for basic payload index building."""

    def test_empty_registry(self):
        """Test building index from empty registry."""
        result = build_registry_payload_index({})
        assert result == {}

    def test_single_item_with_id(self):
        """Test index building with single item having 'id'."""
        registry = {"contact_abc123": {"payload": {"id": "person/123", "name": "John"}}}
        result = build_registry_payload_index(registry)

        assert result["person/123"] == "contact_abc123"

    def test_single_item_with_resource_name(self):
        """Test index building with 'resourceName' (Google Contacts)."""
        registry = {"contact_def456": {"payload": {"resourceName": "people/456", "name": "Jane"}}}
        result = build_registry_payload_index(registry)

        assert result["people/456"] == "contact_def456"

    def test_multiple_items(self):
        """Test index building with multiple items."""
        registry = {
            "contact_a": {"payload": {"id": "id_a"}},
            "contact_b": {"payload": {"id": "id_b"}},
            "place_c": {"payload": {"place_id": "place_c_id"}},
        }
        result = build_registry_payload_index(registry)

        assert result["id_a"] == "contact_a"
        assert result["id_b"] == "contact_b"
        assert result["place_c_id"] == "place_c"


class TestBuildRegistryPayloadIndexIdFields:
    """Tests for various ID field types."""

    def test_place_id(self):
        """Test index with place_id (Google Places)."""
        registry = {"place_abc": {"payload": {"place_id": "ChIJ123", "name": "Restaurant"}}}
        result = build_registry_payload_index(registry)

        assert result["ChIJ123"] == "place_abc"

    def test_place_id_camel_case(self):
        """Test index with placeId (camelCase)."""
        registry = {"place_def": {"payload": {"placeId": "ChIJ456", "name": "Cafe"}}}
        result = build_registry_payload_index(registry)

        assert result["ChIJ456"] == "place_def"

    def test_file_id(self):
        """Test index with file_id (Google Drive)."""
        registry = {"file_xyz": {"payload": {"file_id": "1ABC", "name": "doc.pdf"}}}
        result = build_registry_payload_index(registry)

        assert result["1ABC"] == "file_xyz"

    def test_thread_id(self):
        """Test index with threadId (Gmail)."""
        registry = {"email_thread": {"payload": {"threadId": "thread123", "subject": "Hello"}}}
        result = build_registry_payload_index(registry)

        assert result["thread123"] == "email_thread"

    def test_event_id(self):
        """Test index with eventId (Google Calendar)."""
        registry = {"event_cal": {"payload": {"eventId": "event789", "title": "Meeting"}}}
        result = build_registry_payload_index(registry)

        assert result["event789"] == "event_cal"

    def test_multiple_id_fields_on_same_item(self):
        """Test item with multiple ID fields all get indexed."""
        registry = {
            "item_multi": {
                "payload": {
                    "id": "id_value",
                    "resourceName": "resource_value",
                    "name": "Test",
                }
            }
        }
        result = build_registry_payload_index(registry)

        # Both IDs should point to same registry key
        assert result["id_value"] == "item_multi"
        assert result["resource_value"] == "item_multi"


class TestBuildRegistryPayloadIndexFormats:
    """Tests for different registry item formats."""

    def test_pydantic_like_item(self):
        """Test with Pydantic-like RegistryItem object."""
        mock_item = MockRegistryItem(payload={"id": "obj_id", "name": "Object"})
        registry = {"item_obj": mock_item}

        result = build_registry_payload_index(registry)

        assert result["obj_id"] == "item_obj"

    def test_dict_without_payload_key(self):
        """Test with dict that IS the payload (no nested payload)."""
        registry = {"direct_item": {"id": "direct_id", "name": "Direct"}}
        result = build_registry_payload_index(registry)

        assert result["direct_id"] == "direct_item"

    def test_skips_items_without_payload(self):
        """Test that items without valid payload are skipped."""
        registry = {
            "no_payload": {"other": "data"},
            "valid": {"payload": {"id": "valid_id"}},
        }
        result = build_registry_payload_index(registry)

        assert "valid_id" in result
        assert len(result) == 1

    def test_skips_non_string_ids(self):
        """Test that non-string IDs are skipped."""
        registry = {
            "num_id": {"payload": {"id": 12345}},  # int, not string
            "str_id": {"payload": {"id": "string_id"}},
        }
        result = build_registry_payload_index(registry)

        assert "string_id" in result
        assert len(result) == 1


# ============================================================================
# Tests for filter_registry_by_current_turn
# ============================================================================


class TestFilterRegistryByCurrentTurnBasic:
    """Tests for basic turn-based filtering."""

    def test_returns_registry_when_turn_id_none(self):
        """Test that original registry is returned when turn_id is None."""
        registry = {"item_a": {"data": 1}}
        result = filter_registry_by_current_turn(
            agent_results={},
            current_turn_id=None,
            data_registry=registry,
        )

        assert result == registry

    def test_returns_registry_when_empty(self):
        """Test that empty registry is returned as-is."""
        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results={"1:agent": {"registry_updates": {"k": "v"}}},
                current_turn_id=1,
                data_registry={},
            )

        assert result == {}

    def test_filters_by_registry_updates(self):
        """Test filtering based on registry_updates from agent_results."""
        registry = {
            "item_a": {"data": "a"},
            "item_b": {"data": "b"},
            "item_c": {"data": "c"},
        }
        agent_results = {"2:contacts_agent": {"registry_updates": {"item_a": {}, "item_b": {}}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results=agent_results,
                current_turn_id=2,
                data_registry=registry,
            )

        assert len(result) == 2
        assert "item_a" in result
        assert "item_b" in result
        assert "item_c" not in result


class TestFilterRegistryByCurrentTurnAgentResults:
    """Tests for different agent_results formats."""

    def test_with_dict_result(self):
        """Test with agent_results as dict."""
        registry = {"item_x": {"data": "x"}}
        agent_results = {"5:emails_agent": {"registry_updates": {"item_x": {"email": "test"}}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results=agent_results,
                current_turn_id=5,
                data_registry=registry,
            )

        assert "item_x" in result

    def test_with_object_result(self):
        """Test with agent_results as object with registry_updates attribute."""

        class ResultObj:
            registry_updates = {"item_obj": {"data": 1}}

        registry = {"item_obj": {"data": "obj"}}
        agent_results = {"3:places_agent": ResultObj()}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results=agent_results,
                current_turn_id=3,
                data_registry=registry,
            )

        assert "item_obj" in result

    def test_ignores_other_turn_results(self):
        """Test that results from other turns are ignored."""
        registry = {"item_turn1": {"data": 1}, "item_turn2": {"data": 2}}
        agent_results = {
            "1:agent": {"registry_updates": {"item_turn1": {}}},
            "2:agent": {"registry_updates": {"item_turn2": {}}},
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results=agent_results,
                current_turn_id=2,
                data_registry=registry,
            )

        # Only turn 2 item
        assert len(result) == 1
        assert "item_turn2" in result


class TestFilterRegistryByCurrentTurnResolvedContext:
    """Tests for resolved_context fallback."""

    def test_uses_resolved_context_when_no_registry_updates(self):
        """Test fallback to resolved_context when no registry_updates."""
        registry = {"contact_abc": {"payload": {"id": "people/123", "name": "John"}}}
        resolved_context = {
            "items": [{"id": "people/123", "name": "John"}],
            "source_turn_id": 1,
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results={},
                current_turn_id=2,
                data_registry=registry,
                resolved_context=resolved_context,
            )

        assert len(result) == 1
        assert "contact_abc" in result

    def test_resolved_context_with_resource_name(self):
        """Test resolved_context matching by resourceName."""
        registry = {"contact_def": {"payload": {"resourceName": "people/456", "name": "Jane"}}}
        resolved_context = {
            "items": [{"resourceName": "people/456"}],
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results={},
                current_turn_id=3,
                data_registry=registry,
                resolved_context=resolved_context,
            )

        assert "contact_def" in result


class TestFilterRegistryByCurrentTurnReferenceTurn:
    """Tests for REFERENCE turn type behavior."""

    def test_reference_turn_returns_empty_when_no_match(self):
        """Test REFERENCE turn returns empty dict when no match found."""
        registry = {"item_a": {"data": "a"}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results={},
                current_turn_id=1,
                data_registry=registry,
                turn_type="REFERENCE",
            )

        # Security: REFERENCE should not leak data
        assert result == {}

    def test_reference_turn_with_match_returns_filtered(self):
        """Test REFERENCE turn returns filtered items when match found."""
        registry = {"item_a": {"data": "a"}, "item_b": {"data": "b"}}
        agent_results = {"1:agent": {"registry_updates": {"item_a": {}}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results=agent_results,
                current_turn_id=1,
                data_registry=registry,
                turn_type="REFERENCE",
            )

        assert len(result) == 1
        assert "item_a" in result


class TestFilterRegistryByCurrentTurnActionTurn:
    """Tests for ACTION turn type behavior."""

    def test_action_turn_returns_empty_when_no_updates(self):
        """Test ACTION turn returns empty dict when no registry_updates."""
        registry = {"old_item": {"data": "old"}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_current_turn(
                agent_results={},
                current_turn_id=1,
                data_registry=registry,
                turn_type="ACTION",
            )

        # Prevents cross-turn contamination
        assert result == {}


# ============================================================================
# Tests for filter_registry_by_relevant_ids
# ============================================================================


class TestFilterRegistryByRelevantIdsBasic:
    """Tests for basic relevant ID filtering."""

    def test_empty_relevant_ids_returns_empty(self):
        """Test that empty relevant_ids returns empty registry."""
        registry = {"item_a": {"data": "a"}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_relevant_ids(registry, [])

        assert result == {}

    def test_empty_registry_returns_empty(self):
        """Test that empty registry returns empty."""
        result = filter_registry_by_relevant_ids({}, ["id_1"])
        assert result == {}

    def test_filters_by_exact_registry_key(self):
        """Test filtering by exact registry key match."""
        registry = {
            "item_a": {"data": "a"},
            "item_b": {"data": "b"},
            "item_c": {"data": "c"},
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_relevant_ids(registry, ["item_a", "item_c"])

        assert len(result) == 2
        assert "item_a" in result
        assert "item_c" in result
        assert "item_b" not in result


class TestFilterRegistryByRelevantIdsPayloadMatch:
    """Tests for payload ID matching."""

    def test_matches_payload_id(self):
        """Test matching by payload 'id' field."""
        registry = {"contact_abc": {"payload": {"id": "people/123", "name": "John"}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            # LLM returns raw API ID instead of registry key
            result = filter_registry_by_relevant_ids(registry, ["people/123"])

        assert "contact_abc" in result

    def test_matches_payload_place_id(self):
        """Test matching by payload 'place_id' field."""
        registry = {"place_xyz": {"payload": {"place_id": "ChIJ123", "name": "Cafe"}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_relevant_ids(registry, ["ChIJ123"])

        assert "place_xyz" in result


class TestFilterRegistryByRelevantIdsSuffixMatch:
    """Tests for suffix matching (hash-only IDs)."""

    def test_matches_by_suffix(self):
        """Test matching by registry key suffix (hash only)."""
        registry = {"event_600dc4": {"payload": {"id": "cal123", "title": "Meeting"}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            # LLM returns only the hash suffix
            result = filter_registry_by_relevant_ids(registry, ["600dc4"])

        assert "event_600dc4" in result

    def test_suffix_match_with_multiple_items(self):
        """Test suffix matching with multiple items."""
        registry = {
            "event_abc123": {"payload": {"id": "ev1"}},
            "event_def456": {"payload": {"id": "ev2"}},
            "event_ghi789": {"payload": {"id": "ev3"}},
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_relevant_ids(registry, ["abc123", "ghi789"])

        assert len(result) == 2
        assert "event_abc123" in result
        assert "event_ghi789" in result


class TestFilterRegistryByRelevantIdsPrefixMatch:
    """Tests for prefix matching (truncated IDs)."""

    def test_matches_by_prefix_long_id(self):
        """Test matching truncated Google Calendar IDs by prefix."""
        long_cal_id = "a" * 50
        registry = {"event_cal": {"payload": {"id": long_cal_id, "title": "Meeting"}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            # LLM truncates to first 25 chars
            truncated = long_cal_id[:25]
            result = filter_registry_by_relevant_ids(registry, [truncated])

        assert "event_cal" in result

    def test_prefix_match_requires_min_length(self):
        """Test that prefix matching requires minimum 20 characters."""
        registry = {"item_abc": {"payload": {"id": "abcdefghijklmnopqrstuvwxyz"}}}

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            # 15 chars is too short for prefix matching
            short_prefix = "abcdefghijklmno"  # 15 chars
            result = filter_registry_by_relevant_ids(registry, [short_prefix])

        # Should not match (too short for prefix)
        assert len(result) == 0


class TestFilterRegistryByRelevantIdsMixedMatching:
    """Tests for mixed matching strategies."""

    def test_combines_all_matching_strategies(self):
        """Test that all matching strategies work together."""
        registry = {
            "contact_abc123": {"payload": {"id": "people/contact1"}},
            "event_def456": {"payload": {"id": "calendar_event_id_xyz"}},
            "place_ghi789": {"payload": {"place_id": "ChIJ456"}},
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            result = filter_registry_by_relevant_ids(
                registry,
                [
                    "contact_abc123",  # Exact registry key
                    "calendar_event_id_xyz",  # Payload ID
                    "ghi789",  # Suffix match
                ],
            )

        assert len(result) == 3


# ============================================================================
# Tests for parse_relevant_ids_from_response
# ============================================================================


class TestParseRelevantIdsBasic:
    """Tests for basic parsing of relevant_ids tag."""

    def test_empty_content_returns_empty(self):
        """Test empty content returns empty list and empty content."""
        ids, content = parse_relevant_ids_from_response("")
        assert ids == []
        assert content == ""

    def test_none_content_returns_empty(self):
        """Test None content returns empty list and None."""
        ids, content = parse_relevant_ids_from_response(None)  # type: ignore
        assert ids == []
        assert content is None

    def test_no_tag_returns_original(self):
        """Test content without tag returns original content."""
        original = "This is a response without any tags."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(original)

        assert ids == []
        assert content == original


class TestParseRelevantIdsWithTag:
    """Tests for parsing content with relevant_ids tag."""

    def test_parses_single_id(self):
        """Test parsing single ID in tag."""
        text = "<relevant_ids>item_abc</relevant_ids>Response text here."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["item_abc"]
        assert content == "Response text here."

    def test_parses_multiple_ids(self):
        """Test parsing multiple comma-separated IDs."""
        text = "<relevant_ids>item_a, item_b, item_c</relevant_ids>Response."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["item_a", "item_b", "item_c"]
        assert content == "Response."

    def test_parses_ids_with_extra_whitespace(self):
        """Test parsing IDs with extra whitespace."""
        text = "<relevant_ids>  id_1  ,  id_2  ,  id_3  </relevant_ids>Text."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["id_1", "id_2", "id_3"]

    def test_empty_tag_returns_empty_list(self):
        """Test that empty tag returns empty list (no matches)."""
        text = "<relevant_ids></relevant_ids>No matching items."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == []
        assert content == "No matching items."

    def test_tag_with_only_whitespace(self):
        """Test tag with only whitespace returns empty list."""
        text = "<relevant_ids>   </relevant_ids>Response."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == []


class TestParseRelevantIdsTagPosition:
    """Tests for tag in different positions."""

    def test_tag_at_beginning(self):
        """Test tag at beginning of content."""
        text = "<relevant_ids>id_1</relevant_ids>Main response content."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["id_1"]
        assert content == "Main response content."

    def test_tag_at_end(self):
        """Test tag at end of content."""
        text = "Main response content.<relevant_ids>id_1</relevant_ids>"

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["id_1"]
        assert content == "Main response content."

    def test_tag_in_middle(self):
        """Test tag in middle of content."""
        text = "Before<relevant_ids>id_1</relevant_ids>After"

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["id_1"]
        assert content == "BeforeAfter"


class TestParseRelevantIdsCaseInsensitive:
    """Tests for case insensitivity in tag matching."""

    def test_uppercase_tag(self):
        """Test uppercase tag is matched."""
        text = "<RELEVANT_IDS>id_1</RELEVANT_IDS>Text."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["id_1"]

    def test_mixed_case_tag(self):
        """Test mixed case tag is matched."""
        text = "<Relevant_Ids>id_1</Relevant_Ids>Text."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert ids == ["id_1"]


class TestParseRelevantIdsMultiline:
    """Tests for multiline content in tag."""

    def test_multiline_ids(self):
        """Test IDs split across multiple lines."""
        text = """<relevant_ids>
        id_1,
        id_2,
        id_3
        </relevant_ids>Response here."""

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(text)

        assert len(ids) == 3
        assert "id_1" in ids
        assert "id_2" in ids
        assert "id_3" in ids


# ============================================================================
# Tests for module interface
# ============================================================================


class TestModuleInterface:
    """Tests for module exports."""

    def test_functions_importable(self):
        """Test that all public functions are importable."""
        from src.domains.agents.utils.registry_filtering import (
            build_registry_payload_index,
            filter_registry_by_current_turn,
            filter_registry_by_relevant_ids,
            parse_relevant_ids_from_response,
        )

        assert callable(build_registry_payload_index)
        assert callable(filter_registry_by_current_turn)
        assert callable(filter_registry_by_relevant_ids)
        assert callable(parse_relevant_ids_from_response)


# ============================================================================
# Integration tests
# ============================================================================


class TestRegistryFilteringIntegration:
    """Integration tests for registry filtering workflow."""

    def test_full_filtering_pipeline(self):
        """Test complete filtering pipeline from response parsing to registry filtering."""
        # Registry with multiple items
        registry = {
            "contact_abc": {"payload": {"id": "people/1", "name": "John"}},
            "contact_def": {"payload": {"id": "people/2", "name": "Jane"}},
            "contact_ghi": {"payload": {"id": "people/3", "name": "Bob"}},
        }

        # LLM response with relevant_ids tag
        response = "<relevant_ids>people/1, people/3</relevant_ids>Here are the contacts."

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            # Parse response
            relevant_ids, cleaned_content = parse_relevant_ids_from_response(response)

            # Filter registry
            filtered = filter_registry_by_relevant_ids(registry, relevant_ids)

        assert len(filtered) == 2
        assert "contact_abc" in filtered  # people/1
        assert "contact_ghi" in filtered  # people/3
        assert cleaned_content == "Here are the contacts."

    def test_turn_then_intelligent_filtering(self):
        """Test turn-based filtering followed by intelligent filtering."""
        # Full registry with items from multiple turns
        registry = {
            "place_a": {"payload": {"place_id": "ChIJ1", "name": "Restaurant 1"}},
            "place_b": {"payload": {"place_id": "ChIJ2", "name": "Restaurant 2"}},
            "place_c": {"payload": {"place_id": "ChIJ3", "name": "Restaurant 3"}},
        }

        # Agent results with current turn updates
        agent_results = {
            "3:places_agent": {
                "registry_updates": {
                    "place_a": {},
                    "place_b": {},
                    "place_c": {},
                }
            }
        }

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            # First: turn-based filtering
            turn_filtered = filter_registry_by_current_turn(
                agent_results=agent_results,
                current_turn_id=3,
                data_registry=registry,
            )

            # Then: intelligent filtering (LLM selected 2 of 3)
            final = filter_registry_by_relevant_ids(turn_filtered, ["place_a", "place_c"])

        assert len(final) == 2
        assert "place_a" in final
        assert "place_c" in final

    def test_realistic_places_search_scenario(self):
        """Test realistic Places search and filter scenario."""
        # User searches for restaurants, then asks for "the Italian ones"
        registry = {
            "place_ita1": {"payload": {"place_id": "ChIJitalian1", "name": "Bella Italia"}},
            "place_ita2": {"payload": {"place_id": "ChIJitalian2", "name": "Pizzeria Roma"}},
            "place_fr1": {"payload": {"place_id": "ChIJfrench1", "name": "Le Bistrot"}},
        }

        # LLM identifies Italian restaurants
        response = (
            "<relevant_ids>ChIJitalian1,ChIJitalian2</relevant_ids>Voici les restaurants italiens."
        )

        with patch("src.domains.agents.utils.registry_filtering.logger"):
            ids, content = parse_relevant_ids_from_response(response)
            filtered = filter_registry_by_relevant_ids(registry, ids)

        assert len(filtered) == 2
        assert "place_ita1" in filtered
        assert "place_ita2" in filtered
        assert "place_fr1" not in filtered
