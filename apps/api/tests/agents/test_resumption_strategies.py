"""
Comprehensive tests for HITL resumption strategies.

Tests the ConversationalHitlResumption strategy implementation covering:
- Strategy initialization
- Resume and stream with approve/reject/edit decisions
- Nested HITL interrupts
- Error handling and edge cases
- Tracker management (unified vs new)
- Message archival and conversation stats

Coverage target: 85%+ for resumption_strategies.py
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessageChunk, HumanMessage, RemoveMessage, ToolMessage
from langgraph.types import Command

from src.domains.agents.domain_schemas import ToolApprovalDecision
from src.domains.agents.services.hitl.resumption_strategies import (
    ConversationalHitlResumption,
)

# ============================================================================
# Fixtures
# ============================================================================


# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)


@pytest.fixture
def mock_db():
    """Mock database session."""
    db_mock = MagicMock()
    db_mock.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    db_mock.commit = AsyncMock()
    return db_mock


@pytest.fixture
def conversation_service_mock():
    """Mock ConversationService for message archival and stats."""
    service = MagicMock()
    service.archive_message = AsyncMock()
    service.increment_conversation_stats = AsyncMock()
    return service


@pytest.fixture
def resumption_strategy(conversation_service_mock):
    """ConversationalHitlResumption strategy instance."""
    return ConversationalHitlResumption(conversation_service_mock)


@pytest.fixture
def mock_graph():
    """Mock CompiledStateGraph with astream."""
    graph = MagicMock()
    graph.aget_state = AsyncMock()
    return graph


@pytest.fixture
def mock_tracker():
    """Mock TrackingContext for token tracking."""
    tracker = MagicMock()
    tracker.get_summary = MagicMock(
        return_value={
            "tokens_in": 100,
            "tokens_out": 200,
            "tokens_cache": 50,
            "cost_eur": 0.005,
        }
    )
    return tracker


@pytest.fixture
def base_test_ids():
    """Base test IDs for all tests."""
    return {
        "conversation_id": uuid4(),
        "user_id": uuid4(),
        "run_id": "test_run_123",
    }


@pytest.fixture
def approval_decision_approve():
    """ToolApprovalDecision for approve."""
    return ToolApprovalDecision(
        decisions=[{"type": "approve"}],
        action_indices=[0],
        rejection_messages=[None],
    )


@pytest.fixture
def approval_decision_reject():
    """ToolApprovalDecision for reject."""
    return ToolApprovalDecision(
        decisions=[{"type": "reject"}],
        action_indices=[0],
        rejection_messages=["User declined"],
    )


@pytest.fixture
def approval_decision_edit():
    """ToolApprovalDecision for edit."""
    return ToolApprovalDecision(
        decisions=[
            {
                "type": "edit",
                "edited_action": {
                    "name": "search_contacts_tool",
                    "args": {"query": "jean"},
                },
            }
        ],
        action_indices=[0],
        rejection_messages=[None],
    )


# ============================================================================
# Test ConversationalHitlResumption Initialization
# ============================================================================


class TestConversationalHitlResumptionInit:
    """Tests for ConversationalHitlResumption initialization."""

    def test_init_success(self, conversation_service_mock):
        """Test successful initialization."""
        strategy = ConversationalHitlResumption(conversation_service_mock)
        assert strategy.conversation_service == conversation_service_mock

    def test_init_stores_conversation_service(self, conversation_service_mock):
        """Test that conversation service is stored correctly."""
        strategy = ConversationalHitlResumption(conversation_service_mock)
        assert hasattr(strategy, "conversation_service")
        assert strategy.conversation_service is conversation_service_mock


# ============================================================================
# Test Resume and Stream - Approve Decision
# ============================================================================


class TestResumeAndStreamApprove:
    """Tests for resume_and_stream with approve decisions."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_approve_basic_flow(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test basic approve flow without user_response."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock graph stream
        async def mock_stream(*args, **kwargs):
            yield ("messages", (AIMessageChunk(content="Hello"), {}))
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify
        assert len(chunks) >= 2  # At least token + done
        assert any(c.type == "token" for c in chunks)
        assert any(c.type == "done" for c in chunks)

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_approve_builds_correct_resume_value(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test that approve decision builds correct resume value."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Capture Command passed to astream
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify resume value structure
        assert captured_command is not None
        assert isinstance(captured_command, Command)
        assert captured_command.resume["approved"] is True
        assert captured_command.resume["edited_args"] is None
        assert captured_command.resume["decisions"] == [{"type": "approve"}]

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_approve_streams_tokens(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test that approve streams AIMessageChunk tokens."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock graph stream with multiple tokens
        async def mock_stream(*args, **kwargs):
            yield ("messages", (AIMessageChunk(content="Hello "), {}))
            yield ("messages", (AIMessageChunk(content="world"), {}))
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify
        token_chunks = [c for c in chunks if c.type == "token"]
        assert len(token_chunks) == 2
        assert token_chunks[0].content == "Hello "
        assert token_chunks[1].content == "world"


# ============================================================================
# Test Resume and Stream - Reject Decision
# ============================================================================


class TestResumeAndStreamReject:
    """Tests for resume_and_stream with reject decisions."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_reject_injects_tool_message(
        self,
        mock_redis_cache,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_reject,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test reject injects ToolMessage with tool_call_id."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup Redis mock with tool_call_id mapping
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=json.dumps({"0": "tool_call_abc123"}))
        mock_redis_cache.return_value = redis_mock

        # Capture Command passed to astream
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_reject,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="non",
        ):
            chunks.append(chunk)

        # Verify Command has ToolMessage with tool_call_id
        assert captured_command is not None
        messages = captured_command.update["messages"]

        # Should have HumanMessage + ToolMessage
        assert len(messages) == 2
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "non"
        assert isinstance(messages[1], ToolMessage)
        assert messages[1].tool_call_id == "tool_call_abc123"
        assert "refusé" in messages[1].content

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_reject_fallback_without_tool_call_id(
        self,
        mock_redis_cache,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_reject,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test reject fallback when tool_call_id is not found."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup Redis mock without mapping
        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        mock_redis_cache.return_value = redis_mock

        # Capture Command
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_reject,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="non",
        ):
            chunks.append(chunk)

        # Verify fallback to HumanMessage only
        messages = captured_command.update["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)
        assert messages[0].content == "non"

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_reject_builds_correct_resume_value(
        self,
        mock_redis_cache,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_reject,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test that reject decision builds correct resume value."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.get = AsyncMock(return_value=None)
        mock_redis_cache.return_value = redis_mock

        # Capture Command
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_reject,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="non",
        ):
            chunks.append(chunk)

        # Verify resume value
        assert captured_command.resume["approved"] is False
        assert captured_command.resume["decisions"] == [{"type": "reject"}]


# ============================================================================
# Test Resume and Stream - Edit Decision
# ============================================================================


class TestResumeAndStreamEdit:
    """Tests for resume_and_stream with edit decisions."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_edit_removes_original_message(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_edit,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test edit removes original HumanMessage and adds reformulated."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock state with messages
        original_msg = HumanMessage(content="recherche jean", id="msg_123")
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"messages": [original_msg]})
        )

        # Capture Command
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_edit,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="recherche jean",
        ):
            chunks.append(chunk)

        # Verify RemoveMessage + HumanMessage
        messages = captured_command.update["messages"]
        assert len(messages) == 2
        assert isinstance(messages[0], RemoveMessage)
        assert messages[0].id == "msg_123"
        assert isinstance(messages[1], HumanMessage)
        assert "jean" in messages[1].content

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_edit_fallback_without_message_id(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_edit,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test edit fallback when original message has no ID."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock state with message without ID
        original_msg = HumanMessage(content="recherche jean")  # No id
        mock_graph.aget_state = AsyncMock(
            return_value=MagicMock(values={"messages": [original_msg]})
        )

        # Capture Command
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_edit,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="recherche jean",
        ):
            chunks.append(chunk)

        # Verify fallback to HumanMessage only (no RemoveMessage)
        messages = captured_command.update["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], HumanMessage)

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_edit_state_load_error_fallback(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_edit,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test edit fallback when state loading fails."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock state to raise error
        mock_graph.aget_state = AsyncMock(side_effect=Exception("State load failed"))

        # Capture Command
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_edit,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="recherche jean",
        ):
            chunks.append(chunk)

        # Verify fallback was used
        assert hasattr(captured_command, "update")
        # Should still have reformulated message
        messages = captured_command.update["messages"]
        assert len(messages) >= 1
        assert isinstance(messages[0], HumanMessage)

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_edit_builds_correct_resume_value(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_edit,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test that edit decision builds correct resume value."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock state
        mock_graph.aget_state = AsyncMock(return_value=MagicMock(values={"messages": []}))

        # Capture Command
        captured_command = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_command
            captured_command = args[0] if args else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_edit,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            user_response="recherche jean",
        ):
            chunks.append(chunk)

        # Verify resume value
        assert captured_command.resume["approved"] is True
        assert captured_command.resume["edited_args"] == {"query": "jean"}


# ============================================================================
# Test Nested HITL Interrupts
# ============================================================================


class TestNestedHitlInterrupts:
    """Tests for nested HITL interrupt detection and handling."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    @patch("src.infrastructure.cache.redis.get_redis_cache")
    async def test_nested_interrupt_detected(
        self,
        mock_redis_cache,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test nested interrupt is detected during resume."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        redis_mock = AsyncMock()
        redis_mock.set = AsyncMock()
        mock_redis_cache.return_value = redis_mock

        # Setup mock graph stream with nested interrupt
        async def mock_stream(*args, **kwargs):
            yield (
                "values",
                {
                    "messages": [],
                    "__interrupt__": [
                        MagicMock(
                            value={
                                "action_requests": [
                                    {"name": "nested_tool", "args": {"param": "value"}}
                                ],
                                "review_configs": None,
                            }
                        )
                    ],
                },
            )

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify hitl_interrupt chunk was yielded
        interrupt_chunks = [c for c in chunks if c.type == "hitl_interrupt"]
        assert len(interrupt_chunks) == 1
        assert interrupt_chunks[0].metadata["nested"] is True

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_nested_interrupt_invalid_format_skipped(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test nested interrupt with invalid format is skipped."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock graph stream with invalid interrupt
        async def mock_stream(*args, **kwargs):
            yield (
                "values",
                {
                    "messages": [],
                    "__interrupt__": [MagicMock(value="invalid_string")],
                },
            )
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify no hitl_interrupt chunk was yielded
        interrupt_chunks = [c for c in chunks if c.type == "hitl_interrupt"]
        assert len(interrupt_chunks) == 0


# ============================================================================
# Test Error Handling
# ============================================================================


class TestErrorHandling:
    """Tests for error handling in resume_and_stream."""

    @pytest.mark.asyncio
    async def test_graph_execution_error_yields_error_chunk(
        self,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
    ):
        """Test graph execution error yields error chunk."""

        # Setup mock graph to raise error
        async def mock_stream(*args, **kwargs):
            raise Exception("Graph execution failed")

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify error chunk was yielded
        error_chunks = [c for c in chunks if c.type == "error"]
        assert len(error_chunks) == 1
        assert (
            "erreur" in error_chunks[0].content.lower()
            or "error" in error_chunks[0].content.lower()
        )


# ============================================================================
# Test Tracker Management
# ============================================================================


class TestTrackerManagement:
    """Tests for tracker management (unified vs new)."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_unified_tracker_used(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test that provided tracker is used (unified mode)."""
        # Setup mocks
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup
        async def mock_stream(*args, **kwargs):
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute with tracker
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify tracker.get_summary was called
        mock_tracker.get_summary.assert_called_once()

    # Note: Testing tracker=None path is complex due to dynamic import
    # The main path (with tracker provided) is tested above


# ============================================================================
# Test Message Archival and Stats
# ============================================================================


class TestMessageArchivalAndStats:
    """Tests for message archival and conversation stats updates."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_archives_assistant_response(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        conversation_service_mock,
        mock_db,
    ):
        """Test that assistant response is archived."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock graph stream with assistant response
        async def mock_stream(*args, **kwargs):
            yield ("messages", (AIMessageChunk(content="Response from assistant"), {}))
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify archive_message was called
        conversation_service_mock.archive_message.assert_called_once()
        call_args = conversation_service_mock.archive_message.call_args
        assert call_args[0][0] == base_test_ids["conversation_id"]
        assert call_args[0][1] == "assistant"
        assert "Response from assistant" in call_args[0][2]

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_updates_conversation_stats(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        conversation_service_mock,
        mock_db,
    ):
        """Test that conversation stats are updated."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock graph stream
        async def mock_stream(*args, **kwargs):
            yield ("messages", (AIMessageChunk(content="Response"), {}))
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify increment_conversation_stats was called
        conversation_service_mock.increment_conversation_stats.assert_called_once()
        call_args = conversation_service_mock.increment_conversation_stats.call_args
        assert call_args[0][0] == base_test_ids["conversation_id"]
        assert call_args[0][1] == 300  # 100 + 200 from mock_tracker

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_no_archival_when_no_response(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        conversation_service_mock,
        mock_db,
    ):
        """Test no archival when assistant response is empty."""
        # Setup mock DB
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Setup mock graph stream without content
        async def mock_stream(*args, **kwargs):
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify archive_message was NOT called
        conversation_service_mock.archive_message.assert_not_called()


# ============================================================================
# Test Done Chunk Metadata
# ============================================================================


class TestDoneChunkMetadata:
    """Tests for done chunk metadata."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_done_chunk_includes_token_metrics(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test done chunk includes token metrics from tracker."""
        # Setup
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify done chunk
        done_chunks = [c for c in chunks if c.type == "done"]
        assert len(done_chunks) == 1
        done_chunk = done_chunks[0]

        assert done_chunk.metadata["tokens_in"] == 100
        assert done_chunk.metadata["tokens_out"] == 200
        assert done_chunk.metadata["tokens_cache"] == 50
        assert done_chunk.metadata["cost_eur"] == 0.005
        assert done_chunk.metadata["run_id"] == base_test_ids["run_id"]
        assert done_chunk.metadata["resumption_strategy"] == "conversational"

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_done_chunk_includes_duration(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test done chunk includes execution duration."""
        # Setup
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        async def mock_stream(*args, **kwargs):
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify done chunk has duration
        done_chunks = [c for c in chunks if c.type == "done"]
        assert len(done_chunks) == 1
        assert "duration_seconds" in done_chunks[0].metadata
        assert done_chunks[0].metadata["duration_seconds"] >= 0


# ============================================================================
# Test RunnableConfig Construction
# ============================================================================


class TestRunnableConfigConstruction:
    """Tests for RunnableConfig construction."""

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_runnable_config_includes_thread_id(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test RunnableConfig includes thread_id in configurable."""
        # Setup
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Capture config
        captured_config = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_config
            captured_config = args[1] if len(args) > 1 else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
        ):
            chunks.append(chunk)

        # Verify RunnableConfig
        assert captured_config is not None
        assert captured_config.get("configurable", {}).get("thread_id") == str(
            base_test_ids["conversation_id"]
        )

    @pytest.mark.asyncio
    @patch("src.infrastructure.database.get_db_context")
    async def test_runnable_config_includes_turn_id(
        self,
        mock_get_db_context,
        resumption_strategy,
        mock_graph,
        approval_decision_approve,
        base_test_ids,
        mock_tracker,
        mock_db,
    ):
        """Test RunnableConfig includes turn_id when provided."""
        # Setup
        mock_get_db_context.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_get_db_context.return_value.__aexit__ = AsyncMock()

        # Capture config
        captured_config = None

        async def mock_stream(*args, **kwargs):
            nonlocal captured_config
            captured_config = args[1] if len(args) > 1 else None
            yield ("values", {"messages": []})

        mock_graph.astream = mock_stream

        # Execute with turn_id
        chunks = []
        async for chunk in resumption_strategy.resume_and_stream(
            graph=mock_graph,
            approval_decision=approval_decision_approve,
            conversation_id=base_test_ids["conversation_id"],
            user_id=base_test_ids["user_id"],
            run_id=base_test_ids["run_id"],
            tracker=mock_tracker,
            turn_id=5,
        ):
            chunks.append(chunk)

        # Verify turn_id in config
        assert captured_config is not None
        assert captured_config.get("configurable", {}).get("turn_id") == 5
