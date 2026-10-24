"""A durable state follows a durable delivery, or nothing follows at all (audit AC-003).

``NotificationDispatcher.dispatch`` absorbs every channel failure and RETURNS its
verdict. Five consumers ignored that verdict and wrote « delivered ». The verdict
they need has one definition — archived, pushed, or sent on an external channel;
an SSE event alone reaches an open tab or nobody (owner decision 2026-10-22) — and
``require_durable=True`` turns its absence into an exception their failure path
already handles. Every test runs the REAL ``dispatch`` over scripted channels.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.infrastructure.proactive.notification import (
    NotificationNotDelivered,
    NotificationResult,
)
from tests.helpers.notifications import ScriptedChannels, ScriptedDispatcher, sse_only

pytestmark = pytest.mark.unit


def _user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid4(), language="fr")


async def _dispatch(
    channels: ScriptedChannels,
    *,
    require_durable: bool,
    commit: AsyncMock | None = None,
    commit_before_notification: bool = True,
) -> NotificationResult:
    db = AsyncMock(spec=AsyncSession)
    db.commit = commit if commit is not None else AsyncMock()
    return await ScriptedDispatcher(channels).dispatch(
        user=_user(),
        content="Your call is done.",
        task_type="phone_call",
        target_id="call-1",
        metadata={},
        db=db,
        title="Call",
        commit_before_notification=commit_before_notification,
        require_durable=require_durable,
    )


class TestTheDurablePredicate:
    @pytest.mark.parametrize(
        "result",
        [
            NotificationResult(archived=True),
            NotificationResult(fcm_success=1),
            NotificationResult(channel_sent=1),
        ],
        ids=["archived", "pushed", "external-channel"],
    )
    def test_a_channel_the_person_finds_later_is_durable(self, result: NotificationResult) -> None:
        assert result.durably_delivered

    def test_an_sse_event_alone_is_not(self) -> None:
        result = NotificationResult(sse_sent=True)
        assert not result.durably_delivered


class TestRequireDurable:
    @pytest.mark.parametrize(
        "channels",
        [
            ScriptedChannels(archived=True),
            ScriptedChannels(archived=False, fcm_success=2),
            ScriptedChannels(archived=False, sse=False, channel_sent=1),
        ],
        ids=["archived", "pushed", "external-channel"],
    )
    async def test_a_durable_delivery_returns_its_result(self, channels: ScriptedChannels) -> None:
        result = await _dispatch(channels, require_durable=True)
        assert result.durably_delivered

    @pytest.mark.parametrize(
        "channels",
        [
            sse_only(),
            ScriptedChannels(archived=False, sse=False),
            ScriptedChannels(archive_error=RuntimeError("archive down"), sse=True),
        ],
        ids=["sse-only", "nothing", "archive-raised"],
    )
    async def test_no_durable_channel_raises_with_the_verdict(
        self, channels: ScriptedChannels
    ) -> None:
        with pytest.raises(NotificationNotDelivered) as raised:
            await _dispatch(channels, require_durable=True)

        assert not raised.value.result.durably_delivered
        assert "archived=False" in str(raised.value)

    async def test_without_the_flag_the_verdict_is_returned_as_before(self) -> None:
        result = await _dispatch(sse_only(), require_durable=False)

        assert result.sse_sent and not result.durably_delivered

    async def test_a_cancellation_is_never_absorbed(self) -> None:
        channels = ScriptedChannels(archive_error=asyncio.CancelledError())

        with pytest.raises(asyncio.CancelledError):
            await _dispatch(channels, require_durable=True)

    async def test_an_archive_whose_commit_failed_is_not_durable(self) -> None:
        """Archived means COMMITTED: a commit that failed kept nothing the person finds."""
        commit = AsyncMock(side_effect=ConnectionError("database gone"))

        with pytest.raises(NotificationNotDelivered) as raised:
            await _dispatch(ScriptedChannels(archived=True), require_durable=True, commit=commit)

        assert not raised.value.result.archived
        assert raised.value.result.message_id is None  # a rolled-back row has no id to show

    async def test_an_archive_left_to_the_caller_joins_its_transaction(self) -> None:
        """Without the dispatcher's commit, the row and the caller's state commit together."""
        commit = AsyncMock()

        result = await _dispatch(
            ScriptedChannels(archived=True),
            require_durable=True,
            commit=commit,
            commit_before_notification=False,
        )

        assert result.archived
        commit.assert_not_awaited()
