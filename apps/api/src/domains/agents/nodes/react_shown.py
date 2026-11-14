"""What a ReAct call is shown beside the thread, never written to it (ADR-310, ADR-385).

Two things a call is shown that the thread does not hold: a recovery pass's draft and
directive (ADR-310), and the person's notes (ADR-385). Written into ``messages``, a
draft would be an answer and a note would be the turn's question for every reader
that takes the last human message as such. Shown per call, each sits right after the
message the loop last had when it happened — past the system messages glued to that
message, so the turn's context stays right after its question (ADR-308) — and items
sharing a place come in the order they happened.

Nothing before an item changes from one call to the next: a generation that binds its
thinking to the conversation reads its loop unchanged (ADR-306), and a cached prefix
holds up to the first item shown.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import structlog
from langchain_core.messages import BaseMessage, SystemMessage

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Shown:
    """Messages one call shows after a message of the thread."""

    #: The id of the message they follow.
    anchor_id: str
    #: When they happened, among the items sharing their place (see the orders below).
    order: int
    #: What the call is shown, in order.
    messages: tuple[BaseMessage, ...]


def recovery_order(pass_index: int) -> int:
    """The place of the turn's ``pass_index``-th recovery pass among items sharing an anchor.

    Args:
        pass_index: The pass's position in ``react_recovery_passes`` (0-based).

    Returns:
        An odd order: a pass comes after the notes read before it.
    """
    return 2 * pass_index + 1


def note_order(passes_before: int) -> int:
    """The place of a note read after ``passes_before`` recovery passes.

    Args:
        passes_before: How many passes the turn had taken when the note was read.

    Returns:
        An even order: a note comes after the passes taken before it, before the next.
    """
    return 2 * passes_before


def with_shown(messages: Sequence[BaseMessage], shown: Sequence[Shown]) -> list[BaseMessage]:
    """The messages of one call, each shown item in its place.

    Args:
        messages: The composed messages of the call.
        shown: What the call is shown beside the thread.

    Returns:
        A new list; the given one is never modified. An item whose anchor is no
        longer in the messages (trimmed from the head) is shown at the end, said.
    """
    by_anchor: dict[str, list[Shown]] = {}
    for item in shown:
        by_anchor.setdefault(item.anchor_id, []).append(item)
    out = list(messages)
    for anchor_id, items in by_anchor.items():
        block = [message for item in sorted(items, key=_order) for message in item.messages]
        at = next((i for i, message in enumerate(out) if message.id == anchor_id), None)
        if at is None:
            logger.warning("react_shown_anchor_missing", item_count=len(items))
            out.extend(block)
            continue
        at += 1
        while at < len(out) and isinstance(out[at], SystemMessage):
            at += 1
        out[at:at] = block
    return out


def _order(item: Shown) -> int:
    return item.order


__all__ = ["Shown", "note_order", "recovery_order", "with_shown"]
