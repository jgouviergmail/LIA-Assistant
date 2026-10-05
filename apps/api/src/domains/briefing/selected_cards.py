"""Read a calling surface's selected section plans without building a dashboard.

The caller retains the policy, fetchers, cache identity and consultation observer.
This module only gathers those plans and fills unselected sections with HIDDEN.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from typing import Any, NamedTuple, Protocol

from src.domains.briefing.constants import SECTION_NAMES
from src.domains.briefing.consultations import SectionReadObserver
from src.domains.briefing.schemas import CardsBundle, CardSection, CardStatus


class SectionPlan(NamedTuple):
    """A section's fetcher, cache bound and whether it can be served from cache."""

    name: str
    fetcher: Callable[[], Awaitable[Any]]
    ttl: int
    force: bool
    cache_eligible: bool = True


class SectionReader(Protocol):
    def __call__(
        self,
        name: str,
        fetcher: Callable[[], Awaitable[Any]],
        *,
        ttl: int,
        force: bool,
        respect_hidden: bool,
        record: bool,
        on_read: SectionReadObserver | None,
    ) -> Awaitable[CardSection]: ...


async def selected_cards_bundle(
    plans: Sequence[SectionPlan],
    read: SectionReader,
    on_read: SectionReadObserver | None,
) -> CardsBundle:
    """Read exactly these plans with the calling surface's consultation observer."""
    results = await asyncio.gather(
        *(
            read(
                plan.name,
                plan.fetcher,
                ttl=plan.ttl,
                force=False,
                respect_hidden=False,
                record=False,
                on_read=on_read,
            )
            for plan in plans
        )
    )
    hidden = CardSection(status=CardStatus.HIDDEN, generated_at=datetime.now(UTC))
    selected = dict(zip((plan.name for plan in plans), results, strict=True))
    return CardsBundle(**{name: selected.get(name, hidden) for name in SECTION_NAMES})


__all__ = ["SectionPlan", "selected_cards_bundle"]
