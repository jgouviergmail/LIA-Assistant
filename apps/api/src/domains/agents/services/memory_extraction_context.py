"""Prepare memory-extraction context without changing the source messages or memories."""

from typing import TYPE_CHECKING

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
