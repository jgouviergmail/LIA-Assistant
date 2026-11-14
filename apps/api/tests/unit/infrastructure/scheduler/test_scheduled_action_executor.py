"""Unit tests for the scheduled action executor.

Covers two contracts:

1. The run is flagged as an automated source so response_node skips long-term
   memory / interest / journal / psyche extraction, and the user's display-mode
   preference reaches the agent run. (Entry-point half of the
   ``is_automated_source`` redesign — the guard itself is covered by
   ``tests/agents/test_response_node.py``.)
2. The notification surfaces (FCM push body, SSE toast preview) carry the
   *canonical* post-processed content, flattened to plain text. Both halves
   regressed together in 2026-07: users received
   ``<div class="lia-response"><h2>…`` on their lock screen, built from the
   pre-post-processing token stream.
"""

import uuid
from collections.abc import Iterator
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.config import settings
from src.core.constants import ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS
from src.core.exceptions import ResourceNotFoundError
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.models import ScheduledRunOutcome
from src.domains.users.schemas import UserProfile
from src.infrastructure.scheduler.out_of_turn_run import RunOutcome, RunResult
from src.infrastructure.scheduler.scheduled_action_executor import execute_single_action
from src.infrastructure.scheduler.scheduled_action_notices import RoutineNotice
from tests.fixtures.instruction_runtime import instruction_runtime

#: The harness routine is due at 06:00Z (08:00 Paris); the tick starts 5 s later.
NOW = datetime(2026, 8, 3, 6, 0, 5, tzinfo=UTC)


class _AsyncCM:
    """Minimal async context manager yielding a fixed value (mocks get_db_context)."""

    def __init__(self, value: Any) -> None:
        self._value = value

    async def __aenter__(self) -> Any:
        return self._value

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


def _chunk(chunk_type: str, content: Any) -> SimpleNamespace:
    """Build a minimal ChatStreamChunk stand-in."""
    return SimpleNamespace(type=chunk_type, content=content)


def _make_stream(chunks: list[SimpleNamespace]):
    """Stand-in for AgentService.stream_chat_response yielding fixed chunks."""

    async def _stream(*_args: Any, **_kwargs: Any):
        for chunk in chunks:
            yield chunk

    return _stream


@dataclass
class _Env:
    """Handles on the mocked collaborators, for post-run assertions."""

    action_id: uuid.UUID
    user_id: uuid.UUID
    action: MagicMock
    agent_service: MagicMock
    fcm: MagicMock
    redis: MagicMock
    db: MagicMock
    repo: MagicMock
    run_repo: MagicMock
    calls: list[str]
    conversation_id: uuid.UUID
    user_service: MagicMock
    usage_blocked: AsyncMock
    notice: AsyncMock
    quota_claim: AsyncMock


@contextmanager
def _executor_env(
    *,
    chunks: list[SimpleNamespace],
    language: str = "fr",
    display_mode: str = "markdown",
) -> Iterator[_Env]:
    """Patch every collaborator of ``execute_single_action`` and yield handles."""
    action_id = uuid.uuid4()
    user_id = uuid.uuid4()

    action = MagicMock()
    action.id = action_id
    action.user_id = user_id
    action.action_prompt = "Summarize my unread emails"
    action.title = "Morning briefing"
    # N-07: explicit defaults — a bare MagicMock would autovivify
    # requires_approval as truthy and wrongly enter the propose-first branch,
    # and trigger_kind as a non-"time" mock. These keep the historical
    # time-routine path under test.
    action.trigger_kind = "time"
    action.condition_config = None
    action.condition_state = None
    action.requires_approval = False
    # The model's property: None unless the routine's form ticked servers (D9).
    action.mcp_preapproval = None
    # The column's default: a bare MagicMock would be truthy and run every
    # test as a routine told to notify only of something new.
    action.notify_only_when_new = False
    # A real datetime, like the non-nullable column: re-arming compares the
    # pending due time against now to tell a consumed slot from a manual "run
    # now" (which must not drop the upcoming run). A MagicMock here would only
    # prove the mock cannot be compared.
    action.recurrence_spec = RecurrenceSpec(
        freq="weekly",
        times=DailyTimes(mode="at", at=(TimeOfDay(hour=8, minute=0),)),
        anchor_date=date(2026, 1, 5),
        byweekday=(1, 2, 3, 4, 5, 6, 7),
    )
    action.user_timezone = "Europe/Paris"
    action.next_trigger_at = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)

    # Real UserProfile (not a MagicMock): a MagicMock would trivially carry any
    # attribute, masking the very bug this asserts — the profile schema silently
    # defaulting response_display_mode to "cards". Use the production schema so the
    # read path (getattr on a real UserProfile) is exercised for real.
    user = UserProfile(
        id=user_id,
        email="user@example.com",
        full_name="Test User",
        timezone="Europe/Paris",
        language=language,
        is_active=True,
        is_verified=True,
        is_superuser=False,
        response_display_mode=display_mode,
        created_at=datetime(2026, 7, 1, tzinfo=UTC),
        updated_at=datetime(2026, 7, 1, tzinfo=UTC),
    )

    # The order of the durable writes matters: the run row must be flushed
    # BEFORE the commit that makes the routine's own marking durable.
    calls: list[str] = []

    async def _commit() -> None:
        calls.append("commit")

    db = MagicMock()
    db.commit = AsyncMock(side_effect=_commit)
    db.begin_nested = MagicMock(return_value=_AsyncCM(None))
    db.get = AsyncMock(return_value=SimpleNamespace(id=user_id))

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=action)
    repo.mark_execution_success = AsyncMock()
    repo.mark_execution_failure = AsyncMock()
    repo.reschedule = AsyncMock()
    repo.lock_reserved = AsyncMock(return_value=action)
    repo.disable_for_unavailable_owner = AsyncMock(return_value=True)

    async def _record(**_kwargs: Any) -> str:
        calls.append("record")
        return "row"

    run_repo = MagicMock()
    run_repo.record = AsyncMock(side_effect=_record)
    run_repo.count_fires_since = AsyncMock(return_value=0)

    user_service = MagicMock()
    user_service.get_user_by_id = AsyncMock(return_value=user)

    conversation_id = uuid.uuid4()
    conv_service = MagicMock()
    conv_service.get_or_create_conversation = AsyncMock(
        return_value=SimpleNamespace(id=conversation_id)
    )

    # Single AgentService instance reused for the HITL guard and the run.
    agent_service = MagicMock()
    agent_service._ensure_graph_built = AsyncMock()
    agent_service.graph = MagicMock()
    agent_service.graph.aget_state = AsyncMock(return_value=SimpleNamespace(tasks=[]))
    stream = _make_stream(chunks)

    def _traced_stream(*args: Any, **kwargs: Any) -> Any:
        calls.append("stream")
        return stream(*args, **kwargs)

    agent_service.stream_chat_response = Mock(side_effect=_traced_stream)

    fcm = MagicMock(send_to_user=AsyncMock())
    redis = MagicMock(publish=AsyncMock())

    with ExitStack() as stack:
        stack.enter_context(instruction_runtime(user_id, conversation_id))
        for target, replacement in (
            ("src.infrastructure.database.session.get_db_context", _AsyncCM(db)),
            ("src.domains.scheduled_actions.repository.ScheduledActionRepository", repo),
            ("src.domains.users.service.UserService", user_service),
            ("src.domains.conversations.service.ConversationService", conv_service),
            ("src.domains.agents.api.service.AgentService", agent_service),
            ("src.domains.notifications.service.FCMNotificationService", fcm),
            ("src.domains.scheduled_actions.runs.ScheduledActionRunRepository", run_repo),
            ("src.domains.scheduled_actions.run_repository.ScheduledActionRunRepository", run_repo),
        ):
            stack.enter_context(patch(target, return_value=replacement))

        usage_blocked = stack.enter_context(
            patch(
                "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
                AsyncMock(return_value=False),
            )
        )
        # What a routine tells its owner when it did not run leaves through one
        # door; a test about a notice reads it, the others send nothing.
        notice = stack.enter_context(
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.send_routine_notice",
                AsyncMock(),
            )
        )
        quota_claim = stack.enter_context(
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.claim_quota_notice",
                AsyncMock(return_value=False),
            )
        )
        stack.enter_context(
            patch(
                "src.core.recurrence.rearm_after",
                return_value=datetime(2026, 7, 1, tzinfo=UTC),
            )
        )
        stack.enter_context(
            patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=redis))
        )
        # The thread probe reads the pending-HITL record the chat reads
        # (ADR-276 lot 7); a test that wants a pending question patches it.
        stack.enter_context(
            patch(
                "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
                AsyncMock(return_value=None),
            )
        )
        stack.enter_context(
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.now_utc", return_value=NOW
            )
        )
        # The stand-in stream performs no action, so the register a retry reads
        # first has nothing to show (point 20); a test about a run that acted
        # says so itself.
        stack.enter_context(
            patch(
                "src.infrastructure.scheduler.out_of_turn_run._run_acted",
                AsyncMock(return_value=False),
            )
        )
        # A retry sleeps for real otherwise; the delay is not what is under test.
        stack.enter_context(
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor"
                ".SCHEDULED_ACTIONS_RETRY_DELAY_SECONDS",
                0,
            )
        )

        yield _Env(
            action_id=action_id,
            user_id=user_id,
            action=action,
            agent_service=agent_service,
            fcm=fcm,
            redis=redis,
            db=db,
            repo=repo,
            run_repo=run_repo,
            calls=calls,
            conversation_id=conversation_id,
            user_service=user_service,
            usage_blocked=usage_blocked,
            notice=notice,
            quota_claim=quota_claim,
        )


