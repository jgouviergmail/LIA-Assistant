"""The conversation a produced file belongs to, when there is one (ADR-279).

Every producer passes the BUSINESS conversation identity from its typed context,
never LangGraph's thread_id. A rotated runtime is also a UUID but is not a valid
foreign key. Autonomous producers may declare no conversation; a child run keeps
its parent's business identity. This parser cannot infer identity from a UUID.

One reader, because three producers ask the same question and the third copy is
where the ``"unknown"`` case goes missing.
"""

from __future__ import annotations

import uuid

__all__ = ["conversation_uuid"]


def conversation_uuid(conversation_id: object) -> uuid.UUID | None:
    """The conversation id to file a produced attachment under.

    Args:
        conversation_id: The explicitly declared business identity, or None.

    Returns:
        The conversation UUID, or None when there is no conversation (a
        scheduled or ticket run) or when the value is not one. None is a
        legitimate answer: the file is still the person's, it simply belongs to
        no conversation, and the column is nullable for exactly that.
    """
    if isinstance(conversation_id, uuid.UUID):
        return conversation_id
    if not isinstance(conversation_id, str):
        return None
    try:
        return uuid.UUID(conversation_id)
    except ValueError:
        return None
