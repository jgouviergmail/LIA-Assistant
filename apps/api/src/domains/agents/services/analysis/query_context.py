"""Conversation context projection and turn classification for query analysis."""

from __future__ import annotations

from datetime import tzinfo
from typing import TYPE_CHECKING

from langchain_core.messages import BaseMessage

from src.core.constants import QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.llm.message_view import written_prefix

if TYPE_CHECKING:
    from src.domains.agents.services.reference_resolver import ResolvedContext

#: What the analyzer prompt reads when no earlier turn exists.
_NO_HISTORY = "None"


def extract_conversation_history(
    messages: list[BaseMessage],
    *,
    zone: tzinfo,
    window_size: int = 5,
) -> list[dict[str, str]]:
    """Extract conversation history for LLM context.

    Args:
        messages: The thread, the current question last.
        zone: The person's display zone: each message they wrote reads with its
            instant in it (lot 17, ``message_view.written_prefix``).
        window_size: Turns kept (two messages each).

    Returns:
        ``role``/``content`` pairs: each content is the message's text cut at
        ``QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS``, after the moment it was
        written, so the moment never takes the text's room.
    """
    history = []
    for msg in messages[-window_size * 2 :]:
        text = coerce_content_to_text(getattr(msg, "content", ""))
        if text:
            role = "user" if msg.type == "human" else "assistant"
            content = written_prefix(msg, zone) + text[:QUERY_ANALYZER_HISTORY_TURN_MAX_CHARS]
            history.append({"role": role, "content": content})
    return history


def render_conversation_history(history: list[dict[str, str]], window_size: int) -> str:
    """The analyzer prompt's history block, each turn as it was projected.

    Args:
        history: What :func:`extract_conversation_history` projected; already cut.
        window_size: The last entries shown.

    Returns:
        One ``[role]: content`` line per entry, or ``None`` with no history.
    """
    if not history:
        return _NO_HISTORY
    return "\n".join(
        f"[{turn.get('role', 'user')}]: {turn.get('content', '')}"
        for turn in history[-window_size:]
    )


def determine_turn_type(context_result: ResolvedContext | None, intent: str) -> str:
    """Determine the turn type based on context and intent."""
    if not context_result or not context_result.items:
        return "ACTION"

    ACTION_INTENTS = {"send", "create", "update", "delete"}
    if intent in ACTION_INTENTS:
        return "REFERENCE_ACTION"
    return "REFERENCE_PURE"
