"""Independent conservative acceptance; a model's concentration is not truth."""

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import Decimal
from typing import get_args

from src.core.constants import (
    JEV_CLASSIFICATION_EMAIL_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TTL_SECONDS,
    JEV_CLASSIFICATION_EVENT_TYPE_CATEGORIES,
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
from src.domains.llm_config.jev_gates import gate_passes
from src.domains.llm_config.jev_registry import JevUsage
from src.infrastructure.llm.typesafe_client import ChoiceAnswer, NoulAnswer, choice_confidence

_ALERT_CHOICES = frozenset({"phishing_scam", "critical"})
#: Categories that say the sender is legitimate: only their messages can expect a reply.
_LEGITIMATE_CATEGORIES = frozenset({"professional", "personal"})
#: Categories that expect no legitimate reply, whatever the reply question reads.
_NO_REPLY_CATEGORIES = frozenset({"spam", "phishing_scam"})


def accepted_choice(
    answer: ChoiceAnswer | None,
    options: tuple[str, ...],
    *,
    usage: JevUsage = JevUsage.EMAIL_CLASSIFICATION,
    gate: str = "category",
    thresholds: Mapping[str, Decimal] | None = None,
) -> str:
    """The chosen label when it is the unique maximum and passes its gate, else unknown.

    A phishing or a critical verdict answers to the ``alert`` gate of the e-mail usage;
    every other label to ``gate``. ``thresholds`` are the operation's (ADR-374), the
    declared defaults when ``None``.
    """
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
    key = "alert" if answer.choice in _ALERT_CHOICES else gate
    return answer.choice if gate_passes(thresholds or {}, usage, key, confidence) else "unknown"


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


def accepted_reply(
    category: str,
    reply: NoulAnswer | None,
    thresholds: Mapping[str, Decimal] | None = None,
) -> bool | None:
    """Whether an e-mail expects a reply, once its category is accepted (ADR-374).

    Spam and phishing expect no legitimate reply (the question read them anywhere from
    0.33 to 0.92, measured 2026-11-06). Without an accepted category nothing says the
    sender is legitimate, so nothing is claimed. Otherwise the Noul decides at the
    ``reply_expected`` margin: expected from ``1 - margin`` up, not expected up to it.
    """
    if category in _NO_REPLY_CATEGORIES:
        return False
    if category not in _LEGITIMATE_CATEGORIES or reply is None:
        return None
    if not gate_passes(
        thresholds or {}, JevUsage.EMAIL_CLASSIFICATION, "reply_expected", reply.noul
    ):
        return None
    return reply.noul >= 0.5


def classify_answers(
    observation: ClassificationObservation,
    *,
    category: ChoiceAnswer | None,
    priority: ChoiceAnswer | None,
    now: datetime,
    reply: NoulAnswer | None = None,
    thresholds: Mapping[str, Decimal] | None = None,
) -> ContentClassification:
    if observation.kind == "event":
        accepted = _provider_event_category(observation) or accepted_choice(
            category,
            get_args(EventCategory),
            usage=JevUsage.EVENT_CLASSIFICATION,
            thresholds=thresholds,
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
    accepted_category = accepted_choice(category, get_args(EmailCategory), thresholds=thresholds)
    if accepted_category == "spam" and _provider_filed_commercial(observation):
        # Measured (2026-10-25): commercial mail read as spam by the model was the
        # only wrong label left on the production-shaped corpus.
        accepted_category = "unknown"
    accepted_priority = accepted_choice(
        priority, get_args(EmailPriority), gate="priority", thresholds=thresholds
    )
    ttl = (
        JEV_CLASSIFICATION_UNKNOWN_TTL_SECONDS
        if "unknown" in {accepted_category, accepted_priority}
        else JEV_CLASSIFICATION_EMAIL_TTL_SECONDS
    )
    return EmailClassification.model_validate(
        {
            "category": accepted_category,
            "priority": accepted_priority,
            "reply_expected": accepted_reply(accepted_category, reply, thresholds),
            "evidence_scope": observation.evidence_scope,
            "evaluated_at": now,
            "valid_until": now + timedelta(seconds=ttl),
        }
    )
