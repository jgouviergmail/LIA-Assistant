"""One closed annotation read contract for model projections and display.

What a MODEL is told of an annotation is its labels and a state the code decides
at the moment it is shown — ``current`` or ``expired`` — never the annotation's
instants (2026-10-25). Handed ``valid_until`` in UTC beside a clock in the
person's own zone, a model compared the two wall times and told the person a
label valid for another hour had expired (measured on dev: 00:05:59Z read
against « 01:05, Europe/Paris »). The collection filters already work this way:
the code computes the comparison, the decision model never does date arithmetic.
The display reads the whole annotation (its badges, its cache), never this view.

The walk that applies this view to tool data and to archived answers is shared with
every other annotation an item carries (``core/annotation_projection``).
"""

from datetime import UTC, datetime

from pydantic import TypeAdapter, ValidationError

from src.core.content_classification import (
    ContentClassification,
    EmailClassification,
    EventClassification,
)

_ADAPTER: TypeAdapter[ContentClassification] = TypeAdapter(ContentClassification)
#: The key under which a published item carries its annotation (``publication``).
CLASSIFICATION_KEY = "classification"


def read_classification(value: object) -> ContentClassification | None:
    try:
        return _ADAPTER.validate_python(value)
    except ValidationError:
        return None


def classification_view(value: object, now: datetime | None = None) -> dict[str, str] | None:
    """What a model is told of one annotation: its labels and its state.

    Args:
        value: A stored annotation (its JSON form or the model).
        now: The moment it is shown; the current instant by default.

    Returns:
        The labels, the evidence scope and ``state`` — ``current`` or ``expired``,
        decided here — or ``None`` when the value is no annotation.
    """
    annotation = read_classification(value)
    if annotation is None:
        return None
    moment = now if now is not None else datetime.now(UTC)
    view: dict[str, str] = {
        "kind": annotation.kind,
        "category": annotation.category,
        "evidence_scope": annotation.evidence_scope,
    }
    if isinstance(annotation, EmailClassification):
        view["priority"] = annotation.priority
        # Said only once decided: an undecided reply is no claim (ADR-374).
        if annotation.reply_expected is not None:
            view["reply_expected"] = str(annotation.reply_expected).lower()
    view["state"] = "current" if moment < annotation.valid_until else "expired"
    return view


def classification_text(value: object, now: datetime | None = None) -> str:
    """The one-line form of :func:`classification_view`; empty when nothing is labelled."""
    view = classification_view(value, now)
    if view is None:
        return ""
    labels = []
    if view["category"] != "unknown":
        labels.append(f"category={view['category']}")
    if view.get("priority", "unknown") != "unknown":
        labels.append(f"priority={view['priority']}")
    if "reply_expected" in view:
        labels.append(f"reply_expected={view['reply_expected']}")
    if not labels:
        return ""
    return (
        f"JEV qualification ({view['evidence_scope']}; advisory; {view['state']}): "
        f"{', '.join(labels)}"
    )


def classification_fields(value: object) -> dict[str, str]:
    annotation = read_classification(value)
    if annotation is None or annotation.valid_until <= datetime.now(UTC):
        return {}
    text = classification_text(value)
    return {"qualification": text} if text else {}


def email_classification(value: object) -> EmailClassification | None:
    annotation = read_classification(value)
    return annotation if isinstance(annotation, EmailClassification) else None


def event_classification(value: object) -> EventClassification | None:
    annotation = read_classification(value)
    return annotation if isinstance(annotation, EventClassification) else None
