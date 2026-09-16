"""The execution result says what was done, to whom, with what — and is drawn per surface (ADR-289).

A batch result used to list bare labels (« ✅ Tout va bien »): the person who
had just approved two e-mails could not see from the answer who received
what. Every row now carries the key fields the display registry declares for
its type — recipient, date, place, a bounded excerpt of the text — and the
chat draws the whole result as a ``lia-card``, the ticket keeping Markdown.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.constants import DRAFT_RESULT_EXCERPT_MAX_CHARS
from src.domains.agents.drafts.card_html import CardSurface
from src.domains.agents.drafts.models import DraftAction
from src.domains.agents.drafts.result_renderer import render_execution_result

pytestmark = pytest.mark.unit

BODY = "Bonjour,\n\nJe voulais juste te dire que tout va bien.\n\nÀ bientôt,\nJérôme"


def _row(status: str, draft_type: str, content: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": status,
        "draft_id": f"d-{content.get('subject', content.get('summary', 'x'))}",
        "draft_type": draft_type,
        "message": "ok" if status == "success" else "",
        "data": {
            "_draft_content": {**content, "user_language": "fr", "user_timezone": "Europe/Paris"}
        },
    }


def _batch(draft_type: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    attempted = [r for r in rows if r["status"] != "cancelled"]
    return {
        "status": "success",
        "message": "batch ok",
        "draft_type": draft_type,
        "action": DraftAction.CONFIRM_BATCH.value,
        "data": {
            "batch_results": rows,
            "success_count": sum(1 for r in attempted if r["status"] == "success"),
            "error_count": 0,
            "cancelled_count": len(rows) - len(attempted),
            "total_count": len(attempted),
        },
    }


def _single(draft_type: str, content: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": "success",
        "message": "E-mail envoyé",
        "draft_type": draft_type,
        "action": "confirm",
        "data": {
            "_draft_content": {**content, "user_language": "fr", "user_timezone": "Europe/Paris"}
        },
    }


TWO_MAILS = [
    _row("success", "email", {"to": "paul@example.org", "subject": "Tout va bien", "body": BODY}),
    _row(
        "success",
        "email",
        {
            "to": "anne@example.org",
            "subject": "Penser à appeler Hua demain",
            "body": "Petit rappel.",
        },
    ),
]


class TestARowSaysToWhomAndWhat:
    def test_an_email_row_carries_its_recipient_and_an_excerpt(self) -> None:
        rendered = render_execution_result(_batch("email", TWO_MAILS))
        lines = rendered.splitlines()
        first = next(line for line in lines if "Tout va bien" in line)
        assert first.startswith("- ✅ **Tout va bien**")
        assert "paul@example.org" in first
        assert "« Bonjour, Je voulais juste te dire que tout va bien." in first

    def test_the_excerpt_is_one_bounded_line(self) -> None:
        long_body = "Ligne une.\n\n" + "mot " * 200
        rows = [_row("success", "email", {"to": "a@x", "subject": "S", "body": long_body})]
        rendered = render_execution_result(_batch("email", rows))
        row = next(line for line in rendered.splitlines() if line.startswith("- ✅"))
        excerpt = row.split("« ", 1)[1].rsplit(" »", 1)[0]
        assert "\n" not in excerpt
        assert len(excerpt) <= DRAFT_RESULT_EXCERPT_MAX_CHARS
        assert excerpt.endswith("…")

    def test_an_event_row_carries_its_place_and_its_date(self) -> None:
        rows = [
            _row(
                "success",
                "event",
                {
                    "summary": "Point projet",
                    "start_datetime": "2026-09-17T10:00:00+02:00",
                    "location": "Salle B",
                },
            )
        ]
        rendered = render_execution_result(_batch("event", rows))
        row = next(line for line in rendered.splitlines() if "Point projet" in line)
        assert "Salle B" in row
        assert "10h00" in row or "10:00" in row

    @pytest.mark.parametrize(
        ("language", "opening", "closing"),
        [
            ("fr", "« ", " »"),
            ("en", "“", "”"),
            ("de", "„", "“"),
            ("es", "« ", " »"),
            ("it", "« ", " »"),
            ("zh-CN", "“", "”"),
        ],
    )
    def test_the_excerpt_is_quoted_the_way_the_language_quotes(
        self, language: str, opening: str, closing: str
    ) -> None:
        row = _row("success", "email", {"to": "a@x", "subject": "S", "body": "Hello there"})
        row["data"]["_draft_content"]["user_language"] = language
        rendered = render_execution_result(_batch("email", [row]))
        line = next(line for line in rendered.splitlines() if line.startswith("- ✅"))
        assert f"{opening}Hello there{closing}" in line

    def test_a_peer_message_row_quotes_its_message(self) -> None:
        rows = [
            _row(
                "success",
                "peer_message",
                {"recipient_name": "Anne", "message": "On se voit lundi ?"},
            )
        ]
        rendered = render_execution_result(_batch("peer_message", rows))
        row = next(line for line in rendered.splitlines() if "Anne" in line)
        assert "« On se voit lundi ? »" in row

    def test_the_label_field_is_not_repeated_among_the_fields(self) -> None:
        rendered = render_execution_result(_batch("email", TWO_MAILS))
        row = next(line for line in rendered.splitlines() if "Tout va bien" in line)
        assert row.count("Tout va bien") == 1


class TestTheChatDrawsACard:
    def test_a_batch_is_a_card_with_a_section_per_item(self) -> None:
        html = render_execution_result(_batch("email", TWO_MAILS), surface=CardSurface.CHAT)
        assert html.startswith('<div class="lia-card lia-draft-result">')
        assert html.count('class="lia-sec__label"') == 2
        assert "✅ Tout va bien" in html
        assert "paul@example.org" in html and "anne@example.org" in html
        assert "\n" not in html

    def test_a_cancelled_item_wears_its_mark(self) -> None:
        rows = [
            _row("cancelled", "email", {"to": "a@x", "subject": "Pas celui-là", "body": "x"}),
            _row("success", "email", {"to": "b@x", "subject": "Celui-ci", "body": "y"}),
        ]
        html = render_execution_result(_batch("email", rows), surface=CardSurface.CHAT)
        assert "🚫 Pas celui-là" in html and "✅ Celui-ci" in html

    def test_a_single_result_is_a_card_with_its_fields_and_its_text(self) -> None:
        html = render_execution_result(
            _single("email", {"to": "paul@example.org", "subject": "Tout va bien", "body": BODY}),
            surface=CardSurface.CHAT,
        )
        assert html.startswith('<div class="lia-card lia-draft-result">')
        assert "E-mail envoyé" in html
        assert "paul@example.org" in html
        assert "Bonjour,<br><br>Je voulais juste te dire que tout va bien." in html

    def test_every_value_is_escaped(self) -> None:
        rows = [_row("success", "email", {"to": "a@x", "subject": "<b>S</b>", "body": "<i>t</i>"})]
        html = render_execution_result(_batch("email", rows), surface=CardSurface.CHAT)
        assert "<b>S</b>" not in html and "&lt;b&gt;S&lt;/b&gt;" in html
        assert "<i>t</i>" not in html

    def test_a_result_without_a_family_emoji_shows_its_mark_once(self) -> None:
        html = render_execution_result(
            {"status": "cancelled", "message": "OK, c'est annulé.", "draft_type": "no_such_type"},
            surface=CardSurface.CHAT,
        )
        assert html.count("🚫") == 1
        assert "OK, c&#x27;est annulé." in html or "OK, c'est annulé." in html

    def test_the_plain_form_is_the_default(self) -> None:
        rendered = render_execution_result(_batch("email", TWO_MAILS))
        assert rendered.startswith("📧 ✅ **")
        assert "<" not in rendered
