"""
Apple Push Notification service provider client.

The only route to an iPhone. Apple speaks HTTP/2 exclusively and authenticates
providers with a short-lived ES256 JWT signed by a ``.p8`` key belonging to the
Apple Developer team that owns the bundle identifier — which is why this client
exists at all: a self-hosted deployment cannot reach an app it does not own, so
the published shell's notifications go through the deployment that does (see
``domains/push_relay``).

Two Apple rules shape the token handling and are easy to get wrong in opposite
directions: a provider token older than one hour is refused, and a provider that
mints a fresh token per request is rate-limited. One cached token, renewed on a
window comfortably inside the hour, satisfies both.

A third rule shapes the connection: Apple asks providers to keep it **open**.
One client is held for the object's lifetime rather than opened per
notification — a TLS and HTTP/2 handshake for every push is both slow and
something Apple throttles. It has an owner, and it is closed at shutdown
(``infrastructure/startup/shutdown.py``).

The client is deliberately generic — it sends whatever payload it is given. What
a notification may CONTAIN is a policy question, and it belongs to the caller
that has the context to answer it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import httpx
import jwt
import structlog

from src.core.constants import (
    APNS_PRODUCTION_HOST,
    APNS_PROVIDER_TOKEN_REFRESH_SECONDS,
    APNS_REQUEST_TIMEOUT_SECONDS,
    APNS_SANDBOX_HOST,
)

logger = structlog.get_logger(__name__)

# Apple's reasons meaning the token names a device that no longer exists. Any
# other refusal is about US or about the moment, never about the device.
_DEVICE_GONE_REASONS = frozenset({"Unregistered", "BadDeviceToken"})

# The one refusal a retry can fix, because the fix is entirely on our side.
_EXPIRED_TOKEN_REASON = "ExpiredProviderToken"


class ApnsDeliveryStatus(StrEnum):
    """What Apple's answer means for the caller.

    ``ACCEPTED`` is deliberately not called "delivered": a 200 says Apple took
    custody of the notification, and nothing at all about whether a phone ever
    displayed it.
    """

    ACCEPTED = "accepted"
    DEVICE_GONE = "device_gone"
    REJECTED = "rejected"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class ApnsCredentials:
    """Everything Apple checks before accepting a push.

    Attributes:
        key_pem: Contents of the ``.p8`` signing key, PKCS#8 PEM.
        key_id: The key's 10-character identifier, carried in the JWT header.
        team_id: The Apple Developer team identifier, the JWT's issuer.
        topic: The app's bundle identifier.
        sandbox: Target the development gateway instead of production. A token
            minted against one gateway is meaningless to the other.
    """

    key_pem: str
    key_id: str
    team_id: str
    topic: str
    sandbox: bool = False


@dataclass(frozen=True, slots=True)
class ApnsResult:
    """The verdict on one send, and Apple's own word for it when there was one."""

    status: ApnsDeliveryStatus
    reason: str | None = None


