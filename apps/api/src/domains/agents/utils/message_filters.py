"""
Message filtering utilities for LangGraph agents.

Provides reusable functions for filtering and processing message lists
in different contexts (response generation, agent input, tool context, etc.).

All functions preserve immutability - input lists are never modified.
"""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def _extract_text_before_html(content: str) -> str:
    """
    Extract text content before any HTML tags.

    When AI responses contain both commentary text and HTML cards (lia-card),
    this extracts just the text portion to preserve context without the HTML.

    Args:
        content: Full AI message content possibly containing HTML.

    Returns:
        Text before first HTML tag, stripped. Empty string if no text found.

    Example:
        >>> _extract_text_before_html("Voici la météo!\\n\\n<div class='lia-card'>...")
        "Voici la météo!"
        >>> _extract_text_before_html("<div class='lia-card'>...")
        ""
    """
    import re

    # Find first HTML tag position
    html_match = re.search(r"<[a-zA-Z]", content)
    if html_match:
        text_before = content[: html_match.start()].strip()
        return text_before
    return content.strip()


def filter_conversational_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Filter messages to keep only conversational messages (HumanMessage and AIMessage without tool_calls).

    Removes:
    - ToolMessage (tool execution results - internal to agent)
    - AIMessage with tool_calls (agent internal reasoning)

    Keeps:
    - HumanMessage (user messages)
    - AIMessage without tool_calls (conversational responses from agents)

    This ensures response LLM only sees conversational history, not internal tool execution details.
    Agent results should be provided separately via agent_results parameter in prompts.

    Args:
        messages: Full message history from state.

    Returns:
        Filtered list containing only conversational messages.

    Example:
        >>> from langchain_core.messages import HumanMessage, AIMessage, ToolMessage
        >>> messages = [
        ...     HumanMessage(content="email de jean"),
        ...     AIMessage(content="", tool_calls=[{"id": "call_123", "name": "search"}]),  # Filtered out
        ...     ToolMessage(content='{"results": [...]}', tool_call_id="call_123"),  # Filtered out
        ...     AIMessage(content="Voici l'email de jean"),  # Kept
        ... ]
        >>> filtered = filter_conversational_messages(messages)
        >>> len(filtered)  # 2 (HumanMessage + final AIMessage)
        2

    Note:
        Used primarily in response_node to prepare clean message history for response LLM.
    """
    conversational = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Keep all user messages
            conversational.append(msg)
        elif isinstance(msg, AIMessage):
            # Only keep AI messages without tool calls (conversational responses)
            if not hasattr(msg, "tool_calls") or not msg.tool_calls:
                conversational.append(msg)
        elif isinstance(msg, SystemMessage):
            # Skip internal system markers (e.g., __PLAN_REJECTED__)
            if msg.content.startswith("__"):
                continue
        # Skip ToolMessage - these are internal tool results

    logger.debug(
        "filter_conversational_messages",
        original_count=len(messages),
        filtered_count=len(conversational),
        removed=len(messages) - len(conversational),
    )

    return conversational


def filter_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Filter messages to keep only ToolMessages.

    Useful for extracting tool execution results from message history
    for context analysis or debugging.

    Args:
        messages: Full message history.

    Returns:
        List containing only ToolMessages.

    Example:
        >>> tool_messages = filter_tool_messages(state["messages"])
        >>> # Analyze tool execution results
        >>> for tool_msg in tool_messages:
        ...     print(f"Tool: {tool_msg.name}, Result: {tool_msg.content[:50]}")
    """
    tool_messages = [msg for msg in messages if isinstance(msg, ToolMessage)]

    logger.debug(
        "filter_tool_messages",
        total_messages=len(messages),
        tool_messages_count=len(tool_messages),
    )

    return tool_messages


