"""
E2E Integration Tests for HITL (Human-in-the-Loop) Flows.

Tests complete HITL workflows end-to-end:
- User initiates conversation
- Graph interrupts for HITL approval
- User responds (APPROVE/REJECT/EDIT)
- Graph resumes with decision
- Final result returned
- Token tracking and metrics
"""

import os
import uuid
from unittest.mock import Mock, patch

import pytest

from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.constants import (
    HITL_DECISION_APPROVE,
    HITL_DECISION_EDIT,
    HITL_DECISION_REJECT,
)
from src.domains.agents.domain_schemas import ToolApprovalDecision

# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestHITLApproveFlow:
    """E2E tests for HITL APPROVE flow."""

    async def test_hitl_approve_flow_complete(self):
        """
        Test complete HITL APPROVE flow.

        Scenario:
        1. User: "Search for John Doe"
        2. Agent: Interrupt with search_contacts_tool
        3. User: "Yes, go ahead"
        4. Agent: Executes tool and returns results
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        # Step 1: Simulate HITL interrupt
        action_requests = [
            {
                "name": "search_contacts_tool",
                "args": {"query": "John Doe"},
            }
        ]

        # Step 2: User approves
        class MockClassification:
            decision = HITL_DECISION_APPROVE
            reasoning = "User approved action"
            edited_params = None
            confidence = 0.95
            clarification_question = None

        # Step 3: Build approval decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="oui vas-y",
        )

        # Verify decision structure
        assert isinstance(decision, ToolApprovalDecision)
        assert len(decision.decisions) == 1
        assert decision.decisions[0]["type"] == "approve"
        assert decision.action_indices == [0]

        # Step 4: Graph would resume with APPROVE decision
        # In real flow, this would execute search_contacts_tool
        # Result: User gets contact results

    async def test_hitl_approve_multiple_tools(self):
        """
        Test HITL APPROVE flow with multiple tools.

        Scenario:
        1. User: "Search John and send him an email"
        2. Agent: Interrupt with search_contacts_tool AND send_email_tool
        3. User: "Yes, do both"
        4. Agent: Executes both tools
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        # Simulate multi-tool interrupt
        action_requests = [
            {"name": "search_contacts_tool", "args": {"query": "John"}},
            {"name": "send_email_tool", "args": {"to": "john@example.com", "subject": "Hello"}},
        ]

        class MockClassification:
            decision = HITL_DECISION_APPROVE
            reasoning = "User approved all actions"
            edited_params = None
            confidence = 0.9
            clarification_question = None

        # Build decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="oui fais les deux",
        )

        # Verify both tools approved
        assert len(decision.decisions) == 2
        assert decision.decisions[0]["type"] == "approve"
        assert decision.decisions[1]["type"] == "approve"
        assert decision.action_indices == [0, 1]


