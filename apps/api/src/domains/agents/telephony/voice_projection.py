"""A tool result reduced to what a VOICE can say (lot 8 of the phone channel).

Measured on production 2026-09-16: a weekend agenda lookup returned four
events and the voice agent heard ONE. The live-tool projection paged the RAW
tool items — a Google event carries its id, its link, its attendees with
their response status, its reminders, its colour id — under a token budget,
and a single raw event filled it. A bigger budget is not the remedy: a voice
never reads an identifier, a link or a nested structure, so every item is
first reduced to what can be SAID, and the item-by-item paging of ADR-286
then decides how many fit.

Three rules, each a function of the SHAPE, never of the tool:

- a key that names an identifier, a link, a payload or a wire detail is
  dropped (``id``, ``htmlLink``, ``iCalUID``, ``etag``, ``colorId``,
  ``payload``, ``mimeType``…);
- a scalar is kept, a long text cut at :data:`MAX_SPOKEN_TEXT_CHARS`;
- a nested value speaks through its spoken form when it has one (a
  ``formatted`` date, a ``name``, a ``title``…) and is dropped otherwise; a
  list of words is joined into words, a list of records becomes a count.
"""

from __future__ import annotations

import re
from typing import Any, Final

#: A long text is cut here, with an ellipsis: a voice reads a gist, not a body.
MAX_SPOKEN_TEXT_CHARS: Final = 240
#: Keys a voice never reads: identifiers, links, wire details (matched on the
#: lower-cased key, ``camelCase`` included).
_UNSPOKEN_KEY: Final = re.compile(
    r"(^|_)(id|ids|uid|token|etag|self|kind|mimetype|mime_type|internaldate|internal_date)$"
    r"|link$|url$|uri$|^ical|^payload$|color_?id$|^etag$",
    re.IGNORECASE,
)
#: The fields a nested value speaks through, in order of preference.
_SPOKEN_FORMS: Final = ("formatted", "display", "name", "title", "summary", "label", "text")


def _is_unspoken(key: str) -> bool:
    return bool(_UNSPOKEN_KEY.search(key.replace("-", "_")))


def _spoken_text(value: str) -> str:
    text = value.strip()
    if len(text) <= MAX_SPOKEN_TEXT_CHARS:
        return text
    return text[:MAX_SPOKEN_TEXT_CHARS] + "…"


def _spoken_form(value: dict[str, Any]) -> str | None:
    for field in _SPOKEN_FORMS:
        spoken = value.get(field)
        if isinstance(spoken, str) and spoken.strip():
            return _spoken_text(spoken)
    return None


def compact_item(item: dict[str, Any]) -> dict[str, Any]:
    """Reduce one record to what a voice can say.

    Args:
        item: A tool item (an event, a message, a contact…).

    Returns:
        A flat dict of spoken values, in the item's key order.
    """
    out: dict[str, Any] = {}
    for key, value in item.items():
        if _is_unspoken(str(key)):
            continue
        spoken = _spoken_value(value)
        if spoken is not None:
            out[key] = spoken
    return out


def _is_word(value: Any) -> bool:
    return isinstance(value, str | int | float) and not isinstance(value, bool)


def _spoken_value(value: Any) -> Any | None:
    """What a voice says of one value, or None when it says nothing."""
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, str):
        return _spoken_text(value) if value.strip() else None
    if isinstance(value, dict):
        return _spoken_form(value)
    if isinstance(value, list) and value:
        if all(_is_word(v) for v in value):
            return _spoken_text(", ".join(str(v) for v in value))
        if all(isinstance(v, dict) for v in value):
            return len(value)
    return None


def compact_items(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce the item lists of a tool's data, keep its scalars, drop its ids.

    Args:
        data: The tool's ``structured_data`` (or grouped registry payloads).

    Returns:
        The same shape with every record list compacted, ready for the
        item-by-item paging.
    """
    out: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            out[key] = [compact_item(v) for v in value]
        elif _is_unspoken(str(key)):
            continue
        else:
            out[key] = value
    return out


__all__ = ["MAX_SPOKEN_TEXT_CHARS", "compact_item", "compact_items"]
