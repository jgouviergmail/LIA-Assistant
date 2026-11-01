"""The workbench: the person's own door to their connected services (ADR-369).

Contains settings for:
- The deployment ceiling of the capability (``PlatformCapability.WORKBENCH``)
- The per-account rate windows of its routes (read, write, send, bulk, download)
- The bounds it enforces and publishes (page, bulk selection, calendar window,
  download ceiling) and how long a submission remembers its outcome

Created: 2026-10-31
Reference: docs/superpowers/specs/2026-10-30-workbench-design.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    WORKBENCH_BULK_MAX_ITEMS_DEFAULT,
    WORKBENCH_BULK_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_BULK_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_CALENDAR_WINDOW_MAX_EVENTS_DEFAULT,
    WORKBENCH_DOWNLOAD_MAX_BYTES_DEFAULT,
    WORKBENCH_DOWNLOAD_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_IDEMPOTENCY_TTL_SECONDS_DEFAULT,
    WORKBENCH_MAIL_HTML_MAX_BYTES_DEFAULT,
    WORKBENCH_PAGE_SIZE_DEFAULT,
    WORKBENCH_READ_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_READ_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_SEND_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_SEND_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_WRITE_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_WRITE_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
)

_WINDOW = "The sliding window of that per-account limit (seconds)."


class WorkbenchSettings(BaseSettings):
    """Settings of the « Tools » section of the dashboard."""

    workbench_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling of the « Tools » section (PlatformCapability.WORKBENCH): "
            "the person reads and acts on their own mailbox, calendar, tasks, contacts, "
            "Drive and Hue bridge by hand, with no model in the path."
        ),
    )

    workbench_read_rate_limit_calls: int = Field(
        default=WORKBENCH_READ_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=10_000,
        description="Reads (listings, a message, an event) one account may make per window.",
    )
    workbench_read_rate_limit_window_seconds: int = Field(
        default=WORKBENCH_READ_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=86_400,
        description=_WINDOW,
    )
    workbench_write_rate_limit_calls: int = Field(
        default=WORKBENCH_WRITE_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=10_000,
        description="Single writes (an edit, a toggle, a delete) one account may make per window.",
    )
    workbench_write_rate_limit_window_seconds: int = Field(
        default=WORKBENCH_WRITE_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=86_400,
        description=_WINDOW,
    )
    workbench_send_rate_limit_calls: int = Field(
        default=WORKBENCH_SEND_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1_000,
        description="Messages sent (new, reply, forward, draft) one account may send per window.",
    )
    workbench_send_rate_limit_window_seconds: int = Field(
        default=WORKBENCH_SEND_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=86_400,
        description=_WINDOW,
    )
    workbench_bulk_rate_limit_calls: int = Field(
        default=WORKBENCH_BULK_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1_000,
        description="Acts on a selection (bulk trash, bulk read state) per window.",
    )
    workbench_bulk_rate_limit_window_seconds: int = Field(
        default=WORKBENCH_BULK_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=86_400,
        description=_WINDOW,
    )
    workbench_download_rate_limit_calls: int = Field(
        default=WORKBENCH_DOWNLOAD_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1_000,
        description="Attachments and Drive files downloaded per window.",
    )
    workbench_download_rate_limit_window_seconds: int = Field(
        default=WORKBENCH_DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=86_400,
        description=_WINDOW,
    )

    workbench_page_size: int = Field(
        default=WORKBENCH_PAGE_SIZE_DEFAULT,
        ge=1,
        le=50,
        description=(
            "Items in one page of a listing. Published as the smaller of this and "
            "API_MAX_ITEMS_PER_REQUEST, the ceiling every provider client applies."
        ),
    )
    workbench_bulk_max_items: int = Field(
        default=WORKBENCH_BULK_MAX_ITEMS_DEFAULT,
        ge=1,
        le=500,
        description="The largest selection one bulk act carries (published).",
    )
    workbench_calendar_window_max_events: int = Field(
        default=WORKBENCH_CALENDAR_WINDOW_MAX_EVENTS_DEFAULT,
        ge=1,
        le=5_000,
        description=(
            "Events read for one calendar and one visible window, provider pages "
            "drained; past it the view says the window is cut."
        ),
    )
    workbench_download_max_bytes: int = Field(
        default=WORKBENCH_DOWNLOAD_MAX_BYTES_DEFAULT,
        ge=1,
        le=200 * 1024 * 1024,
        description="The largest attachment or Drive file served (bytes, published).",
    )
    workbench_mail_html_max_bytes: int = Field(
        default=WORKBENCH_MAIL_HTML_MAX_BYTES_DEFAULT,
        ge=1024,
        le=20 * 1024 * 1024,
        description=(
            "The largest HTML body the mail reader is served (bytes); past it the "
            "HTML is cut on a character boundary and the cut is said."
        ),
    )
    workbench_idempotency_ttl_seconds: int = Field(
        default=WORKBENCH_IDEMPOTENCY_TTL_SECONDS_DEFAULT,
        ge=1,
        le=7 * 86_400,
        description=(
            "How long a submitted send or create remembers its outcome, so a second "
            "click never sends twice (seconds)."
        ),
    )
