"""Conversation context projection and turn classification for query analysis."""

from __future__ import annotations

from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from src.infrastructure.llm.message_text import coerce_content_to_text

if TYPE_CHECKING:
    from src.domains.agents.services.reference_resolver import ResolvedContext


def extract_conversation_history(
    messages: list[BaseMessage],
    window_size: int = 5,
) -> list[dict[str, str]]:
    """Extract conversation history for LLM context."""
    history = []
    for msg in messages[-window_size * 2 :]:
        role = "user" if msg.type == "human" else "assistant"
        content = coerce_content_to_text(getattr(msg, "content", ""))
        if content:
            history.append({"role": role, "content": content[:500]})
    return history


def determine_turn_type(context_result: ResolvedContext | None, intent: str) -> str:
    """Determine the turn type based on context and intent."""
    if not context_result or not context_result.items:
        return "ACTION"

    ACTION_INTENTS = {"send", "create", "update", "delete"}
    if intent in ACTION_INTENTS:
        return "REFERENCE_ACTION"
    return "REFERENCE_PURE"
