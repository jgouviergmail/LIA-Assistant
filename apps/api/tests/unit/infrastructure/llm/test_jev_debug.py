"""Native diagnostics are bounded, interpretable and independent of the paid path."""

import importlib
from datetime import UTC, datetime
from fnmatch import fnmatch
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from pydantic import ValidationError

from src.infrastructure.llm.typesafe_client import ChoiceAnswer, ChoiceQuestion

pytestmark = pytest.mark.unit


def test_diagnostics_participate_in_account_and_conversation_purge() -> None:
    from src.infrastructure.cache.key_families import (
        is_reset_purgeable,
        is_user_scoped,
        scan_patterns_for,
    )
    from src.infrastructure.llm.jev_debug_store import trace_keys

    owner = uuid4()
    for key in trace_keys(owner):
        assert is_user_scoped(key)
        assert is_reset_purgeable(key)
        assert any(fnmatch(key, pattern) for pattern in scan_patterns_for(str(owner)))


def test_context_is_bounded_and_reports_omitted_characters() -> None:
    module = importlib.import_module("src.infrastructure.llm.jev_debug_models")
    preview = module.context_preview({"transcript": "界" * 20_000})
    assert len(preview.text) <= 6000
    assert preview.original_characters > 20_000
    assert preview.omitted_characters == preview.original_characters - len(preview.text)
    assert "界" in preview.text


def test_response_explains_opaque_candidates_and_states_the_cut() -> None:
    module = importlib.import_module("src.infrastructure.llm.jev_debug_models")
    question = ChoiceQuestion(
        instructions="Select.", criteria={f"c{i}": f"Format {i}" for i in range(20)}
    )
    answer = ChoiceAnswer(
        type="choice",
        choice="c19",
        confidence=0.99,
        probabilities={**{f"c{i}": 0.01 for i in range(19)}, "c19": 0.81},
    )
    response = module.choice_preview(answer, question)
    assert response.choice_label == "Format 19"
    assert response.probabilities[0].key == "c19"
    assert response.probabilities[0].probability == 0.81
    assert len(response.probabilities) == 10
    assert response.omitted_candidates == 10


def test_historical_trace_remains_readable_and_failure_reason_is_a_closed_code() -> None:
    module = importlib.import_module("src.infrastructure.llm.jev_debug_models")
    historical = {
        "id": str(uuid4()),
        "run_id": "synthetic-run",
        "caller": "memory_extraction",
        "usage": "observe_memory",
        "started_at": datetime.now(UTC).isoformat(),
        "requested_model": "jev-1.13.0",
        "context": {"text": "synthetic", "original_characters": 9, "omitted_characters": 0},
        "outcome": "invalid_response",
    }
    restored = module.JevCallTrace.model_validate(historical)
    assert restored.invalid_response_reason is None
    reasoned = module.JevCallTrace.model_validate(
        {**historical, "invalid_response_reason": "probability_sum"}
    )
    round_trip = module.JevCallTrace.model_validate_json(reasoned.model_dump_json())
    assert round_trip.invalid_response_reason == "probability_sum"
    with pytest.raises(ValidationError):
        module.JevCallTrace.model_validate(
            {**historical, "invalid_response_reason": "arbitrary response text"}
        )


@pytest.mark.parametrize("action", ["fallback", "preview"])
def test_trace_round_trip_keeps_caller_response_and_action(action: str) -> None:
    module = importlib.import_module("src.infrastructure.llm.jev_debug_models")
    trace = module.JevCallTrace(
        id=uuid4(),
        run_id="meeting-run",
        caller="meeting_template_selection",
        usage="meeting_template",
        started_at=datetime.now(UTC),
        requested_model="jev-1.13.0",
        context=module.context_preview({"state": "synthetic"}),
        outcome="low_confidence",
        action=action,
        action_target="meeting_synthesis",
        applied_decisions={"q0": "unknown"},
        decision_labels={"q0": "Source title"},
    )
    restored = module.JevCallTrace.model_validate_json(trace.model_dump_json())
    assert restored.caller == "meeting_template_selection"
    assert restored.action == action
    assert restored.applied_decisions == {"q0": "unknown"}
    assert restored.decision_labels == {"q0": "Source title"}
    assert restored.run_id == "meeting-run"
    assert restored.context.text == '{\n  "state": "synthetic"\n}'


async def test_batch_debug_keeps_every_answer_under_its_own_question() -> None:
    from src.infrastructure.llm.jev_debug_models import JevCallTrace, context_preview
    from src.infrastructure.llm.jev_debug_store import finish_trace
    from src.infrastructure.llm.typesafe_client import DecisionUsage

    trace = JevCallTrace(
        id=uuid4(),
        run_id="filter-run",
        caller="filter",
        usage="filter",
        started_at=datetime.now(UTC),
        requested_model="jev-1.13.0",
        context=context_preview("synthetic"),
    )
    question = ChoiceQuestion(
        instructions="Classify.", criteria={"match": "Match", "unknown": "Missing evidence"}
    )
    answers = {
        "q0": ChoiceAnswer(
            type="choice",
            choice="match",
            confidence=0.99,
            probabilities={"match": 0.999, "unknown": 0.001},
        ),
        "q1": ChoiceAnswer(
            type="choice",
            choice="unknown",
            confidence=0.99,
            probabilities={"match": 0.001, "unknown": 0.999},
        ),
    }
    with patch("src.infrastructure.llm.jev_debug_store.save_trace", AsyncMock()):
        result = await finish_trace(
            uuid4(),
            trace,
            answer=answers,
            question={"q0": question, "q1": question},
            reported_model="jev-1.13.0",
            duration_ms=200,
            outcome="success",
            action="pending",
            status_code=None,
            counters=DecisionUsage(input_tokens=700, output_tokens=30),
            cost_eur=0.0001,
        )
    assert result is not None
    restored = JevCallTrace.model_validate_json(result.model_dump_json())
    assert restored.responses["q0"].choice == "match"
    assert restored.responses["q1"].choice_label == "Missing evidence"
    assert restored.input_tokens == 700
    assert restored.response is None
