"""Recover a tool call the parser or the schema refused for a mechanical reason.

Two shapes, both measured on DeepSeek, both complete answers the door threw away:

- **Nulls where the schema has a default** (production 2026-09-05,
  ``deepseek-v4-flash``, a complete minutes payload, ``"bullets": null`` on a
  paragraph section, three identical rejections). A model that fills every
  property writes ``null`` where it has nothing to say, and Pydantic refuses
  ``null`` on a ``list[str]`` field even when the field has a default. The rule
  is structural, never per schema: a ``null`` under a key whose field HAS a
  default and does NOT admit ``None`` is the model's spelling of « absent » and
  the key is dropped so the default applies; a ``null`` on an Optional field is
  a value and stays; a ``null`` on a required field is an error and stays.
  Nested models and lists of models are walked the same way.
- **A bare word where a JSON string belongs** (dev replay 2026-09-20,
  ``deepseek-flash``, ``"primary_domain": mcp`` on 11 of 24 query-analyzer
  calls; production lost 4 of 26 analyses in 48 h to it). LangChain cannot parse
  the arguments, files the call under ``invalid_tool_calls`` with ``tool_calls``
  EMPTY, and the door read « no tool call, empty answer » — a wrong diagnosis
  of a complete answer, which cost the whole turn (the analyzer's fallback is a
  bare conversation). What is mechanically repairable is repaired before
  validation (ADR-184): a bare token in VALUE position, outside any string, is
  quoted; nothing else moves. A truncated answer is never rescued here — the
  door consults ADR-275's verdict before it reaches this module.
"""

from __future__ import annotations

import json
import types
from collections.abc import Sequence
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from src.infrastructure.llm.message_text import coerce_content_to_text
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

#: Paths listed in a rejection reason before the list is cut (a log line, not a report).
_REASON_PATHS_MAX = 8

#: Bare tokens JSON itself accepts in value position — never quoted.
_JSON_LITERALS = frozenset({"true", "false", "null", "NaN", "Infinity"})

#: Characters a bare token may carry (``mcp_excalidraw``, ``gemini-3.6``, ``v1.2``).
_BARE_TOKEN_CHARS = frozenset("_-.")

#: The parser's own words, kept out of a log line that would otherwise carry the payload.
_REASON_DETAIL_MAX = 120


def _admits_none(annotation: Any) -> bool:
    """Whether ``None`` is a legitimate value for this annotation."""
    if annotation is Any or annotation is None or annotation is type(None):
        return True
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        return any(_admits_none(arg) for arg in get_args(annotation))
    return False


