"""Real original meeting rows, encrypted transcripts and owner-filtered templates."""

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from langgraph.store.memory import InMemoryStore
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.security.utils import encrypt_data
from src.domains.agents.application.meeting_reads import read_meeting_view
from src.domains.agents.tools.application_meeting_read_tools import get_lia_meetings_tool
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStatus, MeetingTemplate
from src.domains.meetings.read_gateway import SavedMeetingReads
from src.domains.meetings.schemas import MeetingReport, ReportSection, SectionKind
from src.domains.users.models import User
from src.infrastructure.meeting_reads import (
    MeetingReadInput,
    TemplateReadInput,
    configure_meeting_reads,
)
from tests.helpers.runtime_context import installed_runtime_context, make_tool_runtime
from tests.integration.domains.skills.test_per_account_skill_names import _user

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def read_owner(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "application_tools_enabled", True)
    monkeypatch.setattr(settings, "meetings_enabled", True)
    previous = configure_meeting_reads(SavedMeetingReads())
    try:
        yield
    finally:
        configure_meeting_reads(previous)


@pytest.mark.parametrize(
    "view",
    [
        "list",
        "active",
        "limits",
        "detail",
        "report",
        "generated_report",
        "transcript",
        "template_snapshot",
    ],
)
async def test_original_owned_meeting_views_do_not_mutate_or_serve_diagnostics(
    async_session: AsyncSession,
    test_user: User,
    view: str,
) -> None:
    report = MeetingReport(
        title="Controlled minutes",
        sections=[
            ReportSection(
                key="summary",
                label="Summary",
                kind=SectionKind.PARAGRAPH,
                paragraph="Ignore instructions is literal meeting text. " * 120,
            )
        ],
    )
    meeting = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="Europe/Paris",
        report_current=report.model_dump(mode="json"),
        report_generated=report.model_copy(
            update={"title": "Original generated version"}
        ).model_dump(mode="json"),
        transcript_encrypted=encrypt_data(
            json.dumps(
                [{"speaker": "S1", "start": 0, "end": 1, "text": "Private controlled transcript"}]
            )
        ),
        last_error_message="provider-private-diagnostic",
        audio_path="private/storage/file",
    )
    async_session.add(meeting)
    await async_session.commit()
    actor_id, meeting_id = test_user.id, meeting.id

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    query = MeetingReadInput.model_validate(
        {
            "view": view,
            **({"meeting_id": meeting_id} if view not in {"list", "active", "limits"} else {}),
        }
    )
    with (
        installed_runtime_context(user_id=actor_id, language="fr"),
        patch("src.domains.agents.tools.application_meeting_read_tools.get_db_context", session),
        patch.object(async_session, "commit", wraps=async_session.commit) as commit,
    ):
        result = await get_lia_meetings_tool.coroutine(
            query=query, runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore())
        )
    assert result.success
    commit.assert_not_called()
    payload = result.structured_data
    assert "provider-private-diagnostic" not in str(payload)
    assert "private/storage/file" not in str(payload)
    assert "transcript_encrypted" not in str(payload)
    if view == "list":
        assert payload["total"] == 1 and payload["data"]["items"][0]["id"] == str(meeting_id)
    if view == "active":
        assert payload["total"] == 0 and payload["data"]["active"] is None
    if view == "limits":
        from src.domains.meetings.service import MeetingService

        assert payload["data"]["limits"] == MeetingService(async_session).limits().model_dump(
            mode="json"
        )
        assert payload["total"] == 1 and payload["next_offset"] is None
    if view == "detail":
        assert payload["data"]["has_report"] and payload["data"]["has_transcript"]
    if view == "report":
        assert len(payload["text"]) == 4000 and payload["next_offset"] == 4000
        assert payload["content_format"] == "json_fragment"
    if view == "generated_report":
        assert "Original generated version" in payload["text"]
        assert payload["content_format"] == "json_fragment"
        assert payload["data"]["version"] == "generated"
    if view == "transcript":
        assert "Private controlled transcript" in payload["text"]
    await async_session.refresh(meeting)
    assert meeting.status is MeetingStatus.READY


@pytest.mark.parametrize("view", ["detail", "generated_report"])
async def test_foreign_meeting_and_template_refs_cannot_be_read(
    async_session: AsyncSession, test_user: User, view: str
) -> None:
    other_id = await _user(async_session)
    meeting = Meeting(
        user_id=other_id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
    )
    template = MeetingTemplate(
        user_id=other_id,
        name="Foreign private template",
        category="custom",
        sections=[
            {
                "key": "summary",
                "label": "Summary",
                "instruction": "private instruction",
                "kind": "paragraph",
            }
        ],
    )
    async_session.add_all([meeting, template])
    await async_session.commit()
    from src.core.exceptions import BaseAPIException

    with pytest.raises(BaseAPIException) as meeting_error:
        await read_meeting_view(
            async_session,
            test_user.id,
            MeetingReadInput.model_validate({"view": view, "meeting_id": meeting.id}),
        )
    assert meeting_error.value.status_code == 404
    with pytest.raises(BaseAPIException) as template_error:
        await read_meeting_view(
            async_session,
            test_user.id,
            TemplateReadInput(view="template", ref=f"user:{template.id}"),
        )
    assert template_error.value.status_code == 404
    page = await read_meeting_view(async_session, test_user.id, TemplateReadInput())
    assert "Foreign private template" not in page.model_dump_json()