def _sse_payload(env: _Env) -> dict[str, Any]:
    """Decode the JSON published on the user's notification channel."""
    import json

    env.redis.publish.assert_awaited_once()
    _channel, raw = env.redis.publish.await_args.args
    return json.loads(raw)


@pytest.mark.asyncio
async def test_unavailable_owner_settles_its_reservation_without_running():
    with _executor_env(chunks=[]) as env:
        token = uuid.uuid4()
        env.user_service.get_user_by_id.side_effect = ResourceNotFoundError("user")
        result = await execute_single_action(env.action_id, env.user_id, execution_token=token)
    assert result == ""
    env.repo.disable_for_unavailable_owner.assert_awaited_once_with(
        env.action_id, env.user_id, token
    )
    env.agent_service.stream_chat_response.assert_not_called()
    env.run_repo.record.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message", ["Execution timed out after 30s", "MisleadingType: private prose"]
)
async def test_failure_log_uses_the_structured_code_without_parsing_prose(message: str) -> None:
    result = RunResult(
        outcome=RunOutcome.FAILED, attempts=1, error=message, error_code="TimeoutError"
    )
    with (
        _executor_env(chunks=[]) as env,
        patch("src.infrastructure.scheduler.scheduled_action_executor.logger") as log,
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor.stream_instruction",
            AsyncMock(return_value=result),
        ),
    ):
        await execute_single_action(env.action_id, env.user_id)
    assert log.warning.call_args.kwargs["error_type"] == "TimeoutError"
    assert message not in str(log.warning.call_args)


@pytest.mark.asyncio
async def test_executor_refuses_a_routine_owned_by_a_different_account():
    with _executor_env(chunks=[_chunk("token", "hello")]) as env:
        env.action.user_id = uuid.uuid4()
        result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)
    assert result == ""
    env.agent_service.stream_chat_response.assert_not_called()


@pytest.mark.parametrize("allowed", [[False], [True, False], [True, True, False]])
async def test_a_withdrawn_exact_manual_guard_never_calls_the_pipeline(allowed: list[bool]):
    guard = AsyncMock(side_effect=allowed)
    with _executor_env(chunks=[_chunk("token", "hello")]) as env:
        result = await execute_single_action(
            action_id=env.action_id, user_id=env.user_id, execution_guard=guard
        )
    assert result == ""
    env.agent_service.stream_chat_response.assert_not_called()
    assert guard.await_count == len(allowed)


@pytest.mark.asyncio
async def test_execute_single_action_marks_run_as_automated_source():
    """execute_single_action must call stream_chat_response(is_automated_source=True).

    This guarantees scheduled-action runs are flagged so response_node's guard
    skips memory/interest/journal/psyche extraction — fulfilling the contract that
    only DIRECT user inputs feed those subsystems.
    """
    with _executor_env(chunks=[_chunk("token", "hello")]) as env:
        result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    assert result == "hello"
    env.agent_service.stream_chat_response.assert_called_once()
    kwargs = env.agent_service.stream_chat_response.call_args.kwargs
    assert kwargs["is_automated_source"] is True
    # Sanity: scheduled actions also auto-approve the HITL plan gate.
    assert kwargs["auto_approve_plan"] is True
    # Regression: the user's display-mode preference must reach the agent run
    # instead of silently defaulting to "cards".
    assert kwargs["user_display_mode"] == "markdown"


@pytest.mark.asyncio
async def test_content_replacement_supersedes_streamed_tokens():
    """The canonical post-processed content REPLACES the token deltas.

    ``content_replacement`` carries the final text after post-processing (HTML
    cards, photo injection, psyche-tag cleanup) and is what
    ``stream_chat_response`` archives. Accumulating only tokens made the
    notification disagree with the message the user opens in chat.
    """
    with _executor_env(
        chunks=[
            _chunk("token", "partial "),
            _chunk("token", "draft"),
            _chunk("content_replacement", "final canonical text"),
        ]
    ) as env:
        result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    assert result == "final canonical text"
    assert "draft" not in result  # replaced, not appended


@pytest.mark.asyncio
async def test_tokens_are_used_when_no_replacement_is_emitted():
    """No post-processing → the token stream remains the source of truth."""
    with _executor_env(chunks=[_chunk("token", "un "), _chunk("token", "deux")]) as env:
        result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    assert result == "un deux"


@pytest.mark.asyncio
async def test_non_string_replacement_content_is_ignored():
    """A dict-typed chunk must not silently blank the notification body."""
    with _executor_env(
        chunks=[
            _chunk("token", "kept"),
            _chunk("content_replacement", {"unexpected": "shape"}),
        ]
    ) as env:
        result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    assert result == "kept"


@pytest.mark.asyncio
async def test_notification_surfaces_receive_flattened_plain_text():
    """The exact 2026-07 regression: HTML reached the push body and the toast.

    Both surfaces render their text verbatim, so the markup must be gone from
    each — while the returned value (archived by the caller) keeps it.
    """
    html = (
        '<div class="lia-response">\n'
        "<h2>Technologies 2026 : le monde tourne encore sans IA</h2>\n"
        "<p>On respire un peu.</p>\n"
        "</div>"
    )
    with _executor_env(chunks=[_chunk("content_replacement", html)]) as env:
        result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    # The agent's rich content is returned untouched for archiving/chat.
    assert result == html

    body = env.fcm.send_to_user.await_args.kwargs["body"]
    assert "<" not in body and "lia-response" not in body
    assert body.startswith("Technologies 2026")

    content = _sse_payload(env)["content"]
    assert "<" not in content and "lia-response" not in content
    assert content.startswith("Technologies 2026")
    # Single-line: the HTML stripper's block newlines must not survive.
    assert "\n" not in content


