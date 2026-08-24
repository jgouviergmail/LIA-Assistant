"""
Request and response models of the wake relay.

The response of a wake deliberately publishes ``should_forget_handle`` next to
the raw outcome. Whatever a caller must decide, it must be able to read — a
self-hosted server should not have to learn this relay's taxonomy by heart to
work out whether to delete a stored handle, and a taxonomy that grows later
must not silently change what old callers do.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.core.constants import SUPPORTED_LANGUAGES
from src.domains.push_relay.service import WakeOutcome


class DeviceRegisterRequest(BaseModel):
    """A shell presenting its APNs device token."""

    device_token: str = Field(
        ...,
        min_length=32,
        max_length=200,
        pattern=r"^[A-Fa-f0-9]+$",
        description="APNs device token, hexadecimal as Apple reports it",
    )
    sandbox: bool = Field(
        default=False,
        description=(
            "Whether the token was minted against Apple's development gateway. "
            "A token sent to the wrong gateway is permanently invalid there."
        ),
    )
    language: str = Field(
        default="fr",
        description="Language of the generic wake text, sealed into the handle",
    )

    def normalized_language(self) -> str:
        """Return the language, or the default when it is not one we speak."""
        return self.language if self.language in SUPPORTED_LANGUAGES else "fr"


class DeviceRegisterResponse(BaseModel):
    """The handle the shell hands to its own server."""

    handle: str = Field(
        ...,
        description=(
            "Opaque capability permitting exactly one thing: waking this device "
            "with a fixed, contentless notification."
        ),
    )


class WakeRequest(BaseModel):
    """A self-hosted server spending a handle."""

    handle: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="The handle the device reported to this server",
    )


class WakeResponse(BaseModel):
    """What became of one wake."""

    outcome: WakeOutcome = Field(
        ...,
        description="What happened, in the relay's own terms",
    )
    should_forget_handle: bool = Field(
        ...,
        description=(
            "Whether the caller should delete its stored handle. True only when "
            "retrying could never start working — never for a failure of ours."
        ),
    )
