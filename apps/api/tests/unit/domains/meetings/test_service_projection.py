"""What the detail projection publishes about the job (ADR-258, amended 2026-09-05).

The page must be able to say « attempt 2 of 3 » and « the worker stopped
responding » without computing either from the client's clock: the attempt
budget is a server constraint (published because it is enforced, ADR-184) and
the staleness of the lease is decided here.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from src.core.config import settings
from src.domains.meetings.models import Meeting, MeetingAudioFormat, MeetingStage, MeetingStatus
from src.domains.meetings.service import MeetingService, worker_stale

pytestmark = pytest.mark.unit

NOW = datetime.now(UTC)


def _meeting(**overrides: object) -> Meeting:
    meeting = Meeting(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        status=MeetingStatus.PROCESSING,
        stage=MeetingStage.TRANSCRIBING,
        audio_format=MeetingAudioFormat.WEBM_OPUS,
        segment_count=2,
        audio_bytes=1000,
        audio_gaps=0,
        started_at=NOW - timedelta(minutes=5),
        client_timezone="UTC",
        attempts=2,
        lease_expires_at=NOW + timedelta(minutes=10),
        stt_diarized=False,
        synthesis_tokens_in=0,
        synthesis_tokens_out=0,
        synthesis_tokens_cache=0,
    )
    for key, value in overrides.items():
        setattr(meeting, key, value)
    return meeting


@pytest.mark.parametrize(
    ("status", "lease_offset", "expected"),
    [
        (MeetingStatus.PROCESSING, timedelta(minutes=10), False),
        (MeetingStatus.PROCESSING, timedelta(seconds=-1), True),
        (MeetingStatus.PROCESSING, None, True),
        (MeetingStatus.STOPPED, None, False),
        (MeetingStatus.READY, timedelta(hours=-1), False),
    ],
)
def test_worker_stale_is_a_processing_row_whose_lease_is_gone(
    status: MeetingStatus, lease_offset: timedelta | None, expected: bool
) -> None:
    # The lease is built at TEST time: a module-level "now" drifts past a
    # +1 minute lease once the suite runs longer than a minute (it did, 16 min).
    lease = None if lease_offset is None else datetime.now(UTC) + lease_offset
    assert worker_stale(_meeting(status=status, lease_expires_at=lease)) is expected


def test_the_detail_publishes_the_attempt_budget_and_the_worker_state() -> None:
    service = MeetingService(MagicMock())
    detail = service.to_detail(
        _meeting(lease_expires_at=NOW - timedelta(minutes=1)), include_transcript=False
    )
    assert detail.attempts == 2
    assert detail.max_attempts == settings.meetings_job_max_attempts  # never hard-coded
    assert detail.worker_stale is True
