"""One answer for what a conversation holds, whichever provider keeps it (ADR-369, lot 8).

What makes a conversation differs: a Gmail thread, a Graph ``conversationId``, the headers
on IMAP. What a reader gets does not: the messages, headers alone, oldest first, the newest
kept when there are too many, and the cut said. A draft is the person's unsent words, no
part of what was said. No total is given: Graph and IMAP read at most one more than they
keep, and a count is exact or it does not exist (ADR-185).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any


def conversation_answer(
    said: Sequence[dict[str, Any]], max_messages: int, *, more: bool = False
) -> dict[str, Any]:
    """The newest of what was said, and whether anything was left out.

    Args:
        said: The messages, oldest first.
        max_messages: How many are kept.
        more: The caller knows of messages ``said`` does not hold.

    Returns:
        ``{"messages": [...], "truncated": bool}``.
    """
    kept = list(said[-max_messages:])
    return {"messages": kept, "truncated": more or len(kept) < len(said)}
