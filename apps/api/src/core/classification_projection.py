"""One closed annotation read contract for model projections and display."""

from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from src.core.content_classification import (
    ContentClassification,
    EmailClassification,
    EventClassification,
)

_ADAPTER: TypeAdapter[ContentClassification] = TypeAdapter(ContentClassification)


def read_classification(value: object) -> ContentClassification | None:
    try:
        return _ADAPTER.validate_python(value)
    except ValidationError:
        return None


def classification_text(value: object) -> str:
    annotation = read_classification(value)
    if annotation is None:
        return ""
    labels = []
    if annotation.category != "unknown":
        labels.append(f"category={annotation.category}")
    if isinstance(annotation, EmailClassification) and annotation.priority != "unknown":
        labels.append(f"priority={annotation.priority}")
    if not labels:
        return ""
    return (
        f"JEV qualification ({annotation.evidence_scope}; advisory; "
        f"valid_until={annotation.valid_until.isoformat()}): {', '.join(labels)}"
    )


def email_classification(value: object) -> EmailClassification | None:
    annotation = read_classification(value)
    return annotation if isinstance(annotation, EmailClassification) else None


def classification_fields(value: object) -> dict[str, str]:
    annotation = read_classification(value)
    if annotation is None or annotation.valid_until <= datetime.now(UTC):
        return {}
    text = classification_text(value)
    return {"qualification": text} if text else {}


def event_classification(value: object) -> EventClassification | None:
    annotation = read_classification(value)
    return annotation if isinstance(annotation, EventClassification) else None
