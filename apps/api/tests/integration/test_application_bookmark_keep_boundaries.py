"""Native saving respects source visibility, existing copies and truthful post-ack indexing."""

import pytest

from src.core.config import settings
from src.core.exceptions import ResourceNotFoundError, ValidationError
from src.domains.agents.application.bookmark_keep import (
    execute_bookmark_keep,
    prepare_bookmark_keep,
)
from src.domains.agents.application.bookmark_keep_schemas import BookmarkKeepInput
from src.domains.bookmarks.service import BookmarkService
from src.domains.users.preference_cas import PreferenceWriteReceipt
from tests.integration.domains.bookmarks.test_bookmarks_db import _conversation, _message, _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("reason", ["foreign", "user_message", "hidden", "empty"])
async def test_only_owned_visible_nonempty_assistant_answers_can_be_saved(
    async_session, test_user, monkeypatch, reason
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    actor = test_user.id
    owner = await _user(async_session) if reason == "foreign" else test_user
    conversation = await _conversation(async_session, owner)
    answer = await _message(
        async_session,
        conversation,
        role="user" if reason == "user_message" else "assistant",
        content=" " if reason == "empty" else "Actual answer",
        minutes=1,
        hidden=reason == "hidden",
    )
    with pytest.raises((ResourceNotFoundError, ValidationError)):
        await prepare_bookmark_keep(async_session, actor, BookmarkKeepInput(message_id=answer.id))


@pytest.mark.parametrize("existing", [False, True])
async def test_large_answer_is_fully_sealed_and_existing_copy_does_not_reindex(
    async_session, test_user, monkeypatch, existing
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_max_per_user", 1)
    actor = test_user.id
    conversation = await _conversation(async_session, test_user)
    content = "A" * 100_000
    answer = await _message(
        async_session, conversation, role="assistant", content=content, minutes=1
    )
    await async_session.commit()
    if existing:
        await BookmarkService(async_session).keep(actor, answer.id, commit=False)
        await async_session.commit()
    draft = await prepare_bookmark_keep(
        async_session, actor, BookmarkKeepInput(message_id=answer.id)
    )
    assert len(draft.model_dump_json()) < 10_000
    await async_session.commit()
    calls = []
    monkeypatch.setattr(
        "src.domains.agents.application.bookmark_keep.enqueue_bookmark_index", calls.append
    )
    receipt = PreferenceWriteReceipt()
    await execute_bookmark_keep(async_session, actor, draft, receipt)
    assert receipt.committed and receipt.no_op is existing and len(calls) == int(not existing)
    saved = await BookmarkService(async_session).repository.get_by_message(actor, answer.id)
    assert saved.content == content
