"""The server badge row: which labels an accepted annotation shows, and how each is drawn.

Characterization written before the label selection and the badge drawing were split
(ADR-374, lot F): the exact HTML, order and tone classes included, is the oracle.
"""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.content_classification import (
    ContentClassification,
    EmailClassification,
    EventClassification,
)
from src.core.i18n_classification import classification_label
from src.domains.agents.display.components.classification_badges import classification_badges

pytestmark = pytest.mark.unit

_EVALUATED_AT = datetime.now(UTC)


def _email(**fields: object) -> EmailClassification:
    return EmailClassification.model_validate(
        {
            "evidence_scope": "snippet",
            "evaluated_at": _EVALUATED_AT,
            "valid_until": _EVALUATED_AT + timedelta(minutes=5),
            **fields,
        }
    )


def _badge(key: str, modifiers: str = "", glyph: str = "") -> str:
    return (
        f'<span class="content-classification-badge{modifiers}" '
        f'data-classified-at="{_EVALUATED_AT.isoformat()}">'
        f"{glyph}{classification_label(key, 'en')}</span>"
    )


def _row(*badges: str) -> str:
    return '<div class="lia-classification">' + " ".join(badges) + "</div>"


def _render(annotation: ContentClassification) -> str:
    return classification_badges(annotation.model_dump(mode="json"), "en")


def test_an_urgent_email_awaiting_a_reply_reads_category_priority_then_reply() -> None:
    annotation = _email(category="professional", priority="urgent", reply_expected=True)
    assert _render(annotation) == _row(
        _badge("professional"),
        _badge("urgent", " content-classification-badge--warning"),
        _badge("reply_expected"),
    )


def test_a_critical_phishing_email_raises_both_alerts_with_one_warning_glyph() -> None:
    annotation = _email(category="phishing_scam", priority="critical", reply_expected=False)
    assert _render(annotation) == _row(
        _badge(
            "phishing_scam",
            " content-classification-badge--alert content-classification-badge--phishing",
            '<span aria-hidden="true">⚠</span> ',
        ),
        _badge("critical", " content-classification-badge--alert"),
    )


@pytest.mark.parametrize("priority", ["unknown", "normal"])
def test_a_quiet_priority_draws_no_badge(priority: str) -> None:
    assert _render(_email(category="personal", priority=priority)) == _row(_badge("personal"))


def test_an_event_shows_its_category_alone() -> None:
    annotation = EventClassification(
        category="professional",
        evidence_scope="event",
        evaluated_at=_EVALUATED_AT,
        valid_until=_EVALUATED_AT + timedelta(minutes=5),
    )
    assert _render(annotation) == _row(_badge("professional"))


def test_an_annotation_with_nothing_to_show_draws_no_row() -> None:
    assert _render(_email()) == ""
    assert classification_badges(None, "en") == ""
