"""Accepted native annotations; never provider flags or model-written HTML."""

from src.core.classification_projection import read_classification
from src.core.content_classification import EmailClassification
from src.core.i18n_classification import ClassificationLabel, classification_label
from src.domains.agents.display.components.base import escape_html


def classification_badges(value: object, language: str) -> str:
    annotation = read_classification(value)
    if annotation is None:
        return ""
    labels: list[ClassificationLabel] = []
    if annotation.category != "unknown":
        labels.append(annotation.category)
    if isinstance(annotation, EmailClassification) and annotation.priority not in {
        "unknown",
        "normal",
    }:
        if annotation.priority == "urgent":
            labels.append("urgent")
        elif annotation.priority == "critical":
            labels.append("critical")
    parts = []
    for key in labels:
        danger = (
            " content-classification-badge--alert" if key in {"phishing_scam", "critical"} else ""
        )
        phishing = " content-classification-badge--phishing" if key == "phishing_scam" else ""
        warning_tone = " content-classification-badge--warning" if key == "urgent" else ""
        warning = '<span aria-hidden="true">⚠</span> ' if phishing else ""
        parts.append(
            f'<span class="content-classification-badge{danger}{phishing}{warning_tone}" '
            f'data-classified-at="{escape_html(annotation.evaluated_at.isoformat())}">'
            f"{warning}{escape_html(classification_label(key, language))}</span>"
        )
    return '<div class="lia-classification">' + " ".join(parts) + "</div>" if parts else ""
