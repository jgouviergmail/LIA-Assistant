"""Classification gates bind accepted labels to evidence, independently of relevance."""

from datetime import UTC, datetime

import pytest

from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.domains.agents.services.qualification.policy import (
    accepted_choice,
    classify_answers,
)
from src.infrastructure.llm.typesafe_client import ChoiceAnswer

pytestmark = pytest.mark.unit


def observation(kind: str = "email") -> ClassificationObservation:
    return ClassificationObservation.model_validate(
        {
            "identity": "message-1",
            "kind": kind,
            "container_id": "inbox",
            "item_id": "id-1",
            "occurrence": "",
            "revision": "etag-1",
            "evidence_scope": "snippet",
            "evidence": {"subject": "A contract", "snippet": "Please read"},
        }
    )


def answer(choice: str, options: tuple[str, ...], confidence: float = 1.0) -> ChoiceAnswer:
    return ChoiceAnswer(
        type="choice",
        choice=choice,
        confidence=confidence,
        probabilities={key: float(key == choice) for key in options},
    )


EMAIL = ("unknown", "professional", "personal", "spam", "phishing_scam")
PRIORITY = ("unknown", "normal", "urgent", "critical")


def test_low_confidence_category_does_not_erase_an_independently_accepted_priority() -> None:
    result = classify_answers(
        observation(),
        category=answer("professional", EMAIL, 0.1),
        priority=answer("urgent", PRIORITY),
        now=datetime.now(UTC),
    )
    assert result.category == "unknown" and result.priority == "urgent"


def test_phishing_is_a_category_in_the_same_question_not_a_third_billable_question() -> None:
    result = classify_answers(
        observation(),
        category=answer("phishing_scam", EMAIL),
        priority=answer("normal", PRIORITY),
        now=datetime.now(UTC),
    )
    assert result.category == "phishing_scam" and result.priority == "normal"
    assert result.evidence_scope == "snippet"


@pytest.mark.parametrize(
    "case",
    ["tie", "unknown_option", "low_provider", "low_concentration", "missing_option"],
)
def test_doubt_or_a_malformed_distribution_never_publishes_a_label(case: str) -> None:
    probabilities = {"unknown": 0.0, "professional": 1.0, "personal": 0.0}
    choice, confidence = "professional", 1.0
    if case == "tie":
        probabilities = {"unknown": 0.5, "professional": 0.5, "personal": 0.0}
    if case == "unknown_option":
        choice = "administrator"
    if case == "low_provider":
        confidence = 0.1
    if case == "low_concentration":
        probabilities = {"unknown": 0.3, "professional": 0.4, "personal": 0.3}
    if case == "missing_option":
        probabilities.pop("personal")
    value = ChoiceAnswer(
        type="choice", choice=choice, confidence=confidence, probabilities=probabilities
    )
    assert accepted_choice(value, ("unknown", "professional", "personal")) == "unknown"


def test_event_cannot_inherit_email_only_categories_or_priorities() -> None:
    result = classify_answers(
        observation("event"),
        category=answer("phishing_scam", EMAIL),
        priority=answer("critical", PRIORITY),
        now=datetime.now(UTC),
    )
    assert result.kind == "event" and result.category == "unknown"
    assert "priority" not in result.model_dump()


def test_closed_annotation_round_trips_without_source_text_and_has_a_bounded_validity() -> None:
    now = datetime(2026, 10, 18, 12, tzinfo=UTC)
    result = classify_answers(
        observation(), category=answer("personal", EMAIL), priority=None, now=now
    )
    assert type(result).model_validate_json(result.model_dump_json()) == result
    assert result.evaluated_at == now and result.valid_until > now
    assert "Please read" not in result.model_dump_json()
