"""Gmail history.list delta sync for the heartbeat (lot G, 2026-08).

Replaces the heartbeat's ``is:unread after:<today>`` re-query with an exact
"new INBOX mail since the last tick" delta, anchored on Gmail's historyId
(persisted in Redis per user).

Contract: :func:`fetch_new_message_ids` returns

- a list of message ids (possibly EMPTY — "no new mail" is a real answer,
  the caller must not re-query);
- ``None`` whenever the caller must use the legacy query path: provider
  without history support, first run (anchored for the next tick), expired
  anchor (re-anchored), or Redis unavailable. None is always fail-open.

This module is also the prerequisite of lot H phase 2 (Gmail push): a push
notification only carries a historyId — this is what turns it into messages.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from src.core.constants import GMAIL_HISTORY_ANCHOR_TTL_SECONDS
from src.core.exceptions import ConnectorAPIError

logger = structlog.get_logger(__name__)


def _anchor_key(user_id: UUID) -> str:
    return f"gmail_history_anchor:{user_id}"


async def _store_anchor(redis: Any, user_id: UUID, history_id: str) -> None:
    await redis.set(_anchor_key(user_id), str(history_id), ex=GMAIL_HISTORY_ANCHOR_TTL_SECONDS)


async def _reanchor_from_profile(client: Any, redis: Any, user_id: UUID) -> None:
    """Best-effort re-anchor on the mailbox's current historyId."""
    try:
        profile = await client.get_profile()
        history_id = profile.get("historyId")
        if history_id:
            await _store_anchor(redis, user_id, str(history_id))
    except Exception as exc:
        logger.warning("gmail_delta_reanchor_failed", user_id=str(user_id), error=str(exc))


async def delta_messages_or_none(
    client: Any, user_id: UUID, max_emails: int
) -> list[dict[str, str]] | None:
    """Heartbeat entry point: id-only message dicts since the anchor, or None.

    Owns the Redis access so the aggregator stays a thin caller. Returns
    ``[{"id": ...}, ...]`` capped at ``max_emails`` ([] = exactly no new
    mail), or None when the legacy query path must run (always fail-open).
    """
    try:
        from src.infrastructure.cache.redis import get_redis_cache

        redis = await get_redis_cache()
    except Exception as exc:
        logger.warning("gmail_delta_redis_unavailable", user_id=str(user_id), error=str(exc))
        return None
    message_ids = await fetch_new_message_ids(client, redis, user_id)
    if message_ids is None:
        return None
    return [{"id": message_id} for message_id in message_ids[:max_emails]]


async def fetch_new_message_ids(client: Any, redis: Any, user_id: UUID) -> list[str] | None:
    """Exact new-INBOX-message ids since the stored anchor, or None (legacy path).

    Args:
        client: Resolved email client (only Gmail exposes ``get_history``).
        redis: Async Redis client for the per-user anchor.
        user_id: Owner of the mailbox.

    Returns:
        Ordered, deduplicated message ids since the anchor; [] when nothing
        is new; None when the legacy query path must run instead.
    """
    if not hasattr(client, "get_history"):
        return None

    try:
        anchor = await redis.get(_anchor_key(user_id))
    except Exception as exc:
        logger.warning("gmail_delta_redis_unavailable", user_id=str(user_id), error=str(exc))
        return None

    if not anchor:
        # First run: anchor now, answer through the legacy path this tick.
        await _reanchor_from_profile(client, redis, user_id)
        return None

    anchor_str = anchor.decode() if isinstance(anchor, bytes) else str(anchor)
    try:
        response = await client.get_history(start_history_id=anchor_str)
    except ConnectorAPIError as exc:
        # Gmail 404s an expired historyId: re-anchor and use the legacy path.
        logger.info(
            "gmail_delta_anchor_expired",
            user_id=str(user_id),
            upstream_status=exc.status_code,
        )
        await _reanchor_from_profile(client, redis, user_id)
        return None
    except Exception as exc:
        logger.warning("gmail_delta_history_failed", user_id=str(user_id), error=str(exc))
        return None

    seen: set[str] = set()
    message_ids: list[str] = []
    for entry in response.get("history", []):
        for added in entry.get("messagesAdded", []):
            message_id = (added.get("message") or {}).get("id")
            if message_id and message_id not in seen:
                seen.add(message_id)
                message_ids.append(message_id)

    new_anchor = response.get("historyId")
    if new_anchor:
        try:
            await _store_anchor(redis, user_id, str(new_anchor))
        except Exception as exc:
            logger.warning("gmail_delta_anchor_store_failed", user_id=str(user_id), error=str(exc))

    logger.debug(
        "gmail_delta_fetched",
        user_id=str(user_id),
        new_messages=len(message_ids),
    )
    return message_ids
