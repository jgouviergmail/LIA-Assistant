"""
Reading an OAuth state payload without spending it.

The state token is single-use and the token exchange consumes it, so anything a
callback needs to know about its own flow has to be read BEFORE that — the user
id, and now which surface started it. Three call sites made this read
independently, each with its own JSON handling and its own idea of what a
malformed payload means.

Fail-closed, and quietly: an unknown state, a Redis outage and a corrupt payload
all yield ``None``. A caller deciding where to send a user needs an answer, and
the states that would produce an exception here are the same ones the flow is
about to reject anyway, with a message written for a human.
"""

from __future__ import annotations

import json
from typing import Any

import structlog

from src.core.constants import REDIS_KEY_OAUTH_STATE_PREFIX
from src.infrastructure.cache.redis import get_redis_session

logger = structlog.get_logger(__name__)


async def peek_oauth_state(
    state: str,
    *,
    prefix: str = REDIS_KEY_OAUTH_STATE_PREFIX,
) -> dict[str, Any] | None:
    """
    Read a flow's stored payload, leaving it available for the exchange.

    Args:
        state: CSRF state token from the provider's redirect.
        prefix: Redis key namespace. A parameter because the MCP flow keeps its
            own, and reading the wrong namespace answers "not native" for every
            MCP flow — silently, and only in the shell.

    Returns:
        The stored payload, or ``None`` when there is nothing readable under
        that token. Never raises.
    """
    if not state:
        return None

    try:
        redis = await get_redis_session()
        raw = await redis.get(f"{prefix}{state}")
    except Exception as exc:
        # A cache outage is not a verdict on the flow. The exchange that
        # follows will fail on its own terms, with a message meant for a human.
        logger.warning("oauth_state_peek_failed", error=str(exc))
        return None

    if not raw:
        return None

    try:
        payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    except json.JSONDecodeError, AttributeError, TypeError, ValueError:
        return None

    return payload if isinstance(payload, dict) else None
