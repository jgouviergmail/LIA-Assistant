"""Debug coverage separates evaluated uncertainty from untouched collection candidates."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.infrastructure.llm.jev_debug_models import (
    JevCallTrace,
    JevCollectionCoverage,
    context_preview,
)
from src.infrastructure.llm.jev_debug_store import record_action

pytestmark = pytest.mark.unit


def _trace() -> JevCallTrace:
    return JevCallTrace(
        id=uuid4(),
        run_id="synthetic-collection-run",
        caller="filter_events",
        usage="filter_event",
        started_at=datetime.now(UTC),
        requested_model="jev-1.13.0",
        context=context_preview("synthetic"),
        cost_eur=0.0001,
        input_tokens=700,
        output_tokens=30,
    )


def _coverage() -> JevCollectionCoverage:
    return JevCollectionCoverage(
        candidate_count=120,
        evaluated_count=75,
        unevaluated_count=45,
        omitted_count=20,
        unknown_count=14,
        batch_index=2,
        batch_count=4,
    )


@pytest.mark.parametrize(
    "update",
    [
        {"candidate_count": -1},
        {"evaluated_count": 74},
        {"unknown_count": 76},
        {"omitted_count": 46},
        {"batch_index": 0},
        {"batch_index": 5},
        {"batch_count": None},
        {"batch_index": None},
        {"source_body": "unexpected arbitrary content"},
    ],
)
def test_coverage_rejects_impossible_counts_or_unbounded_extra_data(update: dict) -> None:
    with pytest.raises(ValidationError):
        JevCollectionCoverage.model_validate({**_coverage().model_dump(), **update})


def test_historical_trace_has_no_inferred_coverage_and_round_trip_keeps_global_counts() -> None:
    trace = _trace()
    historical = trace.model_dump(exclude={"collection_coverage"})
    assert JevCallTrace.model_validate(historical).collection_coverage is None
    completed = trace.model_copy(update={"collection_coverage": _coverage()})
    restored = JevCallTrace.model_validate_json(completed.model_dump_json())
    assert restored.collection_coverage == _coverage()
    assert (
        restored.collection_coverage.unknown_count != restored.collection_coverage.unevaluated_count
    )


async def test_collection_annotation_keeps_attempt_cost_and_preserves_coverage_on_later_action() -> (
    None
):
    owner = uuid4()
    trace = _trace()
    with patch("src.infrastructure.llm.jev_debug_store.save_trace", AsyncMock()) as save:
        await record_action(
            owner,
            trace,
            action="preview",
            outcome="uncertain",
            target="result_preview",
            applied_decisions={"q7": "unknown"},
            collection_coverage=_coverage(),
        )
        annotated = save.call_args.args[1]
        assert save.call_args.args[0] == owner
        restored = JevCallTrace.model_validate_json(annotated.model_dump_json())
        assert restored.collection_coverage == _coverage()
        assert restored.applied_decisions == {"q7": "unknown"}
        assert restored.cost_eur == trace.cost_eur
        assert restored.input_tokens == 700
        assert restored.output_tokens == 30
        await record_action(owner, restored, action="preview", outcome="uncertain")
        assert save.call_args.args[1].collection_coverage == _coverage()
