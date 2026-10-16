"""Original native HITL, command fence and PostgreSQL transcript purge."""

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
from src.core.security.utils import encrypt_data
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.effects.runtime import ClaimTicket
from src.domains.agents.services import draft_executor
from src.domains.agents.tools.application_meeting_transcript_tools import (
    delete_lia_meeting_transcript_tool,
)
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.transcript_gateway import SavedMeetingTranscripts
from src.domains.users.models import User
from src.infrastructure.meeting_transcripts import configure_meeting_transcripts
from tests.helpers.draft_refusals import draft_refusal_code
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "intervention", ["none", "changed", "disabled", "no_op", "lost_ack", "foreign", "live"]
)
async def test_owned_transcript_purge_requires_original_confirmation_and_fresh_state(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, intervention: str
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    report = {"title": "Controlled minutes", "participants": [], "sections": []}
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current=report,
        transcript_encrypted=(
            None if intervention == "no_op" else encrypt_data("private source words")
        ),
    )
    if intervention == "foreign":
        row.user_id = await _user(async_session)
    if intervention == "live":
        row.status = MeetingStatus.RECORDING
    async_session.add(row)
    await async_session.commit()
    actor_id, meeting_id = test_user.id, row.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session
        await async_session.commit()

    gateway = SavedMeetingTranscripts()
    if intervention == "lost_ack":
        real_commit = async_session.commit

        async def lost_commit() -> None:
            await real_commit()
            raise OperationalError("COMMIT", {}, Exception("lost acknowledgment"))

        class LostAcknowledgment(SavedMeetingTranscripts):
            async def delete(self, db, actor_id, meeting_id, confirmation):
                with patch.object(db, "commit", lost_commit):
                    await super().delete(db, actor_id, meeting_id, confirmation)

        gateway = LostAcknowledgment()
    previous = configure_meeting_transcripts(gateway)
    ledger = AsyncMock()
    ledger.claim.return_value = ClaimTicket(uuid4(), uuid4(), None)
    queue: asyncio.Queue[ChatStreamChunk] = asyncio.Queue()
    try:
        with (
            installed_runtime_context(
                user_id=actor_id, language="fr", deps=object(), side_channel_queue=queue
            ),
            patch(
                "src.domains.agents.tools.application_meeting_transcript_tools.get_db_context",
                session,
            ),
            patch("src.domains.agents.application.command_service.get_db_context", session),
            patch("src.domains.agents.application.draft_execution.get_db_context", session),
            patch("src.domains.agents.effects.runtime._LEDGER", ledger),
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await delete_lia_meeting_transcript_tool.coroutine(
                request={"meeting_id": str(meeting_id)},
                runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore()),
            )
            if intervention in {"foreign", "live"}:
                assert proposal.success is False
                ledger.claim.assert_not_awaited()
                await async_session.refresh(row)
                assert row.transcript_encrypted is not None
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            await async_session.refresh(row)
            assert (row.transcript_encrypted is None) is (intervention == "no_op")
            if intervention == "changed":
                row.transcript_encrypted = encrypt_data("changed words")
                await async_session.commit()
            if intervention == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": item.payload["content"],
            }
            outcome = await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "transcript-confirmation"}},
                "transcript-confirmation",
                "fr",
            )
            if intervention in {"none", "lost_ack", "no_op"}:
                replay = await draft_executor._execute_confirmed_draft(
                    payload,
                    {"configurable": {"thread_id": "transcript-confirmation"}},
                    "transcript-confirmation",
                    "fr",
                )
                assert replay.success is False
    finally:
        configure_meeting_transcripts(previous)
    await async_session.refresh(row)
    assert row.report_current == report
    assert (row.transcript_encrypted is None) is (intervention in {"none", "lost_ack", "no_op"})
    assert outcome.success is (intervention in {"none", "no_op"})
    if intervention in {"changed", "disabled", "lost_ack"}:
        assert (
            draft_refusal_code(outcome)
            == {
                "changed": "STALE_STATE",
                "disabled": "CAPABILITY_DISABLED",
                "lost_ack": "COMPLETION_UNKNOWN",
            }[intervention]
        )
    hints = [queue.get_nowait() for _ in range(queue.qsize())]
    hints = [event for event in hints if event.type == "application_state_changed"]
    assert len(hints) == int(intervention == "none")
    if hints:
        assert hints[0].metadata["change"]["resources"] == ["meetings"]
        assert "transcript_digest" not in str(hints[0].metadata)
