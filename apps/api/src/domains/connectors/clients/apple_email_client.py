"""
Apple iCloud Email client (IMAP/SMTP).

Implements the same interface as GoogleGmailClient for transparent
provider switching via functional_category in ConnectorTool.

Uses imap_tools (synchronous) wrapped via asyncio.to_thread().
SMTP via smtplib for sending.

IMPORTANT: imap_tools MailMessage properties are cached_property
that access the IMAP connection. All data must be extracted WITHIN
the MailBox context manager (with block).

Created: 2026-03-10
"""

import asyncio
import json
import smtplib
import ssl
import uuid
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
from email.message import Message
from typing import Any
from uuid import UUID

import structlog
from imap_tools import AND, MailBox

from src.core.config import settings
from src.core.constants import APPLE_MAIL_MESSAGE_MAX_BYTES
from src.core.field_names import FIELD_CACHED_AT
from src.domains.connectors.clients.apple_compose import (
    forward_message,
    new_message,
    reply_message,
)
from src.domains.connectors.clients.apple_drafts_mixin import AppleDraftsMixin
from src.domains.connectors.clients.apple_imap import (
    TRASH_ROLE,
    authenticated_imap_mailbox,
    mailbox_scope,
    message_cache_key,
    move_messages,
    page_offset,
    search_folder,
    select_message_folder,
    special_folder,
)
from src.domains.connectors.clients.base_apple_client import (
    AppleAuthenticationError,
    BaseAppleClient,
)
from src.domains.connectors.clients.base_google_client import apply_max_items_limit
from src.domains.connectors.clients.email_attachments import (
    EmailAttachmentContent,
    EmailAttachmentNotFoundError,
    attachment_mime,
    ensure_within_bound,
    select_attachment,
)
from src.domains.connectors.clients.mail_folders import EXCLUDES_ITS_FOLDER
from src.domains.connectors.clients.mailbox_drafts import prepare_for_smtp
from src.domains.connectors.clients.normalizers.email_normalizer import (
    normalize_imap_message,
    parse_imap_query,
)
from src.domains.connectors.clients.normalizers.imap_handles import (
    MessageLocation,
    read_message_handle,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.cache.redis import get_redis_session
from src.infrastructure.email.outgoing import OutgoingAttachment, max_file_bytes
from src.infrastructure.email.smtp_outcome import SMTPPartialAcceptanceError

logger = structlog.get_logger(__name__)


def _located(message_id: str) -> MessageLocation:
    """Where an id says its message is; an id that cannot be one names no message.

    Raises:
        ValueError: The id lacks a valid account/folder/UIDVALIDITY binding.
    """
    location = read_message_handle(message_id)
    if location is None or location.scope_digest is None:
        raise ValueError("Message not found: list the messages again for a current identifier.")
    return location


class AppleEmailClient(AppleDraftsMixin, BaseAppleClient):
    """
    Apple iCloud Email client using IMAP/SMTP.

    Interface matches GoogleGmailClient for transparent provider switching.
    """

    connector_type = ConnectorType.APPLE_EMAIL
    OUTGOING_FILE_MAX_BYTES = max_file_bytes(APPLE_MAIL_MESSAGE_MAX_BYTES)
    # The IMAP fetch returns whole messages unless headers_only.
    SEARCH_HITS_ARE_WHOLE = True

    def __init__(
        self,
        user_id: UUID,
        credentials: AppleCredentials,
        connector_service: Any,
    ) -> None:
        super().__init__(user_id, credentials, connector_service)

    # =========================================================================
    # PUBLIC INTERFACE (matches GoogleGmailClient exactly)
    # =========================================================================

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
        fields: list[str] | None = None,
        use_cache: bool = True,
        page_token: str | None = None,
        headers_only: bool = False,
    ) -> dict[str, Any]:
        """Search emails via IMAP, cache results in Redis.

        Args:
            query: Gmail-style query, translated to IMAP criteria.
            max_results: Page size.
            fields: Unused, kept for interface parity.
            use_cache: Unused for the listing itself (IMAP has no list cache).
            page_token: The ``next_page_token`` of a previous page — an offset
                into the newest-first listing (ADR-287).
            headers_only: Fetch envelopes only (a ``metadata`` listing): no
                body, no attachment payloads, and nothing written to the
                per-message cache ``get_message`` reads later.
        """
        return await self._execute_with_retry(
            "search_emails",
            self._search_emails_impl,
            query,
            max_results,
            fields,
            use_cache,
            page_token=page_token,
            headers_only=headers_only,
        )

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get a single email by its id (its UID and its folder), checking Redis cache first."""
        return await self._execute_with_retry(
            "get_message",
            self._get_message_impl,
            message_id,
            format,
            fields,
            use_cache,
        )

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
        attachments: Sequence[OutgoingAttachment] = (),
        *,
        single_attempt: bool = True,
    ) -> dict[str, Any]:
        """Send an email via SMTP, with its files when given (ADR-321)."""
        return await self._execute_with_retry(
            "send_email",
            self._send_email_impl,
            to,
            subject,
            body,
            cc,
            bcc,
            is_html,
            attachments,
            max_retries=0,
        )

    async def reply_email(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
        to: str | None = None,
    ) -> dict[str, Any]:
        """Reply to an email."""
        return await self._execute_with_retry(
            "reply_email",
            self._reply_email_impl,
            message_id,
            body,
            reply_all,
            is_html,
            to,
            max_retries=0,
        )

    async def download_attachment(
        self,
        message_id: str,
        *,
        attachment_id: str | None = None,
        filename: str | None = None,
        max_bytes: int | None = None,
    ) -> EmailAttachmentContent:
        """Download ONE attachment of a message, by handle or by name.

        IMAP has no attachment handle: the listing publishes the part's INDEX
        (``normalize_imap_message``), and that index is the handle read here.
        The message is fetched by UID with its parts, off the event loop —
        IMAP serves the whole message, so the bound applies to the part once
        fetched, before its bytes leave the client.

        Args:
            message_id: The message's id (its UID, and its folder — ``imap_handles``).
            attachment_id: The part index the listing published; wins when given.
            filename: The name as sent, when the index is unknown.
            max_bytes: Refuse a part larger than this.

        Returns:
            The file name, the MIME type as sent and the bytes.

        Raises:
            EmailAttachmentNotFoundError: No message, or no matching part.
            EmailAttachmentAmbiguousError: The name matches several parts.
            EmailAttachmentTooLargeError: The part exceeds the bound.
        """

        location = read_message_handle(message_id)
        if location is None or location.scope_digest is None:
            raise EmailAttachmentNotFoundError(f"message {message_id!r} not found")

        def _fetch_parts() -> list[dict[str, Any]]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    if (
                        select_message_folder(
                            mailbox, location, principal=self.credentials.apple_id
                        )
                        is None
                    ):
                        raise EmailAttachmentNotFoundError(f"message {message_id!r} not found")
                    for msg in mailbox.fetch(AND(uid=location.uid), mark_seen=False):
                        return [
                            {
                                "attachmentId": str(index),
                                "filename": att.filename,
                                "mimeType": att.content_type,
                                "size": len(att.payload),
                                "payload": att.payload,
                            }
                            for index, att in enumerate(msg.attachments)
                        ]
            except EmailAttachmentNotFoundError:
                raise
            except Exception as e:
                self._check_imap_auth_error(e)
                raise
            raise EmailAttachmentNotFoundError(f"message {message_id!r} not found")

        parts = await asyncio.to_thread(_fetch_parts)
        chosen = select_attachment(parts, attachment_id=attachment_id, filename=filename)
        ensure_within_bound(chosen, max_bytes=max_bytes)
        return EmailAttachmentContent(
            filename=str(chosen.get("filename") or ""),
            mime_type=attachment_mime(chosen),
            data=bytes(chosen.get("payload") or b""),
        )

    async def forward_email(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
        include_attachments: bool = True,
    ) -> dict[str, Any]:
        """Forward an email with optional attachments."""
        return await self._execute_with_retry(
            "forward_email",
            self._forward_email_impl,
            message_id,
            to,
            body,
            cc,
            is_html,
            include_attachments,
            max_retries=0,
        )

    async def get_own_address(self) -> str | None:
        """The connected mailbox's address: the Apple ID it signs in with (ADR-314)."""
        return self.credentials.apple_id or None

    async def trash_email(self, message_id: str) -> dict[str, Any]:
        """Move an email to Trash."""
        return await self._execute_with_retry(
            "trash_email",
            self._trash_email_impl,
            message_id,
            max_retries=0,
        )

    async def list_labels(self, use_cache: bool = True) -> dict[str, str]:
        """List IMAP folders (equivalent to Gmail labels)."""
        return await self._execute_with_retry(
            "list_labels",
            self._list_labels_impl,
            use_cache,
        )

    async def resolve_label_names_in_query(self, query: str, use_cache: bool = True) -> str:
        """For Apple, label names map directly to IMAP folders. Return query unchanged."""
        return query

    # =========================================================================
    # SMTP HELPER
    # =========================================================================

    async def _smtp_send(self, recipients: list[str], msg: Message) -> None:
        """
        Send an email via SMTP STARTTLS.

        Handles connect, STARTTLS, login, sendmail, and quit in a single helper
        to avoid duplicating this pattern across send/reply/forward methods.

        Args:
            recipients: List of recipient email addresses.
            msg: Fully constructed MIME message to send.
        """

        def _do_send() -> None:
            accepted = False
            refused: dict[str, tuple[int, bytes]] = {}
            try:
                with smtplib.SMTP(
                    settings.apple_smtp_host, settings.apple_smtp_port, timeout=30
                ) as server:
                    server.starttls(context=ssl.create_default_context())
                    server.login(self.credentials.apple_id, self.credentials.app_password)
                    # Bytes: a draft read back may carry 8-bit parts, which a
                    # str would have to squeeze into ASCII.
                    refused = server.sendmail(self.credentials.apple_id, recipients, msg.as_bytes())
                    accepted = True
            except smtplib.SMTPAuthenticationError as e:
                raise AppleAuthenticationError(
                    self.connector_type,
                    "SMTP authentication failed.",
                ) from e
            except (smtplib.SMTPException, OSError) as error:
                if not accepted:
                    raise
                # Only QUIT remains after sendmail acknowledged acceptance.
                logger.warning(
                    "apple_smtp_close_failed_after_acceptance", error_type=type(error).__name__
                )
            if refused:
                raise SMTPPartialAcceptanceError(len(recipients) - len(refused), len(refused))

        await asyncio.to_thread(_do_send)

    # =========================================================================
    # IMPLEMENTATION
    # =========================================================================

    async def _search_emails_impl(
        self,
        query: str,
        max_results: int,
        fields: list[str] | None,
        use_cache: bool,
        page_token: str | None = None,
        headers_only: bool = False,
    ) -> dict[str, Any]:
        """Search emails via IMAP and cache results in Redis.

        Raises:
            ValueError: A query that excludes the folder it reads.
            MailFolderLookupError: A folder of the person's own the query
                names that no folder, or several, of the server answer to.
            MailboxFolderUnavailableError: A system location the server lacks.
        """
        import time as _time

        # Enforce the global per-request volumetry ceiling (centralized cap).
        max_results = apply_max_items_limit(max_results)
        # IMAP has no cursor: the token is an offset into the newest-first
        # listing, and a page is a slice of it.
        offset = page_offset(page_token)

        _email_start = _time.perf_counter()
        _email_status = "success"
        parsed = parse_imap_query(query)
        if parsed.excludes_its_folder:
            raise ValueError(EXCLUDES_ITS_FOLDER)
        criteria, requested_folder = parsed.criteria, parsed.folder

        def _imap_fetch() -> list[dict[str, Any]]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    # The folder is read where THIS server keeps it: a system
                    # location by its role, a folder of the person's own by its
                    # name — or refused, never the inbox in its place.
                    folder = search_folder(mailbox, requested_folder)
                    if folder != "INBOX":
                        mailbox.folder.set(folder)
                    scope = mailbox_scope(mailbox, folder, self.credentials.apple_id)

                    messages = []
                    for msg in mailbox.fetch(
                        criteria,
                        limit=slice(offset, offset + max_results) if offset else max_results,
                        mark_seen=False,
                        reverse=True,
                        headers_only=headers_only,
                    ):
                        # Extract ALL data within context manager
                        normalized = normalize_imap_message(msg, folder, scope=scope)
                        messages.append(normalized)
                    return messages
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        messages = await asyncio.to_thread(_imap_fetch)

        # Cache each message in Redis for get_message (solves N+1 IMAP).
        # The write timestamp travels WITH the payload so a later cache hit can
        # report the real age — same contract as GoogleGmailClient, which
        # calculate_cache_age_seconds relies on to expose data freshness.
        # An envelope-only listing carries no body: caching it would hand a
        # later full read a message without one.
        if messages and not headers_only:
            try:
                redis = await get_redis_session()
                ttl = settings.apple_email_message_cache_ttl
                written_at = datetime.now(UTC).isoformat()
                for msg in messages:
                    cache_key = message_cache_key(
                        self.user_id, self.credentials.apple_id, msg["id"]
                    )
                    await redis.set(
                        cache_key, json.dumps({**msg, FIELD_CACHED_AT: written_at}), ex=ttl
                    )
            except Exception as e:
                logger.debug("apple_email_cache_write_error", error=str(e))

        # Prometheus (dashboard 10 Email)
        with suppress(Exception):
            from src.infrastructure.observability.metrics_agents import (
                email_api_calls,
                email_api_latency,
                email_results_count,
            )

            email_api_calls.labels(operation="search", status=_email_status).inc()
            email_api_latency.labels(operation="search").observe(
                _time.perf_counter() - _email_start
            )
            email_results_count.labels(operation="search").observe(len(messages))

        # The normalised messages themselves, like the Gmail search (which
        # fetches metadata per hit): a ``metadata`` level reads them as they are.
        # ADR-185: IMAP gives no total for a paged fetch, and the page size is
        # not one — nothing is stated; ``next_page_token`` says whether more exist.
        return {
            "messages": messages,
            "resultSizeEstimate": None,
            "next_page_token": (
                str(offset + len(messages)) if len(messages) >= max_results else None
            ),
            "from_cache": False,
            FIELD_CACHED_AT: None,
        }

    async def _get_message_impl(
        self,
        message_id: str,
        format: str,
        fields: list[str] | None,
        use_cache: bool,
    ) -> dict[str, Any]:
        """Get a single message, checking Redis cache first."""
        location = _located(message_id)
        # Check Redis cache (populated by search_emails)
        if use_cache:
            try:
                redis = await get_redis_session()
                cache_key = message_cache_key(self.user_id, self.credentials.apple_id, message_id)
                cached = await redis.get(cache_key)
                if cached:
                    with suppress(Exception):
                        from src.infrastructure.observability.metrics_agents import (
                            email_cache_hits,
                        )

                        email_cache_hits.labels(cache_type="redis_message").inc()
                    result = json.loads(cached)
                    result["from_cache"] = True
                    # Entries written before the timestamp existed report an
                    # unknown age rather than a fabricated one.
                    result.setdefault(FIELD_CACHED_AT, None)
                    return result
                with suppress(Exception):
                    from src.infrastructure.observability.metrics_agents import (
                        email_cache_misses,
                    )

                    email_cache_misses.labels(cache_type="redis_message").inc()
            except Exception as e:
                logger.debug("apple_email_cache_read_error", error=str(e))

        # Cache miss: the message is read in the folder its id names — a UID
        # names a message within ONE folder (``imap_handles``).
        def _imap_fetch_single() -> dict[str, Any]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    folder = select_message_folder(
                        mailbox, location, principal=self.credentials.apple_id
                    )
                    if folder is not None:
                        for msg in mailbox.fetch(AND(uid=location.uid), mark_seen=False):
                            return normalize_imap_message(msg, folder, scope=location.scope_digest)
                    raise ValueError(f"Message {message_id} not found")
            except ValueError:
                raise
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        result = await asyncio.to_thread(_imap_fetch_single)

        # Cache for future requests, stamped with the write time (freshness contract)
        try:
            redis = await get_redis_session()
            cache_key = message_cache_key(self.user_id, self.credentials.apple_id, message_id)
            await redis.set(
                cache_key,
                json.dumps({**result, FIELD_CACHED_AT: datetime.now(UTC).isoformat()}),
                ex=settings.apple_email_message_cache_ttl,
            )
        except Exception as e:
            logger.warning("apple_email_cache_write_error", error_type=type(e).__name__)

        result["from_cache"] = False
        result[FIELD_CACHED_AT] = None
        return result

    async def _send_email_impl(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None,
        bcc: str | None,
        is_html: bool,
        attachments: Sequence[OutgoingAttachment] = (),
    ) -> dict[str, Any]:
        """Send email via SMTP STARTTLS; each file follows the body.

        The message is the one a draft would hold (``apple_compose``); its
        ``Bcc`` leaves the headers for the envelope.
        """
        message = new_message(
            sender=self.credentials.apple_id,
            to=to,
            subject=subject,
            body=body,
            cc=cc,
            bcc=bcc,
            is_html=is_html,
            attachments=attachments,
        )
        await self._smtp_send(prepare_for_smtp(message), message)
        message_id = str(uuid.uuid4())

        return {
            "id": message_id,
            "threadId": message_id,
            "labelIds": ["Sent"],
        }

    async def _reply_email_impl(
        self,
        message_id: str,
        body: str,
        reply_all: bool,
        is_html: bool,
        to: str | None = None,
    ) -> dict[str, Any]:
        """Reply to an email.

        Args:
            message_id: Original message ID to reply to.
            body: Reply body content.
            reply_all: Whether to reply to all recipients.
            is_html: Whether body is HTML.
            to: Override recipient address. If None, replies to original sender.

        Returns:
            Dict with sent message details (id, threadId, labelIds).
        """
        original = await self.get_message(message_id)
        # The normaliser's top-level fields (ADR-287) — the reply a draft would
        # hold, addressed like every mail client (``email_compose``).
        message = reply_message(
            original,
            body,
            sender=self.credentials.apple_id,
            reply_all=reply_all,
            is_html=is_html,
            override_to=to,
        )
        await self._smtp_send(prepare_for_smtp(message), message)
        new_id = str(uuid.uuid4())

        return {
            "id": new_id,
            "threadId": message_id,
            "labelIds": ["Sent"],
        }

    async def _forward_email_impl(
        self,
        message_id: str,
        to: str,
        body: str | None,
        cc: str | None,
        is_html: bool,
        include_attachments: bool,
    ) -> dict[str, Any]:
        """Forward an email with optional attachments — the message a draft would hold."""
        original, files = await self._original_with_files(
            message_id, include_files=include_attachments
        )
        message = forward_message(
            original,
            files,
            sender=self.credentials.apple_id,
            to=to,
            body=body,
            cc=cc,
            is_html=is_html,
        )
        await self._smtp_send(prepare_for_smtp(message), message)
        new_id = str(uuid.uuid4())

        return {
            "id": new_id,
            "threadId": message_id,
            "labelIds": ["Sent"],
            "attachments_forwarded": len(files),
            "attachment_names": [file.filename for file in files],
        }

    async def _original_with_files(
        self, message_id: str, *, include_files: bool
    ) -> tuple[dict[str, Any], list[OutgoingAttachment]]:
        """The original message, read in the folder its id names, and its files when asked.

        Raises:
            ValueError: No such message.
        """
        files: list[OutgoingAttachment] = []
        location = _located(message_id)

        def _fetch_with_attachments() -> dict[str, Any]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    folder = select_message_folder(
                        mailbox, location, principal=self.credentials.apple_id
                    )
                    if folder is not None:
                        for msg in mailbox.fetch(AND(uid=location.uid), mark_seen=False):
                            if include_files:
                                files.extend(
                                    OutgoingAttachment(att.filename, att.content_type, att.payload)
                                    for att in msg.attachments
                                )
                            return normalize_imap_message(msg, folder, scope=location.scope_digest)
                    raise ValueError(f"Message {message_id} not found")
            except ValueError:
                raise
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        return await asyncio.to_thread(_fetch_with_attachments), files

    async def _trash_email_impl(self, message_id: str) -> dict[str, Any]:
        """Move email to Trash via IMAP, from the folder its id names.

        A UID names a message within ONE folder (``imap_handles``): the id says
        which, so another folder's message of the same number is never moved.
        """
        location = _located(message_id)

        def _imap_trash() -> dict[str, Any]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    # The trash found by its role, never a typed name: iCloud
                    # names its own « Deleted Messages » (ADR-344).
                    trash = special_folder(mailbox, TRASH_ROLE)
                    folder = select_message_folder(
                        mailbox, location, principal=self.credentials.apple_id
                    )
                    if folder is None or not mailbox.uids(AND(uid=location.uid)):
                        raise ValueError(f"Message {message_id} not found")
                    uids = [location.uid]
                    # A failure after COPY may have stored a copy: never replay it.
                    # Shared cleanup targets only these UIDs, never global EXPUNGE.
                    move_messages(mailbox, uids, trash)

                    return {
                        "id": message_id,
                        "threadId": message_id,
                        "labelIds": [trash],
                    }
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        result = await asyncio.to_thread(_imap_trash)

        # Invalidate Redis cache
        try:
            redis = await get_redis_session()
            cache_key = message_cache_key(self.user_id, self.credentials.apple_id, message_id)
            await redis.delete(cache_key)
        except Exception as e:
            logger.debug("cache_invalidation_error", error=str(e))

        return result

    async def _list_labels_impl(self, use_cache: bool) -> dict[str, str]:
        """List IMAP folders as label mapping.

        Note: use_cache is accepted for interface compatibility with
        GoogleGmailClient but caching is handled at the caller level.
        """

        def _imap_list_folders() -> dict[str, str]:
            try:
                with authenticated_imap_mailbox(
                    MailBox, self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    folders = {}
                    for folder_info in mailbox.folder.list():
                        name = folder_info.name
                        folders[name] = name
                    return folders
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        return await asyncio.to_thread(_imap_list_folders)

    # =========================================================================
    # CLEANUP
    # =========================================================================

    async def close(self) -> None:
        """No persistent connections to close (each operation uses its own)."""
