"""
Tests for Draft Executor Service (LARS LOT 5.4 / LOT 7).

Tests cover:
- execute_draft_if_confirmed() routing (confirm/edit/cancel)
- _execute_confirmed_draft() with ToolDependencies injection
- DraftExecutionResult creation and formatting
- Executor registry pattern (register_executor, ensure_executors_registered)
- Prometheus metrics tracking (registry_drafts_executed_total)
- Error handling and graceful degradation

Architecture:
    draft_critique_node → state["draft_action_result"] = {action: "confirm", ...}
    → response_node → execute_draft_if_confirmed()
    → draft_executor → EXECUTOR_REGISTRY[draft_type]
    → execute_*_draft() → API call → DraftExecutionResult

Created: 2025-11-26
LARS LOT 7: Tests E2E
"""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.unit
from langchain_core.runnables import RunnableConfig  # noqa: E402

from src.core.i18n_drafts import (  # noqa: E402
    get_draft_cancel_message,
    get_draft_success_message,
)
from src.domains.agents.services.draft_executor import (  # noqa: E402
    EXECUTOR_REGISTRY,
    DraftExecutionResult,
    ensure_executors_registered,
    execute_draft_if_confirmed,
    register_executor,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(autouse=True)
def no_tcm_session():
    """Keep the suite hermetic: no TCM session, therefore no database socket.

    After a confirmed draft, the engine mirrors the result into the Tool Context
    Manager. Acquiring that session opens the LangGraph Postgres store, which in
    a unit environment means a real connection attempt that only fails on the
    5-second connect timeout — measured 41 s for this file, all of it waiting on
    a socket a unit test must never open. `get_tcm_session` returns None when the
    store is unavailable and the engine treats that as "skip the mirror", so
    returning None here reproduces the production contract exactly.

    The mirroring itself is covered by
    ``tests/unit/domains/agents/services/test_draft_executor_tcm_sync.py``.
    """
    with patch(
        "src.domains.agents.services.draft_executor.get_tcm_session",
        AsyncMock(return_value=None),
    ):
        yield


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
        """Test agent result format for successful email execution.

        The oracle is the i18n table, not a literal: the wording is product copy
        that may be reworded (it lost its type prefix — "Envoyé avec succès", no
        longer "Email envoyé"), while what must hold is that the message comes
        from the entry for THIS draft type.
        """
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_123",
            draft_type="email",
            action="confirm",
            result_data={"message_id": "msg_abc"},
        )

        agent_result = result.to_agent_result()

        assert agent_result["status"] == "success"
        assert agent_result["message"] == get_draft_success_message("email", "fr")
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
        assert agent_result["message"] == get_draft_success_message(
            "event", "fr", summary="Team Meeting"
        )
        # The placeholder was actually substituted, not left as "{summary}".
        assert "Team Meeting" in agent_result["message"]
        assert "{" not in agent_result["message"]

    def test_to_agent_result_honours_the_user_language(self):
        """A non-French user must not receive the French copy.

        `user_language` is threaded from the graph state down to this result;
        a default that silently wins would ship French to every user.
        """
        result = DraftExecutionResult(
            success=True,
            draft_id="draft_456",
            draft_type="event",
            action="confirm",
            result_data={"summary": "Team Meeting"},
            user_language="de",
        )

        message = result.to_agent_result()["message"]

        assert message == get_draft_success_message("event", "de", summary="Team Meeting")
        assert message != get_draft_success_message("event", "fr", summary="Team Meeting")
        assert "Team Meeting" in message

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
        assert agent_result["message"] == get_draft_success_message(
            "contact", "fr", name="Jean Dupont"
        )
        assert "Jean Dupont" in agent_result["message"]
        assert "{" not in agent_result["message"]

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
        assert agent_result["message"] == get_draft_cancel_message("email", "fr")

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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
    """Tests for executor registry pattern.

    The registry is ONE dict object shared by three modules (`draft_executor`,
    `draft_executor_types`, `draft_executor_registry`). It must therefore be
    mutated in place — `EXECUTOR_REGISTRY = {}` rebinds this module's name only,
    leaves the object every other module holds untouched, and the assertions
    then read an empty dict the code under test never sees. That is exactly how
    these tests used to "pass" while asserting nothing.
    """

    @pytest.fixture(autouse=True)
    def restore_registry(self):
        """Snapshot and restore the shared registry around each test."""
        original = EXECUTOR_REGISTRY.copy()
        yield
        EXECUTOR_REGISTRY.clear()
        EXECUTOR_REGISTRY.update(original)

    def test_register_executor_adds_to_registry(self):
        """Test that register_executor adds function to registry."""

        async def test_executor(content, user_id, deps):
            return {"test": True}

        register_executor("test_type", test_executor)

        assert EXECUTOR_REGISTRY["test_type"] is test_executor

    def test_ensure_executors_registered_populates_registry(self):
        """Test that ensure_executors_registered populates the registry."""
        EXECUTOR_REGISTRY.clear()
        ensure_executors_registered()

        # Should have email, event, contact executors
        assert "email" in EXECUTOR_REGISTRY
        assert "event" in EXECUTOR_REGISTRY
        assert "contact" in EXECUTOR_REGISTRY

    def test_ensure_executors_registered_is_idempotent(self):
        """Test that calling ensure_executors_registered twice is safe."""
        EXECUTOR_REGISTRY.clear()
        ensure_executors_registered()
        first_call_keys = set(EXECUTOR_REGISTRY)

        # Second call short-circuits on the non-empty registry.
        ensure_executors_registered()

        assert set(EXECUTOR_REGISTRY) == first_call_keys

    def test_registry_is_the_object_the_engine_reads(self):
        """Guard: one registry object, reachable under one name per module.

        A back-compat alias in `draft_executor` used to shadow this: patching it
        rebound the alias while `_execute_confirmed_draft` read
        `EXECUTOR_REGISTRY`, so eleven tests silently ran the REAL executors.
        """
        from src.domains.agents.services import (
            draft_executor,
            draft_executor_registry,
            draft_executor_types,
        )

        assert draft_executor.EXECUTOR_REGISTRY is draft_executor_types.EXECUTOR_REGISTRY
        assert draft_executor_registry.EXECUTOR_REGISTRY is draft_executor_types.EXECUTOR_REGISTRY
        assert not hasattr(
            draft_executor, "_EXECUTOR_REGISTRY"
        ), "the aliased name is back — patching it is a silent no-op"


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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
                "src.domains.agents.services.draft_executor.EXECUTOR_REGISTRY",
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
