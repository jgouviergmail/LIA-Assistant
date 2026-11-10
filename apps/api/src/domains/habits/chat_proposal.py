"""The one habit proposal a chat answer shows (ADR-375).

The chat is the second surface of the proposals, beside the inbox: under an
answer, at most one, decided by code and never by a model — the open proposal
of the turn's own domain (to automate it, or to connect the source it needs)
when the chat has not shown it within ``HABITS_PROPOSAL_CHAT_REPEAT_DAYS``,
else the oldest one it never showed; and never more than one per
``HABITS_PROPOSAL_CHAT_GAP_HOURS``, whatever became of the last one.

The doors are the inbox's — the habits capability (deployment and operator)
and the person's « learn my habits » — plus the card's own instance switch
(``RECURRENCE_SUGGESTION_ENABLED``). They are read BEFORE the claim's session
opens, so its transaction never waits on a switch, and a closed door claims
nothing.

The showing is CLAIMED before the answer carries it (``chat_shown_at``): a
stream that fails after the claim loses one showing, and the proposal stays
in the inbox — the cheap side of the trade, against showing it twice.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from src.domains.habits.capability import habits_capability_enabled
from src.domains.habits.learning_gate import read_learning_gate
from src.domains.habits.models import ProposalKind
from src.domains.habits.need_domains import connector_category_of
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.proposal_schemas import HabitProposalResponse
from src.infrastructure.database.session import get_db_context
from src.infrastructure.observability.metrics_habits import habit_proposals_total

#: The ``transition`` a showing is counted under in ``habit_proposals_total``.
SHOWN_IN_CHAT = "shown_in_chat"


def chat_keys(domain: str | None) -> tuple[tuple[str, str], ...]:
    """The proposal identities a turn on ``domain`` is about.

    Its automation (``automate_need`` is keyed by the domain) and the connector
    it lacks (``connect_source`` is keyed by the domain's connector category).

    Args:
        domain: The turn's actionable domain, when the router resolved one.

    Returns:
        ``(kind, key)`` identities, in that order; empty without a domain.
    """
    if not domain:
        return ()
    keys = [(ProposalKind.AUTOMATE_NEED.value, domain)]
    category = connector_category_of(domain)
    if category is not None:
        keys.append((ProposalKind.CONNECT_SOURCE.value, category))
    return tuple(keys)


async def claim_chat_proposal(
    user_id: UUID, domain: str | None, *, settings: Any, now: datetime
) -> HabitProposalResponse | None:
    """Choose, claim and project the proposal this answer shows, if any.

    Args:
        user_id: The person the answer is for.
        domain: The turn's actionable domain, when the router resolved one.
        settings: The application settings (switch, gap, repeat delay).
        now: The showing instant (UTC).

    Returns:
        The proposal as the card reads it, or None when nothing is shown.
    """
    if not settings.recurrence_suggestion_enabled or not await habits_capability_enabled():
        return None
    if not (await read_learning_gate(user_id)).allowed:
        return None
    async with get_db_context() as db:
        row = await HabitProposalRepository(db).claim_chat_showing(
            user_id,
            preferred=chat_keys(domain),
            now=now,
            gap=timedelta(hours=int(settings.habits_proposal_chat_gap_hours)),
            repeat=timedelta(days=int(settings.habits_proposal_chat_repeat_days)),
        )
        # Projected INSIDE the transaction: a row the card cannot read rolls
        # its claim back rather than spending a showing on nothing.
        shown = HabitProposalResponse.from_row(row) if row is not None else None
    if shown is not None:
        habit_proposals_total.labels(kind=shown.kind.value, transition=SHOWN_IN_CHAT).inc()
    return shown
