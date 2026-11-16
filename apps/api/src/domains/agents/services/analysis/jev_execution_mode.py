"""The shape of a request, judged for the automatic execution mode (ADR-390).

Four Noul questions in one call, on the person's words alone: is a figure worked
out from what the lookups return (``computed``), are results checked against each
other (``cross_check``), is the work open-ended (``open_ended``), is a later lookup
about someone or something only an item's written content names
(``named_in_text``)? Each was qualified on the 2026-11-15 held-out corpus. The
pipeline may plan a turn only when all four are judged ABSENT at their margins
(``jev_gates``); a property present, an answer inside the margin, a missing answer
or any failure is a verdict for the loop.

Owned by the router: started beside the analysis, awaited or cancelled there. A
judgement never raises: a decision point that can only send a turn to the slower,
complete engine must never be what breaks the turn.
"""

from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal
from functools import cache
from time import perf_counter

import structlog

from src.core.context import current_tracker
from src.domains.agents.prompts.prompt_loader import PromptName, load_prompt
from src.domains.agents.services.engine_resolution import EngineReason
from src.domains.llm_config.jev_gates import gate_passes
from src.domains.llm_config.jev_registry import JevUsage
from src.domains.llm_config.jev_statistics_sink import count_jev_outcome
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_many_with_jev
from src.infrastructure.llm.typesafe_client import NoulQuestion
from src.infrastructure.observability.metrics_jev import jev_decision_duration_seconds

__all__ = ["judge_request_shape", "property_absent", "shape_questions", "shape_verdict"]

logger = structlog.get_logger(__name__)

#: (question key, its prompt, the loop reason it gives), in the order a verdict reads them.
_QUESTIONS: tuple[tuple[str, PromptName, EngineReason], ...] = (
    ("computed", "jev_execution_mode_computed_question", EngineReason.COMPUTED),
    ("cross_check", "jev_execution_mode_cross_check_question", EngineReason.CROSS_CHECK),
    ("open_ended", "jev_execution_mode_open_ended_question", EngineReason.OPEN_ENDED),
    ("named_in_text", "jev_execution_mode_named_in_text_question", EngineReason.NAMED_IN_TEXT),
)
#: A Noul is about the property's PRESENCE: below one half, it leans towards absence.
_PRESENCE_LEANING = 0.5


@cache
def shape_questions() -> dict[str, NoulQuestion]:
    """The versioned questions, parsed once per worker, in the order a verdict reads them.

    Public for the qualification bench (`scripts/agents/measure_execution_mode.py`),
    which must ask exactly what a turn asks.
    """
    return {
        key: NoulQuestion.model_validate_json(load_prompt(prompt, version="v1"))
        for key, prompt, _reason in _QUESTIONS
    }


def property_absent(thresholds: Mapping[str, Decimal], key: str, noul: float) -> bool:
    """Whether one property is judged ABSENT: decided at its margin, and leaning no.

    The one reading of a shape answer, shared by the verdict and the qualification
    bench: a score inside the margin is undecided, and undecided is never absent.

    Args:
        thresholds: The margins the operation froze (the defaults when empty).
        key: The property's question key.
        noul: The provider's probability that the property is present.

    Returns:
        True only when the property is judged absent.
    """
    decided = gate_passes(thresholds, JevUsage.EXECUTION_MODE, key, noul)
    return decided and noul < _PRESENCE_LEANING


def shape_verdict(attempt: DecisionAttempt) -> EngineReason:
    """The verdict an attempt gives, at the margins its operation froze.

    Args:
        attempt: The decision provider's attempt.

    Returns:
        ``DIRECT`` when every property is judged absent; the first property present
        or undecided; ``NO_DECISION`` without a usable answer.
    """
    if attempt.outcome != "success":
        return EngineReason.NO_DECISION
    for key, _prompt, reason in _QUESTIONS:
        answer = attempt.nouls.get(key)
        if answer is None:
            return EngineReason.NO_DECISION
        if not property_absent(attempt.thresholds, key, answer.noul):
            return reason
    return EngineReason.DIRECT


async def judge_request_shape(request: str) -> EngineReason:
    """Ask the decision provider for the shape of ``request``.

    The turn's tracker names who pays and which run the call belongs to; without
    one (a script, a probe) nothing is asked.

    Args:
        request: The person's words, as typed.

    Returns:
        The verdict; ``NO_DECISION`` when nothing could be asked or answered.
    """
    tracker = current_tracker.get()
    if tracker is None or not tracker.run_id or not request.strip():
        return EngineReason.NO_DECISION
    started = perf_counter()
    try:
        attempt = await choose_many_with_jev(
            usage=JevUsage.EXECUTION_MODE,
            user_id=tracker.user_id,
            run_id=tracker.run_id,
            state={"request": request},
            questions=shape_questions(),
        )
    except Exception as exc:  # noqa: BLE001 - a judgement never breaks the turn
        logger.info("jev_execution_mode_fallback", error_type=type(exc).__name__)
        return EngineReason.NO_DECISION
    verdict = shape_verdict(attempt)
    outcome = verdict.value if attempt.outcome == "success" else attempt.outcome
    await record_action(
        tracker.user_id,
        attempt.diagnostic,
        action="selected" if verdict is EngineReason.DIRECT else "fallback",
        outcome=outcome,
        target="pipeline" if verdict is EngineReason.DIRECT else "react",
    )
    count_jev_outcome(JevUsage.EXECUTION_MODE, outcome)
    jev_decision_duration_seconds.labels(usage=JevUsage.EXECUTION_MODE, outcome=outcome).observe(
        perf_counter() - started
    )
    return verdict
