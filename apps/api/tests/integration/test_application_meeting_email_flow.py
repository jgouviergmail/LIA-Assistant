"""Original HITL and real effect ledger guard one platform SMTP attempt."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_meeting_delivery_tools
from src.domains.meetings.email_gateway import SavedMeetingEmail
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.users.models import User
from src.infrastructure.meeting_email import configure_meeting_email
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "body_changed",
        "header_changed",
        "recipient_changed",
        "sender_changed",
        "already_sent",
        "disabled",
        "meetings_off",
        "foreign",
        "not_ready",
        "lost_ack",
        "cancelled",
        "metadata_failure",
        "late_refusal",
        "rate_limited",
    ],
)
async def test_minutes_email_requires_current_exact_consent_and_never_replays(
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
                "paragraph": "Private SMTP-only words",
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
        location_label="Approved place",
    )
    if scenario == "foreign":
        row.user_id = await _user(async_session)
    if scenario == "not_ready":
        row.status = MeetingStatus.STOPPED
    async_session.add(row)
    await async_session.commit()
    owner, identity, recipient = test_user.id, row.id, test_user.email

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "meeting_email_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_meeting_delivery_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    smtp = MagicMock(smtp_from="platform@example.test", send_email=AsyncMock(return_value=True))
    previous = configure_meeting_email(SavedMeetingEmail())
    queue: asyncio.Queue[ChatStreamChunk] = asyncio.Queue()
    try:
        with (
            installed_runtime_context(
                user_id=owner,
                language="fr",
                deps=object(),
                execution_mode=mode,
                side_channel_queue=queue,
            ),
            patch("src.domains.meetings.email_gateway.get_email_service", return_value=smtp),
            patch("src.domains.meetings.delivery.get_email_service", return_value=smtp),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = (
                await application_meeting_delivery_tools.email_lia_meeting_report_tool.coroutine(
                    request={"meeting_id": str(identity)},
                    runtime=make_tool_runtime(
                        user_id=owner, store=InMemoryStore(), execution_mode=mode
                    ),
                )
            )
            smtp.send_email.assert_not_called()
            if scenario in {"foreign", "not_ready"}:
                assert not proposal.success
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            assert "Private SMTP-only words" not in str(content)
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected) as refused:
                    await execute_application_action_draft(content, owner, object())
                assert refused.value.code == "CONFIRMATION_MISSING"
                smtp.send_email.assert_not_called()
                return
            if scenario == "body_changed":
                row.report_current = {
                    **report,
                    "sections": [{**report["sections"][0], "paragraph": "Changed private words"}],
                }
            if scenario == "header_changed":
                row.location_label = "Changed place"
            if scenario == "recipient_changed":
                test_user.email = "changed@example.test"
            if scenario == "sender_changed":
                smtp.smtp_from = "changed-platform@example.test"
            if scenario == "already_sent":
                row.email_sent_at = datetime.now(UTC)
            await async_session.commit()
            if scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "meetings_off":
                monkeypatch.setattr(settings, "meetings_enabled", False)
            if scenario == "rate_limited":
                from src.domains.email_share.rate_limits import rate_limit_email_share

                for _ in range(settings.email_share_rate_limit_calls):
                    await rate_limit_email_share(test_user)
            if scenario == "lost_ack":
                smtp.send_email.side_effect = TimeoutError()
            if scenario == "cancelled":
                smtp.send_email.side_effect = asyncio.CancelledError()
            if scenario == "metadata_failure":
                monkeypatch.setattr(
                    "src.domains.meetings.delivery.MeetingRepository.set_email_sent",
                    AsyncMock(side_effect=RuntimeError("Controlled metadata failure")),
                )
            if scenario == "late_refusal":
                real_html = __import__(
                    "src.domains.meetings.delivery", fromlist=["render_html"]
                ).render_html

                def render(*args):
                    monkeypatch.setattr(settings, "application_tools_enabled", False)
                    return real_html(*args)

                monkeypatch.setattr("src.domains.meetings.delivery.render_html", render)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            result = await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "meeting-email-flow"}},
                "meeting-email-flow",
                "fr",
            )
            if scenario == "valid":
                assert result.success
                smtp.send_email.assert_awaited_once()
                assert smtp.send_email.call_args.kwargs["to_email"] == recipient
                assert "Private SMTP-only words" in smtp.send_email.call_args.kwargs["html_body"]
                assert (
                    result.result_data["values"]["meeting_email_sent"]["provider_acknowledged"]
                    is True
                )
                assert (
                    result.result_data["values"]["meeting_email_sent"][
                        "recipient_delivery_confirmed"
                    ]
                    is False
                )
                await async_session.refresh(row)
                assert row.email_sent_at is not None
                changes = []
                while not queue.empty():
                    chunk = queue.get_nowait()
                    if chunk.type == "application_state_changed":
                        changes.append(chunk.metadata["change"])
                assert len(changes) == 1
                assert changes[0]["resources"] == ["meetings"]
                assert changes[0]["changed_fields"] == ["meeting_email_send"]
            else:
                assert not result.success
                if scenario == "rate_limited":
                    assert result.result_data["error_code"] == "RATE_LIMIT_EXCEEDED"
                if scenario == "metadata_failure":
                    assert result.result_data["committed"]
                    assert (
                        result.result_data["values"]["meeting_email_sent"]["metadata_saved"]
                        is False
                    )
                if scenario in {"lost_ack", "cancelled", "metadata_failure"}:
                    smtp.send_email.assert_awaited_once()
                else:
                    smtp.send_email.assert_not_called()
            calls = smtp.send_email.await_count
            await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "meeting-email-flow"}},
                "meeting-email-flow",
                "fr",
            )
            assert smtp.send_email.await_count == calls
    finally:
        configure_meeting_email(previous)
