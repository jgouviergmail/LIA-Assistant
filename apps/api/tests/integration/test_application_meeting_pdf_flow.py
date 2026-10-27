"""Original browser HITL, real effect ledger and frozen owned minutes transfer."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import ClientDisconnect

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_pdf_download import serve_meeting_pdf_command
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_meeting_delivery_tools
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.pdf_gateway import SavedMeetingPDF
from src.domains.users.models import User
from src.infrastructure.application_sessions import bind_browser_session
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.cache.session_store import SessionStore
from src.infrastructure.meeting_pdf import configure_meeting_pdf
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]
PDF = b"%PDF-1.7\nControlled original minutes"


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "other_session",
        "operator_off",
        "meetings_off",
        "body_changed",
        "header_changed",
        "send_failure",
        "lost_ack",
        "disabled_during_render",
    ],
)
async def test_pdf_transfer_is_confirmed_origin_bound_and_single_use(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    report = {
        "title": "Controlled minutes",
        "participants": [],
        "sections": [
            {
                "key": "summary",
                "label": "Summary",
                "kind": "paragraph",
                "paragraph": "private PDF-only body",
            }
        ],
    }
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current=report,
        location_label="Approved location",
    )
    async_session.add(row)
    await async_session.commit()
    owner, identity = test_user.id, row.id
    store = SessionStore(await get_redis_session())
    session = await store.create_session(str(owner))
    other = await store.create_session(str(owner))
    origin = bind_browser_session(owner, session.session_id)

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
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
        "meeting_pdf_editing",
    ):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_meeting_delivery_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    previous = configure_meeting_pdf(SavedMeetingPDF())

    def rendered(*args, **kwargs):
        if scenario == "disabled_during_render":
            monkeypatch.setattr(settings, "meetings_enabled", False)
        return PDF

    try:
        with (
            installed_runtime_context(
                user_id=owner, application_origin=origin, deps=object(), execution_mode=mode
            ),
            patch("src.domains.meetings.delivery.render_document", side_effect=rendered) as render,
        ):
            proposal = (
                await application_meeting_delivery_tools.download_lia_meeting_pdf_tool.coroutine(
                    request={"meeting_id": str(identity)},
                    runtime=make_tool_runtime(
                        user_id=owner,
                        application_origin=origin,
                        store=InMemoryStore(),
                        execution_mode=mode,
                    ),
                )
            )
            assert proposal.success and proposal.metadata["requires_confirmation"]
            render.assert_not_called()
            item = next(iter(proposal.registry_updates.values()))
            draft = ApplicationActionDraftContent.model_validate(item.payload["content"])
            assert "private PDF-only body" not in draft.model_dump_json()
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
                        {"configurable": {"thread_id": "meeting-pdf-flow"}},
                        "meeting-pdf-flow",
                        "fr",
                    )
                assert not result.success and result.result_data.get("phase") == "waiting"
                render.assert_not_called()
            if scenario == "operator_off":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "meetings_off":
                monkeypatch.setattr(settings, "meetings_enabled", False)
            if scenario == "body_changed":
                row.report_current = {
                    **report,
                    "sections": [{**report["sections"][0], "paragraph": "Changed PDF body"}],
                }
                await async_session.commit()
            if scenario == "header_changed":
                row.location_label = "Changed location"
                await async_session.commit()
            selected_origin = (
                bind_browser_session(owner, other.session_id)
                if scenario == "other_session"
                else origin
            )
            if scenario == "lost_ack":
                from src.domains.agents.application import stored_download_service
                from src.infrastructure.account_export_downloads import (
                    ExportDownloadCompletionUnknown,
                )

                original_commit = async_session.commit
                original_claim = stored_download_service.claim_approved_waiting_interaction

                async def claim_then_lose_commit(*args):
                    ticket = await original_claim(*args)

                    async def lost_commit():
                        monkeypatch.setattr(async_session, "commit", original_commit)
                        await original_commit()
                        raise OSError("Controlled lost transfer acknowledgment")

                    monkeypatch.setattr(async_session, "commit", lost_commit)
                    return ticket

                monkeypatch.setattr(
                    stored_download_service,
                    "claim_approved_waiting_interaction",
                    claim_then_lose_commit,
                )
                with pytest.raises(ExportDownloadCompletionUnknown):
                    await serve_meeting_pdf_command(async_session, owner, draft.command_id, origin)
                monkeypatch.setattr(async_session, "commit", original_commit)
                return
            if scenario not in {"valid", "send_failure"}:
                with pytest.raises((BaseAPIException, CommandRejected)):
                    await serve_meeting_pdf_command(
                        async_session, owner, draft.command_id, selected_origin
                    )
                if scenario == "disabled_during_render":
                    render.assert_called_once()
                else:
                    render.assert_not_called()
                return
            response = await serve_meeting_pdf_command(
                async_session, owner, draft.command_id, origin
            )
            render.assert_called_once()
            assert response.headers["cache-control"] == "no-store"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert response.headers["content-type"] == "application/pdf"
            row.report_current = {**report, "title": "Changed after frozen transfer"}
            await async_session.commit()
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
                assert (
                    b"".join(
                        message["body"]
                        for message in messages
                        if message["type"] == "http.response.body"
                    )
                    == PDF
                )
            from src.domains.agents.application.command_status import read_command_status

            observed = await read_command_status(async_session, owner, draft.command_id, origin)
            assert observed.outcome.committed
            assert observed.outcome.values["download_requested"] is True
            assert observed.outcome.values["save_confirmed"] is False
            with pytest.raises(BaseAPIException):
                await serve_meeting_pdf_command(async_session, owner, draft.command_id, origin)
            assert response._reader.closed
    finally:
        configure_meeting_pdf(previous)
