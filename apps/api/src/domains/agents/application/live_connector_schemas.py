"""Strict non-secret deltas reuse the Live owner's field bounds."""

from enum import Enum
from typing import Annotated

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictFloat,
    StrictInt,
    StrictStr,
    field_validator,
    model_validator,
)

from src.core.constants import (
    LIVE_DURATION_UNLIMITED,
    LIVE_IDLE_TIMEOUT_SECONDS_MAX,
    LIVE_IDLE_TIMEOUT_SECONDS_MIN,
    LIVE_SESSION_BUDGET_EUR_MAX,
    LIVE_SESSION_MAX_MINUTES_MAX,
    LIVE_SESSION_MAX_MINUTES_MIN,
)
from src.infrastructure.live_connector_preferences import (
    LiveConnectorPreferenceSnapshot,
    LiveConnectorSettingValues,
)


class LiveConnectorSettingField(str, Enum):
    SETTINGS = "live_connector_settings"


class LiveConnectorSettingsDelta(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, json_schema_extra={"minProperties": 1})
    model: Annotated[
        StrictStr | None, *LiveConnectorSettingValues.model_fields["model"].metadata
    ] = Field(
        default=None,
        json_schema_extra={"anyOf": [{"type": "string", "minLength": 1, "maxLength": 120}]},
    )
    voice: Annotated[
        StrictStr | None, *LiveConnectorSettingValues.model_fields["voice"].metadata
    ] = Field(
        default=None,
        json_schema_extra={"anyOf": [{"type": "string", "minLength": 1, "maxLength": 64}]},
    )
    thinking_level: Annotated[
        StrictStr | None,
        *LiveConnectorSettingValues.model_fields["thinking_level"].metadata,
    ] = None
    idle_timeout_seconds: StrictInt | None = Field(
        default=None,
        json_schema_extra={
            "anyOf": [
                {"type": "integer", "const": LIVE_DURATION_UNLIMITED},
                {
                    "type": "integer",
                    "minimum": LIVE_IDLE_TIMEOUT_SECONDS_MIN,
                    "maximum": LIVE_IDLE_TIMEOUT_SECONDS_MAX,
                },
            ]
        },
    )
    session_max_minutes: StrictInt | None = Field(
        default=None,
        json_schema_extra={
            "anyOf": [
                {"type": "integer", "const": LIVE_DURATION_UNLIMITED},
                {
                    "type": "integer",
                    "minimum": LIVE_SESSION_MAX_MINUTES_MIN,
                    "maximum": LIVE_SESSION_MAX_MINUTES_MAX,
                },
            ]
        },
    )
    session_budget_eur: Annotated[
        StrictFloat | StrictInt | None,
        Field(gt=0, le=LIVE_SESSION_BUDGET_EUR_MAX, allow_inf_nan=False),
    ] = Field(
        default=None,
        json_schema_extra={
            "anyOf": [
                {
                    "type": "number",
                    "exclusiveMinimum": 0,
                    "maximum": LIVE_SESSION_BUDGET_EUR_MAX,
                },
                {"type": "null"},
            ]
        },
    )

    @field_validator("model", "voice", "idle_timeout_seconds", "session_max_minutes", mode="before")
    @classmethod
    def refuse_explicit_null(cls, value: object) -> object:
        if value is None:
            raise ValueError("This Live setting cannot be cleared")
        return value

    @model_validator(mode="after")
    def validate_owner_bounds(self) -> LiveConnectorSettingsDelta:
        values = self.model_dump(exclude_unset=True)
        if not values:
            raise ValueError("Choose a Live connector setting")
        for name, low, high in (
            (
                "idle_timeout_seconds",
                LIVE_IDLE_TIMEOUT_SECONDS_MIN,
                LIVE_IDLE_TIMEOUT_SECONDS_MAX,
            ),
            (
                "session_max_minutes",
                LIVE_SESSION_MAX_MINUTES_MIN,
                LIVE_SESSION_MAX_MINUTES_MAX,
            ),
        ):
            value = getattr(self, name)
            if value is not None and value != LIVE_DURATION_UNLIMITED and not low <= value <= high:
                raise ValueError("Live duration outside the source bounds")
        return self


class LiveConnectorChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: StrictStr = Field(min_length=1, max_length=32)
    settings: LiveConnectorSettingsDelta


class LiveConnectorCommandValues(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    expected: LiveConnectorPreferenceSnapshot
    settings: LiveConnectorSettingValues


class LiveConnectorPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    live_connector_settings: LiveConnectorCommandValues


def assert_live_connector_setting_coverage() -> None:
    if set(LiveConnectorSettingsDelta.model_fields) != set(LiveConnectorSettingValues.model_fields):
        raise AssertionError("New Live connector settings require explicit non-secret review")


assert_live_connector_setting_coverage()
