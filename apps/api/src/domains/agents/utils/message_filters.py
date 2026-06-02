"""
Message filtering utilities for LangGraph agents.

Provides reusable functions for filtering and processing message lists
in different contexts (response generation, agent input, tool context, etc.).

All functions preserve immutability - input lists are never modified.
"""

import re

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.constants import (
    COMPACTION_SUMMARY_MARKER,
    CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER,
    CONTEXT_RESULTS_DISPLAYED_PLACEHOLDER,
)
from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

# Markdown style markers to strip when neutralizing prior assistant answers for the
# response LLM's history (see ``_neutralize_assistant_formatting``). Each pattern is
# anchored or scoped so it removes only *formatting* tokens, never the surrounding
# textual content (e.g. ``2*3`` or an in-word underscore is left untouched).
_MD_FENCED_CODE_RE = re.compile(r"^[ \t]*```[^\n]*$", re.MULTILINE)
_MD_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.MULTILINE)
_MD_BLOCKQUOTE_RE = re.compile(r"^[ \t]{0,3}>[ \t]?", re.MULTILINE)
_MD_THEMATIC_BREAK_RE = re.compile(r"^[ \t]{0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$", re.MULTILINE)
_MD_LIST_BULLET_RE = re.compile(r"^([ \t]*)[-*+][ \t]+", re.MULTILINE)
_MD_TABLE_DELIM_RE = re.compile(r"^[ \t]{0,3}\|?[ \t:|-]+\|?[ \t]*$", re.MULTILINE)
_MD_BOLD_RE = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_MD_ITALIC_RE = re.compile(r"(?<![\w*_])([*_])(?=\S)(.+?)(?<=\S)\1(?![\w*_])")
_MD_INLINE_CODE_RE = re.compile(r"`([^`\n]+)`")
_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)\s]+\)")
_MULTI_BLANK_LINE_RE = re.compile(r"\n{3,}")


def _strip_markdown_syntax(text: str) -> str:
    """Remove common Markdown *formatting* tokens, preserving textual content.

    Used to neutralize the style of prior assistant answers in the response LLM's
    conversational history (via ``_neutralize_assistant_formatting``) so they cannot act
    as a Markdown style precedent that fights the HTML output directive. This is
    intentionally conservative: it strips only unambiguous formatting markers (headings,
    emphasis, list bullets, thematic breaks, table delimiter rows, inline code,
    blockquotes, and link syntax) and leaves all other characters — including
    ordered-list numbers and in-word ``*``/``_`` — intact.

    Args:
        text: Raw message text (already coerced to ``str``).

    Returns:
        The text with Markdown formatting markers removed and runs of blank lines
        collapsed. Content words, names, dates and numbers are preserved verbatim.
    """
    text = _MD_FENCED_CODE_RE.sub("", text)
    text = _MD_THEMATIC_BREAK_RE.sub("", text)
    text = _MD_TABLE_DELIM_RE.sub("", text)
    text = _MD_HEADING_RE.sub("", text)
    text = _MD_BLOCKQUOTE_RE.sub("", text)
    text = _MD_LIST_BULLET_RE.sub(r"\1", text)
    text = _MD_LINK_RE.sub(r"\1", text)
    text = _MD_BOLD_RE.sub(r"\2", text)
    text = _MD_ITALIC_RE.sub(r"\2", text)
    text = _MD_INLINE_CODE_RE.sub(r"\1", text)
    # Drop residual table cell pipes, then collapse blank-line runs created above.
    text = text.replace("|", " ")
    text = _MULTI_BLANK_LINE_RE.sub("\n\n", text)
    return text.strip()


def _neutralize_assistant_formatting(content: str) -> str:
    """Render a prior assistant answer as style-free text tagged for the response LLM.

    Produces a representation that preserves *what* was answered (for conversational
    continuity) while removing every *style* signal — both HTML and Markdown — so the
    response LLM cannot infer an output format from the history and only obeys the
    active formatting directive. The result is prefixed with
    ``CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER`` so the model treats it as a stripped
    excerpt rather than a style precedent.

    HTML answers keep the existing minimization (text before the first tag only),
    avoiding re-injection of full card payloads into context. The call is idempotent:
    content already carrying the marker is returned unchanged.

    Args:
        content: The assistant message content (already coerced to ``str``).

    Returns:
        Marker-prefixed, style-neutralized text. If no textual content remains
        (e.g. an HTML-only data card), the bare marker is returned.
    """
    if content.startswith(CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER):
        # Idempotency guard: never double-strip or double-prefix.
        return content

    # For HTML answers, keep only the leading prose (mirrors the non-neutralized
    # branch) so we do not pour entire card markup back into the context window.
    if 'class="lia-' in content or "class='lia-" in content:
        text = _extract_text_before_html(content)
    else:
        text = content

    text = _strip_markdown_syntax(text)
    if not text:
        return CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER
    return f"{CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER} {text}"


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


