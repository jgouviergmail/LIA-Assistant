"""
Tests for Phase 3 - HITL Policy Classes.

These tests verify that HITL decision building policies are correctly implemented
and can be instantiated without errors.
"""

from src.domains.agents.services.hitl.policies import (
    ApprovalDecisionBuilder,
    ClassificationExtractor,
    EditDecisionBuilder,
    RejectionDecisionBuilder,
)


class TestPolicyClassesInstantiation:
    """Test that all HITL policy classes can be instantiated."""

    def test_classification_extractor_instantiation(self):
        """Test ClassificationExtractor can be instantiated."""
        extractor = ClassificationExtractor()
        assert extractor is not None

    def test_rejection_builder_instantiation(self):
        """Test RejectionDecisionBuilder can be instantiated."""
        builder = RejectionDecisionBuilder(agent_type="test_agent")
        assert builder is not None
        assert builder.agent_type == "test_agent"

    def test_edit_builder_instantiation(self):
        """Test EditDecisionBuilder can be instantiated."""
        builder = EditDecisionBuilder(agent_type="test_agent")
        assert builder is not None
        assert builder.agent_type == "test_agent"

    def test_approval_builder_instantiation(self):
        """Test ApprovalDecisionBuilder can be instantiated."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        assert builder is not None
        assert builder.agent_type == "test_agent"


class TestClassificationExtractor:
    """Test ClassificationExtractor extraction logic."""

    def test_extract_from_object(self):
        """Test extraction from ClassificationResult object."""

        class MockClassification:
            decision = "approve"
            reasoning = "User approved"
            edited_params = {"name": "John"}
            clarification_question = "Are you sure?"

        extractor = ClassificationExtractor()
        decision, reasoning, edited_params, clarification = extractor.extract(MockClassification())

        assert decision == "approve"
        assert reasoning == "User approved"
        assert edited_params == {"name": "John"}
        assert clarification == "Are you sure?"

    def test_extract_from_dict(self):
        """Test extraction from dict (backward compatibility)."""
        extractor = ClassificationExtractor()
        classification_dict = {
            "decision": "reject",
            "reasoning": "User rejected",
            "edited_params": None,
            "clarification_question": None,
        }

        decision, reasoning, edited_params, clarification = extractor.extract(classification_dict)

        assert decision == "reject"
        assert reasoning == "User rejected"
        assert edited_params is None
        assert clarification is None


class TestRejectionDecisionBuilder:
    """Test RejectionDecisionBuilder logic."""

    def test_infer_rejection_type_explicit_no(self):
        """Test inference of explicit_no rejection type."""
        rejection_type = RejectionDecisionBuilder.infer_rejection_type(
            user_response="non annule ça", classification={"confidence": 0.8}
        )
        assert rejection_type == "explicit_no"

    def test_infer_rejection_type_low_confidence(self):
        """Test inference of low_confidence rejection type."""
        rejection_type = RejectionDecisionBuilder.infer_rejection_type(
            user_response="plutôt paul durand", classification={"confidence": 0.3}
        )
        assert rejection_type == "low_confidence"

    def test_infer_rejection_type_implicit_no(self):
        """Test inference of implicit_no rejection type."""
        rejection_type = RejectionDecisionBuilder.infer_rejection_type(
            user_response="plutôt paul durand", classification={"confidence": 0.9}
        )
        assert rejection_type == "implicit_no"


class TestEditDecisionBuilder:
    """Test EditDecisionBuilder logic."""

    def test_infer_edit_type_minor_adjustment(self):
        """Test inference of minor_adjustment edit type."""
        edit_type = EditDecisionBuilder.infer_edit_type(
            tool_args={"name": "John"}, edited_params={"name": "Jane"}, tool_name="search"
        )
        assert edit_type == "minor_adjustment"

    def test_infer_edit_type_full_rewrite(self):
        """Test inference of full_rewrite edit type."""
        edit_type = EditDecisionBuilder.infer_edit_type(
            tool_args={"name": "John"},
            edited_params={"name": "Jane", "city": "Paris", "age": 30, "country": "France"},
            tool_name="search",
        )
        assert edit_type == "full_rewrite"

    def test_infer_edit_type_params_modified(self):
        """Test inference of params_modified edit type."""
        edit_type = EditDecisionBuilder.infer_edit_type(
            tool_args={"name": "John", "city": "London"},
            edited_params={"name": "Jane", "city": "Paris", "age": 30},
            tool_name="search",
        )
        assert edit_type == "params_modified"


class TestApprovalDecisionBuilder:
    """Test ApprovalDecisionBuilder composition."""

    def test_approval_builder_has_composed_builders(self):
        """Test that ApprovalDecisionBuilder composes other builders."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")

        assert hasattr(builder, "extractor")
        assert isinstance(builder.extractor, ClassificationExtractor)

        assert hasattr(builder, "rejection_builder")
        assert isinstance(builder.rejection_builder, RejectionDecisionBuilder)

        assert hasattr(builder, "edit_builder")
        assert isinstance(builder.edit_builder, EditDecisionBuilder)

    def test_build_from_draft_action_confirm(self):
        """Test building decision from draft action with confirm."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        draft_action = {
            "type": "draft_action",
            "action": "confirm",
            "draft_id": "draft_123",
            "updated_content": None,
        }
        action_requests = [{"type": "draft_critique", "draft_id": "draft_123"}]

        decision = builder.build_from_draft_action(draft_action, action_requests)

        # confirm maps to approve in ToolApprovalDecision
        assert decision.decisions[0]["type"] == "approve"
        assert decision.decisions[0]["draft_id"] == "draft_123"
        assert decision.decisions[0]["original_action"] == "confirm"
        assert decision.action_indices == [0]

    def test_build_from_draft_action_edit(self):
        """Test building decision from draft action with edit."""
        builder = ApprovalDecisionBuilder(agent_type="test_agent")
        draft_action = {
            "type": "draft_action",
            "action": "edit",
            "draft_id": "draft_123",
            "updated_content": {"subject": "New subject"},
        }
        action_requests = [{"type": "draft_critique", "draft_id": "draft_123"}]

        decision = builder.build_from_draft_action(draft_action, action_requests)

        assert decision.decisions[0]["type"] == "edit"
        assert decision.decisions[0]["draft_id"] == "draft_123"
        assert decision.decisions[0]["updated_content"] == {"subject": "New subject"}


class TestHITLOrchestratorIntegration:
    """Test HITLOrchestrator integrates with Policy Classes correctly."""

    def test_hitl_orchestrator_has_approval_builder(self):
        """Test that HITLOrchestrator has approval_builder."""
        from src.domains.agents.services.hitl_orchestrator import HITLOrchestrator

        orchestrator = HITLOrchestrator(
            hitl_classifier=None,  # type: ignore
            hitl_question_generator=None,  # type: ignore
            hitl_store=None,  # type: ignore
            graph=None,  # type: ignore
            agent_type="test_agent",
        )

        assert hasattr(orchestrator, "approval_builder")
        assert isinstance(orchestrator.approval_builder, ApprovalDecisionBuilder)
        assert orchestrator.approval_builder.agent_type == "test_agent"
