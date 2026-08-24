"""Session handoff between the system browser and a native shell's WebView.

OAuth cannot run inside a WebView — both engines refuse it with
``disallowed_useragent`` — so a native shell must send the user to the system
browser. The provider then calls back to the API, which would normally set the
session cookie and redirect… into the *browser*, where the WebView cannot see
it. This module bridges that gap.

**Why a code and not the session.** The deep link that brings the user back
travels through the operating system. It cannot be an App Link, because App
Links pin domains at build time and LIA ships **one** app for every self-hosted
server, whose URL the user types at first launch. That leaves a custom scheme —
and a custom scheme can be claimed by any installed application, so the link
must be assumed intercepted.

**What makes an intercepted link useless.** The WebView draws a random verifier
and sends only its SHA-256 (the *challenge*) when the flow starts; the server
stores the challenge, never the verifier. Redeeming the code requires presenting
the verifier, which the interceptor does not have. This is RFC 7636's mechanism,
applied to the handoff rather than to the token exchange (RFC 8252 §8.1
recommends exactly this for native apps).

The code carries **no session**: it names a user and whether a second factor is
still owed. What it can produce is decided server-side, at redemption.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import structlog

from src.core.config import settings
from src.core.constants import (
    NATIVE_HANDOFF_VERIFIER_MAX_LENGTH,
    NATIVE_HANDOFF_VERIFIER_MIN_LENGTH,
    REDIS_KEY_NATIVE_HANDOFF_PREFIX,
    REDIS_KEY_OAUTH_STATE_PREFIX,
)
from src.core.field_names import FIELD_USER_ID
from src.core.single_use_token import SingleUseTokenStore
from src.infrastructure.cache.redis import get_redis_session

logger = structlog.get_logger(__name__)

#: Path component of the deep link. Fixed: the app registers one entry point.
_DEEP_LINK_HOST = "auth-callback"

#: Unreserved base64url alphabet, unpadded (RFC 7636 §4.1 leaves no padding).
_BASE64URL_RE = re.compile(r"^[A-Za-z0-9\-_]+$")


@dataclass(frozen=True, slots=True)
class NativeHandoff:
    """What a redeemed code entitles the caller to.

    Attributes:
        user_id: Account the provider authenticated.
        challenge: SHA-256 of the app's verifier, base64url, unpadded.
        mfa_pending: True when a second factor is still owed, so redemption
            must produce an MFA step rather than a session.
    """

    user_id: str
    challenge: str
    mfa_pending: bool


def _decode(payload: dict[str, Any]) -> NativeHandoff:
    """Rebuild a :class:`NativeHandoff` from its stored mapping.

    Args:
        payload: Mapping read back from Redis.

    Returns:
        The typed payload.

    Raises:
        KeyError: When a required field is absent, which the store reports as
            an unusable code rather than letting a partial handoff through.
    """
    return NativeHandoff(
        user_id=str(payload[FIELD_USER_ID]),
        challenge=str(payload["challenge"]),
        mfa_pending=bool(payload.get("mfa_pending", False)),
    )


_HANDOFF_TOKENS: SingleUseTokenStore[NativeHandoff] = SingleUseTokenStore(
    prefix=REDIS_KEY_NATIVE_HANDOFF_PREFIX,
    decode=_decode,
)


def _is_valid_secret(value: object) -> bool:
    """Whether a value is a well-formed PKCE-shaped secret.

    Args:
        value: Candidate challenge or verifier.

    Returns:
        True when it is an unpadded base64url string within RFC 7636's bounds.
    """
    if not isinstance(value, str):
        return False
    if not (NATIVE_HANDOFF_VERIFIER_MIN_LENGTH <= len(value) <= NATIVE_HANDOFF_VERIFIER_MAX_LENGTH):
        return False
    return bool(_BASE64URL_RE.match(value))


def is_valid_challenge(value: object) -> bool:
    """Whether a challenge may be accepted from a client.

    Validated at the door rather than at redemption: a malformed challenge can
    never match any verifier, so storing one would mint a code that is
    guaranteed to fail minutes later, with nothing to explain why.

    Args:
        value: Candidate challenge, straight off the query string.

    Returns:
        True when the challenge is well-formed.
    """
    return _is_valid_secret(value)


def challenge_for(verifier: str) -> str:
    """Derive the challenge a verifier must match.

    Args:
        verifier: The client's secret.

    Returns:
        Unpadded base64url SHA-256 of the verifier.
    """
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


async def issue_handoff(user_id: str, challenge: str, mfa_pending: bool) -> str:
    """Mint the single-use code the deep link will carry.

    Args:
        user_id: Account the provider authenticated.
        challenge: SHA-256 of the app's verifier, validated by the caller.
        mfa_pending: Whether a second factor is still owed.

    Returns:
        The opaque code.

    Raises:
        ValueError: When the challenge is malformed.
    """
    if not is_valid_challenge(challenge):
        raise ValueError("challenge is not a well-formed base64url PKCE challenge")

    return await _HANDOFF_TOKENS.issue(
        {
            FIELD_USER_ID: user_id,
            "challenge": challenge,
            "mfa_pending": mfa_pending,
        },
        ttl_seconds=settings.native_handoff_ttl_seconds,
    )


async def consume_handoff(code: str, verifier: str) -> NativeHandoff | None:
    """Redeem a code, if and only if the verifier matches its challenge.

    Args:
        code: Opaque code from the deep link.
        verifier: The secret the WebView kept when it started the flow.

    Returns:
        The handoff payload, or ``None`` when the code is unknown, expired,
        already spent, or when the verifier does not match. Every failure looks
        the same to the caller on purpose.

    Note:
        A well-formed but wrong verifier still spends the code. That is a
        deliberate trade: an app that intercepted the deep link can burn a
        legitimate code and force the user to sign in again, but it can never
        use one. The alternative — putting the payload back on a mismatch —
        would give up the atomicity that makes "single use" true, to defend
        against an attacker who already has a hostile application installed.
    """
    if not _is_valid_secret(verifier):
        # Refused before touching Redis: a malformed verifier cannot match
        # anything, and consuming the code here would let a hostile app burn a
        # legitimate one it merely observed.
        return None

    payload = await _HANDOFF_TOKENS.consume(code)
    if payload is None:
        return None

    # Constant-time: the challenge is a public value, but comparing it in
    # variable time is a habit not worth acquiring on an auth path.
    if not secrets.compare_digest(payload.challenge, challenge_for(verifier)):
        logger.warning("native_handoff_verifier_mismatch", user_id=payload.user_id)
        return None

    return payload


def build_native_redirect(code: str | None = None, error: str | None = None) -> str:
    """Build the deep link handing control back to the app.

    Args:
        code: The handoff code, on success.
        error: A provider or flow error, on failure.

    Returns:
        A URL on the configured custom scheme.

    Raises:
        ValueError: When neither ``code`` nor ``error`` is given — a link with
            no outcome would reach the app looking like a success.
    """
    if code is None and error is None:
        raise ValueError("build_native_redirect needs either a code or an error")

    params = {"code": code} if code is not None else {"error": error}
    return f"{settings.native_app_scheme}://{_DEEP_LINK_HOST}?{urlencode(params)}"


#: Key the flow stored its challenge under, inside the OAuth state payload.
NATIVE_CHALLENGE_METADATA_KEY = "native_challenge"


async def peek_native_challenge(state: str) -> str | None:
    """Read the challenge a flow was started with, WITHOUT consuming the state.

    The OAuth state is single-use and the token exchange spends it, so the
    callback has to learn where to send the user *before* that happens. Peeking
    rather than consuming is the same move
    ``_handle_oauth_connector_callback_stateless`` already makes for the user
    id — the state remains available for the PKCE validation that follows.

    Args:
        state: CSRF state token from the provider's redirect.

    Returns:
        The challenge when the flow was started by a native shell, ``None`` for
        a browser flow, an unknown state, or a payload that does not carry a
        well-formed challenge. A malformed value is treated as "not native": it
        can never match a verifier, and a deep link is not somewhere to send a
        user whose sign-in cannot possibly complete.
    """
    if not state:
        return None

    redis = await get_redis_session()
    raw = await redis.get(f"{REDIS_KEY_OAUTH_STATE_PREFIX}{state}")
    if not raw:
        return None

    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except json.JSONDecodeError, AttributeError, TypeError, ValueError:
        return None

    challenge = payload.get(NATIVE_CHALLENGE_METADATA_KEY) if isinstance(payload, dict) else None
    return challenge if is_valid_challenge(challenge) else None
