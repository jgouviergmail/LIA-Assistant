"""The real HITL journal authorizes one original-browser file upload, never a replay."""

import asyncio
from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import UploadFile
from langgraph.store.memory import InMemoryStore
from starlette.datastructures import FormData

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.document_upload_service import serve_document_upload_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_space_tools
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize(
    "scenario",
    ["valid", "no_confirmation", "other_session", "operator_off", "source_off", "no_file_consent"],
)
@pytest.mark.parametrize("mode", ["pipeline", "react"])
async def test_upload_requires_original_approval_browser_and_one_local_confirmation(
    async_session, test_user, monkeypatch, tmp_path, scenario, mode
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Original destination")
    async_session.add(space)
    await async_session.commit()
    space_id = space.id
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(owner))
    other = await store.create_session(str(owner))
    origin = bind_browser_session(owner, session.session_id)

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "secure_continuation"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_space_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    launched = AsyncMock()
    monkeypatch.setattr(
        "src.domains.agents.application.document_upload_service.launch_uploaded_document", launched
    )
    parsed = 0
    events = asyncio.Queue()

    @asynccontextmanager
    async def form():
        nonlocal parsed
        parsed += 1
        data = FormData([("file", UploadFile(filename="controlled.txt", file=BytesIO(b"data")))])
        try:
            yield data
        finally:
            await data.close()

    try:
        with installed_runtime_context(
            user_id=owner,
            application_origin=origin,
            deps=object(),
            execution_mode=mode,
            side_channel_queue=events,
        ):
            proposal = await application_space_tools.upload_lia_knowledge_document_tool.coroutine(
                request={"space_id": space_id},
                runtime=make_tool_runtime(
                    user_id=owner,
                    application_origin=origin,
                    store=InMemoryStore(),
                    execution_mode=mode,
                    side_channel_queue=events,
                ),
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            if scenario != "no_confirmation":
                with patch.dict(draft_executor.EXECUTOR_REGISTRY):
                    draft_executor.register_executor(
                        "application_action", execute_application_action_draft
                    )
                    result = await draft_executor._execute_confirmed_draft(
                        {
                            "draft_id": item.id,
                            "draft_type": "application_action",
                            "draft_content": draft.model_dump(mode="json"),
                        },
                        {"configurable": {"thread_id": "document-upload-flow"}},
                        "document-upload-flow",
                        "fr",
                    )
                assert not result.success and result.result_data.get("phase") == "waiting"
            if scenario == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "source_off":
                monkeypatch.setattr(settings, "rag_spaces_enabled", False)
            selected_origin = (
                bind_browser_session(owner, other.session_id)
                if scenario == "other_session"
                else origin
            )
            if scenario != "valid":
                with pytest.raises((BaseAPIException, ValueError)):
                    await serve_document_upload_command(
                        async_session,
                        owner,
                        draft.command_id,
                        selected_origin,
                        file_confirmed=scenario != "no_file_consent",
                        parse_form=form,
                    )
                assert parsed == 0
                assert not list(tmp_path.rglob("*.txt"))
                launched.assert_not_awaited()
            else:
                result = await serve_document_upload_command(
                    async_session,
                    owner,
                    draft.command_id,
                    origin,
                    file_confirmed=True,
                    parse_form=form,
                )
                assert (
                    result.success
                    and result.committed
                    and result.values["indexing_completed"] is False
                )
                row = await async_session.get(RAGDocument, draft.command_id)
                assert row is not None and row.user_id == owner and row.space_id == space_id
                assert parsed == 1
                launched.assert_awaited_once_with(async_session, owner, draft.command_id)
                with pytest.raises(BaseAPIException):
                    await serve_document_upload_command(
                        async_session,
                        owner,
                        draft.command_id,
                        origin,
                        file_confirmed=True,
                        parse_form=form,
                    )
                assert parsed == 1 and launched.await_count == 1
                changes = []
                while not events.empty():
                    event = events.get_nowait()
                    if event.type == "application_state_changed":
                        changes.append(event)
                assert len(changes) == 1
                assert changes[0].metadata["change"]["resources"] == ["spaces"]
    finally:
        await store.delete_session(session.session_id)
        await store.delete_session(other.session_id)