@pytest.mark.asyncio
async def test_push_body_honors_the_configured_length_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The push budget follows the setting, not a hardcoded literal.

    The setting's default happens to equal the former hardcoded 150, so
    asserting against the default would pass for both implementations. Override
    it to a distinct value: only a settings-driven ``_truncate`` can satisfy
    this.
    """
    override = 80
    assert (
        override != settings.proactive_notification_max_length
    ), "override must differ from the default, otherwise this test cannot fail"
    monkeypatch.setattr(settings, "proactive_notification_max_length", override)

    long_text = "a" * (override + 200)
    with _executor_env(chunks=[_chunk("token", long_text)]) as env:
        await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    body = env.fcm.send_to_user.await_args.kwargs["body"]
    assert len(body) == override
    assert body.endswith("...")


@pytest.mark.asyncio
async def test_title_is_localized_for_backend_canonical_chinese():
    """zh-CN must resolve: the old inline table was keyed "zh" (English fallback)."""
    with _executor_env(chunks=[_chunk("token", "ok")], language="zh-CN") as env:
        await execute_single_action(action_id=env.action_id, user_id=env.user_id)

    title = env.fcm.send_to_user.await_args.kwargs["title"]
    assert title.startswith("计划操作")
    assert "Scheduled" not in title


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

    # A reserved action always carries the token it was reserved under.
    action = SimpleNamespace(id=uuid.uuid4(), user_id=uuid.uuid4(), execution_token=uuid.uuid4())

    mock_db = AsyncMock()
    repo = MagicMock()
    repo.recover_stale_executing = AsyncMock(return_value=0)
    repo.get_and_lock_due_actions = AsyncMock(return_value=[action])
    repo.close_finished = AsyncMock(return_value=0)  # nothing to close this tick

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
        _served_calls_repository(),
    ):
        stats = await mod.process_scheduled_actions()

    assert stats["processed"] == 1
    assert stats["success"] == 1
    exec_mock.assert_awaited_once()
    redis_factory.assert_not_called()


# =============================================================================
# Run history (ADR-265): one row per exit, before the commit, never a gate
# =============================================================================


def _recorded(env: _Env) -> dict[str, Any]:
    env.run_repo.record.assert_awaited_once()
    return env.run_repo.record.await_args.kwargs


def _raising_stream(exc: BaseException):
    """A stream that raises before yielding anything."""

    async def _stream(*_args: Any, **_kwargs: Any):
        raise exc
        yield  # pragma: no cover — makes this an async generator

    return _stream


class TestRunHistory:
    @pytest.mark.asyncio
    async def test_a_success_is_recorded_for_its_due_slot_before_the_commit(self) -> None:
        with _executor_env(chunks=[_chunk("token", "hello")]) as env:
            await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.SUCCESS
            assert recorded["scheduled_action_id"] == env.action_id
            assert recorded["user_id"] == env.user_id
            assert recorded["slot_at"] == env.action.next_trigger_at
            assert recorded["started_at"] == NOW
            assert (recorded["attempts"], recorded["manual"], recorded["error"]) == (
                1,
                False,
                None,
            )
            # Flushed inside the transaction whose commit makes the routine's
            # marking durable (the first commit only ended the reads, ADR-304).
            assert "commit" in env.calls[env.calls.index("record") :]

    @pytest.mark.asyncio
    async def test_a_manual_run_after_the_slot_is_marked_manual_and_serves_it(self) -> None:
        with _executor_env(chunks=[_chunk("token", "hello")]) as env:
            # Nothing due until tomorrow: the user pressed "Test now" at 08:00:05.
            env.action.next_trigger_at = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
            await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            recorded = _recorded(env)
            assert recorded["manual"] is True
            assert recorded["slot_at"] == datetime(2026, 8, 3, 6, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_a_final_failure_is_recorded_with_its_attempts_and_error(self) -> None:
        with _executor_env(chunks=[]) as env:
            env.agent_service.stream_chat_response = Mock(
                side_effect=_raising_stream(ConnectionError("provider down"))
            )
            await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            env.repo.mark_execution_failure.assert_awaited_once()
            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.FAILURE
            assert recorded["attempts"] == 2  # one retry on a transient error
            assert "provider down" in recorded["error"]
            assert "commit" in env.calls[env.calls.index("record") :]

    @pytest.mark.asyncio
    async def test_a_non_retryable_failure_counts_one_attempt(self) -> None:
        with _executor_env(chunks=[]) as env:
            env.agent_service.stream_chat_response = Mock(
                side_effect=_raising_stream(RuntimeError("HITL interrupt"))
            )
            await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.FAILURE
            assert recorded["attempts"] == 1

    @pytest.mark.asyncio
    async def test_a_check_that_finds_nothing_new_writes_no_row_and_runs_nothing(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env)
            with _verdict(env, ConditionVerdict(note_prefix="Overdue tasks: ")):
                result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert result == ""
            env.agent_service.stream_chat_response.assert_not_called()
            env.run_repo.record.assert_not_awaited()
            # The check itself is recorded — on the routine's ledger.
            state = env.repo.reschedule.await_args.kwargs["condition_state"]
            assert state["last_checked_at"] == NOW.isoformat()

    @pytest.mark.asyncio
    async def test_a_proposal_is_recorded_as_proposed(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.requires_approval = True
            with patch(
                "src.infrastructure.scheduler.scheduled_action_executor"
                ".send_approval_notification",
                AsyncMock(),
            ) as notify:
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            notify.assert_awaited_once()
            env.agent_service.stream_chat_response.assert_not_called()
            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.PROPOSED
            assert recorded["attempts"] == 0

    @pytest.mark.asyncio
    async def test_a_pending_hitl_is_recorded_as_skipped(self) -> None:
        with (
            _executor_env(chunks=[_chunk("token", "never")]) as env,
            patch(
                "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
                AsyncMock(
                    return_value={
                        "run_id": "pending-run",
                        "action_requests": [{"type": "clarification"}],
                    }
                ),
            ),
        ):
            await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            env.agent_service.stream_chat_response.assert_not_called()
            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.SKIPPED_HITL
            assert recorded["attempts"] == 0
            # Nothing ran: the slot is re-armed, never counted as an execution
            # (it used to raise execution_count and last_executed_at).
            env.repo.reschedule.assert_awaited_once()
            env.repo.mark_execution_success.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_failed_history_write_never_costs_the_routine_its_marking(self) -> None:
        with _executor_env(chunks=[_chunk("token", "hello")]) as env:
            env.run_repo.record = AsyncMock(side_effect=RuntimeError("history down"))
            result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert result == "hello"
            env.repo.mark_execution_success.assert_awaited_once()
            assert "commit" in env.calls


def _served_calls_repository(*, purged: int = 0, fails: bool = False) -> Any:
    """Stub the served-calls purge of the executor's step zero (ADR-386)."""
    repo = MagicMock()
    repo.purge_served_before = AsyncMock(
        side_effect=RuntimeError("locked") if fails else None, return_value=purged
    )
    return patch(
        "src.domains.scheduled_actions.webhook_repository.RoutineWebhookRepository",
        return_value=repo,
    )


