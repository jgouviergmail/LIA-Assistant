"""One dashboard page load is one act — signed, short-lived, bound to its context.

Spec 2026-10-21 §5.8 (D2). The progressive dashboard reads its slow sources
in separate requests (``GET /briefing/sections/{name}``) after the initial
response; those requests must still be ONE act of reading — one decision
row, the consultations and the spend under one run id — and must not be
replayed by another account, after the token expired, or into a context that
changed (another language, timezone, local day or hidden set: a section read
across local midnight would mix two days).

The token is ``base64url(act_id.user_id.context_digest.expiry).signature``, the
signature an HMAC-SHA256 under the instance's secret key with a domain
separator (the ``connectors/media_attribution`` precedent). A foreign or
malformed token is never honoured; the caller then gets a fresh run of its own.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import uuid
from datetime import date, datetime
from typing import Literal, NamedTuple
from uuid import UUID

from src.core.config import settings

#: What a presented token turned out to be.
ActCheck = Literal["valid", "foreign", "expired", "context_changed", "malformed"]

#: Keeps a briefing-act signature from verifying any other signed value.
_DOMAIN = b"lia-briefing-act-v1:"
_SIGNATURE_LENGTH = 32
_FIELDS = 4


class ActVerdict(NamedTuple):
    """A verified token: what it is, and the act it names when it is valid."""

    check: ActCheck
    act_id: str | None


def new_act_id() -> str:
    """A fresh act id — the run id the act's reads and spend file under."""
    return f"briefing_act_{uuid.uuid4().hex[:16]}"


def briefing_context_digest(
    *, hidden: frozenset[str], language: str, timezone: str, local_day: date
) -> str:
    """The context an act's sections must still be read in.

    Args:
        hidden: The sections the person hid.
        language: The briefing language.
        timezone: The person's IANA timezone.
        local_day: The person's local date when the act started.

    Returns:
        A short digest; any change answers ``context_changed``.
    """
    context = {
        "hidden": sorted(hidden),
        "language": language,
        "timezone": timezone,
        "day": local_day.isoformat(),
    }
    encoded = json.dumps(context, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:32]


def _encode(payload: bytes) -> str:
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _signature(payload: bytes) -> str:
    return hmac.new(
        settings.secret_key.encode("utf-8"), _DOMAIN + payload, hashlib.sha256
    ).hexdigest()[:_SIGNATURE_LENGTH]


def sign_act(*, act_id: str, user_id: UUID, context_digest: str, expires_at: datetime) -> str:
    """The token naming one act for one account in one context until ``expires_at``.

    Args:
        act_id: The act's run id.
        user_id: The account it was issued to.
        context_digest: ``briefing_context_digest`` at issue.
        expires_at: When it stops being honoured (aware).

    Returns:
        The opaque token.
    """
    payload = f"{act_id}.{user_id}.{context_digest}.{int(expires_at.timestamp())}".encode()
    return f"{_encode(payload)}.{_signature(payload)}"


def verify_act(token: str, *, user_id: UUID, context_digest: str, now: datetime) -> ActVerdict:
    """Check a presented token against the caller and the current context.

    Args:
        token: The token the client sent back.
        user_id: The authenticated caller.
        context_digest: The caller's context NOW.
        now: The current instant (aware).

    Returns:
        ``valid`` with the act id, or why it is not honoured.
    """
    encoded, _, signature = token.rpartition(".")
    try:
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    except binascii.Error, ValueError:
        return ActVerdict("malformed", None)
    # One spelling per token: the decoder ignores stray characters and padding bits,
    # so a second encoding of the same payload would otherwise verify too.
    if _encode(payload) != encoded:
        return ActVerdict("malformed", None)
    if not signature or not hmac.compare_digest(signature, _signature(payload)):
        return ActVerdict("malformed", None)
    fields = payload.decode("utf-8", errors="replace").split(".")
    if len(fields) != _FIELDS or not fields[3].isdigit():
        return ActVerdict("malformed", None)
    act_id, owner, digest, expiry = fields
    if owner != str(user_id):
        return ActVerdict("foreign", None)
    if int(expiry) <= int(now.timestamp()):
        return ActVerdict("expired", None)
    if digest != context_digest:
        return ActVerdict("context_changed", None)
    return ActVerdict("valid", act_id)


__all__ = [
    "ActCheck",
    "ActVerdict",
    "briefing_context_digest",
    "new_act_id",
    "sign_act",
    "verify_act",
]
