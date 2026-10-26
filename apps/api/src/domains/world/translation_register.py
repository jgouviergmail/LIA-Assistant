"""Content-free native decision row for an explicitly requested paid translation."""

from datetime import datetime
from uuid import UUID

from src.domains.agents.effects.decision_recorder import record_decision_once
from src.domains.agents.effects.decisions import out_of_turn_decision
from src.domains.agents.effects.models import DecisionOutcome, EffectSource


async def file_translation(
    *, user_id: UUID, run_id: str, started_at: datetime, outcome: DecisionOutcome
) -> None:
    """Record content-free translation evidence through the payer's native effect register."""
    decision = out_of_turn_decision(
        run_id=run_id, user_id=user_id, thread_id=run_id, source=EffectSource.USER.value
    )
    decision.route = "world_translation"
    decision.started_at = started_at
    decision.outcome = outcome
    await record_decision_once(decision)
