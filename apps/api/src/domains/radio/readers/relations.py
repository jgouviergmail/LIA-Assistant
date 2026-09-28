"""People the listener starred and has not heard from for a while, for the personal corner.

The personal CRM's own overview decides who and when (ADR-185: every figure an
aggregate over open commitments, calls and relayed messages): a person the
listener STARRED whose last exchange is older than the CRM page's own dormancy
line — a prompt to get back in touch, never a verdict. Only starred people: the
overview is a capped page ranked by recency, so an unstarred quiet person is
exactly the one the cap would cut, and the radio never says « nobody » where it
simply did not look.

The overview opens its own short sessions (ADR-304).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final
from uuid import UUID

from src.domains.radio.facts import FactKind, Sensitivity
from src.domains.radio.personal import MAX_PER_SOURCE, PersonalDraft, PersonalSource, digest
from src.domains.relations.schemas import RelationSummary
from src.domains.relations.service import RelationsService

#: Past this silence a relationship is worth noticing again — the CRM page's own
#: dormancy line (``DORMANT_AFTER_DAYS`` in ``RelationCardList.tsx``).
QUIET_AFTER_DAYS: Final[int] = 90


@dataclass(frozen=True, slots=True)
class QuietRelation:
    """A starred person gone quiet.

    Attributes:
        name: How the listener's records name them.
        last_at: Their last exchange (aware).
    """

    name: str
    last_at: datetime


def quiet_relations(summaries: Sequence[RelationSummary], *, now: datetime) -> list[QuietRelation]:
    """The starred people whose last exchange is past the dormancy line, the longest silence first."""
    quiet = [
        QuietRelation(name=summary.display_name, last_at=summary.last_interaction_at)
        for summary in summaries
        if summary.is_favorite
        and summary.last_interaction_at is not None
        and (now - summary.last_interaction_at).days > QUIET_AFTER_DAYS
    ]
    return sorted(quiet, key=lambda relation: relation.last_at)


def relation_drafts(quiet: Sequence[QuietRelation], *, now: datetime) -> list[PersonalDraft]:
    """The quiet people as drafts.

    The ledger key moves every thirty days of silence: a person heard about
    today may come back a month later, not tomorrow.
    """
    drafts: list[PersonalDraft] = []
    for relation in quiet:
        days = (now - relation.last_at).days
        drafts.append(
            PersonalDraft(
                FactKind.RELATION,
                f"No exchange with {relation.name}, someone the listener starred, "
                f"for {days} days",
                f"relation:{digest(relation.name.casefold())}:{days // 30}",
                Sensitivity.PERSONAL,
            )
        )
    return drafts


async def read_relations(user_id: UUID, *, now: datetime) -> list[PersonalDraft]:
    """The starred people gone quiet, read from the CRM's overview.

    Args:
        user_id: The listener.
        now: The current instant (aware).

    Returns:
        The drafts, bounded like every personal source.
    """
    overview = await RelationsService(user_id).build_overview()
    quiet = quiet_relations(overview.relations, now=now)
    return relation_drafts(quiet[: MAX_PER_SOURCE[PersonalSource.RELATIONS]], now=now)


__all__ = [
    "QUIET_AFTER_DAYS",
    "QuietRelation",
    "quiet_relations",
    "read_relations",
    "relation_drafts",
]
