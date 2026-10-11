"""Exact row/audio checkpoints with bounded public future-job metadata."""

import hashlib
import json
from typing import TYPE_CHECKING

from src.core.i18n import normalize_language
from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.preference_commands import preference_response
from src.domains.meetings.retry_audio import seal_retry_audio
from src.domains.users.models import User
from src.infrastructure.meeting_preferences import MeetingPreferenceState
from src.infrastructure.meeting_retry import MeetingRetrySnapshot

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def retry_snapshot(
    service: MeetingService, meeting: Meeting, actor: User
) -> MeetingRetrySnapshot:
    from src.domains.meetings.service import raise_meeting_conflict

    if meeting.status not in (MeetingStatus.STOPPED, MeetingStatus.FAILED):
        raise_meeting_conflict("meeting_not_retryable", status=meeting.status.value)
    if meeting.audio_purged_at is not None:
        raise_meeting_conflict("audio_unavailable")
    audio = await seal_retry_audio(service.store, actor.id, meeting.id, meeting.audio_path)
    if not audio.files or not audio.bytes_on_disk:
        raise_meeting_conflict("audio_unavailable")
    preference = preference_response(await service.preference_repo.get_for_user(actor.id))
    report = service._report_or_none(meeting.report_current)
    values = {column.key: getattr(meeting, column.key) for column in Meeting.__table__.columns}
    raw = json.dumps(
        {
            "meeting": values,
            "audio": audio.digest,
            "preferences": preference.model_dump(mode="json"),
            "language": actor.language,
            "account_email": str(actor.email),
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return MeetingRetrySnapshot(
        meeting_id=meeting.id,
        status=meeting.status.value,
        stage=meeting.stage.value if meeting.stage else None,
        title=report.title if report else None,
        attempts=meeting.attempts,
        audio_files=audio.files,
        audio_bytes_on_disk=audio.bytes_on_disk,
        transcript_available=bool(meeting.transcript_encrypted),
        keep_audio_until=meeting.keep_audio_until,
        language=normalize_language(actor.language),
        account_email=str(actor.email),
        preferences_at_confirmation=MeetingPreferenceState.model_validate(
            preference.model_dump(mode="json")
        ),
        source_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
