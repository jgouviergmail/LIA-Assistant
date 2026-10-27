"""Original native HITL and real ledger queue only an acknowledged owned rebuild."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_regeneration_editing import rebuild_meeting_regeneration
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_meeting_lifecycle_tools
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.regeneration_gateway import SavedMeetingRegeneration
from src.domains.users.models import User
from src.infrastructure.meeting_regeneration import configure_meeting_regeneration
from tests.helpers.runtime_context import make_tool_runtime
from tests.integration.application_runtime_context import installed_runtime_context
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = [pytest.mark.integration, pytest.mark.usefixtures("agent_registry")]


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "transcript_changed",
        "body_changed",
        "disabled",
        "meetings_off",
        "foreign",
        "live",
        "invalid_current",
        "missing_transcript",
        "lost_ack",
        "post_read_failure",
        "amend",
    ],
)
async def test_regeneration_uses_original_human_consent_and_real_effect_ledger(
    async_session: AsyncSession,
    test_user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path))
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        transcript_encrypted=encrypt_data(
            '[ {"speaker":"S1","start":0,"end":1,"text":"private-transcript"} ]'
        ),
        report_current={"title": "Controlled", "participants": [], "sections": []},
    )
    if scenario == "invalid_current":
        row.report_current = {"malformed": True}
    if scenario == "missing_transcript":
        row.transcript_encrypted = None
    if scenario == "foreign":
        row.user_id = await _user(async_session)
    if scenario == "live":
        row.status = MeetingStatus.RECORDING
    async_session.add(row)
    await async_session.commit()
    owner, identity = test_user.id, row.id

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "meeting_regeneration_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_meeting_lifecycle_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    previous = configure_meeting_regeneration(SavedMeetingRegeneration())
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
            patch("src.domains.meetings.regeneration.launch_regenerate") as launch,
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await application_meeting_lifecycle_tools.regenerate_lia_meeting_report_tool.coroutine(
                request={"meeting_id": str(identity)},
                runtime=make_tool_runtime(
                    user_id=owner, store=InMemoryStore(), execution_mode=mode
                ),
            )
            launch.assert_not_called()
            if scenario in {"foreign", "live", "missing_transcript"}:
                assert not proposal.success
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            assert "private-transcript" not in str(content)
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected) as refused:
                    await execute_application_action_draft(content, owner, object())
                assert refused.value.code == "CONFIRMATION_MISSING"
                launch.assert_not_called()
                return
            if scenario in {"transcript_changed", "amend"}:
                row.transcript_encrypted = encrypt_data(
                    '[ {"speaker":"S1","start":0,"end":1,"text":"changed-transcript"} ]'
                )
                await async_session.commit()
            if scenario == "body_changed":
                row.report_current = {"title": "Changed", "participants": [], "sections": []}
                await async_session.commit()
            if scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "meetings_off":
                monkeypatch.setattr(settings, "meetings_enabled", False)
            if scenario == "amend":
                content = await rebuild_meeting_regeneration(
                    ApplicationActionDraftContent.model_validate(content),
                    {"intent": {"meeting_id": str(identity)}},
                )
                launch.assert_not_called()
            if scenario == "post_read_failure":
                from unittest.mock import AsyncMock

                monkeypatch.setattr(
                    "src.domains.meetings.service.MeetingService._fresh",
                    AsyncMock(side_effect=RuntimeError("Controlled post-commit read failure")),
                )
            if scenario == "lost_ack":
                original_commit = async_session.commit
                original_requeue = __import__(
                    "src.domains.meetings.repository", fromlist=["MeetingRepository"]
                ).MeetingRepository.begin_regenerate

                async def requeue(repo, *args, **kwargs):
                    result = await original_requeue(repo, *args, **kwargs)

                    async def commit() -> None:
                        monkeypatch.setattr(async_session, "commit", original_commit)
                        await original_commit()
                        raise OperationalError(
                            "COMMIT", {}, Exception("Controlled lost acknowledgment")
                        )

                    monkeypatch.setattr(async_session, "commit", commit)
                    return result

                monkeypatch.setattr(
                    "src.domains.meetings.repository.MeetingRepository.begin_regenerate", requeue
                )
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            result = await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "meeting-regeneration-flow"}},
                "meeting-regeneration-flow",
                "fr",
            )
            if scenario in {"valid", "amend", "post_read_failure", "invalid_current"}:
                launch.assert_called_once_with(identity)
                assert result.result_data["committed"]
                assert (
                    result.result_data["values"]["meeting_regeneration"]["processing_completed"]
                    is False
                )
                assert result.success is (scenario != "post_read_failure")
                await async_session.refresh(row)
                assert row.status is MeetingStatus.READY and row.stage.value == "synthesizing"
                changes = []
                while not queue.empty():
                    chunk = queue.get_nowait()
                    if chunk.type == "application_state_changed":
                        changes.append(chunk.metadata["change"])
                assert len(changes) == 1 and changes[0]["resources"] == ["meetings"]
                assert changes[0]["changed_fields"] == ["meeting_regeneration"]
            else:
                assert not result.success
                launch.assert_not_called()
            count = launch.call_count
            await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "meeting-regeneration-flow"}},
                "meeting-regeneration-flow",
                "fr",
            )
            assert launch.call_count == count
    finally:
        configure_meeting_regeneration(previous)
