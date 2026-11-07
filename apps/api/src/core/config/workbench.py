"""The workbench: the person's own door to their connected services (ADR-369).

Contains settings for:
- The deployment ceiling of the capability (``PlatformCapability.WORKBENCH``)
- The per-account rate windows of its routes (read, write, send, bulk, download)
- The bounds it enforces and publishes (page, bulk selection, calendar window,
  download ceiling) and how long a submission remembers its outcome
- What LIA does from the Tools (``PlatformCapability.TOOL_ASSISTS``, ADR-372): its
  ceiling, its rate window and the bounds of what a click reads and writes

Created: 2026-10-31
Reference: docs/superpowers/specs/2026-10-30-workbench-design.md
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings

from src.core.constants import (
    TOOL_ASSIST_CONVERSATION_MAX_MESSAGES_DEFAULT,
    TOOL_ASSIST_DOCUMENT_MAX_CHARS_DEFAULT,
    TOOL_ASSIST_INSTRUCTION_MAX_CHARS_DEFAULT,
    TOOL_ASSIST_RATE_LIMIT_CALLS_DEFAULT,
    TOOL_ASSIST_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    TOOL_ASSIST_READOUT_MAX_CHARS_DEFAULT,
    TOOL_ASSIST_TEXT_MAX_CHARS_DEFAULT,
    WORKBENCH_BULK_MAX_ITEMS_DEFAULT,
    WORKBENCH_BULK_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_BULK_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_CALENDAR_WINDOW_MAX_EVENTS_DEFAULT,
    WORKBENCH_DOWNLOAD_MAX_BYTES_DEFAULT,
    WORKBENCH_DOWNLOAD_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_DOWNLOAD_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_DRAFT_AUTOSAVE_SECONDS_DEFAULT,
    WORKBENCH_IDEMPOTENCY_TTL_SECONDS_DEFAULT,
    WORKBENCH_MAIL_HTML_MAX_BYTES_DEFAULT,
    WORKBENCH_MAIL_INLINE_MAX_BYTES_DEFAULT,
    WORKBENCH_PAGE_SIZE_DEFAULT,
    WORKBENCH_READ_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_READ_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_SEND_RATE_LIMIT_CALLS_DEFAULT,
    WORKBENCH_SEND_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
    WORKBENCH_SEND_UNDO_SECONDS_DEFAULT,
    WORKBENCH_UPLOAD_MAX_BYTES_DEFAULT,
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

    tool_assists_enabled: bool = Field(
        default=True,
        description=(
            "Deployment ceiling of what LIA can do from the Tools (PlatformCapability."
            "TOOL_ASSISTS, ADR-372): a person's click asks a model, on the instance's key, "
            "billed and filed to their account. Off on a public demonstrator."
        ),
    )
    tool_assist_rate_limit_calls: int = Field(
        default=TOOL_ASSIST_RATE_LIMIT_CALLS_DEFAULT,
        ge=1,
        le=1000,
        description="Assists one account may ask in a window: a replayed session spends euros.",
    )
    tool_assist_rate_limit_window_seconds: int = Field(
        default=TOOL_ASSIST_RATE_LIMIT_WINDOW_SECONDS_DEFAULT,
        ge=1,
        le=3600,
        description="The window of the assists' limit (seconds).",
    )
    tool_assist_text_max_chars: int = Field(
        default=TOOL_ASSIST_TEXT_MAX_CHARS_DEFAULT,
        ge=100,
        le=100_000,
        description="The longest words of the person's own a writing helper takes (characters).",
    )
    tool_assist_instruction_max_chars: int = Field(
        default=TOOL_ASSIST_INSTRUCTION_MAX_CHARS_DEFAULT,
        ge=20,
        le=4000,
        description="The longest instruction a person gives an assist (characters).",
    )
    tool_assist_document_max_chars: int = Field(
        default=TOOL_ASSIST_DOCUMENT_MAX_CHARS_DEFAULT,
        ge=1000,
        le=500_000,
        description="What a model reads of a document or a conversation; a cut is said.",
    )
    tool_assist_readout_max_chars: int = Field(
        default=TOOL_ASSIST_READOUT_MAX_CHARS_DEFAULT,
        ge=100,
        le=20_000,
        description="What a click reads aloud (characters); a cut is said.",
    )
    tool_assist_conversation_max_messages: int = Field(
        default=TOOL_ASSIST_CONVERSATION_MAX_MESSAGES_DEFAULT,
        ge=2,
        le=50,
        description="The latest messages of a conversation a summary reads; a cut is said.",
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
    workbench_mail_inline_max_bytes: int = Field(
        default=WORKBENCH_MAIL_INLINE_MAX_BYTES_DEFAULT,
        ge=1024,
        le=64 * 1024 * 1024,
        description=(
            "What one message may carry to its frame as images of its own (bytes); "
            "past it the rest are counted and said."
        ),
    )
    workbench_send_undo_seconds: int = Field(
        default=WORKBENCH_SEND_UNDO_SECONDS_DEFAULT,
        ge=0,
        le=30,
        description=(
            "How long « Send » waits on the page before a message leaves, so the person "
            "can take it back (0: it leaves at once). Published."
        ),
    )
    workbench_draft_autosave_seconds: int = Field(
        default=WORKBENCH_DRAFT_AUTOSAVE_SECONDS_DEFAULT,
        ge=0,
        le=600,
        description=(
            "How long a composer stays quiet before it saves what was written as a draft "
            "(0: only when the person asks). Published."
        ),
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
    workbench_upload_max_bytes: int = Field(
        default=WORKBENCH_UPLOAD_MAX_BYTES_DEFAULT,
        ge=1,
        le=200 * 1024 * 1024,
        description=(
            "The largest file sent to a drive (bytes, published); MAX_REQUEST_BODY_BYTES "
            "must carry it, or the boot refuses."
        ),
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
