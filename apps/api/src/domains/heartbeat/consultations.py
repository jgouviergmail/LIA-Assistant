"""The heartbeat sweep's half of the consultation vocabulary.

The most consequential instance of the defect the briefing and the debrief
already paid for. ``record_treatment`` fires from exactly one place — the tool
gate — and this aggregator reads sixteen sources through direct calls, in
parallel, **on LIA's own initiative and while nobody is watching**: 824 runs
over thirty days, and not one row in the consultation register (measured
2026-09-07).

That is the surface where a register matters most. A person can reconstruct
what a conversation read by re-reading the conversation; they have no way at
all to know that their mail and their calendar were opened at 04:00.

The names and the authorship are declared with every other direct-read surface
in :mod:`src.domains.shared.consultation_surfaces`; what this module owns is
the correspondence to the aggregator's own source keys, and which of them the
second pass fetches.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from src.domains.shared.consultation_surfaces import (
    CONSULTATION_SURFACES,
    record_surface_consultations,
)

#: This surface's key, shared with ``CONSULTATION_RECORDERS``.
SURFACE: Final[str] = "heartbeat"

_SURFACE = CONSULTATION_SURFACES[SURFACE]

#: What every heartbeat capability name starts with, so the register can tell
#: them apart from tool names without matching each one.
CONSULTATION_PREFIX: Final[str] = _SURFACE.prefix

#: What the aggregator's second pass CAN open, in the order it tries them.
#: What it DID open is decided by the per-source gates and returned by
#: ``_second_pass`` — this list is the declaration, never the runtime answer:
#: appending it unconditionally recorded a journal read for people who had
#: switched their journals off (found by a cold review, 2026-09-07).
SECOND_PASS_SOURCES: Final[list[str]] = ["journals", "departure", "memories"]

#: Each source of the aggregator, and the noun the register headlines it with.
SECTION_DOMAINS: Final[dict[str, str]] = dict(_SURFACE.domains)


def consultation_capability(source: str) -> str:
    """The register name of one heartbeat source.

    Args:
        source: Source key, as the aggregator's ``specs`` names it.

    Returns:
        The bounded capability name, e.g. ``heartbeat:emails``.
    """
    return _SURFACE.capability(source)


def record_source_consultations(
    *,
    user_id: object,
    opened: Iterable[str],
    failed: Iterable[str],
    duration_ms: int,
) -> None:
    """Record one consultation per source the sweep actually opened.

    A source the person silenced records nothing: ``is_source_enabled`` already
    skipped it before the coroutine was built, so it was never opened.

    Args:
        user_id: Whose data was read. The run id comes from the collector the
            sweep published — a fetcher deep in the aggregation has no other
            use for an identifier.
        opened: Source keys whose fetch was actually planned and awaited.
        failed: Source keys whose fetch raised; the rest answered.
        duration_ms: Wall-clock duration of the whole aggregation.
    """
    record_surface_consultations(
        surface=SURFACE,
        user_id=user_id,
        opened=opened,
        failed=failed,
        duration_ms=duration_ms,
    )


__all__ = [
    "CONSULTATION_PREFIX",
    "SECOND_PASS_SOURCES",
    "SECTION_DOMAINS",
    "SURFACE",
    "consultation_capability",
    "record_source_consultations",
]
