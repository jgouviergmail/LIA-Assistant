"""Prepare memory-extraction context without changing the source messages or memories."""

from datetime import datetime, tzinfo
from typing import TYPE_CHECKING
from uuid import UUID

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.core.config import settings
from src.core.constants import (
    MEMORY_CONTENT_MIN_CHARS,
    MEMORY_TRIGGER_TOPIC_MAX_CHARS,
    MEMORY_USAGE_NUANCE_MAX_CHARS,
)
from src.domains.agents.prompts import load_prompt
from src.domains.agents.sms.message_policy import is_sms_source_message
from src.domains.health_metrics.prompt_context import opted_in_health_context
from src.domains.shared.extraction_targets import is_synthetic_message
from src.infrastructure.llm.message_view import present_label, written_prefix

if TYPE_CHECKING:
    from src.domains.memories.models import Memory


def render_extraction_prompt(
    *,
    conversation: str,
    existing_memories: str,
    known_relationships: list[str],
    health_context: str,
    zone: tzinfo,
    now: datetime | None = None,
) -> str:
    """Fill the extraction prompt, with the bounds the parser will hold the model to.

    Args:
        conversation: The exchange to analyze, already formatted (stamped in ``zone``).
        existing_memories: The candidates for update or delete, already formatted.
        known_relationships: What is known of the person's relationships.
        health_context: The opted-in health context, empty otherwise.
        zone: The person's display zone: the present is written in it (ADR-381).
        now: The present; the current instant by default.

    Returns:
        The prompt, ready for the model.
    """
    return str(load_prompt("memory_extraction_prompt")).format(
        conversation=conversation,
        existing_memories=existing_memories,
        current_datetime=present_label(zone, now),
        known_relationships=(
            "\n".join(f"- {relationship}" for relationship in known_relationships)
            if known_relationships
            else "No known relationships"
        ),
        health_context=health_context,
        memory_content_min_chars=MEMORY_CONTENT_MIN_CHARS,
        memory_content_max_chars=settings.memory_content_max_chars,
        memory_trigger_topic_max_chars=MEMORY_TRIGGER_TOPIC_MAX_CHARS,
        memory_usage_nuance_max_chars=MEMORY_USAGE_NUANCE_MAX_CHARS,
    )


def format_messages_for_extraction(messages: list[BaseMessage], *, zone: tzinfo) -> str:
    """Format messages for extraction prompt context.

    Args:
        messages: List of conversation messages.
        zone: The person's display zone: a message carrying the instant it was
            written starts with it, in that zone (ADR-381).

    Returns:
        Formatted conversation string.
    """
    lines = []
    for msg in messages:
        if isinstance(msg, ToolMessage) and (is_sms_source_message(msg)):
            continue
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

        lines.append(f"{prefix}: {written_prefix(msg, zone)}{content}")

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


async def _maybe_build_health_context(user_id: str) -> str:
    """Return the opted-in Health Metrics context block for the extraction prompt.

    The gate (instance switch, the person's opt-in, their zone) is the one
    door's, ``health_metrics.prompt_context``; the prompt marks the
    ``{health_context}`` placeholder optional, so an empty block is fine.

    Args:
        user_id: Owner user ID (string form from the extractor plumbing).

    Returns:
        A short textual block (``""`` if none).
    """
    return await opted_in_health_context(UUID(user_id), surface="memory_extraction")
