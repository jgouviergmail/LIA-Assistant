"""
The relay's handle: an authenticated ciphertext, not a database row.

A handle carries the device token it stands for, sealed with the relay's own
key. That single decision removes the entire storage design — no table mapping
handles to devices, no cleanup job, no dataset to leak, and nothing for an
operator to read. The relay learns a device token only for the instant it takes
to send one notification.

The key is the relay's alone, deliberately separate from the application's
``fernet_key``: rotating it invalidates every handle in circulation at once —
a panic button that must not also force re-encrypting every connector token.

Fernet supplies what the design needs and no more: authentication (a tampered
handle is not readable), randomised ciphertext (two seals of one device differ,
so handles held by two servers cannot be correlated) and an embedded timestamp
(handles expire; the shell re-registers on every launch, so expiry is
self-healing).
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import timedelta

import structlog
from cryptography.fernet import Fernet, InvalidToken

from src.core.constants import SUPPORTED_LANGUAGES
from src.core.i18n_types import DEFAULT_LANGUAGE

logger = structlog.get_logger(__name__)

_TOKEN_FIELD = "t"
_SANDBOX_FIELD = "s"
_LANGUAGE_FIELD = "l"


@dataclass(frozen=True, slots=True)
class SealedDevice:
    """What a readable handle turns out to name."""

    device_token: str
    sandbox: bool
    language: str = DEFAULT_LANGUAGE


def seal_device(
    device_token: str,
    *,
    sandbox: bool,
    key: str,
    language: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Seal a device token into a handle safe to hand to a third-party server.

    Args:
        device_token: The APNs device token, as the shell reported it.
        sandbox: Whether the token belongs to Apple's development gateway.
        key: The relay's Fernet seal key.
        language: Language the generic wake text is written in. Sealed here
            rather than passed at wake time so a calling server never has to
            tell the relay anything about the user it is waking.

    Returns:
        An opaque handle. Holding it permits waking that device and nothing
        else — it names no user, no server and no content.
    """
    payload = json.dumps(
        {
            _TOKEN_FIELD: device_token,
            _SANDBOX_FIELD: sandbox,
            _LANGUAGE_FIELD: language,
        }
    )
    return Fernet(key.encode()).encrypt(payload.encode()).decode()


def unseal_handle(
    handle: str,
    *,
    key: str,
    max_age: timedelta | None = None,
    now: float | None = None,
) -> SealedDevice | None:
    """
    Read a handle, or refuse it.

    Args:
        handle: The handle presented by a calling server.
        key: The relay's Fernet seal key.
        max_age: Reject handles sealed longer ago than this.
        now: Unix timestamp to measure that age against; the current time by
            default. Injected rather than read so the window is testable at its
            boundary — Fernet compares whole seconds, which makes a zero-width
            window pass for the second it was created in.

    Returns:
        The device the handle names, or ``None`` for anything we did not issue,
        cannot read, or issued too long ago.

        Every failure collapses to ``None`` on purpose: a caller must not be
        able to tell a forged handle from an expired one from a handle whose
        device is gone. Nor should a misconfigured seal key surface as a 500
        that reads like the caller's mistake.
    """
    try:
        cipher = Fernet(key.encode())
        if max_age is None:
            raw = cipher.decrypt(handle.encode())
        else:
            raw = cipher.decrypt_at_time(
                handle.encode(),
                ttl=int(max_age.total_seconds()),
                current_time=int(now if now is not None else time.time()),
            )
        payload = json.loads(raw)
        device_token = payload[_TOKEN_FIELD]
        sandbox = payload[_SANDBOX_FIELD]
        # Read leniently: a handle sealed before this field existed is still a
        # handle we issued, and refusing it would silence a device for months.
        language = payload.get(_LANGUAGE_FIELD, DEFAULT_LANGUAGE)
    except InvalidToken, ValueError, TypeError, KeyError, AttributeError:
        return None

    if not isinstance(device_token, str) or not isinstance(sandbox, bool):
        return None
    if language not in SUPPORTED_LANGUAGES:
        language = DEFAULT_LANGUAGE
    return SealedDevice(device_token=device_token, sandbox=sandbox, language=language)
