"""Optional absence-of-utility judgment over the existing evaluator's complete input."""

from time import perf_counter
from uuid import UUID

from src.domains.agents.nodes.initiative_schemas import InitiativeDecision
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

# Calibrated for this three-way utility judgment, not borrowed from another task.
MIN_CONFIDENCE = 0.85


async def choose_empty_initiative(
    prompt: str, user_id: str, run_id: str
) -> InitiativeDecision | None:
    try:
        owner = UUID(user_id)
    except ValueError:
        return None
    started = perf_counter()
    attempt = await choose_with_jev(
        usage=JevUsage.INITIATIVE_UTILITY,
        user_id=owner,
        run_id=run_id,
        state={"evaluation_context": prompt},
        question=ChoiceQuestion.model_validate_json(
            load_prompt("jev_initiative_question", version="v1")
        ),
    )
    answer = attempt.answer
    empty = (
        attempt.outcome == "success"
        and answer is not None
        and answer.choice == "no_utility"
        and answer.confidence >= MIN_CONFIDENCE
    )
    outcome = (
        "no_utility"
        if empty
        else ("uncertain" if attempt.outcome == "success" else attempt.outcome)
    )
    await record_action(
        owner,
        attempt.diagnostic,
        action="selected" if empty else "fallback",
        outcome=outcome,
        target="response" if empty else "initiative",
    )
    jev_decisions_total.labels(usage=JevUsage.INITIATIVE_UTILITY, outcome=outcome).inc()
    jev_decision_duration_seconds.labels(
        usage=JevUsage.INITIATIVE_UTILITY, outcome=outcome
    ).observe(perf_counter() - started)
    if not empty:
        return None
    return InitiativeDecision(
        analysis="No additional utility identified.", should_act=False, reasoning="jev_no_utility"
    )
