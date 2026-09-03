"""Bulk operations on meetings (ADR-259): one answer per id, never a disguised partial success.

The list page lets the user select several meetings; the server answers each
id — deleted, or skipped with a stable reason the client can explain. A live
capture is skipped (its client owns the upload queue: discarding goes through
the banner) and so is a processing job (a worker holds its lease).
"""

from __future__ import annotations

import uuid

import structlog

from src.core.exceptions import BaseAPIException
from src.domains.meetings.models import MeetingStatus
from src.domains.meetings.repository import LIVE_STATUSES
from src.domains.meetings.schemas import BulkSkipped, MeetingBulkDeleteResponse
from src.domains.meetings.service import MeetingService

logger = structlog.get_logger(__name__)

#: Statuses a bulk delete leaves alone (the single delete refuses PROCESSING
#: outright and treats a live row as a discard the banner must drive).
_UNDELETABLE: tuple[MeetingStatus, ...] = (*LIVE_STATUSES, MeetingStatus.PROCESSING)


async def bulk_delete(
    service: MeetingService, user_id: uuid.UUID, ids: list[uuid.UUID]
) -> MeetingBulkDeleteResponse:
    """Delete the owned, terminal meetings among ``ids``; skip the rest with a reason.

    Args:
        service: The meeting service (ownership checks and the projection-first delete).
        user_id: The caller.
        ids: Requested ids; duplicates are folded, order is kept.

    Returns:
        The ids deleted and the ids skipped, each skip with its code.
    """
    deleted: list[uuid.UUID] = []
    skipped: list[BulkSkipped] = []
    for meeting_id in dict.fromkeys(ids):
        try:
            meeting = await service.get(user_id, meeting_id)
        except BaseAPIException:
            skipped.append(BulkSkipped(id=meeting_id, code="meeting_not_found"))
            continue
        if meeting.status in _UNDELETABLE:
            skipped.append(BulkSkipped(id=meeting_id, code="meeting_in_progress"))
            continue
        try:
            await service.delete(user_id, meeting_id)
        except Exception as exc:  # noqa: BLE001 — one failure must not hide the others
            logger.warning(
                "meeting_bulk_delete_item_failed",
                meeting_id=str(meeting_id),
                error=exc.__class__.__name__,
            )
            skipped.append(BulkSkipped(id=meeting_id, code="delete_failed"))
            continue
        deleted.append(meeting_id)
    logger.info(
        "meeting_bulk_delete", user_id=str(user_id), deleted=len(deleted), skipped=len(skipped)
    )
    return MeetingBulkDeleteResponse(deleted=deleted, skipped=skipped)
