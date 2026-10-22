"""A decision is never refused for what is mechanical; its intent stays as strict as the schema."""

import pytest
from pydantic import ValidationError

from src.domains.proactive_discussions.llm_contracts import DecisionEnvelope
from src.domains.proactive_discussions.schemas import (
    EngageDecision,
    SkipDecision,
)

pytestmark = pytest.mark.unit


def published_length(model: type, name: str) -> int:
    (limit,) = [
        constraint.max_length
        for constraint in model.model_fields[name].metadata
        if getattr(constraint, "max_length", None) is not None
    ]
    return limit


def test_a_skip_reason_past_its_published_length_is_cut_at_it():
    # Measured 2026-10-21: an opening run failed at its decision over a skip reason one
    # model wrote longer than the schema allows.
    limit = published_length(SkipDecision, "reason")
    envelope = DecisionEnvelope.model_validate(
        {"decision": {"action": "skip", "reason": "word " * limit}}
    )
    assert envelope.decision.action == "skip"
    assert 0 < len(envelope.decision.reason) <= limit


def test_an_engagement_keeps_its_intent_its_topic_cut_and_references_read_once():
    limit = published_length(EngageDecision, "topic")
    envelope = DecisionEnvelope.model_validate(
        {
            "decision": {
                "action": "engage",
                "reason": "A fictional plan worth asking about",
                "topic": "t" * (limit + 40),
                "references": ["calendar:a", "calendar:a", "emails:b"],
            }
        }
    )
    decision = envelope.decision
    assert isinstance(decision, EngageDecision)
    assert len(decision.topic) == limit
    assert decision.references == ("calendar:a", "emails:b")


@pytest.mark.parametrize(
    "decision",
    [
        {"action": "maybe", "reason": "an action nobody declared"},
        {"action": "engage", "reason": "r", "topic": "t", "references": []},
        {"action": "defer", "reason": "r", "retry_after_seconds": 0},
    ],
)
def test_what_carries_intent_stays_strict(decision):
    with pytest.raises(ValidationError):
        DecisionEnvelope.model_validate({"decision": decision})


def test_the_schema_the_model_reads_is_the_decision_union_alone():
    assert set(DecisionEnvelope.model_json_schema()["properties"]) == {"decision"}
