"""Saying which of the person's sources a documentary space actually read.

A space is a STANDING INSTRUCTION: « keep this Drive folder indexed », «
follow this Gmail label » (ADR-262). Honouring it means opening the person's
Drive and their mailbox — through the connector CLIENTS, never through the
``@tool`` layer, so the gate that fills the consultation register never sees
any of it.

That silence is loudest where it matters most: a Google push can trigger a
reindex at four in the morning, and the person had no way at all to learn that
their mail had been opened.

The authorship is ``scheduled`` and not ``proactive``: LIA did not decide to
read their mailbox, they asked for it once and it keeps being honoured — the
same word this codebase already uses for a reminder, their own deferred
instruction.

Two sections only, and on purpose: the register names the CAPABILITY, never
the file or the message. « Which of my sources did it open » is the question a
person asks; « which of my 4 000 documents » is a different one, and answering
it here would drown the register the first time a folder synced.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from contextlib import asynccontextmanager
from time import perf_counter
from typing import Final

from src.domains.shared.consultation_surfaces import (
    CONSULTATION_SURFACES,
    record_surface_consultations,
)

#: This surface's key, shared with ``CONSULTATION_RECORDERS``.
SURFACE: Final[str] = "space"

_SURFACE = CONSULTATION_SURFACES[SURFACE]

#: The person's Drive, read to index or to re-index a folder source.
SECTION_DRIVE: Final[str] = "drive"

#: The person's mailbox, read to follow a label source.
SECTION_MAIL: Final[str] = "mail"


def record_space_read(
    *,
    user_id: object,
    section: str,
    failed: bool = False,
    duration_ms: int,
    run_id: str | None = None,
) -> None:
    """Record one read a documentary space performed on the person's sources.

    Args:
        user_id: Whose space, and whose data.
        section: :data:`SECTION_DRIVE` or :data:`SECTION_MAIL`.
        failed: Whether the source refused; the rest answered. « Unreadable »
            is never « empty »: a folder that could not be listed must not read
            as a folder with nothing in it.
        duration_ms: Wall-clock duration of the read.
        run_id: The run this belongs to, or None to take the collector's own.
    """
    record_surface_consultations(
        surface=SURFACE,
        user_id=user_id,
        opened=[section],
        failed=[section] if failed else (),
        duration_ms=duration_ms,
        run_id=run_id,
    )


@asynccontextmanager
async def space_read(
    *,
    user_id: object,
    section: str,
    run_id: str | None = None,
) -> AsyncIterator[None]:
    """Record one read of the person's sources, around the call that makes it.

    One line per site, so every read is recorded the same way and a new one
    cannot be added in a different shape. A read that raises is recorded as
    ``failed`` and the exception continues on its way — observing must never
    change what it observes.

    Args:
        user_id: Whose space, and whose data.
        section: :data:`SECTION_DRIVE` or :data:`SECTION_MAIL`.
        run_id: The run this belongs to, or None to take the collector's own.

    Yields:
        Nothing; the block does the reading.
    """
    started = perf_counter()
    failed = False
    try:
        yield
    except Exception:
        failed = True
        raise
    finally:
        record_space_read(
            user_id=user_id,
            section=section,
            failed=failed,
            duration_ms=int((perf_counter() - started) * 1000),
            run_id=run_id,
        )


def sections() -> Iterable[str]:
    """Every section this surface can record — for the guards."""
    return _SURFACE.domains.keys()


__all__ = [
    "SECTION_DRIVE",
    "SECTION_MAIL",
    "SURFACE",
    "record_space_read",
    "sections",
    "space_read",
]