class TestRetentionPurge:
    @pytest.mark.asyncio
    async def test_the_tick_purges_history_older_than_the_retention(self) -> None:
        from src.infrastructure.scheduler import scheduled_action_executor as mod

        mock_db = AsyncMock()
        repo = MagicMock()
        repo.recover_stale_executing = AsyncMock(return_value=0)
        repo.get_and_lock_due_actions = AsyncMock(return_value=[])
        repo.close_finished = AsyncMock(return_value=0)  # nothing to close this tick
        run_repo = MagicMock()
        run_repo.purge_older_than = AsyncMock(return_value=3)

        with (
            patch(
                "src.infrastructure.database.session.get_db_context",
                return_value=_AsyncCM(mock_db),
            ),
            patch(
                "src.domains.scheduled_actions.repository.ScheduledActionRepository",
                return_value=repo,
            ),
            patch(
                "src.domains.scheduled_actions.run_repository.ScheduledActionRunRepository",
                return_value=run_repo,
            ),
            patch.object(mod, "now_utc", return_value=NOW),
            _served_calls_repository(purged=2) as calls_repo,
        ):
            stats = await mod.process_scheduled_actions()

        assert stats["runs_purged"] == 3
        run_repo.purge_older_than.assert_awaited_once_with(
            NOW - timedelta(days=settings.scheduled_actions_runs_retention_days)
        )
        # ADR-386: the calls already served go after their own retention, in the same step.
        assert stats["calls_purged"] == 2
        calls_repo.return_value.purge_served_before.assert_awaited_once_with(
            NOW - timedelta(days=ROUTINE_WEBHOOK_SERVED_RETENTION_DAYS)
        )

    @pytest.mark.asyncio
    async def test_a_failed_purge_never_fails_the_tick(self) -> None:
        from src.infrastructure.scheduler import scheduled_action_executor as mod

        mock_db = AsyncMock()
        repo = MagicMock()
        repo.recover_stale_executing = AsyncMock(return_value=0)
        repo.get_and_lock_due_actions = AsyncMock(return_value=[])
        repo.close_finished = AsyncMock(return_value=0)  # nothing to close this tick
        run_repo = MagicMock()
        run_repo.purge_older_than = AsyncMock(side_effect=RuntimeError("locked"))

        with (
            patch(
                "src.infrastructure.database.session.get_db_context",
                return_value=_AsyncCM(mock_db),
            ),
            patch(
                "src.domains.scheduled_actions.repository.ScheduledActionRepository",
                return_value=repo,
            ),
            patch(
                "src.domains.scheduled_actions.run_repository.ScheduledActionRunRepository",
                return_value=run_repo,
            ),
            _served_calls_repository(fails=True),
        ):
            stats = await mod.process_scheduled_actions()

        assert stats["runs_purged"] == 0
        assert stats["calls_purged"] == 0
        assert stats["processed"] == 0


class TestTheReArmIsComputedInOnePlace:
    """Five exits, one rule.

    Every exit of the executor — condition not met, proposal, pending HITL,
    success, final failure — must re-arm the routine the same way. They did,
    by five literal copies of the same three-argument call. That is the shape
    ADR-248's second invariant names: a rule in five copies gets changed in
    four, and the exit nobody updated re-arms differently from its siblings
    with nothing to reveal it.

    The five behaviours are pinned by the tests above; this pins the fact that
    they cannot drift apart.
    """

    def test_the_executor_asks_the_plan_from_a_single_site(self) -> None:
        import ast
        import inspect
        from pathlib import Path

        from src.infrastructure.scheduler import scheduled_action_executor

        source = Path(inspect.getfile(scheduled_action_executor)).read_text(encoding="utf-8")
        tree = ast.parse(source)
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"after_tick", "first"}
        ]
        engine = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"rearm_after", "next_occurrence", "next_check"}
        ]
        assert len(calls) == 1, (
            f"the routine's plan is asked from {len(calls)} sites; route every exit through "
            "the single helper so the exits cannot re-arm differently"
        )
        assert engine == [], "the executor must re-arm through the plan, never the engine"


# =============================================================================
# Condition routines on the system's clock (ADR-322)
# =============================================================================

from src.domains.scheduled_actions.trigger import check_interval  # noqa: E402
from src.infrastructure.scheduler.condition_evaluators import (  # noqa: E402
    ConditionFact,
    ConditionVerdict,
)

_SEEN = ConditionFact(key="k-seen", label="Old invoice")
_NEW = ConditionFact(key="k-new", label="New invoice")


def _as_watch(env: _Env, *, seen: tuple[str, ...] = ()) -> None:
    """Turn the harness routine into a condition routine."""
    env.action.trigger_kind = "condition"
    env.action.recurrence_spec = None
    env.action.condition_config = {"type": "mail_match", "query": "invoice"}
    env.action.condition_state = {"seen": list(seen)} if seen else None


@contextmanager
def _verdict(env: _Env, verdict: ConditionVerdict) -> Iterator[AsyncMock]:
    """The check answers ``verdict``; the trace records when it ran."""

    async def _evaluate(*_args: Any, **_kwargs: Any) -> ConditionVerdict:
        env.calls.append("evaluate")
        return verdict

    evaluate = AsyncMock(side_effect=_evaluate)
    with patch("src.infrastructure.scheduler.condition_evaluators.evaluate_condition", evaluate):
        yield evaluate


class TestAConditionRoutine:
    @pytest.mark.asyncio
    async def test_a_new_fact_runs_the_pipeline_on_that_fact_alone(self) -> None:
        with _executor_env(chunks=[_chunk("token", "done")]) as env:
            _as_watch(env, seen=("k-seen",))
            verdict = ConditionVerdict(facts=(_SEEN, _NEW), note_prefix="Matching mails: ")
            with _verdict(env, verdict):
                result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert result == "done"
            prompt = env.agent_service.stream_chat_response.call_args.kwargs["user_message"]
            assert prompt.endswith("[Trigger context] Matching mails: New invoice")
            state = env.repo.mark_execution_success.await_args.kwargs["condition_state"]
            assert set(state["seen"]) == {"k-seen", "k-new"}
            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.SUCCESS
            # The run serves the check that fired: its own start.
            assert recorded["slot_at"] == NOW

    @pytest.mark.asyncio
    async def test_nothing_is_held_open_while_the_source_or_the_model_answers(self) -> None:
        # ADR-304: every wait starts after a commit.
        with _executor_env(chunks=[_chunk("token", "done")]) as env:
            _as_watch(env)
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert env.calls[env.calls.index("evaluate") - 1] == "commit"
            assert env.calls[env.calls.index("stream") - 1] == "commit"
            # And the outcome is durable before the push.
            assert "commit" in env.calls[env.calls.index("record") :]

    @pytest.mark.asyncio
    async def test_the_daily_cap_keeps_the_fact_new_for_tomorrow(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env)
            env.run_repo.count_fires_since = AsyncMock(
                return_value=settings.scheduled_actions_condition_max_fires_per_day
            )
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            env.agent_service.stream_chat_response.assert_not_called()
            env.run_repo.record.assert_not_awaited()
            state = env.repo.reschedule.await_args.kwargs["condition_state"]
            assert "k-new" not in state["seen"]

    @pytest.mark.asyncio
    async def test_the_cap_counts_from_the_routines_own_midnight(self) -> None:
        with _executor_env(chunks=[_chunk("token", "done")]) as env:
            _as_watch(env)
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            # 08:00:05 in Paris: the day began at 22:00 UTC the evening before.
            action_id, since = env.run_repo.count_fires_since.await_args.args
            assert action_id == env.action_id
            assert since == datetime(2026, 8, 2, 22, 0, tzinfo=UTC)

    @pytest.mark.asyncio
    async def test_a_failed_run_leaves_the_fact_new(self) -> None:
        with _executor_env(chunks=[]) as env:
            _as_watch(env)
            env.agent_service.stream_chat_response = Mock(
                side_effect=_raising_stream(RuntimeError("HITL interrupt"))
            )
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            state = env.repo.mark_execution_failure.await_args.kwargs["condition_state"]
            assert "k-new" not in state["seen"]
            assert _recorded(env)["outcome"] is ScheduledRunOutcome.FAILURE

    @pytest.mark.asyncio
    async def test_a_pending_question_writes_no_row_and_keeps_the_fact_new(self) -> None:
        with (
            _executor_env(chunks=[_chunk("token", "never")]) as env,
            patch(
                "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
                AsyncMock(
                    return_value={
                        "run_id": "pending-run",
                        "action_requests": [{"type": "clarification"}],
                    }
                ),
            ),
        ):
            _as_watch(env)
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            env.agent_service.stream_chat_response.assert_not_called()
            env.run_repo.record.assert_not_awaited()
            state = env.repo.reschedule.await_args.kwargs["condition_state"]
            assert "k-new" not in state["seen"]

    @pytest.mark.asyncio
    async def test_an_unreadable_source_is_said_on_the_ledger_and_runs_nothing(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env, seen=("k-seen",))
            with _verdict(env, ConditionVerdict(error="unavailable")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            env.agent_service.stream_chat_response.assert_not_called()
            state = env.repo.reschedule.await_args.kwargs["condition_state"]
            assert state["last_check_error"] == "unavailable"
            assert state["seen"] == ["k-seen"]

    @pytest.mark.asyncio
    async def test_the_proposal_push_waits_for_no_open_transaction(self) -> None:
        # ADR-304: the cap's count is a read — committed before the push leaves.
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env)
            env.action.requires_approval = True

            async def _count(*_args: Any) -> int:
                env.calls.append("count")
                return 0

            async def _notify(*_args: Any, **_kwargs: Any) -> None:
                env.calls.append("notify")

            env.run_repo.count_fires_since = AsyncMock(side_effect=_count)
            with (
                _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")),
                patch(
                    "src.infrastructure.scheduler.scheduled_action_executor"
                    ".send_approval_notification",
                    AsyncMock(side_effect=_notify),
                ),
            ):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert env.calls.index("count") < env.calls.index("notify")
            assert env.calls[env.calls.index("notify") - 1] == "commit"

    @pytest.mark.asyncio
    async def test_a_proposal_serves_the_fact(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env)
            env.action.requires_approval = True
            with (
                _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")),
                patch(
                    "src.infrastructure.scheduler.scheduled_action_executor"
                    ".send_approval_notification",
                    AsyncMock(),
                ),
            ):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            state = env.repo.reschedule.await_args.kwargs["condition_state"]
            assert "k-new" in state["seen"]
            assert _recorded(env)["outcome"] is ScheduledRunOutcome.PROPOSED

    @pytest.mark.asyncio
    async def test_it_re_arms_on_the_systems_next_check(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env)
            with _verdict(env, ConditionVerdict(note_prefix="Mails: ")):
                await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            next_trigger = env.repo.reschedule.await_args.args[1]
            # The published interval of the type, never a figure typed here.
            assert NOW < next_trigger <= NOW + check_interval("mail_match")


