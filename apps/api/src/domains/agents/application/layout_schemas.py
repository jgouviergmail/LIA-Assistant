"""Closed layout selectors; UI value sanitization stays in the shared owner."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.infrastructure.account_preferences import LayoutPreferencePatch


class LayoutPreferenceField(str, Enum):
    BRIEFING = "briefing_preferences"
    CHAT_SHORTCUTS = "chat_shortcuts"
    SETTINGS_SHORTCUTS = "settings_shortcuts"


class LayoutPreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[LayoutPreferenceField] | None = Field(
        default=None,
        min_length=1,
        max_length=len(LayoutPreferenceField),
        description="Distinct layout fields; omit to read all",
    )

    @field_validator("fields")
    @classmethod
    def require_unique_fields(
        cls, value: list[LayoutPreferenceField] | None
    ) -> list[LayoutPreferenceField] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Select each layout once")
        return value


if {field.value for field in LayoutPreferenceField} != set(LayoutPreferencePatch.model_fields):
    raise AssertionError("New layout preferences require explicit read and invalidation coverage")
