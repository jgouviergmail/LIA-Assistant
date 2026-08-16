"""Tests for the HITL resumption helpers consumed by the production resume path.

Covers the two pure helpers kept in resumption_strategies.py:
- _build_plan_modifications_from_classifier (Issue #60 bridge)
- build_edit_reformulated_intent (localized EDIT reformulation)

The ConversationalHitlResumption strategy class this file previously exercised
was deleted with its Protocol (ADR-222): it had no production caller — resumes
stream through StreamingService — so its tests kept dead code green.
"""

from src.domains.agents.services.hitl.resumption_strategies import (
    _build_plan_modifications_from_classifier,
    build_edit_reformulated_intent,
)

# ============================================================================
# _build_plan_modifications_from_classifier Tests (Issue #60 Fix)
# ============================================================================


class TestBuildPlanModificationsFromClassifier:
    """
    Test suite for _build_plan_modifications_from_classifier().

    Issue #60 Fix: This function bridges classifier output (edited_params)
    to approval_gate_node expectations (modifications).
    """

    def test_empty_edited_params_returns_empty_list(self):
        """Test that empty edited_params returns empty list."""
        result = _build_plan_modifications_from_classifier(
            edited_params={},
            pending_action_requests=[],
            run_id="run_123",
        )
        assert result == []

    def test_no_plan_summary_returns_empty_list(self):
        """Test that missing plan_summary returns empty list."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"max_results": 4},
            pending_action_requests=[{"type": "tool_approval"}],  # No plan_approval
            run_id="run_123",
        )
        assert result == []

    def test_no_steps_in_plan_summary_returns_empty_list(self):
        """Test that plan_summary without steps returns empty list."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"max_results": 4},
            pending_action_requests=[
                {
                    "type": "plan_approval",
                    "plan_summary": {},  # No steps
                }
            ],
            run_id="run_123",
        )
        assert result == []

    def test_single_param_matches_single_step(self):
        """Test matching a single edited param to a step."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"max_results": 4},
            pending_action_requests=[
                {
                    "type": "plan_approval",
                    "plan_summary": {
                        "steps": [
                            {
                                "step_id": "step_1",
                                "parameters": {"max_results": 20},
                            }
                        ]
                    },
                }
            ],
            run_id="run_123",
        )

        assert len(result) == 1
        assert result[0]["modification_type"] == "edit_params"
        assert result[0]["step_id"] == "step_1"
        assert result[0]["new_parameters"] == {"max_results": 4}

    def test_multiple_params_match_same_step(self):
        """Test matching multiple edited params to the same step."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"max_results": 4, "query": "nouveau"},
            pending_action_requests=[
                {
                    "type": "plan_approval",
                    "plan_summary": {
                        "steps": [
                            {
                                "step_id": "step_1",
                                "parameters": {"max_results": 20, "query": "ancien"},
                            }
                        ]
                    },
                }
            ],
            run_id="run_123",
        )

        assert len(result) == 1
        assert result[0]["step_id"] == "step_1"
        assert result[0]["new_parameters"] == {"max_results": 4, "query": "nouveau"}

    def test_params_match_different_steps(self):
        """Test matching params to different steps based on parameter keys."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"max_results": 4, "recipient_email": "new@example.com"},
            pending_action_requests=[
                {
                    "type": "plan_approval",
                    "plan_summary": {
                        "steps": [
                            {
                                "step_id": "step_1",
                                "parameters": {"max_results": 20, "query": "contacts"},
                            },
                            {
                                "step_id": "step_2",
                                "parameters": {
                                    "recipient_email": "old@example.com",
                                    "subject": "Hello",
                                },
                            },
                        ]
                    },
                }
            ],
            run_id="run_123",
        )

        assert len(result) == 2

        # Find modifications by step_id
        step1_mod = next(m for m in result if m["step_id"] == "step_1")
        step2_mod = next(m for m in result if m["step_id"] == "step_2")

        assert step1_mod["new_parameters"] == {"max_results": 4}
        assert step2_mod["new_parameters"] == {"recipient_email": "new@example.com"}

    def test_unmatched_params_applied_to_first_step_with_params(self):
        """Test that unmatched params are applied to first step with parameters."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"count": 5},  # 'count' doesn't exist in step params
            pending_action_requests=[
                {
                    "type": "plan_approval",
                    "plan_summary": {
                        "steps": [
                            {
                                "step_id": "step_1",
                                "parameters": {"max_results": 20},  # No 'count' key
                            }
                        ]
                    },
                }
            ],
            run_id="run_123",
        )

        # Unmatched params should be applied to first step with parameters
        assert len(result) == 1
        assert result[0]["step_id"] == "step_1"
        assert result[0]["new_parameters"] == {"count": 5}

    def test_mixed_matched_and_unmatched_params(self):
        """Test handling of both matched and unmatched params."""
        result = _build_plan_modifications_from_classifier(
            edited_params={"max_results": 4, "unknown_param": "value"},
            pending_action_requests=[
                {
                    "type": "plan_approval",
                    "plan_summary": {
                        "steps": [
                            {
                                "step_id": "step_1",
                                "parameters": {"max_results": 20},
                            }
                        ]
                    },
                }
            ],
            run_id="run_123",
        )

        # Should have 2 modifications: one matched, one unmatched fallback
        assert len(result) == 2

        # Find matched and unmatched modifications
        matched_mods = [m for m in result if "max_results" in m["new_parameters"]]
        unmatched_mods = [m for m in result if "unknown_param" in m["new_parameters"]]

        assert len(matched_mods) == 1
        assert matched_mods[0]["new_parameters"]["max_results"] == 4

        assert len(unmatched_mods) == 1
        assert unmatched_mods[0]["new_parameters"]["unknown_param"] == "value"


