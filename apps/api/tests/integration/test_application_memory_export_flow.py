"""The memory-specific projection runs through the same exact original-browser receipt."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.management_export_schemas import ManagementExportRequest
from src.domains.agents.application.management_export_service import serve_management_export_command
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_management_export_tools import export_lia_memories_tool
from src.domains.memories.models import Memory
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "scenario", ["json", "csv", "changed", "invalidated", "other_origin", "no_confirmation"]
)
async def test_memory_export_preserves_current_source_projection_and_never_uses_private_context(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    scenario: str,
) -> None:
    actor_id = test_user.id
    row = Memory(
        user_id=actor_id,
        content="=1+1",
        category="personal",
        importance=0.0,
        context_biometric={"private": "biometric-secret"},
        pinned=True,
    )
    historical = Memory(
        user_id=actor_id,
        content="Superseded historical secret",
        category="personal",
        invalidated_at=datetime.now(UTC),
    )
    async_session.add_all([row, historical])
    await async_session.commit()
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
            proposal = await export_lia_memories_tool.coroutine(
                request=ManagementExportRequest(format=format),
                runtime=make_tool_runtime(
                    user_id=actor_id, application_origin=origin, store=InMemoryStore()
                ),
            )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert draft.intent["management_export"]["selected_count"] == 1
        assert "=1+1" not in str(draft.intent) and "biometric-secret" not in str(proposal)
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
        if scenario in {"changed", "invalidated"}:
            changes = (
                {"content": "Changed memory"}
                if scenario == "changed"
                else {"invalidated_at": datetime.now(UTC)}
            )
            await async_session.execute(update(Memory).where(Memory.id == row.id).values(**changes))
            await async_session.commit()
        selected_origin = (
            bind_browser_session(actor_id, second.session_id)
            if scenario == "other_origin"
            else origin
        )
        if scenario in {"changed", "invalidated", "other_origin", "no_confirmation"}:
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
            assert (
                "biometric-secret" not in body.decode()
                and "Superseded historical secret" not in body.decode()
            )
            if format == "json":
                payload = json.loads(body)
                assert payload["total_memories"] == 1
                assert payload["memories"][0]["importance"] == 0
                assert payload["memories"][0]["context_biometric"] is None
            else:
                assert "'=1+1" in body.decode("utf-8-sig")
                assert (
                    "purge_risk" not in body.decode() and "context_biometric" not in body.decode()
                )
        finally:
            await response._reader.close()
        status = await read_command_status(async_session, actor_id, draft.command_id, origin)
        assert status.outcome is not None and status.outcome.values["save_confirmed"] is False
        await async_session.refresh(row)
        assert row.usage_count == 0 and row.importance == 0 and row.pinned
        with pytest.raises(BaseAPIException):
            await serve_management_export_command(async_session, actor_id, draft.command_id, origin)
    finally:
        await store.delete_session(first.session_id)
        await store.delete_session(second.session_id)
