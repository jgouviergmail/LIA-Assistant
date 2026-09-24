"""Download an image a vendor returned as a URL (ADR-305).

Qwen's OpenAI-compatible mode answers with a URL valid 24 hours and ignores a
request for base64. The URL is the one server-side fetch the vendor directs, so it
is held to that vendor: https, a declared host, no redirect followed, a body bounded
in size and time, and a PNG signature. The URL itself is never logged — it carries
a signed access token.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import httpx

from src.core.config import settings
from src.domains.image_generation.providers.base import PNG_SIGNATURE, ImageGenerationError
from src.infrastructure.utils.bounded_read import BodyTooLargeError, read_bounded


def _host_allowed(host: str, allowed_suffixes: tuple[str, ...]) -> bool:
    """Whether ``host`` is one of the vendor's (``.example.com`` or ``example.com``)."""
    return any(host == suffix.lstrip(".") or host.endswith(suffix) for suffix in allowed_suffixes)


async def download_result(
    url: str, *, client: httpx.AsyncClient, allowed_host_suffixes: tuple[str, ...]
) -> bytes:
    """Fetch a vendor's result image under the vendor's own constraints.

    Args:
        url: The result URL the vendor returned.
        client: The caller's HTTP client (the caller owns its lifecycle).
        allowed_host_suffixes: Host suffixes the vendor serves results from.

    Returns:
        The PNG bytes.

    Raises:
        ImageGenerationError: On a refused host, a non-200 answer (a redirect
            included), an oversized body, an expired deadline, a transport
            failure or a body that is not a PNG.
    """
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme != "https" or not _host_allowed(host, allowed_host_suffixes):
        raise ImageGenerationError(f"Result URL refused: host {host or 'none'} is not the vendor's")

    deadline = settings.image_generation_result_download_timeout_seconds
    max_bytes = settings.image_generation_result_max_mb * 1024 * 1024
    try:
        async with asyncio.timeout(deadline):
            async with client.stream(
                "GET", url, follow_redirects=False, timeout=deadline
            ) as response:
                if response.status_code != 200:
                    raise ImageGenerationError(
                        f"Result download answered HTTP {response.status_code}"
                    )
                body = await read_bounded(response, max_bytes)
    except BodyTooLargeError as exc:
        raise ImageGenerationError(f"Result image exceeds {exc.max_bytes} bytes") from exc
    except TimeoutError as exc:
        raise ImageGenerationError("Result download exceeded its deadline") from exc
    except httpx.HTTPError as exc:
        raise ImageGenerationError(f"Result download failed: {type(exc).__name__}") from exc

    if not body.startswith(PNG_SIGNATURE):
        raise ImageGenerationError("Result is not a PNG image")
    return body