# ============================================================================
# build_edit_reformulated_intent Tests
# ============================================================================


class TestBuildEditReformulatedIntent:
    """
    Tests for build_edit_reformulated_intent helper.

    This helper builds a reformulated user intent from EDIT modifications,
    used to replace the original HumanMessage in LangGraph state during HITL
    EDIT resumption. This avoids LLM confusion between original query and
    modified results.

    Issue #62 Fix: Ensures response_node sees consistent message + results.
    """

    def test_returns_none_for_empty_modifications(self):
        """Test that empty modifications list returns None."""
        result = build_edit_reformulated_intent([])
        assert result is None

    def test_returns_none_for_non_edit_params(self):
        """Test that non-edit_params modifications return None."""
        result = build_edit_reformulated_intent(
            [
                {"modification_type": "add_step", "step_id": "step_1"},
                {"modification_type": "remove_step", "step_id": "step_2"},
            ]
        )
        assert result is None

    def test_contacts_query_reformulation(self):
        """Test contacts domain: query → 'recherche {query}'."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"query": "jean"},
                }
            ]
        )
        assert result == "recherche jean"

    def test_emails_search_query_reformulation(self):
        """Test emails domain: search_query → 'recherche emails {search_query}'."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"search_query": "factures"},
                }
            ]
        )
        assert result == "recherche emails factures"

    def test_emails_recipient_to_reformulation(self):
        """Test emails domain: to → 'envoie à {to}'."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"to": "jean@example.com"},
                }
            ]
        )
        assert result == "envoie à jean@example.com"

    def test_emails_recipient_recipient_reformulation(self):
        """Test emails domain: recipient → 'envoie à {recipient}'."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"recipient": "marie@example.com"},
                }
            ]
        )
        assert result == "envoie à marie@example.com"

    def test_calendar_event_query_reformulation(self):
        """Test calendar domain: event_query → 'recherche événements {event_query}'."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"event_query": "réunion"},
                }
            ]
        )
        assert result == "recherche événements réunion"

    def test_generic_fallback_with_string_params(self):
        """Test generic fallback for unknown string parameters."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"custom_param": "value", "another": "test"},
                }
            ]
        )
        # Generic format: "execute with: param=value, ..."
        assert result is not None
        assert "exécute avec:" in result
        assert "custom_param=value" in result
        assert "another=test" in result

    def test_generic_fallback_with_numeric_params(self):
        """Test generic fallback for numeric parameters."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"max_results": 10, "page": 2},
                }
            ]
        )
        assert result is not None
        assert "exécute avec:" in result
        assert "max_results=10" in result
        assert "page=2" in result

    def test_generic_fallback_with_boolean_params(self):
        """Test generic fallback for boolean parameters."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"include_attachments": True},
                }
            ]
        )
        assert result is not None
        assert "include_attachments=True" in result

    def test_empty_new_parameters_returns_none(self):
        """Test that empty new_parameters dict returns None."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {},
                }
            ]
        )
        assert result is None

    def test_first_edit_params_wins(self):
        """Test that only the first edit_params modification is used."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"query": "first"},
                },
                {
                    "modification_type": "edit_params",
                    "step_id": "step_2",
                    "new_parameters": {"query": "second"},
                },
            ]
        )
        # Should use first match
        assert result == "recherche first"

    def test_priority_query_over_generic(self):
        """Test that 'query' param has priority over generic params."""
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"query": "jean", "max_results": 10},
                }
            ]
        )
        # query has priority - should return contacts format
        assert result == "recherche jean"

    def test_skips_long_string_values(self):
        """Test that very long string values are excluded from generic fallback."""
        long_value = "x" * 100  # 100 chars, > 50 limit
        result = build_edit_reformulated_intent(
            [
                {
                    "modification_type": "edit_params",
                    "step_id": "step_1",
                    "new_parameters": {"long_param": long_value, "short_param": "ok"},
                }
            ]
        )
        assert result is not None
        assert "long_param" not in result  # Excluded due to length
        assert "short_param=ok" in result
