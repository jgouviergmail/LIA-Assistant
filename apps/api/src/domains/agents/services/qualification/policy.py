"""Independent conservative acceptance; a model's concentration is not truth."""

import math
from datetime import datetime, timedelta
from typing import get_args

from src.core.constants import (
    JEV_CLASSIFICATION_ALERT_MIN_CONFIDENCE,
    JEV_CLASSIFICATION_EMAIL_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TTL_SECONDS,
    JEV_CLASSIFICATION_MIN_CONFIDENCE,
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
from src.infrastructure.llm.typesafe_client import ChoiceAnswer


def accepted_choice(answer: ChoiceAnswer | None, options: tuple[str, ...]) -> str:
    if answer is None or answer.choice not in options or set(answer.probabilities) != set(options):
        return "unknown"
    probabilities = answer.probabilities
    best = probabilities[answer.choice]
    if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=1e-6):
        return "unknown"
    if sum(value == best for value in probabilities.values()) != 1 or best != max(
        probabilities.values()
    ):
        return "unknown"
    concentration = (best - 1 / len(options)) / (1 - 1 / len(options))
    threshold = (
        JEV_CLASSIFICATION_ALERT_MIN_CONFIDENCE
        if answer.choice in {"phishing_scam", "critical"}
        else JEV_CLASSIFICATION_MIN_CONFIDENCE
    )
    return answer.choice if min(answer.confidence, concentration) >= threshold else "unknown"


def classify_answers(
    observation: ClassificationObservation,
    *,
    category: ChoiceAnswer | None,
    priority: ChoiceAnswer | None,
    now: datetime,
) -> ContentClassification:
    if observation.kind == "event":
        accepted = accepted_choice(category, get_args(EventCategory))
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
