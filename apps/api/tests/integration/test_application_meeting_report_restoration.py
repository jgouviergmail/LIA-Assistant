"""Full-content restoration through original HITL and actual PostgreSQL writes."""

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
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_meeting_report_tools import (
    restore_lia_meeting_report_tool,
)
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.report_gateway import SavedMeetingReports
from src.domains.users.models import User
from src.infrastructure.meeting_reports import configure_meeting_reports
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention",
    [
        "none",
        "current_changed",
        "generated_changed",
        "disabled",
        "no_op",
        "lost_ack",
        "foreign",
        "corrupt_current",
        "corrupt_generated",
    ],
)
async def test_restoration_uses_full_content_consent_and_original_writer(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    generated = {
        "title": "Controlled minutes",
        "participants": [],
        "sections": [
            {
                "key": "summary",
                "label": "Summary",
                "kind": "paragraph",
                "paragraph": "private original words",
            }
        ],
    }
    current = {
        **generated,
        "sections": [{**generated["sections"][0], "paragraph": "private edited words"}],
    }
    if intervention == "no_op":
        current = dict(generated)
    if intervention == "corrupt_current":
        current = {"title": ["malformed private words"]}
    if intervention == "corrupt_generated":
        generated = {"title": ["malformed private words"]}
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current=current,
        report_generated=generated,
        location_label="Preserved place",
    )
    if intervention == "foreign":
        row.user_id = await _user(async_session)
    async_session.add(row)
    await async_session.commit()
    actor_id, meeting_id = test_user.id, row.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    gateway = SavedMeetingReports()
    if intervention == "lost_ack":
        real_commit = async_session.commit

        async def lost_commit() -> None:
            await real_commit()
            raise OperationalError("COMMIT", {}, Exception("lost acknowledgment"))

        class LostAcknowledgment(SavedMeetingReports):
            async def restore(self, db, actor_id, meeting_id, confirmation):
                with patch.object(db, "commit", lost_commit):
                    await super().restore(db, actor_id, meeting_id, confirmation)

        gateway = LostAcknowledgment()
    previous = configure_meeting_reports(gateway)
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
            proposal = await restore_lia_meeting_report_tool.coroutine(
                request={"meeting_id": str(meeting_id)},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            if intervention in {"foreign", "corrupt_generated"}:
                assert not proposal.success
                ledger.claim.assert_not_awaited()
                reindex.assert_not_called()
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            assert "private original words" not in str(content)
            assert "private edited words" not in str(content)
            await async_session.refresh(row)
            assert row.report_current == current
            if intervention in {"current_changed", "generated_changed"}:
                modified = {
                    **generated,
                    "sections": [
                        {**generated["sections"][0], "paragraph": "same headings changed body"}
                    ],
                }
                if intervention == "current_changed":
                    current = modified
                    row.report_current = modified
                else:
                    generated = modified
                    row.report_generated = modified
                await async_session.commit()
            if intervention == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            outcome = await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "report-confirmation"}},
                "report-confirmation",
                "fr",
            )
            if intervention in {"none", "lost_ack", "no_op", "corrupt_current"}:
                replay = await draft_executor._execute_confirmed_draft(
                    payload,
                    {"configurable": {"thread_id": "report-confirmation"}},
                    "report-confirmation",
                    "fr",
                )
                assert not replay.success
            assert reindex.call_count == int(intervention in {"none", "corrupt_current"})
    finally:
        configure_meeting_reports(previous)
    await async_session.refresh(row)
    assert row.location_label == "Preserved place"
    assert row.report_current == (
        generated if intervention in {"none", "lost_ack", "no_op", "corrupt_current"} else current
    )
    assert outcome.success is (intervention in {"none", "no_op", "corrupt_current"})
    expected_error = {
        "current_changed": "STALE_STATE",
        "generated_changed": "STALE_STATE",
        "disabled": "CAPABILITY_DISABLED",
        "lost_ack": "COMPLETION_UNKNOWN",
    }
    if intervention in expected_error:
        assert draft_refusal_code(outcome) == expected_error[intervention]
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention in {"none", "corrupt_current"})
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["meetings"]
        assert "source_digest" not in str(hints[0].metadata)
