"""Heartbeat integration of the open-loops ledger (P5, Lot 2).

Covers the nudge-worthiness matrix of the fetcher, the context rendering,
and the post-notification cooldown bump.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domains.heartbeat.context_sources import fetch_open_loops_context
from src.domains.heartbeat.proactive_task import HeartbeatProactiveTask
from src.domains.heartbeat.schemas import HeartbeatContext, HeartbeatDecision
from src.infrastructure.proactive.base import ProactiveTaskResult

NOW = datetime.now(UTC)


def _settings(**overrides):
    defaults = {
        "open_loops_enabled": True,
        "open_loops_max_open_per_user": 30,
        "open_loops_nudge_due_hours": 48,
        "open_loops_nudge_stale_days": 7,
        "open_loops_nudge_cooldown_days": 3,
        "open_loops_expiry_days": 21,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _loop(
    *,
    subject: str = "rappeler le plombier",
    due_hint: datetime | None = None,
    updated_at: datetime | None = None,
    last_nudged_at: datetime | None = None,
    direction: str = "user_owes",
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        subject=subject,
        counterparty="le plombier",
        direction=direction,
        due_hint=due_hint,
        updated_at=updated_at or NOW,
        created_at=NOW - timedelta(days=1),
        last_nudged_at=last_nudged_at,
    )


def _user():
    return SimpleNamespace(timezone="Europe/Paris")


async def _fetch(loops, settings=None):
    repo = MagicMock()
    repo.expire_stale = AsyncMock(return_value=0)
    repo.list_open_for_user = AsyncMock(return_value=loops)
    with patch("src.domains.open_loops.repository.OpenLoopRepository", return_value=repo):
        result = await fetch_open_loops_context(
            MagicMock(), uuid.uuid4(), _user(), settings or _settings()
        )
    return result, repo


@pytest.mark.unit
class TestFetchOpenLoopsContext:
    """Nudge-worthiness matrix."""

    async def test_flag_off_returns_none(self):
        result, _ = await _fetch([], settings=_settings(open_loops_enabled=False))
        assert result is None

    async def test_due_soon_is_included(self):
        result, _ = await _fetch([_loop(due_hint=NOW + timedelta(hours=12))])
        assert result is not None
        assert result[0]["subject"] == "rappeler le plombier"
        assert result[0]["direction"] == "user_owes"

    async def test_overdue_is_included(self):
        result, _ = await _fetch([_loop(due_hint=NOW - timedelta(days=1))])
        assert result is not None

    async def test_stale_without_deadline_is_included(self):
        result, _ = await _fetch([_loop(due_hint=None, updated_at=NOW - timedelta(days=10))])
        assert result is not None

    async def test_fresh_without_deadline_is_excluded(self):
        result, _ = await _fetch([_loop(due_hint=None, updated_at=NOW)])
        assert result is None

    async def test_cooldown_excludes_even_when_due(self):
        result, _ = await _fetch(
            [
                _loop(
                    due_hint=NOW + timedelta(hours=2),
                    last_nudged_at=NOW - timedelta(hours=12),
                )
            ]
        )
        assert result is None

    async def test_cooldown_elapsed_reincludes(self):
        result, _ = await _fetch(
            [
                _loop(
                    due_hint=NOW + timedelta(hours=2),
                    last_nudged_at=NOW - timedelta(days=5),
                )
            ]
        )
        assert result is not None

    async def test_lazy_expiry_runs_before_listing(self):
        _, repo = await _fetch([])
        repo.expire_stale.assert_awaited_once()
        cutoff = repo.expire_stale.await_args.kwargs["cutoff"]
        assert cutoff < NOW - timedelta(days=20)

    async def test_entries_carry_id_for_post_notify_bump(self):
        loop = _loop(due_hint=NOW + timedelta(hours=12))
        result, _ = await _fetch([loop])
        assert result[0]["id"] == str(loop.id)


@pytest.mark.unit
class TestOpenLoopsContextRendering:
    """Prompt section + source label."""

    def test_prompt_section_renders_direction_and_subject(self):
        ctx = HeartbeatContext(
            open_loops=[
                {
                    "id": "x",
                    "subject": "rappeler le plombier",
                    "counterparty": "le plombier",
                    "direction": "user_owes",
                    "due_local": "2026-07-23 18:00",
                    "days_open": 3,
                },
                {
                    "id": "y",
                    "subject": "devis de Marie",
                    "counterparty": "Marie",
                    "direction": "waiting_on_other",
                    "due_local": None,
                    "days_open": 9,
                },
            ]
        )
        rendered = ctx.to_prompt_context()
        assert "OPEN LOOPS" in rendered
        assert "rappeler le plombier" in rendered
        assert "waiting_on_other" in rendered

    def test_open_loops_alone_are_meaningful(self):
        ctx = HeartbeatContext(open_loops=[{"id": "x", "subject": "s", "direction": "user_owes"}])
        assert ctx.has_meaningful_context() is True

    def test_decision_accepts_open_loops_label(self):
        decision = HeartbeatDecision(
            action="notify",
            reason="loop due",
            message_draft="N'oublie pas le plombier !",
            sources_used=["OPEN_LOOPS"],
        )
        assert decision.sources_used == ["OPEN_LOOPS"]


def _patch_db():
    @asynccontextmanager
    async def _ctx():
        session = MagicMock()
        session.commit = AsyncMock()
        yield session

    return patch("src.domains.heartbeat.proactive_task.get_db_context", new=_ctx)


def _patch_store():
    store = AsyncMock()
    return patch(
        "src.domains.agents.context.store.get_tool_context_store",
        new=AsyncMock(return_value=store),
    )


def _result(metadata: dict) -> ProactiveTaskResult:
    return ProactiveTaskResult(
        success=True,
        content="notification body",
        target_id="hbtest",
        metadata=metadata,
    )


@pytest.mark.unit
class TestPostNotifyBump:
    """last_nudged_at bump when a delivered notification used OPEN_LOOPS."""

    async def test_bump_when_source_used(self):
        task = HeartbeatProactiveTask()
        loop_id = uuid.uuid4()

        with (
            _patch_db(),
            _patch_store(),
            patch(
                "src.domains.heartbeat.repository.HeartbeatNotificationRepository"
            ) as hb_repo_cls,
            patch("src.domains.open_loops.repository.OpenLoopRepository") as loop_repo_cls,
        ):
            hb_repo_cls.return_value.create = AsyncMock()
            loop_repo_cls.return_value.bump_nudged = AsyncMock()

            await task.on_notification_sent(
                uuid.uuid4(),
                MagicMock(),
                _result(
                    {
                        "sources_used": ["OPEN_LOOPS", "UPCOMING_CALENDAR_EVENTS"],
                        "open_loop_ids": [str(loop_id)],
                    }
                ),
            )

            bumped = loop_repo_cls.return_value.bump_nudged.await_args.args[0]
            assert bumped == [loop_id]

    async def test_no_bump_when_source_not_used(self):
        task = HeartbeatProactiveTask()

        with (
            _patch_db(),
            _patch_store(),
            patch(
                "src.domains.heartbeat.repository.HeartbeatNotificationRepository"
            ) as hb_repo_cls,
            patch("src.domains.open_loops.repository.OpenLoopRepository") as loop_repo_cls,
        ):
            hb_repo_cls.return_value.create = AsyncMock()
            loop_repo_cls.return_value.bump_nudged = AsyncMock()

            await task.on_notification_sent(
                uuid.uuid4(),
                MagicMock(),
                _result(
                    {
                        "sources_used": ["CURRENT_WEATHER"],
                        "open_loop_ids": [str(uuid.uuid4())],
                    }
                ),
            )

            loop_repo_cls.return_value.bump_nudged.assert_not_awaited()
