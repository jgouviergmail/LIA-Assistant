"""How a planner catalogue seats its tools under its cap: by relevance first.

ADR-293 amendment 2026-11-15. Both catalogue strategies group the detected
domains' tools by domain, give every domain one seat, then fill the remaining
seats domain by domain until the cap. Each domain's list was in REGISTRATION
order, so a domain's seat went to whichever of its tools was registered first
and the cap cut by position. Measured during the ADR-390 qualification (E06,
« what day must I return the books, and what weather that day? »): five
domains for a ten-seat cap, the reminder domain seated by its write tool while
its reader, four times as relevant by the router's own scores, fell under the
cap behind four weather tools, and the planner, offered no reader of
reminders, read the tasks.

The router has already paid for the scores (ADR-293: one embedding, two
readers). Within a domain the tools are taken by descending score; a tie, or a
turn the selector did not score, keeps registration order (the sort is
stable), so such a turn is seated exactly as before. The domains keep the
analyzer's order: which domain is seated, and filled, first is unchanged.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, NamedTuple

#: One candidate of a domain: its catalogue entry and its tool category.
_Candidate = tuple[dict[str, Any], str]


class CatalogueSeats(NamedTuple):
    """The tools a catalogue seated, with the domains and categories they cover."""

    tools: list[dict[str, Any]]
    domains_included: set[str]
    categories_included: set[str]


def _by_relevance(
    candidates: Sequence[_Candidate], scores: Mapping[str, float]
) -> list[_Candidate]:
    """A domain's candidates, most relevant first; equal scores keep their order."""
    return sorted(candidates, key=lambda candidate: -scores.get(candidate[0]["name"], 0.0))


def seat_tools(
    tools_by_domain: Mapping[str, Sequence[_Candidate]],
    scores: Mapping[str, float],
    max_tools: int,
) -> CatalogueSeats:
    """Seat every domain's most relevant tool, then fill each domain by relevance.

    Args:
        tools_by_domain: Each domain's candidates in registration order, the
            domains in the analyzer's order.
        scores: The router's calibrated score per tool name; a tool it did not
            score counts as 0.
        max_tools: The catalogue cap.

    Returns:
        The seated tools in catalogue order, the domains that got a seat and
        the categories of every seated tool.
    """
    ranked = {domain: _by_relevance(tools, scores) for domain, tools in tools_by_domain.items()}
    seats = CatalogueSeats(tools=[], domains_included=set(), categories_included=set())
    for domain, tools in ranked.items():
        if tools and len(seats.tools) < max_tools:
            tool, category = tools[0]
            seats.tools.append(tool)
            seats.domains_included.add(domain)
            seats.categories_included.add(category)
    for tools in ranked.values():
        for tool, category in tools[1:]:
            if len(seats.tools) >= max_tools:
                break
            seats.tools.append(tool)
            seats.categories_included.add(category)
    return seats


__all__ = ["CatalogueSeats", "seat_tools"]
