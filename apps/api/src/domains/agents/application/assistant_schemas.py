"""Closed selectors for the non-secret assistant preference surface."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, ValidationInfo, field_validator

from src.domains.auth.preference_commands import (
    ASSISTANT_PREFERENCE_SOURCES,
    AssistantPreferencePatch,
)


class AssistantPreferenceChange(AssistantPreferencePatch):
    # Native UI labels normalize to canonical API values without schema drift.
    model_config = ConfigDict(extra="forbid", title="AssistantPreferencePatch")

    @field_validator("*", mode="before")
    @classmethod
    def normalize_displayed_choice(cls, value: object, info: ValidationInfo) -> object:
        from src.domains.agents.application.setting_choices import (
            normalize_setting_value,
        )

        return normalize_setting_value(info.field_name or "", value)


class AssistantPreferenceField(str, Enum):
    MEMORY_ENABLED = "memory_enabled"
    HEALTH_METRICS_AGENTS_ENABLED = "health_metrics_agents_enabled"
    EXECUTION_MODE = "execution_mode"
    USE_LAST_KNOWN_LOCATION = "use_last_known_location"
    VOICE_ENABLED = "voice_enabled"
    VOICE_MODE_ENABLED = "voice_mode_enabled"
    VOICE_STT_MODE = "voice_stt_mode"
    TOKENS_DISPLAY_ENABLED = "tokens_display_enabled"
    LOGIN_NOTIFICATIONS_ENABLED = "login_notifications_enabled"
    ONBOARDING_COMPLETED = "onboarding_completed"
    DEBUG_PANEL_ENABLED = "debug_panel_enabled"
    RESPONSE_DISPLAY_MODE = "response_display_mode"


class AssistantPreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fields: list[AssistantPreferenceField] | None = Field(
        default=None,
        min_length=1,
        max_length=len(AssistantPreferenceField),
        description="Distinct non-secret assistant preference fields; omit to read all",
    )

    @field_validator("fields")
    @classmethod
    def require_distinct_fields(
        cls, value: list[AssistantPreferenceField] | None
    ) -> list[AssistantPreferenceField] | None:
        if value is not None and len(value) != len(set(value)):
            raise ValueError("Select each preference only once")
        return value


if {field.value for field in AssistantPreferenceField} != set(ASSISTANT_PREFERENCE_SOURCES):
    raise AssertionError("Assistant preference reads must cover the reviewed write vocabulary")
