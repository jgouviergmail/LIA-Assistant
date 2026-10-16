"""Mailbox drafts on Gmail, mixed into ``GoogleGmailClient`` (ADR-344).

Gmail stores a draft as a resource (``users.drafts``) holding ONE message. What
was measured on a real mailbox on 2026-10-13, and what this mixin rests on:

* an update keeps the draft id and replaces the message — a NEW message id;
* deleting a draft is permanent, while trashing its MESSAGE moves it to the
  trash, out of the listing and recoverable — so a draft is trashed that way;
* a write through the upload URI keeps the draft in its thread only when the
  multipart METADATA names the thread: a media upload left it (a reply draft
  edited that way would leave its conversation) — every write is multipart;
* an unknown draft id answers 404, whatever its shape;
* a draft may have no recipient.

The handle published as ``mailbox_draft_id`` is the draft resource id, checked
before it reaches a URL path.

Lives here because the client is frozen at its audited size.
"""

from __future__ import annotations

import asyncio
import base64
import json
import re
import uuid
from collections.abc import Sequence
from email.message import Message
from email.mime.text import MIMEText
from typing import Any, Final, Protocol
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    GMAIL_FORMAT_FULL,
    GMAIL_FORMAT_METADATA,
    GOOGLE_GMAIL_UPLOAD_BASE_URL,
)
from src.core.exceptions import ConnectorAPIError
from src.core.field_names import FIELD_MAILBOX_DRAFT_ID, FIELD_MAILBOX_DRAFT_REVISION
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.gmail_compose import ComposedForward, ComposedReply
from src.domains.connectors.clients.mailbox_drafts import (
    MailboxDraftNotFoundError,
    edit_draft_message,
    ensure_draft_revision,
    trash_each,
)

logger = structlog.get_logger(__name__)

_DRAFTS: Final = "/users/me/drafts"
_FORMAT_MINIMAL: Final = "minimal"
_FORMAT_RAW: Final = "raw"
_TRASH_LABEL: Final = "TRASH"

#: What a Gmail draft id is made of; anything else never reaches a URL path.
_DRAFT_ID: Final = re.compile(r"[A-Za-z0-9_-]+")


class _GmailDraftsHost(Protocol):
    """What the mixin needs from its host."""

    user_id: UUID

    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        max_retries: int = 3,
        extra_headers: dict[str, str] | None = None,
        *,
        content: bytes | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]: ...

    async def _compose_reply(
        self,
        message_id: str,
        body: str,
        *,
        reply_all: bool,
        is_html: bool,
        to: str | None,
    ) -> ComposedReply: ...

    async def _compose_forward(
        self,
        message_id: str,
        to: str,
        *,
        body: str | None,
        cc: str | None,
        is_html: bool,
        include_attachments: bool,
    ) -> ComposedForward: ...

    @staticmethod
    def _normalize_message_fields(
        message: dict[str, Any], format: str, *, keep_quoted: bool = False
    ) -> None: ...

    @staticmethod
    def _encode_email_header(addresses: str) -> str: ...

    async def _read_draft(self, draft_id: str, fmt: str) -> dict[str, Any]: ...

    async def _save_draft(
        self, message: Message, *, thread_id: str | None, draft_id: str | None = None
    ) -> dict[str, Any]: ...

    async def get_draft(self, draft_id: str) -> dict[str, Any]: ...


def _checked(draft_id: str) -> str:
    """The id itself, or not found when it cannot be a Gmail draft id."""
    if not _DRAFT_ID.fullmatch(draft_id):
        raise MailboxDraftNotFoundError(draft_id)
    return draft_id


def _multipart_related(metadata: dict[str, Any], raw: bytes) -> tuple[bytes, str]:
    """The upload URI's multipart body: the draft's metadata, then its message."""
    boundary = f"lia_{uuid.uuid4().hex}"
    head = (
        f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n"
        f"{json.dumps(metadata)}\r\n"
        f"--{boundary}\r\nContent-Type: message/rfc822\r\n\r\n"
    ).encode()
    return head + raw + f"\r\n--{boundary}--\r\n".encode(), (
        f"multipart/related; boundary={boundary}"
    )


def _encoded(host: _GmailDraftsHost, addresses: str | None) -> str | None:
    """Addresses validated and RFC 2047-encoded; None and "" pass unchanged."""
    return host._encode_email_header(addresses) if addresses else addresses


