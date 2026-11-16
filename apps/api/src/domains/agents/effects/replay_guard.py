"""Whether replaying a run could perform one of its acts a second time (ADR-263).

ONE door for every caller that replays a turn under the same run: the out-of-turn
retry (``infrastructure/scheduler/out_of_turn_run``) and the replay of a turn the
model's window refused (``agents/services/orchestration/overflow_replay``, lot 15).
The register answers: any action row of the run but a refusal says it may have
acted. A register that cannot be read answers yes, because doubt never replays:
an action that may have happened must not happen twice.
"""

from __future__ import annotations

import structlog

__all__ = ["run_may_have_acted"]

logger = structlog.get_logger(__name__)


async def run_may_have_acted(run_id: str | None) -> bool:
    """Whether an attempt of this run may have acted on the world.

    Args:
        run_id: The run, or None when the graph minted its own per attempt.

    Returns:
        True when a replay could repeat an action. A caller that names no run
        can read nothing, and keeps the replay it always had (False).
    """
    if not run_id:
        return False
    from src.domains.agents.effects.repository import EffectLedgerRepository
    from src.infrastructure.database.session import get_db_context

    try:
        async with get_db_context() as db:
            return await EffectLedgerRepository(db).acted_in_run(run_id)
    except Exception as read_error:  # noqa: BLE001 — doubt never replays
        logger.warning(
            "replay_register_unreadable",
            run_id=run_id,
            error_type=type(read_error).__name__,
        )
        return True
