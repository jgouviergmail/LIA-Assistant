"""Native original HITL seals source bytes and launches one acknowledged retry."""

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
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_retry_editing import rebuild_meeting_retry
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_meeting_lifecycle_tools
from src.domains.meetings.audio_store import MeetingAudioStore
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.retry_gateway import SavedMeetingRetry
from src.domains.users.models import User
from src.infrastructure.meeting_retry import configure_meeting_retry
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
        "audio_changed",
        "body_changed",
        "disabled",
        "meetings_off",
        "foreign",
        "live",
        "lost_ack",
        "post_read_failure",
        "amend",
    ],
)
async def test_retry_uses_original_human_consent_and_real_effect_ledger(
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
        status=MeetingStatus.FAILED,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        attempts=3,
        report_current={"title": "Controlled", "participants": [], "sections": []},
    )
    if scenario == "foreign":
        row.user_id = await _user(async_session)
    if scenario == "live":
        row.status = MeetingStatus.RECORDING
    async_session.add(row)
    await async_session.commit()
    owner, identity = test_user.id, row.id
    audio = MeetingAudioStore(tmp_path)
    await audio.write_segment(row.user_id, identity, 0, b"private-audio")

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "meeting_retry_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_meeting_lifecycle_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    previous = configure_meeting_retry(SavedMeetingRetry())
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
            patch("src.domains.meetings.processing.launch_processing") as launch,
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await application_meeting_lifecycle_tools.retry_lia_meeting_tool.coroutine(
                request={"meeting_id": str(identity)},
                runtime=make_tool_runtime(
                    user_id=owner, store=InMemoryStore(), execution_mode=mode
                ),
            )
            launch.assert_not_called()
            if scenario in {"foreign", "live"}:
                assert not proposal.success
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            assert "private-audio" not in str(content)
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected) as refused:
                    await execute_application_action_draft(content, owner, object())
                assert refused.value.code == "CONFIRMATION_MISSING"
                launch.assert_not_called()
                return
            if scenario in {"audio_changed", "amend"}:
                await audio.write_segment(owner, identity, 0, b"changed-audio")
            if scenario == "body_changed":
                row.report_current = {"title": "Changed", "participants": [], "sections": []}
                await async_session.commit()
            if scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "meetings_off":
                monkeypatch.setattr(settings, "meetings_enabled", False)
            if scenario == "amend":
                content = await rebuild_meeting_retry(
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
                ).MeetingRepository.requeue_for_retry

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
                    "src.domains.meetings.repository.MeetingRepository.requeue_for_retry", requeue
                )
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            result = await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "meeting-retry-flow"}},
                "meeting-retry-flow",
                "fr",
            )
            if scenario in {"valid", "amend", "post_read_failure"}:
                launch.assert_called_once_with(identity)
                assert result.result_data["committed"]
                assert (
                    result.result_data["values"]["meeting_retry"]["processing_completed"] is False
                )
                assert result.success is (scenario != "post_read_failure")
                await async_session.refresh(row)
                assert row.status is MeetingStatus.STOPPED and row.attempts == 0
                changes = []
                while not queue.empty():
                    chunk = queue.get_nowait()
                    if chunk.type == "application_state_changed":
                        changes.append(chunk.metadata["change"])
                assert len(changes) == 1 and changes[0]["resources"] == ["meetings"]
                assert changes[0]["changed_fields"] == ["meeting_retry"]
            else:
                assert not result.success
                launch.assert_not_called()
            count = launch.call_count
            await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "meeting-retry-flow"}},
                "meeting-retry-flow",
                "fr",
            )
            assert launch.call_count == count
    finally:
        configure_meeting_retry(previous)