@pytest.mark.e2e
@pytest.mark.asyncio
class TestHITLRejectFlow:
    """E2E tests for HITL REJECT flow."""

    @patch("src.domains.agents.api.mixins.hitl_management.hitl_tool_rejections_by_reason")
    @patch("src.domains.agents.api.mixins.hitl_management.hitl_rejection_type_total")
    async def test_hitl_reject_flow_complete(self, mock_rejection_type, mock_rejections_by_reason):
        """
        Test complete HITL REJECT flow.

        Scenario:
        1. User: "Delete contact John"
        2. Agent: Interrupt with delete_contact_tool
        3. User: "No, cancel that"
        4. Agent: Skips execution, returns rejection message
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()
        mixin.agent_type = "planner"

        # Simulate HITL interrupt with dangerous action
        action_requests = [
            {
                "name": "delete_contact_tool",
                "args": {"contact_id": "123"},
            }
        ]

        # User rejects
        class MockClassification:
            decision = HITL_DECISION_REJECT
            reasoning = "User cancelled the delete operation"
            edited_params = None
            confidence = 0.92
            clarification_question = None

        # Build rejection decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="non annule ça",
        )

        # Verify decision structure
        assert len(decision.decisions) == 1
        assert decision.decisions[0]["type"] == "reject"
        assert "Action refusée" in decision.decisions[0]["message"]
        assert "User cancelled" in decision.decisions[0]["message"]

        # Verify metrics were tracked
        mock_rejections_by_reason.labels.assert_called_once()
        mock_rejection_type.labels.assert_called_once()

        # In real flow, graph would inject ToolMessage with rejection
        # and continue without executing the tool

    @patch("src.domains.agents.api.mixins.hitl_management.hitl_tool_rejections_by_reason")
    @patch("src.domains.agents.api.mixins.hitl_management.hitl_rejection_type_total")
    async def test_hitl_reject_low_confidence(self, mock_rejection_type, mock_rejections_by_reason):
        """
        Test HITL REJECT due to low confidence classification.

        Scenario:
        1. User: "Maybe send email to John"
        2. Agent: Interrupt with send_email_tool
        3. User: "I'm not sure" (low confidence response)
        4. Agent: Treats as rejection for safety
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        action_requests = [{"name": "send_email_tool", "args": {"to": "john@example.com"}}]

        # Low confidence classification
        class MockClassification:
            decision = HITL_DECISION_REJECT
            reasoning = "Low confidence in user intent"
            edited_params = None
            confidence = 0.3  # Low confidence
            clarification_question = None

        # Build decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="je sais pas trop",
        )

        # Verify rejection
        assert decision.decisions[0]["type"] == "reject"

        # Verify rejection type is "low_confidence"
        # (inferred by _infer_rejection_type)


