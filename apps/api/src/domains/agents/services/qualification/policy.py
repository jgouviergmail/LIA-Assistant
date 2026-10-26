"""Independent conservative acceptance; a model's concentration is not truth."""

from datetime import datetime, timedelta
from typing import get_args

from src.core.constants import (
    JEV_CLASSIFICATION_ALERT_MIN_CONFIDENCE,
    JEV_CLASSIFICATION_EMAIL_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TYPE_CATEGORIES,
    JEV_CLASSIFICATION_MIN_CONFIDENCE,
    JEV_CLASSIFICATION_PROVIDER_COMMERCIAL_LABELS,
    JEV_CLASSIFICATION_PROVIDER_SPAM_LABEL,
    JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS,
)
from src.core.content_classification import (
    ContentClassification,
    EmailCategory,
    EmailClassification,
    EmailPriority,
    EventCategory,
    EventClassification,
)
from src.domains.agents.services.qualification.contracts import (
    ClassificationObservation,
)
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, choice_confidence


def accepted_choice(answer: ChoiceAnswer | None, options: tuple[str, ...]) -> str:
    if answer is None or answer.choice not in options or set(answer.probabilities) != set(options):
        return "unknown"
    probabilities = answer.probabilities
    best = probabilities[answer.choice]
    confidence = choice_confidence(answer)
    if confidence is None:
        return "unknown"
    if sum(value == best for value in probabilities.values()) != 1 or best != max(
        probabilities.values()
    ):
        return "unknown"
    threshold = (
        JEV_CLASSIFICATION_ALERT_MIN_CONFIDENCE
        if answer.choice in {"phishing_scam", "critical"}
        else JEV_CLASSIFICATION_MIN_CONFIDENCE
    )
    return answer.choice if confidence >= threshold else "unknown"


def _provider_event_category(observation: ClassificationObservation) -> str | None:
    """A calendar entry the provider typed as a birthday or a focus block IS its category."""
    event_type = observation.evidence.get("event_type")
    return (
        JEV_CLASSIFICATION_EVENT_TYPE_CATEGORIES.get(event_type)
        if isinstance(event_type, str)
        else None
    )


def _provider_filed_commercial(observation: ClassificationObservation) -> bool:
    """Mail the provider filed under promotions, social, updates or forums, never spam."""
    labels = observation.evidence.get("labels")
    if not isinstance(labels, list):
        return False
    names = {str(label) for label in labels}
    return (
        bool(names & JEV_CLASSIFICATION_PROVIDER_COMMERCIAL_LABELS)
        and JEV_CLASSIFICATION_PROVIDER_SPAM_LABEL not in names
    )


def classify_answers(
    observation: ClassificationObservation,
    *,
    category: ChoiceAnswer | None,
    priority: ChoiceAnswer | None,
    now: datetime,
) -> ContentClassification:
    if observation.kind == "event":
        accepted = _provider_event_category(observation) or accepted_choice(
            category, get_args(EventCategory)
        )
        ttl = (
            JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS
            if accepted == "unknown"
            else JEV_CLASSIFICATION_EVENT_TTL_SECONDS
        )
        return EventClassification.model_validate(
            {
                "category": accepted,
                "evidence_scope": observation.evidence_scope,
                "evaluated_at": now,
                "valid_until": now + timedelta(seconds=ttl),
            }
        )
    accepted_category = accepted_choice(category, get_args(EmailCategory))
    if accepted_category == "spam" and _provider_filed_commercial(observation):
        # Measured (2026-10-25): commercial mail read as spam by the model was the
        # only wrong label left on the production-shaped corpus.
        accepted_category = "unknown"
    accepted_priority = accepted_choice(priority, get_args(EmailPriority))
    ttl = (
        JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS
        if "unknown" in {accepted_category, accepted_priority}
        else JEV_CLASSIFICATION_EMAIL_TTL_SECONDS
    )
    return EmailClassification.model_validate(
        {
            "category": accepted_category,
            "priority": accepted_priority,
            "evidence_scope": observation.evidence_scope,
            "evaluated_at": now,
            "valid_until": now + timedelta(seconds=ttl),
        }
    )
