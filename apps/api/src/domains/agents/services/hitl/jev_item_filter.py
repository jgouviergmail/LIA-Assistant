"""An atomic exclusion proposal; the existing HITL node still requires approval."""

import json
from typing import Any
from uuid import UUID

from src.domains.agents.context.runtime_context import runtime_context_if_running
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.llm.typesafe_client import MAX_QUESTIONS, ChoiceQuestion
from src.infrastructure.observability.metrics_jev import jev_decisions_total

MIN_CONFIDENCE = 0.99
REFERENCE_SCOPE_MIN_CONFIDENCE = 0.80
REFERENCE_SCOPE_KEY = "reference_scope"


def exclusion_questions(count: int) -> dict[str, ChoiceQuestion]:
    template = ChoiceQuestion.model_validate_json(
        load_prompt("jev_hitl_exclusion_question", version="v1")
    )
    return {
        **{
            f"item_{i}": template.model_copy(
                update={"instructions": template.instructions.format(item_key=f"item_{i}")}
            )
            for i in range(count)
        },
        REFERENCE_SCOPE_KEY: ChoiceQuestion.model_validate_json(
            load_prompt("jev_hitl_reference_scope_question", version="v1")
        ),
    }


def _kept_indices(attempt: DecisionAttempt, count: int) -> list[int] | None:
    expected = {f"item_{i}" for i in range(count)} | {REFERENCE_SCOPE_KEY}
    if attempt.outcome != "success" or set(attempt.answers) != expected:
        return None
    scope = attempt.answers[REFERENCE_SCOPE_KEY]
    if scope.choice != "clear" or scope.confidence < REFERENCE_SCOPE_MIN_CONFIDENCE:
        return None
    if any(
        attempt.answers[f"item_{i}"].confidence < MIN_CONFIDENCE
        or attempt.answers[f"item_{i}"].choice not in {"keep", "exclude"}
        for i in range(count)
    ):
        return None
    return [i for i in range(count) if attempt.answers[f"item_{i}"].choice == "keep"]


async def try_filter_items(
    item_previews: list[dict[str, Any]],
    exclude_criteria: str,
    run_id: str | None,
) -> list[int] | None:
    context = runtime_context_if_running()
    if context is None or not run_id or not 0 < len(item_previews) < MAX_QUESTIONS:
        return None
    # Snapshot the exact proposed list. Unsupported values, overflow or any
    # later mutation must not turn into a partial positional filter.
    try:
        snapshot = json.loads(json.dumps(item_previews, ensure_ascii=False, allow_nan=False))
    except ValueError, TypeError, RecursionError:
        return None
    questions = exclusion_questions(len(snapshot))
    attempt = await choose_many_with_jev(
        usage=JevUsage.HITL_EXCLUSION,
        user_id=context.user_id,
        run_id=run_id,
        state={
            "exclude_criteria": exclude_criteria,
            "items": {f"item_{i}": item for i, item in enumerate(snapshot)},
        },
        questions=questions,
    )
    keep = _kept_indices(attempt, len(snapshot)) if item_previews == snapshot else None
    await _record_result(context.user_id, attempt, snapshot, keep)
    return keep


async def _record_result(
    user_id: UUID,
    attempt: DecisionAttempt,
    snapshot: list[dict[str, Any]],
    keep: list[int] | None,
) -> None:
    outcome = (
        "selected"
        if keep is not None
        else ("uncertain" if attempt.outcome == "success" else attempt.outcome)
    )
    await record_action(
        user_id,
        attempt.diagnostic,
        action="selected" if keep is not None else "fallback",
        outcome=outcome,
        target=(
            "item_filter"
            if keep is None
            else ("human_reconfirmation" if keep else "cancel_empty_selection")
        ),
        decision_labels={
            **{
                f"item_{i}": str(item.get("subject") or item.get("title") or item.get("name") or i)
                for i, item in enumerate(snapshot)
            },
            REFERENCE_SCOPE_KEY: "Exclusion reference scope",
        },
    )
    jev_decisions_total.labels(usage=JevUsage.HITL_EXCLUSION, outcome=outcome).inc()
