"""What LIA does to a Claude request payload before it leaves (ADR-306).

The Claude API never caches unasked: a request is cached only up to a
``cache_control`` breakpoint, by exact prefix, and a written entry costs 1.25x
the input price where a read costs a tenth of it (a fortieth on Fable 5.1).
Where the breakpoints sit therefore decides the bill. Three rules, each one
measured on the Claude API on 2026-09-23 (Sonnet 5, the real ``response``
prompt, ``max_tokens=0``):

1. **The static prefix is marked where the marker says, whatever the shape of
   the system prompt.** Consecutive system messages reach the API as a LIST of
   blocks, and the previous patch put the breakpoint on the LAST block -- the
   turn's data. The cache key then changed on every call: the second call read
   0 tokens and rewrote 5,222 at 1.25x, where one block read 5,074.
2. **The rolling breakpoint only where a later call reads it.** The root-level
   ``cache_control`` moves with the conversation; it pays inside a tool loop,
   whose next iteration re-sends the whole prefix, and nowhere else: a single
   call's tail (the date, the question, the history) is unique, so writing it
   was a 25 % surcharge nothing ever read.
3. **An earlier turn's thinking is not replayed.** It is billed as input on
   every later turn, and the generations that bind a block to its conversation
   refuse it once the system prompt changed -- which LIA rebuilds every turn
   (400 on Opus 5.5 with enforcement on, the default for every account created
   from 2026-08-31). The current turn's blocks are kept: a tool loop must replay
   the thinking of the call it continues.

Pure functions over the wire-format dicts ``langchain-anthropic`` produces; the
factory wires :func:`shape_claude_payload` onto every Claude client.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import (
    ANTHROPIC_CACHE_MIN_TOKENS_TYPICAL,
    ANTHROPIC_MAX_CACHE_BREAKPOINTS,
    DYNAMIC_CONTEXT_MARKER,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The 5-minute TTL: LIA's prompt cache is a BURST cache (89 % of the cached
#: tokens came from calls less than five minutes apart, ADR-244 measurement),
#: where the 1-hour TTL would double every write for gaps it never sees.
_EPHEMERAL: dict[str, str] = {"type": "ephemeral"}

#: Block types that carry a model's reasoning in an assistant message.
_THINKING_BLOCK_TYPES = frozenset({"thinking", "redacted_thinking"})


def shape_claude_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Apply the three rules to one request payload.

    Args:
        payload: The dict ``ChatAnthropic._get_request_payload`` built.

    Returns:
        The same dict, reshaped in place.
    """
    if "system" in payload:
        payload["system"] = mark_static_system_prefix(payload["system"])
    messages = payload.get("messages")
    if isinstance(messages, list):
        payload["messages"] = strip_prior_turn_thinking(messages)
    if (
        wants_rolling_breakpoint(payload)
        and _count_breakpoints(payload) < ANTHROPIC_MAX_CACHE_BREAKPOINTS
    ):
        payload["cache_control"] = dict(_EPHEMERAL)
    return payload


def mark_static_system_prefix(system: Any) -> Any:
    """Place one breakpoint at the end of the system prompt's static part.

    The static part is everything before ``DYNAMIC_CONTEXT_MARKER``, the one
    convention every system prompt follows (a fully static prompt ENDS with it).
    A block holding the marker is split in two; a marker opening a block ends
    the prefix on the block before it.

    Args:
        system: The payload's ``system`` field -- a string, a list of text
            blocks, or absent.

    Returns:
        A list of blocks with the breakpoint placed, or ``system`` unchanged
        when there is no marker (nothing says where per-request content
        starts, and a breakpoint there would pay the write premium on every
        call), nothing before it, or breakpoints the caller placed itself.
    """
    blocks = [{"type": "text", "text": system}] if isinstance(system, str) else system
    if not isinstance(blocks, list) or not blocks:
        return system
    if any(isinstance(block, dict) and "cache_control" in block for block in blocks):
        return system
    located = _locate_marker(blocks)
    if located is None:
        return system
    index, position = located
    block = blocks[index]
    static_text = block["text"][:position].rstrip()
    if static_text:
        prefix = [
            *blocks[:index],
            {**block, "text": static_text, "cache_control": dict(_EPHEMERAL)},
        ]
        rest = [{**block, "text": block["text"][position:]}, *blocks[index + 1 :]]
    elif index > 0:
        prefix = [*blocks[: index - 1], {**blocks[index - 1], "cache_control": dict(_EPHEMERAL)}]
        rest = blocks[index:]
    else:
        return system
    _warn_if_below_typical_minimum(prefix)
    return [*prefix, *rest]


