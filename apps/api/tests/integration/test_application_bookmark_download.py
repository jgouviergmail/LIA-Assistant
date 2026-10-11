"""Saved-copy download seals all Markdown bytes without indexing or exposing content to a model."""

from unittest.mock import AsyncMock

import pytest

from src.core.config import settings
from src.domains.agents.application.bookmark_download import (
    open_bookmark_download,
    prepare_bookmark_download,
)
from src.domains.agents.application.bookmark_download_schemas import BookmarkDownloadInput
from src.domains.agents.application.command_service import CommandRejected
from tests.helpers.runtime_context import installed_runtime_context
from tests.integration.domains.bookmarks.test_bookmarks_db import _bookmark

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("changed", [False, True])
async def test_bookmark_download_binds_complete_copy_and_refuses_changed_text(
    async_session, test_user, monkeypatch, changed
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    owner = test_user.id
    saved = await _bookmark(
        async_session,
        test_user,
        None,
        content="Complete saved answer " * 5_000,
        request_content="Original whole request",
    )
    await async_session.commit()
    # Original browser identity is validated at the existing management-export seam.
    monkeypatch.setattr(
        "src.domains.agents.application.bookmark_download.authorize_management_export", AsyncMock()
    )
    with installed_runtime_context(user_id=owner, deps=object()):
        draft = await prepare_bookmark_download(
            async_session, owner, BookmarkDownloadInput(bookmark_id=saved.id)
        )
    assert len(draft.model_dump_json()) < 10_000
    if changed:
        saved.content = "Different copied answer"
        await async_session.commit()
    if changed:
        with pytest.raises(CommandRejected):
            await open_bookmark_download(async_session, owner, draft)
    else:
        selected = await open_bookmark_download(async_session, owner, draft)
        chunks = []
        try:
            while part := await selected.reader.read_chunk():
                chunks.append(part)
        finally:
            await selected.reader.close()
        content = b"".join(chunks).decode("utf-8")
        assert saved.content.rstrip() in content and "Original whole request" in content
        assert selected.content_type.startswith("text/markdown")
