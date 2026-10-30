"""The decision row of one dashboard act — filed when the act actually read a source.

Extracted from ``BriefingService._record_cards_turn`` (spec 2026-10-21 D2) so the
progressive routes file their act the same way: only when at least one source was
read (a page load served entirely from cache opened nothing, and a register row
would claim a read that never happened), once per act when several requests share
it (``record_decision_once``). Never raises — the dashboard is already built.
"""

from __future__ import annotations

from uuid import UUID

import structlog

logger = structlog.get_logger(__name__)


async def file_briefing_act(*, user_id: UUID, run_id: str, route: str, once: bool = False) -> None:
    """File the act the consultations of ``run_id`` belong to.

    Args:
        user_id: The account whose sources were read.
        run_id: The act's run id.
        route: The surface that read (``briefing_cards``, ``briefing_text``…).
        once: Several requests share the act: a second filing changes nothing.
    """
    try:
        from src.domains.agents.effects.decision_recorder import (
            record_decision,
            record_decision_once,
        )
        from src.domains.agents.effects.decisions import out_of_turn_decision
        from src.domains.agents.effects.models import DecisionOutcome, EffectSource

        decision = out_of_turn_decision(
            run_id=run_id,
            user_id=user_id,
            thread_id=run_id,
            # A request reached the API; nothing schedules the briefing.
            source=EffectSource.USER.value,
        )
        decision.outcome = DecisionOutcome.ANSWERED
        decision.route = route
        if once:
            await record_decision_once(decision)
        else:
            await record_decision(decision)
    except Exception as exc:  # noqa: BLE001 - observing never breaks the observed
        logger.warning(
            "briefing_cards_decision_not_recorded", run_id=run_id, error_type=type(exc).__name__
        )


__all__ = ["file_briefing_act"]
