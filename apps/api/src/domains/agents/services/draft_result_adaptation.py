"""Returned draft dispositions and batch counts, without executing or mutating context."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from prometheus_client import Counter

from src.core.application_interaction import pending_interaction_of
from src.core.tool_outcome import error_code_of, explicit_success
from src.domains.agents.services.draft_execution_result import DraftExecutionResult


def incomplete_draft_result(
    draft_id: str, draft_type: str, result: dict[str, object], language: str, counter: Counter
) -> DraftExecutionResult | None:
    if pending_interaction_of(result) is not None:
        counter.labels(draft_type=draft_type, outcome="waiting").inc()
        return DraftExecutionResult(
            False,
            draft_id,
            draft_type,
            "confirm",
            result_data=result,
            user_language=language,
        )
    if explicit_success(result):
        return None
    counter.labels(draft_type=draft_type, outcome="failed").inc()
    return DraftExecutionResult(
        False,
        draft_id,
        draft_type,
        "confirm",
        result_data=result,
        error=error_code_of(result) or "EXECUTION_FAILED",
        user_language=language,
    )


@dataclass(frozen=True)
class DraftBatchCounts:
    succeeded: int
    failed: int
    waiting: int
    cancelled: int


def count_draft_results(results: Sequence[Mapping[str, object]]) -> DraftBatchCounts:
    counts = {"success": 0, "error": 0, "waiting": 0, "cancelled": 0}
    for item in results:
        status = item.get("status")
        key = status if isinstance(status, str) and status in counts else "error"
        counts[key] += 1
    return DraftBatchCounts(
        counts["success"], counts["error"], counts["waiting"], counts["cancelled"]
    )
