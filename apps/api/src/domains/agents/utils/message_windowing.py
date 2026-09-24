"""
Message windowing utilities for optimizing LLM latency in long conversations.

Provides reusable functions for creating message "windows" - keeping only recent
conversation turns while preserving important system messages. This reduces token
count sent to LLMs, improving response time without losing contextual accuracy.

Key principle: Balance latency vs. context
- Response node needs rich context (creative synthesis) → large window
- ReAct history is windowed via get_windowed_messages() directly, or by blocks
  anchored on the turn counter under the cross-turn cache flag (ADR-309)
- Store persists ALL contexts → no loss of business context (contacts, entities, etc.)

Note (ADR-094): per-node windowing helpers for router/planner/orchestrator were
removed as dead scaffolding — they were never wired. State-level truncation
(add_messages_with_truncate) already bounds tokens; deliberate per-node windowing
is deferred to the latency-optimization effort (with routing-quality benchmarks).

All functions preserve immutability - input lists are never modified.
"""

import math

from langchain_core.messages import BaseMessage, HumanMessage

from src.core.config import settings
from src.domains.agents.utils.message_filters import (
    extract_system_messages,
    filter_conversational_messages,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


def history_block_turns(window_size: int) -> int:
    """How many turns a block-windowed history drops at once (ADR-309).

    The configured share of the window (``react_cross_turn_history_block_fraction``),
    rounded up, and never under one turn.

    Args:
        window_size: The history window, in turns.

    Returns:
        The block size, in turns.
    """
    return max(1, math.ceil(window_size * settings.react_cross_turn_history_block_fraction))


def block_window_turns(window_size: int, block_size: int, turn_id: int | None) -> int:
    """How many previous turns a block-windowed history keeps at turn ``turn_id``.

    Between ``window_size`` and ``window_size + block_size - 1``, as a function of the
    conversation's turn counter ALONE: it grows by one turn per turn and drops a whole
    block at once, so the history's first turn only moves when a block goes. Nothing
    here reads the thread's length, which the messages reducer shortens from the head
    in the middle of a turn (ADR-309, amended 2026-09-24). The phase makes a thread
    that still holds each of its ``turn_id - 1`` previous turns keep exactly what the
    blocks kept before.

    Args:
        window_size: The history window, in turns.
        block_size: How many turns go at once (``history_block_turns``).
        turn_id: The conversation's turn counter (``current_turn_id``); None slides.

    Returns:
        The number of previous turns to keep.
    """
    if turn_id is None or block_size <= 1:
        return window_size
    return window_size + (turn_id - 1 - window_size) % block_size


def _split_turns(
    conversational: list[BaseMessage],
) -> tuple[list[BaseMessage], list[list[BaseMessage]]]:
    """Split conversational messages into turns, each opened by its HumanMessage.

    Args:
        conversational: Output of ``filter_conversational_messages``, in order.

    Returns:
        The messages before the first HumanMessage — an answer whose question the
        reducer trimmed, or a message LIA sent first — and the turns, in order.
    """
    preamble: list[BaseMessage] = []
    turns: list[list[BaseMessage]] = []
    for message in conversational:
        if isinstance(message, HumanMessage):
            turns.append([message])
        elif turns:
            turns[-1].append(message)
        else:
            preamble.append(message)
    return preamble, turns


def get_block_windowed_messages(
    messages: list[BaseMessage],
    *,
    window_size: int,
    block_size: int,
    turn_id: int | None,
) -> list[BaseMessage]:
    """SystemMessages + the last previous turns, dropped by blocks anchored on the turn counter.

    The ReAct loop's history under ``REACT_CROSS_TURN_CACHE_ENABLED`` (ADR-309): every
    call of a turn must resend the previous call's prompt, and each turn's history must
    extend the previous turn's until a block goes, or no provider's prompt cache reads
    it again. Two rules make that hold:

    - **The count comes from the turn counter** (``block_window_turns``) and is taken
      from the END: a head trim — the reducer's, on every tool result of a long turn —
      that leaves the kept turns in place moves nothing. Aligned on the thread's length,
      each trim moved the block boundary (measured in production on 2026-09-24: three
      calls of one routine run re-billed after the tools).
    - **A turn is kept whole, from its HumanMessage**, so the history never opens on an
      answer whose question is gone.

    When the reducer has trimmed into the block, the window proper (``window_size``
    turns) is kept — a further trim cannot move it while it holds; while the thread
    holds fewer turns than the block wants, it therefore slides by one turn per turn,
    as before ADR-309. A history shorter than the window is kept whole, a message
    LIA sent first included. SystemMessages are hoisted first, as before: a
    compaction summary sits where compaction appended it, so the one head trim that
    changes the view is the one that takes it.

    Args:
        messages: Previous turns' messages (the current turn excluded).
        window_size: The history window, in turns (0 or less: SystemMessages only).
        block_size: How many turns go at once (``history_block_turns``).
        turn_id: The conversation's turn counter (``current_turn_id``); None slides.

    Returns:
        SystemMessages, then the kept turns' conversational messages, in order.
    """
    if not messages:
        return []
    system_messages = extract_system_messages(messages)
    if window_size <= 0:
        return system_messages

    preamble, turns = _split_turns(filter_conversational_messages(messages))
    wanted = block_window_turns(window_size, block_size, turn_id)
    keep = wanted if len(turns) >= wanted else window_size
    if len(turns) >= keep:
        kept = [message for turn in turns[-keep:] for message in turn]
    else:
        kept = [*preamble, *(message for turn in turns for message in turn)]

    result = [*system_messages, *kept]
    # Counts only. ``turns_available < turns_wanted`` is the reducer trimming into
    # the block: the loop then keeps the window proper (see above).
    logger.info(
        "message_windowing_complete",
        input_messages=len(messages),
        output_messages=len(result),
        window_size=window_size,
        block_size=block_size,
        turn_id=turn_id,
        turns_wanted=wanted,
        turns_available=len(turns),
        turns_kept=min(keep, len(turns)),
        reduction_percent=int((1 - len(result) / len(messages)) * 100),
    )
    return result


def get_windowed_messages(
    messages: list[BaseMessage],
    window_size: int | None = None,
    include_system: bool = True,
) -> list[BaseMessage]:
    """
    Create a windowed view of messages - keeping system messages + recent N turns.

    A "turn" consists of one HumanMessage + corresponding AIMessage(s).
    Window size controls how many recent turns are kept.

    This function:
    1. Extracts SystemMessages (if include_system=True)
    2. Filters to conversational messages (removes ToolMessage, AIMessage with tool_calls)
    3. Keeps last N turns (window_size * 2 messages: N HumanMessages + N AIMessages)
    4. Returns SystemMessages + windowed conversational messages in chronological order

    Args:
        messages: Full conversation history from state.
        window_size: Number of conversation TURNS to keep (1 turn = user + assistant pair).
                     If None, uses settings.default_message_window_size (5).
                     Set to 0 or negative to return only system messages.
        include_system: Whether to include SystemMessages in output (default: True).
                        SystemMessages are always kept regardless of window size.

    Returns:
        Windowed message list: SystemMessages (if included) + last N turns.
        If window_size covers entire history, returns all conversational messages.

    Example:
        >>> # Router node - fast routing with minimal context
        >>> windowed = get_windowed_messages(state["messages"], window_size=5)
        >>> # Returns: [SystemMessage] + last 10 messages (5 HumanMessage + 5 AIMessage)

        >>> # Planner node - more context for planning
        >>> windowed = get_windowed_messages(state["messages"], window_size=10)
        >>> # Returns: [SystemMessage] + last 20 messages (10 turns)

        >>> # Short conversation (3 turns total) with window_size=5
        >>> windowed = get_windowed_messages(messages, window_size=5)
        >>> # Returns: [SystemMessage] + all 6 messages (window larger than history)

    Performance Impact:
        - 5 turns (router): Reduces 50-turn conversation from ~7500 tokens to ~500 tokens
        - 10 turns (planner): Reduces from ~12400 tokens to ~1500 tokens
        - 20 turns (response): Reduces from ~6000 tokens to ~3000 tokens

    Note:
        Contextual references (e.g., "Affiche ses détails" referencing earlier search)
        are resolved via Store, not message history. Store persists all contexts
        regardless of windowing, ensuring no loss of business context.

    Related:
        - filter_conversational_messages(): Used internally to clean message types
        - extract_system_messages(): Used internally to preserve system prompts
        - Store (ContextStore): Preserves business context independently of windows
    """
    if not messages:
        return []

    # Use default window size from settings if not specified
    if window_size is None:
        window_size = settings.default_message_window_size

    # Handle edge cases
    if window_size <= 0:
        # Return only system messages (if requested)
        return extract_system_messages(messages) if include_system else []

    # Step 1: Extract system messages (always preserved)
    system_messages = extract_system_messages(messages) if include_system else []

    # Step 2: Filter to conversational messages only (remove tool execution details)
    conversational = filter_conversational_messages(messages)

    # Step 3: Calculate how many messages to keep
    # Each turn = 2 messages (HumanMessage + AIMessage)
    # BUT some turns may have only HumanMessage (no response yet) or multiple AIMessages
    # So we use a simpler heuristic: keep last (window_size * 2) conversational messages
    max_conversational_messages = window_size * 2

    # Step 4: Keep last N conversational messages
    if len(conversational) > max_conversational_messages:
        recent_conversational = conversational[-max_conversational_messages:]
        logger.debug(
            "windowing_applied",
            original_count=len(messages),
            conversational_count=len(conversational),
            window_size=window_size,
            windowed_count=len(recent_conversational),
            system_count=len(system_messages),
            total_output=len(system_messages) + len(recent_conversational),
        )
    else:
        # Window is larger than history - keep everything
        recent_conversational = conversational
        logger.debug(
            "windowing_skipped_small_history",
            original_count=len(messages),
            conversational_count=len(conversational),
            window_size=window_size,
            reason="history smaller than window",
        )

    # Step 5: Combine system + windowed conversational messages
    # Preserve chronological order: system messages first, then conversational
    result = system_messages + recent_conversational

    logger.info(
        "message_windowing_complete",
        input_messages=len(messages),
        output_messages=len(result),
        window_size=window_size,
        reduction_percent=int((1 - len(result) / len(messages)) * 100) if messages else 0,
    )

    return result


def get_response_windowed_messages(messages: list[BaseMessage]) -> list[BaseMessage]:
    """
    Get windowed messages optimized for response node (creative synthesis).

    Response node needs rich conversational context to generate:
    - Natural, contextual responses
    - References to earlier conversation
    - Creative synthesis of agent results

    Uses settings.response_message_window_size (default: 20 turns).

    Args:
        messages: Full conversation history.

    Returns:
        SystemMessages + last 20 turns (~40 messages).

    Performance:
        Reduces response TTFT at 50 turns from ~2500ms to ~1200ms (52% improvement).

    Example:
        >>> # In response_node.py
        >>> windowed = get_response_windowed_messages(state[STATE_KEY_MESSAGES])
        >>> conversational = filter_conversational_messages(windowed)
        >>> # Now send to response LLM
    """
    return get_windowed_messages(messages, window_size=settings.response_message_window_size)


def extract_last_user_message(messages: list[BaseMessage]) -> str | None:
    """
    Extract content from the most recent HumanMessage.

    Utility function for extracting user query from windowed or full message history.

    Args:
        messages: Message list (windowed or full).

    Returns:
        Content of last HumanMessage, or None if no user messages found.

    Example:
        >>> windowed = get_response_windowed_messages(state["messages"])
        >>> user_query = extract_last_user_message(windowed)
        >>> # user_query: "Show the details of the first contact"
    """
    for msg in reversed(messages):
        if isinstance(msg, HumanMessage):
            return msg.content
    return None


__all__ = [
    "block_window_turns",
    "extract_last_user_message",
    "get_block_windowed_messages",
    "get_response_windowed_messages",
    "get_windowed_messages",
    "history_block_turns",
]
