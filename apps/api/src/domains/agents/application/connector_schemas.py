"""Reviewed non-secret connector fields; future fields cannot silently expose credentials."""

from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from src.domains.connectors.preferences.commands import ConnectorPreferenceSnapshot
from src.domains.connectors.preferences.registry import CONNECTOR_PREFERENCES_REGISTRY
from src.domains.connectors.preferences.schemas import PreferencesRequest


class ConnectorPreferenceField(str, Enum):
    PREFERENCES = "connector_preferences"


class ConnectorPreferencesRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    after_id: UUID | None = None
    limit: StrictInt = Field(default=25, ge=1, le=50)


class ConnectorPreferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connector_id: UUID
    preferences: PreferencesRequest = Field(json_schema_extra={"minProperties": 1})

    @model_validator(mode="after")
    def require_explicit_change(self) -> ConnectorPreferenceUpdateRequest:
        if not self.preferences.model_fields_set:
            raise ValueError("Name a preference to set or clear")
        return self


class ConnectorPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    connector_preferences: ConnectorPreferenceSnapshot


class ConnectorPreferencesProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    connectors: list[ConnectorPreferenceSnapshot]
    total: int
    next_cursor: UUID | None = None


def assert_connector_preference_coverage() -> None:
    reviewed = {
        "google_calendar": {"default_calendar_name"},
        "apple_calendar": {"default_calendar_name"},
        "microsoft_calendar": {"default_calendar_name"},
        "google_tasks": {"default_task_list_name"},
        "microsoft_tasks": {"default_task_list_name"},
    }
    if (
        set(reviewed) != set(CONNECTOR_PREFERENCES_REGISTRY)
        or any(
            set(schema.model_fields) != reviewed[kind]
            for kind, schema in CONNECTOR_PREFERENCES_REGISTRY.items()
        )
        or set(PreferencesRequest.model_fields) != set().union(*reviewed.values())
    ):
        raise AssertionError("New connector preferences require explicit non-secret review")


assert_connector_preference_coverage()
