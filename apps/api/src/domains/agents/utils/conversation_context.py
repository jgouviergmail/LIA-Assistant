"""
Conversation Context Injection for LangGraph Nodes.

This module provides utilities for injecting conversation history into LLM prompts
for the main orchestration nodes (Router, Planner, Response).

Architecture Overview:
======================

There are TWO distinct message management mechanisms in the system:

1. **MESSAGE_WINDOW_SIZE** (for orchestration nodes):
   - Router: 5 turns (fast routing decisions, minimal context)
   - Planner: 10 turns (moderate context for plan generation)
   - Response: 20 turns (rich context for creative synthesis)
   - Used by: router_node, planner_node, response_node
   - Purpose: Reduce latency by limiting context sent to LLM

2. **AGENT_HISTORY_KEEP_LAST** (for ReAct agents):
   - Default: 50 messages
   - Used by: contacts_agent, emails_agent, calendar_agent, etc.
   - Purpose: Keep tool results visible for context resolution
   - Implemented via: MessageHistoryMiddleware

Why Different Values?
=====================
- Orchestration nodes need SPEED (routing, planning are latency-critical)
- ReAct agents need CONTEXT (tool results must be visible for follow-up actions)
- Store persists ALL business context regardless of windowing

Usage Pattern:
==============
All orchestration nodes should:
1. Apply message windowing: get_*_windowed_messages()
2. Filter to conversational: filter_conversational_messages()
3. Format for prompt: format_conversation_history()
4. Inject into prompt template via {conversation_history} placeholder

The prompts contain explicit {conversation_history} placeholders for visibility.

HTML Stripping:
===============
AIMessages may contain HTML cards (lia-card, lia-contacts-list, etc.) injected for display.
When formatting history for LLM prompts, HTML is stripped to prevent the LLM from
reformulating it as Markdown links. The LLM only needs user messages and text summaries,
not the formatted HTML which is for end-user display only.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage

from src.domains.agents.utils.message_filters import (
    filter_for_llm_context,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def format_conversation_history(
    messages: list[BaseMessage],
    max_content_length: int = 500,
) -> str:
    """
    Format conversation messages as readable text for prompt injection.

    Converts a list of LangChain messages into a human-readable format
    suitable for injection into prompt templates via {conversation_history}.

    Args:
        messages: Windowed and filtered conversation messages
        max_content_length: Maximum length per message content (truncated if longer)

    Returns:
        Formatted string with conversation history, or "(aucun historique)" if empty.

    Format:
        [USER]: Message content here...
        [ASSISTANT]: Response content here...
        [USER]: Another message...

    Example:
        >>> messages = [HumanMessage("Bonjour"), AIMessage("Salut!")]
        >>> text = format_conversation_history(messages)
        >>> print(text)
        [USER]: Bonjour
        [ASSISTANT]: Salut!
    """
    if not messages:
        return "(aucun historique)"

    lines = []
    for msg in messages:
        content = getattr(msg, "content", "")

        # Truncate long content
        if len(content) > max_content_length:
            content = content[:max_content_length] + "..."

        # Skip empty content
        if not content.strip():
            continue

        # Format based on message type
        if isinstance(msg, HumanMessage):
            lines.append(f"[USER]: {content}")
        elif isinstance(msg, AIMessage):
            lines.append(f"[ASSISTANT]: {content}")
        elif isinstance(msg, SystemMessage):
            # Skip system messages in history display
            continue
        else:
            lines.append(f"[{type(msg).__name__.upper()}]: {content}")

    if not lines:
        return "(aucun historique)"

    return "\n".join(lines)


def inject_conversation_history(
    prompt_messages: list[BaseMessage],
    conversation_messages: list[BaseMessage],
    run_id: str | None = None,
    node_name: str = "unknown",
) -> list[BaseMessage]:
    """
    Inject conversation history into prompt messages.

    This function inserts filtered conversation history between the SystemMessage
    and the final HumanMessage in a prompt, enabling the LLM to see prior context.

    Architecture:
        Input:  [SystemMessage, HumanMessage]
        Output: [SystemMessage, ...conversation..., HumanMessage]

    This is used by nodes that cannot use ChatPromptTemplate with MessagesPlaceholder
    (e.g., Planner where JSON examples contain {} that would be parsed as variables).

    Args:
        prompt_messages: Original prompt [SystemMessage, HumanMessage]
        conversation_messages: Windowed conversation history from state
        run_id: Run ID for logging (optional)
        node_name: Node name for logging (e.g., "planner")

    Returns:
        New list with conversation history injected between system and human messages.
        If injection fails, returns original prompt_messages unchanged.

    Example:
        >>> prompt = [SystemMessage("You are..."), HumanMessage("Generate plan for: X")]
        >>> history = [HumanMessage("Hi"), AIMessage("Hello!"), HumanMessage("Search Y")]
        >>> result = inject_conversation_history(prompt, history, run_id="123", node_name="planner")
        >>> # result = [SystemMessage, HumanMessage("Hi"), AIMessage("Hello!"), HumanMessage("Search Y"), HumanMessage("Generate plan...")]

    Note:
        - Filters conversation_messages to keep only conversational messages
        - Removes ToolMessage and AIMessage with tool_calls
        - Preserves message order from original conversation
    """
    # Validate input
    if not prompt_messages or len(prompt_messages) < 2:
        logger.warning(
            f"{node_name}_inject_history_invalid_prompt",
            run_id=run_id,
            prompt_count=len(prompt_messages) if prompt_messages else 0,
            reason="prompt_messages must have at least 2 elements",
        )
        return prompt_messages

    if not conversation_messages:
        logger.debug(
            f"{node_name}_inject_history_no_conversation",
            run_id=run_id,
            reason="No conversation messages to inject",
        )
        return prompt_messages

    # Filter to LLM context: HumanMessage + ToolMessage (JSON) + simple AIMessage (no HTML)
    # Excludes AIMessage with HTML formatting to prevent LLM reformulating as Markdown
    conversational = filter_for_llm_context(conversation_messages)

    if not conversational:
        logger.debug(
            f"{node_name}_inject_history_no_conversational",
            run_id=run_id,
            original_count=len(conversation_messages),
            reason="No messages after filtering for LLM context",
        )
        return prompt_messages

    # Extract system message (first) and final human message (last)
    system_message = prompt_messages[0]
    final_human_message = prompt_messages[-1]

    # Validate types
    if not isinstance(system_message, SystemMessage):
        logger.warning(
            f"{node_name}_inject_history_invalid_system",
            run_id=run_id,
            actual_type=type(system_message).__name__,
            reason="First message must be SystemMessage",
        )
        return prompt_messages

    if not isinstance(final_human_message, HumanMessage):
        logger.warning(
            f"{node_name}_inject_history_invalid_human",
            run_id=run_id,
            actual_type=type(final_human_message).__name__,
            reason="Last message must be HumanMessage",
        )
        return prompt_messages

    # Build new prompt: [SystemMessage] + [conversation] + [HumanMessage]
    result = [system_message] + list(conversational) + [final_human_message]

    logger.info(
        f"{node_name}_conversation_history_injected",
        run_id=run_id,
        history_count=len(conversational),
        total_messages=len(result),
        original_conversation_count=len(conversation_messages),
    )

    return result


def get_conversation_summary_for_logging(
    messages: list[BaseMessage],
    max_preview_length: int = 100,
) -> list[dict]:
    """
    Create a summary of conversation messages for logging purposes.

    Args:
        messages: Conversation messages to summarize
        max_preview_length: Maximum length of content preview

    Returns:
        List of dicts with message type and content preview
    """
    summary = []
    for msg in messages:
        msg_type = type(msg).__name__
        content = getattr(msg, "content", "")
        preview = (
            content[:max_preview_length] + "..." if len(content) > max_preview_length else content
        )
        summary.append(
            {
                "type": msg_type,
                "preview": preview,
            }
        )
    return summary


__all__ = [
    "format_conversation_history",
    "get_conversation_summary_for_logging",
    "inject_conversation_history",
]
