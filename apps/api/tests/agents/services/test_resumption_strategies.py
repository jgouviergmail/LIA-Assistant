"""
Tests for HITL resumption strategies.

Tests ConversationalHitlResumption strategy that resumes LangGraph execution after user approval.

REFACTORED (Phase 8): Tests now properly mock the complex infrastructure:
- TrackingContext (async context manager with get_summary_dto)
- Redis cache (for nested interrupts)
- TokenTrackingCallback (for metrics)
- ConversationService (for archival)
- Database access (get_db_context)
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk
from langgraph.graph.state import CompiledStateGraph

from src.domains.agents.domain_schemas import ToolApprovalDecision
from src.domains.agents.services.hitl.resumption_strategies import (
    ConversationalHitlResumption,
    _build_plan_modifications_from_classifier,
    _build_resume_value,
    build_edit_reformulated_intent,
)
from src.domains.chat.schemas import TokenSummaryDTO
from src.domains.conversations.service import ConversationService


@pytest.fixture
def conversation_service():
    """Mock ConversationService for tests."""
    service = MagicMock(spec=ConversationService)
    service.archive_message = AsyncMock()
    service.increment_conversation_stats = AsyncMock()
    return service


@pytest.fixture
def mock_tracker():
    """Mock TrackingContext for token tracking."""
    tracker = MagicMock()
    tracker.get_summary_dto.return_value = TokenSummaryDTO(
        tokens_in=100,
        tokens_out=50,
        tokens_cache=10,
        cost_eur=0.001,
        message_count=1,
    )
    return tracker


@pytest.fixture
def conversational_strategy(conversation_service):
    """Create ConversationalHitlResumption instance."""
    return ConversationalHitlResumption(conversation_service)


@pytest.fixture
def approval_decision():
    """Sample approval decision (approve single tool)."""
    return ToolApprovalDecision(
        decisions=[
            {
                "tool_call_id": "call_123",
                "type": "approve",
                "edited_args": None,
            }
        ],
        action_indices=[0],
    )


@pytest.fixture
def mock_graph():
    """Mock CompiledStateGraph."""
    graph = MagicMock(spec=CompiledStateGraph)

    # Mock astream to return tokens
    async def mock_astream(*args, **kwargs):
        # Simulate graph execution: yield AI response tokens as (mode, chunk) pairs
        for token in ["Bonjour", " ", "je", " ", "suis", " ", "l'assistant"]:
            chunk = (AIMessageChunk(content=token, additional_kwargs={}, id="msg_123"), {})
            yield ("messages", chunk)

    graph.astream = mock_astream
    return graph


# ============================================================================
# _build_resume_value Unit Tests (Pure logic, no infrastructure)
# ============================================================================


def test_build_resume_value_tool_level_approve():
    """Test building resume value for tool-level approve decision."""
    decision = ToolApprovalDecision(
        decisions=[{"type": "approve"}],
        action_indices=[0],
    )
    result = _build_resume_value(decision, None, "run_123")

    assert result["approved"] is True
    assert result["edited_args"] is None
    assert result["decisions"] == [{"type": "approve"}]


def test_build_resume_value_tool_level_reject():
    """Test building resume value for tool-level reject decision."""
    decision = ToolApprovalDecision(
        decisions=[{"type": "reject"}],
        action_indices=[0],
    )
    result = _build_resume_value(decision, None, "run_123")

    assert result["approved"] is False
    assert result["edited_args"] is None


def test_build_resume_value_tool_level_edit():
    """Test building resume value for tool-level edit decision."""
    decision = ToolApprovalDecision(
        decisions=[
            {
                "type": "edit",
                "edited_action": {"name": "search_contacts_tool", "args": {"query": "Huà"}},
            }
        ],
        action_indices=[0],
    )
    result = _build_resume_value(decision, None, "run_123")

    assert result["approved"] is True  # Edit counts as approved
    assert result["edited_args"] == {"query": "Huà"}


def test_build_resume_value_plan_level_approve():
    """Test building resume value for plan-level approve decision."""
    decision = ToolApprovalDecision(
        decisions=[{"type": "approve"}],
        action_indices=[0],
    )
    pending_actions = [{"type": "plan_approval"}]
    result = _build_resume_value(decision, pending_actions, "run_123")

    assert result["decision"] == "APPROVE"


def test_build_resume_value_plan_level_reject():
    """Test building resume value for plan-level reject decision."""
    decision = ToolApprovalDecision(
        decisions=[{"type": "reject", "rejection_reason": "Je ne veux pas"}],
        action_indices=[0],
    )
    pending_actions = [{"type": "plan_approval"}]
    result = _build_resume_value(decision, pending_actions, "run_123")

    assert result["decision"] == "REJECT"
    assert result["rejection_reason"] == "Je ne veux pas"


def test_build_resume_value_plan_level_edit():
    """Test building resume value for plan-level edit decision."""
    # Note: Plan-level edit requires valid 'edit' format with edited_action
    # but the modifications are passed through as-is for approval_gate_node
    decision = ToolApprovalDecision(
        decisions=[
            {
                "type": "edit",
                "edited_action": {"name": "plan_edit", "args": {}},  # Required for validation
                "modifications": [{"modification_type": "update_args", "target_step_id": "step_1"}],
            }
        ],
        action_indices=[0],
    )
    pending_actions = [{"type": "plan_approval"}]
    result = _build_resume_value(decision, pending_actions, "run_123")

    assert result["decision"] == "EDIT"
    assert len(result["modifications"]) == 1


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

    def test_integration_with_build_resume_value(self):
        """
        Test full integration: classifier edited_params → modifications via _build_resume_value.

        This is the Issue #60 scenario:
        - User says "pas 20, mais 4 emails"
        - Classifier extracts edited_params={"max_results": 4}
        - _build_resume_value converts to modifications for approval_gate_node
        """
        decision = ToolApprovalDecision(
            decisions=[
                {
                    "type": "edit",
                    "edited_action": {"name": "plan_edit", "args": {"max_results": 4}},
                }
            ],
            action_indices=[0],
        )
        pending_actions = [
            {
                "type": "plan_approval",
                "plan_summary": {
                    "steps": [
                        {
                            "step_id": "gmail_send_email_step",
                            "parameters": {"max_results": 20, "query": "contacts"},
                        }
                    ]
                },
            }
        ]

        result = _build_resume_value(decision, pending_actions, "run_123")

        assert result["decision"] == "EDIT"
        assert len(result["modifications"]) == 1
        assert result["modifications"][0]["step_id"] == "gmail_send_email_step"
        assert result["modifications"][0]["new_parameters"] == {"max_results": 4}


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


# ============================================================================
# ConversationalHitlResumption Integration Tests (with mocked infrastructure)
# ============================================================================


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    session = MagicMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    session.commit = AsyncMock()
    return session


@pytest.fixture
def mock_db_context(mock_db_session):
    """Create a mock async context manager for get_db_context."""
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _mock_db_context():
        yield mock_db_session

    return _mock_db_context


@pytest.mark.asyncio
async def test_conversational_resumption_yields_tokens_and_done(
    conversational_strategy, mock_graph, mock_tracker, mock_db_context
):
    """Test that resumption yields tokens and done chunk."""
    with patch(
        "src.infrastructure.database.get_db_context",
        mock_db_context,
    ):
        chunks = []
        async for chunk in conversational_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=ToolApprovalDecision(
                decisions=[{"type": "approve"}],
                action_indices=[0],
            ),
            conversation_id=uuid4(),
            user_id=uuid4(),
            run_id="test_run",
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

    # Should have tokens + done chunk
    assert len(chunks) > 0
    assert chunks[-1].type == "done"

    # Verify token chunks exist
    token_chunks = [c for c in chunks if c.type == "token"]
    assert len(token_chunks) >= 1


@pytest.mark.asyncio
async def test_resumption_done_chunk_has_metrics(
    conversational_strategy, mock_graph, mock_tracker, mock_db_context
):
    """Test that done chunk includes token metrics."""
    with patch(
        "src.infrastructure.database.get_db_context",
        mock_db_context,
    ):
        chunks = []
        async for chunk in conversational_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=ToolApprovalDecision(
                decisions=[{"type": "approve"}],
                action_indices=[0],
            ),
            conversation_id=uuid4(),
            user_id=uuid4(),
            run_id="test_run",
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

    done_chunk = chunks[-1]
    assert done_chunk.type == "done"
    assert "tokens_in" in done_chunk.metadata
    assert "tokens_out" in done_chunk.metadata
    assert "cost_eur" in done_chunk.metadata
    assert "duration_seconds" in done_chunk.metadata
    assert "run_id" in done_chunk.metadata
    assert done_chunk.metadata["resumption_strategy"] == "conversational"


@pytest.mark.asyncio
async def test_resumption_handles_graph_error(
    conversational_strategy, approval_decision, mock_tracker, mock_db_context
):
    """Test that resumption handles graph errors gracefully."""
    error_graph = MagicMock(spec=CompiledStateGraph)

    async def mock_astream_error(*args, **kwargs):
        raise RuntimeError("Graph execution failed")
        yield  # Make it a generator

    error_graph.astream = mock_astream_error

    with (
        patch(
            "src.infrastructure.database.get_db_context",
            mock_db_context,
        ),
        patch("src.infrastructure.observability.metrics_agents.hitl_resumption_total"),
        patch("src.infrastructure.observability.metrics_agents.sse_streaming_errors_total"),
    ):
        chunks = []
        async for chunk in conversational_strategy.resume_and_stream(
            graph=error_graph,
            approval_decision=approval_decision,
            conversation_id=uuid4(),
            user_id=uuid4(),
            run_id="test_run",
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

    # Should yield error chunk and done chunk
    assert len(chunks) >= 2
    assert any(c.type == "error" for c in chunks)
    assert chunks[-1].type == "done"
    assert chunks[-1].metadata.get("error") is True


@pytest.mark.asyncio
async def test_resumption_records_success_metrics(
    conversational_strategy, mock_graph, approval_decision, mock_tracker, mock_db_context
):
    """Test that resumption records Prometheus metrics on success."""
    with (
        patch(
            "src.infrastructure.database.get_db_context",
            mock_db_context,
        ),
        patch(
            "src.infrastructure.observability.metrics_agents.hitl_resumption_total"
        ) as mock_total,
        patch(
            "src.infrastructure.observability.metrics_agents.hitl_resumption_duration_seconds"
        ) as mock_duration,
    ):
        async for _chunk in conversational_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision,
            conversation_id=uuid4(),
            user_id=uuid4(),
            run_id="test_run",
            tracker=mock_tracker,
        ):
            pass

        mock_total.labels.assert_called_with(strategy="conversational", status="success")
        mock_duration.labels.assert_called_with(strategy="conversational")


@pytest.mark.asyncio
async def test_resumption_records_error_metrics(
    conversational_strategy, approval_decision, mock_tracker, mock_db_context
):
    """Test that resumption records Prometheus metrics on error."""
    error_graph = MagicMock(spec=CompiledStateGraph)

    async def mock_astream_error(*args, **kwargs):
        raise RuntimeError("Graph failed")
        yield

    error_graph.astream = mock_astream_error

    with (
        patch(
            "src.infrastructure.database.get_db_context",
            mock_db_context,
        ),
        patch(
            "src.infrastructure.observability.metrics_agents.hitl_resumption_total"
        ) as mock_total,
        patch("src.infrastructure.observability.metrics_agents.sse_streaming_errors_total"),
    ):
        async for _chunk in conversational_strategy.resume_and_stream(
            graph=error_graph,
            approval_decision=approval_decision,
            conversation_id=uuid4(),
            user_id=uuid4(),
            run_id="test_run",
            tracker=mock_tracker,
        ):
            pass

        mock_total.labels.assert_called_with(strategy="conversational", status="error")
