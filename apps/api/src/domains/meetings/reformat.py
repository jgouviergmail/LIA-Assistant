"""Reformatting minutes with another template (ADR-259).

Two modes, one transcript:

- ``replace`` — the same meeting is rewritten in place (the old minutes stay
  readable until the new ones are published, like « Rebuild »);
- ``new`` — a new meeting row is derived from the same transcript: the facts
  are copied, the audio is not (it may already be purged, and the transcript
  is what a rewrite needs), the transcription price stays on the source, and
  the new minutes are indexed as their own knowledge-space document. The owner's
  vocabulary: never a « copy » — new minutes from the same transcript.
"""

from __future__ import annotations

import uuid

import structlog

from src.core.config import settings
from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.reformat_confirmation import confirmed_reformat_source
from src.domains.meetings.regeneration import launch_regenerate
from src.domains.meetings.schemas import MeetingReformatRequest, TemplateSelection
from src.domains.meetings.service import MeetingService, raise_meeting_conflict
from src.domains.meetings.template_service import MeetingTemplateService
from src.infrastructure.confirmed_commit import commit_confirmed_write
from src.infrastructure.meeting_reformat import MeetingReformatConfirmation

logger = structlog.get_logger(__name__)


async def reformat_meeting(
    service: MeetingService,
    user_id: uuid.UUID,
    meeting_id: uuid.UUID,
    request: MeetingReformatRequest,
    language: str | None,
    *,
    confirmation: MeetingReformatConfirmation | None = None,
) -> Meeting:
    """Write the minutes again with ``request.template_ref``, in place or as new minutes.

    Returns:
        The meeting being written: the same one for ``replace``, the new one for ``new``.

    Raises:
        BaseAPIException: 409 ``report_not_ready`` (not READY), 409
            ``transcript_unavailable`` (transcript purged), 409
            ``regeneration_in_progress`` (replace while a rebuild runs), 404 /
            422 from the template reference.
    """
    meeting = (
        await confirmed_reformat_source(service, user_id, meeting_id, request, confirmation)
        if confirmation is not None
        else await service.get(user_id, meeting_id)
    )
    if meeting.status is not MeetingStatus.READY:
        raise_meeting_conflict("report_not_ready", status=meeting.status.value)
    if not meeting.transcript_encrypted:
        raise_meeting_conflict("transcript_unavailable")
    resolved = await MeetingTemplateService(service.db).resolve(
        user_id, request.template_ref, language
    )
    values = {
        "template_ref": str(resolved.ref),
        "template_name": resolved.name,
        "template_selection": TemplateSelection.USER.value,
        "template_selection_reason": None,
    }
    if request.mode == "replace":
        if not await service.repo.begin_regenerate(meeting_id, values=values, commit=False):
            raise_meeting_conflict("regeneration_in_progress")
        await commit_reformat(service, meeting_id, meeting_id, request, confirmation)
        if confirmation is None:
            launch_regenerate(meeting_id)
        logger.info(
            "meeting_reformat_replace",
            meeting_id=str(meeting_id),
            template_ref=values["template_ref"],
        )
        return await service._fresh(meeting_id, user_id)

    if confirmation is not None:
        derived = await service.repo.create_from_transcript(
            meeting,
            values=values,
            rag_enabled=settings.rag_spaces_enabled,
            derived_id=confirmation.destination_id,
        )
    else:
        derived = await service.repo.create_from_transcript(
            meeting,
            values=values,
            rag_enabled=settings.rag_spaces_enabled,
        )
    await commit_reformat(service, meeting_id, derived.id, request, confirmation)
    if confirmation is None:
        launch_regenerate(derived.id)
    logger.info(
        "meeting_reformat_new",
        meeting_id=str(meeting_id),
        derived_id=str(derived.id),
        template_ref=values["template_ref"],
    )
    return derived


async def commit_reformat(
    service: MeetingService,
    source_id: uuid.UUID,
    destination_id: uuid.UUID,
    request: MeetingReformatRequest,
    confirmation: MeetingReformatConfirmation | None,
) -> None:
    await commit_confirmed_write(
        service.db,
        confirmation,
        {
            "meeting_reformat": {
                "meeting_id": str(source_id),
                "destination_id": str(destination_id),
                "mode": request.mode,
                "stage": "synthesizing",
                "processing_completed": False,
                "indexing_completed": False,
            }
        },
    )


__all__ = ["reformat_meeting"]
