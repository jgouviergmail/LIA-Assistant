"""ntfy settings (ADR-391): notifications through a server the person subscribes to.

Two kinds of server, read differently:

- the INSTANCE server, declared here by the operator. LIA publishes to ``ntfy_server_url`` (it
  may be private: the compose service beside the API) with ``ntfy_publish_token``, and people
  subscribe to ``ntfy_public_url`` from their phone. Empty: the instance offers none.
- a server a PERSON chooses (``ntfy.sh``, their own): public, over TLS, checked before every
  request. ``ntfy_custom_servers_enabled`` lets an operator keep their people on their server.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.constants import (
    NTFY_CUSTOM_SERVERS_ENABLED_DEFAULT,
    NTFY_ENABLED_DEFAULT,
    NTFY_MAX_SUBSCRIPTIONS_PER_USER_DEFAULT,
    NTFY_TIMEOUT_SECONDS_DEFAULT,
)


class NtfySettings(BaseSettings):
    """Configuration of the ntfy notification route."""

    model_config = SettingsConfigDict(extra="ignore")

    ntfy_enabled: bool = Field(
        default=NTFY_ENABLED_DEFAULT,
        description="Offer ntfy as a way to receive LIA's notifications (deployment ceiling).",
    )
    ntfy_server_url: str = Field(
        default="",
        description=(
            "Where LIA publishes on the instance's own ntfy server (may be private, e.g. "
            "http://ntfy:80). Empty: the instance offers no server of its own."
        ),
    )
    ntfy_public_url: str = Field(
        default="",
        description=(
            "The instance server's address as people's apps reach it. Empty: ntfy_server_url."
        ),
    )
    ntfy_publish_token: str = Field(
        default="",
        repr=False,
        description=(
            "Access token LIA publishes with on the instance server (tk_…). Empty: anonymous."
        ),
    )
    ntfy_custom_servers_enabled: bool = Field(
        default=NTFY_CUSTOM_SERVERS_ENABLED_DEFAULT,
        description="Let a person use a public ntfy server of their own choosing.",
    )
    ntfy_max_subscriptions_per_user: int = Field(
        default=NTFY_MAX_SUBSCRIPTIONS_PER_USER_DEFAULT,
        ge=1,
        le=20,
        description="ntfy subscriptions one account may hold.",
    )
    ntfy_timeout_seconds: float = Field(
        default=NTFY_TIMEOUT_SECONDS_DEFAULT,
        ge=1.0,
        le=60.0,
        description="Timeout of one publication to an ntfy server.",
    )

    @model_validator(mode="after")
    def _instance_urls_are_http(self) -> NtfySettings:
        """An instance URL is an http(s) address, or nothing."""
        for name in ("ntfy_server_url", "ntfy_public_url"):
            value = getattr(self, name).strip()
            if value and not value.startswith(("http://", "https://")):
                raise ValueError(f"{name} must start with http:// or https://")
            setattr(self, name, value.rstrip("/"))
        return self

    @property
    def ntfy_instance_public_url(self) -> str:
        """The instance server as people subscribe to it, or "" when there is none."""
        return self.ntfy_public_url or self.ntfy_server_url