def _interrupt_chunks(kind: str) -> list[SimpleNamespace]:
    """A turn that stopped on a question, as the stream reports it."""
    return [
        SimpleNamespace(
            type="hitl_interrupt_metadata",
            content="",
            metadata={"action_requests": [{"type": kind}]},
        ),
        SimpleNamespace(
            type="hitl_interrupt_complete", content="", metadata={"generated_question": "Which?"}
        ),
    ]


@pytest.mark.asyncio
class TestAQuestionNobodyCanAnswer:
    """N10: a routine's run that stops on a question must not leave it waiting
    on the person's thread, where it reads their next message as its answer and
    makes every later routine of the account stand aside."""

    async def test_every_attempt_runs_under_the_one_id_the_routine_owns(self) -> None:
        """The question saved on the thread names this id; so does every row a
        retry files — two attempts are one run, as on a ticket."""
        with _executor_env(chunks=[_chunk("token", "Done")]) as env:
            healthy = env.agent_service.stream_chat_response.side_effect
            attempts: list[int] = []

            def _first_attempt_blinks(*args: Any, **kwargs: Any) -> Any:
                attempts.append(1)
                if len(attempts) == 1:
                    raise ConnectionError("blink")
                return healthy(*args, **kwargs)

            env.agent_service.stream_chat_response.side_effect = _first_attempt_blinks
            await execute_single_action(env.action_id, env.user_id)

        run_ids = [
            call.kwargs["run_id"] for call in env.agent_service.stream_chat_response.call_args_list
        ]
        assert len(run_ids) == 2
        assert run_ids[0] and run_ids[0] == run_ids[1]

    async def test_the_question_the_run_raised_is_taken_back(self) -> None:
        with (
            _executor_env(chunks=_interrupt_chunks("clarification")) as env,
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.clear_question_of_run",
                AsyncMock(return_value=True),
            ) as taken_back,
        ):
            await execute_single_action(env.action_id, env.user_id)

        run_id = env.agent_service.stream_chat_response.call_args.kwargs["run_id"]
        admission = env.agent_service.stream_chat_response.call_args.kwargs["admission"]
        assert admission.run_id == run_id and admission.target.id == env.conversation_id
        taken_back.assert_awaited_once_with(admission)
        # Still a failure, as it has always been: nobody answered.
        env.repo.mark_execution_failure.assert_awaited_once()

    async def test_a_run_that_answered_takes_nothing_back(self) -> None:
        with (
            _executor_env(chunks=[_chunk("token", "Done")]) as env,
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.clear_question_of_run",
                AsyncMock(return_value=False),
            ) as taken_back,
        ):
            await execute_single_action(env.action_id, env.user_id)

        taken_back.assert_not_awaited()


