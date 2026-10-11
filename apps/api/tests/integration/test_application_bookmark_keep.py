"""Confirmed saved-answer copies are exact, quota-bound and indexed only after known commit."""

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application.bookmark_keep import (
    execute_bookmark_keep,
    prepare_bookmark_keep,
)
from src.domains.agents.application.bookmark_keep_schemas import BookmarkKeepInput
from src.domains.agents.application.command_service import CommandRejected
from src.domains.bookmarks.models import MessageBookmark
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.bookmarks.test_bookmarks_db import _conversation, _message

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "enqueue_failed",
        "source_changed",
        "request_changed",
        "disabled",
        "keep_off",
        "revoked",
        "expired",
        "quota_changed",
        "ack_lost",
        "cancelled",
    ],
)
async def test_native_keep_seals_copy_and_waits_for_known_ack(
    async_session, test_user, monkeypatch, scenario
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_max_per_user", 100)
    actor = test_user.id
    conversation = await _conversation(async_session, test_user)
    request_message = await _message(
        async_session, conversation, role="user", content="Actual request", minutes=0
    )
    message = await _message(
        async_session, conversation, role="assistant", content="Actual answer", minutes=1
    )
    await async_session.commit()
    draft = await prepare_bookmark_keep(
        async_session, actor, BookmarkKeepInput(message_id=message.id)
    )
    await async_session.commit()
    if scenario == "source_changed":
        message.content = "Different answer"
        await async_session.commit()
    elif scenario == "request_changed":
        request_message.content = "Different request"
        await async_session.commit()
    elif scenario == "disabled":
        monkeypatch.setattr(settings, "application_tools_enabled", False)
    elif scenario == "keep_off":
        monkeypatch.setattr(settings, "bookmarks_enabled", False)
    elif scenario == "revoked":
        test_user.is_active = False
        await async_session.commit()
    elif scenario == "expired":
        draft = draft.model_copy(update={"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    elif scenario == "quota_changed":
        monkeypatch.setattr(settings, "bookmarks_max_per_user", 99)
    commit_original = async_session.commit
    acknowledged = False
    scheduled = []

    async def commit():
        nonlocal acknowledged
        await commit_original()
        if scenario == "ack_lost":
            raise OSError("Controlled lost acknowledgement")
        if scenario == "cancelled":
            raise asyncio.CancelledError()
        acknowledged = True

    def enqueue(identity):
        assert acknowledged
        if scenario == "enqueue_failed":
            raise OSError("Controlled scheduling failure after commit")
        scheduled.append(identity)

    monkeypatch.setattr(async_session, "commit", commit)
    monkeypatch.setattr(
        "src.domains.agents.application.bookmark_keep.enqueue_bookmark_index", enqueue
    )
    receipt = PreferenceWriteReceipt()
    if scenario in {"valid", "enqueue_failed"}:
        await execute_bookmark_keep(async_session, actor, draft, receipt)
        assert receipt.committed and len(scheduled) == int(scenario == "valid")
        assert receipt.values["saved_answer_to_keep"]["indexing_pending"]
        kept = await async_session.scalar(
            select(MessageBookmark).where(MessageBookmark.user_id == actor)
        )
        assert kept.content == "Actual answer" and kept.request_content == "Actual request"
    else:
        with pytest.raises((CommandRejected, AuthorizationError)):
            await execute_bookmark_keep(async_session, actor, draft, receipt)
        await async_session.rollback()
        assert not receipt.committed and not scheduled
    count = await async_session.scalar(
        select(func.count(MessageBookmark.id)).where(MessageBookmark.user_id == actor)
    )
    assert count == int(scenario in {"valid", "enqueue_failed", "ack_lost", "cancelled"})
