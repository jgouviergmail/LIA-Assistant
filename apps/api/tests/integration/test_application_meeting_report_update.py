"""Original HITL edits exact sparse values through the real PostgreSQL owner."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.meeting_reports import MeetingReport
from src.core.meeting_templates import MeetingTemplateCreate, MeetingTemplateUpdate
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_meeting_report_tools import update_lia_meeting_report_tool
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.report_update_gateway import SavedMeetingReportUpdates
from src.domains.meetings.template_service import MeetingTemplateService
from src.domains.users.models import User
from src.infrastructure.meeting_report_updates import configure_meeting_report_updates
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "none",
        "body_changed",
        "disabled",
        "no_op",
        "lost_ack",
        "foreign",
        "full_lists",
        "template",
        "template_changed",
        "template_locked",
        "duplicate_sections",
        "template_only",
    ],
)
async def test_sparse_report_edit_requires_original_consent_and_fresh_source(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    section = {
        "key": "summary",
        "label": "Summary",
        "kind": "paragraph",
        "paragraph": "unrequested private body",
    }
    report = {
        "title": "Before",
        "participants": [{"label": "S1", "name": "Preserved participant"}],
        "sections": [section],
    }
    row = Meeting(
        user_id=test_user.id,
        status=(
            MeetingStatus.STOPPED
            if intervention in {"template", "template_changed"}
            else MeetingStatus.READY
        ),
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current=report,
        report_generated=report,
        location_label="Preserved place",
    )
    if intervention == "foreign":
        row.user_id = await _user(async_session)
    if intervention == "template_only":
        row.status = MeetingStatus.RECORDING
        row.report_current = None
        report = None
    async_session.add(row)
    await async_session.commit()
    actor_id, meeting_id = test_user.id, row.id
    changes = {"title": "Before" if intervention == "no_op" else "After"}
    if intervention == "full_lists":
        changes = {
            "participants": [],
            "sections": [{**section, "paragraph": "Explicit new body"}],
            "location_label": "New place",
        }
    if intervention == "duplicate_sections":
        changes = {"sections": [section, dict(section)]}
    if intervention == "template_locked":
        changes = {"template_ref": "builtin:daily_standup"}
    if intervention == "template_only":
        changes = {"template_ref": "builtin:daily_standup"}
    template = None
    if intervention in {"template", "template_changed"}:
        template = await MeetingTemplateService(async_session).create(
            actor_id,
            MeetingTemplateCreate(
                name="Selected template",
                sections=[
                    {
                        "key": "summary",
                        "label": "Summary",
                        "instruction": "Original selected instruction",
                        "kind": "paragraph",
                    }
                ],
            ),
            "fr",
        )
        changes = {"template_ref": template.ref, "title": "After"}

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    gateway = SavedMeetingReportUpdates()
    if intervention == "lost_ack":
        real_commit = async_session.commit

        async def lost_commit() -> None:
            await real_commit()
            raise OperationalError("COMMIT", {}, Exception("lost acknowledgment"))

        class LostAcknowledgment(SavedMeetingReportUpdates):
            async def update(self, db, actor_id, meeting_id, changes, language, confirmation):
                with patch.object(db, "commit", lost_commit):
                    await super().update(db, actor_id, meeting_id, changes, language, confirmation)

        gateway = LostAcknowledgment()
    previous = configure_meeting_report_updates(gateway)
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[ChatStreamChunk] = asyncio.Queue()
    try:
        with (
            installed_runtime_context(
                user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
            ),
            patch(
                "src.domains.agents.tools.application_meeting_report_tools.get_db_context", session
            ),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_execution.get_db_context", session),
            patch("src.domains.agents.effects.runtime._LEDGER", ledger),
            patch("src.domains.meetings.indexing.schedule_reindex") as reindex,
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await update_lia_meeting_report_tool.coroutine(
                request={"meeting_id": str(meeting_id), "changes": changes},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            if intervention in {"foreign", "template_locked", "duplicate_sections"}:
                assert not proposal.success
                ledger.claim.assert_not_awaited()
                reindex.assert_not_called()
                await async_session.refresh(row)
                assert row.report_current == report
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            if intervention != "full_lists":
                assert "unrequested private body" not in str(content)
            await async_session.refresh(row)
            assert row.report_current == report
            if intervention == "body_changed":
                report = {
                    **report,
                    "sections": [{**section, "paragraph": "Changed unrequested body"}],
                }
                row.report_current = report
                await async_session.commit()
            if intervention == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if intervention == "template_changed":
                await MeetingTemplateService(async_session).update(
                    actor_id,
                    template.ref,
                    MeetingTemplateUpdate(
                        name="Selected template",
                        sections=[
                            {
                                "key": "summary",
                                "label": "Summary",
                                "instruction": "Changed selected instruction",
                                "kind": "paragraph",
                            }
                        ],
                    ),
                )
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            outcome = await draft_executor._execute_confirmed_draft(
                payload, {"configurable": {"thread_id": "report-update"}}, "report-update", "fr"
            )
            if intervention in {
                "none",
                "no_op",
                "lost_ack",
                "full_lists",
                "template",
                "template_only",
            }:
                replay = await draft_executor._execute_confirmed_draft(
                    payload, {"configurable": {"thread_id": "report-update"}}, "report-update", "fr"
                )
                assert not replay.success
            assert reindex.call_count == int(
                intervention in {"none", "full_lists", "template", "template_only"}
            )
    finally:
        configure_meeting_report_updates(previous)
    await async_session.refresh(row)
    succeeded = intervention in {"none", "no_op", "full_lists", "template", "template_only"}
    assert outcome.success is succeeded
    if intervention in {"body_changed", "template_changed", "disabled", "lost_ack"}:
        assert (
            outcome.error
            == {
                "body_changed": "STALE_STATE",
                "template_changed": "STALE_STATE",
                "disabled": "CAPABILITY_DISABLED",
                "lost_ack": "COMPLETION_UNKNOWN",
            }[intervention]
        )
    if intervention in {"none", "lost_ack", "template"}:
        assert row.report_current["title"] == "After"
        assert (
            MeetingReport.model_validate(row.report_current).participants
            == MeetingReport.model_validate(report).participants
        )
        assert row.report_current["sections"][0]["paragraph"] == "unrequested private body"
    elif intervention == "full_lists":
        assert row.report_current["title"] == "Before"
        assert row.report_current["participants"] == []
        assert row.report_current["sections"][0]["paragraph"] == "Explicit new body"
        assert row.location_label == "New place"
    else:
        assert row.report_current == report
    if intervention != "full_lists":
        assert row.location_label == "Preserved place"
    if intervention == "template":
        assert row.template_ref == template.ref
    if intervention == "template_only":
        assert row.template_ref == "builtin:daily_standup" and row.report_current is None
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention in {"none", "full_lists", "template", "template_only"})
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["meetings"]
        assert "source_digest" not in str(hints[0].metadata)
