"""How a Gmail reply or forward is composed, mixed into ``GoogleGmailClient`` (ADR-344).

A reply sent at once and a reply saved as a mailbox draft are the SAME message:
one composition serves both, so a draft holds exactly what sending it would
have sent. What a reply or a forward SAYS is decided once for every hand-built
composition (``email_compose``); this mixin reads the original from Gmail and
builds the MIME message.

Lives here because the client is frozen at its audited size.
"""

from __future__ import annotations

from dataclasses import dataclass
from email.message import Message
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Protocol

import structlog

from src.domains.connectors.clients.email_compose import (
    forward_subject,
    forwarded_body,
    quoted_reply,
    reply_recipients,
    reply_subject,
)
from src.domains.connectors.clients.gmail_attachments_mixin import read_gmail_attachment
from src.infrastructure.email.outgoing import OutgoingAttachment, attachment_part

logger = structlog.get_logger(__name__)


class _GmailComposeHost(Protocol):
    """What the mixin needs from its host: the reads and the header helpers."""

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]: ...

    async def get_attachment(self, message_id: str, attachment_id: str) -> bytes: ...

    async def get_own_address(self) -> str | None: ...

    @staticmethod
    def _extract_body_recursive(
        payload: dict[str, Any], max_depth: int = 10, _current_depth: int = 0
    ) -> str: ...

    @staticmethod
    def _extract_attachment_info(payload: dict[str, Any]) -> list[dict[str, Any]]: ...

    @staticmethod
    def _encode_email_header(addresses: str) -> str: ...


@dataclass(frozen=True)
class ComposedReply:
    """A reply ready to leave or to be saved, and the thread it belongs to."""

    message: Message
    thread_id: str | None


@dataclass(frozen=True)
class ComposedForward:
    """A forward ready to leave or to be saved, with every requested file attached."""

    message: Message
    listed_files: list[dict[str, Any]]


def _headers(message: dict[str, Any]) -> dict[str, str]:
    """The original's headers, by lower-case name."""
    return {
        h.get("name", "").lower(): h.get("value", "")
        for h in message.get("payload", {}).get("headers", [])
    }


class GmailComposeMixin:
    """Gmail's reply and forward composition, shared by sending and drafts."""

    async def _compose_reply(
        self: _GmailComposeHost,
        message_id: str,
        body: str,
        *,
        reply_all: bool,
        is_html: bool,
        to: str | None,
    ) -> ComposedReply:
        """Build the reply to ``message_id``: recipients, quote and threading headers.

        Args:
            message_id: The original message.
            body: The reply's own words (text or HTML).
            reply_all: Answer every recipient of the original.
            is_html: Whether ``body`` is HTML (an HTML reply quotes nothing).
            to: A recipient chosen instead of the answered ones.

        Returns:
            The message (headers encoded) and the original's thread id.
        """
        original = await self.get_message(message_id)
        headers = _headers(original)
        original_from = headers.get("from", "")
        # The person's address only matters to a reply to all (never answer
        # oneself) and to a reply to their own message (answer its recipients).
        own_needed = reply_all or "SENT" in original.get("labelIds", [])
        recipients, cc = reply_recipients(
            original_from,
            headers.get("to", ""),
            headers.get("cc", ""),
            own_address=await self.get_own_address() if own_needed else None,
            reply_all=reply_all,
            override_to=to,
            reply_to=headers.get("reply-to"),
        )
        full_body = quoted_reply(
            body,
            self._extract_body_recursive(original.get("payload", {})),
            date=headers.get("date", ""),
            sender=original_from,
            is_html=is_html,
        )
        message = MIMEText(full_body, "html" if is_html else "plain", "utf-8")
        # Encode headers with RFC 2047 for non-ASCII characters
        message["To"] = self._encode_email_header(recipients)
        message["Subject"] = reply_subject(headers.get("subject", ""))
        message["In-Reply-To"] = headers.get("message-id", "")
        message["References"] = headers.get("message-id", "")
        if cc:
            message["Cc"] = self._encode_email_header(cc)
        return ComposedReply(message=message, thread_id=original.get("threadId"))

    async def _compose_forward(
        self: _GmailComposeHost,
        message_id: str,
        to: str,
        *,
        body: str | None,
        cc: str | None,
        is_html: bool,
        include_attachments: bool,
    ) -> ComposedForward:
        """Build the forward of ``message_id``, its files carried along.

        Every requested file must be downloaded before the caller can write.
        A failure refuses the composition, so neither sending nor saving a
        draft silently loses a file or claims it was carried.

        Args:
            message_id: The original message.
            to: Recipient(s), comma-separated.
            body: Words above the forwarded message, if any.
            cc: Copies, comma-separated, if any.
            is_html: Whether ``body`` is HTML.
            include_attachments: Carry the original's files.

        Returns:
            The message (headers encoded) and the files the original listed.
        """
        original = await self.get_message(message_id)
        payload = original.get("payload", {})
        headers = _headers(original)
        original_subject = headers.get("subject", "")
        full_body = forwarded_body(
            body,
            self._extract_body_recursive(payload),
            sender=headers.get("from", ""),
            date=headers.get("date", ""),
            subject=original_subject,
            to=headers.get("to", ""),
        )
        listed = self._extract_attachment_info(payload) if include_attachments else []
        text_part = MIMEText(full_body, "html" if is_html else "plain", "utf-8")
        message: Message = text_part
        if listed:
            message = MIMEMultipart("mixed")
            message.attach(text_part)
            for info in listed:
                message.attach(await _download_part(self, message_id, payload, info))
        # Encode headers with RFC 2047 for non-ASCII characters
        message["To"] = self._encode_email_header(to)
        message["Subject"] = forward_subject(original_subject)
        if cc:
            message["Cc"] = self._encode_email_header(cc)
        return ComposedForward(message=message, listed_files=listed)


async def _download_part(
    host: _GmailComposeHost, message_id: str, payload: dict[str, Any], info: dict[str, Any]
) -> Message:
    """One listed file as an outgoing part; a failed fetch refuses composition.

    The part is the shared outgoing one (ADR-321). The original failure reaches
    the caller's error classifier before any provider write occurs.
    """
    filename = info.get("filename", "attachment")
    mime_type = info.get("mime_type", "application/octet-stream")
    data = await read_gmail_attachment(host, message_id, payload, info)
    logger.debug(
        "gmail_forward_attachment_added",
        filename=filename,
        mime_type=mime_type,
        size=info.get("size", 0),
    )
    return attachment_part(OutgoingAttachment(filename, mime_type, data))


__all__ = ["ComposedForward", "ComposedReply", "GmailComposeMixin"]
