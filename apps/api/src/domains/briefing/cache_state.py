"""Pure cache-origin classification for briefing duration metrics."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.domains.briefing.schemas import CardSection


def classify_cache_state(outcomes: Iterable[tuple[CardSection, bool]], *, now: datetime) -> str:
    """Classify only cache-eligible sections, preserving the caller's clock."""
    live_count = 0
    eligible_count = 0
    for section, cache_eligible in outcomes:
        if not cache_eligible:
            continue
        eligible_count += 1
        if (now - section.generated_at).total_seconds() < 1.5:
            live_count += 1
    if eligible_count == 0 or live_count == 0:
        return "warm"
    if live_count == eligible_count:
        return "cold"
    return "partial"
