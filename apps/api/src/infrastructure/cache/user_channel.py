"""The one name of a person's real-time channel, and the one way to publish on it.

Every real-time event a person's open tabs receive travels on one Redis Pub/Sub
channel, which the SSE route (``GET /notifications/stream``) subscribes to. Five
publishers used to spell that name by hand beside the route that reads it — a
name written six times is a name that can drift, and the day one of them is
misspelled its events reach nobody while nothing fails (ADR-320). Writers and
reader now share this function.

The family is declared ``USER_RUNTIME`` in ``key_families``: a Pub/Sub channel
holds no value, so a conversation reset has nothing to purge there.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Mapping
from typing import Any

from src.infrastructure.cache.redis import get_redis_cache


def user_notifications_channel(user_id: uuid.UUID | str) -> str:
    """The Pub/Sub channel a person's open tabs listen to.

    Args:
        user_id: The account.

    Returns:
        The channel name.
    """
    return f"user_notifications:{user_id}"


async def publish_to_user(user_id: uuid.UUID | str, payload: Mapping[str, Any]) -> bool:
    """Publish one event to a person's open tabs.

    Args:
        user_id: The account.
        payload: The event, JSON-serialisable; the SSE route forwards it as is.

    Returns:
        False when no Redis client is available (the event did not leave);
        True once Redis accepted it — a tab that is closed simply misses it.

    Raises:
        Whatever the Redis client raises: the caller decides how a failure is
        counted, since only it knows what the event was for.
    """
    redis = await get_redis_cache()
    if redis is None:
        return False
    await redis.publish(
        user_notifications_channel(user_id), json.dumps(payload, ensure_ascii=False)
    )
    return True
