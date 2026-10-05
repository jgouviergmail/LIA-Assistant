"""Authenticated avatar contracts; credentials never enter these schemas."""

from enum import Enum
from typing import Literal
from urllib.parse import urlsplit
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictBool, field_validator, model_validator

from src.infrastructure.simli import SimliIceServer as IceServer


class AvatarSource(str, Enum):
    COMMENTS = "comments"
    LIVE = "live"


class AvatarCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AvatarSettingsRequest(AvatarCommand):
    enabled: StrictBool
    face_id: UUID | None = None


class AvatarFace(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=128)
    source: Literal["preset", "private"]
    preview_image_url: str | None = Field(default=None, max_length=2048)

    @field_validator("preview_image_url")
    @classmethod
    def trusted_preview(cls, value: str | None) -> str | None:
        if value is None:
            return None
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or parsed.hostname != "mintcdn.com"
            or parsed.username
            or parsed.password
            or parsed.port not in (None, 443)
            or not parsed.path.startswith("/simli/")
            or parsed.fragment
        ):
            raise ValueError("unsupported preview origin")
        return value


class AvatarConfig(BaseModel):
    available: bool
    enabled: bool
    connected: bool
    face_id: UUID | None
    connector_version: str | None
    session_length_seconds: int
    connect_timeout_seconds: float


class AvatarSessionRequest(AvatarCommand):
    owner_id: UUID
    source: AvatarSource
    live_session_id: UUID | None = None

    @model_validator(mode="after")
    def validate_source(self) -> AvatarSessionRequest:
        if (self.source is AvatarSource.LIVE) != (self.live_session_id is not None):
            raise ValueError("live_session_id is required only for a Live source")
        return self


class AvatarSessionResponse(BaseModel):
    server_relay: bool = True
    session_token: str = Field(min_length=1, max_length=8192, repr=False)
    lease_id: UUID
    ice_servers: list[IceServer]
    max_session_seconds: int


class AvatarLeaseRequest(AvatarCommand):
    owner_id: UUID
    lease_id: UUID | None = None


class AvatarHeartbeatRequest(AvatarSessionRequest):
    lease_id: UUID


class AvatarLeaseResponse(BaseModel):
    released: bool


class AvatarSessionStatus(BaseModel):
    owner_id: UUID
    lease_id: UUID
    phase: str
    controlled: bool
    control_phase: str | None = None


class AvatarFailureReport(AvatarLeaseRequest):
    code: str = Field(
        pattern=r"^(avatar_(start_(busy|failed|rate_limited)|connection_timeout|transport_(failed|closed)|connect_failed|heartbeat_failed|output_failed|no_remote_sound|clock_stalled|drain_timeout|output_unavailable|pcm_backlog_full|capture_failed|chat_failed|stopped|rtc_failed|media_failed|socket_failed|socket_closed|bad_answer|provider_closed|send_failed)|voice_pcm_(backlog_full|send_failed|send_stalled))$"
    )