def filter_by_message_types(
    messages: list[BaseMessage], types: list[type[BaseMessage]]
) -> list[BaseMessage]:
    """
    Generic filter for messages by type.

    Args:
        messages: Full message history.
        types: List of message types to keep (e.g., [HumanMessage, AIMessage]).

    Returns:
        Filtered list containing only messages of specified types.

    Example:
        >>> from langchain_core.messages import HumanMessage, SystemMessage
        >>> # Keep only user messages and system messages
        >>> filtered = filter_by_message_types(messages, [HumanMessage, SystemMessage])
    """
    filtered = [msg for msg in messages if type(msg) in types]

    logger.debug(
        "filter_by_message_types",
        original_count=len(messages),
        filtered_count=len(filtered),
        types=[t.__name__ for t in types],
    )

    return filtered


def extract_system_messages(messages: list[BaseMessage]) -> list[SystemMessage]:
    """
    Extract all SystemMessages from message list.

    Useful for preserving system prompts during message truncation or filtering.

    Args:
        messages: Full message history.

    Returns:
        List of SystemMessages (empty list if none found).

    Example:
        >>> system_msgs = extract_system_messages(state["messages"])
        >>> # Always include system messages in agent input
        >>> agent_input = system_msgs + recent_messages
    """
    system_messages = [msg for msg in messages if isinstance(msg, SystemMessage)]

    logger.debug(
        "extract_system_messages",
        total_messages=len(messages),
        system_messages_count=len(system_messages),
    )

    return system_messages


def remove_orphan_tool_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Remove ToolMessages that don't have a corresponding AIMessage with tool_calls.

    This function ensures OpenAI API compatibility by maintaining the constraint:
    "messages with role 'tool' must be a response to a preceding message with 'tool_calls'"

    Orphan ToolMessages can occur after message truncation when an AIMessage with tool_calls
    is removed but its corresponding ToolMessage is kept.

    Args:
        messages: Message list potentially containing orphan ToolMessages.

    Returns:
        Cleaned message list with orphan ToolMessages removed.

    Example:
        >>> messages = [
        ...     HumanMessage(content="search contacts"),
        ...     ToolMessage(content="result", tool_call_id="call_123"),  # Orphan (no parent AIMessage)!
        ... ]
        >>> cleaned = remove_orphan_tool_messages(messages)
        >>> len(cleaned)  # 1 (ToolMessage removed)
        1

    Note:
        This function is called automatically in add_messages_with_truncate reducer
        to prevent OpenAI API errors after message truncation.
    """
    if not messages:
        return []

    # Step 1: Collect all tool_call_ids from AIMessages
    available_tool_call_ids = set()

    for msg in messages:
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            for tool_call in msg.tool_calls:
                if isinstance(tool_call, dict) and "id" in tool_call:
                    available_tool_call_ids.add(tool_call["id"])

    # Step 2: Filter messages - keep everything except orphan ToolMessages
    validated = []
    orphan_count = 0

    for msg in messages:
        if isinstance(msg, ToolMessage):
            tool_call_id = getattr(msg, "tool_call_id", None)

            if tool_call_id not in available_tool_call_ids:
                # Orphan ToolMessage - remove it
                orphan_count += 1
                logger.warning(
                    "orphan_tool_message_removed",
                    tool_call_id=tool_call_id,
                    message_content_preview=str(msg.content)[:100] if msg.content else None,
                )
                continue  # Skip this message

        # Keep all other messages (HumanMessage, AIMessage, SystemMessage, valid ToolMessage)
        validated.append(msg)

    # Log summary if orphans were found
    if orphan_count > 0:
        logger.info(
            "orphan_tool_messages_removed",
            original_count=len(messages),
            validated_count=len(validated),
            orphans_removed=orphan_count,
        )

    return validated


def filter_for_llm_context(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Filter messages to keep user input, JSON tool results, and simple chat AI responses.

    This filter is designed for building conversation history that the LLM sees.
    It excludes AI responses containing HTML formatting (lia-card, etc.) to prevent
    the LLM from reformulating HTML as Markdown.

    Keeps:
    - HumanMessage (user input)
    - ToolMessage (JSON results from tools)
    - AIMessage WITHOUT HTML content (simple chat responses)

    Removes:
    - AIMessage with tool_calls (internal agent reasoning)
    - AIMessage containing HTML (class="lia-) - formatted display responses
    - SystemMessage starting with __ (internal markers)

    Args:
        messages: Full message history from state.

    Returns:
        Filtered list for LLM context.

    Example:
        >>> messages = [
        ...     HumanMessage(content="salut"),
        ...     AIMessage(content="Bonjour!"),  # Kept (simple chat)
        ...     HumanMessage(content="recherche contacts jean"),
        ...     ToolMessage(content='{"items": [...]}'),  # Kept (JSON)
        ...     AIMessage(content="<div class='lia-card'>...</div>"),  # Excluded (HTML)
        ... ]
        >>> filtered = filter_for_llm_context(messages)

    Note:
        Used by format_conversation_history to build clean context for response LLM.
    """
    filtered = []

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Keep all user messages
            filtered.append(msg)
        elif isinstance(msg, ToolMessage):
            # Keep tool results (JSON data)
            filtered.append(msg)
        elif isinstance(msg, AIMessage):
            # Exclude AI messages with tool_calls (internal reasoning)
            if hasattr(msg, "tool_calls") and msg.tool_calls:
                continue
            # Handle AI messages containing HTML formatting
            content = getattr(msg, "content", "") or ""
            if 'class="lia-' in content or "class='lia-" in content:
                # Extract text before HTML, or use placeholder to indicate response was given
                # This prevents LLM from thinking previous query is unanswered
                text_before_html = _extract_text_before_html(content)
                if text_before_html:
                    filtered.append(AIMessage(content=text_before_html))
                else:
                    # Placeholder so LLM knows query was handled
                    filtered.append(AIMessage(content="[Résultats affichés]"))
                continue
            # Keep simple chat responses
            filtered.append(msg)
        elif isinstance(msg, SystemMessage):
            # Skip internal system markers
            content = getattr(msg, "content", "") or ""
            if content.startswith("__"):
                continue
            filtered.append(msg)

    logger.debug(
        "filter_for_llm_context",
        original_count=len(messages),
        filtered_count=len(filtered),
    )

    return filtered


