"""Whole-journal portability is an exact original-browser, source-authorized continuation."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export_schemas import ManagementExportRequest
from src.domains.agents.application.management_export_service import serve_management_export_command
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_management_export_tools import export_lia_journals_tool
from src.domains.journals.models import JournalEntry
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize(
    "scenario",
    [
        "json",
        "csv",
        "changed",
        "portrait_changed",
        "new_entry",
        "disabled",
        "other_origin",
        "no_confirmation",
    ],
)
async def test_journal_export_requires_exact_confirmation_session_source_and_stored_portrait(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    actor_id = test_user.id
    monkeypatch.setattr(settings, "journals_enabled", True)
    test_user.journals_enabled = False
    test_user.journal_portrait_full = "Stored historical portrait secret"
    row = JournalEntry(
        user_id=actor_id, theme="learnings", title="=1+1", content="Owned journal", char_count=13
    )
    archived = JournalEntry(
        user_id=actor_id,
        theme="learnings",
        title="Archived",
        content="Archived journal",
        char_count=16,
        status="archived",
    )
    async_session.add_all([row, archived])
    await async_session.commit()
    row_id = row.id
    store = SessionStore(await get_redis_session())
    first = await store.create_session(str(actor_id))
    second = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, first.session_id)

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    for module in ["command_service", "draft_execution", "secure_continuation"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr(
        "src.domains.agents.tools.application_management_export_tools.get_db_context", session
    )
    try:
        format = "csv" if scenario == "csv" else "json"
        with installed_runtime_context(user_id=actor_id, application_origin=origin):
            proposal = await export_lia_journals_tool.coroutine(
                request=ManagementExportRequest(format=format),
                runtime=make_tool_runtime(
                    user_id=actor_id, application_origin=origin, store=InMemoryStore()
                ),
            )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert draft.intent["management_export"]["selected_count"] == 2
        assert (
            "=1+1" not in str(draft.intent)
            and "Stored historical portrait secret" not in str(proposal)
            and "Owned journal" not in str(proposal)
        )
        if scenario != "no_confirmation":
            with (
                installed_runtime_context(
                    user_id=actor_id, application_origin=origin, deps=object()
                ),
                patch.dict(draft_executor.EXECUTOR_REGISTRY),
            ):
                draft_executor.register_executor(
                    "application_action", execute_application_action_draft
                )
                result = await draft_executor._execute_confirmed_draft(
                    {
                        "draft_id": item.id,
                        "draft_type": "application_action",
                        "draft_content": draft.model_dump(mode="json"),
                    },
                    {"configurable": {"thread_id": "memory-export-flow"}},
                    "memory-export-flow",
                    "fr",
                )
            assert result.to_agent_result()["status"] == "waiting"
        if scenario == "changed":
            await async_session.execute(
                update(JournalEntry)
                .where(JournalEntry.id == row_id)
                .values(content="Changed journal")
            )
        if scenario == "portrait_changed":
            await async_session.execute(
                update(User)
                .where(User.id == actor_id)
                .values(journal_portrait_full="Changed portrait")
            )
        if scenario == "new_entry":
            async_session.add(
                JournalEntry(
                    user_id=actor_id,
                    theme="learnings",
                    title="New",
                    content="New journal",
                    char_count=11,
                )
            )
        await async_session.commit()
        if scenario == "disabled":
            monkeypatch.setattr(settings, "journals_enabled", False)
        selected_origin = (
            bind_browser_session(actor_id, second.session_id)
            if scenario == "other_origin"
            else origin
        )
        if scenario in {
            "changed",
            "portrait_changed",
            "new_entry",
            "disabled",
            "other_origin",
            "no_confirmation",
        }:
            with pytest.raises(BaseAPIException):
                await serve_management_export_command(
                    async_session, actor_id, draft.command_id, selected_origin
                )
            return
        response = await serve_management_export_command(
            async_session, actor_id, draft.command_id, origin
        )
        try:
            body = b"".join([chunk async for chunk in response.body_iterator])
            assert b"embedding" not in body
            if format == "json":
                payload = json.loads(body)
                assert len(payload["entries"]) == 2
                assert payload["portrait"]["full"] == "Stored historical portrait secret"
                assert {entry["status"] for entry in payload["entries"]} == {"active", "archived"}
            else:
                assert "'=1+1" in body.decode("utf-8-sig")
                assert "Stored historical portrait secret" not in body.decode()
        finally:
            await response._reader.close()
        status = await read_command_status(async_session, actor_id, draft.command_id, origin)
        assert status.outcome is not None and status.outcome.values["save_confirmed"] is False
        await async_session.refresh(row)
        assert row.injection_count == 0
        with pytest.raises(BaseAPIException):
            await serve_management_export_command(async_session, actor_id, draft.command_id, origin)
    finally:
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)
