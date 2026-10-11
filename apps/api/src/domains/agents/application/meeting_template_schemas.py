"""Original creation constraints, sparse edits and sealed source observations."""

from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.meeting_templates import (
    MAX_TEMPLATE_SECTIONS,
    TEMPLATE_REF_PATTERN,
    MeetingTemplateCreate,
    MeetingTemplateResponse,
    MeetingTemplateUpdate,
    TemplateCategory,
    TemplateSection,
)
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_templates import TemplateWriteFacts


def _strict_sections(value: object) -> object:
    if not isinstance(value, dict):
        return value
    sections = value.get("sections")
    if isinstance(sections, list):
        for section in sections:
            if isinstance(section, dict) and section.keys() - TemplateSection.model_fields.keys():
                raise ValueError("Unknown template section field")
    return value


class TemplateCreateInput(MeetingTemplateCreate):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="before")
    @classmethod
    def strict_sections(cls, value: object) -> object:
        return _strict_sections(value)


class TemplateEditValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    name: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    category: TemplateCategory | None = None
    sections: list[TemplateSection] | None = Field(
        default=None, min_length=1, max_length=MAX_TEMPLATE_SECTIONS
    )

    @model_validator(mode="before")
    @classmethod
    def strict_sections(cls, value: object) -> object:
        return _strict_sections(value)

    @model_validator(mode="after")
    def sparse_nonnull(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, key) is None for key in self.model_fields_set - {"description"}
        ):
            raise ValueError("Select explicit template changes; only description accepts null")
        return self


class TemplateUpdateInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(max_length=MEETINGS_TEMPLATE_REF_MAX, pattern=TEMPLATE_REF_PATTERN)
    changes: TemplateEditValues


class TemplateDeleteInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    ref: str = Field(max_length=MEETINGS_TEMPLATE_REF_MAX, pattern=TEMPLATE_REF_PATTERN)


class TemplateCreation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: TemplateCreateInput
    expected: TemplateWriteFacts
    created_id: UUID


class TemplateReplacement(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: TemplateUpdateInput
    expected: MeetingTemplateResponse
    desired: MeetingTemplateUpdate


class TemplateRemoval(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: TemplateDeleteInput
    expected: MeetingTemplateResponse
    default_template_ref: str | None


class TemplateCreatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_template_create: TemplateCreation


class TemplateUpdatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_template_update: TemplateReplacement


class TemplateDeletePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_template_delete: TemplateRemoval


class TemplateActionField(StrEnum):
    CREATE = "meeting_template_create"
    UPDATE = "meeting_template_update"
    DELETE = "meeting_template_delete"


TemplateStates = tuple[dict[str, JsonValue], dict[str, JsonValue]]


def desired_template_update(
    request: TemplateUpdateInput, before: MeetingTemplateResponse
) -> MeetingTemplateUpdate:
    values = before.model_dump(mode="json", include=set(MeetingTemplateUpdate.model_fields))
    values.update(request.changes.model_dump(mode="json", exclude_unset=True))
    return MeetingTemplateUpdate.model_validate(values)


def template_creation_states(selected: TemplateCreation) -> TemplateStates:
    return {
        "meeting_template_create": {
            "count": selected.expected.count,
            "maximum": selected.expected.maximum,
        }
    }, {
        "meeting_template_create": {
            "ref": f"user:{selected.created_id}",
            **selected.expected.values,
        }
    }


def template_replacement_states(selected: TemplateReplacement) -> TemplateStates:
    return {"meeting_template_update": selected.expected.model_dump(mode="json")}, {
        "meeting_template_update": {
            "ref": selected.request.ref,
            **selected.desired.model_dump(mode="json"),
        }
    }


def template_removal_states(selected: TemplateRemoval) -> TemplateStates:
    return {
        "meeting_template_delete": {
            "template": selected.expected.model_dump(mode="json"),
            "default_template_ref": selected.default_template_ref,
        }
    }, {
        "meeting_template_delete": {
            "ref": selected.request.ref,
            "deleted": True,
            "reset_default_template": selected.default_template_ref == selected.request.ref,
        }
    }


def canonical_template_creation(draft: ApplicationActionDraftContent) -> bool:
    selected = TemplateCreatePatch.model_validate(draft.intent).meeting_template_create
    before, after = template_creation_states(selected)
    return (
        selected.expected.current is None
        and selected.expected.count is not None
        and selected.expected.maximum is not None
        and draft.before == before
        and draft.after == after
    )


def canonical_template_replacement(draft: ApplicationActionDraftContent) -> bool:
    selected = TemplateUpdatePatch.model_validate(draft.intent).meeting_template_update
    before, after = template_replacement_states(selected)
    return (
        not selected.expected.builtin
        and selected.expected.ref == selected.request.ref
        and selected.desired == desired_template_update(selected.request, selected.expected)
        and draft.before == before
        and draft.after == after
    )


def canonical_template_removal(draft: ApplicationActionDraftContent) -> bool:
    selected = TemplateDeletePatch.model_validate(draft.intent).meeting_template_delete
    before, after = template_removal_states(selected)
    return (
        not selected.expected.builtin
        and selected.expected.ref == selected.request.ref
        and draft.before == before
        and draft.after == after
    )
