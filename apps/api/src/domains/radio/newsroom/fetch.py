"""Fetching a public URL for the newsroom — safely, politely, and bounded.

Every feed an instance reads may have been added by one of its users, so every
request is treated as hostile input: each URL, the first and every redirect,
is validated against private and internal addresses before it is requested
(the web-fetch tool's own validator, one implementation — it also upgrades
``http`` to ``https``, so every request made here carries TLS); redirects are
followed here, one validated hop at a time, whatever the client's own setting;
the body streams through the shared bounded reader and is abandoned past a
byte ceiling, which is also what stops a decompression bomb (the ceiling counts
DECODED bytes); a conditional request (ETag / Last-Modified) makes an unchanged
feed cost one 304.

Residual risk, documented and accepted as for the skills' URL import: DNS
rebinding between the validator's resolution and the connection's own (no IP
pinning). What bounds it: every request is ``https``, so the certificate must
match the host a rebinding would redirect; the body is bounded; and nothing
fetched is ever returned raw — it is parsed as a feed or reduced to an
article's text.

The crawler says who it is: a newsroom that identifies itself can be opted out
of with one robots.txt line, the courtesy tokenFM extends and the owner asked
for (robots.txt itself is honoured by :mod:`~src.domains.radio.newsroom.robots`).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final
from urllib.parse import urljoin

import httpx

from src.domains.agents.web_fetch.url_validator import validate_url
from src.domains.radio.constants import ETAG_MAX_CHARS, LAST_MODIFIED_MAX_CHARS
from src.infrastructure.utils.bounded_read import BodyTooLargeError, read_bounded

#: How the newsroom introduces itself to the sites it reads.
NEWSROOM_USER_AGENT: Final[str] = "LIA-Radio/1.0 (+https://github.com/jgouviergmail/LIA)"

#: Redirects followed at most (each one re-validated).
_MAX_REDIRECTS: Final[int] = 5


class FetchOutcome(StrEnum):
    """What a fetch ended in — a bounded vocabulary (a metric label)."""

    OK = "ok"
    NOT_MODIFIED = "not_modified"
    BLOCKED = "blocked"
    TOO_LARGE = "too_large"
    HTTP_ERROR = "http_error"
    NETWORK_ERROR = "network_error"
    TOO_MANY_REDIRECTS = "too_many_redirects"


@dataclass(frozen=True, slots=True)
class FetchResult:
    """What came back.

    Attributes:
        outcome: How the fetch ended.
        final_url: The URL that answered (after redirects).
        status: The HTTP status, when one was received.
        content: The body (empty unless ``OK``).
        etag: The validator to send next time, when the server gave one.
        last_modified: The other validator, when the server gave one.
        charset: The body's charset as the ``Content-Type`` header declares it.
    """

    outcome: FetchOutcome
    final_url: str
    status: int | None = None
    content: bytes = b""
    etag: str | None = None
    last_modified: str | None = None
    charset: str | None = None


def _validator(value: str | None, max_chars: int) -> str | None:
    """A validator worth keeping: printable ASCII that its column holds, or nothing.

    It is echoed in the next request's headers, which httpx encodes as ASCII —
    a stored non-ASCII ETag would make every later fetch of the feed raise; and
    one longer than its column would make every reading of the feed fail to be
    filed. Without it, the next request is simply unconditional.
    """
    if value and len(value) <= max_chars and value.isascii() and value.isprintable():
        return value
    return None


def _conditional_headers(etag: str | None, last_modified: str | None) -> dict[str, str]:
    headers: dict[str, str] = {}
    if etag:
        headers["If-None-Match"] = etag
    if last_modified:
        headers["If-Modified-Since"] = last_modified
    return headers


async def public_url(url: str) -> str | None:
    """The URL as it will be requested (``https``), or None when it is not a public web address.

    The same validator every hop of :func:`fetch_public` goes through, for a
    caller that must tell « not a public address » from « did not answer »
    before anything is requested.
    """
    verdict = await validate_url(url)
    return verdict.url if verdict.valid else None


async def fetch_public(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    etag: str | None = None,
    last_modified: str | None = None,
) -> FetchResult:
    """GET a public URL with SSRF checks at every hop and a byte ceiling.

    Args:
        client: The caller's client (it owns the pool and closes it).
        url: The URL to read.
        max_bytes: The largest decoded body accepted.
        etag: The previous ``ETag``, for a conditional request.
        last_modified: The previous ``Last-Modified``, for a conditional request.

    Returns:
        The outcome, never an exception for a network or HTTP failure.
    """
    current = url
    headers = {"User-Agent": NEWSROOM_USER_AGENT, **_conditional_headers(etag, last_modified)}
    for _ in range(_MAX_REDIRECTS + 1):
        verdict = await validate_url(current)
        if not verdict.valid:
            return FetchResult(FetchOutcome.BLOCKED, current)
        current = verdict.url
        try:
            async with client.stream(
                "GET", current, headers=headers, follow_redirects=False
            ) as response:
                # 304 before the success test: not a 2xx, yet the answer hoped for.
                if response.status_code == 304:
                    return FetchResult(
                        FetchOutcome.NOT_MODIFIED,
                        current,
                        304,
                        etag=etag,
                        last_modified=last_modified,
                    )
                if response.has_redirect_location:
                    current = urljoin(current, response.headers["Location"])
                    continue
                if not response.is_success:
                    return FetchResult(FetchOutcome.HTTP_ERROR, current, response.status_code)
                try:
                    body = await read_bounded(response, max_bytes)
                except BodyTooLargeError:
                    return FetchResult(FetchOutcome.TOO_LARGE, current, response.status_code)
                return FetchResult(
                    FetchOutcome.OK,
                    current,
                    response.status_code,
                    content=body,
                    etag=_validator(response.headers.get("ETag"), ETAG_MAX_CHARS),
                    last_modified=_validator(
                        response.headers.get("Last-Modified"), LAST_MODIFIED_MAX_CHARS
                    ),
                    charset=response.charset_encoding,
                )
        except httpx.InvalidURL:
            # A URL the validator accepted but no request can carry (a control
            # character in its path, from a hostile feed or redirect).
            return FetchResult(FetchOutcome.BLOCKED, current)
        except httpx.HTTPError:
            return FetchResult(FetchOutcome.NETWORK_ERROR, current)
    return FetchResult(FetchOutcome.TOO_MANY_REDIRECTS, current)


__all__ = ["NEWSROOM_USER_AGENT", "FetchOutcome", "FetchResult", "fetch_public", "public_url"]