def filter_for_llm_context(
    messages: list[BaseMessage],
    *,
    neutralize_formatting: bool = False,
) -> list[BaseMessage]:
    """
    Filter messages to keep user input, JSON tool results, and simple chat AI responses.

    This filter is designed for building conversation history that the LLM sees.
    It excludes AI responses containing HTML formatting (lia-card, etc.) to prevent
    the LLM from reformulating HTML as Markdown.

    Keeps:
    - HumanMessage (user input)
    - ToolMessage (JSON results from tools)
    - AIMessage WITHOUT HTML content (simple chat responses)
    - SystemMessage carrying a compaction summary (prefixed with
      ``COMPACTION_SUMMARY_MARKER``) — the only legitimate SystemMessage here, as it
      holds the compacted conversation history and is not re-injected elsewhere.

    Removes:
    - AIMessage with tool_calls (internal agent reasoning)
    - AIMessage containing HTML (class="lia-) - formatted display responses
    - Every OTHER SystemMessage — internal node scaffolding (the ReAct agent system
      prompt with its PLAN/OBSERVE workflow + tool-calling role, memory/skills context
      blocks, ``__`` internal markers) that must never reach the response synthesizer.

    Args:
        messages: Full message history from state.
        neutralize_formatting: When ``True`` (used only by the response node in the
            ``html`` display mode), every retained assistant answer is rewritten to
            style-free text tagged with ``CONTEXT_PRIOR_ANSWER_UNFORMATTED_MARKER``
            (see ``_neutralize_assistant_formatting``). This removes the Markdown/HTML
            style precedent that otherwise accumulates in history and overrides the
            HTML output directive over multi-turn conversations. Defaults to ``False``,
            i.e. the historical behaviour (Markdown answers kept verbatim, HTML answers
            reduced to their leading prose) — so the ``cards`` and ``markdown`` display
            modes, the planner path, and all existing callers are byte-for-byte
            unchanged.

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
            # Handle AI messages containing HTML formatting. Gemini 3.x content is
            # list[dict] blocks; coerce to text so the HTML-card check works.
            content = coerce_content_to_text(getattr(msg, "content", ""))
            if neutralize_formatting:
                # html display mode: strip every style signal (HTML + Markdown) and
                # tag the prior answer so it cannot act as a style precedent.
                filtered.append(AIMessage(content=_neutralize_assistant_formatting(content)))
                continue
            if 'class="lia-' in content or "class='lia-" in content:
                # Extract text before HTML, or use placeholder to indicate response was given
                # This prevents LLM from thinking previous query is unanswered
                text_before_html = _extract_text_before_html(content)
                if text_before_html:
                    filtered.append(AIMessage(content=text_before_html))
                else:
                    # Placeholder so LLM knows query was handled
                    filtered.append(AIMessage(content=CONTEXT_RESULTS_DISPLAYED_PLACEHOLDER))
                continue
            # Keep simple chat responses
            filtered.append(msg)
        elif isinstance(msg, SystemMessage):
            # Keep ONLY the compaction summary. It carries the compacted conversation
            # history and is the response LLM's sole source for it (the `compaction_summary`
            # state field is not re-injected into the response prompt). Every OTHER
            # SystemMessage in state["messages"] is internal node scaffolding — notably the
            # ReAct agent system prompt (with its PLAN/OBSERVE workflow + tool-calling role)
            # injected by react_setup_node, plus redundant memory/skills context blocks. If
            # those reach the response synthesizer, the model mimics the agent's reasoning
            # structure (PLAN/OBSERVATION leak) or adopts its role ("I'll search…, call
            # tool…") instead of delivering the answer. So we drop them here.
            # ``content`` may be a list (provider block format); only a str summary qualifies.
            raw_content = getattr(msg, "content", "")
            content = raw_content if isinstance(raw_content, str) else ""
            if content.startswith(COMPACTION_SUMMARY_MARKER):
                filtered.append(msg)
            # else: drop ReAct scaffolding, memory/skills context, and "__" internal markers

    logger.debug(
        "filter_for_llm_context",
        original_count=len(messages),
        filtered_count=len(filtered),
    )

    return filtered


def drop_current_turn_responses(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Drop every message that follows the last ``HumanMessage`` in the list.

    The response synthesizer builds its conversation *history* from
    ``state["messages"]``. In the ReAct passthrough path the agent's final answer is
    appended to ``state["messages"]`` during the current turn, so without this pruning
    the history would end with a fully-formed assistant answer to the very question
    being answered. The synthesis LLM then sees the turn as already complete and emits
    a dismissive or minimal reply ("you already got the answer") instead of formatting
    the data — dropping the initiative enrichment and HTML directive. The answer stays
    available to it through the AUTHORITATIVE ``agent_results`` block, so nothing is lost.

    Removing everything after the last user message yields history = strictly prior turns
    plus the current user query, matching the planner path (where the current turn has no
    assistant message in ``state["messages"]`` yet, making this a no-op there).

    Args:
        messages: Full message history from state, in chronological order.

    Returns:
        A new list keeping all messages up to and including the last ``HumanMessage``.
        If no ``HumanMessage`` is present, the input is returned unchanged (defensive:
        nothing identifies a "current turn" to prune).

    Example:
        >>> from langchain_core.messages import HumanMessage, AIMessage
        >>> msgs = [
        ...     HumanMessage(content="prev"),
        ...     AIMessage(content="prev answer"),
        ...     HumanMessage(content="search my appointments"),
        ...     AIMessage(content="Here are your 3 appointments..."),  # current-turn ReAct answer
        ... ]
        >>> [type(m).__name__ for m in drop_current_turn_responses(msgs)]
        ['HumanMessage', 'AIMessage', 'HumanMessage']
    """
    last_human_idx = -1
    for idx, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human_idx = idx

    if last_human_idx == -1:
        return list(messages)

    return list(messages[: last_human_idx + 1])


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
    "drop_current_turn_responses",
    "extract_system_messages",
    "filter_by_message_types",
    "filter_conversational_messages",
    "filter_for_llm_context",
    "filter_tool_messages",
    "remove_orphan_tool_messages",
    "split_messages_by_turn",
]
