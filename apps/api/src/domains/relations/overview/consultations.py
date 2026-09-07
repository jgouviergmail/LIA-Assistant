"""The relationship debrief's half of the consultation vocabulary.

``record_treatment`` fires from exactly one place — the tool gate — and this
assembly reads its sources through direct calls. The consultations of a debrief
were therefore absent BY CONSTRUCTION, and a reader who had just generated one
found, at the top of the register, a briefing card read from a few seconds
later: they reasonably concluded the debrief had been filed under the wrong
name, when it had been filed under no name at all (reported from production,
2026-09-07).

Two rules inherited from the 360° scope (ADR-269):

- **outside the scope, nothing is recorded.** « I did not look, on purpose » is
  the reader's own decision; a row would invent a read that never happened.
- **unreadable is not empty.** A section the scope asked for and the provider
  refused reads as ``failed``, never as a silent success.

The recording lives HERE and not inside ``build_overview_evidence``, which the
360° tool shares: that tool already gets its row from the tool gate, and adding
per-section rows there would double its footprint in the register.

The names and the authorship are declared with every other direct-read surface
in :mod:`src.domains.shared.consultation_surfaces`.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from src.domains.shared.consultation_surfaces import (
    CONSULTATION_SURFACES,
    record_surface_consultations,
)

#: This surface's key, shared with ``CONSULTATION_RECORDERS``.
SURFACE: Final[str] = "relation_debrief"

_SURFACE = CONSULTATION_SURFACES[SURFACE]

#: What every 360° capability name starts with, so the register can tell them
#: apart from tool names without matching each one.
CONSULTATION_PREFIX: Final[str] = _SURFACE.prefix

#: Each section, and the noun the register headlines it with.
SECTION_DOMAINS: Final[dict[str, str]] = dict(_SURFACE.domains)


def consultation_capability(section: str) -> str:
    """The register name of one 360° section.

    Args:
        section: Section key, from :class:`OverviewSection`.

    Returns:
        The bounded capability name, e.g. ``relation:emails``.
    """
    return _SURFACE.capability(section)


def record_evidence_consultations(
    *,
    user_id: object,
    run_id: str,
    requested: Iterable[str],
    unavailable: Iterable[str],
    duration_ms: int,
) -> None:
    """Record one consultation per source the scope asked for.

    Args:
        user_id: Whose relationship was read.
        run_id: The build this belongs to.
        requested: Section values the scope allowed — the ONLY ones recorded.
        unavailable: Section values that could not be read; the rest answered.
        duration_ms: Wall-clock duration of the whole assembly. The sources are
            gathered concurrently, so the same figure is carried by each row
            rather than an invented per-source split.
    """
    record_surface_consultations(
        surface=SURFACE,
        user_id=user_id,
        run_id=run_id,
        opened=requested,
        failed=unavailable,
        duration_ms=duration_ms,
    )


__all__ = [
    "CONSULTATION_PREFIX",
    "SECTION_DOMAINS",
    "SURFACE",
    "consultation_capability",
    "record_evidence_consultations",
]
