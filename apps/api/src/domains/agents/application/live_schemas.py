"""Live reflex deltas preserve unrelated fields and cannot choose a provider or open a session."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from src.infrastructure.live_preferences import (
    EndOfSpeech,
    LivePreferenceSnapshot,
    LiveReflexName,
    LiveReflexValues,
    ResultDelivery,
)


class LivePreferenceField(str, Enum):
    REFLEXES = "live_reflexes"


class LivePreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LivePreferenceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    interruptions: StrictBool | None = None
    end_of_speech: EndOfSpeech | None = None
    result_delivery: ResultDelivery | None = None

    @field_validator("interruptions", "end_of_speech", "result_delivery", mode="before")
    @classmethod
    def refuse_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("Live reflexes cannot be cleared")
        return value

    @model_validator(mode="after")
    def require_change(self) -> LivePreferenceRequest:
        if not self.model_fields_set:
            raise ValueError("Choose at least one live reflex")
        return self


class LivePreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    live_reflexes: LivePreferenceSnapshot


class LivePreferenceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    preferences: LiveReflexValues
    defaulted_fields: list[LiveReflexName] = Field(default_factory=list, max_length=3)
