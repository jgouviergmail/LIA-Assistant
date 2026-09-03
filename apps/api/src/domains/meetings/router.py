"""Meetings API (ADR-258) — recording lifecycle, minutes, template, preferences.

Mounted only when ``MEETINGS_ENABLED`` is set (see ``api/v1/routes.py``).
Static sub-paths (``/active``, ``/template``, ``/preferences``) are declared
before the ``/{meeting_id}`` family: FastAPI matches in order and a UUID path
parameter would otherwise answer 422 for them.
"""

from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.core.dependencies import get_db
from src.core.session_dependencies import get_current_active_session
from src.domains.feature_switches.guard import capability_dependencies
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.meetings.schemas import (
    MeetingActionResponse,
    MeetingDetailResponse,
    MeetingListResponse,
    MeetingPatchRequest,
    MeetingPreferencesResponse,
    MeetingPreferencesUpdate,
    MeetingSegmentAck,
    MeetingStartRequest,
    MeetingStartResponse,
    MeetingStopRequest,
    MeetingTemplateResponse,
    MeetingTemplateUpdate,
)
from src.domains.meetings.service import MeetingService, raise_meeting_too_large
from src.domains.users.models import User
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Closed by the admin capability switch as well as the deployment flag: an
# operator can pause recordings without redeploying (ADR-229 doctrine).
router = APIRouter(
    prefix="/meetings",
    tags=["Meetings"],
    dependencies=capability_dependencies(PlatformCapability.MEETINGS),
)


# ============================================================================
# Recording lifecycle
# ============================================================================


