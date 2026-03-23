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
import uuid
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from uuid import UUID

import structlog
from imap_tools import AND, MailBox

from src.core.config import settings
from src.domains.connectors.clients.base_apple_client import (
    AppleAuthenticationError,
    BaseAppleClient,
)
from src.domains.connectors.clients.normalizers.email_normalizer import (
    _GMAIL_FOLDER_TO_IMAP,
    convert_imap_query,
    normalize_imap_message,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import AppleCredentials
from src.infrastructure.cache.redis import get_redis_session

logger = structlog.get_logger(__name__)


class AppleEmailClient(BaseAppleClient):
    """
    Apple iCloud Email client using IMAP/SMTP.

    Interface matches GoogleGmailClient for transparent provider switching.
    """

    connector_type = ConnectorType.APPLE_EMAIL

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
    ) -> dict[str, Any]:
        """Search emails via IMAP, cache results in Redis."""
        return await self._execute_with_retry(
            "search_emails",
            self._search_emails_impl,
            query,
            max_results,
            fields,
            use_cache,
        )

    async def get_message(
        self,
        message_id: str,
        format: str = "full",
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get a single email by UID, checking Redis cache first."""
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
    ) -> dict[str, Any]:
        """Send an email via SMTP."""
        return await self._execute_with_retry(
            "send_email",
            self._send_email_impl,
            to,
            subject,
            body,
            cc,
            bcc,
            is_html,
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
        )

    async def trash_email(self, message_id: str) -> dict[str, Any]:
        """Move an email to Trash."""
        return await self._execute_with_retry(
            "trash_email",
            self._trash_email_impl,
            message_id,
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

    async def _smtp_send(self, recipients: list[str], msg: MIMEMultipart) -> None:
        """
        Send an email via SMTP STARTTLS.

        Handles connect, STARTTLS, login, sendmail, and quit in a single helper
        to avoid duplicating this pattern across send/reply/forward methods.

        Args:
            recipients: List of recipient email addresses.
            msg: Fully constructed MIME message to send.
        """

        def _do_send() -> None:
            try:
                with smtplib.SMTP(
                    settings.apple_smtp_host, settings.apple_smtp_port, timeout=30
                ) as server:
                    server.starttls()
                    server.login(self.credentials.apple_id, self.credentials.app_password)
                    server.sendmail(self.credentials.apple_id, recipients, msg.as_string())
            except smtplib.SMTPAuthenticationError as e:
                raise AppleAuthenticationError(
                    self.connector_type,
                    f"SMTP LOGIN failed: {e}",
                ) from e

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
    ) -> dict[str, Any]:
        """Search emails via IMAP and cache results in Redis."""
        criteria, target_folder = convert_imap_query(query)
        folder = target_folder or "INBOX"

        def _imap_fetch() -> list[dict[str, Any]]:
            try:
                with MailBox(settings.apple_imap_host, settings.apple_imap_port).login(
                    self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    if folder != "INBOX":
                        mailbox.folder.set(folder)

                    messages = []
                    for msg in mailbox.fetch(
                        criteria,
                        limit=max_results,
                        mark_seen=False,
                        reverse=True,
                    ):
                        # Extract ALL data within context manager
                        normalized = normalize_imap_message(msg, folder)
                        messages.append(normalized)
                    return messages
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        messages = await asyncio.to_thread(_imap_fetch)

        # Cache each message in Redis for get_message (solves N+1 IMAP)
        if messages:
            try:
                redis = await get_redis_session()
                ttl = settings.apple_email_message_cache_ttl
                for msg in messages:
                    cache_key = f"apple_email:{self.user_id}:msg:{msg['id']}"
                    await redis.setex(cache_key, ttl, json.dumps(msg))
            except Exception as e:
                logger.debug("apple_email_cache_write_error", error=str(e))

        return {
            "messages": [{"id": msg["id"]} for msg in messages],
            "resultSizeEstimate": len(messages),
            "from_cache": False,
            "cached_at": None,
        }

    async def _get_message_impl(
        self,
        message_id: str,
        format: str,
        fields: list[str] | None,
        use_cache: bool,
    ) -> dict[str, Any]:
        """Get a single message, checking Redis cache first."""
        # Check Redis cache (populated by search_emails)
        if use_cache:
            try:
                redis = await get_redis_session()
                cache_key = f"apple_email:{self.user_id}:msg:{message_id}"
                cached = await redis.get(cache_key)
                if cached:
                    result = json.loads(cached)
                    result["from_cache"] = True
                    return result
            except Exception as e:
                logger.debug("apple_email_cache_read_error", error=str(e))

        # Cache miss: fetch from IMAP, trying multiple folders
        # UIDs are per-folder in IMAP, so we search INBOX first then other common folders
        search_folders = ["INBOX"]
        for folder in _GMAIL_FOLDER_TO_IMAP.values():
            if folder not in search_folders:
                search_folders.append(folder)

        def _imap_fetch_single() -> dict[str, Any]:
            try:
                with MailBox(settings.apple_imap_host, settings.apple_imap_port).login(
                    self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    for folder in search_folders:
                        try:
                            mailbox.folder.set(folder)
                        except Exception:
                            # Folder may not exist on this server
                            continue
                        for msg in mailbox.fetch(AND(uid=message_id), mark_seen=False):
                            return normalize_imap_message(msg, folder)
                    raise ValueError(f"Message {message_id} not found in any folder")
            except ValueError:
                raise
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        result = await asyncio.to_thread(_imap_fetch_single)

        # Cache for future requests
        try:
            redis = await get_redis_session()
            cache_key = f"apple_email:{self.user_id}:msg:{message_id}"
            await redis.setex(cache_key, settings.apple_email_message_cache_ttl, json.dumps(result))
        except Exception as e:
            logger.warning("apple_email_cache_write_error", error=str(e))

        result["from_cache"] = False
        result["cached_at"] = None
        return result

    async def _send_email_impl(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None,
        bcc: str | None,
        is_html: bool,
    ) -> dict[str, Any]:
        """Send email via SMTP STARTTLS."""
        msg = MIMEMultipart()
        msg["From"] = self.credentials.apple_id
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc

        content_type = "html" if is_html else "plain"
        msg.attach(MIMEText(body, content_type, "utf-8"))

        # Build recipient list
        recipients = [addr.strip() for addr in to.split(",")]
        if cc:
            recipients.extend(addr.strip() for addr in cc.split(","))
        if bcc:
            recipients.extend(addr.strip() for addr in bcc.split(","))

        await self._smtp_send(recipients, msg)
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

        # Extract original headers
        headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}

        # Use override recipient if provided, otherwise reply to original sender
        if not to:
            to = headers.get("From", "")
        subject = headers.get("Subject", "")
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}"

        cc = None
        if reply_all:
            original_to = headers.get("To", "")
            original_cc = headers.get("Cc", "")
            # Combine To and Cc, excluding sender
            all_recipients = []
            for addr in f"{original_to},{original_cc}".split(","):
                addr = addr.strip()
                if addr and addr.lower() != self.credentials.apple_id.lower():
                    all_recipients.append(addr)
            if all_recipients:
                cc = ", ".join(all_recipients)

        # Extract RFC 2822 Message-ID from original for threading headers
        original_message_id = headers.get("Message-ID") or headers.get("Message-Id")

        msg = MIMEMultipart()
        msg["From"] = self.credentials.apple_id
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc
        if original_message_id:
            msg["In-Reply-To"] = original_message_id
            msg["References"] = original_message_id

        # Extract original body and append as quoted text
        original_body = original.get("body", "")
        original_date = headers.get("Date", "")
        original_from_header = headers.get("From", "")

        if original_body and not is_html:
            quoted_lines = "\n".join(f"> {line}" for line in original_body.strip().splitlines())
            quoted_block = f"\n\nOn {original_date}, {original_from_header} wrote:\n{quoted_lines}"
            full_body = body + quoted_block
        else:
            full_body = body

        content_type = "html" if is_html else "plain"
        msg.attach(MIMEText(full_body, content_type, "utf-8"))

        recipients = [addr.strip() for addr in to.split(",")]
        if cc:
            recipients.extend(addr.strip() for addr in cc.split(","))

        await self._smtp_send(recipients, msg)
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
        """Forward an email with optional attachments."""
        # Fetch original with attachments via IMAP
        attachments_data: list[tuple[str, str, bytes]] = []

        def _fetch_with_attachments() -> dict[str, Any]:
            try:
                with MailBox(settings.apple_imap_host, settings.apple_imap_port).login(
                    self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    for msg in mailbox.fetch(AND(uid=message_id), mark_seen=False):
                        normalized = normalize_imap_message(msg, "INBOX")
                        if include_attachments:
                            for att in msg.attachments:
                                attachments_data.append(
                                    (att.filename, att.content_type, att.payload)
                                )
                        return normalized
                    raise ValueError(f"Message {message_id} not found")
            except ValueError:
                raise
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        original = await asyncio.to_thread(_fetch_with_attachments)

        # Build forward headers
        headers = {h["name"]: h["value"] for h in original.get("payload", {}).get("headers", [])}
        subject = headers.get("Subject", "")
        if not subject.lower().startswith("fwd:"):
            subject = f"Fwd: {subject}"

        # Build forward body
        forward_header = (
            f"\n\n---------- Forwarded message ----------\n"
            f"From: {headers.get('From', '')}\n"
            f"Date: {headers.get('Date', '')}\n"
            f"Subject: {headers.get('Subject', '')}\n"
            f"To: {headers.get('To', '')}\n\n"
        )

        # Get original body — Apple normalized messages store body at top-level
        original_body = original.get("body", "")

        full_body = (body or "") + forward_header + original_body

        msg = MIMEMultipart()
        msg["From"] = self.credentials.apple_id
        msg["To"] = to
        msg["Subject"] = subject
        if cc:
            msg["Cc"] = cc

        content_type = "html" if is_html else "plain"
        msg.attach(MIMEText(full_body, content_type, "utf-8"))

        # Attach original attachments
        for filename, content_type_att, payload in attachments_data:
            part = MIMEApplication(payload)
            part.add_header("Content-Disposition", "attachment", filename=filename)
            part["Content-Type"] = content_type_att
            msg.attach(part)

        recipients = [addr.strip() for addr in to.split(",")]
        if cc:
            recipients.extend(addr.strip() for addr in cc.split(","))

        await self._smtp_send(recipients, msg)
        new_id = str(uuid.uuid4())

        return {
            "id": new_id,
            "threadId": message_id,
            "labelIds": ["Sent"],
            "attachments_forwarded": len(attachments_data),
            "attachment_names": [a[0] for a in attachments_data],
        }

    async def _trash_email_impl(self, message_id: str) -> dict[str, Any]:
        """Move email to Trash via IMAP.

        Note: IMAP UIDs are per-folder. We search across common folders
        to find the message before trashing it.
        """
        # Build folder search order: INBOX first, then other common folders
        search_folders = ["INBOX"]
        for folder in _GMAIL_FOLDER_TO_IMAP.values():
            if folder not in search_folders:
                search_folders.append(folder)

        def _imap_trash() -> dict[str, Any]:
            try:
                with MailBox(settings.apple_imap_host, settings.apple_imap_port).login(
                    self.credentials.apple_id, self.credentials.app_password
                ) as mailbox:
                    # Find the message across folders (UIDs are per-folder)
                    found_folder: str | None = None
                    for folder in search_folders:
                        try:
                            mailbox.folder.set(folder)
                        except Exception:
                            # Folder may not exist on this server
                            continue
                        for _msg in mailbox.fetch(AND(uid=message_id), mark_seen=False):
                            found_folder = folder
                            break
                        if found_folder:
                            break

                    if not found_folder:
                        raise ValueError(f"Message {message_id} not found in any folder")

                    # Ensure we're in the correct folder for the operation
                    mailbox.folder.set(found_folder)

                    try:
                        # Try MOVE first (RFC 6851)
                        mailbox.move([message_id], "Trash")
                    except Exception:
                        # Fallback: COPY + DELETE
                        mailbox.copy([message_id], "Trash")
                        mailbox.delete([message_id])

                    return {
                        "id": message_id,
                        "threadId": message_id,
                        "labelIds": ["Trash"],
                    }
            except Exception as e:
                self._check_imap_auth_error(e)
                raise

        result = await asyncio.to_thread(_imap_trash)

        # Invalidate Redis cache
        try:
            redis = await get_redis_session()
            cache_key = f"apple_email:{self.user_id}:msg:{message_id}"
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
                with MailBox(settings.apple_imap_host, settings.apple_imap_port).login(
                    self.credentials.apple_id, self.credentials.app_password
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
