"""The mail screen's listing and reader, by the person's own hand (ADR-369).

A listing is ONE search (``mail_query``) read FRESH — the person's own view of
their mailbox, never the assistant's minute-old cache — at the published page
size, headers only. A row says who, what, when, read or starred; the page says
how many hits the provider listed but could not read (F11). The reader reads
one message whole, fresh, and marks nothing read: reading is not an act. Its
text is the provider's clean text (the quoted history left out — the HTML
reader shows the message whole); its conversation is read apart, so the message
never waits for it, as rows, the newest kept and the cut said. Where each row of a
page stands in its conversation is read apart too (ADR-379): one read through the one
door for the rows shown, answered as the marks to draw, and a mailbox that cannot tell
marks nothing — the page never depends on it. An attachment carries its handle AND its
name, because a Gmail handle expires between two reads (ADR-296). The HTML
reader is served the message's HTML up to a published ceiling, cut on a
character boundary past it, and the cut said — never read by any tool: the
model reads text, never markup (ADR-287). The images its HTML names are read
apart, so the message never waits for them, under a published budget. Who an
answer would reach is read when the person answers, never with the message:
the mailbox's own address costs a call the reader has no use for, and the rule
is the clients' own, never a second one on the screen.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import WORKBENCH_MAIL_INLINE_IMAGES_MAX
from src.core.field_names import FIELD_SKIPPED_HITS
from src.domains.connectors.active_client import ActiveClient
from src.domains.connectors.clients.email_compose import reply_recipients
from src.domains.connectors.clients.google_gmail_client import GoogleGmailClient
from src.domains.connectors.clients.mail_inline_images import InlineBudget
from src.domains.connectors.clients.protocols import EmailClientProtocol
from src.domains.connectors.mail_reply_states import reply_states_of
from src.domains.connectors.models import ConnectorType
from src.domains.workbench.availability import listing_page_size
from src.domains.workbench.calls import provider_call
from src.domains.workbench.clients import open_tool_client
from src.domains.workbench.features import WorkbenchTool
from src.domains.workbench.mail_projection import (
    addresses,
    attachments_of,
    first_address,
    has_attachments,
    is_read,
    is_starred,
    received_at,
    reply_mark,
    user_labels,
)
from src.domains.workbench.mail_query import MailSearch, compose_query
from src.domains.workbench.schemas.mail import (
    InlineImagesQuery,
    MailConversation,
    MailHtml,
    MailInlineImage,
    MailInlineImages,
    MailListing,
    MailMessage,
    MailPage,
    MailReplyMark,
    MailReplyMarks,
    MailSummary,
    ReplyMarksRequest,
)
from src.domains.workbench.schemas.mail_compose import ReplyRecipients

_TOOL = WorkbenchTool.MAIL


async def list_messages(
    user_id: UUID, zone: ZoneInfo, listing: MailListing, *, size: int | None = None
) -> MailPage:
    """One page of a folder, narrowed by the person's words and the chips.

    Args:
        user_id: The account.
        zone: The account's zone (where a day starts).
        listing: The folder, the words and the chips.
        size: What a caller showing fewer rows reads; a listing's page when left out.

    Returns:
        The page, and the next one's token.
    """
    async with open_tool_client(_TOOL, user_id) as opened:
        search = compose_query(opened.connector_type, listing, zone)
        async with provider_call(_TOOL, "list", act=False):
            raw = await _search(opened, search, listing.page_token, size or listing_page_size())
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


async def read_conversation(user_id: UUID, message_id: str) -> MailConversation:
    """What was said around a message, as rows; nothing is marked read."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_conversation", act=False):
            raw = await client.get_conversation(message_id, listing_page_size())
    return MailConversation(
        items=[_summary(hit, opened.connector_type) for hit in raw["messages"]],
        truncated=bool(raw["truncated"]),
    )


async def read_reply_marks(
    user_id: UUID, zone: ZoneInfo, request: ReplyMarksRequest
) -> MailReplyMarks:
    """Where the rows of a page stand in their conversations; nothing is marked read.

    Args:
        user_id: The account.
        zone: The account's zone.
        request: The rows shown, each named with its conversation.

    Returns:
        A mark per row something happened to; a row absent has none, or the mailbox
        could not tell (the read is fail-open, ``mail_reply_states``).
    """
    asked = [{"id": row.id, "threadId": row.thread_id} for row in request.messages]
    async with open_tool_client(_TOOL, user_id) as opened:
        async with provider_call(_TOOL, "read_reply_marks", act=False):
            states = await reply_states_of(opened.client, asked, user_timezone=zone.key)
    marks = ((row.id, reply_mark(states.get(row.id))) for row in request.messages)
    return MailReplyMarks(
        items=[MailReplyMark(id=row, status=mark) for row, mark in marks if mark is not None]
    )


async def read_reply_recipients(
    user_id: UUID, message_id: str, *, reply_all: bool
) -> ReplyRecipients:
    """Who a reply to this message would reach, by the rule the clients send with."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read", act=False):
            raw = await client.get_message(message_id, use_cache=False)
            own_address = await client.get_own_address()
    to, cc = reply_recipients(
        str(raw.get("from") or ""),
        str(raw.get("to") or ""),
        str(raw.get("cc") or ""),
        own_address=own_address,
        reply_all=reply_all,
        reply_to=str(raw.get("reply_to") or "") or None,
    )
    return ReplyRecipients(to=addresses(to), cc=addresses(cc))


async def read_message_html(user_id: UUID, message_id: str) -> MailHtml:
    """The message's HTML, cut at the published ceiling; none when it has none."""
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_html", act=False):
            html = await client.get_message_html(message_id)
    return bounded_html(html, settings.workbench_mail_html_max_bytes)


async def read_inline_images(user_id: UUID, query: InlineImagesQuery) -> MailInlineImages:
    """The images a message's HTML names, under the published budget."""
    ceiling = settings.workbench_mail_inline_max_bytes
    budget = InlineBudget(
        each_max=ceiling, total_max=ceiling, count_max=WORKBENCH_MAIL_INLINE_IMAGES_MAX
    )
    async with open_tool_client(_TOOL, user_id) as opened:
        client: EmailClientProtocol = opened.client
        async with provider_call(_TOOL, "read_inline", act=False):
            await client.read_inline_images(query.message_id, set(query.cid), budget)
    return MailInlineImages(
        images=[MailInlineImage(cid=image.cid, data_url=image.data_url) for image in budget.images],
        skipped=budget.skipped,
    )


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
    opened: ActiveClient, search: MailSearch, page_token: str | None, size: int
) -> dict[str, Any]:
    if search.label_ids:
        gmail: GoogleGmailClient = opened.client
        return await gmail.search_in_labels(
            search.label_ids,
            search.query,
            max_results=size,
            use_cache=False,
            page_token=page_token,
            headers_only=True,
        )
    client: EmailClientProtocol = opened.client
    page: dict[str, Any] = await client.search_emails(
        search.query,
        max_results=size,
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
        has_attachments=has_attachments(hit),
        label_ids=user_labels(hit, provider),
    )
