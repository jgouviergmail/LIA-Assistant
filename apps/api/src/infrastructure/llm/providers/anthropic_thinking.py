"""Which earlier thinking a Claude request carries back (ADR-306, ADR-362).

A previous turn's thinking is part of what a model reads on the generations
that keep it (from Opus 4.5 and Sonnet 4.6 on): the vendor's default is to pass
it back unchanged, and to drop, unbilled, a block the receiving model cannot
read. LIA keeps that context where it is valid -- the model that WROTE a block
reads it again -- and removes it where it is not:

* a generation that BINDS a block to the conversation that produced it refuses
  it once the history before it changed, which LIA's per-turn rebuild always
  does (a 400; with ``drop_block`` the first stale block and every later one,
  the current tool loop's included);
* a generation that strips prior thinking itself also drops the messages cache
  after the first stripped block, so a block sent there costs the cache;
* another model's block, or one of unknown origin, would be dropped unread --
  an outcome the vendor still describes as rolling out;
* a generation the surface table does not declare is sent none: nothing is
  known of it, and a history without earlier thinking is accepted everywhere.

Measured 2026-10-22 on a generation that keeps without binding: the replayed
block, in LIA's history shape (two assistant messages per ReAct turn), was
accepted and billed as input -- about a hundred tokens for a short reasoning.

Decided on LangChain's messages, BEFORE the client formats them: that is where a
message still says which model wrote it (``response_metadata.model_name``), and
the client drops an empty assistant message, so the formatted assistant messages
cannot be matched back by position. The current turn -- from the last human
message that answers no tool call -- is never touched: a tool loop must replay
the thinking of the call it continues.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.core.claude_surface import claude_surface
from src.infrastructure.llm.usage_metadata import model_name_of_response
from src.infrastructure.observability.metrics_prompt_cache import (
    llm_prior_turn_thinking_blocks_total,
)

#: Block types that carry a model's reasoning in an assistant message.
_THINKING_BLOCK_TYPES = frozenset({"thinking", "redacted_thinking"})
#: A dated snapshot answers under its alias's name plus the date.
_SNAPSHOT_SUFFIX = re.compile(r"-\d{8}$")


def replay_prior_turn_thinking(
    messages: Sequence[BaseMessage], receiver: str, *, enabled: bool
) -> list[BaseMessage]:
    """The messages with each earlier turn's thinking kept or removed for ``receiver``.

    Args:
        messages: The request's messages, as LangChain holds them.
        receiver: The model the request goes to.
        enabled: The operator switch (``PRIOR_TURN_THINKING_REPLAY_ENABLED``);
            off, every earlier turn's thinking is removed.

    Returns:
        A new list. A message whose thinking is removed is a copy; nothing given
        is mutated. A message left with no content stays empty: the client
        drops it, as the API refuses an empty assistant message.
    """
    boundary = _current_turn_start(messages)
    replayed: list[BaseMessage] = []
    for position, message in enumerate(messages):
        thinking = _thinking_blocks(message) if 0 <= position < boundary else 0
        if not thinking:
            replayed.append(message)
            continue
        reason = _strip_reason(message, receiver, enabled=enabled)
        llm_prior_turn_thinking_blocks_total.labels(
            model=receiver or "unknown",
            decision="kept" if reason is None else "stripped",
            reason=reason or "same_model",
        ).inc(thinking)
        replayed.append(message if reason is None else _without_thinking(message))
    return replayed


def _strip_reason(message: BaseMessage, receiver: str, *, enabled: bool) -> str | None:
    """Why an earlier turn's thinking does not go back to ``receiver``; None when it does."""
    if not enabled:
        return "disabled"
    surface = claude_surface(receiver)
    if surface.thinking is None:
        return "receiver_undeclared"
    if surface.binds_thinking_to_conversation:
        return "receiver_binds"
    if not surface.preserves_prior_turn_thinking:
        return "receiver_strips"
    origin = model_name_of_response(message)
    if origin is None:
        return "unknown_origin"
    if _SNAPSHOT_SUFFIX.sub("", origin) != _SNAPSHOT_SUFFIX.sub("", receiver):
        return "other_model"
    return None


def _current_turn_start(messages: Sequence[BaseMessage]) -> int:
    """Where the current turn starts, or -1 when the request holds no earlier turn.

    The client merges each run of consecutive human and tool messages into ONE
    user message; the current turn opens on the last such run that answers no
    tool call -- the rule ``anthropic_payload`` applies to the formatted request.
    """
    position = len(messages) - 1
    while position >= 0:
        if not isinstance(messages[position], HumanMessage | ToolMessage):
            position -= 1
            continue
        end = position
        while position >= 0 and isinstance(messages[position], HumanMessage | ToolMessage):
            position -= 1
        if not any(_answers_a_tool(message) for message in messages[position + 1 : end + 1]):
            return position + 1
    return -1


def _answers_a_tool(message: BaseMessage) -> bool:
    if isinstance(message, ToolMessage):
        return True
    content = message.content
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def _thinking_blocks(message: BaseMessage) -> int:
    if not isinstance(message, AIMessage) or not isinstance(message.content, list):
        return 0
    return sum(1 for block in message.content if _is_thinking(block))


def _without_thinking(message: BaseMessage) -> BaseMessage:
    content = [block for block in message.content if not _is_thinking(block)]
    return message.model_copy(update={"content": content})


def _is_thinking(block: Any) -> bool:
    return isinstance(block, dict) and block.get("type") in _THINKING_BLOCK_TYPES


__all__ = ["replay_prior_turn_thinking"]
