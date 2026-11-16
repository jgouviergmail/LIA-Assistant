"""Client for an ntfy server: one publication, one closed outcome (ADR-391).

LIA publishes as JSON to the server's root (ntfy's « publish as JSON »): the topic travels in the
body, never in a URL a proxy logs, and accented titles need no header encoding.

Two roads, never mixed:

- :meth:`NtfyClient.publish_trusted` reaches the INSTANCE server the operator declared, as
  written — it may be private (``http://ntfy:80`` beside the API);
- :meth:`NtfyClient.publish_checked` reaches a server a PERSON typed: validated, then connected to
  the address the check saw (ADR-326), so a name resolving inside is refused before anything
  leaves. A redirect is never followed: ntfy answers a publication, it does not send LIA away.

The answer is read as one :class:`NtfyOutcome`. Only an outcome after which nothing left may be
tried again (:data:`RETRYABLE_OUTCOMES`): a request that left and got no answer may have been
delivered, so it is ``NO_ANSWER`` and never tried again (ADR-221).
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Final

import httpx
import structlog

from src.infrastructure.utils.retry_after import delivery_retry_delay
from src.infrastructure.utils.url_validation import pinned_stream, url_host, validate_url

logger = structlog.get_logger(__name__)


class NtfyOutcome(StrEnum):
    """How one publication ended — the vocabulary every reader shares."""

    SENT = "sent"
    AUTH_REFUSED = "auth_refused"
    NOT_FOUND = "not_found"
    TOO_LARGE = "too_large"
    RATE_LIMITED = "rate_limited"
    REFUSED = "refused"
    SERVER_ERROR = "server_error"
    UNREACHABLE = "unreachable"
    NO_ANSWER = "no_answer"
    URL_REFUSED = "url_refused"
    NOT_CONFIGURED = "not_configured"


#: Outcomes after which nothing reached a device, so trying again cannot show it twice.
RETRYABLE_OUTCOMES: Final = frozenset(
    {NtfyOutcome.RATE_LIMITED, NtfyOutcome.SERVER_ERROR, NtfyOutcome.UNREACHABLE}
)

#: Transport failures that happen before the request leaves: nothing was sent.
_NEVER_SENT = (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout)


def outcome_of_status(status: int) -> NtfyOutcome:
    """The outcome an HTTP status names.

    Args:
        status: The server's status code.

    Returns:
        ``SENT`` for a 2xx; a refusal otherwise, a redirect included.
    """
    if 200 <= status < 300:
        return NtfyOutcome.SENT
    if status in (401, 403):
        return NtfyOutcome.AUTH_REFUSED
    if status == 404:
        return NtfyOutcome.NOT_FOUND
    if status == 413:
        return NtfyOutcome.TOO_LARGE
    if status == 429:
        return NtfyOutcome.RATE_LIMITED
    if status >= 500:
        return NtfyOutcome.SERVER_ERROR
    return NtfyOutcome.REFUSED


@dataclass(frozen=True, slots=True)
class NtfyPublishResult:
    """What one publication achieved.

    Attributes:
        outcome: How it ended.
        retry_after_seconds: For ``RATE_LIMITED`` alone, the wait before trying again,
            bounded as every delivery outbox bounds it; None otherwise.
    """

    outcome: NtfyOutcome
    retry_after_seconds: int | None = None


def _headers(token: str | None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _root(base_url: str) -> str:
    """ntfy's root, where a JSON publication goes."""
    return base_url.rstrip("/") + "/"


def _encode(publication: dict[str, Any]) -> bytes:
    """One encoding for both roads: UTF-8 JSON, accents as they are."""
    return json.dumps(publication, ensure_ascii=False).encode("utf-8")


def _read(response: httpx.Response) -> NtfyPublishResult:
    """The outcome a status names; a « too many » answer also says when to come back."""
    outcome = outcome_of_status(response.status_code)
    if outcome is not NtfyOutcome.RATE_LIMITED:
        return NtfyPublishResult(outcome)
    return NtfyPublishResult(outcome, delivery_retry_delay(response.headers.get("retry-after")))


def _transport_failure(error: httpx.TransportError) -> NtfyPublishResult:
    """Unreachable when nothing left; no answer when the request may have been delivered."""
    if isinstance(error, _NEVER_SENT):
        return NtfyPublishResult(NtfyOutcome.UNREACHABLE)
    logger.info("ntfy_publication_unanswered", error_type=type(error).__name__)
    return NtfyPublishResult(NtfyOutcome.NO_ANSWER)


class NtfyClient:
    """Publish one notification to an ntfy server."""

    def __init__(
        self,
        *,
        timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
        resolver: Callable[[str], list[str]] | None = None,
    ) -> None:
        """Initialize the client.

        Args:
            timeout: Per-request timeout in seconds.
            transport: Injected transport, for tests.
            resolver: Injected name resolver for the checked road, for tests.
        """
        self._timeout = timeout
        self._transport = transport
        self._resolver = resolver

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self._timeout, transport=self._transport, follow_redirects=False
        )

    async def publish_trusted(
        self, base_url: str, publication: dict[str, Any], *, token: str | None
    ) -> NtfyPublishResult:
        """Publish to the instance server the operator declared, as written.

        Args:
            base_url: The server's address, as configured.
            publication: The JSON publication.
            token: The operator's access token, or None.

        Returns:
            The outcome.
        """
        try:
            async with self._client() as client:
                response = await client.post(
                    _root(base_url), content=_encode(publication), headers=_headers(token)
                )
        except httpx.TransportError as error:
            return _transport_failure(error)
        return _read(response)

    async def publish_checked(
        self, base_url: str, publication: dict[str, Any], *, token: str | None
    ) -> NtfyPublishResult:
        """Publish to a server a person typed, on the address its check saw.

        Args:
            base_url: The server's address, as the person wrote it.
            publication: The JSON publication.
            token: The person's access token, or None.

        Returns:
            The outcome; ``URL_REFUSED`` when the check refused the address.
        """
        verdict = await validate_url(_root(base_url), dns_resolver=self._resolver)
        if not verdict.valid:
            logger.info("ntfy_server_refused", url_host=url_host(base_url))
            return NtfyPublishResult(NtfyOutcome.URL_REFUSED)
        try:
            async with (
                self._client() as client,
                pinned_stream(
                    client, "POST", verdict, headers=_headers(token), content=_encode(publication)
                ) as response,
            ):
                return _read(response)
        except httpx.TransportError as error:
            return _transport_failure(error)


__all__ = [
    "RETRYABLE_OUTCOMES",
    "NtfyClient",
    "NtfyOutcome",
    "NtfyPublishResult",
    "outcome_of_status",
]
