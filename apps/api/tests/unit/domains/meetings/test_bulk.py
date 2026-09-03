"""Bulk delete (ADR-259): every id is answered — deleted, or skipped with a code."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.constants import MEETINGS_BULK_MAX
from src.core.exceptions import BaseAPIException
from src.domains.meetings.bulk import bulk_delete
from src.domains.meetings.models import MeetingStatus
from src.domains.meetings.schemas import MeetingBulkDeleteRequest

pytestmark = pytest.mark.unit


def _service(rows: dict[uuid.UUID, MeetingStatus]) -> MagicMock:
    svc = MagicMock()

    async def _get(user_id: uuid.UUID, meeting_id: uuid.UUID) -> MagicMock:
        if meeting_id not in rows:
            raise BaseAPIException(status_code=404, detail={"code": "meeting_not_found"})
        return MagicMock(id=meeting_id, status=rows[meeting_id])

    svc.get = AsyncMock(side_effect=_get)
    svc.delete = AsyncMock()
    return svc


async def test_ready_rows_are_deleted_in_flight_and_live_rows_are_skipped_with_a_code() -> None:
    ready, busy, live, interrupted, foreign = (uuid.uuid4() for _ in range(5))
    svc = _service(
        {
            ready: MeetingStatus.READY,
            busy: MeetingStatus.PROCESSING,
            live: MeetingStatus.RECORDING,
            interrupted: MeetingStatus.INTERRUPTED,
        }
    )
    result = await bulk_delete(svc, uuid.uuid4(), [ready, busy, live, interrupted, foreign])
    assert result.deleted == [ready]
    assert [(s.id, s.code) for s in result.skipped] == [
        (busy, "meeting_in_progress"),
        (live, "meeting_in_progress"),
        (interrupted, "meeting_in_progress"),
        (foreign, "meeting_not_found"),
    ]
    svc.delete.assert_awaited_once()


async def test_failed_and_stopped_rows_are_deletable() -> None:
    failed, stopped = uuid.uuid4(), uuid.uuid4()
    svc = _service({failed: MeetingStatus.FAILED, stopped: MeetingStatus.STOPPED})
    result = await bulk_delete(svc, uuid.uuid4(), [failed, stopped])
    assert result.deleted == [failed, stopped] and result.skipped == []


async def test_a_failing_delete_is_reported_not_raised_and_the_rest_proceeds() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    svc = _service({a: MeetingStatus.READY, b: MeetingStatus.READY})
    svc.delete = AsyncMock(side_effect=[OSError("disk"), None])
    result = await bulk_delete(svc, uuid.uuid4(), [a, b])
    assert result.deleted == [b]
    assert [(s.id, s.code) for s in result.skipped] == [(a, "delete_failed")]


async def test_duplicate_ids_are_folded_and_order_is_kept() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    svc = _service({a: MeetingStatus.READY, b: MeetingStatus.READY})
    result = await bulk_delete(svc, uuid.uuid4(), [b, a, b])
    assert result.deleted == [b, a]
    assert svc.delete.await_count == 2


def test_the_request_is_bounded_by_the_published_constant() -> None:
    ids = [uuid.uuid4() for _ in range(MEETINGS_BULK_MAX + 1)]
    with pytest.raises(ValueError):
        MeetingBulkDeleteRequest(ids=ids)
    with pytest.raises(ValueError):
        MeetingBulkDeleteRequest(ids=[])
    assert len(MeetingBulkDeleteRequest(ids=ids[:MEETINGS_BULK_MAX]).ids) == MEETINGS_BULK_MAX
