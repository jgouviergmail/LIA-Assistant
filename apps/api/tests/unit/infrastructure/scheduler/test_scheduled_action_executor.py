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
from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.config import settings
from src.core.recurrence import DailyTimes, RecurrenceSpec, TimeOfDay
from src.domains.scheduled_actions.models import ScheduledRunOutcome
from src.domains.users.schemas import UserProfile
from src.infrastructure.scheduler.scheduled_action_executor import execute_single_action

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

    async def _record(**_kwargs: Any) -> str:
        calls.append("record")
        return "row"

    run_repo = MagicMock()
    run_repo.record = AsyncMock(side_effect=_record)

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
    agent_service.stream_chat_response = Mock(side_effect=_make_stream(chunks))

    fcm = MagicMock(send_to_user=AsyncMock())
    redis = MagicMock(publish=AsyncMock())

    with ExitStack() as stack:
        for target, replacement in (
            ("src.infrastructure.database.session.get_db_context", _AsyncCM(db)),
            ("src.domains.scheduled_actions.repository.ScheduledActionRepository", repo),
            ("src.domains.users.service.UserService", user_service),
            ("src.domains.conversations.service.ConversationService", conv_service),
            ("src.domains.agents.api.service.AgentService", agent_service),
            ("src.domains.notifications.service.FCMNotificationService", fcm),
            ("src.domains.scheduled_actions.runs.ScheduledActionRunRepository", run_repo),
        ):
            stack.enter_context(patch(target, return_value=replacement))

        stack.enter_context(
            patch(
                "src.domains.usage_limits.service.UsageLimitService.is_user_blocked_for_llm",
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
        )


def _sse_payload(env: _Env) -> dict[str, Any]:
    """Decode the JSON published on the user's notification channel."""
    import json

    env.redis.publish.assert_awaited_once()
    _channel, raw = env.redis.publish.await_args.args
    return json.loads(raw)


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
            # Flushed inside the routine's transaction, before its commit.
            assert env.calls.index("record") < env.calls.index("commit")

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
            assert env.calls.index("record") < env.calls.index("commit")

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
    async def test_a_condition_not_met_is_recorded_as_skipped_and_runs_nothing(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.trigger_kind = "condition"
            env.action.condition_config = {"type": "task_overdue"}
            verdict = SimpleNamespace(met=False, fingerprint=None, note=None)
            with patch(
                "src.infrastructure.scheduler.condition_evaluators.evaluate_condition",
                AsyncMock(return_value=verdict),
            ):
                result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert result == ""
            env.agent_service.stream_chat_response.assert_not_called()
            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.SKIPPED_CONDITION
            assert recorded["attempts"] == 0
            assert recorded["slot_at"] == env.action.next_trigger_at
            assert env.calls.index("record") < env.calls.index("commit")

    @pytest.mark.asyncio
    async def test_a_proposal_is_recorded_as_proposed(self) -> None:
        with _executor_env(chunks=[_chunk("token", "never")]) as env:
            env.action.requires_approval = True
            with patch(
                "src.infrastructure.scheduler.scheduled_action_executor"
                "._send_approval_notification",
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
                AsyncMock(return_value={"action_requests": [{"type": "clarification"}]}),
            ),
        ):
            await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            env.agent_service.stream_chat_response.assert_not_called()
            recorded = _recorded(env)
            assert recorded["outcome"] is ScheduledRunOutcome.SKIPPED_HITL
            assert recorded["attempts"] == 0

    @pytest.mark.asyncio
    async def test_a_failed_history_write_never_costs_the_routine_its_marking(self) -> None:
        with _executor_env(chunks=[_chunk("token", "hello")]) as env:
            env.run_repo.record = AsyncMock(side_effect=RuntimeError("history down"))
            result = await execute_single_action(action_id=env.action_id, user_id=env.user_id)

            assert result == "hello"
            env.repo.mark_execution_success.assert_awaited_once()
            assert "commit" in env.calls


class TestRetentionPurge:
    @pytest.mark.asyncio
    async def test_the_tick_purges_history_older_than_the_retention(self) -> None:
        from src.infrastructure.scheduler import scheduled_action_executor as mod

        mock_db = AsyncMock()
        repo = MagicMock()
        repo.recover_stale_executing = AsyncMock(return_value=0)
        repo.get_and_lock_due_actions = AsyncMock(return_value=[])
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
        ):
            stats = await mod.process_scheduled_actions()

        assert stats["runs_purged"] == 3
        from datetime import timedelta

        run_repo.purge_older_than.assert_awaited_once_with(
            NOW - timedelta(days=settings.scheduled_actions_runs_retention_days)
        )

    @pytest.mark.asyncio
    async def test_a_failed_purge_never_fails_the_tick(self) -> None:
        from src.infrastructure.scheduler import scheduled_action_executor as mod

        mock_db = AsyncMock()
        repo = MagicMock()
        repo.recover_stale_executing = AsyncMock(return_value=0)
        repo.get_and_lock_due_actions = AsyncMock(return_value=[])
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
        ):
            stats = await mod.process_scheduled_actions()

        assert stats["runs_purged"] == 0
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

    def test_the_executor_calls_the_engine_from_a_single_site(self) -> None:
        import ast
        import inspect
        from pathlib import Path

        from src.infrastructure.scheduler import scheduled_action_executor

        source = Path(inspect.getfile(scheduled_action_executor)).read_text(encoding="utf-8")
        calls = [
            node
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "rearm_after"
        ]
        assert len(calls) == 1, (
            f"`rearm_after` is called from {len(calls)} sites; route every exit through the "
            "single helper so the five exits cannot re-arm differently"
        )
