"""
Tests for Draft Executor Service (LARS LOT 5.4 / LOT 7).

Tests cover:
- execute_draft_if_confirmed() routing (confirm/edit/cancel)
- _execute_confirmed_draft() with ToolDependencies injection
- DraftExecutionResult creation and formatting
- Executor registry pattern (register_executor, _ensure_executors_registered)
- Prometheus metrics tracking (registry_drafts_executed_total)
- Error handling and graceful degradation

Architecture:
    draft_critique_node → state["draft_action_result"] = {action: "confirm", ...}
    → response_node → execute_draft_if_confirmed()
    → draft_executor → _EXECUTOR_REGISTRY[draft_type]
    → execute_*_draft() → API call → DraftExecutionResult

Created: 2025-11-26
LARS LOT 7: Tests E2E
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

# Skip all tests if OPENAI_API_KEY is not set (integration tests that call real LLM)
pytestmark = pytest.mark.skipif(
    not os.getenv("OPENAI_API_KEY"),
    reason="Requires OPENAI_API_KEY for integration tests with real LLM",
)
from langchain_core.runnables import RunnableConfig  # noqa: E402

from src.domains.agents.services.draft_executor import (  # noqa: E402
    DraftExecutionResult,
    _ensure_executors_registered,
    execute_draft_if_confirmed,
    register_executor,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_tool_dependencies():
    """Mock ToolDependencies for draft execution."""
    deps = MagicMock()
    deps.get_connector_service = AsyncMock()
    return deps


@pytest.fixture
def mock_config_with_deps(mock_tool_dependencies) -> RunnableConfig:
    """Create RunnableConfig with ToolDependencies and user_id."""
    user_id = str(uuid4())
    return RunnableConfig(
        configurable={
            "__deps": mock_tool_dependencies,
        },
        metadata={
            "user_id": user_id,
            "conversation_id": str(uuid4()),
        },
    )


@pytest.fixture
def mock_config_without_deps() -> RunnableConfig:
    """Create RunnableConfig without ToolDependencies (error case)."""
    return RunnableConfig(
        configurable={},
        metadata={
            "user_id": str(uuid4()),
        },
    )


@pytest.fixture
def mock_config_without_user_id(mock_tool_dependencies) -> RunnableConfig:
    """Create RunnableConfig without user_id (error case)."""
    return RunnableConfig(
        configurable={
            "__deps": mock_tool_dependencies,
        },
        metadata={},
    )


@pytest.fixture
def email_draft_action_confirm():
    """Sample email draft action result for confirm."""
    return {
        "action": "confirm",
        "draft_id": "draft_email_123",
        "draft_type": "email",
        "draft_content": {
            "to": "jean@example.com",
            "subject": "Test Subject",
            "body": "Test body content",
            "cc": None,
            "bcc": None,
        },
    }


@pytest.fixture
def event_draft_action_confirm():
    """Sample event draft action result for confirm."""
    return {
        "action": "confirm",
        "draft_id": "draft_event_456",
        "draft_type": "event",
        "draft_content": {
            "summary": "Team Meeting",
            "start_datetime": "2025-11-27T10:00:00",
            "end_datetime": "2025-11-27T11:00:00",
            "timezone": "Europe/Paris",
        },
    }


@pytest.fixture
def contact_draft_action_confirm():
    """Sample contact draft action result for confirm."""
    return {
        "action": "confirm",
        "draft_id": "draft_contact_789",
        "draft_type": "contact",
        "draft_content": {
            "name": "Jean Dupont",
            "email": "jean@example.com",
            "phone": "+33612345678",
        },
    }


@pytest.fixture
def draft_action_cancel():
    """Sample draft action result for cancel."""
    return {
        "action": "cancel",
        "draft_id": "draft_email_123",
        "draft_type": "email",
        "reason": "User cancelled",
    }


@pytest.fixture
def draft_action_edit():
    """Sample draft action result for edit."""
    return {
        "action": "edit",
        "draft_id": "draft_email_123",
        "draft_type": "email",
        "updated_content": {
            "to": "jean@example.com",
            "subject": "Updated Subject",
            "body": "Updated body",
        },
    }


# ============================================================================
# DraftExecutionResult Tests
# ============================================================================


class TestDraftExecutionResult:
    """Tests for DraftExecutionResult dataclass."""

    def test_success_result_to_dict(self):
        """Test converting success result to dict."""
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_123",
            draft_type="email",
            action="confirm",
            result_data={"message_id": "msg_abc"},
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is True
        assert result_dict["draft_id"] == "draft_123"
        assert result_dict["draft_type"] == "email"
        assert result_dict["action"] == "confirm"
        assert result_dict["result_data"]["message_id"] == "msg_abc"
        assert result_dict["error"] is None

    def test_error_result_to_dict(self):
        """Test converting error result to dict."""
        result = DraftExecutionResult(
            success=False,
            draft_id="draft_123",
            draft_type="email",
            action="confirm",
            error="Gmail API error",
        )

        result_dict = result.to_dict()

        assert result_dict["success"] is False
        assert result_dict["error"] == "Gmail API error"

    def test_to_agent_result_success_email(self):
        """Test agent result format for successful email execution."""
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_123",
            draft_type="email",
            action="confirm",
            result_data={"message_id": "msg_abc"},
        )

        agent_result = result.to_agent_result()

        assert agent_result["status"] == "success"
        assert "Email envoyé" in agent_result["message"]
        assert agent_result["draft_id"] == "draft_123"
        assert agent_result["action"] == "confirm"

    def test_to_agent_result_success_event(self):
        """Test agent result format for successful event creation."""
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_456",
            draft_type="event",
            action="confirm",
            result_data={"summary": "Team Meeting"},
        )

        agent_result = result.to_agent_result()

        assert agent_result["status"] == "success"
        assert "Événement" in agent_result["message"]
        assert "Team Meeting" in agent_result["message"]

    def test_to_agent_result_success_contact(self):
        """Test agent result format for successful contact creation."""
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_789",
            draft_type="contact",
            action="confirm",
            result_data={"name": "Jean Dupont"},
        )

        agent_result = result.to_agent_result()

        assert agent_result["status"] == "success"
        assert "Contact" in agent_result["message"]
        assert "Jean Dupont" in agent_result["message"]

    def test_to_agent_result_cancelled(self):
        """Test agent result format for cancelled draft."""
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_123",
            draft_type="email",
            action="cancel",
        )

        agent_result = result.to_agent_result()

        assert agent_result["status"] == "cancelled"
        assert "annulé" in agent_result["message"]

    def test_to_agent_result_error(self):
        """Test agent result format for error."""
        result = DraftExecutionResult(
            success=False,
            draft_id="draft_123",
            draft_type="email",
            action="confirm",
            error="Connection timeout",
        )

        agent_result = result.to_agent_result()

        assert agent_result["status"] == "error"
        assert agent_result["message"] == "Connection timeout"


# ============================================================================
# execute_draft_if_confirmed Tests - Routing Logic
# ============================================================================


class TestExecuteDraftIfConfirmedRouting:
    """Tests for execute_draft_if_confirmed() routing logic."""

    @pytest.mark.asyncio
    async def test_returns_none_if_no_draft_action_result(self, mock_config_with_deps):
        """Test that None is returned when draft_action_result is None."""
        result = await execute_draft_if_confirmed(None, mock_config_with_deps, "run_123")
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_if_empty_draft_action_result(self, mock_config_with_deps):
        """Test that None is returned when draft_action_result is empty dict."""
        result = await execute_draft_if_confirmed({}, mock_config_with_deps, "run_123")
        # Empty dict has no action, should return None
        assert result is None

    @pytest.mark.asyncio
    async def test_cancel_action_returns_cancelled_result(
        self, draft_action_cancel, mock_config_with_deps
    ):
        """Test that cancel action returns cancelled result without execution."""
        with patch(
            "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
        ) as mock_metric:
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                draft_action_cancel, mock_config_with_deps, "run_123"
            )

            assert result is not None
            assert result.action == "cancel"
            assert result.success is True
            assert result.draft_type == "email"
            mock_metric.labels.assert_called_with(draft_type="email", outcome="cancelled")

    @pytest.mark.asyncio
    async def test_edit_action_returns_edit_result(self, draft_action_edit, mock_config_with_deps):
        """Test that edit action returns edit result with needs_reconfirmation."""
        result = await execute_draft_if_confirmed(
            draft_action_edit, mock_config_with_deps, "run_123"
        )

        assert result is not None
        assert result.action == "edit"
        assert result.success is True
        assert result.result_data["needs_reconfirmation"] is True

    @pytest.mark.asyncio
    async def test_unknown_action_returns_none(self, mock_config_with_deps):
        """Test that unknown action returns None."""
        draft_action = {
            "action": "unknown_action",
            "draft_id": "draft_123",
            "draft_type": "email",
        }

        result = await execute_draft_if_confirmed(draft_action, mock_config_with_deps, "run_123")

        assert result is None


# ============================================================================
# execute_draft_if_confirmed Tests - Confirm Action Execution
# ============================================================================


class TestExecuteDraftIfConfirmedExecution:
    """Tests for execute_draft_if_confirmed() confirm action execution."""

    @pytest.mark.asyncio
    async def test_confirm_email_draft_success(
        self, email_draft_action_confirm, mock_config_with_deps
    ):
        """Test successful email draft execution."""
        # Mock the execute_email_draft function
        mock_execute_result = {
            "success": True,
            "message_id": "msg_abc123",
            "thread_id": "thread_xyz",
        }

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": AsyncMock(return_value=mock_execute_result)},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            assert result is not None
            assert result.success is True
            assert result.action == "confirm"
            assert result.draft_type == "email"
            assert result.result_data["message_id"] == "msg_abc123"
            mock_metric.labels.assert_called_with(draft_type="email", outcome="success")

    @pytest.mark.asyncio
    async def test_confirm_event_draft_success(
        self, event_draft_action_confirm, mock_config_with_deps
    ):
        """Test successful event draft execution."""
        mock_execute_result = {
            "success": True,
            "event_id": "evt_abc123",
            "summary": "Team Meeting",
        }

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"event": AsyncMock(return_value=mock_execute_result)},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                event_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            assert result is not None
            assert result.success is True
            assert result.draft_type == "event"

    @pytest.mark.asyncio
    async def test_confirm_contact_draft_success(
        self, contact_draft_action_confirm, mock_config_with_deps
    ):
        """Test successful contact draft execution."""
        mock_execute_result = {
            "success": True,
            "resource_name": "people/c123456",
            "name": "Jean Dupont",
        }

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"contact": AsyncMock(return_value=mock_execute_result)},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                contact_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            assert result is not None
            assert result.success is True
            assert result.draft_type == "contact"


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestDraftExecutorErrorHandling:
    """Tests for draft executor error handling."""

    @pytest.mark.asyncio
    async def test_missing_deps_returns_error_result(
        self, email_draft_action_confirm, mock_config_without_deps
    ):
        """Test that missing ToolDependencies returns error result."""
        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": AsyncMock()},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_without_deps, "run_123"
            )

            assert result is not None
            assert result.success is False
            assert "ToolDependencies not found" in result.error
            mock_metric.labels.assert_called_with(draft_type="email", outcome="failed")

    @pytest.mark.asyncio
    async def test_missing_user_id_returns_error_result(
        self, email_draft_action_confirm, mock_config_without_user_id
    ):
        """Test that missing user_id returns error result."""
        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": AsyncMock()},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_without_user_id, "run_123"
            )

            assert result is not None
            assert result.success is False
            assert "user_id not found" in result.error

    @pytest.mark.asyncio
    async def test_unknown_draft_type_returns_error_result(self, mock_config_with_deps):
        """Test that unknown draft type returns error result."""
        draft_action = {
            "action": "confirm",
            "draft_id": "draft_123",
            "draft_type": "unknown_type",
            "draft_content": {},
        }

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {},  # Empty registry - no executor for unknown_type
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                draft_action, mock_config_with_deps, "run_123"
            )

            assert result is not None
            assert result.success is False
            assert "No executor registered" in result.error

    @pytest.mark.asyncio
    async def test_executor_exception_returns_error_result(
        self, email_draft_action_confirm, mock_config_with_deps
    ):
        """Test that executor exception is caught and returns error result."""
        mock_executor = AsyncMock(side_effect=Exception("Gmail API timeout"))

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": mock_executor},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            assert result is not None
            assert result.success is False
            assert "Gmail API timeout" in result.error
            mock_metric.labels.assert_called_with(draft_type="email", outcome="failed")


# ============================================================================
# Executor Registry Tests
# ============================================================================


class TestExecutorRegistry:
    """Tests for executor registry pattern."""

    def test_register_executor_adds_to_registry(self):
        """Test that register_executor adds function to registry."""
        from src.domains.agents.services import draft_executor

        # Save original registry
        original_registry = draft_executor._EXECUTOR_REGISTRY.copy()

        try:
            # Register a test executor
            async def test_executor(content, user_id, deps):
                return {"test": True}

            register_executor("test_type", test_executor)

            assert "test_type" in draft_executor._EXECUTOR_REGISTRY
            assert draft_executor._EXECUTOR_REGISTRY["test_type"] is test_executor
        finally:
            # Restore original registry
            draft_executor._EXECUTOR_REGISTRY = original_registry

    def test_ensure_executors_registered_populates_registry(self):
        """Test that _ensure_executors_registered populates the registry."""
        from src.domains.agents.services import draft_executor

        # Clear and re-populate
        original_registry = draft_executor._EXECUTOR_REGISTRY.copy()

        try:
            draft_executor._EXECUTOR_REGISTRY = {}
            _ensure_executors_registered()

            # Should have email, event, contact executors
            assert "email" in draft_executor._EXECUTOR_REGISTRY
            assert "event" in draft_executor._EXECUTOR_REGISTRY
            assert "contact" in draft_executor._EXECUTOR_REGISTRY
        finally:
            draft_executor._EXECUTOR_REGISTRY = original_registry

    def test_ensure_executors_registered_is_idempotent(self):
        """Test that calling _ensure_executors_registered twice is safe."""
        from src.domains.agents.services import draft_executor

        original_registry = draft_executor._EXECUTOR_REGISTRY.copy()

        try:
            draft_executor._EXECUTOR_REGISTRY = {}
            _ensure_executors_registered()
            first_call_keys = set(draft_executor._EXECUTOR_REGISTRY.keys())

            # Second call should not modify registry
            _ensure_executors_registered()
            second_call_keys = set(draft_executor._EXECUTOR_REGISTRY.keys())

            assert first_call_keys == second_call_keys
        finally:
            draft_executor._EXECUTOR_REGISTRY = original_registry


# ============================================================================
# Prometheus Metrics Tests
# ============================================================================


class TestDraftExecutorMetrics:
    """Tests for Prometheus metrics tracking."""

    @pytest.mark.asyncio
    async def test_success_increments_success_metric(
        self, email_draft_action_confirm, mock_config_with_deps
    ):
        """Test that success increments success metric."""
        mock_execute_result = {"success": True, "message_id": "msg_123"}

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": AsyncMock(return_value=mock_execute_result)},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_inc = MagicMock()
            mock_metric.labels.return_value.inc = mock_inc

            await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            mock_metric.labels.assert_called_with(draft_type="email", outcome="success")
            mock_inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_increments_cancelled_metric(
        self, draft_action_cancel, mock_config_with_deps
    ):
        """Test that cancel increments cancelled metric."""
        with patch(
            "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
        ) as mock_metric:
            mock_inc = MagicMock()
            mock_metric.labels.return_value.inc = mock_inc

            await execute_draft_if_confirmed(draft_action_cancel, mock_config_with_deps, "run_123")

            mock_metric.labels.assert_called_with(draft_type="email", outcome="cancelled")
            mock_inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_failure_increments_failed_metric(
        self, email_draft_action_confirm, mock_config_with_deps
    ):
        """Test that failure increments failed metric."""
        mock_executor = AsyncMock(side_effect=Exception("API Error"))

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": mock_executor},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_inc = MagicMock()
            mock_metric.labels.return_value.inc = mock_inc

            await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            mock_metric.labels.assert_called_with(draft_type="email", outcome="failed")
            mock_inc.assert_called_once()


# ============================================================================
# Integration with response_node Pattern Tests
# ============================================================================


class TestResponseNodeIntegrationPattern:
    """Tests for integration patterns with response_node."""

    @pytest.mark.asyncio
    async def test_result_to_agent_result_usable_by_response_node(
        self, email_draft_action_confirm, mock_config_with_deps
    ):
        """Test that result.to_agent_result() returns format usable by response_node."""
        mock_execute_result = {"success": True, "message_id": "msg_abc"}

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": AsyncMock(return_value=mock_execute_result)},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(
                email_draft_action_confirm, mock_config_with_deps, "run_123"
            )

            agent_result = result.to_agent_result()

            # response_node expects these fields
            assert "status" in agent_result
            assert "message" in agent_result
            assert "draft_id" in agent_result
            assert "draft_type" in agent_result
            assert "action" in agent_result

    @pytest.mark.asyncio
    async def test_handles_uuid_string_user_id(
        self, email_draft_action_confirm, mock_tool_dependencies
    ):
        """Test that string UUID user_id is properly converted."""
        user_id_str = "550e8400-e29b-41d4-a716-446655440000"
        config = RunnableConfig(
            configurable={"__deps": mock_tool_dependencies},
            metadata={"user_id": user_id_str},
        )

        mock_execute = AsyncMock(return_value={"success": True})

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": mock_execute},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(email_draft_action_confirm, config, "run_123")

            assert result.success is True
            # Verify executor was called with UUID (not string)
            call_args = mock_execute.call_args
            user_id_arg = call_args[0][1]  # Second positional arg
            assert isinstance(user_id_arg, UUID)

    @pytest.mark.asyncio
    async def test_handles_uuid_object_user_id(
        self, email_draft_action_confirm, mock_tool_dependencies
    ):
        """Test that UUID object user_id is properly handled."""
        user_id = uuid4()
        config = RunnableConfig(
            configurable={"__deps": mock_tool_dependencies},
            metadata={"user_id": user_id},
        )

        mock_execute = AsyncMock(return_value={"success": True})

        with (
            patch(
                "src.domains.agents.services.draft_executor._EXECUTOR_REGISTRY",
                {"email": mock_execute},
            ),
            patch(
                "src.domains.agents.services.draft_executor.registry_drafts_executed_total"
            ) as mock_metric,
        ):
            mock_metric.labels.return_value.inc = MagicMock()

            result = await execute_draft_if_confirmed(email_draft_action_confirm, config, "run_123")

            assert result.success is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
