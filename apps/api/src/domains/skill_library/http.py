"""One outgoing request of the skill library, checked at every hop (ADR-327, ADR-326).

Every address the library reads — the portal, its audit service, GitHub's API
and raw files — goes through :func:`fetch`: the URL is validated, the request
connects to the address the check saw (``pinned_stream``), a redirect is a new
URL validated before it is contacted, the whole exchange runs under ONE total
deadline and the body is read under a byte ceiling. A failure is an OUTCOME,
never an exception: the caller decides what it tells the person.

A credential travels to the host it was given for and nowhere else: a
redirect to another host drops the ``Authorization`` header.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import urljoin, urlparse

import httpx
import structlog

from src.core.config import settings
from src.core.constants import SKILL_LIBRARY_MAX_REDIRECTS, SKILL_LIBRARY_RESPONSE_MAX_BYTES
from src.domains.agents.web_fetch.url_validator import pinned_stream, validate_url
from src.infrastructure.utils.bounded_read import BodyTooLargeError, read_bounded

logger = structlog.get_logger(__name__)

#: What the library says it is, to the hosts it reads.
USER_AGENT: Final = "LIA-skill-library"
_AUTHORIZATION: Final = "authorization"


class FetchOutcome(StrEnum):
    """How one request ended."""

    OK = "ok"
    NOT_FOUND = "not_found"
    RATE_LIMITED = "rate_limited"
    BLOCKED = "blocked"
    TOO_LARGE = "too_large"
    HTTP_ERROR = "http_error"
    UNREACHABLE = "unreachable"


@dataclass(frozen=True)
class Fetched:
    """What one request brought back.

    Attributes:
        outcome: How it ended.
        status: The last HTTP status seen (0 when none).
        body: The body, on ``OK`` only.
        reset_at: When a rate limit lifts (epoch seconds), if the host said.
    """

    outcome: FetchOutcome
    status: int = 0
    body: bytes = b""
    reset_at: int | None = None


def _rate_limited(response: httpx.Response) -> bool:
    """GitHub answers 403 or 429 with no request left; a plain 429 is one too."""
    if response.status_code == 429:
        return True
    return response.status_code == 403 and response.headers.get("x-ratelimit-remaining") == "0"


def _reset_at(response: httpx.Response) -> int | None:
    raw = response.headers.get("x-ratelimit-reset", "")
    return int(raw) if raw.isdigit() else None


def _hop_headers(headers: dict[str, str], origin_host: str, url: str) -> dict[str, str]:
    """The headers one hop carries: a credential only to the host it was given for."""
    if (urlparse(url).hostname or "") == origin_host:
        return headers
    return {k: v for k, v in headers.items() if k.lower() != _AUTHORIZATION}


async def _follow(
    client: httpx.AsyncClient, url: str, headers: dict[str, str], max_bytes: int
) -> Fetched:
    """Walk the redirects of ``url``, each hop validated before it is contacted."""
    origin_host = urlparse(url).hostname or ""
    current = url
    for _ in range(SKILL_LIBRARY_MAX_REDIRECTS + 1):
        verdict = await validate_url(current)
        if not verdict.valid or urlparse(verdict.url).scheme != "https":
            return Fetched(FetchOutcome.BLOCKED)
        current = verdict.url
        hop = _hop_headers(headers, origin_host, current)
        async with pinned_stream(client, "GET", verdict, headers=hop) as response:
            if response.has_redirect_location:
                current = urljoin(current, response.headers["Location"])
                continue
            if _rate_limited(response):
                return Fetched(
                    FetchOutcome.RATE_LIMITED, response.status_code, b"", _reset_at(response)
                )
            if response.status_code == 404:
                return Fetched(FetchOutcome.NOT_FOUND, 404)
            if not response.is_success:
                return Fetched(FetchOutcome.HTTP_ERROR, response.status_code)
            try:
                body = await read_bounded(response, max_bytes)
            except BodyTooLargeError:
                return Fetched(FetchOutcome.TOO_LARGE, response.status_code)
            return Fetched(FetchOutcome.OK, response.status_code, body)
    return Fetched(FetchOutcome.BLOCKED)


async def fetch(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    max_bytes: int = SKILL_LIBRARY_RESPONSE_MAX_BYTES,
) -> Fetched:
    """GET an https URL for the library, under the hardening above.

    Args:
        client: The caller's client (it owns the pool and closes it).
        url: The https URL.
        headers: Headers to send (a credential reaches its own host only).
        max_bytes: The largest body accepted.

    Returns:
        The outcome; never raises for a network or HTTP failure.
    """
    sent = {"User-Agent": USER_AGENT, **(headers or {})}
    try:
        async with asyncio.timeout(settings.skill_library_timeout_seconds):
            return await _follow(client, url, sent, max_bytes)
    except TimeoutError:
        logger.info("skill_library_fetch_timeout", host=urlparse(url).hostname)
        return Fetched(FetchOutcome.UNREACHABLE)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.info(
            "skill_library_fetch_failed", host=urlparse(url).hostname, error_type=type(exc).__name__
        )
        return Fetched(FetchOutcome.UNREACHABLE)
