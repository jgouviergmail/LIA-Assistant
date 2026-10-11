"""Natural 'save the last answer' resolves a real visible archived id before confirmation."""

import pytest

from src.core.config import settings
from src.domains.agents.application.bookmark_keep import (
    execute_bookmark_keep,
    prepare_bookmark_keep,
)
from src.domains.agents.application.bookmark_keep_schemas import (
    BookmarkKeepInput,
    BookmarkKeepPatch,
)
from src.domains.agents.application.command_service import CommandRejected
from src.domains.bookmarks.service import BookmarkService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.bookmarks.test_bookmarks_db import _conversation, _message, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("deleted", [False, True])
async def test_latest_selection_excludes_foreign_hidden_user_and_deleted_conversation_rows(
    async_session, test_user, monkeypatch, deleted
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_max_per_user", 100)
    conversation = await _conversation(async_session, test_user)
    wanted = await _message(
        async_session,
        conversation,
        role="assistant",
        content="Actual last visible answer",
        minutes=1,
    )
    await _message(
        async_session,
        conversation,
        role="assistant",
        content="Hidden run answer",
        minutes=5,
        hidden=True,
    )
    await _message(async_session, conversation, role="user", content="Save that answer", minutes=6)
    foreign = await _conversation(async_session, await _user(async_session))
    await _message(async_session, foreign, role="assistant", content="Foreign answer", minutes=10)
    if deleted:
        conversation.deleted_at = wanted.created_at
    await async_session.flush()
    if deleted:
        with pytest.raises(CommandRejected, match="NOT_FOUND_OR_UNAUTHORIZED"):
            await prepare_bookmark_keep(async_session, test_user.id, BookmarkKeepInput())
        return
    draft = await prepare_bookmark_keep(async_session, test_user.id, BookmarkKeepInput())
    selected = BookmarkKeepPatch.model_validate(draft.intent).saved_answer_to_keep
    assert selected.request.message_id == wanted.id
    assert selected.answer_preview == "Actual last visible answer"
    await async_session.commit()
    later = await _message(
        async_session, conversation, role="assistant", content="Later unapproved answer", minutes=30
    )
    await async_session.commit()
    monkeypatch.setattr(
        "src.domains.agents.application.bookmark_keep.enqueue_bookmark_index", lambda identity: None
    )
    receipt = PreferenceWriteReceipt()
    await execute_bookmark_keep(async_session, test_user.id, draft, receipt)
    assert receipt.committed
    assert (
        await BookmarkService(async_session).repository.get_by_message(test_user.id, later.id)
        is None
    )
    kept = await BookmarkService(async_session).repository.get_by_message(test_user.id, wanted.id)
    assert kept.content == "Actual last visible answer"