@pytest.mark.asyncio
class TestTheReservationHoldsTheRun:
    """Point 19: a tick that no longer holds its reservation neither runs nor
    settles — the routine is another tick's now."""

    async def test_a_tick_whose_reservation_was_taken_runs_nothing(self) -> None:
        token = uuid.uuid4()
        with _executor_env(chunks=[_chunk("token", "Done")]) as env:
            env.repo.renew_reservation = AsyncMock(return_value=False)
            answer = await execute_single_action(env.action_id, env.user_id, execution_token=token)

        assert answer == ""
        env.agent_service.stream_chat_response.assert_not_called()
        env.repo.mark_execution_success.assert_not_awaited()
        env.repo.renew_reservation.assert_awaited_once_with(env.action_id, token)

    async def test_the_reservation_is_renewed_and_committed_right_before_the_model_runs(
        self,
    ) -> None:
        """The recovery then counts from the run's real start, never from a
        reservation that waited for its turn — and the renewal is COMMITTED
        first: held open, its row lock would last the whole inference."""
        token = uuid.uuid4()
        with _executor_env(chunks=[_chunk("token", "Done")]) as env:

            async def _renew(*_args: Any) -> bool:
                env.calls.append("renew")
                return True

            env.repo.renew_reservation = AsyncMock(side_effect=_renew)
            env.repo.lock_reserved = AsyncMock(return_value=env.action)
            await execute_single_action(env.action_id, env.user_id, execution_token=token)

        before_model = env.calls[: env.calls.index("stream")]
        last_renewal = len(before_model) - 1 - before_model[::-1].index("renew")
        assert "commit" in before_model[last_renewal:]
        env.repo.lock_reserved.assert_awaited_once_with(env.action_id, token)
        env.repo.mark_execution_success.assert_awaited_once()

    async def test_the_proposal_push_holds_no_renewed_reservation(self) -> None:
        """ADR-304: a renewal is an UPDATE, and its row lock would last the
        whole push of a proposal — the person editing the routine meanwhile
        would wait on a provider. Every renewal is committed at once."""
        token = uuid.uuid4()
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.requires_approval = True

            async def _renew(*_args: Any) -> bool:
                env.calls.append("renew")
                return True

            async def _notify(*_args: Any, **_kwargs: Any) -> None:
                env.calls.append("notify")

            env.repo.renew_reservation = AsyncMock(side_effect=_renew)
            with patch(
                "src.infrastructure.scheduler.scheduled_action_executor"
                ".send_approval_notification",
                AsyncMock(side_effect=_notify),
            ):
                await execute_single_action(env.action_id, env.user_id, execution_token=token)

        before_push = env.calls[: env.calls.index("notify")]
        last_renewal = len(before_push) - 1 - before_push[::-1].index("renew")
        assert "commit" in before_push[last_renewal:]

    async def test_a_settle_whose_reservation_was_taken_meanwhile_leaves_the_routine_alone(
        self,
    ) -> None:
        """The routine is the other tick's: nothing of it is marked. The run
        itself happened, so its row is written — every exit of the executor
        ends with one (ADR-265), and a condition routine's daily cap counts
        its runs from them (ADR-322)."""
        token = uuid.uuid4()
        with _executor_env(chunks=[_chunk("token", "Done")]) as env:
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            answer = await execute_single_action(env.action_id, env.user_id, execution_token=token)

        assert answer == "Done"  # the run happened: its answer is still the person's
        env.repo.mark_execution_success.assert_not_awaited()
        env.repo.mark_execution_failure.assert_not_awaited()
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SUCCESS

    @pytest.mark.parametrize("verdict", [ConditionVerdict(), ConditionVerdict(error="unavailable")])
    async def test_a_condition_check_cannot_rearm_a_superseding_reservation(
        self, verdict: ConditionVerdict
    ) -> None:
        with _executor_env(chunks=[]) as env:
            _as_watch(env)
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            with _verdict(env, verdict):
                await execute_single_action(
                    env.action_id, env.user_id, execution_token=uuid.uuid4()
                )

        env.repo.reschedule.assert_not_awaited()
        env.run_repo.record.assert_not_awaited()

    async def test_a_proposal_cannot_rearm_after_losing_its_reservation(self) -> None:
        with _executor_env(chunks=[]) as env:
            env.action.requires_approval = True
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            with patch(
                "src.infrastructure.scheduler.scheduled_action_executor.send_approval_notification",
                AsyncMock(),
            ):
                await execute_single_action(
                    env.action_id, env.user_id, execution_token=uuid.uuid4()
                )

        env.repo.reschedule.assert_not_awaited()
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.PROPOSED

    @pytest.mark.parametrize("condition", [False, True])
    async def test_a_pending_question_cannot_rearm_a_superseding_reservation(
        self, condition: bool
    ) -> None:
        with _executor_env(chunks=[]) as env:
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            if condition:
                _as_watch(env)
            with (
                _verdict(env, ConditionVerdict(facts=(_NEW,))),
                patch(
                    "src.domains.agents.api.hitl_pending.check_pending_hitl_uncached",
                    AsyncMock(
                        return_value={
                            "run_id": "pending-run",
                            "action_requests": [{"type": "clarification"}],
                        }
                    ),
                ),
            ):
                await execute_single_action(
                    env.action_id, env.user_id, execution_token=uuid.uuid4()
                )

        env.repo.reschedule.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_routines_preapproval_reaches_its_run() -> None:
    """Spec D9: the run carries the servers the routine's form ticked — and only those."""
    from src.domains.shared.mcp_preapproval import MCPPreapproval

    result = RunResult(outcome=RunOutcome.SUCCESS, attempts=1, text="ok")
    streamed = AsyncMock(return_value=result)
    preapproval = MCPPreapproval(servers=frozenset({"notes"}), routine_id="r-1")
    with (
        _executor_env(chunks=[]) as env,
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor.stream_instruction",
            streamed,
        ),
    ):
        env.action.mcp_preapproval = preapproval
        await execute_single_action(env.action_id, env.user_id)

    (request,), _ = streamed.await_args
    assert request.mcp_preapproval == preapproval


@pytest.mark.asyncio
async def test_a_routine_s_attempt_lasts_what_its_model_calls_may_take() -> None:
    """An administrator's timeout reaches the run, not only the client (ADR-221)."""
    result = RunResult(outcome=RunOutcome.SUCCESS, attempts=1, text="ok")
    streamed = AsyncMock(return_value=result)
    with (
        _executor_env(chunks=[]) as env,
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor.stream_instruction",
            streamed,
        ),
        patch(
            "src.infrastructure.scheduler.scheduled_action_executor._attempt_bound_seconds",
            return_value=4321,
        ),
    ):
        await execute_single_action(env.action_id, env.user_id)

    (request,), _ = streamed.await_args
    assert request.timeout_seconds == 4321


# =============================================================================
# A routine that does not run says so (ADR-265 amendment 2026-11-12)
# =============================================================================


def _marked(consecutive_failures: int, *, disabled: bool = False) -> SimpleNamespace:
    """The routine as ``mark_execution_failure`` leaves it."""
    return SimpleNamespace(
        consecutive_failures=consecutive_failures,
        status="error" if disabled else "active",
    )


async def _fail(env: _Env, *, marked: SimpleNamespace, token: uuid.UUID | None = None) -> None:
    """Run the harness routine into a failure the repository marks as ``marked``."""
    env.repo.mark_execution_failure = AsyncMock(return_value=marked)
    env.agent_service.stream_chat_response = Mock(side_effect=_raising_stream(RuntimeError("boom")))
    await execute_single_action(env.action_id, env.user_id, execution_token=token)


class TestAFailedRoutineSaysSo:
    """A routine used to fail five times and be switched off without a word."""

    async def test_the_first_failure_of_a_series_is_announced_once_it_is_durable(self) -> None:
        with _executor_env(chunks=[]) as env:
            seen_at_send: list[list[str]] = []
            env.notice.side_effect = lambda *_a, **_k: seen_at_send.append(list(env.calls))
            await _fail(env, marked=_marked(1))

        sent = env.notice.await_args.kwargs
        assert sent["kind"] is RoutineNotice.FAILED
        assert sent["action"] is env.action
        assert sent["user_language"] == "fr"
        # The marking is committed before anything leaves the process.
        (calls,) = seen_at_send
        assert "commit" in calls[calls.index("record") :]

    @pytest.mark.parametrize("rank", [2, 4])
    async def test_a_later_failure_of_the_same_series_stays_silent(self, rank: int) -> None:
        with _executor_env(chunks=[]) as env:
            await _fail(env, marked=_marked(rank))

        env.notice.assert_not_awaited()

    async def test_the_failure_that_pauses_the_routine_says_so(self) -> None:
        with _executor_env(chunks=[]) as env:
            await _fail(env, marked=_marked(5, disabled=True))

        assert env.notice.await_args.kwargs["kind"] is RoutineNotice.DISABLED

    async def test_a_run_the_person_started_always_says_it_failed(self) -> None:
        with _executor_env(chunks=[]) as env:
            # Nothing due until tomorrow: the person pressed « Run now ».
            env.action.next_trigger_at = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
            await _fail(env, marked=_marked(3))

        assert env.notice.await_args.kwargs["kind"] is RoutineNotice.FAILED

    async def test_a_run_that_answered_sends_its_result_and_no_notice(self) -> None:
        with _executor_env(chunks=[_chunk("token", "hello")]) as env:
            await execute_single_action(env.action_id, env.user_id)

        env.notice.assert_not_awaited()
        env.fcm.send_to_user.assert_awaited_once()

    async def test_a_tick_that_lost_the_routine_announces_nothing(self) -> None:
        """The routine is another tick's: this one marked nothing, so it has
        no series to speak of."""
        with _executor_env(chunks=[]) as env:
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            await _fail(env, marked=_marked(1), token=uuid.uuid4())

        env.repo.mark_execution_failure.assert_not_awaited()
        env.notice.assert_not_awaited()


_QUOTA_REFUSAL = RunResult(
    outcome=RunOutcome.QUOTA_BLOCKED,
    attempts=1,
    error="Usage limit exceeded",
    error_code="usage_limit_exceeded",
)


