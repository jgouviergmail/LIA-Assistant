"""Accepted native annotations; never provider flags or model-written HTML."""

from src.core.classification_projection import read_classification
from src.core.content_classification import ContentClassification, EmailClassification
from src.core.i18n_classification import ClassificationLabel, classification_label
from src.domains.agents.display.components.base import escape_html


def classification_badges(value: object, language: str, *, answered: bool = False) -> str:
    """Render the badge row of an accepted annotation, or nothing.

    Args:
        value: The stored annotation, read through the one projection.
        language: The reader's language for the labels.
        answered: The mailbox said the person answered this message (ADR-379): the
            reply it asked for was given, so « reply expected » is not shown.

    Returns:
        The badge row's HTML, or an empty string when nothing is shown.
    """
    annotation = read_classification(value)
    if annotation is None:
        return ""
    classified_at = escape_html(annotation.evaluated_at.isoformat())
    parts = [
        _badge(key, classified_at, language)
        for key in _shown_labels(annotation)
        if not (answered and key == "reply_expected")
    ]
    return '<div class="lia-classification">' + " ".join(parts) + "</div>" if parts else ""


def _shown_labels(annotation: ContentClassification) -> list[ClassificationLabel]:
    """The labels an annotation shows, in reading order: category, priority, reply."""
    labels: list[ClassificationLabel] = []
    if annotation.category != "unknown":
        labels.append(annotation.category)
    if not isinstance(annotation, EmailClassification):
        return labels
    if annotation.priority == "urgent":
        labels.append("urgent")
    elif annotation.priority == "critical":
        labels.append("critical")
    # Only an expected reply is shown: « no reply » and « undecided » say nothing (ADR-374).
    if annotation.reply_expected is True:
        labels.append("reply_expected")
    return labels


def _badge(key: ClassificationLabel, classified_at: str, language: str) -> str:
    """One badge: its tone modifiers, the phishing glyph, its translated label."""
    danger = " content-classification-badge--alert" if key in {"phishing_scam", "critical"} else ""
    phishing = " content-classification-badge--phishing" if key == "phishing_scam" else ""
    warning_tone = " content-classification-badge--warning" if key == "urgent" else ""
    warning = '<span aria-hidden="true">⚠</span> ' if phishing else ""
    return (
        f'<span class="content-classification-badge{danger}{phishing}{warning_tone}" '
        f'data-classified-at="{classified_at}">'
        f"{warning}{escape_html(classification_label(key, language))}</span>"
    )
