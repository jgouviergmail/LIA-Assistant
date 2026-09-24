"""Qwen through DashScope's OpenAI-compatible API, with its explicit prompt cache (ADR-309).

DashScope documents Qwen 3.5 and 3.6 (Plus and Flash) with NO implicit prompt
cache in any region -- only an explicit one: ``cache_control`` on a content part,
written at 125 % and read at 10 % for five minutes, at most four markers per
request (context cache guide, updated 2026-09-18). Measured 2026-09-23 on LIA's
workspace with qwen3.5-plus: two identical requests read nothing; marked, the
first wrote 11,940 tokens and the second read them all.

The marker follows the one boundary every mechanism is translated from
(:func:`~src.core.prompt_layout.split_at_marker`): the static system prefix,
ending on its ``DYNAMIC_CONTEXT_MARKER`` line -- the tool definitions count
inside the system message there -- plus, inside a tool loop, a rolling marker on
the last message, so each iteration reads the previous one. A model WITH an
implicit cache keeps it: a marker switches a request to the explicit mode, which
only beats the implicit one (no write surcharge, 20 % read) from four reads per
five minutes, so the families are DECLARED rather than guessed.

DashScope reports the write as ``prompt_tokens_details.cache_creation_input_tokens``,
a field langchain does not map; it is copied into the standard
``cache_write_tokens`` before langchain reads the usage, so the write reaches the
one usage reader (``usage_metadata.py``) and is billed at its price.
"""

from __future__ import annotations

from typing import Any

from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI

from src.core.prompt_layout import split_at_marker

#: The families with an explicit cache and no implicit one (DashScope's model
#: table, 2026-09-18; qwen3.5-plus measured). A name belongs to a family when it
#: is the family or continues it with a dash (a dated snapshot).
_EXPLICIT_ONLY_FAMILIES: tuple[str, ...] = (
    "qwen3.5-plus",
    "qwen3.6-plus",
    "qwen3.5-flash",
    "qwen3.6-flash",
)

#: DashScope's one marker type (5 minutes, renewed on every hit).
_MARKER: dict[str, str] = {"type": "ephemeral"}


def uses_explicit_cache(model: str) -> bool:
    """Whether ``model`` belongs to a family cached through explicit markers only.

    Args:
        model: DashScope model id.

    Returns:
        True for the declared families.
    """
    name = model.lower()
    return any(
        name == family or name.startswith(f"{family}-") for family in _EXPLICIT_ONLY_FAMILIES
    )


def shape_qwen_payload(payload: dict[str, Any], model: str) -> dict[str, Any]:
    """Mark a Chat Completions payload where its cacheable prefixes end.

    Args:
        payload: The dict ``ChatOpenAI._get_request_payload`` built.
        model: The model the request goes to.

    Returns:
        The same dict, reshaped in place when the model is cached explicitly.
    """
    messages = payload.get("messages")
    if not uses_explicit_cache(model) or not isinstance(messages, list):
        return payload
    marked = _mark_static_system_prefix(messages)
    if any(isinstance(message, dict) and message.get("role") == "tool" for message in marked):
        marked = _mark_last_message(marked)
    payload["messages"] = marked
    return payload


def _mark_static_system_prefix(messages: list[Any]) -> list[Any]:
    """The first system message holding the marker, split so its static part is marked."""
    for index, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "system":
            continue
        content = message.get("content")
        if not isinstance(content, str):
            continue
        split = split_at_marker(content)
        if split is None:
            continue
        parts: list[dict[str, Any]] = [
            {"type": "text", "text": split.static, "cache_control": dict(_MARKER)}
        ]
        remainder = content[len(split.static) :]
        if remainder:
            parts.append({"type": "text", "text": remainder})
        return [*messages[:index], {**message, "content": parts}, *messages[index + 1 :]]
    return messages


def _mark_last_message(messages: list[Any]) -> list[Any]:
    """A rolling marker on the last message: the next iteration reads this one."""
    last = messages[-1]
    content = last.get("content") if isinstance(last, dict) else None
    if isinstance(content, str) and content:
        parts: list[Any] = [{"type": "text", "text": content, "cache_control": dict(_MARKER)}]
    elif isinstance(content, list) and content and isinstance(content[-1], dict):
        parts = [*content[:-1], {**content[-1], "cache_control": dict(_MARKER)}]
    else:
        return messages
    return [*messages[:-1], {**last, "content": parts}]


def _with_standard_write(usage: Any) -> Any:
    """Copy DashScope's write count into the field langchain maps, when it is missing."""
    if not isinstance(usage, dict):
        return usage
    details = usage.get("prompt_tokens_details")
    if not isinstance(details, dict) or details.get("cache_write_tokens") is not None:
        return usage
    written = details.get("cache_creation_input_tokens")
    if not isinstance(written, int):
        return usage
    return {**usage, "prompt_tokens_details": {**details, "cache_write_tokens": written}}


class ChatQwenCached(ChatOpenAI):
    """``ChatOpenAI`` on DashScope that marks the prompt cache and reads its writes.

    Thin subclass: payload building gains the markers (:func:`shape_qwen_payload`)
    and the usage gains the write count; everything else (tools, structured
    output, streaming, reasoning ``extra_body``) is the stock implementation.
    """

    def _get_request_payload(
        self,
        input_: Any,
        *,
        stop: list[str] | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        return shape_qwen_payload(payload, self.model_name)

    def _create_chat_result(
        self, response: Any, generation_info: dict[str, Any] | None = None
    ) -> ChatResult:
        response_dict = response if isinstance(response, dict) else response.model_dump()
        response_dict = {**response_dict, "usage": _with_standard_write(response_dict.get("usage"))}
        return super()._create_chat_result(response_dict, generation_info)

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,
    ) -> ChatGenerationChunk | None:
        if chunk.get("usage"):
            chunk = {**chunk, "usage": _with_standard_write(chunk["usage"])}
        return super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
