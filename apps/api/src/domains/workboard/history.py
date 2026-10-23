"""How the ticket history spells a holder, written once for every writer.

A hand-over is filed by three writers — the service (the screen and the chat),
the release of a removed connection, and a run handing a ticket back — and the
panel reads the same four keys from all of them to draw « held by: me → LIA ».
Two of them used to file the destination alone, so the history said who held a
ticket and never who had held it a moment before. The creation entry carries
the first holder the same way, so the first change of the thread has a
starting point.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from uuid import UUID

#: The side of a hand-over: who held the ticket before, who holds it after.
HolderSide = Literal["from", "to"]


def holder_fields(side: HolderSide, kind: str, user_id: UUID | None) -> dict[str, str | None]:
    """One end of a hand-over, as the history stores it.

    Args:
        side: ``from`` for the previous holder, ``to`` for the new one.
        kind: ``human`` or ``lia`` (``AssigneeKind``).
        user_id: The person who holds it, or None for the ticket's owner (the
            column's own convention, ADR-276) and for LIA.

    Returns:
        ``{"<side>_kind": kind, "<side>_user": id or None}``.
    """
    return {f"{side}_kind": kind, f"{side}_user": str(user_id) if user_id else None}


__all__ = ["HolderSide", "holder_fields"]
