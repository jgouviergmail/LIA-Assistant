"""
Google Gmail API client for email operations.
Handles authentication, MIME parsing, rate limiting, caching, and pagination.

Inherits from BaseGoogleClient for common functionality.
Reference: https://developers.google.com/gmail/api/reference/rest
"""

import base64
import hashlib
import json
import re
from datetime import UTC, datetime
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr, getaddresses
from html.parser import HTMLParser
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.core.constants import (
    GMAIL_FORMAT_FULL,
    GMAIL_FORMAT_METADATA,
    GMAIL_LABELS_CACHE_TTL,
    GOOGLE_GMAIL_API_BASE_URL,
    REDIS_KEY_GMAIL_LABELS_PREFIX,
    REDIS_KEY_GMAIL_MESSAGE_PREFIX,
    REDIS_KEY_GMAIL_SEARCH_PREFIX,
)
from src.core.field_names import FIELD_CACHED_AT
from src.core.validators import validate_email
from src.domains.connectors.clients.base_google_client import (
    BaseGoogleClient,
    apply_max_items_limit,
)
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import ConnectorCredentials
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


class HTMLToTextConverter(HTMLParser):
    """
    Convert HTML to readable plain text.

    Preserves important structure:
    - Paragraphs: Adds double newlines between <p> tags
    - Line breaks: Converts <br> to single newline
    - Links: Converts <a href="url">text</a> to "text (url)"
    - Lists: Adds bullets/numbers for <li> items
    - Headers: Adds newlines before/after headers
    - Ignores: <style>, <script>, and other non-content tags

    Example:
        >>> converter = HTMLToTextConverter()
        >>> converter.feed("<p>Hello <b>world</b>!</p><p>Second paragraph.</p>")
        >>> text = converter.get_text()
        >>> # Returns: "Hello world!\\n\\nSecond paragraph.\\n\\n"
    """

    def __init__(self, url_shorten_threshold: int = 50) -> None:
        """
        Initialize HTML parser.

        Args:
            url_shorten_threshold: URLs longer than this are shortened to [lien](url)
        """
        super().__init__()
        self.text_parts: list[str] = []
        self.ignore_content = False  # For <style>, <script> tags
        self.current_link_url: str | None = None
        self.in_list_item = False
        self.url_shorten_threshold = url_shorten_threshold

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Handle opening HTML tags."""
        # Block-level elements: Add newlines before
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"):
            self.text_parts.append("\n")
        elif tag == "br":
            self.text_parts.append("\n")
        elif tag == "li":
            self.text_parts.append("\n• ")
            self.in_list_item = True
        elif tag == "a":
            # Extract href attribute
            for attr_name, attr_value in attrs:
                if attr_name == "href" and attr_value:
                    self.current_link_url = attr_value
                    break
        elif tag in ("style", "script"):
            self.ignore_content = True

    def handle_endtag(self, tag: str) -> None:
        """Handle closing HTML tags."""
        # Block-level elements: Add newlines after
        if tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote"):
            self.text_parts.append("\n")
        elif tag == "li":
            self.in_list_item = False
        elif tag == "a":
            # Add clickable [lien](url) in markdown format
            if self.current_link_url:
                self.text_parts.append(f" [lien]({self.current_link_url})")
                self.current_link_url = None
        elif tag in ("style", "script"):
            self.ignore_content = False

    def handle_data(self, data: str) -> None:
        """Handle text content."""
        if not self.ignore_content and data.strip():
            # Normalize whitespace (multiple spaces/tabs/newlines → single space)
            normalized = " ".join(data.split())
            if normalized:
                # Add space before inline content if needed
                # This ensures "This is <b>bold</b> text" becomes "This is bold text"
                # instead of "This isbold text"
                if self.text_parts:
                    last_part = self.text_parts[-1]
                    # If last part doesn't end with whitespace/newline and
                    # current text doesn't start with punctuation, add space
                    if (
                        last_part
                        and not last_part[-1].isspace()
                        and not last_part.endswith("\n")
                        and normalized[0] not in ".,;:!?'\")]}—"
                    ):
                        self.text_parts.append(" ")
                self.text_parts.append(normalized)

    def get_text(self) -> str:
        """
        Get extracted plain text.

        Returns:
            Cleaned plain text with normalized whitespace.
        """
        # Join all parts
        text = "".join(self.text_parts)

        # Replace standalone URLs (not in <a> tags) with clickable [lien](url)
        # Pattern: https?://... with many characters (tracking params, etc.)
        # Keep short URLs as-is, replace longer ones with clickable [lien](url)
        threshold = self.url_shorten_threshold

        def replace_long_url(match: re.Match[str]) -> str:
            url = match.group(0)
            # Skip if already in markdown format [text](url)
            if url.endswith(")"):
                return url
            if len(url) > threshold:
                return f"[lien]({url})"
            return url

        text = re.sub(
            r"https?://[^\s<>\"'\)]+",  # Match URLs not followed by HTML/quotes/parens
            replace_long_url,
            text,
        )

        # Clean up excessive newlines (more than 2 consecutive → 2)
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Remove leading/trailing whitespace from each line
        lines = [line.strip() for line in text.split("\n")]

        # Remove empty lines at start/end
        while lines and not lines[0]:
            lines.pop(0)
        while lines and not lines[-1]:
            lines.pop()

        return "\n".join(lines)


class GoogleGmailClient(BaseGoogleClient):
    """
    Google Gmail API client with OAuth, rate limiting, caching, and error handling.

    Inherits common functionality from BaseGoogleClient:
    - Automatic token refresh with Redis lock
    - Rate limiting (configurable, default 10 req/s)
    - HTTP client with connection pooling
    - Retry logic with exponential backoff

    Adds domain-specific features:
    - Redis caching (configurable TTL)
    - Pagination support
    - MIME message parsing and encoding
    - HTML to plain text conversion

    Example:
        >>> client = GoogleGmailClient(user_id, credentials, connector_service)
        >>> results = await client.search_emails("from:john@example.com", max_results=10)
        >>> # results = {"messages": [...], "resultSizeEstimate": 5}
    """

    # Required by BaseGoogleClient
    connector_type = ConnectorType.GOOGLE_GMAIL
    api_base_url = GOOGLE_GMAIL_API_BASE_URL

    def __init__(
        self,
        user_id: UUID,
        credentials: ConnectorCredentials,
        connector_service: Any,  # ConnectorService
    ) -> None:
        """
        Initialize Google Gmail client.

        Args:
            user_id: User UUID.
            credentials: OAuth credentials (access_token, refresh_token).
            connector_service: ConnectorService instance for token refresh.
        """
        # Initialize base class with default rate limiting
        super().__init__(user_id, credentials, connector_service)

    # ========================================================================
    # MIME PARSING UTILITIES
    # ========================================================================

    @staticmethod
    def _decode_base64url(data: str) -> str:
        """
        Decode Gmail's base64url-encoded string.

        Gmail uses base64url encoding (RFC 4648) for message bodies.
        This replaces - with + and _ with /, then pads with = as needed.

        Args:
            data: Base64url-encoded string.

        Returns:
            Decoded UTF-8 string.
        """
        # Replace URL-safe chars with standard base64
        data = data.replace("-", "+").replace("_", "/")

        # Add padding if needed
        padding = len(data) % 4
        if padding:
            data += "=" * (4 - padding)

        # Decode
        try:
            decoded_bytes = base64.b64decode(data)
            return decoded_bytes.decode("utf-8", errors="ignore")
        except Exception as e:
            logger.warning("base64url_decode_failed", error=str(e))
            return ""

    @staticmethod
    def _encode_base64url(text: str) -> str:
        """
        Encode text to Gmail's base64url format.

        Args:
            text: UTF-8 text to encode.

        Returns:
            Base64url-encoded string (no padding).
        """
        encoded_bytes = base64.urlsafe_b64encode(text.encode("utf-8"))
        # Remove padding (Gmail expects no padding)
        return encoded_bytes.decode("utf-8").rstrip("=")

    @staticmethod
    def _extract_headers(message: dict[str, Any]) -> dict[str, str]:
        """
        Extract common headers from Gmail message payload.

        Args:
            message: Gmail message object.

        Returns:
            Dict with common headers (From, To, Subject, Date, etc.).
        """
        headers_raw = message.get("payload", {}).get("headers", [])
        headers = {}

        for header in headers_raw:
            name = header.get("name", "").lower()
            value = header.get("value", "")

            if name in ["from", "to", "cc", "bcc", "subject", "date", "message-id"]:
                headers[name] = value

        return headers

    @staticmethod
    def _normalize_message_fields(message: dict[str, Any], format: str) -> None:
        """Normalize Gmail API message to unified provider format (in-place).

        Extracts common headers (from, to, cc, subject, date) from
        payload.headers to top-level fields, matching the format already
        produced by Apple (normalize_imap_message) and Microsoft
        (normalize_graph_message) normalizers.

        This ensures all three email providers return messages with the same
        top-level field structure, enabling provider-agnostic consumption
        throughout the application.

        Body is extracted only when format is 'full' (metadata format does
        not include body data in the Gmail API response).

        The original payload.headers structure is preserved for backwards
        compatibility with existing header-based extraction code.

        Args:
            message: Gmail API message dict (mutated in-place).
            format: Gmail format used for the request ('full', 'metadata').
        """
        # Extract headers to top-level (only if not already present)
        headers = GoogleGmailClient._extract_headers(message)
        for field in ("from", "to", "cc", "subject", "date"):
            if field not in message and headers.get(field):
                message[field] = headers[field]

        # Extract body to top-level (only for full format, which includes body data)
        if format == GMAIL_FORMAT_FULL and "body" not in message:
            payload = message.get("payload")
            if payload:
                body = GoogleGmailClient._extract_body_recursive(payload)
                if body:
                    message["body"] = body

        # Mark provider for downstream identification (same as Apple/Microsoft)
        if "_provider" not in message:
            message["_provider"] = "google"

    @staticmethod
    def _extract_body_recursive(
        payload: dict[str, Any],
        max_depth: int = 10,
        _current_depth: int = 0,
    ) -> str:
        """
        Recursively extract text body from multipart MIME message with bounded recursion.

        Gmail messages can be complex multipart structures:
        - text/plain (preferred for LLM consumption)
        - text/html (converted to readable plain text)
        - multipart/alternative (contains both text and HTML)
        - multipart/mixed (contains attachments)

        Security 2025-12-19: Added max_depth to prevent stack overflow on malformed payloads.
        Typical Gmail messages have 2-4 levels; max_depth=10 provides safety margin.

        Args:
            payload: Gmail message payload object.
            max_depth: Maximum recursion depth (default: 10).
            _current_depth: Internal counter (do not set externally).

        Returns:
            Extracted text body (plain text preferred, HTML converted to text).
            Returns "" if max depth exceeded.
        """
        # Fail-safe: prevent stack overflow on malformed/malicious payloads
        if _current_depth >= max_depth:
            return ""
        mime_type = payload.get("mimeType", "")

        # Base case: Simple text/plain body
        if mime_type == "text/plain":
            body_data = payload.get("body", {}).get("data", "")
            if body_data:
                return GoogleGmailClient._decode_base64url(body_data)

        # Base case: HTML body (convert to readable plain text)
        if mime_type == "text/html":
            body_data = payload.get("body", {}).get("data", "")
            if body_data:
                html = GoogleGmailClient._decode_base64url(body_data)
                # Convert HTML to readable plain text using HTMLParser
                # Use configured URL shortening threshold
                converter = HTMLToTextConverter(
                    url_shorten_threshold=settings.emails_url_shorten_threshold
                )
                try:
                    converter.feed(html)
                    return converter.get_text()
                except Exception as e:
                    logger.warning(
                        "html_to_text_conversion_failed",
                        error=str(e),
                        html_preview=html[:100],
                    )
                    # Fallback to basic regex stripping if parser fails
                    text = re.sub(r"<[^>]+>", "", html)
                    return text.strip()

        # Recursive case: Multipart message (with bounded depth)
        if mime_type.startswith("multipart/"):
            parts = payload.get("parts", [])
            next_depth = _current_depth + 1

            # Try text/plain first (preferred)
            for part in parts:
                if part.get("mimeType") == "text/plain":
                    text = GoogleGmailClient._extract_body_recursive(part, max_depth, next_depth)
                    if text:
                        return text

            # Fallback: Try HTML
            for part in parts:
                if part.get("mimeType") == "text/html":
                    text = GoogleGmailClient._extract_body_recursive(part, max_depth, next_depth)
                    if text:
                        return text

            # Fallback: Recurse into nested multipart
            for part in parts:
                if part.get("mimeType", "").startswith("multipart/"):
                    text = GoogleGmailClient._extract_body_recursive(part, max_depth, next_depth)
                    if text:
                        return text

        return ""

    @staticmethod
    def _encode_email_header(addresses: str) -> str:
        """
        Encode email address header(s) with proper RFC 2047 encoding for non-ASCII characters.

        Email headers containing non-ASCII characters (like accents in display names)
        must be encoded per RFC 2047 for Gmail API acceptance.

        Handles both single address and comma-separated list of addresses.

        Args:
            addresses: Email address(es), possibly with display names
                       (e.g., '"Jérôme G" <email@example.com>, john@example.com')

        Returns:
            RFC 2047 encoded email address string.

        Raises:
            ValueError: If any email address has invalid format (missing TLD, etc.)

        Example:
            >>> GoogleGmailClient._encode_email_header('"Jérôme G" <jean@example.com>')
            '=?utf-8?q?J=C3=A9r=C3=B4me_G?= <jean@example.com>'
        """
        # Parse all addresses (handles comma-separated with quoted names)
        addresses_list = getaddresses([addresses])

        encoded_addresses = []
        for name, email in addresses_list:
            # Defensive validation: catch invalid emails before Gmail API rejects them
            # This prevents cryptic "Invalid To header" errors from the API
            if email and not validate_email(email):
                raise ValueError(
                    f"Format d'adresse email invalide: '{email}'. "
                    f"L'adresse doit contenir un domaine complet (ex: user@example.com)"
                )

            if name:
                try:
                    # Check if name contains non-ASCII characters
                    name.encode("ascii")
                    # Pure ASCII, no encoding needed
                    encoded_addresses.append(formataddr((name, email)))
                except UnicodeEncodeError:
                    # Non-ASCII characters, need RFC 2047 encoding
                    encoded_name = Header(name, "utf-8").encode()
                    encoded_addresses.append(formataddr((encoded_name, email)))
            else:
                # No display name, use email address directly
                encoded_addresses.append(email)

        return ", ".join(encoded_addresses)

    @staticmethod
    def _extract_attachment_info(payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Extract attachment information from message payload.

        Recursively scans MIME parts to find all attachments.

        Args:
            payload: Gmail message payload object.

        Returns:
            List of attachment info dicts with:
            - attachment_id: Gmail attachment ID
            - filename: Original filename
            - mime_type: MIME type (e.g., application/pdf)
            - size: Attachment size in bytes
            - part_id: Part ID in the message structure
        """
        attachments: list[dict[str, Any]] = []

        def scan_parts(parts: list[dict[str, Any]], parent_part_id: str = "") -> None:
            for i, part in enumerate(parts):
                part_id = f"{parent_part_id}.{i}" if parent_part_id else str(i)
                mime_type = part.get("mimeType", "")
                filename = part.get("filename", "")
                body = part.get("body", {})

                # Check if this is an attachment (has filename and attachmentId)
                if filename and body.get("attachmentId"):
                    attachments.append(
                        {
                            "attachment_id": body["attachmentId"],
                            "filename": filename,
                            "mime_type": mime_type,
                            "size": body.get("size", 0),
                            "part_id": part_id,
                        }
                    )

                # Recurse into nested parts
                if "parts" in part:
                    scan_parts(part["parts"], part_id)

        # Start scanning from top-level parts
        if "parts" in payload:
            scan_parts(payload["parts"])

        return attachments

    async def get_attachment(
        self,
        message_id: str,
        attachment_id: str,
    ) -> bytes:
        """
        Download attachment data from Gmail.

        Args:
            message_id: Gmail message ID.
            attachment_id: Gmail attachment ID.

        Returns:
            Raw attachment bytes.

        Example:
            >>> data = await client.get_attachment("msg123", "att456")
            >>> with open("file.pdf", "wb") as f:
            ...     f.write(data)
        """
        response = await self._make_request(
            "GET",
            f"/users/me/messages/{message_id}/attachments/{attachment_id}",
        )

        # Gmail returns base64url-encoded data
        data_b64 = response.get("data", "")
        # Convert base64url to standard base64
        data_b64 = data_b64.replace("-", "+").replace("_", "/")
        # Add padding if needed
        padding = len(data_b64) % 4
        if padding:
            data_b64 += "=" * (4 - padding)

        return base64.b64decode(data_b64)

    # ========================================================================
    # PUBLIC API METHODS
    # ========================================================================

    async def search_emails(
        self,
        query: str,
        max_results: int = settings.emails_tool_default_max_results,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Search emails using Gmail search query syntax.

        Gmail query syntax: https://support.google.com/mail/answer/7190
        Examples:
        - "from:john@example.com" - Emails from John
        - "subject:meeting" - Emails with "meeting" in subject
        - "is:unread" - Unread emails
        - "has:attachment" - Emails with attachments
        - "after:2025/01/01" - Emails after Jan 1, 2025

        Args:
            query: Gmail search query (supports all Gmail search operators).
            max_results: Maximum number of results (default 10, max 500).
            fields: Field projection (default: GOOGLE_GMAIL_SEARCH_FIELDS).
            use_cache: Use Redis cache (default True).

        Returns:
            Dict with:
            - messages: List of message objects
            - resultSizeEstimate: Approximate total matches
            - from_cache: Boolean (True if served from cache)
            - cached_at: Cache timestamp (if from cache)

        Example:
            >>> results = await client.search_emails(
            ...     query="from:john@example.com subject:invoice",
            ...     max_results=20
            ... )
        """
        # Generate cache key
        cache_key = f"{REDIS_KEY_GMAIL_SEARCH_PREFIX}{self.user_id}:{hashlib.md5(query.encode()).hexdigest()}:{max_results}"

        # Try cache first
        if use_cache:
            redis_client = await get_redis_cache()
            cached_data_raw = await redis_client.get(cache_key)
            if cached_data_raw:
                # Deserialize JSON string from Redis
                cached_data = json.loads(cached_data_raw)
                logger.debug(
                    "gmail_search_cache_hit",
                    user_id=str(self.user_id),
                    query_preview=query[:50],
                )
                return {
                    **cached_data,
                    "from_cache": True,
                    FIELD_CACHED_AT: cached_data.get(FIELD_CACHED_AT),
                }

        # Apply security limit
        effective_max_results = apply_max_items_limit(max_results)

        # Search messages (list API with query parameter)
        params = {
            "q": query,
            "maxResults": effective_max_results,
        }

        response = await self._make_request("GET", "/users/me/messages", params=params)

        # Get list of message IDs
        message_ids = [msg["id"] for msg in response.get("messages", [])]

        # Fetch message metadata (batch would be better, but simpler for MVP)
        messages = []
        for msg_id in message_ids[:effective_max_results]:
            try:
                msg_data = await self.get_message(msg_id, format=GMAIL_FORMAT_METADATA)
                messages.append(msg_data)
            except Exception as e:
                logger.warning("gmail_search_message_fetch_failed", message_id=msg_id, error=str(e))
                continue

        result = {
            "messages": messages,
            "resultSizeEstimate": response.get("resultSizeEstimate", len(messages)),
        }

        # Cache result
        if use_cache:
            redis_client = await get_redis_cache()
            cache_data = {
                **result,
                FIELD_CACHED_AT: datetime.now(UTC).isoformat(),
            }
            await redis_client.setex(
                cache_key,
                settings.emails_cache_search_ttl_seconds,
                json.dumps(cache_data),  # Serialize dict to JSON string for Redis
            )

        return {
            **result,
            "from_cache": False,
        }

    async def get_message(
        self,
        message_id: str,
        format: str = GMAIL_FORMAT_FULL,
        fields: list[str] | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get a single email message by ID.

        Args:
            message_id: Gmail message ID (e.g., "17f2a1b2c3d4e5f6").
            format: Message format (minimal, metadata, full, raw).
            fields: Field projection (optional).
            use_cache: Use Redis cache (default True).

        Returns:
            Dict with message data:
            - id: Message ID
            - threadId: Thread ID
            - labelIds: List of labels
            - snippet: Preview text
            - payload: Message payload (headers, body, parts)
            - internalDate: Timestamp (milliseconds since epoch)
            - from_cache: Boolean
            - cached_at: Cache timestamp (if from cache)

        Example:
            >>> message = await client.get_message("17f2a1b2c3d4e5f6")
            >>> print(message["payload"]["headers"])
        """
        # Generate cache key
        cache_key = f"{REDIS_KEY_GMAIL_MESSAGE_PREFIX}{self.user_id}:{message_id}:{format}"

        # Try cache first
        if use_cache:
            redis_client = await get_redis_cache()
            cached_data_raw = await redis_client.get(cache_key)
            if cached_data_raw:
                # Deserialize JSON string from Redis
                cached_data = json.loads(cached_data_raw)
                logger.debug(
                    "gmail_message_cache_hit",
                    user_id=str(self.user_id),
                    message_id=message_id,
                )
                return {
                    **cached_data,
                    "from_cache": True,
                    FIELD_CACHED_AT: cached_data.get(FIELD_CACHED_AT),
                }

        # Fetch message
        params = {"format": format}
        response = await self._make_request(
            "GET", f"/users/me/messages/{message_id}", params=params
        )

        # Normalize: extract common headers to top-level fields.
        # Apple and Microsoft normalizers already set top-level from/subject/to/cc/body.
        # This brings Google Gmail in line for a unified message format across providers.
        self._normalize_message_fields(response, format)

        # Cache result (normalized format so cache hits are also normalized)
        if use_cache:
            redis_client = await get_redis_cache()
            cache_data = {
                **response,
                FIELD_CACHED_AT: datetime.now(UTC).isoformat(),
            }
            await redis_client.setex(
                cache_key,
                settings.emails_cache_details_ttl_seconds,
                json.dumps(cache_data),  # Serialize dict to JSON string for Redis
            )

        return {
            **response,
            "from_cache": False,
        }

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str | None = None,
        bcc: str | None = None,
        is_html: bool = False,
    ) -> dict[str, Any]:
        """
        Send an email via Gmail API.

        Args:
            to: Recipient email address (or comma-separated list).
            subject: Email subject.
            body: Email body (text/plain or text/html).
            cc: CC recipients (optional, comma-separated).
            bcc: BCC recipients (optional, comma-separated).
            is_html: True if body is HTML, False for plain text (default False).

        Returns:
            Dict with:
            - id: Sent message ID
            - threadId: Thread ID
            - labelIds: Labels applied to sent message

        Raises:
            HTTPException: On send failure.

        Example:
            >>> result = await client.send_email(
            ...     to="john@example.com",
            ...     subject="Meeting Confirmation",
            ...     body="Hi John,\n\nConfirming our meeting tomorrow at 2pm.\n\nBest regards"
            ... )
        """
        # Build MIME message
        if is_html:
            message = MIMEText(body, "html", "utf-8")
        else:
            message = MIMEText(body, "plain", "utf-8")

        # Encode headers with RFC 2047 for non-ASCII characters
        message["To"] = self._encode_email_header(to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = self._encode_email_header(cc)
        if bcc:
            message["Bcc"] = self._encode_email_header(bcc)

        # Encode to base64url
        raw_message = self._encode_base64url(message.as_string())

        # Send via Gmail API
        json_data = {"raw": raw_message}
        response = await self._make_request("POST", "/users/me/messages/send", json_data=json_data)

        logger.info(
            "gmail_email_sent",
            user_id=str(self.user_id),
            message_id=response.get("id"),
            to=to,
            subject=subject[:50],
        )

        return response

    async def reply_email(
        self,
        message_id: str,
        body: str,
        reply_all: bool = False,
        is_html: bool = False,
        to: str | None = None,
    ) -> dict[str, Any]:
        """
        Reply to an email via Gmail API.

        Maintains the same thread as the original message.

        Args:
            message_id: Original message ID to reply to.
            body: Reply body (text/plain or text/html).
            reply_all: If True, reply to all recipients (default False).
            is_html: True if body is HTML, False for plain text (default False).
            to: Override recipient address. If None, replies to original sender.

        Returns:
            Dict with sent message details (id, threadId, labelIds).

        Example:
            >>> result = await client.reply_email(
            ...     message_id="abc123",
            ...     body="Thank you for your message...",
            ... )
        """
        # Get original message to extract thread info and recipients
        original = await self.get_message(message_id)
        thread_id = original.get("threadId")

        # Extract headers
        headers = original.get("payload", {}).get("headers", [])
        header_dict = {h.get("name", "").lower(): h.get("value", "") for h in headers}

        # Get original subject (add Re: if not present)
        original_subject = header_dict.get("subject", "")
        if not original_subject.lower().startswith("re:"):
            subject = f"Re: {original_subject}"
        else:
            subject = original_subject

        # Get recipients
        original_from = header_dict.get("from", "")
        original_cc = header_dict.get("cc", "")

        # Determine reply-to address (user override takes precedence)
        if to:
            # User explicitly specified recipient (e.g., via draft modification)
            cc = None
        elif reply_all:
            # Reply to all: original sender + original recipients (except self)
            to = original_from
            cc = original_cc if original_cc else None
        else:
            # Simple reply: just to the original sender
            to = original_from
            cc = None

        # Build MIME message
        if is_html:
            message = MIMEText(body, "html", "utf-8")
        else:
            message = MIMEText(body, "plain", "utf-8")

        # Encode headers with RFC 2047 for non-ASCII characters
        message["To"] = self._encode_email_header(to)
        message["Subject"] = subject
        message["In-Reply-To"] = header_dict.get("message-id", "")
        message["References"] = header_dict.get("message-id", "")

        if cc:
            message["Cc"] = self._encode_email_header(cc)

        # Extract original body and append as quoted text
        original_date = header_dict.get("date", "")
        original_body = self._extract_body_recursive(original.get("payload", {}))

        if original_body and not is_html:
            quoted_lines = "\n".join(f"> {line}" for line in original_body.strip().splitlines())
            quoted_block = f"\n\nOn {original_date}, {original_from} wrote:\n{quoted_lines}"
            # Replace body part with body + quoted original
            message.set_payload((body + quoted_block).encode("utf-8"))

        # Encode to base64url
        raw_message = self._encode_base64url(message.as_string())

        # Send via Gmail API with threadId to maintain thread
        json_data = {
            "raw": raw_message,
            "threadId": thread_id,
        }
        response = await self._make_request("POST", "/users/me/messages/send", json_data=json_data)

        logger.info(
            "gmail_email_reply_sent",
            user_id=str(self.user_id),
            message_id=response.get("id"),
            original_message_id=message_id,
            thread_id=thread_id,
            reply_all=reply_all,
        )

        return response

    async def forward_email(
        self,
        message_id: str,
        to: str,
        body: str | None = None,
        cc: str | None = None,
        is_html: bool = False,
        include_attachments: bool = True,
    ) -> dict[str, Any]:
        """
        Forward an email via Gmail API.

        Creates a new thread with the forwarded message.
        Includes all original attachments by default.

        Args:
            message_id: Original message ID to forward.
            to: Forward recipient email address (or comma-separated list).
            body: Additional message to prepend (optional).
            cc: CC recipients (optional, comma-separated).
            is_html: True if body is HTML, False for plain text (default False).
            include_attachments: Include original attachments (default True).

        Returns:
            Dict with sent message details (id, threadId, labelIds, attachments_count).

        Example:
            >>> result = await client.forward_email(
            ...     message_id="abc123",
            ...     to="colleague@example.com",
            ...     body="FYI - see below",
            ... )
        """
        # Get original message with full content
        original = await self.get_message(message_id)
        payload = original.get("payload", {})

        # Extract headers
        headers = payload.get("headers", [])
        header_dict = {h.get("name", "").lower(): h.get("value", "") for h in headers}

        # Get original subject (add Fwd: if not present)
        original_subject = header_dict.get("subject", "")
        if not original_subject.lower().startswith("fwd:"):
            subject = f"Fwd: {original_subject}"
        else:
            subject = original_subject

        # Get original message body using the recursive extractor
        original_body = self._extract_body_recursive(payload)

        # Build forwarded message body
        original_from = header_dict.get("from", "")
        original_date = header_dict.get("date", "")
        original_to = header_dict.get("to", "")

        forward_header = (
            f"\n\n---------- Forwarded message ---------\n"
            f"From: {original_from}\n"
            f"Date: {original_date}\n"
            f"Subject: {original_subject}\n"
            f"To: {original_to}\n\n"
        )

        if body:
            full_body = body + forward_header + original_body
        else:
            full_body = forward_header + original_body

        # Extract attachments info
        attachments_info = self._extract_attachment_info(payload) if include_attachments else []
        has_attachments = len(attachments_info) > 0

        # Build MIME message
        if has_attachments:
            # Use MIMEMultipart for messages with attachments
            message = MIMEMultipart("mixed")

            # Add the text body as the first part
            if is_html:
                text_part = MIMEText(full_body, "html", "utf-8")
            else:
                text_part = MIMEText(full_body, "plain", "utf-8")
            message.attach(text_part)

            # Fetch and attach each attachment
            for att_info in attachments_info:
                try:
                    # Download attachment data
                    att_data = await self.get_attachment(message_id, att_info["attachment_id"])

                    # Determine MIME type
                    mime_type = att_info.get("mime_type", "application/octet-stream")
                    maintype, subtype = (
                        mime_type.split("/", 1)
                        if "/" in mime_type
                        else ("application", "octet-stream")
                    )

                    # Create attachment part
                    att_part = MIMEBase(maintype, subtype)
                    att_part.set_payload(att_data)

                    # Encode in base64
                    from email import encoders

                    encoders.encode_base64(att_part)

                    # Set Content-Disposition header with filename
                    filename = att_info.get("filename", "attachment")
                    att_part.add_header(
                        "Content-Disposition",
                        "attachment",
                        filename=filename,
                    )

                    message.attach(att_part)

                    logger.debug(
                        "gmail_forward_attachment_added",
                        filename=filename,
                        mime_type=mime_type,
                        size=att_info.get("size", 0),
                    )

                except Exception as e:
                    logger.warning(
                        "gmail_forward_attachment_failed",
                        attachment_id=att_info.get("attachment_id"),
                        filename=att_info.get("filename"),
                        error=str(e),
                    )
                    # Continue with other attachments even if one fails
                    continue
        else:
            # Simple text message without attachments
            if is_html:
                message = MIMEText(full_body, "html", "utf-8")
            else:
                message = MIMEText(full_body, "plain", "utf-8")

        # Encode headers with RFC 2047 for non-ASCII characters
        message["To"] = self._encode_email_header(to)
        message["Subject"] = subject

        if cc:
            message["Cc"] = self._encode_email_header(cc)

        # Encode to base64url
        raw_message = self._encode_base64url(message.as_string())

        # Send via Gmail API (no threadId - creates new thread)
        json_data = {"raw": raw_message}
        response = await self._make_request("POST", "/users/me/messages/send", json_data=json_data)

        logger.info(
            "gmail_email_forwarded",
            user_id=str(self.user_id),
            message_id=response.get("id"),
            original_message_id=message_id,
            to=to,
            attachments_count=len(attachments_info),
        )

        # Add attachments count to response for caller info
        response["attachments_forwarded"] = len(attachments_info)
        response["attachment_names"] = [a.get("filename") for a in attachments_info]

        return response

    async def trash_email(
        self,
        message_id: str,
    ) -> dict[str, Any]:
        """
        Move an email to trash via Gmail API.

        This is a soft delete - the email can be recovered from trash
        for 30 days before permanent deletion.

        Args:
            message_id: Message ID to move to trash.

        Returns:
            Dict with trashed message details (id, threadId, labelIds).

        Example:
            >>> result = await client.trash_email(message_id="abc123")
            >>> print(result["labelIds"])  # Will contain "TRASH"
        """
        response = await self._make_request(
            "POST",
            f"/users/me/messages/{message_id}/trash",
        )

        logger.info(
            "gmail_email_trashed",
            user_id=str(self.user_id),
            message_id=message_id,
        )

        return response

    async def untrash_email(
        self,
        message_id: str,
    ) -> dict[str, Any]:
        """
        Remove an email from trash via Gmail API.

        Restores the email to its previous location before being trashed.

        Args:
            message_id: Message ID to restore from trash.

        Returns:
            Dict with restored message details (id, threadId, labelIds).

        Example:
            >>> result = await client.untrash_email(message_id="abc123")
        """
        response = await self._make_request(
            "POST",
            f"/users/me/messages/{message_id}/untrash",
        )

        logger.info(
            "gmail_email_untrashed",
            user_id=str(self.user_id),
            message_id=message_id,
        )

        return response

    async def delete_email_permanently(
        self,
        message_id: str,
    ) -> None:
        """
        Permanently delete an email via Gmail API.

        WARNING: This action is IRREVERSIBLE. The email cannot be recovered.
        Use trash_email for soft delete instead.

        Args:
            message_id: Message ID to permanently delete.

        Raises:
            Exception: If deletion fails.

        Example:
            >>> await client.delete_email_permanently(message_id="abc123")
        """
        await self._make_request(
            "DELETE",
            f"/users/me/messages/{message_id}",
        )

        logger.info(
            "gmail_email_deleted_permanently",
            user_id=str(self.user_id),
            message_id=message_id,
        )

    # ========================================================================
    # LABELS MANAGEMENT
    # ========================================================================

    async def list_labels(
        self,
        use_cache: bool = True,
    ) -> dict[str, str]:
        """
        List all Gmail labels for the user.

        Returns a mapping of label IDs to label names for translating
        technical IDs (e.g., "Label_12345678") to user-friendly names.

        Args:
            use_cache: Use Redis cache (default True). Labels rarely change,
                so caching is highly recommended.

        Returns:
            Dict mapping label ID to label name:
            {
                "INBOX": "INBOX",
                "SENT": "SENT",
                "Label_12345678": "Mon projet",
                "Label_87654321": "À traiter",
            }

        Example:
            >>> labels = await client.list_labels()
            >>> print(labels.get("Label_12345678"))
            "Mon projet"
        """
        cache_key = f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{self.user_id}"

        # Try cache first
        if use_cache:
            redis_client = await get_redis_cache()
            cached_data_raw = await redis_client.get(cache_key)
            if cached_data_raw:
                cached_data = json.loads(cached_data_raw)
                logger.debug(
                    "gmail_labels_cache_hit",
                    user_id=str(self.user_id),
                    labels_count=len(cached_data),
                )
                return cached_data

        # Fetch labels from API
        response = await self._make_request("GET", "/users/me/labels")

        # Build ID -> name mapping
        labels_mapping: dict[str, str] = {}
        for label in response.get("labels", []):
            label_id = label.get("id", "")
            label_name = label.get("name", label_id)
            if label_id:
                labels_mapping[label_id] = label_name

        logger.debug(
            "gmail_labels_fetched",
            user_id=str(self.user_id),
            labels_count=len(labels_mapping),
        )

        # Cache result (labels rarely change)
        if use_cache:
            redis_client = await get_redis_cache()
            await redis_client.setex(
                cache_key,
                GMAIL_LABELS_CACHE_TTL,
                json.dumps(labels_mapping),
            )

        return labels_mapping

    async def get_label_id_by_name(
        self,
        label_name: str,
        use_cache: bool = True,
    ) -> str | None:
        """
        Get label ID from its user-friendly name.

        Performs case-insensitive matching for user convenience.
        Used to translate queries like "label:COPRO" to "label:Label_12345678".

        Args:
            label_name: User-friendly label name (e.g., "COPRO", "Projets")
            use_cache: Use cached labels (default True)

        Returns:
            Label ID if found, None otherwise

        Example:
            >>> label_id = await client.get_label_id_by_name("COPRO")
            >>> print(label_id)
            "Label_12345678"
        """
        labels_mapping = await self.list_labels(use_cache=use_cache)

        # Build reverse mapping (name -> id), case-insensitive
        name_to_id: dict[str, str] = {}
        for label_id, name in labels_mapping.items():
            name_to_id[name.lower()] = label_id

        # Lookup (case-insensitive)
        return name_to_id.get(label_name.lower())

    async def resolve_label_names_in_query(
        self,
        query: str,
        use_cache: bool = True,
    ) -> str:
        """
        Resolve user-friendly label names to Gmail label IDs in a query.

        Transforms queries like "label:COPRO from:john" to "label:Label_12345678 from:john".
        System labels (INBOX, SENT, etc.) are kept as-is.

        Args:
            query: Gmail search query with potential user-friendly label names
            use_cache: Use cached labels (default True)

        Returns:
            Query with label names resolved to IDs

        Example:
            >>> resolved = await client.resolve_label_names_in_query("label:COPRO is:unread")
            >>> print(resolved)
            "label:Label_12345678 is:unread"
        """
        import re

        # System labels that don't need resolution (Gmail understands them as-is)
        SYSTEM_LABELS = {
            "inbox",
            "sent",
            "draft",
            "drafts",
            "trash",
            "spam",
            "starred",
            "important",
            "unread",
            "read",
            "category_personal",
            "category_social",
            "category_promotions",
            "category_updates",
            "category_forums",
        }

        # Find all label:XXX patterns in query
        label_pattern = re.compile(r"\blabel:(\S+)", re.IGNORECASE)
        matches = label_pattern.findall(query)

        if not matches:
            return query

        # Get labels mapping once
        labels_mapping = await self.list_labels(use_cache=use_cache)

        # Build reverse mappings (case-insensitive):
        # 1. Full name -> id (e.g., "administratif/maison/copro" -> Label_123)
        # 2. Last segment -> id (e.g., "copro" -> Label_123 for "Administratif/Maison/COPRO")
        name_to_id: dict[str, str] = {}
        last_segment_to_id: dict[str, str] = {}

        for label_id, name in labels_mapping.items():
            name_lower = name.lower()
            name_to_id[name_lower] = label_id

            # Extract last segment for hierarchical labels
            # e.g., "COPRO" from "Administratif/Maison/COPRO"
            if "/" in name:
                last_segment = name.split("/")[-1].lower()
                # Only store if not ambiguous (first match wins)
                if last_segment not in last_segment_to_id:
                    last_segment_to_id[last_segment] = label_id

        # Replace each label name with its ID if needed
        resolved_query = query
        for label_name in matches:
            # Skip system labels
            if label_name.lower() in SYSTEM_LABELS:
                continue

            # Check if it's already an ID (starts with Label_)
            if label_name.startswith("Label_"):
                continue

            # Lookup the label ID:
            # 1. First try exact match (full path)
            # 2. Then try last segment match (for hierarchical labels)
            label_name_lower = label_name.lower()
            label_id = name_to_id.get(label_name_lower)
            matched_by_segment = False

            if not label_id:
                # Try matching by last segment
                # e.g., "COPRO" matches "Administratif/Maison/COPRO"
                label_id = last_segment_to_id.get(label_name_lower)
                if label_id:
                    matched_by_segment = True

            if label_id:
                # Get the full label name (Gmail search uses names, not IDs)
                full_label_name = labels_mapping.get(label_id, label_name)

                # Replace label:NAME with label:FULL_NAME (case-insensitive)
                # Gmail's q parameter expects label names, not IDs
                # e.g., "label:COPRO" → "label:Administratif/Maison/COPRO"
                resolved_query = re.sub(
                    rf"\blabel:{re.escape(label_name)}\b",
                    f"label:{full_label_name}",
                    resolved_query,
                    flags=re.IGNORECASE,
                )
                logger.debug(
                    "gmail_label_resolved",
                    user_id=str(self.user_id),
                    search_term=label_name,
                    full_label_name=full_label_name,
                    label_id=label_id,
                    matched_by_segment=matched_by_segment,
                )
            else:
                logger.warning(
                    "gmail_label_not_found",
                    user_id=str(self.user_id),
                    label_name=label_name,
                    available_labels=list(name_to_id.keys())[:10],  # First 10 for debug
                )

        return resolved_query

    # ========================================================================
    # LABELS CRUD OPERATIONS
    # ========================================================================

    # Gmail system labels that cannot be modified/deleted
    GMAIL_SYSTEM_LABELS: frozenset[str] = frozenset(
        [
            "INBOX",
            "SENT",
            "DRAFT",
            "TRASH",
            "SPAM",
            "STARRED",
            "IMPORTANT",
            "UNREAD",
            "CATEGORY_PERSONAL",
            "CATEGORY_SOCIAL",
            "CATEGORY_PROMOTIONS",
            "CATEGORY_UPDATES",
            "CATEGORY_FORUMS",
        ]
    )

    async def get_label(
        self,
        label_id: str,
    ) -> dict[str, Any] | None:
        """
        Get detailed information about a specific label.

        Args:
            label_id: Gmail label ID (e.g., "Label_12345678")

        Returns:
            Label details dict or None if not found:
            {
                "id": "Label_12345678",
                "name": "pro/capge/2024",
                "type": "user",
                "messagesTotal": 42,
                "messagesUnread": 5,
            }
        """
        try:
            response = await self._make_request("GET", f"/users/me/labels/{label_id}")
            logger.debug(
                "gmail_label_fetched",
                user_id=str(self.user_id),
                label_id=label_id,
                label_name=response.get("name"),
            )
            return response
        except Exception as e:
            logger.warning(
                "gmail_label_fetch_failed",
                user_id=str(self.user_id),
                label_id=label_id,
                error=str(e),
            )
            return None

    async def list_labels_full(
        self,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        List all Gmail labels with full details.

        Unlike list_labels() which returns a mapping, this returns full label objects
        including type, visibility settings, and color info.

        Args:
            use_cache: Use Redis cache (default True)

        Returns:
            List of label objects:
            [
                {"id": "INBOX", "name": "INBOX", "type": "system"},
                {"id": "Label_123", "name": "pro/capge", "type": "user"},
            ]
        """
        cache_key = f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{self.user_id}:full"

        # Try cache first
        if use_cache:
            redis_client = await get_redis_cache()
            cached_data_raw = await redis_client.get(cache_key)
            if cached_data_raw:
                cached_data = json.loads(cached_data_raw)
                logger.debug(
                    "gmail_labels_full_cache_hit",
                    user_id=str(self.user_id),
                    labels_count=len(cached_data),
                )
                return cached_data

        # Fetch labels from API
        response = await self._make_request("GET", "/users/me/labels")
        labels = response.get("labels", [])

        logger.debug(
            "gmail_labels_full_fetched",
            user_id=str(self.user_id),
            labels_count=len(labels),
        )

        # Cache result
        if use_cache:
            redis_client = await get_redis_cache()
            await redis_client.setex(
                cache_key,
                GMAIL_LABELS_CACHE_TTL,
                json.dumps(labels),
            )

        return labels

    async def get_sublabels(
        self,
        parent_name: str,
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """
        Get all sublabels of a parent label.

        Gmail uses "/" to denote hierarchy (e.g., "pro/capge/2024").
        This returns all labels that start with "parent_name/".

        Args:
            parent_name: Full path of parent label (e.g., "pro" or "pro/capge")
            use_cache: Use cached labels

        Returns:
            List of sublabel objects (direct and indirect children)

        Example:
            >>> sublabels = await client.get_sublabels("pro")
            >>> # Returns: [{"name": "pro/capge"}, {"name": "pro/capge/2024"}, ...]
        """
        labels = await self.list_labels_full(use_cache=use_cache)
        prefix = f"{parent_name.lower()}/"

        sublabels = [
            label
            for label in labels
            if label.get("name", "").lower().startswith(prefix)
            and label.get("type") == "user"  # Exclude system labels
        ]

        logger.debug(
            "gmail_sublabels_fetched",
            user_id=str(self.user_id),
            parent_name=parent_name,
            sublabels_count=len(sublabels),
        )

        return sublabels

    async def create_label(
        self,
        name: str,
    ) -> dict[str, Any]:
        """
        Create a new Gmail label.

        Supports hierarchical labels using "/" separator.
        Parent labels are automatically created by Gmail if they don't exist.

        Args:
            name: Label name (e.g., "pro", "pro/capge", "pro/capge/2024")

        Returns:
            Created label object with id, name, type

        Raises:
            Exception: If label creation fails (e.g., already exists)

        Example:
            >>> label = await client.create_label("pro/capge/2024")
            >>> print(label["id"])
            "Label_12345678"
        """
        payload = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }

        response = await self._make_request(
            "POST",
            "/users/me/labels",
            json_data=payload,
        )

        logger.info(
            "gmail_label_created",
            user_id=str(self.user_id),
            label_id=response.get("id"),
            label_name=name,
        )

        # Invalidate cache
        await self._invalidate_labels_cache()

        return response

    async def update_label(
        self,
        label_id: str,
        new_name: str,
    ) -> dict[str, Any]:
        """
        Rename a Gmail label.

        Note: Renaming a parent label may or may not update sublabel paths
        depending on Gmail's behavior. Test empirically.

        Args:
            label_id: Gmail label ID (e.g., "Label_12345678")
            new_name: New label name

        Returns:
            Updated label object

        Raises:
            Exception: If update fails (e.g., label doesn't exist)
        """
        payload = {"name": new_name}

        response = await self._make_request(
            "PATCH",
            f"/users/me/labels/{label_id}",
            json_data=payload,
        )

        logger.info(
            "gmail_label_updated",
            user_id=str(self.user_id),
            label_id=label_id,
            new_name=new_name,
        )

        # Invalidate cache
        await self._invalidate_labels_cache()

        return response

    async def delete_label(
        self,
        label_id: str,
    ) -> bool:
        """
        Delete a Gmail label.

        Warning: Deleting a parent label also deletes all sublabels.
        Gmail handles this automatically.

        Args:
            label_id: Gmail label ID (e.g., "Label_12345678")

        Returns:
            True if deleted successfully

        Raises:
            Exception: If deletion fails
        """
        await self._make_request(
            "DELETE",
            f"/users/me/labels/{label_id}",
        )

        logger.info(
            "gmail_label_deleted",
            user_id=str(self.user_id),
            label_id=label_id,
        )

        # Invalidate cache
        await self._invalidate_labels_cache()

        return True

    async def modify_message_labels(
        self,
        message_id: str,
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Modify labels on a single message.

        Args:
            message_id: Gmail message ID
            add_label_ids: Label IDs to add
            remove_label_ids: Label IDs to remove

        Returns:
            Updated message object

        Example:
            >>> await client.modify_message_labels(
            ...     "msg_123",
            ...     add_label_ids=["Label_456"],
            ...     remove_label_ids=["INBOX"]
            ... )
        """
        payload: dict[str, Any] = {}
        if add_label_ids:
            payload["addLabelIds"] = add_label_ids
        if remove_label_ids:
            payload["removeLabelIds"] = remove_label_ids

        response = await self._make_request(
            "POST",
            f"/users/me/messages/{message_id}/modify",
            json_data=payload,
        )

        logger.info(
            "gmail_message_labels_modified",
            user_id=str(self.user_id),
            message_id=message_id,
            added=add_label_ids,
            removed=remove_label_ids,
        )

        return response

    async def batch_modify_labels(
        self,
        message_ids: list[str],
        add_label_ids: list[str] | None = None,
        remove_label_ids: list[str] | None = None,
    ) -> bool:
        """
        Modify labels on multiple messages in a single API call.

        More efficient than calling modify_message_labels() in a loop.

        Args:
            message_ids: List of Gmail message IDs (max 1000)
            add_label_ids: Label IDs to add to all messages
            remove_label_ids: Label IDs to remove from all messages

        Returns:
            True if successful

        Example:
            >>> await client.batch_modify_labels(
            ...     ["msg_1", "msg_2", "msg_3"],
            ...     add_label_ids=["Label_archive"],
            ...     remove_label_ids=["INBOX"]
            ... )
        """
        payload: dict[str, Any] = {"ids": message_ids}
        if add_label_ids:
            payload["addLabelIds"] = add_label_ids
        if remove_label_ids:
            payload["removeLabelIds"] = remove_label_ids

        await self._make_request(
            "POST",
            "/users/me/messages/batchModify",
            json_data=payload,
        )

        logger.info(
            "gmail_messages_labels_batch_modified",
            user_id=str(self.user_id),
            message_count=len(message_ids),
            added=add_label_ids,
            removed=remove_label_ids,
        )

        return True

    async def get_or_create_label(
        self,
        name: str,
    ) -> dict[str, Any]:
        """
        Get existing label or create it if it doesn't exist.

        Useful for apply_labels with auto_create=True.

        Args:
            name: Label name (full path for hierarchical labels)

        Returns:
            Label object (existing or newly created)
        """
        # Try to find existing label
        labels_mapping = await self.list_labels(use_cache=False)
        name_lower = name.lower()

        for label_id, label_name in labels_mapping.items():
            if label_name.lower() == name_lower:
                # Return existing label
                return {"id": label_id, "name": label_name, "type": "user"}

        # Create new label
        return await self.create_label(name)

    async def resolve_label_with_disambiguation(
        self,
        label_name: str,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Resolve a label name to its ID, with disambiguation support.

        Returns either:
        - A single resolved label if match is unambiguous
        - Multiple candidates if the name is ambiguous

        Args:
            label_name: User-provided label name (can be partial)
            use_cache: Use cached labels

        Returns:
            Dict with resolution result:
            - If unique match: {"resolved": True, "label": {...}}
            - If ambiguous: {"resolved": False, "candidates": [...]}
            - If not found: {"resolved": False, "candidates": []}

        Example:
            >>> result = await client.resolve_label_with_disambiguation("2018")
            >>> if result["resolved"]:
            ...     print(result["label"]["name"])  # "pro/archive/2018"
            >>> else:
            ...     print(result["candidates"])  # Multiple matches
        """
        labels = await self.list_labels_full(use_cache=use_cache)
        label_name_lower = label_name.lower()

        # 1. Try exact match on full path (case-insensitive)
        for label in labels:
            if label.get("type") != "user":
                continue
            if label.get("name", "").lower() == label_name_lower:
                return {"resolved": True, "label": label}

        # 2. Try matching by last segment for hierarchical labels
        candidates = []
        for label in labels:
            if label.get("type") != "user":
                continue
            name = label.get("name", "")
            # Check if last segment matches
            if "/" in name:
                last_segment = name.split("/")[-1].lower()
                if last_segment == label_name_lower:
                    candidates.append(label)
            elif name.lower() == label_name_lower:
                candidates.append(label)

        if len(candidates) == 1:
            return {"resolved": True, "label": candidates[0]}
        elif len(candidates) > 1:
            return {"resolved": False, "candidates": candidates}
        else:
            return {"resolved": False, "candidates": []}

    def is_system_label(self, label_name: str) -> bool:
        """
        Check if a label name is a Gmail system label.

        Args:
            label_name: Label name or ID

        Returns:
            True if it's a system label that cannot be modified
        """
        return label_name.upper() in self.GMAIL_SYSTEM_LABELS

    async def _invalidate_labels_cache(self) -> None:
        """Invalidate all labels caches after modification."""
        redis_client = await get_redis_cache()
        keys_to_delete = [
            f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{self.user_id}",
            f"{REDIS_KEY_GMAIL_LABELS_PREFIX}{self.user_id}:full",
        ]
        for key in keys_to_delete:
            await redis_client.delete(key)
        logger.debug(
            "gmail_labels_cache_invalidated",
            user_id=str(self.user_id),
        )
