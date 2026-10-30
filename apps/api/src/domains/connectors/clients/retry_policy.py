"""Which failed connector request may be sent again, and under which identity (S1).

Measured on 2026-10-28 with the real ``GoogleCalendarClient.create_event`` against a
server that creates the event and then answers after the read timeout: the request
loop sent the POST three times and made three events, then reported a failure. The
same resend existed in the Microsoft paging loop and in Apple's retry loop.

The rule follows the libraries (``httpcore`` retries only a connection that never
opened, ``urllib3`` leaves POST out of its retries): a request is sent again when it
cannot repeat an act — its method is replay-safe, its caller declares it so, or it
never left (``request_outcome.never_reached_the_server``). PATCH counts as replay-safe
because both providers apply it as a merge of the fields it names (Google's patch
semantics, Graph's JSON merge patch): applied twice, the resource ends the same.

A create that must survive a lost answer carries the provider's own idempotency,
derived from the effect register's key (ADR-263) by :func:`provider_idempotency_id`
— a Graph ``transactionId``, a CalDAV ``uid``, a Google event ``id`` — and is
therefore resent like a replay-safe request. Google refuses an id it already holds,
live or deleted, with a 409 (measured on a real calendar, 2026-10-29), and the
client then reads the event back: the same measurement found it still being written
when read at once, so the read is repeated a bounded number of times.
"""

from __future__ import annotations

import base64
import hashlib
import math
import uuid
from typing import Literal

import httpx

from src.infrastructure.utils.request_outcome import never_reached_the_server

ProviderName = Literal["google", "microsoft", "apple"]

#: How many times a connector request is attempted at most (the request loops' default).
CONNECTOR_REQUEST_ATTEMPTS = 3

#: How many times a create that may have happened is read back, ``backoff_seconds``
#: apart, while the provider answers « not found »: measured on Google, an event whose
#: create answer was lost read 404 at once and was there three seconds later.
CREATE_SETTLE_READS = 3

#: Methods whose repetition leaves the resource as one request would (PATCH: see above).
_REPLAY_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE", "PATCH"})

#: Namespace of the UUIDs derived for Graph and CalDAV (fixed: a derived id must not move).
_IDEMPOTENCY_NAMESPACE = uuid.UUID("6f1d3c0e-2b8a-5e47-9c51-3a7d0b9e4f21")


def may_resend(method: str, error: httpx.RequestError, *, idempotent: bool | None = None) -> bool:
    """Whether a request that failed in transport may be sent again.

    Args:
        method: The HTTP method of the request.
        error: The transport failure.
        idempotent: The caller's declaration — True for a POST that is a read or
            whose effect cannot repeat; None lets the method decide.

    Returns:
        True when the repetition cannot repeat an act, or the request never left.
    """
    replay_safe = method.upper() in _REPLAY_SAFE_METHODS if idempotent is None else idempotent
    return replay_safe or never_reached_the_server(error)


def backoff_seconds(attempt: int) -> float:
    """The wait before the attempt after ``attempt`` (0-indexed): 1 s, 2 s, 4 s…"""
    return float(2**attempt)


def worst_request_seconds(timeout: httpx.Timeout) -> float:
    """The longest one request can take through a connector loop under ``timeout``.

    Every attempt waits its whole connect and read budgets, with the backoff
    between attempts — the bound a caller sizing a deadline around it must assume.
    The pool and write budgets are left out: a loop sends its attempts one at a time
    on the client it owns, and a read writes its headers alone.

    Args:
        timeout: The per-call budget the request runs under.

    Returns:
        Seconds; infinite when either budget is unbounded (``None``).
    """
    if timeout.connect is None or timeout.read is None:
        return math.inf
    per_attempt = timeout.connect + timeout.read
    backoffs = sum(backoff_seconds(attempt) for attempt in range(CONNECTOR_REQUEST_ATTEMPTS - 1))
    return CONNECTOR_REQUEST_ATTEMPTS * per_attempt + backoffs


def provider_idempotency_id(idempotency_key: str, provider: ProviderName) -> str:
    """The provider-side identity of one act, derived from the effect's key.

    Args:
        idempotency_key: The effect register's key of the act (``draft:<id>``…),
            or a key the client minted for one call.
        provider: Whose alphabet the identity is written in.

    Returns:
        Google: base32hex (``[0-9a-v]``, 52 characters), the event id alphabet.
        Microsoft and Apple: a UUID, for a Graph ``transactionId`` or a CalDAV ``uid``.
    """
    if provider == "google":
        digest = hashlib.sha256(f"google:{idempotency_key}".encode()).digest()
        return base64.b32hexencode(digest).decode("ascii").rstrip("=").lower()
    return str(uuid.uuid5(_IDEMPOTENCY_NAMESPACE, f"{provider}:{idempotency_key}"))
