"""Optional absence-of-utility judgment over the existing evaluator's complete input."""

import json
from time import perf_counter
from uuid import UUID

import structlog
from pydantic import JsonValue

from src.domains.agents.nodes.initiative_schemas import InitiativeDecision
from src.domains.agents.nodes.jev_initiative_evidence import closed_omissions, evidence_omissions
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_settings import load_jev_snapshot
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import begin_trace, finish_trace, record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

# Calibrated for this three-way utility judgment, not borrowed from another task.
MIN_CONFIDENCE = 0.85
logger = structlog.get_logger(__name__)


async def _incomplete_attempt(
    owner: UUID,
    run_id: str,
    state: JsonValue,
    question: ChoiceQuestion,
    omissions: dict[str, int],
) -> DecisionAttempt:
    """Preserve opted-in diagnostics without buying a judgment code cannot accept."""
    snapshot = await load_jev_snapshot(JevUsage.INITIATIVE_UTILITY)
    if not snapshot.requested:
        return DecisionAttempt(
            outcome="disabled" if snapshot.readiness == "ready" else snapshot.readiness
        )
    config = snapshot.configuration
    if config is None:
        return DecisionAttempt(outcome=snapshot.readiness)
    started = perf_counter()
    trace = await begin_trace(
        user_id=owner,
        usage=JevUsage.INITIATIVE_UTILITY,
        run_id=run_id,
        model=config.model,
        state=state,
        question=question,
    )
    trace = await finish_trace(
        owner,
        trace,
        answer=None,
        question=question,
        reported_model=None,
        duration_ms=(perf_counter() - started) * 1000,
        outcome="incomplete_evidence",
        action="fallback",
        status_code=None,
        counters=None,
        cost_eur=None,
    )
    logger.info(
        "jev_initiative_preflight",
        run_id=run_id,
        usage=JevUsage.INITIATIVE_UTILITY.value,
        outcome="incomplete_evidence",
        omissions=closed_omissions(omissions),
        state_bytes=len(json.dumps(state, ensure_ascii=False).encode("utf-8")),
    )
    return DecisionAttempt(outcome="incomplete_evidence", diagnostic=trace)


async def choose_empty_initiative(
    prompt: str,
    user_id: str,
    run_id: str,
    *,
    state: JsonValue | None = None,
    omissions: dict[str, int] | None = None,
) -> InitiativeDecision | None:
    try:
        owner = UUID(user_id)
    except ValueError:
        return None
    started = perf_counter()
    native_state = state if state is not None else {"evaluation_context": prompt}
    question = ChoiceQuestion.model_validate_json(
        load_prompt("jev_initiative_question", version="v1")
    )
    omissions = evidence_omissions(native_state, omissions)
    if omissions:
        attempt = await _incomplete_attempt(owner, run_id, native_state, question, omissions)
    else:
        attempt = await choose_with_jev(
            usage=JevUsage.INITIATIVE_UTILITY,
            user_id=owner,
            run_id=run_id,
            state=native_state,
            question=question,
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
        target=(
            "initiative_evaluation"
            if attempt.outcome == "incomplete_evidence"
            else ("response" if empty else "initiative")
        ),
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
