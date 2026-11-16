"""Restore a resumed turn's original choice from its existing register row (ADR-390)."""

from __future__ import annotations

import structlog

from src.core.execution_mode import is_execution_mode_choice
from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import current_turn
from src.infrastructure.database.session import get_db_context

logger = structlog.get_logger(__name__)


async def restore_resumed_choice() -> None:
    """Restore what this turn originally requested, after its checkpoint authorizes resume.

    A person's current preference belongs to their next turn. The decision
    register already preserves the first segment's choice and reason; the
    resumed segment reads them on a short session before any graph work.
    Missing or unreadable evidence leaves both unknown, never inferred from
    today's preference. The engine remains the checkpoint's authority.
    """
    decision = current_turn()
    if decision is None:
        return
    decision.requested_mode = None
    decision.resolution_reason = None
    try:
        async with get_db_context() as db:
            original = await DecisionRepository(db).get_for_run(decision.run_id)
            if original is None:
                return
            if (
                original.run_id != decision.run_id
                or original.user_id != decision.user_id
                or original.thread_id != decision.thread_id
                or not is_execution_mode_choice(original.requested_mode)
            ):
                logger.warning("resumed_decision_inconsistent", run_id=decision.run_id)
                return
            choice = original.requested_mode, original.resolution_reason
    except Exception:
        logger.exception("resumed_decision_read_failed", run_id=decision.run_id)
        return
    decision.requested_mode, decision.resolution_reason = choice
