"""Sparse requested fields and exact observed meeting defaults remain separate."""

from enum import StrEnum
from typing import Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)

from src.core.constants import MEETINGS_TEMPLATE_REF_MAX
from src.core.meeting_templates import canonical_template_reference
from src.domains.agents.application.draft_models import ApplicationActionDraftContent
from src.infrastructure.meeting_preferences import MeetingPreferenceState, MeetingPreferenceValues


class MeetingPreferenceInput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    stt_engine: Literal["auto", "remote", "local"] | None = None
    language: str | None = Field(default=None, pattern=r"^(auto|[a-z]{2})$")
    auto_email: StrictBool | None = None
    keep_audio_hours: StrictInt | None = Field(default=None, ge=0)
    default_template_ref: str | None = Field(
        default=None,
        max_length=MEETINGS_TEMPLATE_REF_MAX,
        pattern=r"^(builtin:[a-z][a-z0-9_]{1,59}|user:[0-9a-fA-F-]{36})$",
    )

    @model_validator(mode="after")
    def exact_sparse_fields(self) -> Self:
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set - {"default_template_ref"}
        ):
            raise ValueError(
                "Choose explicit non-null meeting settings; only the default template accepts null"
            )
        return self

    @field_validator("default_template_ref")
    @classmethod
    def canonical_default_reference(cls, value: str | None) -> str | None:
        return canonical_template_reference(value)


class MeetingPreferenceObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    request: MeetingPreferenceInput
    expected: MeetingPreferenceState


class MeetingPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    meeting_preferences: MeetingPreferenceObservation


class MeetingPreferenceField(StrEnum):
    PREFERENCES = "meeting_preferences"


def requested_meeting_preferences(
    selected: MeetingPreferenceObservation,
) -> MeetingPreferenceValues:
    values = selected.expected.model_dump(mode="json", exclude={"keep_audio_hours_max"})
    values.update(selected.request.model_dump(mode="json", exclude_unset=True))
    desired = MeetingPreferenceValues.model_validate(values)
    return desired.model_copy(
        update={
            "keep_audio_hours": min(
                desired.keep_audio_hours, selected.expected.keep_audio_hours_max
            )
        }
    )


def canonical_meeting_preferences(draft: ApplicationActionDraftContent) -> bool:
    selected = MeetingPreferencePatch.model_validate(draft.intent).meeting_preferences
    return draft.before == {
        "meeting_preferences": selected.expected.model_dump(mode="json")
    } and draft.after == {
        "meeting_preferences": requested_meeting_preferences(selected).model_dump(mode="json")
    }
