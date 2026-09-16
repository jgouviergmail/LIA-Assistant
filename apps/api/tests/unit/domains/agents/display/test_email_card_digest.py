"""The e-mail card draws a digest when the message carries one (ADR-287).

Under ``detail=summary`` a message reaches the card with ``gist``,
``key_points`` and ``actions`` instead of a body. The card shows them under
translated labels — six languages, ``zh-CN`` included — through the same
section components as the recipients and the body, and draws nothing when the
message carries no digest.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import RenderContext, escape_html
from src.domains.agents.display.components.email_card import EmailCard

pytestmark = [pytest.mark.unit]

LANGUAGES = ("fr", "en", "de", "es", "it", "zh-CN")


def _digested() -> dict[str, Any]:
    return {
        "id": "m1",
        "subject": "Weekly digest",
        "from": "Alice <alice@example.com>",
        "date": "Tue, 15 Sep 2026 17:24:45 +0000",
        "snippet": "First paragraph",
        "gist": "Alice shares the weekly numbers and asks for a reply by Friday.",
        "key_points": ["Revenue up 4 %", "Two new hires"],
        "actions": ["Reply before Friday"],
        "category": "work",
        "importance": "high",
        "digest_status": "computed",
        "attachments": [],
    }


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_digest_is_drawn_under_translated_labels(language: str) -> None:
    html = EmailCard().render(_digested(), RenderContext(language=language))

    assert escape_html(V3Messages.get_digest(language)) in html
    assert escape_html(V3Messages.get_key_points(language)) in html
    assert escape_html(V3Messages.get_actions(language)) in html
    assert "asks for a reply by Friday" in html
    assert "Revenue up 4 %" in html and "Two new hires" in html
    assert "Reply before Friday" in html


def test_the_six_labels_are_distinct_translations() -> None:
    for getter in (V3Messages.get_digest, V3Messages.get_key_points, V3Messages.get_actions):
        labels = {getter(lang) for lang in LANGUAGES}
        assert len(labels) >= 5, "a label copied across languages is a missing translation"


def test_a_message_without_a_digest_draws_no_digest_section() -> None:
    data = _digested()
    for key in ("gist", "key_points", "actions", "category", "importance", "digest_status"):
        data.pop(key)
    html = EmailCard().render(data, RenderContext(language="fr"))
    assert escape_html(V3Messages.get_digest("fr")) not in html


def test_empty_lists_draw_no_empty_rows() -> None:
    data = {**_digested(), "key_points": [], "actions": []}
    html = EmailCard().render(data, RenderContext(language="en"))
    assert V3Messages.get_digest("en") in html
    assert V3Messages.get_key_points("en") not in html
    assert V3Messages.get_actions("en") not in html


def test_the_snippet_is_drawn_once() -> None:
    html = EmailCard().render(_digested(), RenderContext(language="en"))
    assert html.count('class="lia-email__snippet"') == 1
