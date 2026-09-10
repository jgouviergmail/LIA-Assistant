"""The conversation a produced file belongs to, when there is one (ADR-279).

Every producer knows its thread as a STRING — the graph's ``thread_id``, which
is a conversation UUID on the ordinary path and the literal ``"unknown"`` on
paths that have no conversation (a scheduled run, a ticket run, a sub-agent).
The column is a real foreign key, so a value that is not a UUID must become
NULL rather than blow up the write that produces the file.

One reader, because three producers ask the same question and the third copy is
where the ``"unknown"`` case goes missing.
"""

from __future__ import annotations

import uuid

__all__ = ["conversation_uuid"]


def conversation_uuid(thread_id: object) -> uuid.UUID | None:
    """The conversation id to file a produced attachment under.

    Args:
        thread_id: Whatever the producer holds — the graph's ``thread_id``, a
            UUID, or nothing at all.

    Returns:
        The conversation UUID, or None when there is no conversation (a
        scheduled or ticket run) or when the value is not one. None is a
        legitimate answer: the file is still the person's, it simply belongs to
        no conversation, and the column is nullable for exactly that.
    """
    if isinstance(thread_id, uuid.UUID):
        return thread_id
    if not isinstance(thread_id, str):
        return None
    try:
        return uuid.UUID(thread_id)
    except ValueError:
        return None
