"""Every annotation a published item carries, as a MODEL reads it — one registry, one walk.

An item may carry closed annotations beside its own fields: a JEV qualification
(``classification``) and, for an e-mail, where it stands in its conversation
(``reply_state``). Each owns a VIEW that decides, at the moment the item is shown,
what a model is told — its labels and a state the code computes, never the instants
of the reading (``classification_projection``, ``mail_reply_state``).

This module is the one door every model-facing serializer goes through: the tool
data block, the pipeline's one-line summaries, the filtering evidence, the archived
answers a later turn reads again. A second walker per annotation would be a second
place to forget one: on 2026-10-26 a single serializer that kept the raw
qualification made a response call current labels expired. An annotation is added
HERE, once, and every serializer follows.

Each annotation is read on its own. Dropping « reply expected » from the qualification
of a message the person answered was tried and measured (2026-11-11, ADR-379): the
response model counted that message among those asking for something just as often,
because it reads the request in the message's own words. What settles it is the reply
state and the rule the prompts state — not a view that hides a label.

The source is never rewritten: the cards and the registry read the same structured
data and need each annotation whole.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Final

from src.core.classification_projection import (
    CLASSIFICATION_KEY,
    classification_text,
    classification_view,
)
from src.core.mail_reply_state import REPLY_STATE_KEY, reply_state_text, reply_state_view

_View = Callable[[object, datetime | None], dict[str, str] | None]
_Text = Callable[[object, datetime | None], str]

#: The key an item carries each annotation under, with what a model is told of it:
#: its view (structured) and its one-line form. The order is the order a payload's
#: lines are stated in.
_ANNOTATIONS: Final[Mapping[str, tuple[_View, _Text]]] = {
    CLASSIFICATION_KEY: (classification_view, classification_text),
    REPLY_STATE_KEY: (reply_state_view, reply_state_text),
}
#: The keys under which an item carries an annotation.
ANNOTATION_KEYS: Final[frozenset[str]] = frozenset(_ANNOTATIONS)

# An annotation key as ``json.dumps`` writes it with its default separators.
_SERIALIZED_KEY: Final = re.compile(
    "|".join(f'"(?P<{key}>{re.escape(key)})": ' for key in _ANNOTATIONS)
)
_DECODER: Final = json.JSONDecoder()


def annotation_view(key: str, value: object, now: datetime | None = None) -> dict[str, str] | None:
    """What a model is told of the value an item carries under ``key``.

    Args:
        key: The field's name.
        value: What the item carries under it.
        now: The moment it is shown; the current instant by default.

    Returns:
        The annotation's model view; None when ``key`` names no annotation or the
        value is not one — the caller then projects the field as any other.
    """
    entry = _ANNOTATIONS.get(key)
    return entry[0](value, now) if entry is not None else None


def annotation_texts(payload: Mapping[str, object], now: datetime | None = None) -> list[str]:
    """The line each annotation of a payload states, the silent ones left out.

    Args:
        payload: An item's payload.
        now: The moment it is shown; the current instant by default.

    Returns:
        One line per annotation that has something to say, in a stable order.
    """
    lines = (text(payload.get(key), now) for key, (_, text) in _ANNOTATIONS.items())
    return [line for line in lines if line]


def model_annotations(data: Mapping[str, object], now: datetime | None = None) -> dict[str, object]:
    """A copy of tool data where every annotation is its model view.

    A value under an annotation's key that is no annotation is left as it is.

    Args:
        data: The data a tool returned, as the model will read it.
        now: The moment it is shown; the current instant by default.

    Returns:
        The same shape, each annotation replaced by its view.
    """
    moment = now if now is not None else datetime.now(UTC)
    return {key: _projected(key, value, moment) for key, value in data.items()}


def serialized_annotations(text: str, now: datetime | None = None) -> str:
    """:func:`model_annotations` over JSON the application serialized itself.

    An answer's model view archives its data as JSON with each annotation whole,
    and later turns read it again (2026-10-26: a history kept handing the ReAct
    loop raw instants after the tool data had stopped). The state is decided
    here, when the text is read, never when the answer was written. Only a real
    key matches: inside a JSON string every quote is escaped, so quoted text
    never reads as an annotation, and a value that is none is left as it is.

    Args:
        text: Text holding serialized records (prose and wrappers around them).
        now: The moment it is shown; the current instant by default.

    Returns:
        The same text, each serialized annotation replaced by its view; the very
        same object when it carries no annotation key.
    """
    found = _SERIALIZED_KEY.search(text)
    if found is None:
        return text
    moment = now if now is not None else datetime.now(UTC)
    chunks: list[str] = []
    copied = 0
    while found is not None:
        start = found.end()
        searched = start
        view = _serialized_view(text, found.lastgroup or "", start, moment)
        if view is not None:
            projected, searched = view
            chunks += [text[copied:start], projected]
            copied = searched
        found = _SERIALIZED_KEY.search(text, searched)
    chunks.append(text[copied:])
    return "".join(chunks)


def _serialized_view(text: str, key: str, start: int, now: datetime) -> tuple[str, int] | None:
    """The view of the JSON value starting at ``start``, and where that value ends."""
    try:
        value, end = _DECODER.raw_decode(text, start)
    except json.JSONDecodeError:
        return None
    view = annotation_view(key, value, now)
    return (json.dumps(view, ensure_ascii=False), end) if view is not None else None


def _projected(key: str, value: object, now: datetime) -> object:
    if (view := annotation_view(key, value, now)) is not None:
        return view
    if isinstance(value, Mapping):
        return {str(k): _projected(str(k), v, now) for k, v in value.items()}
    if isinstance(value, list):
        return [_projected("", item, now) for item in value]
    return value


__all__ = [
    "ANNOTATION_KEYS",
    "annotation_texts",
    "annotation_view",
    "model_annotations",
    "serialized_annotations",
]
