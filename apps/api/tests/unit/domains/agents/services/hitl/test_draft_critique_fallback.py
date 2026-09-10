"""The critique the user reads when the LLM did not answer (lot 14 shape).

`_generate_fallback_critique` is the last thing standing between a user and a
side effect: it is what the confirmation shows when the critique LLM fails,
times out, or is disabled. Since lot 14 it is the SAME card the streaming path
opens with — rendered by `render_confirmation_card`, the one author of the
form — followed by a localized question: the deletion question under its
irreversibility warning for a destructive draft, the generic critique sentence
for every other one.

That closes the class of defect this file used to guard by hand: the fallback
carried its own ladder of per-type branches, kept in step with a THIRD copy of
the card vocabulary (`_DRAFT_SUMMARIES`), and `label_delete` once fell through
it. A card that comes from the renderer's dispatch table — completeness
asserted at boot — cannot forget a type.

Everything here is pure: no LLM, no DB, real i18n tables.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.i18n_hitl import HitlMessages
from src.domains.agents.drafts.display import DRAFT_DISPLAY_REGISTRY
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.preview_renderer import render_confirmation_card
from src.domains.agents.services.hitl.interactions.draft_critique import (
    CARD_SEPARATOR,
    DraftCritiqueInteraction,
)

pytestmark = pytest.mark.unit

PARIS = "Europe/Paris"
LANGUAGES = ("fr", "en", "es", "de", "it", "zh-CN")


@pytest.fixture
def interaction() -> DraftCritiqueInteraction:
    # The question generator is only used by the streaming path.
    return DraftCritiqueInteraction(question_generator=None)  # type: ignore[arg-type]


def critique(
    interaction: DraftCritiqueInteraction,
    draft_type: str,
    content: dict[str, Any],
    language: str = "fr",
) -> str:
    return interaction._generate_fallback_critique(draft_type, content, language, PARIS)


class TestTheCardIsTheStreamsCard:
    def test_it_opens_with_the_renderer_card_and_the_rule(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        content = {"to": "jean@example.com", "subject": "Point projet", "body": "Bonjour Jean,"}

        text = critique(interaction, "email", content)

        card = render_confirmation_card(Draft(type=DraftType.EMAIL, content=content), "fr", PARIS)
        assert text.startswith(card + CARD_SEPARATOR)

    def test_an_email_names_recipient_and_subject_and_shows_the_body(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "email",
            {"to": "jean@example.com", "subject": "Point projet", "body": "Bonjour Jean,"},
        )

        assert "jean@example.com" in text
        assert "Point projet" in text
        assert "Bonjour Jean," in text

    def test_an_event_renders_its_start_in_the_user_timezone(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "event",
            {
                "summary": "Comité",
                "start_datetime": "2026-07-20T08:00:00Z",
                "end_datetime": "2026-07-20T09:00:00Z",
                "location": "Salle 3",
                "attendees": ["jean@example.com"],
            },
        )

        assert "Comité" in text
        assert "Salle 3" in text
        assert "jean@example.com" in text
        # 08:00 UTC is 10:00 in Paris — a raw UTC hour would mislead the user.
        assert "10:00" in text
        assert "2026-07-20T08:00:00Z" not in text

    def test_a_label_deletion_names_the_label_and_its_sublabels(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        # The regression this file was born from: a Gmail label deletion once
        # fell through to a sentence that named nothing.
        text = critique(
            interaction,
            "label_delete",
            {"label_name": "pro", "sublabels": [{"name": "pro/capge"}, {"name": "pro/interne"}]},
        )

        assert "pro/capge" in text
        assert "pro/interne" in text

    def test_a_missing_field_degrades_to_a_placeholder_not_a_crash(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "email", {})

        assert "?" in text


class TestTheQuestion:
    def test_a_deletion_warns_and_asks_its_own_question(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "file_delete", {"file": {"name": "Budget 2026.xlsx"}})
        ui = HitlMessages.get_destructive_confirm_translations("fr")

        assert ui["default_warning"] in text
        assert text.rstrip().endswith(ui["confirm_question"])

    def test_a_creation_asks_the_generic_question(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "task", {"title": "Relancer le devis"})

        assert "Cette action est irréversible" not in text
        assert text.rstrip().endswith("confirmer, modifier ou annuler ?")

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_every_language_ends_on_a_question(
        self, interaction: DraftCritiqueInteraction, language: str
    ) -> None:
        for draft_type in ("email", "event_delete"):
            text = critique(interaction, draft_type, {"subject": "x", "event": {}}, language)
            assert text.rstrip().endswith(("?", "？")), (draft_type, language, text[-40:])


class TestEveryTypeAndTheUnknown:
    @pytest.mark.parametrize("draft_type", list(DraftType))
    def test_every_registered_type_gets_the_card_and_a_question(
        self, interaction: DraftCritiqueInteraction, draft_type: DraftType
    ) -> None:
        text = critique(interaction, draft_type.value, {})

        assert text.startswith(DRAFT_DISPLAY_REGISTRY[draft_type].emoji)
        assert CARD_SEPARATOR in text
        assert text.rstrip().endswith("?")

    def test_an_unknown_draft_type_still_produces_a_question(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "quantum_teleport", {"anything": 1})

        assert text.strip()
        assert CARD_SEPARATOR not in text
