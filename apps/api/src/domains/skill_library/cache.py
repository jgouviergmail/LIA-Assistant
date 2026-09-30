"""The library's shared cache: public answers every account may reuse (ADR-327).

A portal search, a branch head and a repository listing are PUBLIC — the same
for every account — so they live under one GLOBAL family
(``SKILL_LIBRARY_CACHE_PREFIX``, ADR-260) and are shared: GitHub allows the
whole instance 60 anonymous requests per hour, and a person opening the
library twice in a minute should not spend them twice. A listing read at a
COMMIT never changes. Redis failing is never a failure: the library reads
afresh (fail-open, like every cache here).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import structlog

from src.core.constants import SKILL_LIBRARY_CACHE_PREFIX
from src.infrastructure.cache.redis import get_redis_cache

logger = structlog.get_logger(__name__)


def cache_key(kind: str, *parts: str) -> str:
    """A key of the library's family: its kind, then a digest of what names it.

    Args:
        kind: What the value is (``search``, ``head``, ``tree``, ``audit``).
        *parts: What identifies it (a query, a repository and a ref...).

    Returns:
        ``skill_library:<kind>:<sha256 of the parts>`` — bounded whatever the parts.
    """
    digest = hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()
    return f"{SKILL_LIBRARY_CACHE_PREFIX}:{kind}:{digest}"


async def cached(key: str) -> Any | None:
    """The value stored under ``key``, or None (absent, unreadable, Redis down)."""
    try:
        raw = await (await get_redis_cache()).get(key)
    except Exception as exc:
        logger.debug("skill_library_cache_read_failed", error_type=type(exc).__name__)
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        return None


async def store(key: str, value: Any, ttl_seconds: int) -> None:
    """Keep ``value`` for ``ttl_seconds`` (0 keeps nothing); a failure is logged only."""
    if ttl_seconds <= 0:
        return
    try:
        await (await get_redis_cache()).set(key, json.dumps(value), ex=ttl_seconds)
    except Exception as exc:
        logger.debug("skill_library_cache_write_failed", error_type=type(exc).__name__)
