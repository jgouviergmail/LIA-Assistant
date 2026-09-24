"""What LIA does to an OpenAI Responses payload before it leaves (ADR-306).

From GPT-5.6 on, OpenAI caches a prompt by breakpoint and bills the write at
1.25x the input price. By default (« implicit » mode) the breakpoint sits at the
end of the latest eligible message: the person's question, or the last tool
result of a loop. LIA writes the turn's data -- the date, the context, the
history -- into the system prompt, after its static part and before that
message, so the implicit breakpoint's prefix changed on every call. Measured on
gpt-6-luna with the real ``response`` prompt (2026-09-23): a second call sharing
the static part read 0 tokens and rewrote 2,873 at 1.25x.

One rule, measured on the six models of the two generations the same day: **the
static prefix carries an explicit breakpoint**, cut where the marker says. The
second call then read ~2,832 tokens at 0.1x and wrote 41. A request a tool loop
can continue (tools bound) stays in implicit mode: explicit mode looks up
explicit breakpoints only, and a tool loop reads its previous iteration through
the implicit breakpoint and the earlier message endings that mode also looks up.
A request no loop can continue (no tool bound) is sent in explicit mode
(ADR-309): its implicit breakpoint wrote the turn's data at 1.25x for no later
call to read.

Only the models that accept a breakpoint are sent one. Every earlier model
refuses the field outright (400 « prompt_cache_breakpoint is not supported on
this model », measured on ten of them), so the generations are DECLARED rather
than read off a version number: an undeclared model keeps the implicit cache it
always had, where a wrong guess would refuse every one of its calls.

Pure functions over the wire-format dicts ``langchain-openai`` produces;
``ChatOpenAICached`` applies :func:`shape_openai_payload` to every request.
"""

from __future__ import annotations

from typing import Any

from src.core.constants import DYNAMIC_CONTEXT_MARKER

#: The model families that accept ``prompt_cache_breakpoint`` (measured
#: 2026-09-23 on gpt-6-astra/sol/luna and gpt-5.6-sol/terra/luna). A name
#: belongs to a family when it is the family or continues it with a dash (a
#: variant or a dated snapshot), never merely because it starts the same way.
_BREAKPOINT_FAMILIES: tuple[str, ...] = ("gpt-6", "gpt-5.6")

#: A breakpoint in the default TTL (30 minutes, the only value OpenAI offers).
_BREAKPOINT: dict[str, str] = {"mode": "explicit"}

#: The request mode of a call no tool loop can continue (ADR-309). Implicit mode
#: writes the whole prompt up to its last message at 1.25x; with no tool bound no
#: later call extends that prompt, so the write is never read — measured
#: 2026-09-23 on gpt-6-luna, every single-call node (extractions, query analyzer)
#: billed its unread prompt at exactly 1.25x. Explicit mode writes the declared
#: breakpoints only, which later calls do read.
_EXPLICIT_REQUEST: dict[str, str] = {"mode": "explicit"}

#: The roles whose text is an instruction; a user message never holds the marker.
_INSTRUCTION_ROLES = frozenset({"system", "developer"})


def supports_cache_breakpoints(model: str) -> bool:
    """Whether ``model`` belongs to a family that accepts a cache breakpoint.

    Args:
        model: OpenAI model id.

    Returns:
        True for the declared families; False for every other model, which the
        API would refuse with a 400 on sight of the field.
    """
    name = model.lower()
    return any(name == family or name.startswith(f"{family}-") for family in _BREAKPOINT_FAMILIES)


def shape_openai_payload(payload: dict[str, Any], model: str) -> dict[str, Any]:
    """Mark the static prefix of one request payload, when the model accepts it.

    Args:
        payload: The dict ``ChatOpenAI._get_request_payload`` built (Responses API).
        model: The model the request goes to.

    Returns:
        The same dict, reshaped in place.
    """
    items = payload.get("input")
    if supports_cache_breakpoints(model) and isinstance(items, list):
        payload["input"] = mark_static_system_prefix(items)
        if not payload.get("tools"):
            # Merged, never assigned: a kwarg several sources may write.
            payload["prompt_cache_options"] = {
                **(payload.get("prompt_cache_options") or {}),
                **_EXPLICIT_REQUEST,
            }
    return payload


def mark_static_system_prefix(items: list[Any]) -> list[Any]:
    """Place one breakpoint at the end of the system prompt's static part.

    The static part is everything before ``DYNAMIC_CONTEXT_MARKER``, the one
    convention every system prompt follows. A block holding the marker is split
    in two -- the model still reads the same text, in two pieces -- and a marker
    opening a system message ends the prefix on the system message before it.

    Args:
        items: The payload's ``input`` items.

    Returns:
        A new list with the breakpoint placed, or ``items`` unchanged when no
        system message holds the marker (nothing says where the per-request
        part starts, and a breakpoint there would pay the write surcharge on
        text no later call repeats) or nothing static precedes it.
    """
    located = _locate_marker(items)
    if located is None:
        return items
    item_index, blocks, block_index, position = located
    text = blocks[block_index]["text"]
    if text[:position].strip():
        block = blocks[block_index]
        split = [
            *blocks[:block_index],
            {**block, "text": text[:position], "prompt_cache_breakpoint": dict(_BREAKPOINT)},
            {**block, "text": text[position:]},
            *blocks[block_index + 1 :],
        ]
        return _with_content(items, item_index, split)
    if block_index > 0:
        return _with_content(
            items, item_index, _marked_last(blocks[:block_index]) + blocks[block_index:]
        )
    previous = _blocks(items[item_index - 1]) if item_index > 0 else None
    if previous:
        return _with_content(items, item_index - 1, _marked_last(previous))
    return items


def _locate_marker(
    items: list[Any],
) -> tuple[int, list[dict[str, Any]], int, int] | None:
    """The first instruction block holding the marker: item, its blocks, block, offset."""
    for item_index, item in enumerate(items):
        blocks = _blocks(item) or []
        for block_index, block in enumerate(blocks):
            position = block["text"].find(DYNAMIC_CONTEXT_MARKER)
            if position >= 0:
                return item_index, blocks, block_index, position
    return None


def _blocks(item: Any) -> list[dict[str, Any]] | None:
    """An instruction message's content as text blocks, or None for anything else."""
    if not isinstance(item, dict) or item.get("role") not in _INSTRUCTION_ROLES:
        return None
    content = item.get("content")
    if isinstance(content, str):
        return [{"type": "input_text", "text": content}]
    if isinstance(content, list) and all(
        isinstance(block, dict) and isinstance(block.get("text"), str) for block in content
    ):
        return content
    return None


def _marked_last(blocks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The blocks with a breakpoint on the last one."""
    return [*blocks[:-1], {**blocks[-1], "prompt_cache_breakpoint": dict(_BREAKPOINT)}]


def _with_content(items: list[Any], index: int, blocks: list[dict[str, Any]]) -> list[Any]:
    """A copy of ``items`` whose item ``index`` carries ``blocks`` as its content."""
    return [*items[:index], {**items[index], "content": blocks}, *items[index + 1 :]]


__all__ = [
    "mark_static_system_prefix",
    "shape_openai_payload",
    "supports_cache_breakpoints",
]
