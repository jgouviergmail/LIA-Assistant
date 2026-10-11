"""Seal full source revisions and resolve the same template as the original worker."""

import hashlib
import json
from contextlib import suppress
from typing import TYPE_CHECKING

from pydantic import ValidationError

from src.core.i18n import normalize_language
from src.domains.meetings.models import Meeting, MeetingStatus
from src.domains.meetings.template_resolution import template_for_regeneration
from src.domains.users.models import User
from src.infrastructure.meeting_regeneration import (
    MeetingRegenerationSnapshot,
    RegenerationTemplate,
)

if TYPE_CHECKING:
    from src.domains.meetings.service import MeetingService


async def regeneration_snapshot(
    service: MeetingService,
    meeting: Meeting,
    actor: User,
    *,
    template: RegenerationTemplate | None = None,
    allow_regeneration: bool = False,
) -> MeetingRegenerationSnapshot:
    from src.domains.meetings.service import raise_meeting_conflict

    if meeting.status is not MeetingStatus.READY:
        raise_meeting_conflict("report_not_ready", status=meeting.status.value)
    if meeting.stage is not None and not allow_regeneration:
        raise_meeting_conflict("regeneration_in_progress")
    if not meeting.transcript_encrypted:
        raise_meeting_conflict("transcript_unavailable")
    language = normalize_language(actor.language)
    definition = template
    if definition is None:
        decision = await template_for_regeneration(service.db, meeting=meeting, language=language)
        definition = RegenerationTemplate.model_validate(
            {
                "ref": str(decision.ref),
                "name": decision.name,
                "sections": [section.model_dump(mode="json") for section in decision.sections],
            }
        )
    report = None
    with suppress(ValidationError):
        report = service._report_or_none(meeting.report_current)
    turns = service.decrypt_transcript(meeting.transcript_encrypted)
    raw = json.dumps(
        {
            "meeting": {
                column.key: getattr(meeting, column.key) for column in Meeting.__table__.columns
            },
            "template": definition.model_dump(mode="json"),
            "language": language,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return MeetingRegenerationSnapshot(
        meeting_id=meeting.id,
        status=meeting.status.value,
        stage=meeting.stage.value if meeting.stage is not None else None,
        current_title=report.title if report else None,
        current_valid=meeting.report_current is None or report is not None,
        current_participants_count=len(report.participants) if report else None,
        current_sections_count=len(report.sections) if report else None,
        transcript_turns=len(turns),
        language=language,
        template_definition_at_confirmation=definition,
        source_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
    )
