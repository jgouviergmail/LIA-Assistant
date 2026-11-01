"""The mail screen's listing and reader, by the person's own hand (ADR-369).

A listing is ONE search (``mail_query``) read FRESH — the person's own view of
their mailbox, never the assistant's minute-old cache — at the published page
size, headers only. A row says who, what, when, read or starred; the page says
how many hits the provider listed but could not read (F11). The reader reads
one message whole, fresh, and marks nothing read: reading is not an act. Its
text is the provider's clean text (the quoted history left out — the HTML
reader shows the message whole); an attachment carries its handle AND its
name, because a Gmail handle expires between two reads (ADR-296). The HTML
reader is served the message's HTML up to a published ceiling, cut on a
character boundary past it, and the cut said — never read by any tool: the
model reads text, never markup (ADR-287).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.field_names import FIELD_SKIPPED_HITS
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.mail_projection import (
    addresses,
    attachments_of,
    first_address,
    is_read,
    is_starred,
    received_at,
    user_labels,
)
from src.domains.workbench.mail_query import MailSearch, compose_query
from src.domains.workbench.schemas.mail import (
    MailHtml,
    MailListing,
    MailMessage,
    MailPage,
    MailSummary,
)

_TOOL = WorkbenchTool.MAIL


async def list_messages(user_id: UUID, zone: ZoneInfo, listing: MailListing) -> MailPage:
    """One page of a folder, narrowed by the person's words and the chips."""
    async with open_tool_client(_TOOL, user_id) as opened:
        search = compose_query(opened.connector_type, listing, zone)
        async with provider_call(_TOOL, "list", act=False):
            raw = await _search(opened, search, listing.page_token)
    return MailPage(
        items=[_summary(hit, opened.connector_type) for hit in raw.get("messages") or []],
        next_page_token=raw.get("next_page_token") or None,
        skipped=int(raw.get(FIELD_SKIPPED_HITS) or 0),
    )


async def read_message(user_id: UUID, message_id: str) -> MailMessage:
    """One message, whole; nothing is marked read."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_message(message_id, use_cache=False)
        provider = opened.connector_type
    return MailMessage(
        id=str(raw.get("id") or message_id),
        thread_id=str(raw.get("threadId") or raw.get("id") or message_id),
        sender=first_address(raw.get("from")),
        reply_to=addresses(raw.get("reply_to")),
        to=addresses(raw.get("to")),
        cc=addresses(raw.get("cc")),
        subject=str(raw.get("subject") or ""),
        received_at=received_at(raw.get("internalDate")),
        is_read=is_read(raw),
        is_starred=is_starred(raw),
        label_ids=user_labels(raw, provider),
        body=str(raw.get("body") or ""),
        attachments=attachments_of(raw, provider),
    )


async def read_message_html(user_id: UUID, message_id: str) -> MailHtml:
    """The message's HTML, cut at the published ceiling; none when it has none."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_html", act=False):
            html = await client.get_message_html(message_id)
    return bounded_html(html, settings.workbench_mail_html_max_bytes)


def bounded_html(html: str | None, max_bytes: int) -> MailHtml:
    """``html`` whole when it fits ``max_bytes`` of UTF-8, else cut on a character."""
    if html is None:
        return MailHtml(html=None, truncated=False)
    encoded = html.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return MailHtml(html=html, truncated=False)
    # The cut may fall inside a character: its partial bytes are dropped.
    return MailHtml(html=encoded[:max_bytes].decode("utf-8", errors="ignore"), truncated=True)


async def _search(
    opened: ActiveClient, search: MailSearch, page_token: str | None
) -> dict[str, Any]:
    if search.label_ids:
        gmail: GoogleGmailClient = opened.client
        return await gmail.search_in_labels(
            search.label_ids,
            search.query,
            max_results=listing_page_size(),
            use_cache=False,
            page_token=page_token,
            headers_only=True,
        )
    client: EmailClientProtocol = opened.client
    page: dict[str, Any] = await client.search_emails(
        search.query,
        max_results=listing_page_size(),
        use_cache=False,
        page_token=page_token,
        headers_only=True,
    )
    return page


def _summary(hit: Mapping[str, Any], provider: ConnectorType) -> MailSummary:
    return MailSummary(
        id=str(hit.get("id") or ""),
        thread_id=str(hit.get("threadId") or hit.get("id") or ""),
        sender=first_address(hit.get("from")),
        subject=str(hit.get("subject") or ""),
        snippet=str(hit.get("snippet") or ""),
        received_at=received_at(hit.get("internalDate")),
        is_read=is_read(hit),
        is_starred=is_starred(hit),
        label_ids=user_labels(hit, provider),
    )
