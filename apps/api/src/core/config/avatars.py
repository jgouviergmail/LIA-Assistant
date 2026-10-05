"""Personal speaking avatars. No instance credential or platform billing."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings

from src.core.constants import (
    AVATAR_CONNECT_TIMEOUT_SECONDS_DEFAULT,
    AVATAR_HTTP_TIMEOUT_SECONDS_DEFAULT,
    AVATAR_MINTS_PER_HOUR_DEFAULT,
    AVATAR_SESSION_LENGTH_SECONDS_DEFAULT,
)


class AvatarSettings(BaseSettings):
    """Deployment ceiling and finite provider bounds, independent of voice modes."""

    avatar_enabled: bool = Field(default=False)
    avatar_mints_per_hour: int = Field(default=AVATAR_MINTS_PER_HOUR_DEFAULT, ge=1, le=60)
    avatar_session_length_seconds: int = Field(
        default=AVATAR_SESSION_LENGTH_SECONDS_DEFAULT, ge=30, le=3600
    )
    avatar_idle_seconds: int = Field(default=AVATAR_SESSION_LENGTH_SECONDS_DEFAULT, ge=30, le=3600)
    avatar_http_timeout_seconds: float = Field(
        default=AVATAR_HTTP_TIMEOUT_SECONDS_DEFAULT, ge=1, le=30
    )
    avatar_connect_timeout_seconds: float = Field(
        default=AVATAR_CONNECT_TIMEOUT_SECONDS_DEFAULT, ge=5, le=30
    )

    @model_validator(mode="after")
    def validate_avatar_bounds(self) -> AvatarSettings:
        if self.avatar_idle_seconds > self.avatar_session_length_seconds:
            raise ValueError("avatar_idle_seconds exceeds avatar_session_length_seconds")
        return self
