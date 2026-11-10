"""Closed advisory annotations shared by source readers and display serializers."""

from datetime import UTC, datetime
from typing import Annotated, Final, Literal, TypeVar

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    model_validator,
)

EmailCategory = Literal["unknown", "professional", "personal", "spam", "phishing_scam"]
EmailPriority = Literal["unknown", "normal", "urgent", "critical"]
EventCategory = Literal["unknown", "professional", "personal"]
EvidenceScope = Literal["metadata", "snippet", "body", "summary", "partial_body", "event"]


# v2 adds whether an e-mail expects a reply (ADR-374); a v1 annotation is still read, an
# archived one never re-classified, so both versions stay in the vocabulary.
ClassificationVersion = Literal["email-event-v1-phishing", "email-event-v2-reply"]
CLASSIFICATION_VERSION: Final[ClassificationVersion] = "email-event-v2-reply"


class ClassificationStamp(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    version: ClassificationVersion = CLASSIFICATION_VERSION
    evidence_scope: EvidenceScope
    evaluated_at: AwareDatetime
    valid_until: AwareDatetime

    @model_validator(mode="after")
    def positive_validity(self) -> ClassificationStamp:
        if self.valid_until <= self.evaluated_at:
            raise ValueError("An annotation must have positive validity")
        return self


class EmailClassification(ClassificationStamp):
    kind: Literal["email"] = "email"
    category: EmailCategory = "unknown"
    priority: EmailPriority = "unknown"
    # None: not judged, or not decided at the reply margin; False for spam and phishing.
    reply_expected: bool | None = None


class EventClassification(ClassificationStamp):
    kind: Literal["event"] = "event"
    category: EventCategory = "unknown"


ContentClassification = EmailClassification | EventClassification

_Stamp = TypeVar("_Stamp", bound=ClassificationStamp)


def _unexpired(value: _Stamp | None) -> _Stamp | None:
    return value if value is None or value.valid_until > datetime.now(UTC) else None


# Live read DTOs forget expired annotations; archived RegistryItems keep the
# captured advisory value and never trigger a fresh call on replay.
LiveEmailClassification = Annotated[EmailClassification | None, AfterValidator(_unexpired)]
LiveEventClassification = Annotated[EventClassification | None, AfterValidator(_unexpired)]
