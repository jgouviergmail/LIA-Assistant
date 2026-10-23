"""Optional conversation continuity of a delivered heartbeat notification."""

from datetime import UTC, datetime
from uuid import UUID

import structlog

from src.infrastructure.proactive.base import ProactiveTaskResult

logger = structlog.get_logger(__name__)


async def store_heartbeat_continuity(user_id: UUID, result: ProactiveTaskResult) -> None:
    """Store a short summary of the notification for conversational continuity.

    Whatever the sources the decision read: an SMS in view is personal data like
    a mail (ADR-357 amendment 2026-10-23). Best-effort, never raises.

    Args:
        user_id: The notified account.
        result: The delivered notification.
    """
    try:
        from pydantic import JsonValue, TypeAdapter

        from src.infrastructure.proactive.context_sink import write_heartbeat_context

        # Validated as strings, then re-listed as JSON values: a list is invariant,
        # so list[str] is not a list[JsonValue] even though every item is one.
        sources: list[JsonValue] = [
            *TypeAdapter(list[str]).validate_python(result.metadata.get("sources_used", []))
        ]
        await write_heartbeat_context(
            user_id,
            {
                "content": (result.content or "")[:200],
                "sources": sources,
                "sent_at": datetime.now(UTC).isoformat(),
            },
        )
    except Exception:
        # Non-critical: conversational continuity is a bonus
        logger.debug(
            "heartbeat_store_write_failed",
            user_id=str(user_id),
        )
