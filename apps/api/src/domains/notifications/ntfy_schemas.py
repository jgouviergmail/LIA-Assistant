"""Request and response shapes of the ntfy settings (ADR-391)."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.domains.notifications.ntfy import NtfyContent, NtfyServerKind
from src.infrastructure.external.ntfy_client import NtfyOutcome


class NtfySubscriptionCreate(BaseModel):
    """A new subscription: on the instance's server, or on a public server the person names."""

    server: NtfyServerKind = Field(
        description="instance: the operator's server; custom: a public https server."
    )
    server_url: str | None = Field(
        default=None, max_length=512, description="The custom server's https address."
    )
    topic: str | None = Field(
        default=None,
        max_length=64,
        description="An existing topic on a custom server; LIA draws one when absent.",
    )
    token: str | None = Field(
        default=None, max_length=64, description="The person's access token there (tk_…)."
    )
    content: NtfyContent = Field(
        default=NtfyContent.MINIMAL,
        description="minimal: a notice that LIA has something; full: the words themselves.",
    )

    @model_validator(mode="after")
    def _instance_takes_nothing_of_its_own(self) -> NtfySubscriptionCreate:
        """The instance's server, topic and token are LIA's: a request never names them."""
        if self.server is NtfyServerKind.INSTANCE and (self.server_url or self.topic or self.token):
            raise ValueError("an instance subscription names no server, topic or token")
        return self


class NtfySubscriptionUpdate(BaseModel):
    """What a person may change on a subscription."""

    content: NtfyContent | None = Field(default=None, description="What the topic receives.")
    is_active: bool | None = Field(default=None, description="Whether LIA publishes to it.")


class NtfySubscriptionView(BaseModel):
    """One subscription, as its owner sees it to subscribe from an app."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="The subscription.")
    server_kind: NtfyServerKind = Field(description="Whose server it lives on.")
    server_url: str = Field(description="The address an app subscribes to.")
    topic: str | None = Field(
        description=(
            "The topic to subscribe to — a password: shown to its owner. None when it no longer "
            "decrypts: the subscription can only be removed."
        )
    )
    has_token: bool = Field(description="Whether LIA publishes there with the person's token.")
    content: NtfyContent = Field(description="What the topic receives.")
    is_active: bool = Field(description="Whether LIA publishes to it.")
    last_sent_at: datetime | None = Field(description="Last publication the server accepted.")
    last_error_code: NtfyOutcome | None = Field(
        description="How the last publication failed, when it did."
    )
    last_error_at: datetime | None = Field(description="When it was refused.")
    created_at: datetime = Field(description="When the subscription was made.")
    subscribe_link: str | None = Field(
        description=(
            "The ntfy:// link that subscribes the app in one tap; None when the server cannot be "
            "named that way or the topic no longer decrypts."
        )
    )


class NtfyOverview(BaseModel):
    """Everything the ntfy settings draw, in one read."""

    instance_url: str | None = Field(
        description="The instance server people subscribe to; None when there is none."
    )
    custom_servers_enabled: bool = Field(description="Whether a public server may be named.")
    max_subscriptions: int = Field(description="Subscriptions one account may hold.")
    subscriptions: list[NtfySubscriptionView] = Field(description="The account's subscriptions.")


class NtfyTestResult(BaseModel):
    """How a test publication ended."""

    outcome: NtfyOutcome = Field(description="The publication's outcome.")


class NtfyQrCode(BaseModel):
    """The QR code a phone scans to subscribe the ntfy app to a topic."""

    qr_data_uri: str = Field(description="The code as a PNG data URI.")


__all__ = [
    "NtfyOverview",
    "NtfyQrCode",
    "NtfySubscriptionCreate",
    "NtfySubscriptionUpdate",
    "NtfySubscriptionView",
    "NtfyTestResult",
]
