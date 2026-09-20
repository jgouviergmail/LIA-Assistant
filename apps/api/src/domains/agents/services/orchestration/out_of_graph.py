"""A row the graph never wrote, as the next turn reads it.

Two families of rows reach the conversation outside a turn and are injected
into the graph state before the next one: a proactive notification (an
``assistant`` row LIA sent on its own initiative) and, since ADR-299, a
voice-only exchange of a live session (``live_turn``, EITHER role). One
function turns a stored row into the message the graph reads; the repository's
predicate says which rows qualify.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from src.core.constants import LIVE_TURN_MESSAGE_TYPE


def out_of_graph_message(row: Any) -> BaseMessage:
    """The graph message of an archived row injected before the next turn.

    Args:
        row: A ``ConversationMessage`` (``role``, ``content``,
            ``message_metadata``, ``created_at``).

    Returns:
        A ``HumanMessage`` for the person's own spoken words, an ``AIMessage``
        otherwise — each carrying the marker the response node reads.
    """
    # Characterised: no metadata reads as "", a metadata without a type as
    # "proactive" — the values the response node has always seen.
    metadata_type = ""
    if row.message_metadata and isinstance(row.message_metadata, dict):
        metadata_type = str(row.message_metadata.get("type", "proactive"))
    original_created_at = row.created_at.isoformat() if row.created_at else None
    if metadata_type == LIVE_TURN_MESSAGE_TYPE:
        kwargs = {"live_turn": True, "original_created_at": original_created_at}
        if row.role == "user":
            return HumanMessage(content=row.content, additional_kwargs=kwargs)
        return AIMessage(content=row.content, additional_kwargs=kwargs)
    return AIMessage(
        content=row.content,
        additional_kwargs={
            "proactive_notification": True,
            "proactive_type": metadata_type,
            "original_created_at": original_created_at,
        },
    )


__all__ = ["out_of_graph_message"]
