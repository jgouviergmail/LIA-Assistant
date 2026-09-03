"""MeetingService refusals (ADR-258): every bound is refused with a stable code
BEFORE a byte reaches the disk, and a stop never invents missing audio."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.config import settings
from src.core.exceptions import BaseAPIException
from src.domains.meetings import service as service_module
from src.domains.meetings.models import MeetingAudioFormat, MeetingStatus
from src.domains.meetings.schemas import MeetingPatchRequest, MeetingStopRequest
from src.domains.meetings.service import MeetingService

pytestmark = pytest.mark.unit


def _meeting(
    status: MeetingStatus, audio_format: MeetingAudioFormat = MeetingAudioFormat.PCM_S16LE_16
):
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=status,
        audio_format=audio_format,
        segment_count=3,
        audio_bytes=96000,
        audio_path=None,
        audio_purged_at=None,
        rag_document_id=None,
    )


@pytest.fixture
def service() -> MeetingService:
    # The session is a plain MagicMock: `expire_all` is synchronous on it, and an
    # AsyncMock would hand back a never-awaited coroutine (a test failure here).
    db = MagicMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    svc = MeetingService(db)
    svc.repo = AsyncMock()
    svc.store = MagicMock()
    svc.store.write_segment = AsyncMock(return_value=(10, False))
    svc.store.list_sequences = AsyncMock(return_value=[0, 1, 2])
    svc.store.missing_sequences = MagicMock(
        side_effect=lambda present, expected: [s for s in range(expected) if s not in set(present)]
    )
    return svc


def _code(exc: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = exc.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


async def test_segment_refused_when_the_meeting_is_not_live(service: MeetingService) -> None:
    meeting = _meeting(MeetingStatus.READY)
    service.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await service.accept_segment(meeting.user_id, meeting.id, sequence=0, body=b"\x00\x00")
    assert exc.value.status_code == 409 and _code(exc) == "meeting_not_recording"
    service.store.write_segment.assert_not_awaited()


async def test_segment_over_the_byte_cap_never_touches_the_disk(service: MeetingService) -> None:
    meeting = _meeting(MeetingStatus.RECORDING)
    service.repo.get_for_user.return_value = meeting
    body = b"\x00" * (settings.meetings_segment_max_bytes + 2)
    with pytest.raises(BaseAPIException) as exc:
        await service.accept_segment(meeting.user_id, meeting.id, sequence=0, body=body)
    assert exc.value.status_code == 413 and _code(exc) == "segment_too_large"
    service.store.write_segment.assert_not_awaited()


async def test_segment_beyond_the_duration_cap_is_refused(service: MeetingService) -> None:
    meeting = _meeting(MeetingStatus.RECORDING)
    service.repo.get_for_user.return_value = meeting
    max_segments = settings.meetings_max_duration_minutes * 60 // settings.meetings_segment_seconds
    with pytest.raises(BaseAPIException) as exc:
        await service.accept_segment(
            meeting.user_id, meeting.id, sequence=max_segments, body=b"\x00\x00"
        )
    assert exc.value.status_code == 413 and _code(exc) == "duration_cap_reached"
    service.store.write_segment.assert_not_awaited()


async def test_odd_pcm_segment_is_malformed(service: MeetingService) -> None:
    meeting = _meeting(MeetingStatus.RECORDING)
    service.repo.get_for_user.return_value = meeting
    with pytest.raises(BaseAPIException) as exc:
        await service.accept_segment(meeting.user_id, meeting.id, sequence=0, body=b"\x00\x00\x00")
    assert _code(exc) == "segment_malformed"


async def test_a_segment_losing_the_race_against_stop_is_a_conflict(
    service: MeetingService,
) -> None:
    meeting = _meeting(MeetingStatus.RECORDING)
    service.repo.get_for_user.return_value = meeting
    service.repo.record_segment.return_value = None  # the row was no longer live
    with pytest.raises(BaseAPIException) as exc:
        await service.accept_segment(meeting.user_id, meeting.id, sequence=0, body=b"\x00\x00")
    assert exc.value.status_code == 409 and _code(exc) == "meeting_not_recording"


async def test_an_accepted_segment_is_acknowledged_with_the_fresh_counters(
    service: MeetingService,
) -> None:
    meeting = _meeting(MeetingStatus.INTERRUPTED)
    service.repo.get_for_user.return_value = meeting
    # The ack is read from RETURNING: a bulk UPDATE leaves the identity map stale.
    service.repo.record_segment.return_value = (MeetingStatus.RECORDING, 4, 128000)
    ack = await service.accept_segment(meeting.user_id, meeting.id, sequence=3, body=b"\x00\x00")
    assert (ack.sequence, ack.segment_count, ack.audio_bytes, ack.status) == (
        3,
        4,
        128000,
        MeetingStatus.RECORDING,
    )
    service.repo.record_segment.assert_awaited_once_with(meeting.id, sequence=3, added_bytes=10)
    service.repo.get_for_user.assert_awaited_once()


async def test_a_stop_expires_the_session_before_re_reading(service: MeetingService) -> None:
    """Measured 2026-09-03: without the expiry, a stop answered ``status: recording``."""
    meeting = _meeting(MeetingStatus.RECORDING)
    service.repo.get_for_user.return_value = meeting
    service.repo.stop.return_value = True
    await service.stop(meeting.user_id, meeting.id, MeetingStopRequest(segment_count=3))
    service.db.expire_all.assert_called_once()
    assert service.repo.get_for_user.await_count == 2


class TestDelete:
    """The knowledge-space projection never outlives the meeting."""

    async def test_the_rag_document_goes_before_the_row(
        self, service: MeetingService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meeting = _meeting(MeetingStatus.READY)
        meeting.rag_document_id = uuid.uuid4()
        service.repo.get_for_user.return_value = meeting
        service.store.purge_meeting = AsyncMock()
        document = SimpleNamespace(id=meeting.rag_document_id, space_id=uuid.uuid4())
        doc_repo = MagicMock()
        doc_repo.get_by_id = AsyncMock(return_value=document)
        rag_service = MagicMock()
        rag_service.delete_document = AsyncMock()
        monkeypatch.setattr(
            "src.domains.rag_spaces.repository.RAGDocumentRepository",
            MagicMock(return_value=doc_repo),
        )
        monkeypatch.setattr(
            "src.domains.rag_spaces.service.RAGSpaceService", MagicMock(return_value=rag_service)
        )
        await service.delete(meeting.user_id, meeting.id)
        rag_service.delete_document.assert_awaited_once_with(
            document.space_id, document.id, meeting.user_id
        )
        service.repo.delete.assert_awaited_once_with(meeting)
        service.store.purge_meeting.assert_awaited_once_with(meeting.user_id, meeting.id)

    async def test_a_meeting_without_projection_deletes_nothing_in_the_space(
        self, service: MeetingService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        meeting = _meeting(MeetingStatus.FAILED)
        service.repo.get_for_user.return_value = meeting
        service.store.purge_meeting = AsyncMock()
        rag_service = MagicMock(return_value=MagicMock(delete_document=AsyncMock()))
        monkeypatch.setattr("src.domains.rag_spaces.service.RAGSpaceService", rag_service)
        await service.delete(meeting.user_id, meeting.id)
        rag_service.assert_not_called()
        service.repo.delete.assert_awaited_once_with(meeting)

    async def test_a_processing_meeting_cannot_be_deleted(self, service: MeetingService) -> None:
        meeting = _meeting(MeetingStatus.PROCESSING)
        service.repo.get_for_user.return_value = meeting
        with pytest.raises(BaseAPIException) as exc:
            await service.delete(meeting.user_id, meeting.id)
        assert _code(exc) == "meeting_in_progress"
        service.repo.delete.assert_not_awaited()


# ---------------------------------------------------------------- ADR-259: the meeting's template


class TestTemplateChoice:
    @pytest.fixture
    def templates(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        from src.domains.meetings.schemas import TemplateCategory
        from src.domains.meetings.template_ref import TemplateRef
        from src.domains.meetings.template_service import ResolvedTemplate

        resolved = ResolvedTemplate(
            ref=TemplateRef.builtin("daily_standup"),
            name="Daily",
            category=TemplateCategory.MEETING,
            sections=[],
            auto_selectable=True,
        )
        fake = MagicMock()
        fake.resolve = AsyncMock(return_value=resolved)
        monkeypatch.setattr(service_module, "MeetingTemplateService", MagicMock(return_value=fake))
        return fake

    async def test_a_live_meeting_takes_the_template_and_remembers_its_name(
        self, service: MeetingService, templates: MagicMock
    ) -> None:
        meeting = _meeting(MeetingStatus.RECORDING)
        meeting.report_current = None
        service.repo.get_for_user.return_value = meeting
        await service.patch_report(
            meeting.user_id, meeting.id, MeetingPatchRequest(template_ref="builtin:daily_standup")
        )
        templates.resolve.assert_awaited_once()
        service.repo.set_template.assert_awaited_once_with(
            meeting.id, ref="builtin:daily_standup", name="Daily"
        )
        service.repo.set_report_current.assert_not_awaited()

    async def test_once_processing_started_the_template_is_locked(
        self, service: MeetingService, templates: MagicMock
    ) -> None:
        for status in (MeetingStatus.PROCESSING, MeetingStatus.READY):
            meeting = _meeting(status)
            meeting.report_current = None
            service.repo.get_for_user.return_value = meeting
            with pytest.raises(BaseAPIException) as exc:
                await service.patch_report(
                    meeting.user_id,
                    meeting.id,
                    MeetingPatchRequest(template_ref="builtin:daily_standup"),
                )
            assert exc.value.status_code == 409 and _code(exc) == "template_locked"
        service.repo.set_template.assert_not_awaited()
