"""Native template choice; only a confident member of the owned candidate set wins."""

import asyncio
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

from pydantic import BaseModel, Field, ValidationError

from src.domains.llm_config.jev_registry import JevUsage
from src.domains.meetings.native_spend import record_selection_charge
from src.domains.meetings.prompts import MeetingPromptError, load_meeting_prompt
from src.domains.meetings.template_service import ResolvedTemplate
from src.infrastructure.llm.decision_types import DecisionCharge
from src.infrastructure.llm.jev_debug_models import JevAction
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

MIN_CONFIDENCE = 0.95


class _ChoicePrompt(BaseModel):
    instructions: str = Field(min_length=1, description="Versioned selection instructions.")
    no_match: str = Field(min_length=1, description="The abstention criterion.")


@dataclass(frozen=True)
class NativeTemplateSelection:
    """The optional selected template and independently accounted spend."""

    template: ResolvedTemplate | None = None
    charge: DecisionCharge | None = None


async def select_template_with_jev(
    *,
    meeting_id: UUID,
    user_id: UUID,
    run_id: str,
    candidates: list[ResolvedTemplate],
    excerpt: str,
    calendar_title: str | None,
) -> NativeTemplateSelection:
    """Return no template on uncertainty; the caller runs its existing selector."""
    if not candidates or len(candidates) > 254:
        return NativeTemplateSelection()
    try:
        prompt = _ChoicePrompt.model_validate_json(
            load_meeting_prompt("meeting_jev_selection_prompt")
        )
    except MeetingPromptError, ValidationError:
        jev_decisions_total.labels(
            usage=JevUsage.MEETING_TEMPLATE, outcome="prompt_unavailable"
        ).inc()
        return NativeTemplateSelection()
    by_key = {f"c{index}": candidate for index, candidate in enumerate(candidates)}
    question = ChoiceQuestion(
        instructions=prompt.instructions,
        criteria={
            **{
                key: f"{item.category.value}: {item.name}. {item.description or ''}"
                for key, item in by_key.items()
            },
            "none": prompt.no_match,
        },
    )
    started = perf_counter()
    attempt = await choose_with_jev(
        usage=JevUsage.MEETING_TEMPLATE,
        user_id=user_id,
        run_id=run_id,
        state={"calendar_title": calendar_title, "transcript_excerpt": excerpt},
        question=question,
    )
    action: JevAction = "aborted"
    outcome, target = "selection_error", None
    try:
        if attempt.charge is not None:
            await record_selection_charge(meeting_id, user_id, run_id, attempt.charge)
        outcome, chosen = attempt.outcome, None
        if attempt.answer is not None:
            chosen = by_key.get(attempt.answer.choice)
            if chosen is None:
                outcome = "no_match"
            elif attempt.answer.confidence < MIN_CONFIDENCE:
                chosen, outcome = None, "low_confidence"
        jev_decisions_total.labels(usage=JevUsage.MEETING_TEMPLATE, outcome=outcome).inc()
        jev_decision_duration_seconds.labels(
            usage=JevUsage.MEETING_TEMPLATE, outcome=outcome
        ).observe(perf_counter() - started)
        action = "selected" if chosen else "fallback"
        target = f"{chosen.ref}: {chosen.name}" if chosen else "meeting_synthesis"
        return NativeTemplateSelection(chosen, attempt.charge)
    except asyncio.CancelledError:
        action, outcome = "cancelled", "cancelled"
        raise
    finally:
        await record_action(
            user_id, attempt.diagnostic, action=action, outcome=outcome, target=target
        )
