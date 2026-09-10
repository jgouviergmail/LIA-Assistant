"""Handing tickets back without depending on the board that holds them.

`domains/workboard` imports `domains/peers` — the service re-checks the
connection at every write and at every run claim (ADR-276 D8) — so a `peers`
module importing the board back would close a cycle. The coupling ratchet counts
LOCAL imports too, so hiding it inside a function would not help; it would only
make the edge harder to see.

The dependency is therefore inverted, exactly as `consultation_sink` and
`proactive_sink` already do it: this module holds a seam, the board INSTALLS
itself into it at import, and `peers` calls the seam without importing anyone.
Nothing here imports anything.

Two contracts the callers rely on:

- **With nothing installed the call answers « nothing moved »**, never raises: a
  script, a probe or a narrow unit test has no board open, and a helper that
  raised there would turn a bookkeeping concern into an outage. The boot still
  REFUSES a mute seam (`releaser_is_installed`), because an import side effect
  nobody declares is one that stops happening the day someone reorders a module
  (ADR-270).
- **A board that fails never costs the severance.** The connection is already
  gone in the same transaction; a failure to hand its tickets back must be
  loud in the logs and invisible to the caller, who would otherwise have to
  choose between rolling back a severance the person asked for and swallowing
  an exception itself.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class TicketReleaser(Protocol):
    """What the board offers a domain whose relationship just ended."""

    async def __call__(self, *, db: Any, user_a: UUID, user_b: UUID) -> dict[UUID, int]:
        """Hand back every ticket the two accounts share, both directions.

        Args:
            db: The caller's session — the release belongs to the SAME
                transaction as the severance that caused it.
            user_a: One side of the pair.
            user_b: The other side.

        Returns:
            How many tickets came back to each OWNER, by their id. Absent means
            zero; an empty mapping means nothing moved.
        """


async def _ignore(*, db: Any, user_a: UUID, user_b: UUID) -> dict[UUID, int]:
    """The seam before the board claims it: nothing is held, nothing moves."""
    return {}


_releaser: TicketReleaser = _ignore


def install_ticket_releaser(releaser: TicketReleaser) -> None:
    """Let the board receive the pairs that end.

    Called once, by the board's own adapter at import.

    Args:
        releaser: The board's release function.
    """
    global _releaser  # noqa: PLW0603 — one seam, installed once, by its owner
    _releaser = releaser


async def release_tickets_between(*, db: Any, user_a: UUID, user_b: UUID) -> dict[UUID, int]:
    """Hand back every ticket the two accounts share, through the installed board.

    Args:
        db: The caller's session.
        user_a: One side of the pair.
        user_b: The other side.

    Returns:
        How many tickets came back to each owner; an empty mapping when nothing
        moved, when no board is installed, or when the board itself failed.
    """
    try:
        return await _releaser(db=db, user_a=user_a, user_b=user_b)
    except Exception as failure:  # noqa: BLE001 — never costs the severance
        # Local import: this module imports NOTHING at load time, which is what
        # keeps the seam free of the cycle it exists to break.
        import structlog

        structlog.get_logger(__name__).error(
            "workboard_release_failed",
            error=str(failure),
            error_type=type(failure).__name__,
        )
        return {}


def releaser_is_installed() -> bool:
    """Whether the board has claimed the seam — for the boot guard only."""
    return _releaser is not _ignore


__all__ = [
    "TicketReleaser",
    "install_ticket_releaser",
    "release_tickets_between",
    "releaser_is_installed",
]
