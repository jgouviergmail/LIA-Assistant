"""One exact HITL file download uses the original session, source guards and durable effect journal."""

from contextlib import asynccontextmanager
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import func, select
from starlette.requests import ClientDisconnect

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.document_download_service import serve_document_download_command
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.effects.models import AgentEffect
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_space_tools
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.support.file_clock import rewrite_later

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "other_session",
        "operator_off",
        "source_off",
        "file_changed",
        "send_failure",
        "lost_ack",
        "cancelled_ack",
        "edit_refresh",
        "edit_retarget",
    ],
)
@pytest.mark.parametrize("archive", [False, True])
async def test_original_confirmed_document_transfer_is_single_use_and_never_claims_saved_file(
    async_session, test_user, monkeypatch, tmp_path, scenario, archive
):
    monkeypatch.setattr(settings, "rag_spaces_enabled", True)
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path))
    owner = test_user.id
    space = RAGSpace(user_id=owner, name="Owned source space")
    async_session.add(space)
    await async_session.flush()
    document = RAGDocument(
        user_id=owner,
        space_id=space.id,
        filename="server-file.txt",
        original_filename="My document.txt",
        file_size=4,
        content_type="text/plain",
        status="ready",
    )
    async_session.add(document)
    await async_session.commit()
    space_id, document_id = space.id, document.id
    directory = tmp_path / str(owner) / str(space_id)
    directory.mkdir(parents=True)
    path = directory / "server-file.txt"
    path.write_bytes(b"data")
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(owner))
    other = await store.create_session(str(owner))
    origin = bind_browser_session(owner, session.session_id)
    if archive:
        from src.domains.agents.application.document_archive_service import (
            serve_document_archive_command,
        )

        serve = serve_document_archive_command
        tool = application_space_tools.download_lia_knowledge_archive_tool
        request_body = {"space_id": space_id, "document_ids": [document_id]}
    else:
        serve = serve_document_download_command
        tool = application_space_tools.download_lia_knowledge_document_tool
        request_body = {"space_id": space_id, "document_id": document_id}

    @asynccontextmanager
    async def database():
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in (
        "command_service",
        "draft_execution",
        "secure_continuation",
        "document_download_editing",
        "document_archive_editing",
    ):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_space_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    with installed_runtime_context(user_id=owner, application_origin=origin, deps=object()):
        proposal = await tool.coroutine(
            request=request_body,
            runtime=make_tool_runtime(
                user_id=owner, application_origin=origin, store=InMemoryStore()
            ),
        )
        assert (
            proposal.success and proposal.metadata["requires_confirmation"]
        ), proposal.model_dump()
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        if scenario in {"edit_refresh", "edit_retarget"}:
            from uuid import uuid4

            from src.domains.agents.application.command_service import CommandRejected
            from src.domains.agents.application.draft_editing import rebuild_application_draft

            changed_request = dict(request_body)
            if scenario == "edit_retarget":
                if archive:
                    changed_request["document_ids"] = [uuid4()]
                else:
                    changed_request["document_id"] = uuid4()
                with pytest.raises(CommandRejected):
                    await rebuild_application_draft(
                        draft.model_dump(mode="json"), {"intent": changed_request}
                    )
                return
            rewrite_later(path, b"DATA")
            original_draft = draft
            draft = ApplicationActionDraftContent.model_validate(
                await rebuild_application_draft(
                    draft.model_dump(mode="json"), {"intent": changed_request}
                )
            )
            assert (
                draft.command_id == original_draft.command_id
                and draft.intent != original_draft.intent
            )
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
                    {"configurable": {"thread_id": "document-download-flow"}},
                    "document-download-flow",
                    "fr",
                )
            assert (
                not result.success and result.result_data.get("phase") == "waiting"
            ), result.to_agent_result()
        if scenario == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif scenario == "source_off":
            monkeypatch.setattr(settings, "rag_spaces_enabled", False)
        elif scenario == "file_changed":
            rewrite_later(path, b"DATA")
        selected_origin = (
            bind_browser_session(owner, other.session_id) if scenario == "other_session" else origin
        )
        if scenario in {"lost_ack", "cancelled_ack"}:
            from src.domains.agents.application import stored_download_service
            from src.infrastructure.account_export_downloads import ExportDownloadCompletionUnknown

            original_commit = async_session.commit
            original_claim = stored_download_service.claim_approved_waiting_interaction

            async def claim_then_lose_commit(*args):
                ticket = await original_claim(*args)

                async def lost_commit():
                    monkeypatch.setattr(async_session, "commit", original_commit)
                    await original_commit()
                    if scenario == "cancelled_ack":
                        import asyncio

                        raise asyncio.CancelledError()
                    raise OSError("controlled lost commit acknowledgment")

                monkeypatch.setattr(async_session, "commit", lost_commit)
                return ticket

            monkeypatch.setattr(
                "src.domains.agents.application.stored_download_service.claim_approved_waiting_interaction",
                claim_then_lose_commit,
            )
            with pytest.raises(ExportDownloadCompletionUnknown):
                await serve(async_session, owner, draft.command_id, origin)
            monkeypatch.setattr(async_session, "commit", original_commit)
            from src.domains.agents.application.command_status import read_command_status

            observed = await read_command_status(async_session, owner, draft.command_id, origin)
            assert (
                not observed.outcome.committed
                and observed.outcome.error_code == "COMPLETION_UNKNOWN"
            )
            with pytest.raises(BaseAPIException):
                await serve(async_session, owner, draft.command_id, origin)
            return
        if scenario not in {"valid", "send_failure", "edit_refresh"}:
            with pytest.raises(BaseAPIException):
                await serve(async_session, owner, draft.command_id, selected_origin)
            return
        response = await serve(async_session, owner, draft.command_id, origin)
        assert (
            response.headers["Cache-Control"] == "no-store"
            and response.headers["X-Content-Type-Options"] == "nosniff"
        )
        path.write_bytes(b"DATA")  # The confirmed response must retain its frozen bytes.
        messages = []

        async def send(message):
            if scenario == "send_failure":
                raise OSError("Controlled disconnected browser")
            messages.append(message)

        async def receive():
            return {"type": "http.request", "body": b"", "more_body": False}

        scope = {"type": "http", "method": "GET", "asgi": {"spec_version": "2.4"}}
        if scenario == "send_failure":
            with pytest.raises(ClientDisconnect):
                await response(scope, receive, send)
        else:
            await response(scope, receive, send)
            transferred = b"".join(
                message["body"] for message in messages if message["type"] == "http.response.body"
            )
            if archive:
                with ZipFile(BytesIO(transferred)) as packed:
                    assert packed.namelist() == ["My document.txt"]
                    assert packed.read("My document.txt") == (
                        b"DATA" if scenario == "edit_refresh" else b"data"
                    )
            else:
                assert transferred == (b"DATA" if scenario == "edit_refresh" else b"data")
        from src.domains.agents.application.command_status import read_command_status

        status = await read_command_status(async_session, owner, draft.command_id, origin)
        assert status.outcome.committed and status.outcome.values["download_requested"] is True
        assert status.outcome.values["save_confirmed"] is False
        effects = await async_session.scalar(
            select(func.count(AgentEffect.id)).where(AgentEffect.user_id == owner)
        )
        with pytest.raises(BaseAPIException):
            await serve(async_session, owner, draft.command_id, origin)
        assert (
            await async_session.scalar(
                select(func.count(AgentEffect.id)).where(AgentEffect.user_id == owner)
            )
            == effects
        )
        assert response._reader.closed
