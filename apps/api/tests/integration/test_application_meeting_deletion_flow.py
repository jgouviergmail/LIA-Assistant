"""Real native human consent and ledger delete once and preserve derived minutes."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_deletion_editing import rebuild_meeting_deletion
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_meeting_lifecycle_tools
from src.domains.meetings.audio_store import MeetingAudioStore
from src.domains.meetings.deletion_gateway import SavedMeetingDeletions
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus
from src.domains.meetings.repository import MeetingRepository
from src.domains.rag_spaces.models import RAGDocument, RAGSpace
from src.domains.users.models import User
from src.infrastructure.meeting_deletions import configure_meeting_deletions
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
        "foreign",
        "live",
        "disabled",
        "body_changed",
        "audio_changed",
        "lost_ack",
        "cleanup_failed",
        "amend",
        "projection",
    ],
)
async def test_whole_meeting_deletion_uses_original_hitl_and_real_ledger(
    async_session: AsyncSession,
    test_user: User,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    monkeypatch.setattr(settings, "meetings_storage_path", str(tmp_path / "audio"))
    monkeypatch.setattr(settings, "rag_spaces_storage_path", str(tmp_path / "rag"))
    owner = test_user.id
    row = Meeting(
        user_id=owner,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_current={"title": "Selected", "participants": [], "sections": []},
    )
    if scenario == "foreign":
        row.user_id = await _user(async_session)
    if scenario == "live":
        row.status = MeetingStatus.RECORDING
    if scenario == "projection":
        space = RAGSpace(user_id=owner, name="Controlled meetings", kind="meetings")
        async_session.add(space)
        await async_session.flush()
        document = RAGDocument(
            user_id=owner,
            space_id=space.id,
            filename="minutes.md",
            original_filename="Selected minutes",
            file_size=4,
            content_type="text/markdown",
            status="ready",
            source_type="meeting",
        )
        async_session.add(document)
        await async_session.flush()
        row.rag_document_id = document.id
    async_session.add(row)
    await async_session.flush()
    child = Meeting(
        user_id=row.user_id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        source_meeting_id=row.id,
    )
    async_session.add(child)
    await async_session.commit()
    identity, child_id = row.id, child.id
    store = MeetingAudioStore(tmp_path / "audio")
    await store.write_segment(row.user_id, identity, 0, b"private-audio")

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "meeting_deletion_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_meeting_lifecycle_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    previous = configure_meeting_deletions(SavedMeetingDeletions())
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
            patch.dict(draft_executor.EXECUTOR_REGISTRY),
        ):
            proposal = await application_meeting_lifecycle_tools.delete_lia_meeting_tool.coroutine(
                request={"meeting_id": str(identity)},
                runtime=make_tool_runtime(
                    user_id=owner, store=InMemoryStore(), execution_mode=mode
                ),
            )
            assert await async_session.get(Meeting, identity, populate_existing=True) is not None
            assert store.meeting_dir(row.user_id, identity).exists()
            if scenario in {"foreign", "live"}:
                assert not proposal.success
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            assert "private-audio" not in str(content)
            assert content["before"]["meeting_delete"]["derived_minutes_kept"] == 1
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected) as refused:
                    await execute_application_action_draft(content, owner, object())
                assert refused.value.code == "CONFIRMATION_MISSING"
                return
            if scenario in {"body_changed", "amend"}:
                row.report_current = {"title": "Edited", "participants": [], "sections": []}
                await async_session.commit()
            if scenario == "audio_changed":
                await store.write_segment(owner, identity, 0, b"changed-audio")
            if scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "cleanup_failed":
                monkeypatch.setattr(
                    MeetingAudioStore, "purge_meeting", AsyncMock(return_value=False)
                )
            if scenario == "amend":
                content = await rebuild_meeting_deletion(
                    ApplicationActionDraftContent.model_validate(content),
                    {"intent": {"meeting_id": str(identity)}},
                )
            if scenario == "lost_ack":
                original_commit, original_delete = (
                    async_session.commit,
                    MeetingRepository.delete_unless_leased,
                )

                async def delete(repo, *args, **kwargs):
                    result = await original_delete(repo, *args, **kwargs)

                    async def lost_commit() -> None:
                        monkeypatch.setattr(async_session, "commit", original_commit)
                        await original_commit()
                        raise OperationalError(
                            "COMMIT", {}, Exception("Controlled lost acknowledgment")
                        )

                    monkeypatch.setattr(async_session, "commit", lost_commit)
                    return result

                monkeypatch.setattr(MeetingRepository, "delete_unless_leased", delete)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            result = await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "delete-meeting-flow"}},
                "delete-meeting-flow",
                "fr",
            )
            if scenario in {"valid", "amend", "projection", "cleanup_failed"}:
                assert result.success and result.result_data["committed"]
                assert result.result_data["values"]["meeting_delete"]["database_deleted"] is True
                assert result.result_data["values"]["meeting_delete"][
                    "files_cleanup_completed"
                ] is (scenario != "cleanup_failed")
                kept = await async_session.get(Meeting, child_id, populate_existing=True)
                assert kept is not None and kept.source_meeting_id is None
                changes = []
                while not queue.empty():
                    chunk = queue.get_nowait()
                    if chunk.type == "application_state_changed":
                        changes.append(chunk.metadata["change"])
                assert len(changes) == 1 and changes[0]["changed_fields"] == ["meeting_delete"]
                assert changes[0]["resources"] == (
                    ["meetings", "spaces"] if scenario == "projection" else ["meetings"]
                )
                if scenario == "projection":
                    assert (
                        await async_session.scalar(
                            select(RAGDocument).where(RAGDocument.id == document.id)
                        )
                        is None
                    )
            else:
                assert not result.success
            retained = scenario not in {
                "valid",
                "amend",
                "projection",
                "cleanup_failed",
                "lost_ack",
            }
            assert (
                await async_session.get(Meeting, identity, populate_existing=True) is not None
            ) is retained
            await draft_executor._execute_confirmed_draft(
                payload,
                {"configurable": {"thread_id": "delete-meeting-flow"}},
                "delete-meeting-flow",
                "fr",
            )
            assert (
                await async_session.get(Meeting, identity, populate_existing=True) is not None
            ) is retained
    finally:
        configure_meeting_deletions(previous)
