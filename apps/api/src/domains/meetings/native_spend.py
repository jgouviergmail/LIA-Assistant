"""A meeting keeps native spend even if its subsequent synthesis fails or is retried."""

from uuid import UUID

import structlog
from pydantic import Field
from sqlalchemy import func, literal, select, update
from sqlalchemy.dialects.postgresql import JSONB

from src.core.constants import MEETINGS_PROACTIVE_TASK_TYPE
from src.domains.agents.effects.decision_recorder import record_decision_once
from src.domains.agents.effects.decisions import out_of_turn_decision
from src.domains.agents.effects.models import DecisionOutcome
from src.domains.chat.models import TokenUsageLog
from src.domains.meetings.models import Meeting
from src.infrastructure.database import get_db_context
from src.infrastructure.llm.decision_types import DecisionCharge

logger = structlog.get_logger(__name__)


async def finalize_native_meeting_run(user_id: UUID, run_id: str, outcome: DecisionOutcome) -> None:
    """Close a native-paid run even if synthesis failed before its normal filing.

    The ledger is the proof of spend, including an invalid paid answer. The
    idempotent door preserves the normal completion's existing decision row.
    Observation cannot turn completed minutes into a failed processing job.
    """
    try:
        async with get_db_context() as db:
            paid = await db.scalar(
                select(TokenUsageLog.id)
                .where(
                    TokenUsageLog.run_id == run_id,
                    TokenUsageLog.user_id == user_id,
                    TokenUsageLog.provider == "typesafe",
                )
                .limit(1)
            )
        if not paid:
            return
        decision = out_of_turn_decision(
            user_id=user_id, run_id=run_id, thread_id=run_id, source="user"
        )
        decision.route = MEETINGS_PROACTIVE_TASK_TYPE
        decision.outcome = outcome
        await record_decision_once(decision)
    except Exception as exc:
        logger.warning("meeting_native_register_unavailable", error_type=type(exc).__name__)


class MeetingDecisionCharge(DecisionCharge):
    """One uniquely identified native attempt; the platform ledger remains authoritative."""

    run_id: str = Field(description="Accounting id of the processing attempt.")


def selection_charges(meeting: Meeting) -> list[MeetingDecisionCharge]:
    """Reconstruct the durable native usage without repricing historical counters."""
    return [
        MeetingDecisionCharge.model_validate(item)
        for item in meeting.template_selection_usage or []
    ]


async def record_selection_charge(
    meeting_id: UUID, user_id: UUID, run_id: str, charge: DecisionCharge
) -> None:
    """Append once per run atomically, independently of the processing lease or outcome."""
    value = MeetingDecisionCharge(**charge.model_dump(), run_id=run_id).model_dump(mode="json")
    async with get_db_context() as db:
        existing = func.coalesce(Meeting.template_selection_usage, literal([], type_=JSONB))
        await db.execute(
            update(Meeting)
            .where(
                Meeting.id == meeting_id,
                Meeting.user_id == user_id,
                ~existing.bool_op("@>")(literal([{"run_id": run_id}], type_=JSONB)),
            )
            .values(template_selection_usage=existing.op("||")(literal([value], type_=JSONB)))
        )
        await db.commit()
