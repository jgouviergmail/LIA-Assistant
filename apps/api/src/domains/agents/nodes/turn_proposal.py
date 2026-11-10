"""The habit proposal shown under this answer (ADR-375).

Both execution modes converge on the response node, so the card is decided
there, once per answer, by code and never by a model: ``habits`` chooses and
claims the proposal (``habits.chat_proposal``), this module says whether the
turn may carry a card at all and hands the proposal to the stream on the
follow-up chips' channel (``push_turn_proposal``): popped once, archived with
the answer, carried in its ``done`` chunk.

No card under a run nobody typed (a routine), nor where it would never be
drawn: rows that stay out of the chat (a ticket run) or a surface that renders
no markup (``chat_cards_reach_the_person``). Never raises: a card is a
courtesy, and an answer never pays for one that could not be had.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import structlog

from src.core.config import settings
from src.domains.agents.analysis.query_intelligence_helpers import resolve_actionable_domain
from src.domains.agents.api.run_origin import chat_cards_reach_the_person
from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.services.streaming.followup_metadata import push_turn_proposal
from src.domains.habits.chat_proposal import claim_chat_proposal

logger = structlog.get_logger(__name__)


async def resolve_turn_proposal(state: dict[str, Any], run_id: str) -> None:
    """Hand the stream the one habit proposal this answer shows, if any.

    Args:
        state: The graph state (the router's record of the turn's domain).
        run_id: The run, keying the handoff the stream pops.
    """
    try:
        context = runtime_context_if_running()
        if context is None or context.is_automated_source or not chat_cards_reach_the_person():
            return
        proposal = await claim_chat_proposal(
            context.user_id,
            resolve_actionable_domain(state),
            settings=settings,
            now=datetime.now(UTC),
        )
    except Exception as exc:  # noqa: BLE001 — a card never costs the answer
        logger.warning("turn_proposal_unavailable", run_id=run_id, error_type=type(exc).__name__)
        return
    if proposal is not None:
        push_turn_proposal(run_id, proposal.model_dump(mode="json"))
        logger.info("turn_proposal_shown", run_id=run_id, kind=proposal.kind.value)
