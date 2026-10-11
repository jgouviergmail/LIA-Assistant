"""Only an owned displayed identity may select a session; credentials are injected."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictStr

from src.core.constants import SESSION_DISPLAY_ID_LENGTH
from src.domains.auth.session_queries import ListedDeviceSession


class DeviceSessionField(str, Enum):
    SESSION_TO_REVOKE = "session_to_revoke"


class DeviceSessionRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    display_id: StrictStr = Field(pattern=rf"^[0-9a-f]{{{SESSION_DISPLAY_ID_LENGTH}}}$")


class DeviceSessionRevokePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, revalidate_instances="always")
    session_to_revoke: ListedDeviceSession
