"""Unit tests for the scheduled action executor.

Focus: the executor must mark its agent run as an automated source so that
response_node skips long-term memory / interest / journal / psyche extraction.
This is the entry-point half of the ``is_automated_source`` redesign — the
guard itself is covered by ``tests/agents/test_response_node.py``.
"""

import uuid
from contextlib import ExitStack
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.infrastructure.scheduler.scheduled_action_executor import execute_single_action


class _AsyncCM:
    """Minimal async context manager yielding a fixed value (mocks get_db_context)."""

    def __init__(self, value):
        self._value = value

    async def __aenter__(self):
        return self._value

    async def __aexit__(self, *exc_info):
        return False


async def _fake_stream(*_args, **_kwargs):
    """Stand-in for AgentService.stream_chat_response — yields one token chunk."""
    yield SimpleNamespace(type="token", content="hello")


@pytest.mark.asyncio
async def test_execute_single_action_marks_run_as_automated_source():
    """execute_single_action must call stream_chat_response(is_automated_source=True).

    This guarantees scheduled-action runs are flagged so response_node's guard
    skips memory/interest/journal/psyche extraction — fulfilling the contract that
    only DIRECT user inputs feed those subsystems.
    """
    action_id = uuid.uuid4()
    user_id = uuid.uuid4()

    action = MagicMock()
    action.id = action_id
    action.action_prompt = "Summarize my unread emails"
    action.title = "Morning briefing"

    # Real UserProfile (not a MagicMock): a MagicMock would trivially carry any
    # attribute, masking the very bug this asserts — the profile schema silently
    # defaulting response_display_mode to "cards". Use the production schema so the
    # read path (getattr on a real UserProfile) is exercised for real.
    from src.domains.users.schemas import UserProfile

    user = UserProfile(
        id=user_id,
        email="user@example.com",
        full_name="Test User",
        timezone="Europe/Paris",
        language="fr",
        is_active=True,
        is_verified=True,
        is_superuser=False,
        response_display_mode="markdown",
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    db = MagicMock()
    db.commit = AsyncMock()

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=action)
    repo.mark_execution_success = AsyncMock()

    user_service = MagicMock()
    user_service.get_user_by_id = AsyncMock(return_value=user)

    conv_service = MagicMock()
    conv_service.get_or_create_conversation = AsyncMock(
        return_value=SimpleNamespace(id=uuid.uuid4())
    )

    # Single AgentService instance reused for the HITL guard and the run.
    agent_service = MagicMock()
    agent_service._ensure_graph_built = AsyncMock()
    agent_service.graph = MagicMock()
    agent_service.graph.aget_state = AsyncMock(return_value=SimpleNamespace(tasks=[]))
    agent_service.stream_chat_response = Mock(side_effect=_fake_stream)

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "src.infrastructure.database.session.get_db_context",
                return_value=_AsyncCM(db),
            )
        )
        stack.enter_context(
            patch(
                "src.domains.scheduled_actions.repository.ScheduledActionRepository",
                return_value=repo,
            )
        )
        stack.enter_context(
            patch("src.domains.users.service.UserService", return_value=user_service)
        )
        stack.enter_context(
            patch(
                "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
                AsyncMock(return_value=False),
            )
        )
        stack.enter_context(
            patch(
                "src.domains.conversations.service.ConversationService",
                return_value=conv_service,
            )
        )
        stack.enter_context(
            patch(
                "src.domains.agents.api.service.AgentService",
                return_value=agent_service,
            )
        )
        stack.enter_context(
            patch(
                "src.domains.scheduled_actions.schedule_helpers.compute_next_trigger_utc",
                return_value=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )
        stack.enter_context(
            patch(
                "src.domains.notifications.service.FCMNotificationService",
                return_value=MagicMock(send_to_user=AsyncMock()),
            )
        )
        stack.enter_context(
            patch(
                "src.infrastructure.cache.redis.get_redis_cache",
                AsyncMock(return_value=None),
            )
        )

        result = await execute_single_action(action_id=action_id, user_id=user_id)

    assert result == "hello"
    agent_service.stream_chat_response.assert_called_once()
    kwargs = agent_service.stream_chat_response.call_args.kwargs
    assert kwargs["is_automated_source"] is True
    # Sanity: scheduled actions also auto-approve the HITL plan gate.
    assert kwargs["auto_approve_plan"] is True
    # Regression: the user's display-mode preference must reach the agent run
    # instead of silently defaulting to "cards".
    assert kwargs["user_display_mode"] == "markdown"


@pytest.mark.asyncio
async def test_process_scheduled_actions_uses_no_redis_lock():
    """F003: the executor processes due actions with NO Redis SchedulerLock.

    The former per-job Redis lock, retained for its full TTL (300s), throttled
    this 60s job to one run per five minutes. Single execution is already
    guaranteed by leader election + APScheduler ``max_instances=1`` + the
    repository's FOR UPDATE SKIP LOCKED, so the executor must run every cycle
    without ever consulting Redis. This guards against re-introducing the lock.
    """
    from src.infrastructure.scheduler import scheduled_action_executor as mod

    action = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4())

    mock_db = AsyncMock()
    repo = MagicMock()
    repo.recover_stale_executing = AsyncMock(return_value=0)
    repo.get_and_lock_due_actions = AsyncMock(return_value=[action])

    redis_factory = AsyncMock()  # must never be called by the executor

    with (
        patch(
            "src.infrastructure.database.session.get_db_context",
            return_value=_AsyncCM(mock_db),
        ),
        patch(
            "src.domains.scheduled_actions.repository.ScheduledActionRepository",
            return_value=repo,
        ),
        patch.object(mod, "execute_single_action", AsyncMock(return_value="ok")) as exec_mock,
        patch("src.infrastructure.cache.redis.get_redis_cache", redis_factory),
    ):
        stats = await mod.process_scheduled_actions()

    assert stats["processed"] == 1
    assert stats["success"] == 1
    exec_mock.assert_awaited_once()
    redis_factory.assert_not_called()
