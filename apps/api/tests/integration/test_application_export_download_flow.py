"""Exact approval starts a single archive request only in its original browser."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.account_export.gateway import SavedAccountExports
from src.domains.account_export.models import AccountExportJob, ExportJobStatus
from src.domains.agents.application.command_status import read_command_status
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.export_download_schemas import ExportDownloadRequest
from src.domains.agents.application.export_download_service import serve_export_download_command
from src.domains.agents.application.export_download_spec import EXPORT_DOWNLOAD_OPERATION
from src.domains.agents.application.registry import APPLICATION_OPERATIONS
from src.domains.agents.application.secure_continuation import ContinuationCompletionUnknown
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_export_tools import download_lia_account_export_tool
from src.domains.users.models import User
from src.infrastructure.account_exports import configure_account_exports
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "valid",
        "no_confirmation",
        "other_origin",
        "operator_off",
        "source_off",
        "archive_changed",
        "send_failure",
        "settlement_unknown",
    ],
)
async def test_download_uses_original_exact_hitl_and_never_claims_a_saved_file(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    intervention: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "account_export_enabled", True)
    actor_id, identity = test_user.id, uuid4()
    archive = tmp_path / "owned.zip"
    archive.write_bytes(b"data")
    now = datetime.now(UTC)
    job = AccountExportJob(
        id=identity,
        user_id=actor_id,
        status=ExportJobStatus.DONE.value,
        file_path=str(archive),
        file_size_bytes=4,
        completed_at=now,
        expires_at=now + timedelta(minutes=5),
        download_count=0,
    )
    async_session.add(job)
    await async_session.commit()
    store = SessionStore(await get_redis_session())
    browser = await store.create_session(str(actor_id))
    other = await store.create_session(str(actor_id))
    origin = bind_browser_session(actor_id, browser.session_id)
    previous = configure_account_exports(SavedAccountExports())

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    for module in ["command_service", "draft_execution", "secure_continuation"]:
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", session)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", session)
    monkeypatch.setattr("src.domains.agents.tools.application_export_tools.get_db_context", session)
    monkeypatch.setitem(
        APPLICATION_OPERATIONS._operations,
        EXPORT_DOWNLOAD_OPERATION.operation_id,
        EXPORT_DOWNLOAD_OPERATION,
    )
    try:
        with installed_runtime_context(user_id=actor_id, application_origin=origin):
            proposal = await download_lia_account_export_tool.coroutine(
                selection=ExportDownloadRequest(job_id=identity),
                runtime=make_tool_runtime(
                    user_id=actor_id, application_origin=origin, store=InMemoryStore()
                ),
            )
        assert proposal.success and proposal.metadata["requires_confirmation"]
        item = next(iter(proposal.registry_updates.values()))
        draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
        assert browser.session_id not in str(proposal) and str(archive) not in str(proposal)
        if intervention != "no_confirmation":
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
                    {"configurable": {"thread_id": "download-flow"}},
                    "download-flow",
                    "fr",
                )
            assert not result.success and result.to_agent_result()["status"] == "waiting"
            assert result.result_data["interaction"]["kind"] == "device"
        assert job.download_count == 0
        if intervention == "operator_off":
            monkeypatch.setattr(settings, "application_tools_enabled", False)
        elif intervention == "source_off":
            monkeypatch.setattr(settings, "account_export_enabled", False)
        elif intervention == "archive_changed":
            archive.write_bytes(b"DATA")
        selected_origin = (
            bind_browser_session(actor_id, other.session_id)
            if intervention == "other_origin"
            else origin
        )
        if intervention == "settlement_unknown":
            monkeypatch.setattr(
                "src.domains.agents.application.export_download_service.finish_application_continuation",
                AsyncMock(side_effect=ContinuationCompletionUnknown()),
            )
            with pytest.raises(ContinuationCompletionUnknown):
                await serve_export_download_command(
                    async_session, actor_id, draft.command_id, selected_origin
                )
            assert job.download_count == 1
            with pytest.raises(BaseAPIException):
                await serve_export_download_command(
                    async_session, actor_id, draft.command_id, selected_origin
                )
            assert job.download_count == 1
            archive.replace(tmp_path / "reader-closed.zip")
            return
        if intervention in {"valid", "send_failure"}:
            response = await serve_export_download_command(
                async_session, actor_id, draft.command_id, selected_origin
            )
            messages: list[dict[str, object]] = []

            async def send(message: dict[str, object]) -> None:
                if intervention == "send_failure":
                    raise OSError("simulated interrupted transfer")
                messages.append(message)

            async def receive() -> dict[str, object]:
                return {"type": "http.request", "body": b"", "more_body": False}

            scope = {"type": "http", "method": "GET", "asgi": {"spec_version": "2.4"}}
            if intervention == "send_failure":
                with pytest.raises(Exception):
                    await response(scope, receive, send)
            else:
                await response(scope, receive, send)
                assert (
                    b"".join(
                        message["body"]
                        for message in messages
                        if message["type"] == "http.response.body"
                    )
                    == b"data"
                )
            assert job.download_count == 1
            status = await read_command_status(async_session, actor_id, draft.command_id, origin)
            assert status.outcome is not None and status.outcome.values["save_confirmed"] is False
            with pytest.raises(BaseAPIException):
                await serve_export_download_command(
                    async_session, actor_id, draft.command_id, origin
                )
            assert job.download_count == 1
            archive.replace(tmp_path / "reader-closed.zip")
        else:
            with pytest.raises(BaseAPIException):
                await serve_export_download_command(
                    async_session, actor_id, draft.command_id, selected_origin
                )
            await async_session.refresh(job)
            assert job.download_count == 0
    finally:
        configure_account_exports(previous)
        for item in (browser, other):
            await store.delete_session(item.session_id)
