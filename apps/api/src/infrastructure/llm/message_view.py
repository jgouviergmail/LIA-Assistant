"""Versioned host-owned model views, distinct from persisted display content."""

from collections.abc import Sequence
from datetime import UTC, datetime

from langchain_core.messages import AIMessage, BaseMessage

from src.core.classification_projection import serialized_classifications
from src.infrastructure.llm.message_text import coerce_content_to_text

MODEL_VIEW_KEY = "lia_model_view"
MODEL_VIEW_VERSION = 1
CARD_ACTIONS_KEY = "lia_card_actions"


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
    instant, never the state of the moment the answer was written (ADR-351).

    Args:
        message: Any message of a model-bound history.
        now: The moment it is read; the current instant by default.

    Returns:
        The snapshot text, or ``None`` when the message carries no supported one.
    """
    stored = stored_model_view(message)
    return serialized_classifications(stored, now) if stored is not None else None


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