class TestTheUsageCeilingStandsARoutineAside:
    """A ceiling refusal is not a failure (ADR-272): the routine re-arms, its
    history says why, and its account is told once per window."""

    async def test_a_blocked_account_s_routine_is_rearmed_and_says_why(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.usage_blocked.return_value = True
            env.quota_claim.return_value = True
            seen_at_send: list[list[str]] = []
            env.notice.side_effect = lambda *_a, **_k: seen_at_send.append(list(env.calls))
            result = await execute_single_action(env.action_id, env.user_id)

        assert result == ""
        env.agent_service.stream_chat_response.assert_not_called()
        # Not a failure: nothing counts toward the pause.
        env.repo.mark_execution_failure.assert_not_awaited()
        env.repo.reschedule.assert_awaited_once()
        recorded = _recorded(env)
        assert recorded["outcome"] is ScheduledRunOutcome.SKIPPED_QUOTA
        assert (recorded["attempts"], recorded["error"]) == (0, None)
        env.quota_claim.assert_awaited_once_with(env.user_id)
        assert env.notice.await_args.kwargs["kind"] is RoutineNotice.QUOTA
        # The reason is durable before the account is told.
        (calls,) = seen_at_send
        assert "commit" in calls[calls.index("record") :]

    async def test_the_account_is_told_once_per_window(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.usage_blocked.return_value = True
            env.quota_claim.return_value = False
            await execute_single_action(env.action_id, env.user_id)

        # Every skipped slot still shows its reason on the week…
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SKIPPED_QUOTA
        # …but the notice was this account's already.
        env.notice.assert_not_awaited()

    async def test_a_run_the_person_started_is_always_told_what_stopped_it(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.usage_blocked.return_value = True
            env.quota_claim.return_value = False
            env.action.next_trigger_at = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
            await execute_single_action(env.action_id, env.user_id)

        assert env.notice.await_args.kwargs["kind"] is RoutineNotice.QUOTA

    async def test_a_proposal_is_not_sent_past_the_ceiling(self) -> None:
        with (
            _executor_env(chunks=[_chunk("token", "never")]) as env,
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor"
                ".send_approval_notification",
                AsyncMock(),
            ) as propose,
        ):
            env.action.requires_approval = True
            env.usage_blocked.return_value = True
            await execute_single_action(env.action_id, env.user_id)

        propose.assert_not_awaited()
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SKIPPED_QUOTA

    async def test_a_blocked_watch_asks_no_source_and_writes_its_reason_on_its_ledger(
        self,
    ) -> None:
        """A check costs the platform what its source bills (a weather watch):
        past the ceiling it is not made, and the ledger says so in place of the
        run row a check never writes (ADR-322)."""
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            _as_watch(env, seen=("k-seen",))
            env.usage_blocked.return_value = True
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")) as check:
                await execute_single_action(env.action_id, env.user_id)

        check.assert_not_awaited()
        env.run_repo.record.assert_not_awaited()
        state = env.repo.reschedule.await_args.kwargs["condition_state"]
        assert state["last_check_error"] == "quota_blocked"
        assert state["last_checked_at"] == NOW.isoformat()
        # Nothing was read, so nothing seen is forgotten and nothing is served.
        assert state["seen"] == ["k-seen"]

    async def test_a_ceiling_met_inside_the_turn_is_not_a_failure_either(self) -> None:
        with (
            _executor_env(chunks=[]) as env,
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.stream_instruction",
                AsyncMock(return_value=_QUOTA_REFUSAL),
            ),
        ):
            env.quota_claim.return_value = True
            result = await execute_single_action(env.action_id, env.user_id)

        assert result == ""
        env.repo.mark_execution_failure.assert_not_awaited()
        env.repo.reschedule.assert_awaited_once()
        recorded = _recorded(env)
        assert recorded["outcome"] is ScheduledRunOutcome.SKIPPED_QUOTA
        assert recorded["attempts"] == 0
        assert env.notice.await_args.kwargs["kind"] is RoutineNotice.QUOTA

    async def test_a_watch_refused_inside_the_turn_keeps_its_fact_new_and_says_why(self) -> None:
        with (
            _executor_env(chunks=[]) as env,
            patch(
                "src.infrastructure.scheduler.scheduled_action_executor.stream_instruction",
                AsyncMock(return_value=_QUOTA_REFUSAL),
            ),
        ):
            _as_watch(env)
            with _verdict(env, ConditionVerdict(facts=(_NEW,), note_prefix="Mails: ")):
                await execute_single_action(env.action_id, env.user_id)

        env.run_repo.record.assert_not_awaited()
        state = env.repo.reschedule.await_args.kwargs["condition_state"]
        # Still new: the first check past the ceiling serves it.
        assert "k-new" not in state["seen"]
        assert state["last_check_error"] == "quota_blocked"

    async def test_a_tick_that_lost_its_reservation_writes_and_says_nothing(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.usage_blocked.return_value = True
            env.quota_claim.return_value = True
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            await execute_single_action(env.action_id, env.user_id, execution_token=uuid.uuid4())

        env.repo.reschedule.assert_not_awaited()
        env.run_repo.record.assert_not_awaited()
        env.quota_claim.assert_not_awaited()
        env.notice.assert_not_awaited()

    async def test_a_tick_that_is_not_authorized_is_refused_before_the_ceiling_is_asked(
        self,
    ) -> None:
        """An unauthorized tick neither runs nor settles (ADR-335). Asked first,
        the ceiling would re-arm a routine this tick has no right to write on
        and leave a reason on its week."""
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.usage_blocked.return_value = True
            guard = AsyncMock(return_value=False)
            result = await execute_single_action(env.action_id, env.user_id, execution_guard=guard)

        assert result == ""
        guard.assert_awaited_once()
        env.usage_blocked.assert_not_awaited()
        env.repo.reschedule.assert_not_awaited()
        env.run_repo.record.assert_not_awaited()
        env.notice.assert_not_awaited()


#: The occurrence the harness routine was due for, and the one before it.
_DUE = datetime(2026, 8, 3, 6, 0, tzinfo=UTC)
_DUE_THE_DAY_BEFORE = datetime(2026, 8, 2, 6, 0, tzinfo=UTC)
_EXECUTOR = "src.infrastructure.scheduler.scheduled_action_executor"


def _busy() -> Any:
    """The engine found the account's one graph taken by another turn."""
    return patch(
        f"{_EXECUTOR}.stream_instruction", AsyncMock(return_value=RunResult(RunOutcome.BUSY))
    )


class TestAnOccurrenceIsCaughtUpInsideItsWindow:
    """A due occurrence runs late only inside its catch-up window, and an
    account found busy is waited for inside it (ADR-265 amendment 2026-11-12 b)."""

    async def test_an_occurrence_reached_too_late_is_recorded_missed(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.next_trigger_at = _DUE_THE_DAY_BEFORE
            result = await execute_single_action(env.action_id, env.user_id)

        assert result == ""
        env.agent_service.stream_chat_response.assert_not_called()
        # Given up before any ceiling is asked: nothing would run anyway.
        env.usage_blocked.assert_not_awaited()
        recorded = _recorded(env)
        assert recorded["outcome"] is ScheduledRunOutcome.SKIPPED_LATE
        assert recorded["slot_at"] == _DUE_THE_DAY_BEFORE
        assert (recorded["attempts"], recorded["manual"]) == (0, False)
        # Not a failure, and nobody is told: the week says it.
        env.repo.mark_execution_failure.assert_not_awaited()
        env.notice.assert_not_awaited()

    async def test_the_occurrence_that_may_still_start_is_the_one_armed(self) -> None:
        """Today's occurrence is five seconds old: the outage serves TODAY at
        the scheduler's next pass, not tomorrow."""
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.next_trigger_at = _DUE_THE_DAY_BEFORE
            await execute_single_action(env.action_id, env.user_id)

        env.repo.reschedule.assert_awaited_once()
        assert env.repo.reschedule.await_args.args[1] == _DUE

    async def test_an_occurrence_late_inside_its_window_still_runs(self) -> None:
        """A daily occurrence reached ninety minutes late: inside the two hours."""
        with (
            _executor_env(chunks=[_chunk("token", "hello")]) as env,
            patch(f"{_EXECUTOR}.now_utc", return_value=_DUE + timedelta(minutes=90)),
        ):
            await execute_single_action(env.action_id, env.user_id)

        env.agent_service.stream_chat_response.assert_called_once()
        recorded = _recorded(env)
        assert recorded["outcome"] is ScheduledRunOutcome.SUCCESS
        assert recorded["slot_at"] == _DUE

    async def test_past_the_window_by_a_second_it_is_given_up(self) -> None:
        with (
            _executor_env(chunks=[_chunk("token", "never")]) as env,
            patch(f"{_EXECUTOR}.now_utc", return_value=_DUE + timedelta(minutes=120, seconds=1)),
        ):
            await execute_single_action(env.action_id, env.user_id)

        env.agent_service.stream_chat_response.assert_not_called()
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SKIPPED_LATE
        # No later occurrence has come: the next one is tomorrow's.
        assert env.repo.reschedule.await_args.args[1] == _DUE + timedelta(days=1)

    async def test_a_tick_that_lost_the_routine_gives_nothing_up(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.next_trigger_at = _DUE_THE_DAY_BEFORE
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            await execute_single_action(env.action_id, env.user_id, execution_token=uuid.uuid4())

        env.repo.reschedule.assert_not_awaited()
        env.run_repo.record.assert_not_awaited()

    async def test_a_busy_account_keeps_the_occurrence_armed_for_the_next_pass(self) -> None:
        """Re-armed on the NEXT occurrence, a daily routine was lost for a day
        because its owner was typing at 08:00."""
        with _executor_env(chunks=[]) as env, _busy():
            result = await execute_single_action(env.action_id, env.user_id)

        assert result == ""
        env.repo.reschedule.assert_awaited_once()
        assert env.repo.reschedule.await_args.args[1] == _DUE
        # Still pending: its row will be the run's, or the reason it was given up.
        env.run_repo.record.assert_not_awaited()
        env.repo.mark_execution_failure.assert_not_awaited()

    async def test_an_account_still_busy_at_the_end_of_the_window_is_recorded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The next pass would start past the deadline: this attempt is the last."""
        monkeypatch.setattr(settings, "scheduled_actions_catch_up_max_minutes", 2)
        with (
            _executor_env(chunks=[]) as env,
            _busy(),
            patch(f"{_EXECUTOR}.now_utc", return_value=_DUE + timedelta(seconds=90)),
        ):
            await execute_single_action(env.action_id, env.user_id)

        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SKIPPED_BUSY
        env.repo.reschedule.assert_awaited_once()
        # The NEXT occurrence, by the rule every other exit re-arms with.
        assert env.repo.reschedule.await_args.args[1] == _DUE + timedelta(days=1)

    async def test_a_run_the_person_started_is_not_waited_for(self) -> None:
        """No occurrence was due: the pending slot stands, and the row says why
        the test run did nothing."""
        with _executor_env(chunks=[]) as env, _busy():
            env.action.next_trigger_at = datetime(2026, 8, 4, 6, 0, tzinfo=UTC)
            await execute_single_action(env.action_id, env.user_id)

        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SKIPPED_BUSY

    async def test_a_run_the_person_started_runs_whatever_the_age_of_the_pending_slot(
        self,
    ) -> None:
        """« Run now » on a routine whose slot is a day old (the scheduler was down):
        the click is the person's act, never the slot's — it is not given up as missed."""
        with _executor_env(chunks=[_chunk("token", "hello")]) as env:
            env.action.next_trigger_at = _DUE_THE_DAY_BEFORE
            result = await execute_single_action(env.action_id, env.user_id, started_by_person=True)

        assert result == "hello"
        env.agent_service.stream_chat_response.assert_called_once()
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SUCCESS

    async def test_a_due_slot_the_person_ran_is_still_kept_for_a_busy_account(self) -> None:
        """Who started the run changes nothing to the slot: found busy, it stays armed."""
        with _executor_env(chunks=[]) as env, _busy():
            await execute_single_action(env.action_id, env.user_id, started_by_person=True)

        env.repo.reschedule.assert_awaited_once()
        assert env.repo.reschedule.await_args.args[1] == _DUE
        env.run_repo.record.assert_not_awaited()

    async def test_a_tick_that_lost_the_routine_while_waiting_writes_nothing(self) -> None:
        with _executor_env(chunks=[]) as env, _busy():
            env.repo.renew_reservation = AsyncMock(return_value=True)
            env.repo.lock_reserved = AsyncMock(return_value=None)
            await execute_single_action(env.action_id, env.user_id, execution_token=uuid.uuid4())

        env.repo.reschedule.assert_not_awaited()
        env.run_repo.record.assert_not_awaited()


def _declaring_nothing_new() -> list[SimpleNamespace]:
    """A run whose answering model declared its answer says nothing new."""
    return [
        _chunk("token", "Nothing new this morning."),
        SimpleNamespace(type="done", content="", metadata={"nothing_new": True}),
    ]


class TestARoutineToldToNotifyOnlyOfSomethingNew:
    """The run still happens and its answer stays in the chat; what is held
    back is the notification (ADR-265 amendment 2026-11-12 c)."""

    async def test_a_run_with_nothing_new_is_recorded_and_not_pushed(self) -> None:
        with _executor_env(chunks=_declaring_nothing_new()) as env:
            env.action.notify_only_when_new = True
            result = await execute_single_action(env.action_id, env.user_id)

        # The run is a run: answered, counted, on the week.
        assert result == "Nothing new this morning."
        env.repo.mark_execution_success.assert_awaited_once()
        assert _recorded(env)["outcome"] is ScheduledRunOutcome.SUCCESS
        # Its owner asked not to be told: neither push nor toast.
        env.fcm.send_to_user.assert_not_awaited()
        env.redis.publish.assert_not_awaited()
        env.notice.assert_not_awaited()

    async def test_the_answering_model_is_told_only_for_such_a_routine(self) -> None:
        asked: list[bool] = []

        async def _engine(request: Any, *_a: Any, **_k: Any) -> RunResult:
            asked.append(request.quiet_when_nothing_new)
            return RunResult(RunOutcome.SUCCESS, text="ok", attempts=1)

        for option in (True, False):
            with _executor_env(chunks=[]) as env, patch(f"{_EXECUTOR}.stream_instruction", _engine):
                env.action.notify_only_when_new = option
                await execute_single_action(env.action_id, env.user_id)

        assert asked == [True, False]

    async def test_a_run_with_something_to_say_is_pushed(self) -> None:
        with _executor_env(chunks=[_chunk("token", "Two invoices arrived.")]) as env:
            env.action.notify_only_when_new = True
            await execute_single_action(env.action_id, env.user_id)

        env.fcm.send_to_user.assert_awaited_once()

    async def test_a_declaration_nobody_asked_for_silences_nothing(self) -> None:
        """The routine tells everything: a tag the model wrote unasked is not
        this routine's owner asking for silence."""
        with _executor_env(chunks=_declaring_nothing_new()) as env:
            await execute_single_action(env.action_id, env.user_id)

        env.fcm.send_to_user.assert_awaited_once()

    async def test_a_failure_is_always_told(self) -> None:
        with _executor_env(chunks=[]) as env:
            env.action.notify_only_when_new = True
            await _fail(env, marked=_marked(1))

        assert env.notice.await_args.kwargs["kind"] is RoutineNotice.FAILED
