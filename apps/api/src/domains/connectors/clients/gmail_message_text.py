"""The text of a Gmail message, read two ways (ADR-287 amendment 2026-11-15).

- :func:`body_text` — what a normalised message carries as its ``body``: a reader reads the
  words its layout shows (``gmail_html_mixin.shown_body``); a mailbox draft, read to be
  edited and written back, the text the person wrote (ADR-344).
- :func:`sender_text` — the text a sender wrote, for what goes back to a mailbox: an original
  quoted under a reply or a forward, a draft read to be edited. ``text/plain`` first.

Pure functions of a payload, moved out of ``google_gmail_client`` on 2026-11-15: the client is
held to its audited size (file-size ratchet), and it keeps one-line aliases for its callers.
"""

from __future__ import annotations

import base64
from typing import Any

import structlog

from src.domains.connectors.clients.gmail_html_mixin import shown_body
from src.domains.connectors.clients.normalizers.html_text import html_to_text

logger = structlog.get_logger(__name__)


def decode_base64url(data: str) -> str:
    """Decode Gmail's base64url encoding (RFC 4648) as UTF-8.

    Args:
        data: Base64url-encoded string, its padding possibly stripped.

    Returns:
        The decoded text, bytes UTF-8 cannot read dropped; "" when ``data`` is not base64.
    """
    data = data.replace("-", "+").replace("_", "/")
    padding = len(data) % 4
    if padding:
        data += "=" * (4 - padding)
    try:
        return base64.b64decode(data).decode("utf-8", errors="ignore")
    except Exception as error:
        logger.warning("base64url_decode_failed", error_type=type(error).__name__)
        return ""


def sender_text(payload: dict[str, Any], max_depth: int = 10, _current_depth: int = 0) -> str:
    """The text a sender wrote, walked through a multipart payload with bounded recursion.

    ``text/plain`` first, then ``text/html`` turned to text, then nested multiparts. Depth is
    bounded (security 2025-12-19): a malformed payload must not overflow the stack, and real
    messages nest two to four levels.

    Args:
        payload: Gmail message payload object.
        max_depth: Maximum recursion depth.
        _current_depth: Internal counter (do not set externally).

    Returns:
        The body text; "" past the depth bound or when the payload carries none.
    """
    if _current_depth >= max_depth:
        return ""
    mime_type = payload.get("mimeType", "")
    body_data = payload.get("body", {}).get("data", "")
    if mime_type == "text/plain" and body_data:
        return decode_base64url(body_data)
    if mime_type == "text/html" and body_data:
        # One HTML → text for every provider (ADR-287).
        return html_to_text(decode_base64url(body_data))
    if not mime_type.startswith("multipart/"):
        return ""
    parts = payload.get("parts", [])
    for wanted in ("text/plain", "text/html"):
        for part in parts:
            if part.get("mimeType") == wanted:
                text = sender_text(part, max_depth, _current_depth + 1)
                if text:
                    return text
    for part in parts:
        if part.get("mimeType", "").startswith("multipart/"):
            text = sender_text(part, max_depth, _current_depth + 1)
            if text:
                return text
    return ""


def body_text(payload: dict[str, Any], *, keep_quoted: bool) -> str:
    """A message's body as text, before its quoted history leaves.

    Args:
        payload: Gmail message payload object.
        keep_quoted: A mailbox draft, read to be edited and written back (ADR-344).

    Returns:
        The words the layout shows for a reader; the text the person wrote for a draft.
    """
    if keep_quoted:
        return sender_text(payload)
    return shown_body(payload)


__all__ = ["body_text", "decode_base64url", "sender_text"]
