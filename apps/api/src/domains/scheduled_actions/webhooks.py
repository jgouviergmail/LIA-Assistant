"""A signed call starts a routine: keys, secrets, signatures and headers (ADR-386).

Pure functions, no database and no network:

- **an address and its secret** are drawn here, from the system's random source;
- **a signature** is HMAC-SHA256 of the raw body under the routine's secret,
  spelled ``sha256=<hex>`` — the scheme code forges already send, so a forge can
  start a routine with no adapter in between;
- **which headers carry them**: LIA's own first, the forge's spelling second, a
  delivery id that lets a retried call be stored once, and the media type a call
  declares — kept only when the header is a media type and nothing more;
- **what a run is shown** of the calls it serves: the routine's instruction is
  followed by a note naming each call, dated in the routine's zone, its body
  wrapped as another system's words (``wrap_external_content``) and cut at a
  stated bound — a body is what the routine reads, never what it obeys.

The comparison is made in constant time on the decoded digest, so neither the
length nor the content of a wrong signature leaks how close it came.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from functools import cache
from uuid import UUID
from zoneinfo import ZoneInfo

from src.core.config import settings
from src.core.constants import (
    ROUTINE_WEBHOOK_DELIVERY_HEADERS,
    ROUTINE_WEBHOOK_DELIVERY_ID_MAX_LENGTH,
    ROUTINE_WEBHOOK_KEY_BYTES,
    ROUTINE_WEBHOOK_PATH,
    ROUTINE_WEBHOOK_PROMPT_CHARS,
    ROUTINE_WEBHOOK_SECRET_BYTES,
    ROUTINE_WEBHOOK_SIGNATURE_HEADERS,
    ROUTINE_WEBHOOK_SIGNATURE_PREFIX,
)
from src.core.external_content import wrap_external_content
from src.core.prompt_store import parse_prompt_sections, read_prompt_file

#: How the run's note names a call's body in its external-content envelope.
_SOURCE_TYPE = "webhook_call"

#: Length of a SHA-256 digest, in bytes.
_DIGEST_BYTES = hashlib.sha256().digest_size

#: ``type/subtype`` as RFC 6838 names one: a top-level type IANA registers, then a
#: restricted name — 112 characters at most, inside the column that keeps it.
_MEDIA_TYPE = re.compile(
    r"(?:application|audio|example|font|haptics|image|message|model|multipart|text|video)"
    r"/[a-z0-9][a-z0-9!#$&^_.+-]{0,99}"
)


def draw_webhook_key() -> str:
    """A new address key: random, url-safe, unguessable.

    Returns:
        The key, as it appears in the routine's address.
    """
    return secrets.token_urlsafe(ROUTINE_WEBHOOK_KEY_BYTES)


def draw_webhook_secret() -> str:
    """A new HMAC secret: random, url-safe, shown to its owner once.

    Returns:
        The secret, in clear — the caller encrypts it before storing it.
    """
    return secrets.token_urlsafe(ROUTINE_WEBHOOK_SECRET_BYTES)


def routine_webhook_url(key: str) -> str:
    """The address another system calls, as the API publishes it.

    Args:
        key: The routine's address key.

    Returns:
        The absolute URL of ``POST …/hooks/routines/{key}``.
    """
    return f"{settings.api_url}{settings.api_prefix}{ROUTINE_WEBHOOK_PATH}/{key}"


def signature_of(secret: str, body: bytes) -> str:
    """The signature a caller sends for this body.

    Args:
        secret: The routine's secret, in clear.
        body: The raw request body, exactly as sent.

    Returns:
        ``sha256=<hex>``.
    """
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"{ROUTINE_WEBHOOK_SIGNATURE_PREFIX}{digest}"


def signature_matches(secret: str, body: bytes, presented: str | None) -> bool:
    """Whether the presented signature is the body's under this secret.

    Args:
        secret: The routine's secret, in clear.
        body: The raw request body.
        presented: The signature the caller sent, or None.

    Returns:
        True only for ``sha256=`` followed by the exact digest (its hex in any case).
    """
    if not presented or not presented.startswith(ROUTINE_WEBHOOK_SIGNATURE_PREFIX):
        return False
    try:
        claimed = bytes.fromhex(presented[len(ROUTINE_WEBHOOK_SIGNATURE_PREFIX) :])
    except ValueError:
        return False
    if len(claimed) != _DIGEST_BYTES:
        return False
    expected = hmac.new(secret.encode(), body, hashlib.sha256).digest()
    return hmac.compare_digest(claimed, expected)


def presented_signature(headers: Mapping[str, str]) -> str | None:
    """The signature a call carries, read from LIA's header first.

    Args:
        headers: The request's headers, with lowercase names.

    Returns:
        The header's value, or None when the call carries none.
    """
    for name in ROUTINE_WEBHOOK_SIGNATURE_HEADERS:
        value = headers.get(name)
        if value:
            return value.strip()
    return None


def delivery_id_of(headers: Mapping[str, str]) -> str | None:
    """The caller's name for this delivery, when it gives a usable one.

    Args:
        headers: The request's headers, with lowercase names.

    Returns:
        The id, stripped; None when absent, empty, too long or not printable — a
        call with no usable id is simply stored as a new delivery.
    """
    for name in ROUTINE_WEBHOOK_DELIVERY_HEADERS:
        value = (headers.get(name) or "").strip()
        if not value:
            continue
        if len(value) > ROUTINE_WEBHOOK_DELIVERY_ID_MAX_LENGTH or not value.isprintable():
            return None
        return value
    return None


def declared_media_type(headers: Mapping[str, str]) -> str | None:
    """The media type the caller declared: its ``type/subtype`` alone, or None.

    The header is the caller's words — and unlike the body it is not signed —
    while the run's note names the type OUTSIDE the envelope the body is read in.
    Only what can be nothing but a media type is kept: a registered top-level
    type and a restricted name (RFC 6838), lowercased, parameters dropped.

    Args:
        headers: The request's headers, with lowercase names.

    Returns:
        The media type; None when absent or when the header is anything else — the
        call is then stored, and shown, with no declared type.
    """
    declared = (headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    return declared if _MEDIA_TYPE.fullmatch(declared) else None


@dataclass(frozen=True, slots=True)
class WaitingCall:
    """One accepted call a run is about to serve, its body already decrypted.

    Attributes:
        id: The delivery row.
        delivery_id: The sender's own id for it, when it gave one.
        received_at: When it was accepted (UTC).
        content_type: The media type the sender declared, if any.
        body_bytes: The body's size as received.
        text: The body read as text; ``None`` when it could not be read back.
    """

    id: UUID
    delivery_id: str | None
    received_at: datetime
    content_type: str | None
    body_bytes: int
    text: str | None


@cache
def _lines() -> dict[str, str]:
    """The note's one-line templates (``routine_webhook_lines``), read once."""
    return dict(parse_prompt_sections(read_prompt_file("routine_webhook_lines"), 2))


