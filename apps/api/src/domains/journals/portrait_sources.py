"""What the portrait reads besides the journal: nine sections, one provenance.

The consolidation compiles the user portrait from the journal entries and,
since the 2026-09-16 design (part B), from the other records LIA keeps —
four at first (memories, interests, learned habits, relationship debriefs),
nine since 2026-10-12 (open loops, workboard, routines, reminders, kept
answers joined them). This module asks each of them through the seam
(``domains/shared/portrait_sources``: the sources install their readers,
``journals`` imports nobody) and hands the prompt its sections plus the
PROVENANCE the portrait is persisted with: which source was read, how much of
it, which was switched off, which could not be read. A portrait that says what
it was compiled from is a portrait a person can correct (ADR-269's
``sections_used`` contract).

Three rules:

- readers run ONE AT A TIME: short reads, and a ``gather`` would hold nine
  sessions open for nothing (measured, the ``gather``-per-probe trap);
- every item is rendered WHOLE and every source is read whole: the only bounds
  are physical — a declared share of the consolidation slot's context window,
  and one published length per item line (``PORTRAIT_ITEM_MAX_CHARS``, cut at
  the bound and counted, never dropped) — and when the material exceeds the
  share the LAST sections lose items from their END, at item boundaries, and
  the provenance STATES the cut (a cut mid-item would hand the model half a
  memory, a silent cut would hand it a lie);
- a section absent from the prompt is UNKNOWN to the model, not empty; the
  provenance is where the difference is recorded.
"""

from __future__ import annotations

from contextlib import suppress
from dataclasses import dataclass, replace
from typing import Any
from uuid import UUID

import structlog

from src.core.config import settings
from src.domains.journals.portrait_catalogue import (
    complete_item_lines,
    eligible_source_items,
    render_catalogue_sections,
)
from src.domains.shared.portrait_sources import (
    PORTRAIT_ITEM_MAX_CHARS,
    PORTRAIT_SOURCE_KEYS,
    PortraitSourceSection,
    installed_portrait_sources,
)
from src.infrastructure.llm.providers.token_counter import OpenAITokenCounter
from src.infrastructure.observability.metrics_journals import journal_portrait_sources_total

logger = structlog.get_logger(__name__)

#: The persisted provenance's shape; bump when a reader of the JSON must change.
PROVENANCE_VERSION = 1

#: The offline proxy every budget of the pipeline is counted with.
_PROXY_MODEL = "gpt-4o"


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


def _count(section: PortraitSourceSection) -> None:
    with suppress(Exception):  # metrics never break the consolidation
        journal_portrait_sources_total.labels(source=section.key, status=section.status).inc()


def _rendered_tokens(counter: OpenAITokenCounter, key: str, text: str) -> int:
    """What the section costs AS THE MODEL READS IT: references included."""
    return counter.count(render_catalogue_sections({key: text})[key], _PROXY_MODEL)


def _bounded(section: PortraitSourceSection) -> tuple[PortraitSourceSection, int]:
    """Cut every item line longer than the published bound AT the bound; count the cuts.

    An item is never dropped for its length (the catalogue admits a line up to
    the same bound, so what leaves here is what the model reads and may cite).
    """
    cut = 0
    lines: list[str] = []
    for line in section.text.splitlines():
        if line.startswith("- ") and len(line) > PORTRAIT_ITEM_MAX_CHARS:
            line = line[:PORTRAIT_ITEM_MAX_CHARS].rstrip()
            cut += 1
        lines.append(line)
    return (replace(section, text="\n".join(lines)) if cut else section), cut


def _admit(
    section: PortraitSourceSection, counter: OpenAITokenCounter, spent: int, budget: int
) -> tuple[PortraitSourceSection, int]:
    """Keep the longest prefix of the section's ELIGIBLE items whose rendered form fits.

    The cost of a prefix is the rendered text's exact count and grows with the
    prefix, so the largest fitting prefix is found by bisection — a linear scan
    re-tokenised the whole section once per item (review 2026-10-12).

    Args:
        section: A ``used`` section with text.
        counter: The proxy counter.
        spent: Tokens the earlier sections already took.
        budget: The share of the window the sources may take.

    Returns:
        The admitted section (whole; or cut at item boundaries, ``used`` the
        eligible items kept, ``reason="over_budget"`` — ``used == 0`` when not
        even its header fits, the section then absent from the prompt) and the
        new spend.
    """
    headers = [line for line in section.text.splitlines() if line.startswith("## ")]
    items = [item.quote for item in eligible_source_items(section.key, section.text)]

    def cost(kept: int) -> int:
        return _rendered_tokens(counter, section.key, "\n".join([*headers, *items[:kept]]))

    whole = cost(len(items))
    if spent + whole <= budget:
        return section, spent + whole
    low, high = 0, len(items)  # invariant: cost(low) fits or low == 0; cost(high) does not
    while low < high:
        middle = (low + high + 1) // 2
        if spent + cost(middle) <= budget:
            low = middle
        else:
            high = middle - 1
    kept = low
    logger.warning(
        "portrait_source_cut_at_window_share",
        source=section.key,
        kept=kept,
        total=len(items),
        spent=spent,
        budget=budget,
    )
    if kept == 0:
        return replace(section, text="", used=0, reason="over_budget"), spent
    text = "\n".join([*headers, *items[:kept]])
    return replace(section, text=text, used=kept, reason="over_budget"), spent + cost(kept)


async def build_portrait_source_sections(
    user_id: UUID, language: str, *, journal_entries: int, window_tokens: int
) -> PortraitSourceBundle:
    """Read every source for one account, in order, whole, under one stated share.

    Args:
        user_id: The account whose portrait is compiled.
        language: The account's language.
        journal_entries: How many entries the prompt carries (provenance).
        window_tokens: The consolidation slot's effective context window.

    Returns:
        The sections and the provenance; never raises (a reader answers
        ``unavailable`` for its own failure, and the seam is read-only).
    """
    budget = int(window_tokens * settings.journal_consolidation_sources_window_fraction)
    counter = OpenAITokenCounter()
    sections: dict[str, str] = dict.fromkeys(PORTRAIT_SOURCE_KEYS, "")
    provenance: dict[str, dict[str, Any]] = {}
    spent = 0
    for key, (reader, _probe) in installed_portrait_sources().items():
        section, cut = _bounded(await reader(user_id=user_id, language=language))
        complete = complete_item_lines(section.text)
        omitted = max(section.used - len(complete), 0)
        if section.status == "used":
            eligible = len(dict.fromkeys(complete))
            section = replace(
                section,
                status="used" if eligible else "empty",
                text=section.text if eligible else "",
                used=eligible,
            )
        if section.text:
            section, spent = _admit(section, counter, spent, budget)
        _count(section)
        if section.text:
            sections[key] = section.text
        provenance[key] = {"status": section.status, "used": section.used, "total": section.total}
        if omitted:
            provenance[key]["omitted_incomplete"] = omitted
        if cut:
            provenance[key]["cut_items"] = cut
        if section.reason:
            provenance[key]["reason"] = section.reason
    logger.info(
        "portrait_sources_assembled",
        user_id=str(user_id),
        tokens=spent,
        budget=budget,
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
