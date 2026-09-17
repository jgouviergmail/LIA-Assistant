"""What the portrait reads besides the journal: four sections, one provenance.

The consolidation compiles the user portrait from the journal entries and,
since the 2026-09-16 design (part B), from four other records LIA keeps —
memories, interests, learned habits, relationship debriefs. This module asks
each of them through the seam (``domains/shared/portrait_sources``: the
sources install their readers, ``journals`` imports nobody) and hands the
prompt its four sections plus the PROVENANCE the portrait is persisted with:
which source was read, how much of it, which was switched off, which could
not be read. A portrait that says what it was compiled from is a portrait a
person can correct (ADR-269's ``sections_used`` contract).

Three rules:

- readers run ONE AT A TIME: four short reads, and a ``gather`` would hold
  four sessions open for nothing (measured, the ``gather``-per-probe trap);
- the global cap drops a section WHOLE and reports it ``unavailable`` — a cut
  mid-item would hand the model half a memory;
- a section absent from the prompt is UNKNOWN to the model, not empty; the
  provenance is where the difference is recorded.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.shared.portrait_sources import (
    ITEMS_BOUNDED_BY_SOURCE,
    PORTRAIT_SOURCE_KEYS,
    PortraitSourceSection,
    SourceBudget,
    installed_portrait_sources,
)
from src.infrastructure.observability.metrics_journals import journal_portrait_sources_total

logger = structlog.get_logger(__name__)

#: The persisted provenance's shape; bump when a reader of the JSON must change.
PROVENANCE_VERSION = 1


@dataclass(frozen=True, slots=True)
class PortraitSourceBundle:
    """What the prompt receives and what the portrait is persisted with.

    Attributes:
        sections: ``key → rendered section`` in the declared order (``""``
            when absent from the prompt).
        provenance: The JSON written beside the portrait.
    """

    sections: dict[str, str]
    provenance: dict[str, Any]


def _budget_for(key: str) -> SourceBudget:
    """Each source's item budget, from the settings; habits are bounded by construction."""
    items = {
        "memories": settings.journal_consolidation_memories_max,
        "interests": settings.journal_consolidation_interests_max,
        "relation_debriefs": settings.journal_consolidation_debriefs_max,
    }.get(key, ITEMS_BOUNDED_BY_SOURCE)
    return SourceBudget(
        max_items=items, item_max_chars=settings.journal_consolidation_source_item_max_chars
    )


def _count(section: PortraitSourceSection) -> None:
    with suppress(Exception):  # metrics never break the consolidation
        journal_portrait_sources_total.labels(source=section.key, status=section.status).inc()


def _over_cap(section: PortraitSourceSection, spent: int) -> PortraitSourceSection:
    """The section as reported when it would break the global cap."""
    logger.warning(
        "portrait_source_dropped_over_cap",
        source=section.key,
        section_chars=len(section.text),
        spent_chars=spent,
        cap=settings.journal_consolidation_sources_max_chars,
    )
    return PortraitSourceSection(
        key=section.key, status="unavailable", text="", used=0, total=section.total
    )


async def build_portrait_source_sections(
    user_id: UUID, language: str, *, journal_entries: int
) -> PortraitSourceBundle:
    """Read the four sources for one account, in order, under their budgets.

    Args:
        user_id: The account whose portrait is compiled.
        language: The account's language.
        journal_entries: How many entries the prompt carries (provenance).

    Returns:
        The sections and the provenance; never raises (a reader answers
        ``unavailable`` for its own failure, and the seam is read-only).
    """
    cap = settings.journal_consolidation_sources_max_chars
    sections: dict[str, str] = dict.fromkeys(PORTRAIT_SOURCE_KEYS, "")
    provenance: dict[str, dict[str, Any]] = {}
    spent = 0
    for key, (reader, _probe) in installed_portrait_sources().items():
        section = await reader(user_id=user_id, language=language, budget=_budget_for(key))
        if section.text and spent + len(section.text) > cap:
            section = _over_cap(section, spent)
        _count(section)
        if section.text:
            sections[key] = section.text
            spent += len(section.text)
        provenance[key] = {"status": section.status, "used": section.used, "total": section.total}
    logger.info(
        "portrait_sources_assembled",
        user_id=str(user_id),
        chars=spent,
        statuses={key: value["status"] for key, value in provenance.items()},
    )
    return PortraitSourceBundle(
        sections=sections,
        provenance={
            "version": PROVENANCE_VERSION,
            "journal_entries": journal_entries,
            "sources": provenance,
        },
    )


__all__ = ["PROVENANCE_VERSION", "PortraitSourceBundle", "build_portrait_source_sections"]