def calls_note(calls: Sequence[WaitingCall], *, timezone: str) -> str:
    """What a run is shown, after the routine's instruction, of the calls it serves.

    Args:
        calls: The calls the run serves, oldest first.
        timezone: The routine's zone: each call is dated as its owner reads time.

    Returns:
        A header, then each call — dated, sized, its body wrapped as external
        content and cut at ``ROUTINE_WEBHOOK_PROMPT_CHARS`` with the cut stated.
    """
    lines = _lines()
    zone = ZoneInfo(timezone)
    parts = [lines["header"].format(count=len(calls))]
    for call in calls:
        received_at = call.received_at.astimezone(zone).isoformat(timespec="seconds")
        if call.content_type:
            heading = lines["call"].format(
                received_at=received_at, size=call.body_bytes, content_type=call.content_type
            )
        else:
            heading = lines["call_untyped"].format(received_at=received_at, size=call.body_bytes)
        parts.append(heading)
        parts.append(_body(call, lines))
    return "\n\n".join(parts)


def _body(call: WaitingCall, lines: Mapping[str, str]) -> str:
    """One call's body as the run reads it: said when absent, wrapped, cut with a word."""
    if call.text is None:
        return lines["unreadable"]
    if not call.text:
        return lines["empty"]
    shown = call.text[:ROUTINE_WEBHOOK_PROMPT_CHARS]
    wrapped = wrap_external_content(
        shown, source_url=f"routine-webhook:{call.delivery_id or call.id}", source_type=_SOURCE_TYPE
    )
    if len(call.text) <= ROUTINE_WEBHOOK_PROMPT_CHARS:
        return wrapped
    cut = lines["cut"].format(shown=len(shown), total=len(call.text))
    return f"{wrapped}\n{cut}"


__all__ = [
    "WaitingCall",
    "routine_webhook_url",
    "calls_note",
    "declared_media_type",
    "delivery_id_of",
    "draw_webhook_key",
    "draw_webhook_secret",
    "presented_signature",
    "signature_matches",
    "signature_of",
]