class ApnsClient:
    """Send notifications to Apple, and classify what comes back.

    Example:
        >>> client = ApnsClient(credentials)
        >>> result = await client.send(token, {"aps": {"alert": "Hello"}})
        >>> result.status is ApnsDeliveryStatus.ACCEPTED
        True
    """

    def __init__(
        self,
        credentials: ApnsCredentials,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        """
        Initialize the client.

        Args:
            credentials: The signing key and the identifiers Apple checks.
            transport: Injected transport, for tests. Production leaves this
                unset and gets a real HTTP/2 connection.
            now: Injected clock, for tests.
        """
        self._credentials = credentials
        self._transport = transport
        self._now = now or (lambda: datetime.now(UTC))
        self._token: str | None = None
        self._token_issued_at: datetime | None = None
        self._client: httpx.AsyncClient | None = None

    def _http(self) -> httpx.AsyncClient:
        """Return the long-lived connection, opening it on first use.

        Built lazily rather than in ``__init__`` so constructing the client
        binds nothing to an event loop that may not be the one it will run on.
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                http2=True,
                transport=self._transport,
                timeout=APNS_REQUEST_TIMEOUT_SECONDS,
            )
        return self._client

    async def aclose(self) -> None:
        """Close the connection to Apple.

        Called at shutdown by the owning subsystem. Idempotent: a client that
        never sent anything has nothing to close.
        """
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _host_for(self, sandbox: bool | None) -> str:
        """Pick Apple's gateway for one send.

        The provider token is team-scoped and valid on both gateways, so the
        choice is per request rather than per client — which is what lets one
        relay serve production and development devices without minting two
        tokens and edging closer to Apple's refresh limit.
        """
        use_sandbox = self._credentials.sandbox if sandbox is None else sandbox
        return APNS_SANDBOX_HOST if use_sandbox else APNS_PRODUCTION_HOST

    def _provider_token(self, *, force_renew: bool = False) -> str:
        """Return the cached provider token, signing a new one when it is due.

        Args:
            force_renew: Sign a new token regardless of the cached one's age —
                used when Apple has just declared the cached one expired.

        Returns:
            The bearer value, without its ``bearer `` prefix.
        """
        now = self._now()
        age_ok = (
            self._token_issued_at is not None
            and (now - self._token_issued_at).total_seconds() < APNS_PROVIDER_TOKEN_REFRESH_SECONDS
        )
        if self._token is not None and age_ok and not force_renew:
            return self._token

        self._token = jwt.encode(
            {"iss": self._credentials.team_id, "iat": int(now.timestamp())},
            self._credentials.key_pem,
            algorithm="ES256",
            headers={"kid": self._credentials.key_id},
        )
        self._token_issued_at = now
        return self._token

    async def send(
        self,
        device_token: str,
        payload: dict[str, Any],
        *,
        collapse_id: str | None = None,
        push_type: str = "alert",
        priority: int = 10,
        sandbox: bool | None = None,
    ) -> ApnsResult:
        """
        Send one notification and classify Apple's answer.

        Args:
            device_token: The device token, as the app reported it.
            payload: The full APNs payload, sent verbatim.
            collapse_id: Optional identifier folding repeated notifications into
                a single one on the device.
            push_type: Apple's ``apns-push-type``.
            priority: Apple's ``apns-priority``.
            sandbox: Override the gateway for this send. ``None`` keeps the
                credentials' own setting.

        Returns:
            The verdict, which never raises: a caller deciding what to do with a
            device needs an answer, not an exception to re-classify.
        """
        headers = {
            "authorization": f"bearer {self._provider_token()}",
            "apns-topic": self._credentials.topic,
            "apns-push-type": push_type,
            "apns-priority": str(priority),
        }
        if collapse_id is not None:
            headers["apns-collapse-id"] = collapse_id

        host = self._host_for(sandbox)
        url = f"https://{host}/3/device/{device_token}"
        try:
            client = self._http()
            response = await client.post(url, json=payload, headers=headers)
            if _reason_of(response) == _EXPIRED_TOKEN_REASON:
                headers["authorization"] = f"bearer {self._provider_token(force_renew=True)}"
                response = await client.post(url, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning("apns_transport_failed", error=str(exc), host=host)
            return ApnsResult(status=ApnsDeliveryStatus.UNAVAILABLE, reason=type(exc).__name__)

        return _classify(response)


def _reason_of(response: httpx.Response) -> str | None:
    """Extract Apple's machine-readable reason, if the body carries one."""
    if response.is_success:
        return None
    try:
        body = response.json()
    except ValueError:
        return None
    reason = body.get("reason") if isinstance(body, dict) else None
    return reason if isinstance(reason, str) else None


def _classify(response: httpx.Response) -> ApnsResult:
    """Map one HTTP answer onto the four things it can mean to a caller."""
    if response.is_success:
        return ApnsResult(status=ApnsDeliveryStatus.ACCEPTED)

    reason = _reason_of(response)
    if reason in _DEVICE_GONE_REASONS:
        return ApnsResult(status=ApnsDeliveryStatus.DEVICE_GONE, reason=reason)
    if response.status_code == 429 or response.status_code >= 500:
        return ApnsResult(status=ApnsDeliveryStatus.UNAVAILABLE, reason=reason)
    return ApnsResult(status=ApnsDeliveryStatus.REJECTED, reason=reason)
