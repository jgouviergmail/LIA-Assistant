"""A file downloaded by the person's own hand — a mail attachment, a Drive file (ADR-369).

One download at a time per account — a claim in Redis, by its owner token,
expiring on its own — because a client reads the file into memory up to the
published ceiling. Our own throttle never fails a download: an unreachable
cache lets it through.

What leaves is a DOWNLOAD the browser never renders: sandboxed, kept by no
cache, its name and its type made safe — both are somebody else's (a sender's,
a Drive owner's).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Final
from uuid import UUID, uuid4

import structlog
from fastapi import Response

from src.core.constants import (
    REDIS_KEY_WORKBENCH_DOWNLOAD_PREFIX,
    WORKBENCH_DOWNLOAD_CLAIM_TTL_SECONDS,
    WORKBENCH_DOWNLOAD_RETRY_AFTER_SECONDS,
)
from src.core.content_disposition import attachment_disposition, served_media_type
from src.domains.workbench.errors import PROVIDER_RATE_LIMITED, refuse
from src.infrastructure.cache.redis import get_redis_cache
from src.infrastructure.locks.redis_claim import release_claim, try_claim

logger = structlog.get_logger(__name__)

#: A download is a document nothing may run or load.
DOWNLOAD_POLICY: Final = "default-src 'none'; sandbox"


@asynccontextmanager
async def one_download(user_id: UUID) -> AsyncIterator[None]:
    """Hold the account's download claim for the body of the block.

    Raises:
        BaseAPIException: ``provider_rate_limited`` while another download of
            the account runs.
    """
    key = f"{REDIS_KEY_WORKBENCH_DOWNLOAD_PREFIX}{user_id}"
    token = uuid4().hex
    redis = await _cache()
    if redis is not None and not await _claim(redis, key, token):
        refuse(PROVIDER_RATE_LIMITED, retry_after=WORKBENCH_DOWNLOAD_RETRY_AFTER_SECONDS)
    try:
        yield
    finally:
        if redis is not None:
            await release_claim(redis, key, token)


def download_response(data: bytes, filename: str, mime_type: str, fallback: str) -> Response:
    """The bytes as a file the browser saves and never renders.

    Args:
        data: The file.
        filename: Its name as received — untrusted.
        mime_type: Its declared type — untrusted (served opaque when malformed).
        fallback: The ASCII name used when nothing ASCII survives.
    """
    return Response(
        content=data,
        media_type=served_media_type(mime_type),
        headers={
            "Content-Disposition": attachment_disposition(filename, fallback),
            "Content-Security-Policy": DOWNLOAD_POLICY,
            "Cache-Control": "no-store",
        },
    )


async def _cache() -> Any | None:
    """The cache, or None when it cannot be reached (the download goes on)."""
    try:
        return await get_redis_cache()
    except Exception as exc:  # noqa: BLE001 - our own throttle never fails a download
        logger.debug("workbench_download_no_cache", error_type=type(exc).__name__)
        return None


async def _claim(redis: Any, key: str, token: str) -> bool:
    """Take the account's download claim; True too when the cache cannot say."""
    try:
        return await try_claim(redis, key, token, ttl_seconds=WORKBENCH_DOWNLOAD_CLAIM_TTL_SECONDS)
    except Exception as exc:  # noqa: BLE001 - our own throttle never fails a download
        logger.debug("workbench_download_claim_failed", error_type=type(exc).__name__)
        return True
