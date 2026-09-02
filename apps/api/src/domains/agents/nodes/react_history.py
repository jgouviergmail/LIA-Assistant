"""What the ReAct loop is shown of the conversation's history.

Extracted from ``react_nodes.py`` (ADR-256), which had reached its size cap.
One cohesive subject — deciding which prior messages reach the loop's prompt
and in what shape — with no node state involved, so it is testable on its own
(``test_react_history_sentinels.py``, ``test_react_system_blocks.py``).

Two decisions live here, and they are the same decision seen twice: history is
DATA the model reads, never an example it should imitate.
"""

from __future__ import annotations

import structlog
from langchain_core.messages import AIMessage, BaseMessage

from src.core.config import settings

logger = structlog.get_logger(__name__)

__all__ = ["neutralize_widget_sentinels", "window_messages_for_react"]


def neutralize_widget_sentinels(history: list[BaseMessage]) -> list[BaseMessage]:
    """Replace host-owned widget sentinels in prior answers with a short marker.

    ``response_node`` writes the enriched answer — sentinel included — back into
    ``state["messages"]``, and this window serves that history RAW to the ReAct
    model (the response path neutralizes HTML, this one never did). The model
    learned the markup by imitation and started emitting its own, which produced
    duplicate widgets and, worse, sentinels pointing at a registry id from an
    earlier turn. Removing the example removes the incentive — and reclaims the
    tokens the markup was costing on every turn.

    Args:
        history: Windowed prior-turn messages (the current turn is untouched —
            the ReAct loop needs its own reasoning chain verbatim).

    Returns:
        A new list; messages without a sentinel are passed through by identity.
    """
    from src.core.constants import CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER
    from src.domains.agents.display.sentinel_filter import strip_widget_sentinels
    from src.infrastructure.llm.message_text import coerce_content_to_text
    from src.infrastructure.observability.metrics_registry import (
        widget_sentinels_stripped_total,
    )

    out: list[BaseMessage] = []
    stripped = 0
    for msg in history:
        if not isinstance(msg, AIMessage):
            out.append(msg)
            continue
        text = coerce_content_to_text(getattr(msg, "content", ""))
        cleaned, count = strip_widget_sentinels(
            text, replacement=CONTEXT_WIDGET_DISPLAYED_PLACEHOLDER
        )
        if not count:
            out.append(msg)
            continue
        stripped += count
        # Copy, never rebuild: a fresh ``AIMessage(content=..., id=...)`` would
        # silently drop ``tool_calls``/``additional_kwargs``. An AIMessage that
        # carried BOTH tool_calls and a sentinel would then leave its
        # ToolMessages orphaned, and the provider rejects the whole request
        # ("messages with role 'tool' must be a response to a preceding message
        # with 'tool_calls'") — or worse, `enforce_tool_message_pairing` drops
        # the carrier and its results silently. `model_copy` changes the content
        # and nothing else.
        out.append(msg.model_copy(update={"content": cleaned}))

    if stripped:
        widget_sentinels_stripped_total.labels(source="react_history").inc(stripped)
        logger.debug("react_history_widget_sentinels_neutralized", count=stripped)
    return out


def window_messages_for_react(
    messages: list[BaseMessage],
) -> list[BaseMessage]:
    """Window messages for the ReAct LLM call to control token usage.

    Reuses get_windowed_messages() from message_windowing.py for the history
    of previous turns, and preserves the current ReAct loop integrally.

    Strategy:
    1. Split messages at the last HumanMessage (= current turn boundary)
    2. Window the history (previous turns) via get_windowed_messages()
       → keeps SystemMessages + last N conversational turns (no ToolMessages)
    3. Drop every history SystemMessage that is not a compaction summary
    4. Append ALL current turn messages (HumanMessage + ReAct loop: AIMessage
       with tool_calls + ToolMessages) — the agent needs its full reasoning chain

    Step 3 exists for checkpoints written before ADR-169, when the turn's system
    blocks were appended to ``messages``. The windowing hoists every past copy to
    the front, so an old thread would still carry N stale copies of the ReAct
    prompt. Only the compaction summary is a SystemMessage the history genuinely
    needs — it IS the conversation's compressed memory. Everything else the model
    must see this turn is recomposed from ``react_system_blocks``.

    Args:
        messages: Full state messages (accumulated across turns + ReAct loop).

    Returns:
        Windowed message list.
    """
    from langchain_core.messages import HumanMessage as HM
    from langchain_core.messages import SystemMessage as SM

    from src.core.constants import COMPACTION_SUMMARY_MARKER
    from src.domains.agents.utils.message_windowing import get_windowed_messages

    # Find the last HumanMessage — everything after it is the current ReAct loop
    last_human_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        if isinstance(messages[i], HM):
            last_human_idx = i
            break

    if last_human_idx == -1:
        return messages

    # Split: history (before last HumanMessage) and current turn (from HumanMessage onward)
    history = messages[:last_human_idx]
    current_turn = messages[last_human_idx:]

    # Window the history using existing infrastructure
    windowed_history = get_windowed_messages(
        history, window_size=settings.react_agent_history_window_turns
    )

    # Legacy-checkpoint hygiene (see docstring): keep only the compaction
    # summary among history SystemMessages.
    windowed_history = [
        message
        for message in windowed_history
        if not isinstance(message, SM) or str(message.content).startswith(COMPACTION_SUMMARY_MARKER)
    ]

    windowed = neutralize_widget_sentinels(windowed_history) + current_turn

    if len(windowed) < len(messages):
        logger.debug(
            "react_messages_windowed",
            original_count=len(messages),
            windowed_count=len(windowed),
            history_kept=len(windowed_history),
            current_turn_msgs=len(current_turn),
        )

    return windowed
