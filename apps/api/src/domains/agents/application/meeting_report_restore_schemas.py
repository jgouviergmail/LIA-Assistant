"""A full generated-version identity with bounded literal approval metadata."""

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, StrictBool, StrictInt, StrictStr

from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_reports import MeetingReportState


class ReportVersionSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    title: StrictStr = Field(max_length=200)
    participants_count: StrictInt = Field(ge=0)
    sections_count: StrictInt = Field(ge=0)
    headings: tuple[Annotated[StrictStr, Field(max_length=80)], ...] = Field(max_length=12)
    summary_only: Literal[True] = True


class ReportRestoreWitness(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    status: StrictStr
    stage: StrictStr | None
    location_label: StrictStr | None
    edited_at: datetime | None
    current: ReportVersionSummary | None
    current_valid: StrictBool = True
    generated: ReportVersionSummary
    matches_generated: StrictBool
    source_digest: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")


class ReportRestoreInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID


class ReportRestoreSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: ReportRestoreInput
    expected: ReportRestoreWitness


class ReportRestorePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_report_restore: ReportRestoreSelection


class ReportRestoreField(StrEnum):
    RESTORE = "meeting_report_restore"


def _version_summary(report: dict[str, JsonValue]) -> ReportVersionSummary:
    people, sections = report.get("participants"), report.get("sections")
    if not isinstance(people, list) or not isinstance(sections, list):
        raise ValueError("Original report metadata is malformed")
    headings: list[JsonValue] = []
    for section in sections[:12]:
        if not isinstance(section, dict):
            raise ValueError("Original report section is malformed")
        headings.append(section.get("label"))
    return ReportVersionSummary.model_validate(
        {
            "title": report.get("title"),
            "participants_count": len(people),
            "sections_count": len(sections),
            "headings": headings,
        }
    )


def restore_witness(state: MeetingReportState) -> ReportRestoreWitness:
    return ReportRestoreWitness(
        meeting_id=state.meeting_id,
        status=state.status,
        stage=state.stage,
        location_label=state.location_label,
        edited_at=state.edited_at,
        current=_version_summary(state.current) if state.current is not None else None,
        current_valid=state.current_valid,
        generated=_version_summary(state.generated),
        matches_generated=state.matches_generated,
        source_digest=state.source_digest,
    )


def report_restore_states(
    selected: ReportRestoreSelection,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {
        "meeting_report_restore": selected.expected.model_dump(
            mode="json", exclude={"source_digest"}
        )
    }, {
        "meeting_report_restore": {
            "meeting_id": str(selected.request.meeting_id),
            "restore_entire_generated_version": True,
            "generated": selected.expected.generated.model_dump(mode="json"),
            "location_preserved": True,
            "indexing_completed": False,
        }
    }


def canonical_report_restoration(draft: ApplicationActionDraftContent) -> bool:
    selected = ReportRestorePatch.model_validate(draft.intent).meeting_report_restore
    before, after = report_restore_states(selected)
    return (
        selected.request.meeting_id == selected.expected.meeting_id
        and draft.before == before
        and draft.after == after
    )
