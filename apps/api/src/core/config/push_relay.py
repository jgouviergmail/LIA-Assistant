"""
Wake relay settings — both sides of it.

The relay exists because one published iOS app belongs to one Apple Developer
team, and only that team's APNs key may notify it. Two deployments therefore
read this module for opposite reasons:

- the deployment that PUBLISHES the app sets ``push_relay_enabled`` and the
  APNs credentials, becoming the relay;
- a self-hosted deployment sets ``push_relay_url`` to borrow that reach for its
  own users' iPhones.

``push_relay_url`` has no default on purpose. Pointing it somewhere by default
would enrol every self-hosted deployment into telling a third party when its
users are woken — a decision that belongs to whoever runs the server, taken
knowingly, not inherited from a constant.
"""

from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.core.constants import (
    PUSH_RELAY_HANDLE_MAX_AGE_DAYS_DEFAULT,
    PUSH_RELAY_TIMEOUT_SECONDS_DEFAULT,
)


class PushRelaySettings(BaseSettings):
    """Configuration of the wake relay, as operator and as caller."""

    model_config = SettingsConfigDict(extra="ignore")

    # ========================================================================
    # Operating a relay (the deployment that publishes the app)
    # ========================================================================
    push_relay_enabled: bool = Field(
        default=False,
        description=(
            "Serve the wake relay endpoints. Exactly one deployment — the one "
            "publishing the iOS app — turns this on."
        ),
    )
    push_relay_seal_key: str | None = Field(
        default=None,
        repr=False,
        description=(
            "URL-safe base64-encoded 32-byte Fernet key sealing device handles. "
            "Deliberately NOT fernet_key: rotating this invalidates every handle "
            "in circulation without touching any other encrypted column."
        ),
    )
    apns_key_path: str | None = Field(
        default=None,
        description="Path to the APNs .p8 signing key of the team owning the app.",
    )
    apns_key_id: str | None = Field(
        default=None,
        description="Identifier of the APNs signing key (10 characters).",
    )
    apns_team_id: str | None = Field(
        default=None,
        description="Apple Developer team identifier (10 characters).",
    )
    apns_topic: str | None = Field(
        default=None,
        description="Bundle identifier of the published app, e.g. com.lia.assistant.",
    )
    apns_use_sandbox: bool = Field(
        default=False,
        description=(
            "Register devices against Apple's development gateway. A token "
            "minted for one gateway is permanently invalid on the other."
        ),
    )
    push_relay_handle_max_age_days: int = Field(
        default=PUSH_RELAY_HANDLE_MAX_AGE_DAYS_DEFAULT,
        ge=1,
        description=(
            "Handles older than this are refused. The shell re-registers on "
            "every launch, so expiry is self-healing and bounds how long a "
            "leaked handle stays usable."
        ),
    )

    # ========================================================================
    # Using a relay (any self-hosted deployment)
    # ========================================================================
    push_relay_url: str | None = Field(
        default=None,
        description=(
            "Base URL of the relay this deployment asks to wake its users' "
            "iPhones (e.g. https://lia.example.com). Unset means the published "
            "iOS shell receives no notifications from this server."
        ),
    )
    push_relay_timeout_seconds: float = Field(
        default=PUSH_RELAY_TIMEOUT_SECONDS_DEFAULT,
        gt=0,
        description="Timeout of a wake call to the relay.",
    )

    @model_validator(mode="after")
    def _relay_operator_is_fully_configured(self) -> PushRelaySettings:
        """Refuse to boot a relay that cannot actually sign anything.

        A half-configured relay accepts registrations and then fails every wake,
        which reads to a self-hoster as "the relay is down" and to a user as
        "notifications do not work" — a diagnosis nobody can make from either
        end. Failing at boot puts the error where the mistake is.

        Raises:
            ValueError: When the relay is enabled without its credentials.
        """
        if not self.push_relay_enabled:
            return self

        missing = [
            name
            for name, value in (
                ("PUSH_RELAY_SEAL_KEY", self.push_relay_seal_key),
                ("APNS_KEY_PATH", self.apns_key_path),
                ("APNS_KEY_ID", self.apns_key_id),
                ("APNS_TEAM_ID", self.apns_team_id),
                ("APNS_TOPIC", self.apns_topic),
            )
            if not value
        ]
        if missing:
            raise ValueError("PUSH_RELAY_ENABLED requires " + ", ".join(missing) + " to be set")
        return self
