"""The chat draws a draft as a ``lia-card``; a ticket keeps the Markdown (ADR-289).

Same description, two forms. The HTML form uses the classes the data cards
already use (the stylesheet knows them, the sanitiser lets them through),
escapes every value, turns a body's paragraphs into breaks, and is ONE line
so it streams as one chunk. Which form a surface gets is decided by the run's
origin: a ticket run (out-of-turn origin set) renders no markup.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.constants import RESPONSE_DISPLAY_MODE_HTML, RESPONSE_DISPLAY_MODE_MARKDOWN
from src.domains.agents.api.run_origin import (
    RunOrigin,
    out_of_turn_origin_ctx,
    plain_surface_ctx,
)
from src.domains.agents.drafts.card_html import CardSurface, card_surface, to_html_card
from src.domains.agents.drafts.card_spec import Block, CardSpec, Note, Row
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import render_confirmation_card

pytestmark = pytest.mark.unit

EMAIL = {
    "to": "paul@example.org",
    "subject": "Réunion <lundi> & co",
    "body": "Bonjour Paul,\n\nOn se voit lundi ?",
}


def _spec() -> CardSpec:
    return CardSpec(
        emoji="📧",
        title="Réunion <lundi> & co",
        separator=" : ",
        lines=(
            Row("Destinataire", "paul@example.org", key="to"),
            Note("a | b"),
            Block("Message", "Bonjour Paul,\n\nOn se voit lundi ?"),
        ),
    )


class TestTheHtmlForm:
    def test_it_is_a_card_headed_by_the_emoji_and_the_title(self) -> None:
        html = to_html_card(_spec())
        assert html.startswith('<div class="lia-card lia-draft">')
        assert 'class="lia-card-top__title"' in html
        assert "Réunion &lt;lundi&gt; &amp; co" in html
        assert "📧" in html

    def test_a_row_is_an_iconed_detail_row(self) -> None:
        html = to_html_card(_spec())
        assert (
            '<div class="lia-d-row"><span class="material-symbols-outlined">person</span>'
            "<span><strong>Destinataire</strong> : paul@example.org</span></div>"
        ) in html

    def test_a_note_is_a_row_without_a_label(self) -> None:
        html = to_html_card(_spec())
        assert '<div class="lia-d-row"><span>a | b</span></div>' in html

    def test_a_block_is_a_section_over_a_description_block(self) -> None:
        html = to_html_card(_spec())
        assert 'class="lia-sec__label"' in html and "Message" in html
        assert (
            '<div class="lia-desc-block lia-desc-block--no-border">'
            "Bonjour Paul,<br><br>On se voit lundi ?</div>"
        ) in html

    def test_every_value_is_escaped(self) -> None:
        spec = CardSpec("📧", "t", " : ", (Row("À", "<b>x</b>", key="to"),))
        html = to_html_card(spec)
        assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html

    def test_the_card_is_one_line(self) -> None:
        assert "\n" not in to_html_card(_spec())

    def test_a_row_key_without_an_icon_still_draws(self) -> None:
        spec = CardSpec("📧", "t", " : ", (Row("Chose", "v", key="no_such_key"),))
        html = to_html_card(spec)
        assert "<strong>Chose</strong> : v" in html


class TestTheSurface:
    def test_the_chat_gets_the_card(self) -> None:
        assert card_surface() is CardSurface.CHAT
        html = render_confirmation_card(
            Draft(type=DraftType.EMAIL, content=EMAIL),
            "fr",
            "Europe/Paris",
            surface=CardSurface.CHAT,
        )
        assert html.startswith('<div class="lia-card lia-draft">')

    def test_a_ticket_run_gets_the_markdown(self) -> None:
        origin = RunOrigin(kind="workboard", ticket_id="t-1", run_id="r-1")
        token = out_of_turn_origin_ctx.set(origin)
        try:
            assert card_surface() is CardSurface.PLAIN
            card = render_confirmation_card(
                Draft(type=DraftType.EMAIL, content=EMAIL),
                "fr",
                "Europe/Paris",
                surface=card_surface(),
            )
        finally:
            out_of_turn_origin_ctx.reset(token)
        assert card.startswith("📧 **Réunion <lundi> & co**\n\n- **Destinataire**")

    def test_a_channel_run_gets_the_markdown(self) -> None:
        """Telegram strips every card from the first ``<div`` (channels formatter):
        a card there would truncate the question and empty the result."""
        token = plain_surface_ctx.set(True)
        try:
            assert card_surface() is CardSurface.PLAIN
        finally:
            plain_surface_ctx.reset(token)
        assert card_surface() is CardSurface.CHAT

    def test_a_markdown_display_mode_gets_the_markdown(self) -> None:
        """A person who chose the markdown rendering asked for text."""
        with patch(
            "src.domains.agents.drafts.card_html.runtime_display_mode",
            return_value=RESPONSE_DISPLAY_MODE_MARKDOWN,
        ):
            assert card_surface() is CardSurface.PLAIN
        with patch(
            "src.domains.agents.drafts.card_html.runtime_display_mode",
            return_value=RESPONSE_DISPLAY_MODE_HTML,
        ):
            assert card_surface() is CardSurface.CHAT

    def test_the_default_is_the_markdown(self) -> None:
        card = render_confirmation_card(Draft(type=DraftType.EMAIL, content=EMAIL), "fr")
        assert card.startswith("📧 **")
