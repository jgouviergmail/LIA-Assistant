"""Transcript witnesses contain a ciphertext digest, never source words or audio."""

import hashlib

from src.domains.meetings.models import Meeting
from src.infrastructure.meeting_transcripts import MeetingTranscriptState


def transcript_state(meeting: Meeting) -> MeetingTranscriptState:
    report = meeting.report_current or {}
    return MeetingTranscriptState(
        meeting_id=meeting.id,
        title=report.get("title"),
        status=meeting.status.value,
        stage=meeting.stage,
        has_transcript=meeting.transcript_encrypted is not None,
        deleted_at=meeting.transcript_deleted_at,
        transcript_digest=hashlib.sha256(
            (meeting.transcript_encrypted or "").encode("utf-8")
        ).hexdigest(),
    )
