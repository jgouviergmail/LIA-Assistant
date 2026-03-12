"""
Unit tests for orchestration mappers.

Tests for mapping functions that convert between different result formats
in the orchestration layer.
"""

from datetime import datetime

from src.domains.agents.orchestration.mappers import (
    _detect_and_normalize_contacts_result,
    _detect_and_normalize_emails_result,
    _detect_and_normalize_places_result,
    map_execution_result_to_agent_result,
)
from src.domains.agents.orchestration.schemas import (
    ContactsResultData,
    EmailsResultData,
    ExecutionResult,
    PlacesResultData,
    StepResult,
)

# ============================================================================
# Tests for _detect_and_normalize_contacts_result
# ============================================================================


class TestDetectAndNormalizeContactsResultBasic:
    """Tests for basic contact detection and normalization."""

    def test_returns_none_for_empty_step_results(self):
        """Test that None is returned for empty step_results."""
        result = _detect_and_normalize_contacts_result([])
        assert result is None

    def test_returns_none_for_none_step_results(self):
        """Test that None is returned for step_results with only None values."""
        result = _detect_and_normalize_contacts_result([None, None])
        assert result is None

    def test_returns_none_for_no_contacts_in_results(self):
        """Test that None is returned when no contacts key exists."""
        result = _detect_and_normalize_contacts_result(
            [
                {"emails": [{"id": "1"}]},
                {"places": [{"id": "2"}]},
            ]
        )
        assert result is None

    def test_detects_single_contact(self):
        """Test detection of a single contact."""
        result = _detect_and_normalize_contacts_result(
            [{"contacts": [{"name": "Jean Dupont", "resource_name": "c1"}], "total": 1}]
        )

        assert result is not None
        assert isinstance(result, ContactsResultData)
        assert result.total_count == 1
        assert len(result.contacts) == 1
        assert result.contacts[0]["name"] == "Jean Dupont"

    def test_detects_multiple_contacts(self):
        """Test detection of multiple contacts in single result."""
        result = _detect_and_normalize_contacts_result(
            [
                {
                    "contacts": [
                        {"name": "Jean Dupont", "resource_name": "c1"},
                        {"name": "Marie Martin", "resource_name": "c2"},
                    ],
                    "total": 2,
                }
            ]
        )

        assert result is not None
        assert result.total_count == 2
        assert len(result.contacts) == 2

    def test_aggregates_contacts_from_multiple_steps(self):
        """Test aggregation from multiple step results."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1"}], "total": 1},
                {"contacts": [{"name": "Marie", "resource_name": "c2"}], "total": 1},
            ]
        )

        assert result is not None
        assert result.total_count == 2
        names = {c["name"] for c in result.contacts}
        assert "Jean" in names
        assert "Marie" in names


class TestDetectAndNormalizeContactsResultDeduplication:
    """Tests for contact deduplication by resource_name."""

    def test_deduplicates_by_resource_name(self):
        """Test that duplicate contacts are merged by resource_name."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1", "email": ""}]},
                {
                    "contacts": [
                        {"name": "Jean Updated", "resource_name": "c1", "email": "jean@test.com"}
                    ]
                },
            ]
        )

        assert result is not None
        assert result.total_count == 1

    def test_intelligent_merge_prefers_non_empty_list(self):
        """Test that non-empty list wins over empty list."""
        result = _detect_and_normalize_contacts_result(
            [
                {
                    "contacts": [
                        {"name": "Jean", "resource_name": "c1", "relations": ["spouse: Jane"]}
                    ]
                },
                {"contacts": [{"name": "Jean", "resource_name": "c1", "relations": []}]},
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert merged_contact["relations"] == ["spouse: Jane"]

    def test_intelligent_merge_prefers_longer_list(self):
        """Test that longer list wins over shorter list."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1", "phones": ["+33612345678"]}]},
                {
                    "contacts": [
                        {
                            "name": "Jean",
                            "resource_name": "c1",
                            "phones": ["+33612345678", "+33698765432"],
                        }
                    ]
                },
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert len(merged_contact["phones"]) == 2

    def test_intelligent_merge_prefers_non_empty_dict(self):
        """Test that non-empty dict wins over empty dict."""
        result = _detect_and_normalize_contacts_result(
            [
                {
                    "contacts": [
                        {"name": "Jean", "resource_name": "c1", "metadata": {"source": "google"}}
                    ]
                },
                {"contacts": [{"name": "Jean", "resource_name": "c1", "metadata": {}}]},
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert merged_contact["metadata"] == {"source": "google"}

    def test_intelligent_merge_prefers_dict_with_more_keys(self):
        """Test that dict with more keys wins."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1", "metadata": {"a": 1}}]},
                {
                    "contacts": [
                        {"name": "Jean", "resource_name": "c1", "metadata": {"a": 1, "b": 2}}
                    ]
                },
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert len(merged_contact["metadata"]) == 2

    def test_intelligent_merge_prefers_non_empty_string(self):
        """Test that non-empty string wins over empty string."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1", "email": "jean@test.com"}]},
                {"contacts": [{"name": "Jean", "resource_name": "c1", "email": ""}]},
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert merged_contact["email"] == "jean@test.com"

    def test_intelligent_merge_prefers_longer_string(self):
        """Test that longer string wins over shorter string."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1", "notes": "Short"}]},
                {
                    "contacts": [
                        {"name": "Jean", "resource_name": "c1", "notes": "Longer description here"}
                    ]
                },
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert merged_contact["notes"] == "Longer description here"

    def test_creates_synthetic_key_without_resource_name(self):
        """Test that synthetic key is created when resource_name is missing."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean"}]},  # No resource_name
            ]
        )

        assert result is not None
        assert result.total_count == 1

    def test_merges_none_values_correctly(self):
        """Test that None values are handled in merge."""
        result = _detect_and_normalize_contacts_result(
            [
                {"contacts": [{"name": "Jean", "resource_name": "c1", "phone": None}]},
                {"contacts": [{"name": "Jean", "resource_name": "c1", "phone": "+33612345678"}]},
            ]
        )

        assert result is not None
        merged_contact = result.contacts[0]
        assert merged_contact["phone"] == "+33612345678"


class TestDetectAndNormalizeContactsResultMetadata:
    """Tests for metadata preservation."""

    def test_preserves_data_source(self):
        """Test that data_source is preserved."""
        result = _detect_and_normalize_contacts_result(
            [
                {
                    "contacts": [{"name": "Jean", "resource_name": "c1"}],
                    "data_source": "cache",
                }
            ]
        )

        assert result is not None
        assert result.data_source == "cache"

    def test_preserves_timestamp(self):
        """Test that timestamp is preserved."""
        timestamp = "2025-01-15T10:30:00Z"
        result = _detect_and_normalize_contacts_result(
            [
                {
                    "contacts": [{"name": "Jean", "resource_name": "c1"}],
                    "timestamp": timestamp,
                }
            ]
        )

        assert result is not None
        assert result.timestamp == timestamp

    def test_preserves_cache_age_seconds(self):
        """Test that cache_age_seconds is preserved."""
        result = _detect_and_normalize_contacts_result(
            [
                {
                    "contacts": [{"name": "Jean", "resource_name": "c1"}],
                    "cache_age_seconds": 120,
                }
            ]
        )

        assert result is not None
        assert result.cache_age_seconds == 120

    def test_uses_default_data_source_when_not_provided(self):
        """Test that default data_source is 'api'."""
        result = _detect_and_normalize_contacts_result(
            [{"contacts": [{"name": "Jean", "resource_name": "c1"}]}]
        )

        assert result is not None
        assert result.data_source == "api"

    def test_generates_timestamp_when_not_provided(self):
        """Test that timestamp is generated when not provided."""
        result = _detect_and_normalize_contacts_result(
            [{"contacts": [{"name": "Jean", "resource_name": "c1"}]}]
        )

        assert result is not None
        assert result.timestamp is not None
        # Should be a valid ISO timestamp
        datetime.fromisoformat(result.timestamp.replace("Z", "+00:00"))


class TestDetectAndNormalizeContactsResultDataRegistry:
    """Tests for data registry fallback.

    Note: The data_registry fallback only activates when:
    1. step_results is NOT empty (otherwise function returns None early)
    2. step_results don't contain structured contacts data
    """

    def test_returns_none_when_step_results_empty(self):
        """Test that None is returned when step_results is empty, even with data_registry."""
        # This tests the early return behavior - data_registry is NOT checked when step_results is empty
        data_registry = {
            "item_1": {
                "type": "CONTACT",
                "payload": {"name": "Jean", "resource_name": "c1"},
            },
        }

        result = _detect_and_normalize_contacts_result([], data_registry)

        # Function returns None early when step_results is empty
        assert result is None

    def test_extracts_contacts_from_data_registry(self):
        """Test extraction from data_registry when step_results has no contacts."""
        # Step results with non-contact data (simulating summary_for_llm only scenario)
        step_results = [{"summary_for_llm": "Contact found"}]
        data_registry = {
            "item_1": {
                "type": "CONTACT",
                "payload": {"name": "Jean", "resource_name": "c1"},
            },
            "item_2": {
                "type": "CONTACT",
                "payload": {"name": "Marie", "resource_name": "c2"},
            },
        }

        result = _detect_and_normalize_contacts_result(step_results, data_registry)

        assert result is not None
        assert result.total_count == 2
        assert result.data_source == "data_registry"

    def test_ignores_non_contact_registry_items(self):
        """Test that non-CONTACT registry items are ignored."""
        step_results = [{"summary_for_llm": "Result summary"}]
        data_registry = {
            "item_1": {
                "type": "CONTACT",
                "payload": {"name": "Jean", "resource_name": "c1"},
            },
            "item_2": {
                "type": "EMAIL",
                "payload": {"subject": "Test"},
            },
        }

        result = _detect_and_normalize_contacts_result(step_results, data_registry)

        assert result is not None
        assert result.total_count == 1

    def test_uses_item_id_when_no_resource_name_in_registry(self):
        """Test that item_id is used as key when no resource_name in payload."""
        step_results = [{"summary_for_llm": "Contact summary"}]
        data_registry = {
            "item_1": {
                "type": "CONTACT",
                "payload": {"name": "Jean"},  # No resource_name
            },
        }

        result = _detect_and_normalize_contacts_result(step_results, data_registry)

        assert result is not None
        assert result.total_count == 1

    def test_step_results_take_precedence_over_registry(self):
        """Test that step_results are used when they contain contacts."""
        data_registry = {
            "item_1": {
                "type": "CONTACT",
                "payload": {"name": "Registry Jean", "resource_name": "c1"},
            },
        }

        result = _detect_and_normalize_contacts_result(
            [{"contacts": [{"name": "Step Jean", "resource_name": "c2"}]}],
            data_registry,
        )

        assert result is not None
        # Should use step_results data, not registry
        assert result.data_source == "api"  # Not "data_registry"


# ============================================================================
# Tests for _detect_and_normalize_emails_result
# ============================================================================


class TestDetectAndNormalizeEmailsResultBasic:
    """Tests for basic email detection and normalization."""

    def test_returns_none_for_empty_step_results(self):
        """Test that None is returned for empty inputs."""
        result = _detect_and_normalize_emails_result([])
        assert result is None

    def test_returns_none_for_no_emails_in_results(self):
        """Test that None is returned when no emails key exists."""
        result = _detect_and_normalize_emails_result(
            [
                {"contacts": [{"name": "Jean"}]},
            ]
        )
        assert result is None

    def test_detects_direct_email_structure(self):
        """Test detection of direct email structure."""
        result = _detect_and_normalize_emails_result(
            [{"emails": [{"id": "msg1", "subject": "Test"}], "total": 1}]
        )

        assert result is not None
        assert isinstance(result, EmailsResultData)
        assert result.total == 1
        assert len(result.emails) == 1

    def test_detects_wrapped_email_structure(self):
        """Test detection of wrapped email structure (in 'data' key)."""
        result = _detect_and_normalize_emails_result(
            [
                {
                    "success": True,
                    "data": {
                        "emails": [{"id": "msg1", "subject": "Test"}],
                        "total": 1,
                    },
                }
            ]
        )

        assert result is not None
        assert result.total == 1

    def test_aggregates_emails_from_multiple_steps(self):
        """Test aggregation from multiple step results."""
        result = _detect_and_normalize_emails_result(
            [
                {"emails": [{"id": "msg1", "subject": "Test 1"}]},
                {"emails": [{"id": "msg2", "subject": "Test 2"}]},
            ]
        )

        assert result is not None
        assert result.total == 2


class TestDetectAndNormalizeEmailsResultDeduplication:
    """Tests for email deduplication by message_id."""

    def test_deduplicates_by_id(self):
        """Test deduplication by 'id' field."""
        result = _detect_and_normalize_emails_result(
            [
                {"emails": [{"id": "msg1", "subject": "Version 1"}]},
                {"emails": [{"id": "msg1", "subject": "Version 2"}]},
            ]
        )

        assert result is not None
        assert result.total == 1

    def test_deduplicates_by_message_id(self):
        """Test deduplication by 'message_id' field."""
        result = _detect_and_normalize_emails_result(
            [
                {"emails": [{"message_id": "msg1", "subject": "Version 1"}]},
                {"emails": [{"message_id": "msg1", "subject": "Version 2"}]},
            ]
        )

        assert result is not None
        assert result.total == 1

    def test_keeps_emails_without_id(self):
        """Test that emails without ID are kept."""
        result = _detect_and_normalize_emails_result(
            [
                {"emails": [{"subject": "No ID 1"}, {"subject": "No ID 2"}]},
            ]
        )

        assert result is not None
        assert result.total == 2


class TestDetectAndNormalizeEmailsResultDataRegistry:
    """Tests for email data registry fallback."""

    def test_extracts_emails_from_data_registry(self):
        """Test extraction from data_registry when step_results are empty."""
        data_registry = {
            "item_1": {
                "type": "EMAIL",
                "payload": {"id": "msg1", "subject": "Test"},
            },
        }

        result = _detect_and_normalize_emails_result([], data_registry)

        assert result is not None
        assert result.total == 1
        assert result.data_source == "data_registry"

    def test_ignores_non_email_registry_items(self):
        """Test that non-EMAIL registry items are ignored."""
        data_registry = {
            "item_1": {
                "type": "EMAIL",
                "payload": {"id": "msg1"},
            },
            "item_2": {
                "type": "CONTACT",
                "payload": {"name": "Jean"},
            },
        }

        result = _detect_and_normalize_emails_result([], data_registry)

        assert result is not None
        assert result.total == 1


# ============================================================================
# Tests for _detect_and_normalize_places_result
# ============================================================================


class TestDetectAndNormalizePlacesResultBasic:
    """Tests for basic places detection and normalization."""

    def test_returns_none_for_empty_step_results(self):
        """Test that None is returned for empty inputs."""
        result = _detect_and_normalize_places_result([])
        assert result is None

    def test_returns_none_for_no_places_in_results(self):
        """Test that None is returned when no places key exists."""
        result = _detect_and_normalize_places_result(
            [
                {"contacts": [{"name": "Jean"}]},
            ]
        )
        assert result is None

    def test_detects_direct_places_structure(self):
        """Test detection of direct places structure."""
        result = _detect_and_normalize_places_result(
            [{"places": [{"id": "p1", "name": "Restaurant"}], "total": 1}]
        )

        assert result is not None
        assert isinstance(result, PlacesResultData)
        assert result.total_count == 1
        assert len(result.places) == 1

    def test_detects_wrapped_places_structure(self):
        """Test detection of wrapped places structure (in 'data' key)."""
        result = _detect_and_normalize_places_result(
            [
                {
                    "success": True,
                    "data": {
                        "places": [{"id": "p1", "name": "Restaurant"}],
                        "total": 1,
                    },
                }
            ]
        )

        assert result is not None
        assert result.total_count == 1

    def test_aggregates_places_from_multiple_steps(self):
        """Test aggregation from multiple step results."""
        result = _detect_and_normalize_places_result(
            [
                {"places": [{"id": "p1", "name": "Place 1"}]},
                {"places": [{"id": "p2", "name": "Place 2"}]},
            ]
        )

        assert result is not None
        assert result.total_count == 2


class TestDetectAndNormalizePlacesResultDeduplication:
    """Tests for places deduplication by place_id."""

    def test_deduplicates_by_id(self):
        """Test deduplication by 'id' field."""
        result = _detect_and_normalize_places_result(
            [
                {"places": [{"id": "p1", "name": "Version 1"}]},
                {"places": [{"id": "p1", "name": "Version 2"}]},
            ]
        )

        assert result is not None
        assert result.total_count == 1

    def test_deduplicates_by_place_id(self):
        """Test deduplication by 'place_id' field."""
        result = _detect_and_normalize_places_result(
            [
                {"places": [{"place_id": "p1", "name": "Version 1"}]},
                {"places": [{"place_id": "p1", "name": "Version 2"}]},
            ]
        )

        assert result is not None
        assert result.total_count == 1


class TestDetectAndNormalizePlacesResultMetadata:
    """Tests for places metadata preservation."""

    def test_preserves_location(self):
        """Test that location is preserved."""
        result = _detect_and_normalize_places_result(
            [
                {
                    "places": [{"id": "p1", "name": "Restaurant"}],
                    "location": "Paris, France",
                }
            ]
        )

        assert result is not None
        assert result.location == "Paris, France"


class TestDetectAndNormalizePlacesResultDataRegistry:
    """Tests for places data registry fallback."""

    def test_extracts_places_from_data_registry(self):
        """Test extraction from data_registry when step_results are empty."""
        data_registry = {
            "item_1": {
                "type": "PLACE",
                "payload": {"id": "p1", "name": "Restaurant"},
            },
        }

        result = _detect_and_normalize_places_result([], data_registry)

        assert result is not None
        assert result.total_count == 1
        assert result.data_source == "data_registry"


# ============================================================================
# Tests for map_execution_result_to_agent_result
# ============================================================================


class TestMapExecutionResultBasic:
    """Tests for basic mapping functionality."""

    def test_maps_empty_execution_result(self):
        """Test mapping of empty execution result."""
        execution_result = ExecutionResult(
            success=True,
            step_results=[],
            total_steps=0,
            completed_steps=0,
            total_execution_time_ms=100,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        assert result is not None
        assert "1:plan_executor" in result
        agent_result = result["1:plan_executor"]
        assert agent_result["status"] == "success"

    def test_maps_failed_execution_result(self):
        """Test mapping of failed execution result."""
        execution_result = ExecutionResult(
            success=False,
            step_results=[],
            total_steps=1,
            completed_steps=0,
            error="Tool execution failed",
            total_execution_time_ms=50,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        assert result is not None
        agent_result = result["1:plan_executor"]
        assert agent_result["status"] == "failed"
        assert agent_result["error"] == "Tool execution failed"

    def test_generates_correct_composite_key(self):
        """Test that composite key uses colon format."""
        execution_result = ExecutionResult(
            success=True,
            step_results=[],
            total_steps=0,
            completed_steps=0,
            total_execution_time_ms=100,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=5,
        )

        # Key should use colon format: {turn_id}:plan_executor
        assert "5:plan_executor" in result


class TestMapExecutionResultContacts:
    """Tests for contacts normalization in mapping."""

    def test_normalizes_contacts_result(self):
        """Test that contacts are normalized to ContactsResultData."""
        step_result = StepResult(
            step_index=0,
            tool_name="search_contacts",
            args={"query": "Jean"},
            result={
                "contacts": [{"name": "Jean", "resource_name": "c1"}],
                "total": 1,
            },
            success=True,
        )

        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=200,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        assert data["result_type"] == "contacts"
        assert data["total_count"] == 1


class TestMapExecutionResultEmails:
    """Tests for emails normalization in mapping."""

    def test_normalizes_emails_result(self):
        """Test that emails are normalized to EmailsResultData."""
        step_result = StepResult(
            step_index=0,
            tool_name="list_emails",
            args={"query": "test"},
            result={
                "emails": [{"id": "msg1", "subject": "Test"}],
                "total": 1,
            },
            success=True,
        )

        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=150,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        assert data["result_type"] == "emails"
        assert data["total"] == 1


class TestMapExecutionResultPlaces:
    """Tests for places normalization in mapping."""

    def test_normalizes_places_result(self):
        """Test that places are normalized to PlacesResultData."""
        step_result = StepResult(
            step_index=0,
            tool_name="search_places",
            args={"query": "restaurant"},
            result={
                "places": [{"id": "p1", "name": "Restaurant"}],
                "total": 1,
            },
            success=True,
        )

        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=180,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        assert data["result_type"] == "places"
        assert data["total_count"] == 1


class TestMapExecutionResultMultiDomain:
    """Tests for multi-domain result handling."""

    def test_creates_multi_domain_result(self):
        """Test that multi-domain results use MultiDomainResultData."""
        step_results = [
            StepResult(
                step_index=0,
                tool_name="search_contacts",
                args={},
                result={"contacts": [{"name": "Jean", "resource_name": "c1"}]},
                success=True,
            ),
            StepResult(
                step_index=1,
                tool_name="list_emails",
                args={},
                result={"emails": [{"id": "msg1", "subject": "Test"}]},
                success=True,
            ),
        ]

        execution_result = ExecutionResult(
            success=True,
            step_results=step_results,
            total_steps=2,
            completed_steps=2,
            total_execution_time_ms=300,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        assert data["result_type"] == "multi_domain"
        assert data["contacts_total"] == 1
        assert data["emails_total"] == 1


class TestMapExecutionResultSkipsConditional:
    """Tests for conditional step handling."""

    def test_skips_conditional_steps(self):
        """Test that conditional steps are skipped in aggregation."""
        step_results = [
            StepResult(
                step_index=0,
                tool_name="conditional",
                args={},
                result={"condition_result": True},  # Conditional step
                success=True,
            ),
            StepResult(
                step_index=1,
                tool_name="search_contacts",
                args={},
                result={"contacts": [{"name": "Jean", "resource_name": "c1"}]},
                success=True,
            ),
        ]

        execution_result = ExecutionResult(
            success=True,
            step_results=step_results,
            total_steps=2,
            completed_steps=2,
            total_execution_time_ms=200,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        # Should only have contacts, not conditional result
        assert data["result_type"] == "contacts"


class TestMapExecutionResultTokens:
    """Tests for token aggregation."""

    def test_aggregates_tokens_from_steps(self):
        """Test that tokens are aggregated from step results."""
        step_results = [
            StepResult(
                step_index=0,
                tool_name="tool1",
                args={},
                result={"tokens_in": 100, "tokens_out": 50},
                success=True,
            ),
            StepResult(
                step_index=1,
                tool_name="tool2",
                args={},
                result={"tokens_in": 150, "tokens_out": 75},
                success=True,
            ),
        ]

        execution_result = ExecutionResult(
            success=True,
            step_results=step_results,
            total_steps=2,
            completed_steps=2,
            total_execution_time_ms=200,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        assert agent_result["tokens_in"] == 250  # 100 + 150
        assert agent_result["tokens_out"] == 125  # 50 + 75


class TestMapExecutionResultDataRegistry:
    """Tests for data registry handling in mapping."""

    def test_passes_data_registry_to_normalizers(self):
        """Test that data_registry is used when step_results have no structured data."""
        # Step result with non-contact data (simulating registry mode)
        step_result = StepResult(
            step_index=0,
            tool_name="get_contact",
            args={},
            result={"summary_for_llm": "Found contact Jean"},
            success=True,
        )

        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=100,
        )

        data_registry = {
            "item_1": {
                "type": "CONTACT",
                "payload": {"name": "Jean", "resource_name": "c1"},
            },
        }

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
            data_registry=data_registry,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        assert data["result_type"] == "contacts"
        assert data["data_source"] == "data_registry"

    def test_includes_registry_updates_in_result(self):
        """Test that registry_updates are included in agent result."""
        execution_result = ExecutionResult(
            success=True,
            step_results=[],
            total_steps=0,
            completed_steps=0,
            total_execution_time_ms=100,
        )

        data_registry = {
            "item_1": {"type": "CONTACT", "payload": {}},
        }

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
            data_registry=data_registry,
        )

        agent_result = result["1:plan_executor"]
        assert agent_result["registry_updates"] is not None
        assert "item_1" in agent_result["registry_updates"]


class TestMapExecutionResultFallback:
    """Tests for generic fallback format."""

    def test_uses_generic_format_when_no_domain_detected(self):
        """Test that generic format is used when no domain is detected."""
        step_result = StepResult(
            step_index=0,
            tool_name="custom_tool",
            args={},
            result={"custom_data": "value"},
            success=True,
        )

        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=100,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        # Should be a dict with generic fields
        assert "plan_id" in data
        assert "step_results" in data or "aggregated_results" in data

    def test_includes_execution_metadata_in_fallback(self):
        """Test that execution metadata is included in fallback format."""
        step_result = StepResult(
            step_index=0,
            tool_name="custom_tool",
            args={},
            result={"custom": "data"},
            success=True,
        )

        execution_result = ExecutionResult(
            success=True,
            step_results=[step_result],
            total_steps=1,
            completed_steps=1,
            total_execution_time_ms=250,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        data = agent_result["data"]
        assert data.get("plan_id") == "plan123"
        assert data.get("completed_steps") == 1
        assert data.get("total_steps") == 1
        assert data.get("execution_time_ms") == 250


class TestMapExecutionResultAgentResultFields:
    """Tests for AgentResult fields."""

    def test_sets_agent_name(self):
        """Test that agent_name is set to 'plan_executor'."""
        execution_result = ExecutionResult(
            success=True,
            step_results=[],
            total_steps=0,
            completed_steps=0,
            total_execution_time_ms=100,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        assert agent_result["agent_name"] == "plan_executor"

    def test_sets_duration_ms(self):
        """Test that duration_ms is set from execution time."""
        execution_result = ExecutionResult(
            success=True,
            step_results=[],
            total_steps=0,
            completed_steps=0,
            total_execution_time_ms=500,
        )

        result = map_execution_result_to_agent_result(
            execution_result=execution_result,
            plan_id="plan123",
            turn_id=1,
        )

        agent_result = result["1:plan_executor"]
        assert agent_result["duration_ms"] == 500