def split_messages_by_turn(
    messages: list[BaseMessage],
) -> list[tuple[HumanMessage, list[BaseMessage]]]:
    """
    Split messages into turns (user message + all responses until next user message).

    A turn consists of:
    1. HumanMessage (user input)
    2. All subsequent messages (AI, Tool, System) until next HumanMessage

    Useful for analyzing conversation flow, per-turn metrics, or turn-based cleanup.

    Args:
        messages: Full conversation history.

    Returns:
        List of tuples (HumanMessage, responses_list) representing conversation turns.

    Example:
        >>> turns = split_messages_by_turn(state["messages"])
        >>> for user_msg, responses in turns:
        ...     print(f"User: {user_msg.content}")
        ...     print(f"  Responses: {len(responses)} messages")
        >>> # Output:
        >>> # User: email de jean
        >>> #   Responses: 5 messages (AIMessage with tool_calls, ToolMessage, AIMessage)
    """
    turns = []
    current_turn: tuple[HumanMessage | None, list[BaseMessage]] = (None, [])

    for msg in messages:
        if isinstance(msg, HumanMessage):
            # Start new turn
            if current_turn[0] is not None:
                # Save previous turn
                turns.append((current_turn[0], current_turn[1]))
            current_turn = (msg, [])
        else:
            # Add response to current turn
            if current_turn[0] is not None:
                current_turn[1].append(msg)

    # Save last turn if exists
    if current_turn[0] is not None:
        turns.append((current_turn[0], current_turn[1]))

    logger.debug(
        "split_messages_by_turn",
        total_messages=len(messages),
        turns_count=len(turns),
    )

    return turns


__all__ = [
    "extract_system_messages",
    "filter_by_message_types",
    "filter_conversational_messages",
    "filter_for_llm_context",
    "filter_tool_messages",
    "remove_orphan_tool_messages",
    "split_messages_by_turn",
]
