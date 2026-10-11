"""Original HITL and real effect ledger protect both reformat destinations."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.agents.api.schemas import ChatStreamChunk
from src.domains.agents.application.command_service import CommandRejected
from src.domains.agents.application.draft_execution import execute_application_action_draft
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.domains.agents.application.meeting_reformat_editing import rebuild_meeting_reformat
from src.domains.agents.services import draft_executor
from src.domains.agents.tools import application_meeting_lifecycle_tools
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus, MeetingTemplate
from src.domains.meetings.reformat_gateway import SavedMeetingReformat
from src.domains.users.models import User
from src.infrastructure.meeting_reformat import configure_meeting_reformat
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("mode", ["pipeline", "react"])
@pytest.mark.parametrize("reformat_mode", ["replace", "new"])
@pytest.mark.parametrize(
    "scenario",
    [
        "valid",
        "no_confirmation",
        "foreign_template",
        "disabled",
        "source_changed",
        "template_changed",
        "amend",
        "lost_ack",
    ],
)
async def test_reformat_original_consent_and_real_ledger(
    async_session: AsyncSession,
    test_user: User,
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    reformat_mode: str,
    scenario: str,
) -> None:
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    owner = test_user.id
    row = Meeting(
        user_id=owner,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        transcript_encrypted=encrypt_data(
            '[{"speaker":"S1","start":0,"end":1,"text":"Private transcript"}]'
        ),
        report_current={"title": "Source", "participants": [], "sections": []},
    )
    template = MeetingTemplate(
        user_id=owner,
        name="Selected",
        sections=[
            {
                "key": "summary",
                "label": "Summary",
                "instruction": "Exact instructions",
                "kind": "paragraph",
            }
        ],
    )
    if scenario == "foreign_template":
        template.user_id = await _user(async_session)
    async_session.add_all([row, template])
    await async_session.commit()
    identity = row.id
    request = {
        "meeting_id": str(identity),
        "template_ref": f"user:{template.id}",
        "mode": reformat_mode,
    }

    @asynccontextmanager
    async def database() -> AsyncIterator[AsyncSession]:
        try:
            yield async_session
            await async_session.commit()
        except BaseException:
            await async_session.rollback()
            raise

    for module in ("command_service", "draft_execution", "meeting_reformat_editing"):
        monkeypatch.setattr(f"src.domains.agents.application.{module}.get_db_context", database)
    monkeypatch.setattr(application_meeting_lifecycle_tools, "get_db_context", database)
    monkeypatch.setattr("src.infrastructure.database.session.get_db_context", database)
    previous = configure_meeting_reformat(SavedMeetingReformat())
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
            proposal = await application_meeting_lifecycle_tools.reformat_lia_meeting_report_tool.coroutine(
                request=request,
                runtime=make_tool_runtime(
                    user_id=owner, store=InMemoryStore(), execution_mode=mode
                ),
            )
            launch.assert_not_called()
            if scenario == "foreign_template":
                assert not proposal.success
                return
            assert proposal.success and proposal.metadata["requires_confirmation"]
            item = next(iter(proposal.registry_updates.values()))
            content = item.payload["content"]
            assert "Private transcript" not in str(content)
            if scenario == "no_confirmation":
                with pytest.raises(CommandRejected) as refused:
                    await execute_application_action_draft(content, owner, object())
                assert refused.value.code == "CONFIRMATION_MISSING"
                launch.assert_not_called()
                return
            if scenario in {"source_changed", "amend"}:
                row.report_current = {"title": "Edited", "participants": [], "sections": []}
            if scenario == "template_changed":
                template.sections = [
                    {**template.sections[0], "instruction": "Changed instructions"}
                ]
            await async_session.commit()
            if scenario == "disabled":
                monkeypatch.setattr(settings, "application_tools_enabled", False)
            if scenario == "amend":
                content = await rebuild_meeting_reformat(
                    ApplicationActionDraftContent.model_validate(content), {"intent": request}
                )
                launch.assert_not_called()
            selected = content["intent"]["meeting_reformat"]
            from uuid import UUID

            target = UUID(selected["destination_id"])
            if scenario == "lost_ack":
                from src.domains.meetings.repository import MeetingRepository

                original_commit = async_session.commit
                method = (
                    "begin_regenerate" if reformat_mode == "replace" else "create_from_transcript"
                )
                original_write = getattr(MeetingRepository, method)

                async def write(repo, *args, **kwargs):
                    result = await original_write(repo, *args, **kwargs)

                    async def lost_commit() -> None:
                        monkeypatch.setattr(async_session, "commit", original_commit)
                        await original_commit()
                        raise OperationalError(
                            "COMMIT", {}, Exception("Controlled lost acknowledgment")
                        )

                    monkeypatch.setattr(async_session, "commit", lost_commit)
                    return result

                monkeypatch.setattr(MeetingRepository, method, write)
            draft_executor.register_executor("application_action", execute_application_action_draft)
            payload = {
                "draft_id": item.id,
                "draft_type": "application_action",
                "draft_content": content,
            }
            result = await draft_executor._execute_confirmed_draft(
                payload, {"configurable": {"thread_id": "reformat-flow"}}, "reformat-flow", "fr"
            )
            if scenario in {"valid", "amend"}:
                assert result.success and result.result_data["committed"]
                assert result.result_data["values"]["meeting_reformat"]["destination_id"] == str(
                    target
                )
                assert (
                    result.result_data["values"]["meeting_reformat"]["processing_completed"]
                    is False
                )
                launch.assert_called_once_with(target)
                await async_session.refresh(row)
                assert (row.stage is not None) is (reformat_mode == "replace")
                if reformat_mode == "new":
                    derived = await async_session.scalar(
                        select(Meeting).where(Meeting.id == target)
                    )
                    assert derived is not None and derived.source_meeting_id == identity
                    assert derived.audio_path is None and derived.stt_cost_eur is None
                changes = []
                while not queue.empty():
                    chunk = queue.get_nowait()
                    if chunk.type == "application_state_changed":
                        changes.append(chunk.metadata["change"])
                assert len(changes) == 1 and changes[0]["resources"] == ["meetings"]
                assert changes[0]["changed_fields"] == ["meeting_reformat"]
            else:
                assert not result.success
                launch.assert_not_called()
            count = launch.call_count
            await draft_executor._execute_confirmed_draft(
                payload, {"configurable": {"thread_id": "reformat-flow"}}, "reformat-flow", "fr"
            )
            assert launch.call_count == count
    finally:
        configure_meeting_reformat(previous)
