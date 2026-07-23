"""URL-sourced skill fetching (UXR Lot 10, B12).

Downloads a skill package (``.zip`` or ``SKILL.md``) from a user-supplied
https URL and returns raw bytes + an inferred filename for the untouched
hardened import pipeline (``SkillImportService.import_upload`` — S1–S4 and
409 conflicts apply verbatim; this module never writes to disk).

Hardening layers, in order:
    1. Strict https-only pre-check (no http→https upgrade for code imports).
    2. Reused SSRF validator (``agents/web_fetch/url_validator.validate_url``):
       hostname blacklist, DNS resolution, blocked ranges (RFC 1918, loopback,
       link-local/metadata, CGNAT, ULA, IPv4-mapped IPv6 …).
    3. ``follow_redirects=False`` — a 3xx answer is a REFUSAL, not a hop
       (redirects would bypass the pre-resolved DNS check).
    4. Streamed read bounded by ``settings.skills_url_import_max_bytes``
       (aborts mid-transfer, never buffers an unbounded body).
    5. Content sniffing: zip magic / markdown frontmatter — anything else
       is rejected before touching the import pipeline.

Residual risk (documented, accepted): DNS rebinding between the validation
resolve and httpx's own connect resolve (no IP pinning). Mitigations in
place: https-only (certificate must match the hostname), no redirects,
bounded read, and the import pipeline's own validation downstream. A
per-request pinned-IP transport or a hostname allowlist are noted as future
hardening options in the program document.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx
import structlog

from src.core.config import settings
from src.domains.agents.web_fetch.url_validator import validate_url
from src.domains.skills.exceptions import (
    raise_url_import_blocked,
    raise_url_import_fetch_failed,
    raise_url_import_not_https,
    raise_url_import_not_skill_content,
    raise_url_import_too_large,
)

logger = structlog.get_logger(__name__)

_ZIP_MAGIC = b"PK\x03\x04"


def _infer_filename(url: str, content: bytes) -> str:
    """Infer the pipeline filename from the URL basename, else magic bytes.

    Args:
        url: The (validated) source URL.
        content: The downloaded body.

    Returns:
        A ``*.zip`` or ``*.md`` filename for ``import_upload``.

    Raises:
        HTTPException: 422 via raiser when the content is neither format.
    """
    basename = urlparse(url).path.rsplit("/", 1)[-1]
    lowered = basename.lower()
    if lowered.endswith((".zip", ".md")):
        return basename
    if content.startswith(_ZIP_MAGIC):
        return "skill.zip"
    if content.lstrip()[:3] == b"---":
        return "SKILL.md"
    raise_url_import_not_skill_content()


async def _read_bounded(response: httpx.Response, max_bytes: int) -> bytes:
    """Stream the body under the byte cap, aborting mid-transfer.

    Args:
        response: The open streaming response.
        max_bytes: Hard ceiling on the received size.

    Returns:
        The complete body bytes.

    Raises:
        HTTPException: 413 via raiser when the cap is exceeded.
    """
    chunks: list[bytes] = []
    received = 0
    async for chunk in response.aiter_bytes():
        received += len(chunk)
        if received > max_bytes:
            raise_url_import_too_large(max_bytes)
        chunks.append(chunk)
    return b"".join(chunks)


async def _fetch_bytes(active: httpx.AsyncClient, url: str) -> bytes:
    """Perform the bounded GET under the TOTAL transfer deadline.

    httpx's timeout is PER PHASE (connect/read/write) — a server dripping
    one byte per read window would never trip it. The ``asyncio.timeout``
    is the total deadline for the whole transfer.

    Args:
        active: The client to use (caller owns its lifecycle).
        url: The validated https URL.

    Returns:
        The body bytes.

    Raises:
        HTTPException: Via the blocked / fetch-failed / too-large raisers.
        TimeoutError: When the total deadline expires (mapped by the caller).
        httpx.HTTPError: Transport errors (mapped by the caller).
    """
    timeout = settings.skills_url_import_timeout_seconds
    async with asyncio.timeout(timeout):
        async with active.stream(
            "GET",
            url,
            follow_redirects=False,
            timeout=timeout,
        ) as response:
            if 300 <= response.status_code < 400:
                raise_url_import_blocked("redirects are not followed for skill imports")
            if response.status_code != 200:
                raise_url_import_fetch_failed(f"HTTP {response.status_code}")
            return await _read_bounded(response, settings.skills_url_import_max_bytes)


async def fetch_skill_from_url(
    url: str,
    *,
    client: httpx.AsyncClient | None = None,
) -> tuple[bytes, str]:
    """Fetch a skill package from an https URL under the hardening contract.

    Args:
        url: User-supplied source URL.
        client: Optional pre-built AsyncClient (tests inject a MockTransport).
            The caller keeps ownership of an injected client; an internally
            created one is closed here.

    Returns:
        ``(content_bytes, inferred_filename)`` ready for ``import_upload``.

    Raises:
        HTTPException: Via the stable-coded raisers (``url_not_https``,
            ``url_blocked``, ``url_fetch_failed``, ``url_too_large``,
            ``url_not_skill_content``).
    """
    stripped = (url or "").strip()
    scheme = urlparse(stripped).scheme.lower()
    if scheme != "https":
        raise_url_import_not_https(scheme or "none")

    validation = await validate_url(stripped)
    if not validation.valid:
        raise_url_import_blocked(validation.error or "validation failed")

    own_client = client is None
    active = client or httpx.AsyncClient()
    try:
        content = await _fetch_bytes(active, validation.url)
    except TimeoutError:
        raise_url_import_fetch_failed("TotalDeadlineExceeded")
    except httpx.HTTPError as exc:
        raise_url_import_fetch_failed(type(exc).__name__)
    finally:
        if own_client:
            await active.aclose()

    filename = _infer_filename(validation.url, content)
    logger.info(
        "skill_url_import_fetched",
        content_bytes=len(content),
        filename=filename,
    )
    return content, filename
