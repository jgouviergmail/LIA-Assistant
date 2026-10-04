"""Versioned host-owned model views, distinct from persisted display content."""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, BaseMessage

from src.infrastructure.llm.message_text import coerce_content_to_text

MODEL_VIEW_KEY = "lia_model_view"
MODEL_VIEW_VERSION = 1
CARD_ACTIONS_KEY = "lia_card_actions"


def model_view_content(message: BaseMessage) -> str | None:
    """Only final assistant messages may carry a supported semantic snapshot."""
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


def content_for_model(message: BaseMessage) -> str:
    """Read the semantic snapshot when available, with legacy/block compatibility."""
    view = model_view_content(message)
    return view if view is not None else coerce_content_to_text(message.content)


def as_model_message(message: BaseMessage) -> BaseMessage:
    """Copy only content; IDs, pairing, usage and provider metadata survive."""
    view = model_view_content(message)
    updates: dict[str, object] = {"content": view} if view is not None else {}
    if CARD_ACTIONS_KEY in message.additional_kwargs:
        updates["additional_kwargs"] = {
            key: value
            for key, value in message.additional_kwargs.items()
            if key != CARD_ACTIONS_KEY
        }
    return message.model_copy(update=updates) if updates else message


def as_model_messages(messages: Sequence[BaseMessage]) -> list[BaseMessage]:
    """Project a model-bound history without changing its source list or messages."""
    return [as_model_message(message) for message in messages]
