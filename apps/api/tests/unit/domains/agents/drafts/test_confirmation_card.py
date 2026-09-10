"""The confirmation card has ONE author, and it is the renderer (ADR-276, lot 14).

Measured on 2026-09-09, on a real e-mail confirmation: the card in the chat
was written by the MODEL under a prompt describing it, so its shape was
whatever the model produced that day — fields separated by blank lines that
became paragraphs, a `---` that came out as three literal dashes — and the
ticket comment appended the renderer's own preview to it, so the e-mail was
shown twice. The card now has an author: `render_confirmation_card`, the same
renderer that already owned the preview, and the model writes the QUESTION.
"""

from __future__ import annotations

import pytest

from src.domains.agents.drafts.display import DRAFT_DISPLAY_REGISTRY
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import (
    card_title,
    render_confirmation_card,
    render_detailed_preview,
)
from src.domains.agents.drafts.summary_renderer import render_summary

pytestmark = pytest.mark.unit

EMAIL = {
    "to": "marie.dupont@example.com",
    "subject": "Tout va bien",
    "body": "Bonjour,\n\nJe voulais juste te dire que tout va bien.\n\nÀ bientôt,",
}


class TestTheHeader:
    def test_the_email_is_titled_by_its_subject_under_its_emoji(self) -> None:
        card = render_confirmation_card(Draft(type=DraftType.EMAIL, content=EMAIL), "fr")

        assert card.startswith("📧 **Tout va bien**\n\n")

    def test_a_deletion_wears_the_bin_and_names_what_goes(self) -> None:
        draft = Draft(type=DraftType.FILE_DELETE, content={"file": {"name": "Budget 2026.xlsx"}})

        assert render_confirmation_card(draft, "fr").startswith("🗑️")
        assert "**Budget 2026.xlsx**" in render_confirmation_card(draft, "fr").splitlines()[0]

    @pytest.mark.parametrize("draft_type", list(DraftType))
    def test_every_type_has_a_title_even_with_nothing_to_read(self, draft_type: DraftType) -> None:
        """An empty content still yields a header: the summary is the fallback,
        never a lone « ? » above a card."""
        draft = Draft(type=draft_type, content={})

        title = card_title(draft, "fr")

        assert title
        assert title != "?"
        assert title == render_summary(draft, "fr")

    def test_the_title_reads_the_registry_field_first(self) -> None:
        # The display registry names the field a batch row is labelled by; the
        # card's header is the same fact, read from the same place.
        draft = Draft(
            type=DraftType.CONTACT_DELETE,
            content={"contact": {"names": [{"displayName": "Marie Dupont"}]}},
        )

        assert card_title(draft, "fr") == "Marie Dupont"

    def test_a_title_is_one_line(self) -> None:
        draft = Draft(type=DraftType.TASK, content={"title": "Relancer\n   le  devis"})

        assert card_title(draft, "fr") == "Relancer le devis"

    def test_every_emoji_comes_from_the_registry(self) -> None:
        for draft_type, config in DRAFT_DISPLAY_REGISTRY.items():
            card = render_confirmation_card(Draft(type=draft_type, content={}), "en")
            assert card.startswith(config.emoji), draft_type


class TestTheBody:
    def test_the_card_is_the_header_over_the_lot_13_preview(self) -> None:
        draft = Draft(type=DraftType.EMAIL, content=EMAIL)

        card = render_confirmation_card(draft, "fr", "Europe/Paris")

        header, _, body = card.partition("\n\n")
        assert header == "📧 **Tout va bien**"
        assert body == render_detailed_preview(draft, "fr", "Europe/Paris")

    def test_no_html_break_and_no_blank_edge(self) -> None:
        card = render_confirmation_card(Draft(type=DraftType.EMAIL, content=EMAIL), "fr")

        assert "<br/>" not in card
        assert card == card.strip()

    def test_an_email_with_nothing_filled_shows_no_empty_field(self) -> None:
        """« Destinataire : » over nothing is the lot-13 rule, applied to the
        two fields the e-mail renderer used to emit unconditionally."""
        card = render_confirmation_card(Draft(type=DraftType.EMAIL, content={}), "fr")

        assert "Destinataire" not in card
        assert "Objet" not in card
        assert card.splitlines()[0].startswith("📧 **")

    def test_the_language_reaches_the_labels(self) -> None:
        card = render_confirmation_card(Draft(type=DraftType.EMAIL, content=EMAIL), "de")

        assert "- **An**: marie.dupont@example.com" in card
