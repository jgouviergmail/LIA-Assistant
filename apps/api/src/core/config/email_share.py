"""Sending a generated file or an answer by e-mail (ADR-321).

Contains settings for:
- The deployment ceiling of the capability (``PlatformCapability.EMAIL_SHARE``)
- What LIA's own relay accepts, for a person with no connected mailbox
- The per-account rate limit of the send route
- The recipient suggestions: the largest address book read, and their rate limit

Created: 2026-09-25
Reference: docs/architecture/ADR-321-A-File-Or-An-Answer-Sent-By-E-Mail.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    EMAIL_SHARE_DIRECTORY_MAX_CONTACTS_DEFAULT,
    EMAIL_SHARE_RATE_LIMIT_CALLS_DEFAULT,
    EMAIL_SHARE_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    EMAIL_SHARE_RELAY_MAX_MESSAGE_BYTES_DEFAULT,
    EMAIL_SHARE_SUGGEST_RATE_LIMIT_CALLS_DEFAULT,
    EMAIL_SHARE_SUGGEST_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
)


class EmailShareSettings(BaseSettings):
    """Settings for sending a file or an answer from the chat or the gallery."""

    email_share_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling for sending a generated file or an answer by e-mail "
            "(PlatformCapability.EMAIL_SHARE): the routes and every « Send by e-mail » "
            "action."
        ),
    )

    email_share_relay_max_message_bytes: int = Field(
        default=EMAIL_SHARE_RELAY_MAX_MESSAGE_BYTES_DEFAULT,
        ge=1_000_000,
        le=100_000_000,
        description=(
            "The largest MESSAGE the instance's SMTP relay accepts (bytes). Used when "
            "the person has no connected mailbox; the largest file is derived from it "
            "and published. Default: Postfix's message_size_limit."
        ),
    )

    email_share_rate_limit_calls: int = Field(
        default=EMAIL_SHARE_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1_000,
        description="Sends one account may make per window.",
    )

    email_share_rate_limit_window_seconds: int = Field(
        default=EMAIL_SHARE_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=86_400,
        description="The sliding window of the per-account send limit (seconds).",
    )

    email_share_directory_max_contacts: int = Field(
        default=EMAIL_SHARE_DIRECTORY_MAX_CONTACTS_DEFAULT,
        ge=100,
        le=20_000,
        description=(
            "The largest address book the recipient suggestions read (contacts). A "
            "longer book is cut, most recently modified first where the provider "
            "allows it, and the list says contacts are left out."
        ),
    )

    email_share_suggest_rate_limit_calls: int = Field(
        default=EMAIL_SHARE_SUGGEST_RATE_LIMIT_CALLS_DEFAULT,
        ge=10,
        le=10_000,
        description="Recipient suggestion requests one account may make per window.",
    )

    email_share_suggest_rate_limit_window_seconds: int = Field(
        default=EMAIL_SHARE_SUGGEST_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=10,
        le=3_600,
        description="The sliding window of the suggestion limit (seconds).",
    )