@router.post(
    "",
    response_model=MeetingStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a meeting recording",
)
async def start_meeting(
    body: MeetingStartRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingStartResponse:
    """Open a recording: engine resolved and every bound published before the first byte."""
    return await MeetingService(db).start(user, body)


@router.get(
    "/active",
    response_model=MeetingDetailResponse | None,
    summary="The live (recording or interrupted) meeting, or 204",
)
async def get_active_meeting(
    response: Response,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingDetailResponse | None:
    """What a reloaded page needs to offer Resume / Finalize / Discard."""
    service = MeetingService(db)
    meeting = await service.get_live(user.id)
    if meeting is None:
        response.status_code = status.HTTP_204_NO_CONTENT
        return None
    return service.to_detail(meeting, include_transcript=False)


@router.get("", response_model=MeetingListResponse, summary="List the user's meetings")
async def list_meetings(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingListResponse:
    """Newest first, with the EXACT total (ADR-185)."""
    service = MeetingService(db)
    items, total = await service.list_meetings(user.id, limit=limit, offset=offset)
    return MeetingListResponse(
        items=[service.to_summary(m) for m in items], total=total, limit=limit, offset=offset
    )


# ============================================================================
# Template and preferences (static paths first)
# ============================================================================


@router.get("/template", response_model=MeetingTemplateResponse, summary="Minutes template")
async def get_template(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingTemplateResponse:
    return await MeetingService(db).get_template(user.id, user.language)


@router.put("/template", response_model=MeetingTemplateResponse, summary="Replace the template")
async def put_template(
    body: MeetingTemplateUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingTemplateResponse:
    return await MeetingService(db).put_template(user.id, body)


@router.delete("/template", response_model=MeetingTemplateResponse, summary="Reset the template")
async def reset_template(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingTemplateResponse:
    return await MeetingService(db).reset_template(user.id, user.language)


@router.get("/preferences", response_model=MeetingPreferencesResponse, summary="Preferences")
async def get_preferences(
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingPreferencesResponse:
    return await MeetingService(db).get_preferences(user.id)


@router.put(
    "/preferences", response_model=MeetingPreferencesResponse, summary="Replace preferences"
)
async def put_preferences(
    body: MeetingPreferencesUpdate,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingPreferencesResponse:
    return await MeetingService(db).put_preferences(user.id, body)


# ============================================================================
# One meeting
# ============================================================================


@router.get("/{meeting_id}", response_model=MeetingDetailResponse, summary="Meeting detail")
async def get_meeting(
    meeting_id: uuid.UUID,
    include_transcript: bool = Query(default=False),
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingDetailResponse:
    service = MeetingService(db)
    meeting = await service.get(user.id, meeting_id)
    return service.to_detail(meeting, include_transcript=include_transcript)


@router.put(
    "/{meeting_id}/segments/{sequence}",
    response_model=MeetingSegmentAck,
    summary="Upload one audio segment (raw body)",
)
async def put_segment(
    meeting_id: uuid.UUID,
    sequence: int,
    request: Request,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingSegmentAck:
    """Idempotent on ``(meeting, sequence)``; the byte cap is checked before reading."""
    declared = request.headers.get("content-length")
    max_bytes = settings.meetings_segment_max_bytes
    if declared is not None and declared.isdigit() and int(declared) > max_bytes:
        raise_meeting_too_large("segment_too_large", max_bytes=max_bytes)
    body = await request.body()
    return await MeetingService(db).accept_segment(
        user.id, meeting_id, sequence=sequence, body=body
    )


@router.post(
    "/{meeting_id}/stop",
    response_model=MeetingActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Stop the recording and queue processing",
)
async def stop_meeting(
    meeting_id: uuid.UUID,
    body: MeetingStopRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingActionResponse:
    service = MeetingService(db)
    meeting = await service.stop(user.id, meeting_id, body)
    from src.domains.meetings.processing import launch_processing

    launch_processing(meeting.id)
    return MeetingActionResponse(id=meeting.id, status=meeting.status, stage=meeting.stage)


@router.post(
    "/{meeting_id}/resume", response_model=MeetingActionResponse, summary="Resume recording"
)
async def resume_meeting(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingActionResponse:
    meeting = await MeetingService(db).resume(user.id, meeting_id)
    return MeetingActionResponse(id=meeting.id, status=meeting.status, stage=meeting.stage)


@router.post(
    "/{meeting_id}/retry",
    response_model=MeetingActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Retry processing",
)
async def retry_meeting(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingActionResponse:
    meeting = await MeetingService(db).retry(user.id, meeting_id)
    from src.domains.meetings.processing import launch_processing

    launch_processing(meeting.id)
    return MeetingActionResponse(id=meeting.id, status=meeting.status, stage=meeting.stage)


@router.post(
    "/{meeting_id}/regenerate",
    response_model=MeetingActionResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Rebuild the minutes with the current template",
)
async def regenerate_minutes(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingActionResponse:
    meeting = await MeetingService(db).regenerate(user.id, meeting_id)
    from src.domains.meetings.processing import launch_regenerate

    launch_regenerate(meeting.id)
    return MeetingActionResponse(id=meeting.id, status=meeting.status, stage=meeting.stage)


@router.get("/{meeting_id}/pdf", summary="Download the minutes as PDF")
async def download_pdf(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> Response:
    pdf, filename = await MeetingService(db).pdf(user.id, meeting_id, language=user.language)
    ascii_name = filename.encode("ascii", "ignore").decode() or "minutes.pdf"
    disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": disposition},
    )


@router.post(
    "/{meeting_id}/email",
    response_model=MeetingDetailResponse,
    summary="Email the minutes to the user's own address",
)
async def email_minutes(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingDetailResponse:
    service = MeetingService(db)
    meeting = await service.email(user, meeting_id)
    return service.to_detail(meeting, include_transcript=False)


@router.patch("/{meeting_id}", response_model=MeetingDetailResponse, summary="Edit the minutes")
async def patch_meeting(
    meeting_id: uuid.UUID,
    body: MeetingPatchRequest,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingDetailResponse:
    service = MeetingService(db)
    meeting = await service.patch_report(user.id, meeting_id, body)
    from src.domains.meetings.indexing import schedule_reindex

    schedule_reindex(meeting.id)
    return service.to_detail(meeting, include_transcript=False)


@router.post(
    "/{meeting_id}/report/reset",
    response_model=MeetingDetailResponse,
    summary="Restore the generated minutes",
)
async def reset_report(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingDetailResponse:
    service = MeetingService(db)
    meeting = await service.reset_report(user.id, meeting_id)
    from src.domains.meetings.indexing import schedule_reindex

    schedule_reindex(meeting.id)
    return service.to_detail(meeting, include_transcript=False)


@router.delete(
    "/{meeting_id}/transcript",
    response_model=MeetingDetailResponse,
    summary="Delete the transcript, keep the minutes",
)
async def delete_transcript(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> MeetingDetailResponse:
    service = MeetingService(db)
    meeting = await service.delete_transcript(user.id, meeting_id)
    return service.to_detail(meeting, include_transcript=False)


@router.delete("/{meeting_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a meeting")
async def delete_meeting(
    meeting_id: uuid.UUID,
    user: User = Depends(get_current_active_session),
    db: AsyncSession = Depends(get_db),
) -> None:
    await MeetingService(db).delete(user.id, meeting_id)
