"""Reformatting minutes with another template (ADR-259): in place, or as new minutes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.exceptions import BaseAPIException
from src.domains.meetings import reformat as module
from src.domains.meetings.models import MeetingIndexState, MeetingStage, MeetingStatus
from src.domains.meetings.reformat import reformat_meeting
from src.domains.meetings.schemas import (
    MeetingReformatRequest,
    SectionKind,
    TemplateCategory,
    TemplateSection,
)
from src.domains.meetings.template_ref import TemplateRef
from src.domains.meetings.template_service import ResolvedTemplate

pytestmark = pytest.mark.unit

USER = uuid.uuid4()
RESOLVED = ResolvedTemplate(
    ref=TemplateRef.builtin("transcript_clean"),
    name="Transcription normalisée",
    category=TemplateCategory.TRANSCRIPT,
    sections=[
        TemplateSection(key="transcript", label="T", instruction="i", kind=SectionKind.TRANSCRIPT)
    ],
    auto_selectable=False,
)


def _meeting(**over):
    meeting = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=USER,
        status=MeetingStatus.READY,
        stage=None,
        transcript_encrypted="ciphertext",
        audio_format="pcm_s16le_16",
        segment_count=3,
        audio_bytes=1000,
        audio_duration_seconds=90.0,
        audio_gaps=0,
        started_at=datetime(2026, 9, 3, 8, 0, tzinfo=UTC),
        stopped_at=datetime(2026, 9, 3, 9, 0, tzinfo=UTC),
        client_timezone="Europe/Paris",
        location_lat=None,
        location_lon=None,
        location_accuracy_m=None,
        location_label="Salle B",
        calendar_event_id=None,
        calendar_provider=None,
        stt_provider="openai",
        stt_model="gpt-4o-transcribe-diarize",
        stt_language_hint="fr",
        stt_detected_language="fr",
        stt_diarized=True,
        stt_audio_seconds=90.0,
    )
    for key, value in over.items():
        setattr(meeting, key, value)
    return meeting


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> dict:
    service = MagicMock()
    service.db = MagicMock()
    service.db.commit = AsyncMock()
    service.repo = AsyncMock()
    service.repo.begin_regenerate.return_value = True
    meeting = _meeting()
    service.get = AsyncMock(return_value=meeting)
    service._fresh = AsyncMock(return_value=meeting)
    template_service = MagicMock()
    template_service.resolve = AsyncMock(return_value=RESOLVED)
    monkeypatch.setattr(module, "MeetingTemplateService", MagicMock(return_value=template_service))
    launch = MagicMock()
    monkeypatch.setattr(module, "launch_regenerate", launch)
    return {"service": service, "meeting": meeting, "launch": launch, "templates": template_service}


def _code(exc: pytest.ExceptionInfo[BaseAPIException]) -> str:
    detail = exc.value.detail
    assert isinstance(detail, dict)
    return str(detail["code"])


async def test_replace_rewrites_the_same_meeting_with_the_new_template(world: dict) -> None:
    request = MeetingReformatRequest(template_ref="builtin:transcript_clean", mode="replace")
    result = await reformat_meeting(world["service"], USER, world["meeting"].id, request, "fr")
    assert result is world["meeting"]
    world["service"].repo.begin_regenerate.assert_awaited_once()
    kwargs = world["service"].repo.begin_regenerate.await_args.kwargs
    assert kwargs["values"] == {
        "template_ref": "builtin:transcript_clean",
        "template_name": "Transcription normalisée",
        "template_selection": "user",
        "template_selection_reason": None,
    }
    world["launch"].assert_called_once_with(world["meeting"].id)
    world["service"].repo.create_from_transcript.assert_not_awaited()


async def test_replace_refuses_while_a_regeneration_runs(world: dict) -> None:
    world["service"].repo.begin_regenerate.return_value = False
    request = MeetingReformatRequest(template_ref="builtin:transcript_clean", mode="replace")
    with pytest.raises(BaseAPIException) as exc:
        await reformat_meeting(world["service"], USER, world["meeting"].id, request, "fr")
    assert exc.value.status_code == 409 and _code(exc) == "regeneration_in_progress"
    world["launch"].assert_not_called()


async def test_new_creates_derived_minutes_from_the_same_transcript_without_audio(
    world: dict,
) -> None:
    source = world["meeting"]
    created = _meeting(id=uuid.uuid4(), status=MeetingStatus.READY, stage=MeetingStage.SYNTHESIZING)
    world["service"].repo.create_from_transcript.return_value = created
    request = MeetingReformatRequest(template_ref="builtin:transcript_clean", mode="new")
    result = await reformat_meeting(world["service"], USER, source.id, request, "fr")
    assert result is created
    world["service"].repo.create_from_transcript.assert_awaited_once()
    args, kwargs = world["service"].repo.create_from_transcript.await_args
    assert args[0] is source
    assert kwargs["values"]["template_ref"] == "builtin:transcript_clean"
    assert kwargs["values"]["template_selection"] == "user"
    world["service"].db.commit.assert_awaited_once()
    world["launch"].assert_called_once_with(created.id)
    world["service"].repo.begin_regenerate.assert_not_awaited()


async def test_a_meeting_without_transcript_cannot_be_reformatted(world: dict) -> None:
    world["meeting"].transcript_encrypted = None
    request = MeetingReformatRequest(template_ref="builtin:transcript_clean", mode="new")
    with pytest.raises(BaseAPIException) as exc:
        await reformat_meeting(world["service"], USER, world["meeting"].id, request, "fr")
    assert exc.value.status_code == 409 and _code(exc) == "transcript_unavailable"
    world["templates"].resolve.assert_not_awaited()


async def test_a_meeting_not_ready_cannot_be_reformatted(world: dict) -> None:
    world["meeting"].status = MeetingStatus.PROCESSING
    request = MeetingReformatRequest(template_ref="builtin:transcript_clean", mode="replace")
    with pytest.raises(BaseAPIException) as exc:
        await reformat_meeting(world["service"], USER, world["meeting"].id, request, "fr")
    assert exc.value.status_code == 409 and _code(exc) == "report_not_ready"


async def test_an_unknown_template_is_refused_before_anything_changes(world: dict) -> None:
    world["templates"].resolve.side_effect = BaseAPIException(
        status_code=404, detail={"code": "template_not_found"}
    )
    request = MeetingReformatRequest(template_ref="builtin:nope", mode="replace")
    with pytest.raises(BaseAPIException) as exc:
        await reformat_meeting(world["service"], USER, world["meeting"].id, request, "fr")
    assert exc.value.status_code == 404
    world["service"].repo.begin_regenerate.assert_not_awaited()
    world["launch"].assert_not_called()


# ------------------------------------------------------------ repository shape


def test_derived_row_values_copy_the_facts_and_never_the_audio_nor_the_stt_price() -> None:
    from src.domains.meetings.repository import derived_meeting_values

    source = _meeting()
    values = derived_meeting_values(
        source,
        template_values={"template_ref": "builtin:transcript_clean", "template_name": "T"},
        rag_enabled=True,
    )
    assert values["user_id"] == USER and values["source_meeting_id"] == source.id
    assert values["status"] is MeetingStatus.READY and values["stage"] is MeetingStage.SYNTHESIZING
    assert values["transcript_encrypted"] == "ciphertext"
    assert values["audio_path"] is None and values["audio_purged_at"] is not None
    assert values["keep_audio_until"] is None
    assert "stt_cost_eur" not in values or values["stt_cost_eur"] is None
    assert values["stt_provider"] == "openai" and values["stt_diarized"] is True
    assert values["audio_duration_seconds"] == 90.0 and values["location_label"] == "Salle B"
    assert values["report_generated"] is None and values["report_current"] is None
    assert values["index_state"] is MeetingIndexState.PENDING
    assert values["template_ref"] == "builtin:transcript_clean"
    assert values["template_selection"] == "user"
    assert derived_meeting_values(source, template_values={}, rag_enabled=False)["index_state"] is (
        MeetingIndexState.DISABLED
    )
