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
   was a 25 % surcharge nothing ever read. In a tool loop the history's END is
   marked too (ADR-362): an entry is written only at a breakpoint, and the
   rolling one sits on the question and its context, which the next turn never
   sends again -- so the next turn found no entry where its prefix diverges and
   re-wrote the whole history. The extra breakpoint costs nothing (the rolling
   one already writes its span). The two CROSS-TURN read points -- the static
   prefix and the history end -- live the hour when the call asked for the
   extended horizon (``prompt_cache_horizon``); the rolling one, re-read seconds
   later, always keeps the provider's default five minutes.
3. **An earlier turn's thinking goes back only to the model that wrote it**,
   when that generation keeps prior thinking without binding it (ADR-362). That
   decision needs to know which model wrote a block, which only LangChain's
   messages still say, so it is taken BEFORE the client formats the request
   (``anthropic_thinking``, wired by ``anthropic_hooks``) -- not here.

Pure functions over the wire-format dicts ``langchain-anthropic`` produces; the
Claude hooks wire :func:`shape_claude_payload` onto every Claude client.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from src.core.constants import (
    ANTHROPIC_CACHE_MIN_TOKENS_TYPICAL,
    ANTHROPIC_CACHE_TTL_EXTENDED,
    ANTHROPIC_MAX_CACHE_BREAKPOINTS,
    DYNAMIC_CONTEXT_MARKER,
)
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: The provider's default lifetime, five minutes: most of LIA's reuse is a
#: BURST (89 % of the cached tokens came from calls less than five minutes
#: apart, ADR-244 measurement), and a tool loop re-reads its tail in seconds.
_EPHEMERAL: dict[str, str] = {"type": "ephemeral"}
#: The extended lifetime, for the cross-turn read points of a call that asked
#: for it (ADR-362): a write costs 2x instead of 1.25x, and pays when the next
#: turn comes between five minutes and an hour later.
_EPHEMERAL_EXTENDED: dict[str, str] = {"type": "ephemeral", "ttl": ANTHROPIC_CACHE_TTL_EXTENDED}

#: Content blocks a ``cache_control`` may sit on (the API refuses it on a
#: thinking block, and an empty text block caches nothing).
_CACHEABLE_BLOCK_TYPES = frozenset({"text", "image", "document", "tool_use", "tool_result"})


def shape_claude_payload(payload: dict[str, Any], *, extended_ttl: bool = False) -> dict[str, Any]:
    """Apply the three rules to one request payload.

    Args:
        payload: The dict ``ChatAnthropic._get_request_payload`` built.
        extended_ttl: Whether the call's cross-turn read points live the
            extended lifetime (``prompt_cache_horizon``); the rolling
            breakpoint never does, nor does any point beside a breakpoint a
            caller placed itself.

    Returns:
        The same dict, reshaped in place.
    """
    # The API refuses a longer-lived entry after a shorter one, and the policy
    # cannot order a breakpoint it did not place: beside one, the default only.
    extended = extended_ttl and _count_breakpoints(payload) == 0
    read_point = _EPHEMERAL_EXTENDED if extended else _EPHEMERAL
    if "system" in payload:
        payload["system"] = mark_static_system_prefix(payload["system"], cache_control=read_point)
    if not isinstance(payload.get("messages"), list) or not wants_rolling_breakpoint(payload):
        return payload
    # The history's read point only when the rolling breakpoint still fits beside it.
    if _count_breakpoints(payload) + 2 <= ANTHROPIC_MAX_CACHE_BREAKPOINTS:
        payload["messages"] = mark_history_end(
            _as_block_lists(payload["messages"]), cache_control=read_point
        )
    if _count_breakpoints(payload) < ANTHROPIC_MAX_CACHE_BREAKPOINTS:
        payload["cache_control"] = dict(_EPHEMERAL)
    return payload


