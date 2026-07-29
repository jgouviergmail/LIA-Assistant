"""Pre-stream gates for the chat SSE entry point (extracted from service.py).

Two request-scoped, self-contained steps that run BEFORE graph execution:
the usage-limit pre-check (Layer 1 for scheduled actions) and the best-effort
last-known-location capture. Extracted verbatim so the frozen service module
shrinks (file-size ratchet) without behavior change.
"""

import uuid

import structlog

from src.core.config import settings
from src.core.constants import USAGE_LIMIT_EXCEEDED_ERROR_CODE
from src.domains.agents.api.schemas import BrowserContext, ChatStreamChunk

logger = structlog.get_logger(__name__)


async def usage_limit_error_chunk(user_id: uuid.UUID) -> ChatStreamChunk | None:
    """Return the SSE error chunk when the user exceeds a usage limit.

    Args:
        user_id: The requesting user.

    Returns:
        The error chunk to yield (caller then stops), or None when allowed.
    """
    if not getattr(settings, "usage_limits_enabled", False):
        return None
    from src.domains.usage_limits.service import UsageLimitService
    from src.infrastructure.observability.metrics_usage_limits import (
        usage_limit_enforcement_total,
    )

    limit_check = await UsageLimitService.check_user_allowed(user_id)
    if limit_check.allowed:
        return None
    usage_limit_enforcement_total.labels(
        layer="service", limit_type=limit_check.exceeded_limit or "unknown"
    ).inc()
    return ChatStreamChunk(
        type="error",
        content=limit_check.blocked_reason or "Usage limit exceeded",
        metadata={
            "error_code": USAGE_LIMIT_EXCEEDED_ERROR_CODE,
            "limit": limit_check.exceeded_limit,
        },
    )


def capture_location_fire_and_forget(
    user_id: uuid.UUID, browser_context: BrowserContext | None
) -> None:
    """Persist the browser geolocation in the background (opt-in enforced inside).

    Failures are swallowed to never break the chat UX; the task keeps a strong
    reference via safe_fire_and_forget (avoids GC while running).

    Args:
        user_id: The requesting user.
        browser_context: Browser context sent by the frontend, if any.
    """
    if browser_context is None or browser_context.geolocation is None:
        return
    from src.domains.users.user_location_service import (
        update_user_location_fire_and_forget,
    )
    from src.infrastructure.async_utils import safe_fire_and_forget

    safe_fire_and_forget(
        update_user_location_fire_and_forget(
            user_id,
            browser_context.geolocation.lat,
            browser_context.geolocation.lon,
            browser_context.geolocation.accuracy,
        ),
        name="last_known_location_update",
    )
