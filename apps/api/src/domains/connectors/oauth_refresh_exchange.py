"""The one exchange of a refresh token for a fresh access token (audit AC-029).

Every refresh path used to carry its own POST: the legacy connectors, the shared
grants and the Hue bridge each retried and parsed the provider's answer their own
way. One exchange now speaks for all of them, so the refusal that disconnects a
person (``invalid_grant``) has one reading, and a rate limit or an outage is never
mistaken for it. It is the only module allowed to send ``grant_type=refresh_token``
(guarded): a second copy is how two readings came to exist.

The exchange owns no database session and opens none — the refresh door calls it
with no transaction open (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final
from uuid import UUID

import httpx
import structlog
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from src.core.config import settings
from src.core.constants import HUE_REMOTE_TOKEN_ENDPOINT, MICROSOFT_OAUTH_TOKEN_ENDPOINT
from src.core.read_budget import source_http_hooks

logger = structlog.get_logger(__name__)

#: The retry policy, in figures rather than in a decorator's literals: whoever
#: waits for an exchange (a joined refresh, a claim's lifetime) is bounded by it.
OAUTH_REFRESH_ATTEMPTS: Final = 3
OAUTH_REFRESH_WAIT_MIN_SECONDS: Final = 2
OAUTH_REFRESH_WAIT_MAX_SECONDS: Final = 10

#: The lifetime a provider means when it states none (Google's documented hour).
_DEFAULT_EXPIRES_IN_SECONDS: Final = 3599

#: The two refusals that mean the person's consent is gone — and nothing else does.
_REVOKED_ERROR_CODES: Final = frozenset({"invalid_grant", "interaction_required"})
#: Provider error codes logged by name; any other is logged as absent.
_LOGGED_ERROR_CODES: Final = _REVOKED_ERROR_CODES | {"invalid_client"}


class RefreshRefusal(StrEnum):
    """Why an exchange produced no token."""

    #: The provider refused the refresh token itself: the person must reconnect.
    REVOKED = "revoked"
    #: Network, rate limit, outage or any other refusal: retrying later may work.
    TRANSIENT = "transient"
    #: A success whose body carries no usable token.
    UNREADABLE = "unreadable"


class RefreshRefused(Exception):
    """An exchange that produced no token, with the one reading of why.

    Attributes:
        reason: What the refusal means.
        status_code: The provider's HTTP status, when it answered.
    """

    def __init__(self, reason: RefreshRefusal, *, status_code: int | None = None) -> None:
        super().__init__(f"refresh token exchange refused ({reason.value}, status={status_code})")
        self.reason = reason
        self.status_code = status_code


@dataclass(frozen=True, slots=True)
class TokenEndpoint:
    """Where and how a provider exchanges a refresh token.

    Attributes:
        url: The token endpoint.
        client_id: This deployment's OAuth client.
        client_secret: Its secret.
        sends_scope: The provider requires the scopes again (Microsoft does).
        basic_auth: The client authenticates with HTTP Basic, not in the form (Hue).
    """

    url: str
    client_id: str
    client_secret: str
    sends_scope: bool
    basic_auth: bool


@dataclass(frozen=True, slots=True)
class RefreshedToken:
    """What a successful exchange produced.

    Attributes:
        access_token: The fresh access token.
        refresh_token: The rotated refresh token, or the one sent when the provider
            kept it.
        expires_at: When the access token expires.
        reported_scopes: The scopes the provider reported; empty when it reported none.
    """

    access_token: str
    refresh_token: str
    expires_at: datetime
    reported_scopes: frozenset[str]


def oauth_endpoint(provider: str) -> TokenEndpoint:
    """The token endpoint of an OAuth account provider.

    Args:
        provider: ``google`` or ``microsoft``.

    Returns:
        The endpoint, with this deployment's client.

    Raises:
        ValueError: The provider has no refresh endpoint here.
    """
    if provider == "google":
        return TokenEndpoint(
            url="https://oauth2.googleapis.com/token",
            client_id=settings.google_client_id,
            client_secret=settings.google_client_secret,
            sends_scope=False,
            basic_auth=False,
        )
    if provider == "microsoft":
        return TokenEndpoint(
            url=MICROSOFT_OAUTH_TOKEN_ENDPOINT.format(tenant=settings.microsoft_tenant_id),
            client_id=settings.microsoft_client_id,
            client_secret=settings.microsoft_client_secret,
            sends_scope=True,
            basic_auth=False,
        )
    raise ValueError("Unsupported OAuth refresh provider")


def hue_remote_endpoint() -> TokenEndpoint:
    """The Philips Hue remote token endpoint, authenticated with HTTP Basic."""
    return TokenEndpoint(
        url=HUE_REMOTE_TOKEN_ENDPOINT,
        client_id=settings.hue_remote_client_id,
        client_secret=settings.hue_remote_client_secret,
        sends_scope=False,
        basic_auth=True,
    )


def worst_case_refresh_seconds() -> float:
    """How long one exchange may take, every attempt and every wait included.

    Returns:
        The bound a waiter or a claim's lifetime must cover.
    """
    # tenacity's exponential wait after attempt n: 2 ** (n - 1), held to [min, max].
    waits = sum(
        min(
            max(OAUTH_REFRESH_WAIT_MIN_SECONDS, 1 << (attempt - 1)),
            OAUTH_REFRESH_WAIT_MAX_SECONDS,
        )
        for attempt in range(1, OAUTH_REFRESH_ATTEMPTS)
    )
    return OAUTH_REFRESH_ATTEMPTS * settings.http_timeout_oauth + waits


async def exchange_refresh_token(
    endpoint: TokenEndpoint,
    *,
    refresh_token: str,
    scopes: Sequence[str],
    owner_id: UUID | None,
) -> RefreshedToken:
    """Exchange a refresh token, retrying an outage, and read the answer once.

    Args:
        endpoint: The provider's token endpoint.
        refresh_token: The refresh token to exchange.
        scopes: The scopes to request again, for an endpoint that requires them.
        owner_id: The account the call serves, for its read budget.

    Returns:
        The fresh token.

    Raises:
        RefreshRefused: The provider produced no usable token, with why.
    """
    form = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    if not endpoint.basic_auth:
        form |= {"client_id": endpoint.client_id, "client_secret": endpoint.client_secret}
    if endpoint.sends_scope and scopes:
        form["scope"] = " ".join(scopes)
    try:
        response = await _post_with_retries(endpoint, form, owner_id)
    except (httpx.RequestError, httpx.HTTPStatusError) as error:
        logger.error("oauth_token_refresh_network_failure", error_type=type(error).__name__)
        raise RefreshRefused(RefreshRefusal.TRANSIENT) from None
    if response.status_code != 200:
        raise _refusal(response)
    return _read_success(response, refresh_token)


def _retry_wait() -> wait_base:
    """The wait between two attempts (replaced by ``wait_none`` in tests)."""
    return wait_exponential(
        multiplier=1, min=OAUTH_REFRESH_WAIT_MIN_SECONDS, max=OAUTH_REFRESH_WAIT_MAX_SECONDS
    )


async def _post_with_retries(
    endpoint: TokenEndpoint, form: dict[str, str], owner_id: UUID | None
) -> httpx.Response:
    """POST the form, retrying a network failure, a rate limit and an outage."""
    retrying = AsyncRetrying(
        retry=retry_if_exception_type((httpx.RequestError, httpx.HTTPStatusError)),
        stop=stop_after_attempt(OAUTH_REFRESH_ATTEMPTS),
        wait=_retry_wait(),
        reraise=True,
    )
    response: httpx.Response = await retrying(_post_once, endpoint, form, owner_id)
    return response


async def _post_once(
    endpoint: TokenEndpoint, form: dict[str, str], owner_id: UUID | None
) -> httpx.Response:
    """One attempt; a rate limit or an outage raises so that it is retried."""
    auth = httpx.BasicAuth(endpoint.client_id, endpoint.client_secret)
    async with httpx.AsyncClient(
        auth=auth if endpoint.basic_auth else None,
        event_hooks=source_http_hooks(owner_id),
        timeout=settings.http_timeout_oauth,
        follow_redirects=False,
    ) as client:
        response = await client.post(endpoint.url, data=form)
    if response.status_code == 429 or response.status_code >= 500:
        response.raise_for_status()
    return response


def _refusal(response: httpx.Response) -> RefreshRefused:
    """Read a non-200 answer: a revoked grant, or something worth retrying later."""
    error_code = _error_code(response)
    logger.error(
        "oauth_token_refresh_rejected",
        status_code=response.status_code,
        error_code=error_code if error_code in _LOGGED_ERROR_CODES else None,
    )
    reason = (
        RefreshRefusal.REVOKED if error_code in _REVOKED_ERROR_CODES else RefreshRefusal.TRANSIENT
    )
    return RefreshRefused(reason, status_code=response.status_code)


def _error_code(response: httpx.Response) -> str:
    try:
        payload: Any = response.json()
    except ValueError:
        return ""
    return str(payload.get("error", "")) if isinstance(payload, dict) else ""


def _read_success(response: httpx.Response, sent_refresh_token: str) -> RefreshedToken:
    """Read a 200 answer, or refuse it as unreadable — never half of it."""
    try:
        payload: Any = response.json()
    except ValueError:
        raise RefreshRefused(RefreshRefusal.UNREADABLE, status_code=200) from None
    if not isinstance(payload, dict):
        raise RefreshRefused(RefreshRefusal.UNREADABLE, status_code=200)
    access_token = payload.get("access_token")
    expires_in = payload.get("expires_in", _DEFAULT_EXPIRES_IN_SECONDS)
    refresh_token = payload.get("refresh_token") or sent_refresh_token
    scope = payload.get("scope", "")
    if (
        not isinstance(access_token, str)
        or not access_token
        or type(expires_in) is not int
        or expires_in <= 0
        or not isinstance(refresh_token, str)
        or not isinstance(scope, str)
    ):
        raise RefreshRefused(RefreshRefusal.UNREADABLE, status_code=200)
    return RefreshedToken(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=datetime.now(UTC) + timedelta(seconds=expires_in),
        reported_scopes=frozenset(scope.split()),
    )
