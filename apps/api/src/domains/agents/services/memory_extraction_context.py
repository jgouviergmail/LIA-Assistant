"""Prepare memory-extraction context without changing the source messages or memories."""

from typing import TYPE_CHECKING
from uuid import UUID

import structlog
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.config import settings
from src.domains.shared.extraction_targets import is_synthetic_message

if TYPE_CHECKING:
    from src.domains.memories.models import Memory


def format_messages_for_extraction(messages: list[BaseMessage]) -> str:
    """Format messages for extraction prompt context.

    Args:
        messages: List of conversation messages.

    Returns:
        Formatted conversation string.
    """
    lines = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            # System-fabricated HITL scaffolding is not conversation.
            if is_synthetic_message(msg):
                continue
            prefix = "USER"
        elif isinstance(msg, AIMessage):
            if msg.additional_kwargs.get("proactive_notification"):
                continue
            prefix = "ASSISTANT"
        else:
            prefix = "SYSTEM"

        content = str(msg.text)
        max_chars = settings.memory_extraction_message_max_chars
        if len(content) > max_chars:
            content = content[:max_chars] + "..."

        lines.append(f"{prefix}: {content}")

    return "\n".join(lines)


def format_existing_memories_with_ids(
    memories: list[tuple[Memory, float]],
) -> str:
    """Format existing memories for the extraction prompt with IDs.

    Shows memories with their UUIDs so the LLM can reference them
    for update/delete actions. Pinned memories are tagged [PINNED] so the LLM
    avoids emitting update/delete on user-locked entries (these would be
    rejected downstream anyway; tagging saves output tokens and log noise).

    Args:
        memories: List of (Memory, score) tuples from search_by_relevance.

    Returns:
        Formatted string for prompt injection.
    """
    if not memories:
        return "None"

    lines = []
    for memory, _score in memories:
        content = memory.content or ""
        category = memory.category or "personal"
        importance = memory.importance or 0.7
        pinned_tag = " [PINNED]" if memory.pinned else ""
        lines.append(
            f"- [id={memory.id} | {category} | importance={importance:.1f}]{pinned_tag} {content}"
        )

    return "\n".join(lines)


logger = structlog.get_logger(__name__)


async def _maybe_build_health_context(user_id: str) -> str:
    """Return the Health Metrics context block for the extraction prompt.

    Returns an empty string when the global feature flag is off, the user
    has not opted into Health Metrics assistant integrations, or when
    their health history is empty. The prompt template includes a
    ``{health_context}`` placeholder flagged ``(optional)`` so the LLM
    handles the empty case transparently.

    Args:
        user_id: Owner user ID (string form from the extractor plumbing).

    Returns:
        A short textual block (``""`` if none).
    """
    from src.core.config import settings as global_settings
    from src.core.constants import HEALTH_METRICS_USER_TOGGLE_ATTR

    if not getattr(global_settings, "health_metrics_enabled", False):
        return ""

    try:
        from src.infrastructure.database.session import get_db_context

        async with get_db_context() as db:
            from src.domains.health_metrics.service import HealthMetricsService
            from src.domains.users.repository import UserRepository

            user = await UserRepository(db).get_by_id(UUID(user_id))
            if user is None or not getattr(user, HEALTH_METRICS_USER_TOGGLE_ATTR, False):
                return ""
            service = HealthMetricsService(db)
            return await service.build_health_context_for_prompt(UUID(user_id))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(
            "memory_extractor_health_context_failed",
            user_id=user_id,
            error_type=type(exc).__name__,
        )
        return ""
