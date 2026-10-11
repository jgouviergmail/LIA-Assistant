"""Saved-answer tools read the UI projection, literal search and explicit content windows."""

from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import delete

from src.core.config import settings
from src.core.exceptions import AuthorizationError
from src.domains.agents.application import bookmark_read
from src.domains.agents.application.bookmark_read import read_bookmarks
from src.domains.agents.application.bookmark_read_schemas import BookmarkReadQuery
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.tools import application_bookmark_tools
from src.domains.bookmarks.models import MessageBookmark
from src.domains.bookmarks.router import list_bookmarks
from src.domains.chat.models import MessageTokenSummary
from src.domains.rag_spaces.models import RAGDocumentStatus
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.bookmarks.test_bookmarks_db import (
    _bookmark,
    _document,
    _space,
    _user,
)

pytestmark = pytest.mark.integration


async def test_saved_answer_costs_and_projection_never_follow_foreign_links(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    foreign = await _user(async_session)
    space = await _space(async_session, foreign)
    document = await _document(async_session, foreign, space, RAGDocumentStatus.READY)
    document.embedding_tokens = 999
    document.embedding_cost_eur = 1
    run_id = str(uuid4())
    summary = MessageTokenSummary(
        user_id=foreign.id, run_id=run_id, session_id="foreign-test-session", conversation_id=None
    )
    async_session.add(summary)
    kept = await _bookmark(async_session, test_user, None, content="Owned answer")
    kept.rag_document_id = document.id
    kept.run_id = run_id
    await async_session.flush()
    result = await read_bookmarks(async_session, test_user.id, BookmarkReadQuery())
    assert result.page.items[0].content == "Owned answer"
    assert result.page.items[0].index_usage is None
    assert result.page.items[0].answer_usage is None


@pytest.mark.parametrize("change", ["disabled", "revoked", "removed", "oversized"])
async def test_saved_answer_rechecks_authority_rows_and_payload_after_fetch(
    async_session, test_user, monkeypatch, change
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    kept = await _bookmark(async_session, test_user, None)
    owner, identity = test_user.id, kept.id
    original = bookmark_read.read_bookmark_page

    async def changed(*args):
        page = await original(*args)
        if change == "disabled":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif change == "revoked":
            test_user.is_active = False
            await async_session.flush()
        elif change == "removed":
            await async_session.execute(
                delete(MessageBookmark).where(MessageBookmark.id == identity)
            )
        else:
            monkeypatch.setattr(bookmark_read, "BOOKMARK_READ_MAX_BYTES", 1)
        return page

    monkeypatch.setattr(bookmark_read, "read_bookmark_page", changed)
    with pytest.raises((AuthorizationError, CommandRejected, ValueError)):
        await read_bookmarks(async_session, owner, BookmarkReadQuery())


async def test_owned_saved_answers_match_ui_and_page_literal_search(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "bookmarks_enabled", False)
    for i in range(3):
        await _bookmark(async_session, test_user, None, content=f"Literal_%_{i}")
    await _bookmark(async_session, await _user(async_session), None, content="Foreign_%_")
    query = BookmarkReadQuery(q="_%_", limit=2)
    result = await read_bookmarks(async_session, test_user.id, query)
    ui = await list_bookmarks(user=test_user, db=async_session, q="_%_", limit=2, offset=0)
    assert result.page == ui and result.next_offset == 2 and result.page.total == 3
    final = await read_bookmarks(
        async_session, test_user.id, BookmarkReadQuery(q="_%_", limit=2, offset=2)
    )
    assert len(final.page.items) == 1 and final.next_offset is None
    assert "Foreign" not in result.model_dump_json()


async def test_large_answer_is_readable_in_explicit_windows_without_lying_about_completeness(
    async_session, test_user, monkeypatch
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    original = "界" * 30_000
    kept = await _bookmark(async_session, test_user, None, content=original)
    output = ""
    for start in range(0, len(original), 10_000):
        result = await read_bookmarks(
            async_session, test_user.id, BookmarkReadQuery(limit=1, content_offset=start)
        )
        output += result.page.items[0].content
        window = result.content_windows[str(kept.id)].content
        assert window.total_chars == len(original) and window.offset == start
    assert output == original and window.next_offset is None


@pytest.mark.parametrize("reason", ["disabled", "revoked"])
async def test_saved_answer_read_requires_fresh_native_authority(
    async_session, test_user, monkeypatch, reason
):
    monkeypatch.setattr(settings, "application_tools_enabled", reason != "disabled")
    if reason == "revoked":
        test_user.is_active = False
        await async_session.flush()
    with pytest.raises(AuthorizationError):
        await read_bookmarks(async_session, test_user.id, BookmarkReadQuery())


@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_actual_saved_answer_tool_has_no_draft_or_spending(
    async_session, test_user, monkeypatch, mode
):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    actor = test_user.id
    await _bookmark(async_session, test_user, None, content="Actual kept answer")

    @asynccontextmanager
    async def database():
        yield async_session

    monkeypatch.setattr(application_bookmark_tools, "get_db_context", database)
    with installed_runtime_context(user_id=actor, deps=object(), execution_mode=mode):
        result = await application_bookmark_tools.get_lia_saved_answers_tool.coroutine(
            query=BookmarkReadQuery(),
            runtime=make_tool_runtime(user_id=actor, store=InMemoryStore(), execution_mode=mode),
        )
    assert result.success and result.structured_data["page"]["total"] == 1
    assert not result.registry_updates and not result.metadata.get("requires_confirmation")