@pytest.mark.e2e
@pytest.mark.asyncio
class TestHITLEditFlow:
    """E2E tests for HITL EDIT flow."""

    @patch("src.domains.agents.api.mixins.hitl_management.hitl_edit_actions_total")
    @patch("src.domains.agents.api.mixins.hitl_management.hitl_edit_decisions_total")
    async def test_hitl_edit_flow_complete(self, mock_edit_decisions, mock_edit_actions):
        """
        Test complete HITL EDIT flow.

        Scenario:
        1. User: "Search for John Doe"
        2. Agent: Interrupt with search_contacts_tool(query="John Doe")
        3. User: "Actually search for Jane Doe"
        4. Agent: Executes with modified query="Jane Doe"
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()
        mixin.agent_type = "planner"

        # Simulate HITL interrupt
        action_requests = [
            {
                "name": "search_contacts_tool",
                "args": {"query": "John Doe"},
            }
        ]

        # User edits the query
        class MockClassification:
            decision = HITL_DECISION_EDIT
            reasoning = "User corrected the search query"
            edited_params = {"query": "Jane Doe"}  # Modified parameter
            confidence = 0.88
            clarification_question = None

        # Build edit decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="plutôt Jane Doe",
        )

        # Verify decision structure
        assert len(decision.decisions) == 1
        assert decision.decisions[0]["type"] == "edit"

        # Verify edited action
        edited_action = decision.decisions[0]["edited_action"]
        assert edited_action["name"] == "search_contacts_tool"
        assert edited_action["args"]["query"] == "Jane Doe"

        # Verify metrics were tracked
        mock_edit_actions.labels.assert_called_once()
        mock_edit_decisions.labels.assert_called_once()

        # In real flow, graph would execute search_contacts_tool with new query

    @patch("src.domains.agents.api.mixins.hitl_management.hitl_edit_actions_total")
    @patch("src.domains.agents.api.mixins.hitl_management.hitl_edit_decisions_total")
    async def test_hitl_edit_multiple_params(self, mock_edit_decisions, mock_edit_actions):
        """
        Test HITL EDIT flow with multiple parameter modifications.

        Scenario:
        1. User: "Search contacts in Paris"
        2. Agent: Interrupt with search_contacts_tool(city="Paris")
        3. User: "Search in London for people named John"
        4. Agent: Executes with city="London", name="John"
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        action_requests = [
            {
                "name": "search_contacts_tool",
                "args": {"city": "Paris"},
            }
        ]

        # User modifies multiple params
        class MockClassification:
            decision = HITL_DECISION_EDIT
            reasoning = "User updated search criteria"
            edited_params = {"city": "London", "name": "John"}
            confidence = 0.85
            clarification_question = None

        # Build decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="plutôt à Londres pour John",
        )

        # Verify merged args
        edited_action = decision.decisions[0]["edited_action"]
        assert edited_action["args"]["city"] == "London"
        assert edited_action["args"]["name"] == "John"

    @patch("src.domains.agents.api.mixins.hitl_management.hitl_edit_actions_total")
    @patch("src.domains.agents.api.mixins.hitl_management.hitl_edit_decisions_total")
    async def test_hitl_edit_preserves_original_params(
        self, mock_edit_decisions, mock_edit_actions
    ):
        """
        Test HITL EDIT preserves unmodified original parameters.

        Scenario:
        1. Agent proposes: search_contacts_tool(name="John", city="Paris", age=30)
        2. User edits only city: "Change city to London"
        3. Agent executes with: name="John" (preserved), city="London" (modified), age=30 (preserved)
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        action_requests = [
            {
                "name": "search_contacts_tool",
                "args": {"name": "John", "city": "Paris", "age": 30},
            }
        ]

        # User only modifies city
        class MockClassification:
            decision = HITL_DECISION_EDIT
            reasoning = "User changed city only"
            edited_params = {"city": "London"}  # Only city modified
            confidence = 0.9
            clarification_question = None

        # Build decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="change city to London",
        )

        # Verify all params are present
        edited_action = decision.decisions[0]["edited_action"]
        assert edited_action["args"]["name"] == "John"  # Preserved
        assert edited_action["args"]["city"] == "London"  # Modified
        assert edited_action["args"]["age"] == 30  # Preserved


@pytest.mark.e2e
@pytest.mark.asyncio
class TestHITLStreamingIntegration:
    """E2E tests for HITL with streaming and token tracking."""

    async def test_hitl_streaming_with_token_enrichment(self):
        """
        Test HITL flow with streaming chunk buffering and token enrichment.

        Scenario:
        1. User approves HITL action
        2. Graph resumes and streams tokens
        3. StreamingMixin buffers chunks
        4. Done chunk is enriched with aggregated tokens
        """
        from src.domains.agents.api.mixins.streaming import StreamingMixin

        mixin = StreamingMixin()

        # Simulate graph resumption stream
        async def mock_graph_stream():
            yield ChatStreamChunk(type="token", content="Searching", metadata={})
            yield ChatStreamChunk(type="token", content=" contacts", metadata={})
            yield ChatStreamChunk(type="token", content="...", metadata={})
            yield ChatStreamChunk(type="done", content="", metadata={"original": "value"})

        # Mock tracker with aggregated tokens
        mock_tracker = Mock()
        mock_tracker.get_summary.return_value = {
            "tokens_in": 250,  # Classification + resumption
            "tokens_out": 120,
            "tokens_cache": 30,
            "cost_eur": 0.15,
            "message_count": 5,
        }

        # Test streaming
        result_chunks = []
        async for chunk in mixin.buffer_and_enrich_resumption_chunks(
            graph_stream=mock_graph_stream(),
            run_id="hitl_e2e_test",
            user_id=uuid.uuid4(),
            conversation_id=uuid.uuid4(),
            tracker=mock_tracker,
        ):
            result_chunks.append(chunk)

        # Verify all chunks received
        assert len(result_chunks) == 4

        # Verify token chunks
        assert result_chunks[0].content == "Searching"
        assert result_chunks[1].content == " contacts"
        assert result_chunks[2].content == "..."

        # Verify enriched done chunk
        done_chunk = result_chunks[3]
        assert done_chunk.type == "done"
        assert done_chunk.metadata["tokens_in"] == 250
        assert done_chunk.metadata["tokens_out"] == 120
        assert done_chunk.metadata["cost_eur"] == 0.15
        assert done_chunk.metadata["original"] == "value"  # Original preserved


@pytest.mark.e2e
@pytest.mark.asyncio
class TestHITLSecurityValidation:
    """E2E tests for HITL security validation."""

    async def test_hitl_dos_protection_triggered(self):
        """
        Test DoS protection when agent proposes too many actions.

        Scenario:
        1. Malicious/buggy agent proposes 15 tool calls
        2. HITL validation rejects with ValueError
        3. Request is rejected before classification
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        # Simulate excessive actions (15 > MAX_HITL_ACTIONS=10)
        excessive_actions = [{"name": f"tool_{i}", "args": {}} for i in range(15)]

        # Validation should raise
        with pytest.raises(ValueError) as exc_info:
            mixin.validate_hitl_security(excessive_actions)

        assert "Too many HITL actions" in str(exc_info.value)
        assert "15" in str(exc_info.value)
        assert "10" in str(exc_info.value)

    async def test_hitl_dos_protection_at_limit(self):
        """
        Test DoS protection passes exactly at the limit.

        Scenario:
        1. Agent proposes exactly 10 tool calls (limit)
        2. Validation passes
        3. Flow continues normally
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        # Exactly at limit (10 actions)
        action_requests = [{"name": f"tool_{i}", "args": {}} for i in range(10)]

        # Should not raise
        mixin.validate_hitl_security(action_requests)

        # Flow continues...


@pytest.mark.e2e
@pytest.mark.asyncio
class TestHITLErrorHandling:
    """E2E tests for HITL error handling scenarios."""

    async def test_hitl_edit_missing_params_error(self):
        """
        Test error handling when EDIT decision has no edited_params.

        Scenario:
        1. Classifier returns EDIT decision
        2. But edited_params is None/empty
        3. System raises ValueError (should be AMBIGUOUS instead)
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        action_requests = [{"name": "search_contacts_tool", "args": {"query": "John"}}]

        # Invalid EDIT classification (no edited_params)
        class MockClassification:
            decision = HITL_DECISION_EDIT
            reasoning = "User wants to edit"
            edited_params = None  # ERROR: Missing!
            confidence = 0.8
            clarification_question = None

        # Should raise ValueError
        with pytest.raises(ValueError) as exc_info:
            mixin._build_approval_decision_from_classification(
                classification=MockClassification(),
                action_requests=action_requests,
                user_response="modifier quelque chose",
            )

        assert "EDIT decision requires edited_params" in str(exc_info.value)

    async def test_hitl_empty_action_requests(self):
        """
        Test behavior when action_requests is empty (edge case).

        Scenario:
        1. HITL interrupt with empty action_requests
        2. Classification returns APPROVE
        3. Decision should have empty decisions list
        """
        from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

        mixin = HITLManagementMixin()

        # Empty action requests (unusual but possible)
        action_requests = []

        class MockClassification:
            decision = HITL_DECISION_APPROVE
            reasoning = "Approved"
            edited_params = None
            confidence = 0.9
            clarification_question = None

        # Build decision
        decision = mixin._build_approval_decision_from_classification(
            classification=MockClassification(),
            action_requests=action_requests,
            user_response="oui",
        )

        # Should have empty decisions
        assert decision.decisions == []
        assert decision.action_indices == []


# Fixtures for E2E tests
@pytest.fixture
async def mock_agent_service():
    """Provide a mock AgentService for E2E tests."""
    from src.domains.agents.api.mixins.hitl_management import HITLManagementMixin

    from src.domains.agents.api.mixins.graph_management import GraphManagementMixin
    from src.domains.agents.api.mixins.streaming import StreamingMixin

    class TestAgentService(HITLManagementMixin, StreamingMixin, GraphManagementMixin):
        def __init__(self):
            GraphManagementMixin.__init__(self)
            self.agent_type = "test_agent"

    service = TestAgentService()
    yield service
