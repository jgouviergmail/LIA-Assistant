"""Relations (personal CRM) configuration module (N-09).

Env-overridable caps for the read-only relationship aggregation. Defaults are
imported from ``src.core.constants`` (not from the relations domain: importing
it here would wire its router and create a config↔domain cycle — same rule as
``config/briefing.py``).
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    RELATIONS_MAX_ITEMS_DEFAULT,
    RELATIONS_MAX_ITEMS_PER_SECTION_DEFAULT,
    RELATIONS_PROVIDER_EMAIL_EXCERPT_MAX_CHARS_DEFAULT,
    RELATIONS_PROVIDER_EMAIL_WINDOW_DAYS_DEFAULT,
    RELATIONS_PROVIDER_MAX_ADDRESSES_DEFAULT,
    RELATIONS_PROVIDER_MAX_ITEMS_DEFAULT,
    RELATIONS_PROVIDER_RATE_LIMIT_CALLS_DEFAULT,
    RELATIONS_PROVIDER_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    RELATIONS_PROVIDER_WINDOW_DAYS_DEFAULT,
)


class RelationsSettings(BaseSettings):
    """Env-overridable caps for the personal-CRM aggregation."""

    relations_max_items: int = Field(
        default=RELATIONS_MAX_ITEMS_DEFAULT,
        ge=1,
        le=200,
        description="Maximum relationships listed on the CRM overview.",
    )
    relations_max_items_per_section: int = Field(
        default=RELATIONS_MAX_ITEMS_PER_SECTION_DEFAULT,
        ge=1,
        le=200,
        description=(
            "Items RETURNED per section of the 360° view. The UI shows the "
            "first few and reveals the rest on demand, and every section also "
            "carries its exact total — so this cap bounds the payload without "
            "hiding how much it left out."
        ),
    )
    relations_provider_sections_enabled: bool = Field(
        default=True,
        description=(
            "Whether the 360° view may query the active contacts/email/calendar "
            "connectors. Off keeps the CRM strictly database-local (ADR-176's "
            "original posture); the sections then simply do not exist."
        ),
    )
    relations_provider_window_days: int = Field(
        default=RELATIONS_PROVIDER_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=365,
        description=(
            "Symmetric past/future window scanned for shared events. A provider "
            "page is never exhaustive, so the window is SHOWN to the reader "
            "instead of an exact count that could not be honored."
        ),
    )
    relations_provider_email_window_days: int = Field(
        default=RELATIONS_PROVIDER_EMAIL_WINDOW_DAYS_DEFAULT,
        ge=1,
        le=3650,
        description=(
            "How far back mail is searched for one relationship. Bounds "
            "RELEVANCE and what the provider scans — not quota, which is a "
            "function of the NUMBER of calls. Shown to the reader."
        ),
    )
    relations_provider_max_addresses: int = Field(
        default=RELATIONS_PROVIDER_MAX_ADDRESSES_DEFAULT,
        ge=1,
        le=10,
        description=(
            "Addresses of one contact card used to query mail and calendar. "
            "Each address costs THREE mail searches (from, to, cc — none of the "
            "three providers can express an OR), so this is a cost bound."
        ),
    )
    relations_provider_max_items: int = Field(
        default=RELATIONS_PROVIDER_MAX_ITEMS_DEFAULT,
        ge=1,
        le=50,
        description="Items rendered per provider-backed section (mails, events).",
    )
    relations_provider_email_excerpt_max_chars: int = Field(
        default=RELATIONS_PROVIDER_EMAIL_EXCERPT_MAX_CHARS_DEFAULT,
        ge=40,
        le=1000,
        description=(
            "Length of the excerpt shown under an exchanged message. The "
            "excerpt is the preview the provider already returns with the "
            "search, so it costs no extra call; the bound is PUBLISHED to the "
            "planner so the limit it is subject to is the limit it can read "
            "(ADR-184)."
        ),
    )
    relations_provider_rate_limit_calls: int = Field(
        default=RELATIONS_PROVIDER_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1000,
        description=(
            "Per-user budget of provider-backed 360° reads per window. Each "
            "read costs several external API calls and every NAME is its own "
            "cache entry, so the cache cannot bound a caller walking names."
        ),
    )
    relations_provider_rate_limit_window_seconds: int = Field(
        default=RELATIONS_PROVIDER_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=3600,
        description="Sliding window, in seconds, for the budget above.",
    )