def wants_rolling_breakpoint(payload: dict[str, Any]) -> bool:
    """Whether a later call will re-send this request's whole prefix.

    That is a tool loop: a conversation that already made a tool round trip, or
    an agent offered several tools. A structured-output call binds ONE schema
    tool and is a single call.

    Args:
        payload: The request payload.

    Returns:
        True when the rolling (root-level) breakpoint would be read.
    """
    tools = payload.get("tools")
    if isinstance(tools, list) and len(tools) > 1:
        return True
    messages = payload.get("messages")
    return isinstance(messages, list) and any(_carries_tool_result(message) for message in messages)


def strip_prior_turn_thinking(messages: list[Any]) -> list[Any]:
    """Remove the thinking blocks of every turn before the current one.

    The current turn starts at the last user message that carries no tool
    result: everything after it is the tool loop in progress, replayed intact.
    An earlier assistant message left with nothing is dropped -- empty content
    is refused, and the two user messages then adjacent are merged by the API.

    Args:
        messages: The payload's messages, in wire format.

    Returns:
        A new list when something was removed, else the same content.
    """
    boundary = _current_turn_start(messages)
    if boundary <= 0:
        return messages
    kept: list[Any] = []
    for position, message in enumerate(messages):
        content = message.get("content") if isinstance(message, dict) else None
        if (
            position >= boundary
            or not isinstance(content, list)
            or message.get("role") != "assistant"
        ):
            kept.append(message)
            continue
        visible = [block for block in content if not _is_thinking(block)]
        if len(visible) == len(content):
            kept.append(message)
        elif visible:
            kept.append({**message, "content": visible})
    return kept


def _locate_marker(blocks: list[Any]) -> tuple[int, int] | None:
    """The first text block holding the marker, and the marker's offset in it."""
    for index, block in enumerate(blocks):
        text = block.get("text") if isinstance(block, dict) else None
        if isinstance(text, str):
            position = text.find(DYNAMIC_CONTEXT_MARKER)
            if position >= 0:
                return index, position
    return None


def _warn_if_below_typical_minimum(prefix: list[dict[str, Any]]) -> None:
    """A heads-up when the marked prefix is likely too short to be cached at all.

    The minimum is per model (512 tokens on Opus 5, 4096 on Opus 4.5 and Haiku
    4.5); below it the API silently caches nothing -- no cost, no benefit.
    """
    chars = sum(len(block.get("text", "")) for block in prefix)
    estimated_tokens = chars // 3  # ~3.5 characters per token on mixed content
    if estimated_tokens < ANTHROPIC_CACHE_MIN_TOKENS_TYPICAL:
        logger.debug(
            "anthropic_cache_prefix_small",
            estimated_tokens=estimated_tokens,
            chars=chars,
            min_typical=ANTHROPIC_CACHE_MIN_TOKENS_TYPICAL,
        )


def _carries_tool_result(message: Any) -> bool:
    """Whether a user message answers a tool call."""
    if not isinstance(message, dict) or message.get("role") != "user":
        return False
    content = message.get("content")
    return isinstance(content, list) and any(
        isinstance(block, dict) and block.get("type") == "tool_result" for block in content
    )


def _current_turn_start(messages: list[Any]) -> int:
    """Index of the last user message that is not a tool result, or -1."""
    for position in range(len(messages) - 1, -1, -1):
        message = messages[position]
        if isinstance(message, dict) and message.get("role") == "user":
            if not _carries_tool_result(message):
                return position
    return -1


def _is_thinking(block: Any) -> bool:
    """Whether a content block is a model's reasoning."""
    return isinstance(block, dict) and block.get("type") in _THINKING_BLOCK_TYPES


def _count_breakpoints(payload: dict[str, Any]) -> int:
    """Explicit breakpoints on the tools, the system prompt and the messages."""
    places: list[Any] = []
    for key in ("tools", "system"):
        if isinstance(payload.get(key), list):
            places.extend(payload[key])
    for message in payload.get("messages") or []:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, list):
            places.extend(content)
    return sum(1 for place in places if isinstance(place, dict) and "cache_control" in place)


__all__ = [
    "mark_static_system_prefix",
    "shape_claude_payload",
    "strip_prior_turn_thinking",
    "wants_rolling_breakpoint",
]
