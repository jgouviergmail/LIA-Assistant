"""Original sparse report changes with explicit nested-field and consent guards."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, JsonValue, model_validator

from src.core.meeting_reports import (
    ActionItem,
    MeetingPatchRequest,
    Participant,
    ReportSection,
    TopicItem,
    TranscriptLine,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_report_updates import ReportPatchState


def _known_rows(values: object, model: type[BaseModel]) -> None:
    if isinstance(values, list):
        for row in values:
            if isinstance(row, dict) and row.keys() - model.model_fields.keys():
                raise ValueError("Unknown original report field")


class ReportEditValues(MeetingPatchRequest):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def known_nested_fields(cls, value: object) -> object:
        if not isinstance(value, dict):
            return value
        _known_rows(value.get("participants"), Participant)
        sections = value.get("sections")
        _known_rows(sections, ReportSection)
        if isinstance(sections, list):
            for section in sections:
                if isinstance(section, dict):
                    for key, model in (
                        ("topics", TopicItem),
                        ("action_items", ActionItem),
                        ("transcript", TranscriptLine),
                    ):
                        _known_rows(section.get(key), model)
        return value

    @model_validator(mode="after")
    def explicit_nonnull(self) -> Self:
        if any(getattr(self, key) is None for key in self.model_fields_set):
            raise ValueError("Null is ignored by the original API; select an explicit value")
        return self


class ReportUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_id: UUID
    changes: ReportEditValues


class ReportUpdateSelection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: ReportUpdateInput
    expected: ReportPatchState

    @model_validator(mode="after")
    def bounded_exact_scope(self) -> Self:
        if len(self.model_dump_json().encode("utf-8")) > 64_000:
            raise ValueError("Complete report editing consent exceeds the application scope limit")
        return self


class ReportUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_report_update: ReportUpdateSelection


class ReportUpdateField(StrEnum):
    UPDATE = "meeting_report_update"


def report_update_states(
    selected: ReportUpdateSelection,
) -> tuple[dict[str, JsonValue], dict[str, JsonValue]]:
    return {
        "meeting_report_update": {
            "meeting_id": str(selected.request.meeting_id),
            "status": selected.expected.status,
            "stage": selected.expected.stage,
            "values": selected.expected.before,
        }
    }, {
        "meeting_report_update": {
            "meeting_id": str(selected.request.meeting_id),
            "values": selected.expected.after,
            "unrequested_fields_preserved": True,
            "indexing_completed": False,
        }
    }


def canonical_report_update(draft: ApplicationActionDraftContent) -> bool:
    selected = ReportUpdatePatch.model_validate(draft.intent).meeting_report_update
    before, after = report_update_states(selected)
    return (
        selected.request.meeting_id == selected.expected.meeting_id
        and draft.before == before
        and draft.after == after
    )
