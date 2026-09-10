"""The board claims the peer-release seam (ADR-276, lot 5).

Importing this module IS the wiring: it installs `WorkboardService.release_pair`
into `domains/shared/peer_release_sink`, so `peers` can hand tickets back
without importing the board and closing a cycle.

Kept apart from `service.py` for the reason the notification adapter is kept
apart from the runner: a module whose import has a side effect must be the one
thing it does, and the boot step that imports it must be able to say so.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from src.domains.shared.peer_release_sink import install_ticket_releaser

logger = structlog.get_logger(__name__)


async def release_tickets_between(*, db: Any, user_a: UUID, user_b: UUID) -> dict[UUID, int]:
    """Hand every ticket the pair shares back to its owner.

    The write joins the caller's transaction — the severance and the release
    commit together, because a connection that is gone while its tickets stay
    assigned is worse than either alone.

    Args:
        db: The caller's session.
        user_a: One side of the pair.
        user_b: The other side.

    Returns:
        How many tickets came back to each OWNER, by their id. Each side gets a
        different number: a pair usually holds work in both directions, and one
        total would tell each of them something that is not true of them.
    """
    # Local import: the seam module imports nothing, and this adapter is what
    # the boot step imports — the service is loaded here rather than at module
    # scope so the wiring stays the one thing this file does.
    from src.domains.workboard.service import WorkboardService

    # SAVEPOINT, and it is not a precaution: the seam above answers « nothing
    # moved » when the board fails, and that answer is what both sides are
    # TOLD. Measured 2026-09-09 on a real server, without it — the board died
    # after releasing one ticket of two, the seam swallowed, the notification
    # said « 0 », and the caller's own commit wrote the half that had already
    # been mutated. A count shown to a person is exact or it does not exist
    # (ADR-185), so the release is all-or-nothing by construction. The
    # severance itself is outside: `transition_status` is a server-side UPDATE
    # already on the wire before this call, so no rollback here can undo it.
    async with db.begin_nested():
        released = await WorkboardService(db).release_pair(user_a, user_b)
    counts: dict[UUID, int] = {}
    for ticket in released:
        counts[ticket.owner_user_id] = counts.get(ticket.owner_user_id, 0) + 1
    if counts:
        logger.info("workboard_pair_released", owners=len(counts), tickets=len(released))
    return counts


install_ticket_releaser(release_tickets_between)