class GmailDraftsMixin:
    """``users.drafts`` for the person's own unsent messages."""

    async def _read_draft(self: _GmailDraftsHost, draft_id: str, fmt: str) -> dict[str, Any]:
        """One draft at ``fmt``, normalised, its quoted history kept.

        Raises:
            MailboxDraftNotFoundError: Unknown id, or the draft is in the trash.
        """
        try:
            resource = await self._make_request(
                "GET", f"{_DRAFTS}/{_checked(draft_id)}", params={"format": fmt}
            )
        except ConnectorAPIError as error:
            if error.status_code == 404:
                raise MailboxDraftNotFoundError(draft_id) from error
            raise
        message: dict[str, Any] = resource.get("message", {})
        if _TRASH_LABEL in message.get("labelIds", []):
            raise MailboxDraftNotFoundError(draft_id)
        if fmt in (GMAIL_FORMAT_FULL, GMAIL_FORMAT_METADATA):
            self._normalize_message_fields(message, fmt, keep_quoted=True)
        message[FIELD_MAILBOX_DRAFT_ID] = resource.get("id", draft_id)
        # Gmail replaces the underlying immutable message on every draft edit.
        revision = message.get("id")
        message[FIELD_MAILBOX_DRAFT_REVISION] = revision if isinstance(revision, str) else ""
        return message

    async def _save_draft(
        self: _GmailDraftsHost,
        message: Message,
        *,
        thread_id: str | None,
        draft_id: str | None = None,
    ) -> dict[str, Any]:
        """Create (or replace) a draft through the upload URI, then read it back.

        A write is attempted once: a retried creation could leave two drafts;
        a replacement after a lost acknowledgement could overwrite a later
        mailbox edit without checking its revision again.
        """
        metadata: dict[str, Any] = {"message": {"threadId": thread_id} if thread_id else {}}
        if draft_id:
            metadata["id"] = draft_id
        content, content_type = _multipart_related(metadata, message.as_bytes())
        saved = await self._make_request(
            "PUT" if draft_id else "POST",
            f"{_DRAFTS}/{draft_id}" if draft_id else _DRAFTS,
            params={"uploadType": "multipart"},
            max_retries=1,
            extra_headers={"Content-Type": content_type},
            content=content,
            base_url=GOOGLE_GMAIL_UPLOAD_BASE_URL,
        )
        logger.info(
            "gmail_mailbox_draft_saved",
            user_id=str(self.user_id),
            created=draft_id is None,
            threaded=bool(thread_id),
        )
        return await self.get_draft(str(saved.get("id", draft_id or "")))

    async def list_drafts(
        self: _GmailDraftsHost,
        query: str = "",
        max_results: int = 10,
        page_token: str | None = None,
        headers_only: bool = True,
    ) -> dict[str, Any]:
        """The newest drafts first, as Gmail orders them (``users.drafts.list``).

        Args:
            query: Gmail search syntax, matched against the drafts only.
            max_results: Page size (bounded by the API limit).
            page_token: The ``next_page_token`` of a previous page.
            headers_only: Read each draft at ``metadata`` rather than ``full``.

        Returns:
            ``messages`` (each with its ``mailbox_draft_id``), Gmail's
            ``resultSizeEstimate`` and ``next_page_token``. A draft deleted
            between the listing and its read is left out.
        """
        params: dict[str, Any] = {"maxResults": apply_max_items_limit(max_results)}
        if query:
            params = {"q": query, **params}
        if page_token:
            params["pageToken"] = page_token
        listing = await self._make_request("GET", _DRAFTS, params=params)
        fmt = GMAIL_FORMAT_METADATA if headers_only else GMAIL_FORMAT_FULL
        semaphore = asyncio.Semaphore(settings.emails_search_fetch_concurrency)

        async def read(draft_id: str) -> dict[str, Any] | None:
            async with semaphore:
                try:
                    return await self._read_draft(draft_id, fmt)
                except MailboxDraftNotFoundError:
                    return None

        drafts = await asyncio.gather(*(read(str(d.get("id"))) for d in listing.get("drafts", [])))
        return {
            "messages": [draft for draft in drafts if draft is not None],
            "resultSizeEstimate": listing.get("resultSizeEstimate"),
            "next_page_token": listing.get("nextPageToken"),
        }

    async def get_draft(self: _GmailDraftsHost, draft_id: str) -> dict[str, Any]:
        """One draft, whole, its quoted history kept.

        Raises:
            MailboxDraftNotFoundError: Unknown id, or the draft is in the trash.
        """
        return await self._read_draft(draft_id, GMAIL_FORMAT_FULL)

    async def create_draft(
        self: _GmailDraftsHost,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save a new draft; an empty ``to`` leaves the recipient unset.

        Raises:
            ValueError: An address that is not one.
        """
        message = MIMEText(body, "html" if is_html else "plain", "utf-8")
        for header, value in (("To", to), ("Cc", cc), ("Bcc", bcc)):
            if value:
                message[header] = self._encode_email_header(value)
        message["Subject"] = subject
        return await self._save_draft(message, thread_id=None)

    async def create_reply_draft(
        self: _GmailDraftsHost,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save the reply to ``message_id`` as a draft, in its thread.

        It is the message ``reply_email`` would send: same recipients, same
        quote, same threading headers.
        """
        composed = await self._compose_reply(
            message_id, body, reply_all=reply_all, is_html=is_html, to=None
        )
        return await self._save_draft(composed.message, thread_id=composed.thread_id)

    async def create_forward_draft(
        self: _GmailDraftsHost,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """Save the forward of ``message_id`` as a draft, with its files.

        It is the message ``forward_email`` would send.
        """
        composed = await self._compose_forward(
            message_id, to, body=body, cc=cc, is_html=is_html, include_attachments=True
        )
        return await self._save_draft(composed.message, thread_id=None)

    async def update_draft(
        self: _GmailDraftsHost,
        draft_id: str,
        *,
        to: str | None = None,
        cc: str | None = None,
        bcc: str | None = None,
        subject: str | None = None,
        body: str | None = None,
        expected_revision: str | None = None,
    ) -> dict[str, Any]:
        """Change the fields given (None keeps one, "" clears it), keep the rest.

        The RAW message is edited, so the files and the threading headers stay,
        and the draft stays in its thread.

        Raises:
            MailboxDraftNotFoundError: Unknown id, or the draft is in the trash.
            ValueError: An address that is not one (nothing is saved).
        """
        current = await self._read_draft(draft_id, _FORMAT_RAW)
        ensure_draft_revision(current, expected_revision)
        edited = edit_draft_message(
            base64.urlsafe_b64decode(current["raw"] + "=" * (-len(current["raw"]) % 4)),
            to=_encoded(self, to),
            cc=_encoded(self, cc),
            bcc=_encoded(self, bcc),
            subject=subject,
            body=body,
        )
        return await self._save_draft(
            edited, thread_id=current.get("threadId"), draft_id=current[FIELD_MAILBOX_DRAFT_ID]
        )

    async def trash_drafts(self: _GmailDraftsHost, draft_ids: Sequence[str]) -> dict[str, Any]:
        """Move drafts to the trash through their message, where they stay recoverable.

        Returns:
            ``{"trashed": [ids], "failed": [{"mailbox_draft_id", "status"}]}``.
        """

        async def trash_one(draft_id: str) -> None:
            draft = await self._read_draft(draft_id, _FORMAT_MINIMAL)
            await self._make_request("POST", f"/users/me/messages/{draft['id']}/trash")

        result = await trash_each(draft_ids, trash_one)
        logger.info(
            "gmail_mailbox_drafts_trashed",
            user_id=str(self.user_id),
            trashed=len(result["trashed"]),
            failed=len(result["failed"]),
        )
        return result

    async def send_draft(self: _GmailDraftsHost, draft_id: str) -> dict[str, Any]:
        """Send a draft as it is stored — one attempt, never retried.

        The caller reads the draft first: Gmail would send a draft from the
        trash, and this method does not look.

        Raises:
            MailboxDraftNotFoundError: Unknown id.
        """
        try:
            sent = await self._make_request(
                "POST", f"{_DRAFTS}/send", json_data={"id": _checked(draft_id)}, max_retries=1
            )
        except ConnectorAPIError as error:
            if error.status_code == 404:
                raise MailboxDraftNotFoundError(draft_id) from error
            raise
        logger.info("gmail_mailbox_draft_sent", user_id=str(self.user_id))
        return {
            "id": sent.get("id"),
            "threadId": sent.get("threadId"),
            FIELD_MAILBOX_DRAFT_ID: draft_id,
            # Gmail sends and files in one act: the draft never stays behind.
            "draft_kept": False,
        }


__all__ = ["GmailDraftsMixin"]
