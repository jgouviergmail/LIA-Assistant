"""Saying which of the listener's sources the radio actually read (ADR-263, ADR-324).

The radio reads the person's material through the briefing's shared source readers
when their cache is absent, and through its own readers — tickets,
meetings, notifications, quiet relationships, knowledge spaces, kept answers,
the conversation under way — and their taste at the start (interests, stated
preferences). None of that goes through a tool, so the gate that fills the
consultation register never sees it: the radio says it here.

Three rules the register already holds, and the radio keeps:

- a section read from the Today Briefing's CACHE is never a consultation —
  Redis answered, no source was opened — so it is never passed here;
- a reader that raised is ``failed``, never a silent success;
- every read is filed under the session's run, inside a collector the read
  opens itself: the loop runs alone, and a row recorded outside a published
  collector is DROPPED by the sink (the ``space`` surface's lesson, 2026-09-17).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final
from uuid import UUID

from src.domains.radio.readers import ConsultationRecorder
from src.domains.shared.consultation_sink import collector_is_active, consultation_collector
from src.domains.shared.consultation_surfaces import record_surface_consultations

#: This surface's key, shared with ``CONSULTATION_RECORDERS``.
SURFACE: Final[str] = "radio"


def recorder_for(user_id: UUID, run_id: str) -> ConsultationRecorder:
    """The recorder of one session's reads.

    Args:
        user_id: The listener, whose data was read.
        run_id: The session's run.

    Returns:
        A recorder filing every read under the radio's surface and that run.
    """

    def record(*, opened: frozenset[str], failed: frozenset[str], duration_ms: int) -> None:
        record_surface_consultations(
            surface=SURFACE,
            user_id=user_id,
            opened=opened,
            failed=failed,
            duration_ms=duration_ms,
            run_id=run_id,
        )

    return record


@asynccontextmanager
async def collecting(run_id: str) -> AsyncIterator[None]:
    """A collector around one gathering of the session, unless a run already collects.

    Args:
        run_id: The session's run, every collected row's.

    Yields:
        Nothing; the block does the reading, and the rows are written when it ends.
    """
    if collector_is_active():
        yield
        return
    async with consultation_collector(run_id):
        yield


__all__ = ["SURFACE", "collecting", "recorder_for"]
