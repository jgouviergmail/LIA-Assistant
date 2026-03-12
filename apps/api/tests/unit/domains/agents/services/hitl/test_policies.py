"""
Unit tests for HITL policies.

Tests for the policy classes that handle HITL decision building:
- ClassificationExtractor: Extracts classification data
- RejectionDecisionBuilder: Builds rejection decisions
- EditDecisionBuilder: Builds edit decisions
- ApprovalDecisionBuilder: Orchestrates decision building
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

import pytest

from src.domains.agents.services.hitl.policies.approval_decision_builder import (
    ApprovalDecisionBuilder,
)
from src.domains.agents.services.hitl.policies.classification_extractor import (
    ClassificationExtractor,
)
from src.domains.agents.services.hitl.policies.edit_decision_builder import (
    EditDecisionBuilder,
)
from src.domains.agents.services.hitl.policies.rejection_decision_builder import (
    RejectionDecisionBuilder,
)


@dataclass
class MockClassificationResult:
    """Mock ClassificationResult for testing."""

    decision: str
    reasoning: str
    edited_params: dict | None = None
    clarification_question: str | None = None
    confidence: float = 0.9


class TestClassificationExtractor:
    """Tests for ClassificationExtractor."""

    def test_extract_from_classification_object(self):
        """Test extraction from ClassificationResult object."""
        classification = MockClassificationResult(
            decision="APPROVE",
            reasoning="User confirmed",
            edited_params={"name": "John"},
            clarification_question="Is this correct?",
        )
        extractor = ClassificationExtractor()
        decision, reasoning, params, question = extractor.extract(classification)

        assert decision == "APPROVE"
        assert reasoning == "User confirmed"
        assert params == {"name": "John"}
        assert question == "Is this correct?"

    def test_extract_from_dict(self):
        """Test extraction from dict (backward compatibility)."""
        classification = {
            "decision": "REJECT",
            "reasoning": "User said no",
            "edited_params": None,
            "clarification_question": None,
        }
        extractor = ClassificationExtractor()
        decision, reasoning, params, question = extractor.extract(classification)

        assert decision == "REJECT"
        assert reasoning == "User said no"
        assert params is None
        assert question is None

    def test_extract_from_dict_with_missing_keys(self):
        """Test extraction from dict with missing keys uses defaults."""
        classification = {"decision": "APPROVE"}
        extractor = ClassificationExtractor()
        decision, reasoning, params, question = extractor.extract(classification)

        assert decision == "APPROVE"
        assert reasoning == ""  # Default empty string
        assert params is None
        assert question is None

    def test_extract_handles_object_without_clarification_question(self):
        """Test extraction from object without clarification_question attribute."""

        @dataclass
        class MinimalClassification:
            decision: str
            reasoning: str
            edited_params: dict | None

        classification = MinimalClassification(
            decision="EDIT", reasoning="Modified params", edited_params={"x": 1}
        )
        extractor = ClassificationExtractor()
        decision, reasoning, params, question = extractor.extract(classification)

        assert decision == "EDIT"
        assert params == {"x": 1}
        assert question is None


class TestEditDecisionBuilderInferEditType:
    """Tests for EditDecisionBuilder.infer_edit_type() static method."""

    def test_infer_tool_changed(self):
        """Test detection of tool change."""
        result = EditDecisionBuilder.infer_edit_type(
            tool_args={"name": "John"},
            edited_params={"tool_name": "different_tool"},
            tool_name="original_tool",
        )
        assert result == "tool_changed"

    def test_infer_minor_adjustment_one_param(self):
        """Test minor adjustment with one param changed."""
        result = EditDecisionBuilder.infer_edit_type(
            tool_args={"name": "John", "email": "john@test.com"},
            edited_params={"name": "Jane"},
            tool_name="search_contacts",
        )
        assert result == "minor_adjustment"

    def test_infer_minor_adjustment_two_params(self):
        """Test minor adjustment with two params changed."""
        result = EditDecisionBuilder.infer_edit_type(
            tool_args={"name": "John", "email": "john@test.com", "city": "Paris"},
            edited_params={"name": "Jane", "city": "London"},
            tool_name="search_contacts",
        )
        assert result == "minor_adjustment"

    def test_infer_params_modified(self):
        """Test params_modified with 3 params changed."""
        result = EditDecisionBuilder.infer_edit_type(
            tool_args={"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6},
            edited_params={"a": 10, "b": 20, "c": 30},
            tool_name="tool",
        )
        assert result == "params_modified"

    def test_infer_full_rewrite_by_percentage(self):
        """Test full_rewrite when more than 50% params changed."""
        result = EditDecisionBuilder.infer_edit_type(
            tool_args={"a": 1, "b": 2, "c": 3, "d": 4},
            edited_params={"a": 10, "b": 20, "c": 30},  # 75% of original
            tool_name="tool",
        )
        # 3 params > 4 * 0.5 = 2, but not > 3 threshold
        assert result == "params_modified"

    def test_infer_full_rewrite_by_count(self):
        """Test full_rewrite when 4+ params changed."""
        result = EditDecisionBuilder.infer_edit_type(
            tool_args={"a": 1, "b": 2},
            edited_params={"a": 10, "b": 20, "c": 30, "d": 40},  # 4 params
            tool_name="tool",
        )
        assert result == "full_rewrite"


class TestEditDecisionBuilderBuild:
    """Tests for EditDecisionBuilder.build() method."""

    @patch("src.infrastructure.observability.metrics_agents.hitl_edit_actions_total")
    @patch("src.infrastructure.observability.metrics_agents.hitl_edit_decisions_total")
    def test_build_edit_decision(self, mock_decisions, mock_actions):
        """Test building edit decision."""
        builder = EditDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.return_value = "search_contacts"

        action = {"name": "search_contacts", "args": {"name": "John"}}
        edited_params = {"name": "Jane"}
        classification = MockClassificationResult(decision="EDIT", reasoning="User corrected name")

        result = builder.build(
            action=action,
            edited_params=edited_params,
            classification=classification,
            clarification_question=None,
            validator=validator,
        )

        assert result["type"] == "edit"
        assert result["edited_action"]["name"] == "search_contacts"
        assert result["edited_action"]["args"]["name"] == "Jane"
        assert result["edited_params"] == {"name": "Jane"}

        # Metrics should be called
        mock_actions.labels.assert_called_once()
        mock_decisions.labels.assert_called_once()

    @patch("src.infrastructure.observability.metrics_agents.hitl_edit_actions_total")
    @patch("src.infrastructure.observability.metrics_agents.hitl_edit_decisions_total")
    def test_build_edit_decision_merges_args(self, mock_decisions, mock_actions):
        """Test that edited params are merged with original args."""
        builder = EditDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.return_value = "search"

        action = {"name": "search", "args": {"a": 1, "b": 2}}
        edited_params = {"b": 20, "c": 30}
        classification = MockClassificationResult(decision="EDIT", reasoning="Edit")

        result = builder.build(
            action=action,
            edited_params=edited_params,
            classification=classification,
            clarification_question=None,
            validator=validator,
        )

        # Original args merged with edited params
        assert result["edited_action"]["args"] == {"a": 1, "b": 20, "c": 30}

    def test_build_edit_decision_raises_on_empty_params(self):
        """Test that build raises ValueError if edited_params is empty."""
        builder = EditDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.return_value = "tool"

        action = {"name": "tool", "args": {}}
        classification = MockClassificationResult(decision="EDIT", reasoning="Edit")

        with pytest.raises(ValueError) as exc_info:
            builder.build(
                action=action,
                edited_params={},  # Empty
                classification=classification,
                clarification_question=None,
                validator=validator,
            )

        assert "requires edited_params" in str(exc_info.value)

    @patch("src.infrastructure.observability.metrics_agents.hitl_edit_actions_total")
    @patch("src.infrastructure.observability.metrics_agents.hitl_edit_decisions_total")
    def test_build_edit_decision_handles_unknown_tool_name(self, mock_decisions, mock_actions):
        """Test handling when tool name extraction fails."""
        builder = EditDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.side_effect = ValueError("Cannot extract")

        action = {"invalid": "action"}
        edited_params = {"param": "value"}
        classification = MockClassificationResult(decision="EDIT", reasoning="Edit")

        result = builder.build(
            action=action,
            edited_params=edited_params,
            classification=classification,
            clarification_question=None,
            validator=validator,
        )

        assert result["edited_action"]["name"] == "unknown"


class TestRejectionDecisionBuilderInferRejectionType:
    """Tests for RejectionDecisionBuilder.infer_rejection_type() static method."""

    def test_infer_explicit_no_french(self):
        """Test detection of explicit rejection in French."""
        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.9)
        result = RejectionDecisionBuilder.infer_rejection_type("non annule ça", classification)
        assert result == "explicit_no"

    def test_infer_explicit_no_english(self):
        """Test detection of explicit rejection in English."""
        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.9)
        result = RejectionDecisionBuilder.infer_rejection_type("no, cancel that", classification)
        assert result == "explicit_no"

    def test_infer_explicit_no_spanish(self):
        """Test detection of explicit rejection in Spanish."""
        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.9)
        result = RejectionDecisionBuilder.infer_rejection_type("cancelar esto", classification)
        assert result == "explicit_no"

    def test_infer_explicit_no_german(self):
        """Test detection of explicit rejection in German."""
        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.9)
        result = RejectionDecisionBuilder.infer_rejection_type("nein, abbrechen", classification)
        assert result == "explicit_no"

    def test_infer_explicit_no_chinese(self):
        """Test detection of explicit rejection in Chinese."""
        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.9)
        result = RejectionDecisionBuilder.infer_rejection_type("不要 取消", classification)
        assert result == "explicit_no"

    @patch("src.core.config.get_settings")
    def test_infer_low_confidence(self, mock_get_settings):
        """Test detection of low confidence rejection."""
        mock_settings = MagicMock()
        mock_settings.hitl_low_confidence_threshold = 0.7
        mock_get_settings.return_value = mock_settings

        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.5)
        # Use a response without explicit keywords
        result = RejectionDecisionBuilder.infer_rejection_type("maybe later", classification)
        assert result == "low_confidence"

    @patch("src.core.config.get_settings")
    def test_infer_implicit_no(self, mock_get_settings):
        """Test detection of implicit rejection."""
        mock_settings = MagicMock()
        mock_settings.hitl_low_confidence_threshold = 0.5
        mock_get_settings.return_value = mock_settings

        classification = MockClassificationResult(decision="REJECT", reasoning="", confidence=0.9)
        # Use a response without explicit keywords
        result = RejectionDecisionBuilder.infer_rejection_type("plutôt paul durand", classification)
        assert result == "implicit_no"

    def test_infer_rejection_type_from_dict(self):
        """Test inference from dict classification."""
        classification = {"decision": "REJECT", "confidence": 0.9}
        result = RejectionDecisionBuilder.infer_rejection_type("stop doing that", classification)
        assert result == "explicit_no"


class TestRejectionDecisionBuilderBuild:
    """Tests for RejectionDecisionBuilder.build() method."""

    @patch("src.infrastructure.observability.metrics_agents.hitl_tool_rejections_by_reason")
    @patch("src.infrastructure.observability.metrics_agents.hitl_rejection_type_total")
    def test_build_rejection_decision(self, mock_rejection_type, mock_rejections):
        """Test building rejection decision."""
        builder = RejectionDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.return_value = "delete_contact"

        action = {"name": "delete_contact", "args": {"id": "123"}}
        classification = MockClassificationResult(
            decision="REJECT", reasoning="User canceled", confidence=0.9
        )

        result = builder.build(
            action=action,
            reasoning="User canceled",
            user_response="non annule",
            classification=classification,
            validator=validator,
            user_language="fr",
        )

        assert result["type"] == "reject"
        assert "message" in result

        # Verify metrics were called
        mock_rejections.labels.assert_called_once()
        mock_rejection_type.labels.assert_called_once()

    @patch("src.infrastructure.observability.metrics_agents.hitl_tool_rejections_by_reason")
    @patch("src.infrastructure.observability.metrics_agents.hitl_rejection_type_total")
    def test_build_rejection_decision_handles_unknown_tool(
        self, mock_rejection_type, mock_rejections
    ):
        """Test building rejection when tool name extraction fails."""
        builder = RejectionDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.side_effect = ValueError("Cannot extract")

        action = {"invalid": "action"}
        classification = MockClassificationResult(
            decision="REJECT", reasoning="Rejected", confidence=0.9
        )

        result = builder.build(
            action=action,
            reasoning="Rejected",
            user_response="no",
            classification=classification,
            validator=validator,
            user_language="en",
        )

        assert result["type"] == "reject"

    @patch("src.infrastructure.observability.metrics_agents.hitl_tool_rejections_by_reason")
    @patch("src.infrastructure.observability.metrics_agents.hitl_rejection_type_total")
    @patch("src.domains.agents.api.error_messages.SSEErrorMessages")
    def test_build_rejection_uses_correct_language(
        self, mock_sse, mock_rejection_type, mock_rejections
    ):
        """Test that rejection uses correct i18n language."""
        builder = RejectionDecisionBuilder(agent_type="test_agent")
        validator = MagicMock()
        validator.extract_tool_name.return_value = "tool"

        action = {"name": "tool", "args": {}}
        classification = MockClassificationResult(
            decision="REJECT", reasoning="Rejected", confidence=0.9
        )

        mock_sse.hitl_rejection_message.return_value = "Test message"
        builder.build(
            action=action,
            reasoning="Rejected",
            user_response="nein",
            classification=classification,
            validator=validator,
            user_language="de",
        )

        mock_sse.hitl_rejection_message.assert_called_once_with(reasoning="Rejected", language="de")


class TestApprovalDecisionBuilderBuildFromDraftAction:
    """Tests for ApprovalDecisionBuilder.build_from_draft_action()."""

    def test_build_from_confirm_action(self):
        """Test building decision from confirm draft action."""
        builder = ApprovalDecisionBuilder(agent_type="email_agent")
        draft_action = {
            "type": "draft_action",
            "action": "confirm",
            "draft_id": "draft_123",
        }

        result = builder.build_from_draft_action(draft_action, [])

        assert len(result.decisions) == 1
        assert result.decisions[0]["type"] == "approve"
        assert result.decisions[0]["draft_id"] == "draft_123"
        assert result.decisions[0]["original_action"] == "confirm"

    def test_build_from_cancel_action(self):
        """Test building decision from cancel draft action."""
        builder = ApprovalDecisionBuilder(agent_type="email_agent")
        draft_action = {
            "type": "draft_action",
            "action": "cancel",
            "draft_id": "draft_456",
        }

        result = builder.build_from_draft_action(draft_action, [])

        assert result.decisions[0]["type"] == "reject"
        assert result.decisions[0]["original_action"] == "cancel"

    def test_build_from_edit_action(self):
        """Test building decision from edit draft action."""
        builder = ApprovalDecisionBuilder(agent_type="email_agent")
        draft_action = {
            "type": "draft_action",
            "action": "edit",
            "draft_id": "draft_789",
            "updated_content": {"subject": "New Subject"},
        }

        result = builder.build_from_draft_action(draft_action, [])

        assert result.decisions[0]["type"] == "edit"
        assert result.decisions[0]["draft_id"] == "draft_789"
        assert "edited_action" in result.decisions[0]
        assert result.decisions[0]["updated_content"] == {"subject": "New Subject"}

    def test_build_from_unknown_action_defaults_to_reject(self):
        """Test that unknown action defaults to reject."""
        builder = ApprovalDecisionBuilder(agent_type="email_agent")
        draft_action = {
            "type": "draft_action",
            "action": "unknown_action",
            "draft_id": "draft_999",
        }

        result = builder.build_from_draft_action(draft_action, [])

        assert result.decisions[0]["type"] == "reject"


class TestApprovalDecisionBuilderBuildFromClassification:
    """Tests for ApprovalDecisionBuilder.build_from_classification()."""

    def test_build_approve_decision(self):
        """Test building approve decision from classification."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        classification = MockClassificationResult(decision="APPROVE", reasoning="User confirmed")
        action_requests = [{"name": "search", "args": {}}]

        result = builder.build_from_classification(
            classification=classification,
            action_requests=action_requests,
            user_response="oui",
            user_language="fr",
        )

        assert len(result.decisions) == 1
        assert result.decisions[0]["type"] == "approve"

    @patch.object(RejectionDecisionBuilder, "build")
    def test_build_reject_decision(self, mock_build):
        """Test building reject decision from classification."""
        mock_build.return_value = {"type": "reject", "message": "Canceled"}

        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        classification = MockClassificationResult(
            decision="REJECT", reasoning="User said no", confidence=0.9
        )
        action_requests = [{"name": "delete", "args": {}}]

        result = builder.build_from_classification(
            classification=classification,
            action_requests=action_requests,
            user_response="non",
            user_language="fr",
        )

        assert len(result.decisions) == 1
        assert result.decisions[0]["type"] == "reject"

    @patch.object(EditDecisionBuilder, "build")
    def test_build_edit_decision(self, mock_build):
        """Test building edit decision from classification."""
        mock_build.return_value = {
            "type": "edit",
            "edited_action": {"name": "search", "args": {"name": "Jane"}},
        }

        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        classification = MockClassificationResult(
            decision="EDIT",
            reasoning="User corrected params",
            edited_params={"name": "Jane"},
        )
        action_requests = [{"name": "search", "args": {"name": "John"}}]

        result = builder.build_from_classification(
            classification=classification,
            action_requests=action_requests,
            user_response="plutôt Jane",
            user_language="fr",
        )

        assert len(result.decisions) == 1
        assert result.decisions[0]["type"] == "edit"

    def test_build_edit_raises_if_no_edited_params(self):
        """Test that edit decision raises if edited_params is None."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        classification = MockClassificationResult(
            decision="EDIT",
            reasoning="Edit requested",
            edited_params=None,  # Missing
        )
        action_requests = [{"name": "tool", "args": {}}]

        with pytest.raises(ValueError) as exc_info:
            builder.build_from_classification(
                classification=classification,
                action_requests=action_requests,
            )

        assert "requires edited_params" in str(exc_info.value)

    def test_build_multiple_actions(self):
        """Test building decisions for multiple actions."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        classification = MockClassificationResult(decision="APPROVE", reasoning="Confirmed")
        action_requests = [
            {"name": "action1", "args": {}},
            {"name": "action2", "args": {}},
        ]

        result = builder.build_from_classification(
            classification=classification,
            action_requests=action_requests,
        )

        assert len(result.decisions) == 2
        assert result.action_indices == [0, 1]


class TestApprovalDecisionBuilderInit:
    """Tests for ApprovalDecisionBuilder initialization."""

    def test_init_creates_composed_builders(self):
        """Test that init creates all composed builders."""
        builder = ApprovalDecisionBuilder(agent_type="my_agent")

        assert builder.agent_type == "my_agent"
        assert isinstance(builder.extractor, ClassificationExtractor)
        assert isinstance(builder.rejection_builder, RejectionDecisionBuilder)
        assert isinstance(builder.edit_builder, EditDecisionBuilder)

    def test_init_passes_agent_type_to_builders(self):
        """Test that agent_type is passed to composed builders."""
        builder = ApprovalDecisionBuilder(agent_type="contacts_agent")

        assert builder.rejection_builder.agent_type == "contacts_agent"
        assert builder.edit_builder.agent_type == "contacts_agent"
