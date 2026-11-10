"""A compact email preview never hides a distinct received excerpt permanently."""

from html import unescape

import pytest

from src.core.config import settings
from src.core.i18n_cards import card_label
from src.domains.agents.display.components.base import RenderContext, escape_html
from src.domains.agents.display.components.email_card import EmailCard

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ("body_fields", "has_excerpt"),
    [
        ({}, True),
        ({"body": ""}, True),
        ({"body": "A different complete message."}, True),
        ({"body": "Before RECEIVED_FACT after."}, False),
        ({"bodyPreview": "Before RECEIVED_FACT after."}, False),
        ({"bodyPreview": "A different provider body preview."}, True),
        ({"body": "<script>RECEIVED_FACT</script><p>Visible body.</p>"}, True),
    ],
    ids=[
        "absent",
        "empty",
        "distinct",
        "included",
        "preview-included",
        "preview-distinct",
        "hidden-in-html",
    ],
)
def test_short_excerpt_is_reachable_unless_the_displayed_body_already_contains_it(
    body_fields: dict[str, object], has_excerpt: bool
) -> None:
    out = EmailCard().render(
        {"subject": "Message", "snippet": "RECEIVED_FACT", **body_fields},
        RenderContext(language="en"),
    )
    front, separator, details = out.partition("<details")
    assert 'class="lia-email__snippet"' in front
    assert "RECEIVED_FACT" in front
    assert separator and "RECEIVED_FACT" in details
    assert (card_label("excerpt", "en") in details) is has_excerpt
    assert details.count("RECEIVED_FACT") == 1
    assert "<script>" not in out


@pytest.mark.parametrize("language", ["fr", "en", "de", "es", "it", "zh-CN"])
def test_excerpt_disclosure_preserves_literal_html_characters(language: str) -> None:
    snippet = 'Budget < 10 € & "no extra" <b>literal words</b>.'
    out = EmailCard().render(
        {"subject": "Message", "body": "Another fact.", "snippet": snippet},
        RenderContext(language=language),
    )
    details = out.partition("<details")[2]
    assert snippet in unescape(details)
    assert escape_html(snippet) in details
    assert escape_html(card_label("excerpt", language)) in details
    assert "<b>literal words</b>" not in out


def test_excerpt_already_visible_from_html_body_is_not_duplicated() -> None:
    out = EmailCard().render(
        {"body": "<p>Budget &lt; 10 € &amp; no extra.</p>", "snippet": "Budget < 10 € & no extra."},
        RenderContext(language="en"),
    )
    details = out.partition("<details")[2]
    assert "Budget < 10 € & no extra." in unescape(details)
    assert card_label("excerpt", "en") not in details


def test_full_body_disclosure_already_keeps_a_snippet_beyond_its_preview(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "emails_body_max_length", 50)
    out = EmailCard().render(
        {"body": "Earlier text. " * 15 + "LAST_RECEIVED_FACT", "snippet": "LAST_RECEIVED_FACT"},
        RenderContext(language="en"),
    )
    details = out.partition("<details")[2]
    assert "LAST_RECEIVED_FACT" in details
    assert card_label("full_message", "en") in details
    assert card_label("excerpt", "en") not in details


@pytest.mark.parametrize("snippet", ["", None])
def test_absent_excerpt_adds_no_empty_disclosure(snippet: str | None) -> None:
    out = EmailCard().render(
        {"subject": "Message", "snippet": snippet}, RenderContext(language="en")
    )
    assert 'class="lia-email__snippet"' not in out
    assert "<details" not in out
