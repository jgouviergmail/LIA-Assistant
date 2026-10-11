"""Sparse public comparisons bind the whole private report and selected template."""

import hashlib
import json

from pydantic import JsonValue

from src.core.meeting_reports import MeetingPatchRequest, apply_report_changes
from src.domains.meetings.models import Meeting
from src.domains.meetings.repository import LIVE_STATUSES
from src.domains.meetings.service import MeetingService, raise_meeting_conflict
from src.infrastructure.meeting_report_updates import ReportPatchState


async def report_patch_state(
    service: MeetingService, meeting: Meeting, changes: MeetingPatchRequest, language: str | None
) -> ReportPatchState:
    report = service._report_or_none(meeting.report_current)
    if report is None and any(
        value is not None for value in (changes.title, changes.participants, changes.sections)
    ):
        raise_meeting_conflict("report_not_ready", status=meeting.status.value)
    requested = changes.model_dump(mode="json", exclude_none=True, exclude_unset=True)
    before: dict[str, JsonValue] = {}
    after: dict[str, JsonValue] = {}
    current = report.model_dump(mode="json") if report else {}
    apply_report_changes(report, changes)
    for key in ("title", "participants", "sections"):
        if key in requested:
            before[key], after[key] = current.get(key), requested[key]
    if "location_label" in requested:
        before["location_label"], after["location_label"] = (
            meeting.location_label,
            requested["location_label"],
        )
    if changes.template_ref is not None:
        from src.domains.meetings.models import MeetingStatus

        if meeting.status not in (*LIVE_STATUSES, MeetingStatus.STOPPED):
            raise_meeting_conflict("template_locked", status=meeting.status.value)
        template = await service._resolved_template(meeting.user_id, changes.template_ref, language)
        assert template is not None
        before["template_ref"], before["template_name"] = (
            meeting.template_ref,
            meeting.template_name,
        )
        after["template_ref"], after["template_name"] = str(template.ref), template.name
        # The reference is stored; these are its instructions at confirmation time.
        after["template_definition_at_confirmation"] = [
            section.model_dump(mode="json") for section in template.sections
        ]
    raw = json.dumps(
        {
            "report": meeting.report_current,
            "location_label": meeting.location_label,
            "template_ref": meeting.template_ref,
            "template_name": meeting.template_name,
        },
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return ReportPatchState(
        meeting_id=meeting.id,
        status=meeting.status.value,
        stage=meeting.stage,
        edited_at=meeting.report_edited_at,
        source_digest=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        before=before,
        after=after,
    )
