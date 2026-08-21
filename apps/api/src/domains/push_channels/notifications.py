"""Defensive parsers for Google push notifications (lot H, 2026-08).

Phase 1 channels notify with ``X-Goog-*`` headers and an empty body; phase 2
(Gmail) notifies through a Pub/Sub push envelope carrying base64 JSON. A
malformed notification degrades to ``None`` (ignored) — the webhook endpoint
answers 200 regardless, never revealing what it knows.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ChannelNotification:
    """One parsed X-Goog-* channel notification (Calendar / Drive)."""

    channel_id: str
    token: str
    resource_id: str
    resource_state: str
    message_number: int


@dataclass(frozen=True)
class GmailPushEvent:
    """One parsed Gmail Pub/Sub push event."""

    email_address: str
    history_id: int


def parse_channel_headers(headers: Mapping[str, str]) -> ChannelNotification | None:
    """Parse the X-Goog-* headers of a channel notification.

    Args:
        headers: Request headers (matched case-insensitively).

    Returns:
        The parsed notification, or None when the mandatory channel id or
        resource state is absent (not a Google channel notification).
    """
    lowered = {key.lower(): value for key, value in headers.items()}
    channel_id = lowered.get("x-goog-channel-id", "")
    resource_state = lowered.get("x-goog-resource-state", "")
    if not channel_id or not resource_state:
        return None
    try:
        message_number = int(lowered.get("x-goog-message-number", "0"))
    except ValueError:
        message_number = 0
    return ChannelNotification(
        channel_id=channel_id,
        token=lowered.get("x-goog-channel-token", ""),
        resource_id=lowered.get("x-goog-resource-id", ""),
        resource_state=resource_state,
        message_number=message_number,
    )


def parse_pubsub_body(body: dict[str, Any]) -> GmailPushEvent | None:
    """Parse a Pub/Sub push envelope into a Gmail event.

    The envelope is ``{"message": {"data": base64(json)}, ...}`` where the
    decoded JSON carries ``emailAddress`` and ``historyId``.

    Args:
        body: The POSTed JSON body.

    Returns:
        The parsed event, or None on any shape/encoding mismatch.
    """
    message = body.get("message")
    if not isinstance(message, dict):
        return None
    raw_data = message.get("data")
    if not isinstance(raw_data, str):
        return None
    try:
        decoded = json.loads(base64.b64decode(raw_data, validate=True))
    except binascii.Error, ValueError, UnicodeDecodeError:
        logger.debug("gmail_push_undecodable_payload")
        return None
    if not isinstance(decoded, dict):
        return None
    email_address = decoded.get("emailAddress")
    if not isinstance(email_address, str) or not email_address:
        return None
    try:
        history_id = int(decoded.get("historyId", 0))
    except TypeError, ValueError:
        return None
    return GmailPushEvent(email_address=email_address, history_id=history_id)
