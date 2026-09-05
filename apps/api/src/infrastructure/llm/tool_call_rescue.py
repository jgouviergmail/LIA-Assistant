"""Recover a tool call the schema rejected for its ``null`` values.

A model that fills every property of a tool schema writes ``null`` where it
has nothing to say. Pydantic refuses ``null`` on a ``list[str]`` field even
when the field has a default, so the whole answer was thrown away and the
caller told the model had not answered (replayed in production 2026-09-05:
``deepseek-v4-flash``, a complete minutes payload, ``"bullets": null`` on a
paragraph section, three identical rejections).

The rule is structural, never per schema: a ``null`` under a key whose field
HAS a default and does NOT admit ``None`` is the model's spelling of « absent »
and the key is dropped so the default applies; a ``null`` on an Optional field
is a value and stays; a ``null`` on a required field is an error and stays.
Nested models and lists of models are walked the same way.
"""

from __future__ import annotations

import types
from collections.abc import Sequence
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, ValidationError

from src.infrastructure.llm.message_text import coerce_content_to_text

#: Paths listed in a rejection reason before the list is cut (a log line, not a report).
_REASON_PATHS_MAX = 8


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


def rejection_reason(raw_message: Any, parsing_error: BaseException | None) -> str:
    """Why a native structured answer yielded nothing — the words the log carries.

    A rejected tool call is named as such, with the schema paths that failed;
    it is never reported as « no tool call ».
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
    text = coerce_content_to_text(getattr(raw_message, "content", None) or "").strip()
    return "no tool call, text rescue failed" if text else "no tool call, empty answer"