def _model_of(annotation: Any) -> type[BaseModel] | None:
    """The BaseModel behind ``Model`` or ``Model | None``, if any."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        for arg in get_args(annotation):
            model = _model_of(arg)
            if model is not None:
                return model
        return None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _list_item_model(annotation: Any) -> type[BaseModel] | None:
    """The BaseModel behind ``list[Model]`` / ``Sequence[Model]`` (Optional tolerated)."""
    origin = get_origin(annotation)
    if origin is Union or origin is types.UnionType:
        for arg in get_args(annotation):
            model = _list_item_model(arg)
            if model is not None:
                return model
        return None
    if origin in (list, Sequence, tuple) or (
        isinstance(origin, type) and issubclass(origin, Sequence)
    ):
        args = get_args(annotation)
        return _model_of(args[0]) if args else None
    return None


def drop_nulls_with_defaults(schema: type[BaseModel], payload: Any) -> tuple[Any, int]:
    """A copy of ``payload`` without the ``null`` values ``schema`` would default.

    Args:
        schema: The Pydantic model the payload is meant for.
        payload: The model's arguments (anything that is not a dict comes back as is).

    Returns:
        ``(payload, dropped)`` — the cleaned copy and how many keys were removed.
    """
    if not isinstance(payload, dict):
        return payload, 0
    dropped = 0
    cleaned: dict[str, Any] = {}
    for key, value in payload.items():
        field = schema.model_fields.get(key)
        if field is None:
            cleaned[key] = value
            continue
        if value is None:
            if not field.is_required() and not _admits_none(field.annotation):
                dropped += 1
                continue
            cleaned[key] = value
            continue
        nested = _model_of(field.annotation)
        if nested is not None and isinstance(value, dict):
            value, count = drop_nulls_with_defaults(nested, value)
            dropped += count
        else:
            item_model = _list_item_model(field.annotation)
            if item_model is not None and isinstance(value, list):
                items: list[Any] = []
                for item in value:
                    item, count = drop_nulls_with_defaults(item_model, item)
                    dropped += count
                    items.append(item)
                value = items
        cleaned[key] = value
    return cleaned, dropped


def validate_with_defaulted_nulls[T: BaseModel](schema: type[T], payload: Any) -> tuple[T, int]:
    """Validate ``payload`` against ``schema`` after defaulting its nulls.

    Raises:
        ValidationError: When the payload is still invalid once the nulls are gone.
    """
    cleaned, dropped = drop_nulls_with_defaults(schema, payload)
    return schema.model_validate(cleaned), dropped


def rescue_tool_call[T: BaseModel](raw_message: Any, schema: type[T]) -> tuple[T | None, int]:
    """The first tool call of ``raw_message`` validated with its nulls defaulted.

    Answers only for what it changed: a call that validates untouched was the
    parser's to accept, and a call still invalid once cleaned is not rescued.

    Returns:
        ``(instance, dropped)``, or ``(None, 0)`` when nothing could be rescued.
    """
    tool_calls = getattr(raw_message, "tool_calls", None) or []
    if not tool_calls:
        return None, 0
    cleaned, dropped = drop_nulls_with_defaults(schema, tool_calls[0].get("args"))
    if dropped == 0:
        return None, 0
    try:
        return schema.model_validate(cleaned), dropped
    except ValidationError:
        return None, 0


def _string_end(text: str, start: int) -> int:
    """Index just past the string opened at ``start`` (escapes honoured, EOF tolerated)."""
    j = start + 1
    while j < len(text) and text[j] != '"':
        j += 2 if text[j] == "\\" else 1
    return j + 1


def _bare_token(text: str, start: int) -> tuple[str, int, bool]:
    """The bare token at ``start``, where it ends, and whether it needs quoting.

    A token is quoted when it is not a JSON literal and the next non-space
    character closes its value — quoting anything else would only move the
    syntax error.
    """
    j = start
    while j < len(text) and (text[j].isalnum() or text[j] in _BARE_TOKEN_CHARS):
        j += 1
    word = text[start:j]
    k = j
    while k < len(text) and text[k].isspace():
        k += 1
    closes = k >= len(text) or text[k] in ",}]"
    return word, j, word not in _JSON_LITERALS and closes


def _opens_value(char: str, stack: list[str]) -> bool | None:
    """Whether ``char`` opens a value position, or None when it says nothing about it.

    ``:`` does inside an object, ``[`` and ``,`` inside an array; a closing
    bracket ends one. The stack is updated for the brackets.
    """
    if char in "{[":
        stack.append(char)
        return char == "["
    if char in "}]":
        if stack:
            stack.pop()
        return False
    if char == ":":
        return bool(stack) and stack[-1] == "{"
    if char == ",":
        return bool(stack) and stack[-1] == "["
    return None


def quote_bare_values(text: str) -> tuple[str, int]:
    """``text`` with every bare token in JSON value position quoted.

    A value position is what follows ``:`` inside an object, or ``[`` / ``,``
    inside an array. Strings are skipped whole (escapes honoured), so a colon
    or a comma INSIDE a string never opens a value position. JSON's own bare
    literals and numbers are left alone; a bare token that is not followed by
    the end of its value (``,``, ``}``, ``]`` or the end of the text) is left
    alone too, because quoting it would only move the syntax error.

    Args:
        text: The arguments a tool call carried, as the provider spelled them.

    Returns:
        ``(text, quoted)`` — the repaired text and how many tokens were quoted.
    """
    out: list[str] = []
    stack: list[str] = []
    quoted = 0
    expect_value = False
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == '"':
            end = _string_end(text, i)
            out.append(text[i:end])
            i, expect_value = end, False
            continue
        if expect_value and (ch.isalpha() or ch == "_"):
            word, end, quote = _bare_token(text, i)
            out.append(f'"{word}"' if quote else word)
            quoted += int(quote)
            i, expect_value = end, False
            continue
        opens = _opens_value(ch, stack)
        if opens is not None:
            expect_value = opens
        elif not ch.isspace():
            expect_value = False
        out.append(ch)
        i += 1
    return "".join(out), quoted


def rescue_from_text[T: BaseModel](
    raw_message: Any,
    schema: type[T],
    provider: str,
    schema_name: str,
) -> T | None:
    """Salvage a structured output from a model that answered in text.

    Some models resolve the conflict between a forced tool call and prompt
    instructions by answering with raw JSON text instead of calling the tool
    (observed on deepseek-v4-flash with legacy "Output JSON only" prompts —
    audit D5, ADR-100). When ``with_structured_output(include_raw=True)``
    yields no parsed object, this helper tries to recover the payload from the
    raw ``AIMessage`` content before the caller gives up.

    Args:
        raw_message: The raw ``AIMessage`` returned by the model (``None``
            tolerated — returns ``None``).
        schema: Target Pydantic schema.
        provider: Provider name (logging only).
        schema_name: Schema name (logging only).

    Returns:
        A validated schema instance, or ``None`` when no JSON object could
        be extracted and validated from the text content.
    """
    text = coerce_content_to_text(getattr(raw_message, "content", None) or "").strip()
    if not text:
        return None

    # Shared extraction (ADR-220): fences, prose on either side, truncation
    # and trailing commas are handled in ONE place — json_recovery carries the
    # corpus the old find("{")/rfind("}") delimiter failed on.
    from src.infrastructure.llm.json_recovery import extract_json_payload

    payload_text = extract_json_payload(text)
    if payload_text is None:
        return None

    try:
        instance, _defaulted = validate_with_defaulted_nulls(schema, json.loads(payload_text))
    except json.JSONDecodeError, ValidationError:
        return None

    logger.warning(
        "structured_output_rescued_from_text",
        provider=provider,
        schema=schema_name,
        msg="Model answered in raw JSON text instead of calling the forced tool — "
        "payload salvaged; check the prompt for legacy 'output JSON' instructions",
    )
    return instance


def _first_invalid_call(raw_message: Any) -> dict[str, Any] | None:
    calls = getattr(raw_message, "invalid_tool_calls", None) or []
    first = calls[0] if calls else None
    return first if isinstance(first, dict) else None


def invalid_call_arguments(raw_message: Any) -> str:
    """The arguments of the first call the parser refused, for a diagnosis to read."""
    call = _first_invalid_call(raw_message)
    args = call.get("args") if call else None
    return args if isinstance(args, str) else ""


def rescue_invalid_tool_call[T: BaseModel](
    raw_message: Any, schema: type[T]
) -> tuple[T | None, int]:
    """The first call the parser refused, validated once its bare values are quoted.

    Answers only for what it changed: arguments that quote nothing are the
    parser's verdict to keep, and a payload the schema still refuses once it
    parses is not rescued. The schema's defaulted nulls are honoured on the
    way, as for a parsed call.

    Returns:
        ``(instance, quoted)``, or ``(None, 0)`` when nothing could be rescued.
    """
    arguments = invalid_call_arguments(raw_message)
    if not arguments:
        return None, 0
    repaired, quoted = quote_bare_values(arguments)
    if quoted == 0:
        return None, 0
    try:
        instance, _dropped = validate_with_defaulted_nulls(schema, json.loads(repaired))
    except ValueError, ValidationError:
        return None, 0
    return instance, quoted


def rejection_reason(raw_message: Any, parsing_error: BaseException | None) -> str:
    """Why a native structured answer yielded nothing — the words the log carries.

    A rejected tool call is named as such, with the schema paths that failed,
    and a call whose arguments the parser refused is named too, with the
    parser's own words; neither is ever reported as « no tool call ».
    """
    tool_calls = getattr(raw_message, "tool_calls", None) or []
    if tool_calls:
        if isinstance(parsing_error, ValidationError):
            errors = parsing_error.errors()
            paths = ", ".join(
                ".".join(str(part) for part in error["loc"]) for error in errors[:_REASON_PATHS_MAX]
            )
            return f"tool call rejected by schema ({len(errors)} errors: {paths})"
        kind = type(parsing_error).__name__ if parsing_error is not None else "unparsed"
        return f"tool call rejected ({kind})"
    invalid = _first_invalid_call(raw_message)
    if invalid is not None:
        # LangChain's message ends with the parser's verdict after « Received »;
        # everything before it is the payload, which does not belong in a log line.
        error = str(invalid.get("error") or "")
        detail = (error.rsplit("Received ", 1)[-1] if "Received " in error else error).strip()
        detail = detail[:_REASON_DETAIL_MAX]
        suffix = f" ({detail})" if detail else ""
        return f"tool call arguments not valid JSON{suffix}"
    text = coerce_content_to_text(getattr(raw_message, "content", None) or "").strip()
    return "no tool call, text rescue failed" if text else "no tool call, empty answer"