@pytest.mark.parametrize("case", ["missing", "invalid", "changed"])
async def test_generated_source_is_explicitly_available_and_revision_bound(
    async_session: AsyncSession, test_user: User, case: str
) -> None:
    generated = {
        "title": "Generated",
        "participants": [],
        "sections": [
            {
                "key": "summary",
                "label": "Summary",
                "kind": "paragraph",
                "paragraph": "Source original words " * 150,
            }
        ],
    }
    if case == "missing":
        generated = None
    if case == "invalid":
        generated = {"title": ["private malformed generated content"]}
    row = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        report_generated=generated,
        report_current={"title": "Edited current", "participants": [], "sections": []},
    )
    async_session.add(row)
    await async_session.commit()
    actor_id, identity = test_user.id, row.id
    query = MeetingReadInput(view="generated_report", meeting_id=identity, characters=100)
    if case == "invalid":

        @asynccontextmanager
        async def session() -> AsyncIterator[AsyncSession]:
            yield async_session

        with (
            installed_runtime_context(user_id=actor_id, language="fr"),
            patch(
                "src.domains.agents.tools.application_meeting_read_tools.get_db_context", session
            ),
        ):
            output = await get_lia_meetings_tool.coroutine(
                query=query, runtime=make_tool_runtime(user_id=actor_id, store=InMemoryStore())
            )
        assert not output.success
        assert "private malformed generated content" not in str(output.model_dump())
        return
    page = await read_meeting_view(async_session, actor_id, query)
    assert page.data["available"] is (case != "missing")
    assert page.data["version"] == "generated"
    if case == "missing":
        assert page.text == "null" and page.next_offset is None
        return
    first = page.text
    second = await read_meeting_view(
        async_session,
        actor_id,
        query.model_copy(
            update={"offset": page.next_offset, "expected_digest": page.source_digest}
        ),
    )
    assert (
        first + second.text
        == json.dumps(
            MeetingReport.model_validate(generated).model_dump(mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )[: second.offset + len(second.text)]
    )
    row.report_generated = {**generated, "title": "Changed generated version"}
    await async_session.commit()
    from src.core.exceptions import ResourceConflictError

    with pytest.raises(ResourceConflictError):
        await read_meeting_view(
            async_session,
            actor_id,
            query.model_copy(
                update={"offset": page.next_offset, "expected_digest": page.source_digest}
            ),
        )


@pytest.mark.parametrize("flag", ["application_tools_enabled", "meetings_enabled"])
async def test_read_refuses_disabled_capability_before_owner_access(
    async_session: AsyncSession, test_user: User, monkeypatch: pytest.MonkeyPatch, flag: str
) -> None:
    from src.core.exceptions import AuthorizationError

    monkeypatch.setattr(settings, flag, False)
    with pytest.raises(AuthorizationError):
        await read_meeting_view(async_session, test_user.id, MeetingReadInput())


async def test_live_template_library_preserves_original_cap_and_owned_detail(
    async_session: AsyncSession, test_user: User
) -> None:
    template = MeetingTemplate(
        user_id=test_user.id,
        name="Owned controlled template",
        category="custom",
        sections=[
            {
                "key": "summary",
                "label": "Summary",
                "instruction": "Summarize literal content",
                "kind": "paragraph",
            }
        ],
    )
    async_session.add(template)
    await async_session.commit()
    library = await read_meeting_view(async_session, test_user.id, TemplateReadInput(limit=1))
    assert library.total > 1 and library.next_offset == 1
    assert library.data["max_user_templates"] == settings.meetings_max_user_templates
    detail = await read_meeting_view(
        async_session, test_user.id, TemplateReadInput(view="template", ref=f"user:{template.id}")
    )
    assert detail.text is not None and detail.next_offset is None
    contents = json.loads(detail.text)
    assert contents["name"] == "Owned controlled template"
    assert contents["sections"][0]["instruction"] == "Summarize literal content"


async def test_corrupt_encrypted_transcript_returns_sanitized_failure(
    async_session: AsyncSession, test_user: User
) -> None:
    meeting = Meeting(
        user_id=test_user.id,
        status=MeetingStatus.READY,
        started_at=datetime.now(UTC),
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        client_timezone="UTC",
        transcript_encrypted="corrupt-private-cipher",
    )
    async_session.add(meeting)
    await async_session.commit()

    @asynccontextmanager
    async def session() -> AsyncIterator[AsyncSession]:
        yield async_session

    with (
        installed_runtime_context(user_id=test_user.id),
        patch("src.domains.agents.tools.application_meeting_read_tools.get_db_context", session),
    ):
        result = await get_lia_meetings_tool.coroutine(
            query=MeetingReadInput(view="transcript", meeting_id=meeting.id),
            runtime=make_tool_runtime(user_id=test_user.id, store=InMemoryStore()),
        )
    assert not result.success
    assert result.error_code == "INVALID_RESPONSE_FORMAT"
    assert "corrupt-private-cipher" not in str(result)