def mark_static_system_prefix(system: Any, *, cache_control: Mapping[str, str] = _EPHEMERAL) -> Any:
    """Place one breakpoint at the end of the system prompt's static part.

    The static part is everything before ``DYNAMIC_CONTEXT_MARKER``, the one
    convention every system prompt follows (a fully static prompt ENDS with it).
    A block holding the marker is split in two; a marker opening a block ends
    the prefix on the block before it.

    Args:
        system: The payload's ``system`` field -- a string, a list of text
            blocks, or absent.
        cache_control: The breakpoint to place (its lifetime).

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
            {**block, "text": static_text, "cache_control": dict(cache_control)},
        ]
        rest = [{**block, "text": block["text"][position:]}, *blocks[index + 1 :]]
    elif index > 0:
        prefix = [*blocks[: index - 1], {**blocks[index - 1], "cache_control": dict(cache_control)}]
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


def mark_history_end(
    messages: list[Any], *, cache_control: Mapping[str, str] = _EPHEMERAL
) -> list[Any]:
    """Place a breakpoint on the last block before the current turn's question.

    The next turn's request starts with the same history plus this turn's
    exchange, so an entry written here is the one it can read back (within the
    API's 20-position lookback: the exchange adds two). Only a tool loop calls
    this, where the rolling breakpoint writes the span anyway.

    Args:
        messages: The payload's messages, in wire format.
        cache_control: The breakpoint to place (its lifetime).

    Returns:
        A new list with the read point placed, or ``messages`` unchanged when
        there is no history, a caller placed its own breakpoints, or the last
        message before the question holds no block a breakpoint may sit on.
    """
    boundary = _current_turn_start(messages)
    if boundary <= 0 or _carries_breakpoint(messages):
        return messages
    marked = _with_last_block_marked(messages[boundary - 1], cache_control)
    if marked is None:
        return messages
    return [*messages[: boundary - 1], marked, *messages[boundary:]]


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


def _as_block_lists(messages: list[Any]) -> list[Any]:
    """Every text content as the one text block it stands for.

    A breakpoint can only sit on a block, so the history end becomes a list the
    turn it is marked, and one turn later the same message, no longer the end,
    would go back to a string. Whether the API reads both shapes as one prefix
    is not documented; one shape always makes the bytes the next turn resends
    the bytes this turn wrote (LIA's own two-turn build differed before).
    """
    return [
        (
            {**message, "content": [_text_block(message["content"])]}
            if isinstance(message, dict)
            and isinstance(message.get("content"), str)
            and message["content"]
            else message
        )
        for message in messages
    ]


def _with_last_block_marked(
    message: Any, cache_control: Mapping[str, str]
) -> dict[str, Any] | None:
    """A copy of ``message`` whose last cacheable block carries ``cache_control``."""
    if not isinstance(message, dict):
        return None
    content = message.get("content")
    if isinstance(content, str):
        if not content.strip():
            return None
        return {
            **message,
            "content": [{**_text_block(content), "cache_control": dict(cache_control)}],
        }
    if not isinstance(content, list):
        return None
    for position in range(len(content) - 1, -1, -1):
        if _is_cacheable(content[position]):
            block = {**content[position], "cache_control": dict(cache_control)}
            return {**message, "content": [*content[:position], block, *content[position + 1 :]]}
    return None


def _text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _is_cacheable(block: Any) -> bool:
    """Whether a breakpoint may sit on a content block."""
    if not isinstance(block, dict) or block.get("type") not in _CACHEABLE_BLOCK_TYPES:
        return False
    return block.get("type") != "text" or bool(str(block.get("text") or "").strip())


def _carries_breakpoint(messages: list[Any]) -> bool:
    """Whether a caller already placed a breakpoint in the messages."""
    return any(
        isinstance(block, dict) and "cache_control" in block
        for message in messages
        if isinstance(message, dict) and isinstance(message.get("content"), list)
        for block in message["content"]
    )


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
    "mark_history_end",
    "mark_static_system_prefix",
    "shape_claude_payload",
    "wants_rolling_breakpoint",
]
