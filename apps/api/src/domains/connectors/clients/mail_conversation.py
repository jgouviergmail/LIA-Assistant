"""One answer for what a conversation holds, whichever provider keeps it (ADR-369, lot 8).

What makes a conversation differs: a Gmail thread, a Graph ``conversationId``, the headers
on IMAP. What a reader gets does not: the messages, headers alone, oldest first, the newest
kept when there are too many, and the cut said. A draft is the person's unsent words, no
part of what was said. No total is given: Graph and IMAP read at most one more than they
keep, and a count is exact or it does not exist (ADR-185).

:class:`Conversation` is the same answer for a reader that also asks where a message
STANDS in it (ADR-379): what was said, the person's unsent words kept apart, the cut.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class Conversation:
    """What a conversation holds, as the reply-state decider reads it.

    Every message speaks the ``EmailMessage`` vocabulary, headers alone, and two
    things a listing does not say: the owner's own messages carry the ``SENT`` label
    whatever the provider (Graph and IMAP file them in a folder, they do not label
    them), and a message may carry what its mailbox says of it —
    ``FIELD_MAIL_ANSWERED`` / ``FIELD_MAIL_ANSWERED_AT`` (the provider's own
    « answered » mark, where it keeps one) and ``FIELD_MAIL_IN_REPLY_TO`` (the
    Message-ID it answers, where the provider exposes it).

    Attributes:
        messages: What was said, oldest first, the newest kept when there were too
            many.
        drafts: The person's unsent messages of the conversation.
        truncated: Older messages than those kept exist.
    """

    messages: tuple[dict[str, Any], ...] = ()
    drafts: tuple[dict[str, Any], ...] = ()
    truncated: bool = False


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
