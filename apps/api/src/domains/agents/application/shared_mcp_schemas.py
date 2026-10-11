"""Personal shared-server choices; no global server configuration or credential field."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from src.infrastructure.mcp.preferences_contract import SharedMCPPreferenceSnapshot


class SharedMCPPreferenceField(str, Enum):
    SERVER = "shared_mcp_server"


class SharedMCPPreferenceRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_key: str | None = Field(default=None, min_length=1, max_length=256)
    after_key: str | None = Field(default=None, min_length=1, max_length=256)
    limit: StrictInt = Field(default=25, ge=1, le=50)


class SharedMCPPreferenceUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    server_key: str = Field(min_length=1, max_length=256)
    enabled: StrictBool


class SharedMCPPreferencePatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    shared_mcp_server: SharedMCPPreferenceSnapshot


class SharedMCPPreferenceValue(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    server_key: str
    name: str
    enabled_for_user: StrictBool
    tools_count: int


class SharedMCPPreferenceProjection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    servers: list[SharedMCPPreferenceValue]
    total: int
    next_cursor: str | None = None
