"""Versioned host-owned model views, distinct from persisted display content.

A model also reads WHEN an earlier message was written (lot 17): the person's
message carries the instant it arrived (``WRITTEN_AT_KEY``, set when its turn
begins), a message restored from the archive carries its own, and
:func:`with_written_at` prefixes each one in the person's zone. Measured on
three families, without it a history restored days later reads as if everything
had just been said.
"""

from collections.abc import Sequence
from datetime import UTC, datetime, tzinfo
from typing import Any

from langchain_core.messages import AIMessage, BaseMessage

from src.core.annotation_projection import serialized_annotations
from src.infrastructure.llm.message_text import coerce_content_to_text

MODEL_VIEW_KEY = "lia_model_view"
MODEL_VIEW_VERSION = 1
CARD_ACTIONS_KEY = "lia_card_actions"
#: Where a message keeps the instant it was written (ISO 8601, with its offset).
WRITTEN_AT_KEY = "original_created_at"
#: Technical English, whatever the process locale: only a model reads a stamp (ADR-323).
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def written_at(message: BaseMessage) -> datetime | None:
    """The instant a message was written, or None when it carries none.

    A value with no offset is a wall time, not an instant: it is never guessed
    into one (ADR-380).
    """
    raw = message.additional_kwargs.get(WRITTEN_AT_KEY)
    if not isinstance(raw, str):
        return None
    try:
        moment = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else None


def stamped_now[M: BaseMessage](message: M, at: datetime) -> M:
    """A copy of the message carrying the instant it was written; what it says is untouched."""
    kwargs = {**message.additional_kwargs, WRITTEN_AT_KEY: at.isoformat()}
    return message.model_copy(update={"additional_kwargs": kwargs})


def _label(moment: datetime, zone: tzinfo) -> str:
    local = moment.astimezone(zone)
    return (
        f"{_WEEKDAYS[local.weekday()]} {local.day:02d} {_MONTHS[local.month - 1]} "
        f"{local.year}, {local.hour:02d}:{local.minute:02d}"
    )


def _stamp(label: str) -> str:
    return f"[{label}]"


def written_prefix(message: BaseMessage, zone: tzinfo) -> str:
    """What a reader flattening messages to text writes before this one.

    Args:
        message: A message of a model-bound history.
        zone: The person's display zone.

    Returns:
        The stamp and a space, the same shape :func:`with_written_at` writes, or
        nothing when the message carries no instant.
    """
    moment = written_at(message)
    return f"{_stamp(_label(moment, zone))} " if moment else ""


def present_label(zone: tzinfo, now: datetime | None = None) -> str:
    """The present as a reader of stamped messages is told it: a stamp's shape, the zone named.

    The background extractions (memories, interests, open loops, journal) read the
    exchange stamped in the person's zone; their present is written in the same zone,
    so a relative date resolves against one clock (ADR-381 amendment, ADR-380).

    Args:
        zone: The person's display zone.
        now: The present; the current instant by default.

    Returns:
        For example ``Fri 13 Nov 2026, 11:30 (America/Los_Angeles)``.
    """
    moment = now if now is not None else datetime.now(UTC)
    name = getattr(zone, "key", None) or str(zone)
    return f"{_label(moment, zone)} ({name})"


def _prefixed(message: BaseMessage, label: str) -> BaseMessage:
    content: Any = message.content
    if isinstance(content, str):
        updated: Any = f"{_stamp(label)} {content}"
    elif isinstance(content, list):
        updated = [{"type": "text", "text": _stamp(label)}, *content]
    else:
        return message
    return message.model_copy(update={"content": updated})


def with_written_at(messages: Sequence[BaseMessage], zone: tzinfo) -> list[BaseMessage]:
    """A model-bound history where each message carrying its instant starts with it.

    The current question included: its bytes are then the same while it is asked
    and once it is earlier, so a prompt cache that reads a turn back through its
    question (ADR-309) still holds. Only the person's messages and the archive's
    carry an instant; LIA's answer follows the person's message at once.

    Args:
        messages: The history a model is about to read (never changed: copies).
        zone: The person's display zone, in which the moment is written.

    Returns:
        The history, stamped. A message with no recorded instant reads as before.
    """
    stamped: list[BaseMessage] = []
    for message in messages:
        moment = written_at(message)
        stamped.append(_prefixed(message, _label(moment, zone)) if moment else message)
    return stamped


def stored_model_view(message: BaseMessage) -> str | None:
    """The snapshot as archived, to MEASURE it: a model reads :func:`model_view_content`.

    Only final assistant messages may carry a supported semantic snapshot. The
    token counters read this form because it never changes between two reads,
    so their per-message memo holds; it still carries each annotation whole.
    """
    if not isinstance(message, AIMessage) or message.tool_calls:
        return None
    view = message.additional_kwargs.get(MODEL_VIEW_KEY)
    if not isinstance(view, dict):
        return None
    version = view.get("version")
    if type(version) is not int or version != MODEL_VIEW_VERSION:
        return None
    content = view.get("content")
    return content if isinstance(content, str) and content else None


def model_view_content(message: BaseMessage, now: datetime | None = None) -> str | None:
    """The semantic snapshot as a model reads it.

    The snapshot archives each annotation whole and later turns read it again, so
    the state of every annotation is decided here, when it is read — never an
    instant, never the state of the moment the answer was written (ADR-351): a
    qualification past its validity reads expired, a « no reply yet » read on an
    earlier turn reads not checked (ADR-379).

    Args:
        message: Any message of a model-bound history.
        now: The moment it is read; the current instant by default.

    Returns:
        The snapshot text, or ``None`` when the message carries no supported one.
    """
    stored = stored_model_view(message)
    return serialized_annotations(stored, now) if stored is not None else None


def content_for_model(message: BaseMessage) -> str:
    """Read the semantic snapshot when available, with legacy/block compatibility."""
    view = model_view_content(message)
    return view if view is not None else coerce_content_to_text(message.content)


def as_model_message(message: BaseMessage, now: datetime | None = None) -> BaseMessage:
    """Copy only content; IDs, pairing, usage and provider metadata survive."""
    view = model_view_content(message, now)
    updates: dict[str, object] = {"content": view} if view is not None else {}
    if CARD_ACTIONS_KEY in message.additional_kwargs:
        updates["additional_kwargs"] = {
            key: value
            for key, value in message.additional_kwargs.items()
            if key != CARD_ACTIONS_KEY
        }
    return message.model_copy(update=updates) if updates else message


def as_model_messages(
    messages: Sequence[BaseMessage], now: datetime | None = None
) -> list[BaseMessage]:
    """Project a model-bound history without changing its source list or messages.

    Args:
        messages: The history to project.
        now: The moment the history is read — one for the whole list.
    """
    moment = now if now is not None else datetime.now(UTC)
    return [as_model_message(message, moment) for message in messages]
