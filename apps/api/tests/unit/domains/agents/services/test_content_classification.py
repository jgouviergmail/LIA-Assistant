"""Classification gates bind accepted labels to evidence, independently of relevance."""

import json
import re
from datetime import UTC, datetime

import pytest

from src.core.constants import (
    JEV_CLASSIFICATION_PROVIDER_COMMERCIAL_LABELS,
    JEV_CLASSIFICATION_PROVIDER_SPAM_LABEL,
)
from src.domains.agents.prompts.prompt_loader import load_prompt
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


def observed_with(kind: str, evidence: dict[str, object]) -> ClassificationObservation:
    return ClassificationObservation.model_validate(
        {**observation(kind).model_dump(), "evidence": {**observation(kind).evidence, **evidence}}
    )


@pytest.mark.parametrize("label", sorted(JEV_CLASSIFICATION_PROVIDER_COMMERCIAL_LABELS))
def test_mail_the_provider_filed_as_commercial_is_never_published_as_spam(label: str) -> None:
    """Measured 2026-10-25: the only wrong label left on the production-shaped corpus."""
    result = classify_answers(
        observed_with("email", {"labels": ["INBOX", label]}),
        category=answer("spam", EMAIL),
        priority=answer("normal", PRIORITY),
        now=datetime.now(UTC),
    )
    assert result.category == "unknown" and result.priority == "normal"


@pytest.mark.parametrize("labels", [["SPAM", "CATEGORY_PROMOTIONS"], ["INBOX"], None])
def test_spam_stands_when_the_provider_called_it_spam_or_filed_nothing(labels) -> None:
    evidence = {} if labels is None else {"labels": labels}
    result = classify_answers(
        observed_with("email", evidence),
        category=answer("spam", EMAIL),
        priority=answer("normal", PRIORITY),
        now=datetime.now(UTC),
    )
    assert result.category == "spam"


def test_a_commercial_label_never_hides_phishing() -> None:
    result = classify_answers(
        observed_with("email", {"labels": ["CATEGORY_UPDATES"]}),
        category=answer("phishing_scam", EMAIL),
        priority=answer("unknown", PRIORITY),
        now=datetime.now(UTC),
    )
    assert result.category == "phishing_scam"


@pytest.mark.parametrize(
    "event_type,category",
    [("birthday", "personal"), ("focusTime", "professional"), ("workingLocation", "professional")],
)
def test_a_calendar_entry_the_provider_typed_is_its_category(event_type, category) -> None:
    result = classify_answers(
        observed_with("event", {"event_type": event_type}),
        category=answer("unknown", ("unknown", "professional", "personal")),
        priority=None,
        now=datetime.now(UTC),
    )
    assert result.category == category


def test_an_untyped_or_other_entry_is_left_to_the_judgment() -> None:
    result = classify_answers(
        observed_with("event", {"event_type": "outOfOffice"}),
        category=answer("unknown", ("unknown", "professional", "personal")),
        priority=None,
        now=datetime.now(UTC),
    )
    assert result.category == "unknown"


def test_the_question_names_exactly_the_provider_labels_the_rule_reads() -> None:
    # A prompt states what the code enforces (ADR-284): a label the rule reads but
    # the question never names is mail the model was not told is not spam.
    spam = json.loads(load_prompt("jev_email_category_question", version="v1"))["criteria"]["spam"]

    named = set(re.findall(r"\b(?:CATEGORY_[A-Z]+|SPAM)\b", json.dumps(spam)))

    assert named == JEV_CLASSIFICATION_PROVIDER_COMMERCIAL_LABELS | {
        JEV_CLASSIFICATION_PROVIDER_SPAM_LABEL
    }
