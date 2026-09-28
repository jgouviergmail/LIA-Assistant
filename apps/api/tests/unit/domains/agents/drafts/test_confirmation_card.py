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

from src.core.i18n_drafts import format_hitl_item_preview
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

    @pytest.mark.parametrize("space", [chr(0xA0), chr(0x3000)], ids=["nbsp", "ideographic"])
    def test_the_title_is_the_batch_row_s_label(self, space: str) -> None:
        """The chat, the ticket and a FOR_EACH list name a draft identically:
        the title folds as the row's label does, the typography's spaces kept —
        the row kept them and the title flattened them."""
        content: dict[str, object] = {"content": f"Rendez-vous{space}: médecin\nsuivi"}
        draft = Draft(type=DraftType.REMINDER_DELETE, content=content)

        title = card_title(draft, "fr")
        row = format_hitl_item_preview(draft.type.value, content, language="fr")

        assert title == f"Rendez-vous{space}: médecin suivi"
        assert row is not None and title in row

    @pytest.mark.parametrize(
        "blank", [chr(0xA0) * 3, "\n\n", "   "], ids=["no_break_spaces", "line_breaks", "spaces"]
    )
    def test_a_title_that_says_nothing_is_no_title(self, blank: str) -> None:
        """Blank is no name, nor a value to quote: the card was headed ``****``,
        then by a summary quoting the blank — and a title of line breaks broke
        the bold header across three lines that never closed."""
        draft = Draft(type=DraftType.TASK, content={"title": blank})

        untitled = render_summary(Draft(type=DraftType.TASK, content={}), "fr")
        assert card_title(draft, "fr") == untitled
        assert render_confirmation_card(draft, "fr").splitlines()[0].endswith("**")

    def test_a_summary_is_one_line(self) -> None:
        """A title the summary quotes is folded: the e-mail case quoted no subject."""
        summary = render_summary(Draft(type=DraftType.TASK, content={"title": "a\nb"}), "en")

        assert "\n" not in summary
        assert "a b" in summary

    def test_an_absent_value_reads_as_unknown(self) -> None:
        """A renderer may hand the sentence ``None``: it reads « ? », never « None »."""
        draft = Draft(type=DraftType.EVENT_DELETE, content={"event": {"summary": None}})

        summary = render_summary(draft, "en")

        assert "?" in summary
        assert "None" not in summary

    def test_a_title_of_nothing_visible_is_spelled(self) -> None:
        """A title of zero-width spaces headed the card with nothing."""
        draft = Draft(type=DraftType.TASK, content={"title": chr(0x200B) * 3})

        header = render_confirmation_card(draft, "en").splitlines()[0]

        assert header.endswith("**⟨U+200B×3⟩**")

    def test_a_reordering_control_is_spelled_in_the_title_and_the_summary(self) -> None:
        """A tool name ending in an override read backwards in the header."""
        content = {"tool_name": "t", "tool_label": "Send" + chr(0x202E) + "live"}
        draft = Draft(type=DraftType.TOOL_CALL, content=content)

        assert "Send⟨U+202E⟩live" in render_confirmation_card(draft, "en").splitlines()[0]
        assert "Send⟨U+202E⟩live" in render_summary(draft, "en")

    def test_a_title_is_drawn_as_itself(self) -> None:
        """Bold around « *urgent* » drew italics, around « [x](y) » a link."""
        draft = Draft(type=DraftType.TASK, content={"title": "*urgent* [x](https://e.example)"})

        header = render_confirmation_card(draft, "en").splitlines()[0]

        assert header.endswith("**&#42;urgent&#42; &#91;x&#93;(https&#58;//e.example)**")

    def test_a_blank_field_gives_way_to_the_next_one(self) -> None:
        """The registry's chain goes on past a field that names nothing — for
        the card and the batch row alike, read through ONE ``item_label``."""
        content: dict[str, object] = {"summary": chr(0x3000), "event": {"summary": "Réunion"}}
        draft = Draft(type=DraftType.EVENT_DELETE, content=content)

        row = format_hitl_item_preview(draft.type.value, content, language="fr")

        assert card_title(draft, "fr") == "Réunion"
        assert row is not None and "Réunion" in row

    def test_an_indented_title_stays_bold(self) -> None:
        """A space touching ``**`` is no emphasis: the header drew its markers."""
        draft = Draft(type=DraftType.TASK, content={"title": chr(0x3000) * 2 + "给妈妈打电话"})

        header = render_confirmation_card(draft, "zh-CN").splitlines()[0]

        assert "**给妈妈打电话**" in header

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

        assert "- **An**: marie.dupont&#64;example.com" in card
