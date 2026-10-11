"""Closed heartbeat selectors and canonical, non-null confirmation intent."""

from enum import Enum

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetJsonSchemaHandler,
    field_validator,
    model_validator,
)
from pydantic.json_schema import JsonSchemaValue
from pydantic_core import CoreSchema

from src.domains.agents.application.schemas import ApplicationProjection
from src.domains.heartbeat.preference_commands import HEARTBEAT_PREFERENCE_FIELDS
from src.domains.heartbeat.schemas import HeartbeatSettingsResponse, HeartbeatSettingsUpdate
from src.domains.heartbeat.source_policy import sanitize_disabled_sources
from src.domains.moments.preferences import sanitize_disabled_kinds


class HeartbeatPreferenceField(str, Enum):
    ENABLED = "heartbeat_enabled"
    START_HOUR = "heartbeat_notify_start_hour"
    END_HOUR = "heartbeat_notify_end_hour"
    DISABLED_SOURCES = "heartbeat_disabled_sources"
    DISABLED_MOMENT_KINDS = "moment_kinds_disabled"


class HeartbeatPreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[HeartbeatPreferenceField] | None = Field(
        default=None,
        min_length=1,
        max_length=len(HeartbeatPreferenceField),
        description="Distinct saved heartbeat fields; omit for all fields",
    )

    @field_validator("fields")
    @classmethod
    def distinct_fields(
        cls, values: list[HeartbeatPreferenceField] | None
    ) -> list[HeartbeatPreferenceField] | None:
        if values is not None and len(values) != len(set(values)):
            raise ValueError("Select each heartbeat field only once")
        return values


class HeartbeatPreferenceProjection(ApplicationProjection):
    platform_enabled: bool
    delivery_enabled: bool = Field(
        description="Account and platform switches are both enabled; delivery still depends on the saved hours, sources and scheduler eligibility"
    )
    source_status: HeartbeatSettingsResponse


class HeartbeatPreferencePatch(HeartbeatSettingsUpdate):
    model_config = ConfigDict(extra="forbid", strict=True)

    @field_validator("heartbeat_disabled_sources")
    @classmethod
    def canonical_sources(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else sanitize_disabled_sources(values)

    @field_validator("moment_kinds_disabled")
    @classmethod
    def canonical_kinds(cls, values: list[str] | None) -> list[str] | None:
        return None if values is None else sanitize_disabled_kinds(values)

    @model_validator(mode="after")
    def concrete_change(self) -> HeartbeatPreferencePatch:
        if not self.model_fields_set:
            raise ValueError("Name at least one heartbeat preference")
        if any(getattr(self, name) is None for name in self.model_fields_set):
            raise ValueError("A confirmed preference requires an explicit non-null value")
        return self

    @classmethod
    def __get_pydantic_json_schema__(
        cls, core_schema: CoreSchema, handler: GetJsonSchemaHandler
    ) -> JsonSchemaValue:
        schema = handler.resolve_ref_schema(
            super().__get_pydantic_json_schema__(core_schema, handler)
        )
        properties: dict[str, JsonSchemaValue] = {}
        for name, value in schema.get("properties", {}).items():
            prop = dict(value)
            alternatives = [item for item in prop.pop("anyOf", []) if item.get("type") != "null"]
            if len(alternatives) == 1:
                prop.update(alternatives[0])
            prop.pop("default", None)
            properties[name] = prop
        return {**schema, "minProperties": 1, "properties": properties}


if {field.value for field in HeartbeatPreferenceField} != HEARTBEAT_PREFERENCE_FIELDS:
    raise AssertionError("Heartbeat selectors must cover every reviewed preference field")
