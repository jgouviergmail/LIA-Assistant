"""The original report schema validates all visible content; digests bind raw revisions."""

import hashlib
import json

from pydantic import ValidationError

from src.domains.meetings.models import Meeting
from src.domains.meetings.schemas import MeetingReport
from src.infrastructure.meeting_reports import MeetingReportState


def report_state(meeting: Meeting) -> MeetingReportState:
    original = json.dumps(
        {"current": meeting.report_current, "generated": meeting.report_generated},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    generated = MeetingReport.model_validate(meeting.report_generated)
    current_valid = True
    try:
        current = (
            MeetingReport.model_validate(meeting.report_current)
            if meeting.report_current is not None
            else None
        )
    except ValidationError:
        # Restoration can repair the current version; the generated source must be valid.
        current, current_valid = None, False
    return MeetingReportState(
        meeting_id=meeting.id,
        status=meeting.status.value,
        stage=meeting.stage,
        location_label=meeting.location_label,
        edited_at=meeting.report_edited_at,
        current=current.model_dump(mode="json") if current else None,
        current_valid=current_valid,
        generated=generated.model_dump(mode="json"),
        matches_generated=meeting.report_current == meeting.report_generated,
        source_digest=hashlib.sha256(original.encode("utf-8")).hexdigest(),
    )
