"""Canonical application intent carried by the native HITL draft."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE


class ApplicationActionDraftContent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    command_id: UUID
    actor_id: UUID
    operation_id: str = Field(min_length=1, max_length=100)
    schema_version: Literal[1] = 1
    schema_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    intent: dict[str, JsonValue]
    before: dict[str, JsonValue]
    after: dict[str, JsonValue]
    title: str = Field(min_length=1, max_length=200)
    expires_at: datetime
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE

    @field_validator("expires_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Command expiry requires an explicit timezone")
        return value
