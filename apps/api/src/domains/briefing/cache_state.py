"""Pure cache-origin classification for briefing duration metrics."""

from __future__ import annotations

from collections.abc import Iterable

from src.domains.briefing.schemas import CardSection, CardStatus


def classify_cache_state(outcomes: Iterable[tuple[CardSection, bool]]) -> str:
    """Classify the cache-eligible sections by where they came from.

    The provenance is ``from_cache``, set on every cache hit. Age used to stand
    in for it — a section generated less than 1.5 s ago counted as live — so a
    slow live read counted as cached, and production showed no « cold » build in
    seven days while most of them read their sources (spec 2026-10-21 §0ter
    D-H5). A hidden section was neither read nor cached and does not count.

    Args:
        outcomes: Each section with whether its plan may serve it from cache.

    Returns:
        ``cold`` when every counted section was read live, ``warm`` when none
        was (or none counts), ``partial`` otherwise.
    """
    live_count = 0
    eligible_count = 0
    for section, cache_eligible in outcomes:
        if not cache_eligible or section.status is CardStatus.HIDDEN:
            continue
        eligible_count += 1
        if not section.from_cache:
            live_count += 1
    if eligible_count == 0 or live_count == 0:
        return "warm"
    if live_count == eligible_count:
        return "cold"
    return "partial"
