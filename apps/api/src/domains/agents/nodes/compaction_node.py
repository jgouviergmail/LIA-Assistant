"""
Compaction node: Intelligent conversation history summarization.

Runs as the entry point of the LangGraph graph, before the router.
Checks if conversation history exceeds the dynamic token threshold,
and if safe, replaces old messages with a concise LLM-generated summary.

Also handles the /resume command to force compaction regardless of threshold.

Key design: The summary is injected as a SystemMessage (not HumanMessage)
so the router does not interpret it as a user action request. For /resume,
a short conversational HumanMessage asks the assistant to confirm compaction.

Phase: F4 — Intelligent Context Compaction
Created: 2026-03-16
"""

from typing import Any

from langchain_core.messages import BaseMessage, HumanMessage, RemoveMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from src.core.config import settings
from src.domains.agents.models import MessagesState
from src.domains.agents.services.compaction_service import CompactionService
from src.infrastructure.observability.logging import get_logger
from src.infrastructure.observability.metrics_compaction import (
    compaction_skipped_total,
)

logger = get_logger(__name__)

# Command that triggers forced compaction
_RESUME_COMMAND = "/resume"


def _is_resume_command(messages: list[BaseMessage]) -> bool:
    """Check if the last user message is the /resume command."""
    if not messages:
        return False
    last_msg = messages[-1]
    if not isinstance(last_msg, HumanMessage):
        return False
    content = last_msg.content if isinstance(last_msg.content, str) else str(last_msg.content)
    return content.strip().lower() == _RESUME_COMMAND


async def compaction_node(state: MessagesState, config: RunnableConfig) -> dict[str, Any]:
    """
    LangGraph node for context compaction.

    Logic:
    1. If disabled → pass-through (return empty dict)
    2. If /resume command → force compaction (skip threshold check)
    3. If should_compact() and is_safe_to_compact() → compact
    4. Otherwise → pass-through

    When compaction occurs:
    - Old messages are removed via RemoveMessage
    - Summary is injected as a SystemMessage (context, not routed)
    - For /resume: a conversational HumanMessage triggers confirmation response
    - For auto-trigger: the real user message is in preserved recent messages
    - The /resume message is consumed (not forwarded to router)

    Returns:
        Dict with updated state fields, or empty dict for pass-through.
    """
    if not settings.compaction_enabled:
        return {}

    messages: list[BaseMessage] = state.get("messages", [])
    if not messages:
        return {}

    service = CompactionService()
    is_resume = _is_resume_command(messages)

    # Determine if compaction is needed
    force_compact = is_resume
    should_compact = force_compact or service.should_compact(messages)

    if not should_compact:
        return {}

    # Safety check: don't compact if HITL state would be corrupted
    safety = service.is_safe_to_compact(state)
    if not safety.safe:
        logger.info(
            "compaction_skipped_unsafe",
            reason=safety.reason,
            is_resume=is_resume,
        )
        # If /resume was the command but we can't compact, still consume it
        if is_resume:
            return _consume_resume_command(messages, safety.reason)
        return {}

    # Perform compaction
    language = state.get("user_language", "en")
    preserve_n = settings.compaction_preserve_recent_messages

    result = await service.compact(
        messages=messages,
        preserve_recent_n=preserve_n,
        language=language,
        config=config,
    )

    if result.strategy == "noop" or not result.summary:
        if is_resume:
            return _consume_resume_command(messages, "nothing_to_compact")
        return {}

    # Build the new message list:
    # 1. RemoveMessage for each old message that was compacted
    # 2. SystemMessage with the summary (context only — NOT routed by router)
    # 3. For /resume: conversational HumanMessage to trigger confirmation
    compacted_count = state.get("compaction_count", 0) + 1

    # Identify messages to remove (all non-system, non-recent messages)
    non_system = [m for m in messages if not isinstance(m, SystemMessage)]
    preserve_n_effective = min(preserve_n, len(non_system))
    to_remove = non_system[:-preserve_n_effective] if preserve_n_effective > 0 else non_system

    new_messages: list[BaseMessage] = []

    # Remove old messages
    for msg in to_remove:
        if hasattr(msg, "id") and msg.id:
            new_messages.append(RemoveMessage(id=msg.id))

    # If /resume, also remove the /resume message itself
    if is_resume and messages:
        last_msg = messages[-1]
        if hasattr(last_msg, "id") and last_msg.id:
            new_messages.append(RemoveMessage(id=last_msg.id))

    # Summary as SystemMessage — provides context without triggering router actions.
    # The router takes messages[-1] as the user query; a SystemMessage won't be picked up.
    summary_system = SystemMessage(
        content=(
            f"[Conversation history compacted — compaction #{compacted_count}. "
            f"{result.tokens_saved} tokens saved. "
            f"Strategy: {result.strategy}.]\n\n{result.summary}"
        ),
    )
    new_messages.append(summary_system)

    # For /resume: add a conversational HumanMessage so the router routes to response_node
    # and the assistant confirms the compaction to the user.
    if is_resume:
        new_messages.append(
            HumanMessage(
                content=(
                    f"Conversation history has been compacted "
                    f"({result.tokens_saved} tokens saved). "
                    f"Please confirm this to me briefly."
                ),
            )
        )

    logger.info(
        "compaction_node_applied",
        messages_removed=len(to_remove),
        tokens_saved=result.tokens_saved,
        strategy=result.strategy,
        compaction_count=compacted_count,
        is_resume=is_resume,
    )

    return {
        "messages": new_messages,
        "compaction_summary": result.summary,
        "compaction_count": compacted_count,
    }


def _consume_resume_command(messages: list[BaseMessage], reason: str) -> dict[str, Any]:
    """
    Consume the /resume command without compacting.

    Replaces /resume with a conversational message so the router
    routes to response_node for a confirmation instead of trying to act.
    """
    new_messages: list[BaseMessage] = []

    # Remove the /resume message
    last_msg = messages[-1]
    if hasattr(last_msg, "id") and last_msg.id:
        new_messages.append(RemoveMessage(id=last_msg.id))

    # Replace with conversational message — router will route to response_node
    new_messages.append(
        HumanMessage(content=f"Context compaction was skipped ({reason}). Please let me know.")
    )

    compaction_skipped_total.labels(reason=f"resume_{reason}").inc()

    return {"messages": new_messages}
