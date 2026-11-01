"""A mailbox's cache generation: every write makes every cached read of it stale (ADR-369).

A Gmail search is cached under a hash of its query, so the searches a trash
should invalidate cannot be enumerated. Instead every cache key of a mailbox
carries the mailbox's GENERATION, and every write moves it: the entries of the
previous generation are never read again and expire on their own TTL.

The cache is a help, never an authority. A generation that cannot be read
answers ``None`` — the caller then bypasses the cache rather than read an entry
it cannot date — and a bump that fails never fails the write it follows (the
stale entries then live out their short TTL).

The generation outlives every mail cache (``MAIL_GENERATION_TTL_SECONDS``): its
own expiry resets it to 0, which can only meet entries long expired.
"""

from __future__ import annotations

from typing import Any

import structlog

from src.core.constants import MAIL_GENERATION_TTL_SECONDS, REDIS_KEY_MAIL_GENERATION_PREFIX

logger = structlog.get_logger(__name__)


def _key(account: str) -> str:
    return f"{REDIS_KEY_MAIL_GENERATION_PREFIX}{account}"


async def mail_generation(redis: Any, account: str) -> int | None:
    """The mailbox's current generation; ``None`` when it cannot be read (bypass the cache).

    Args:
        redis: The cache client the caller's mail cache lives in.
        account: The mailbox's cache identity (the client's ``_cache_account``).

    Returns:
        0 for a mailbox never written, the count of writes otherwise.
    """
    try:
        raw = await redis.get(_key(account))
    except Exception as error:
        logger.debug("mail_generation_unreadable", error_type=type(error).__name__)
        return None
    if raw is None:
        return 0
    if not isinstance(raw, (str, bytes, int)):
        return None
    try:
        return int(raw)
    except TypeError, ValueError:
        return None


async def bump_mail_generation(redis: Any, account: str) -> None:
    """Make every cached read of the mailbox stale. Never raises.

    Args:
        redis: The cache client the caller's mail cache lives in.
        account: The mailbox's cache identity.
    """
    try:
        await redis.incr(_key(account))
        await redis.expire(_key(account), MAIL_GENERATION_TTL_SECONDS)
    except Exception as error:  # the write happened; stale reads expire with their TTL
        logger.debug("mail_generation_bump_failed", error_type=type(error).__name__)


__all__ = ["bump_mail_generation", "mail_generation"]
