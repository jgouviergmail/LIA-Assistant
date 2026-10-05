"""An absence-only decision before the generative personal-reference extractor."""

from time import perf_counter

import structlog

from src.core.constants import JEV_MEMORY_REFERENCE_MIN_CONFIDENCE
from src.core.context import current_tracker
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.jev_debug_store import record_action
from src.infrastructure.llm.jev_runtime import choose_with_jev
from src.infrastructure.llm.typesafe_client import ChoiceQuestion
from src.infrastructure.observability.metrics_jev import (
    jev_decision_duration_seconds,
    jev_decisions_total,
)

logger = structlog.get_logger(__name__)


def _presence_outcome(attempt: DecisionAttempt) -> str:
    """A confident request to preserve extraction is distinct from uncertainty."""
    if attempt.outcome != "success":
        return attempt.outcome
    answer = attempt.answer
    if answer is None or answer.confidence < JEV_MEMORY_REFERENCE_MIN_CONFIDENCE:
        return "uncertain"
    return {"absent": "no_references", "preserve": "references_preserved"}.get(
        answer.choice, "uncertain"
    )


async def choose_no_memory_references(query: str) -> bool:
    """Skip only extraction, preserving broad retrieval and every other query step.

    A trusted, active account tracker supplies the identity and billing owner.
    Without that context the existing extractor runs, including legacy callers.
    No names, references, permissions or execution are produced by this gate.
    """
    tracker = current_tracker.get()
    if tracker is None or not tracker.run_id:
        return False
    started = perf_counter()
    try:
        attempt = await choose_with_jev(
            usage=JevUsage.MEMORY_REFERENCE_PRESENCE,
            user_id=tracker.user_id,
            run_id=tracker.run_id,
            state={"query": query, "account_owner_identity_known": True},
            question=ChoiceQuestion.model_validate_json(
                load_prompt("jev_memory_reference_presence_question", version="v1")
            ),
        )
    except Exception as exc:
        logger.info("jev_memory_presence_fallback", error_type=type(exc).__name__)
        return False
    outcome = _presence_outcome(attempt)
    absent = outcome == "no_references"
    await record_action(
        tracker.user_id,
        attempt.diagnostic,
        action="selected" if absent else "fallback",
        outcome=outcome,
        target="memory_reference_extraction_skipped" if absent else "memory_reference_extraction",
    )
    jev_decisions_total.labels(usage=JevUsage.MEMORY_REFERENCE_PRESENCE, outcome=outcome).inc()
    jev_decision_duration_seconds.labels(
        usage=JevUsage.MEMORY_REFERENCE_PRESENCE, outcome=outcome
    ).observe(perf_counter() - started)
    return absent
