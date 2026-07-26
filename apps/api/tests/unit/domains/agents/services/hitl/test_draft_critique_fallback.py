"""The draft critique the user reads when the LLM did not answer.

`_generate_fallback_critique` is the last thing standing between a user and a
side effect: it is what the confirmation card shows when the critique LLM
fails, times out, or is disabled. If a branch is missing, the user is asked to
approve *something* — a deletion, an email, an event — with a generic sentence
that names nothing.

That is exactly what happened to `label_delete`: `_DRAFT_SUMMARIES` carried its
template in the six languages, but the ladder had no branch for it, so a Gmail
label deletion fell through to the generic fallback. The completeness guard at
the bottom of this file makes that class of omission impossible to reintroduce.

Everything here is pure: no LLM, no DB, real i18n tables.
"""

import re
from typing import Any

import pytest

from src.core.i18n_hitl import HitlMessages
from src.domains.agents.services.hitl.interactions.draft_critique import (
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


class TestEmailDrafts:
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

    def test_a_reply_names_the_original_sender(self, interaction: DraftCritiqueInteraction) -> None:
        text = critique(
            interaction,
            "email_reply",
            {"original_from": "sophie@example.com", "subject": "Re: Devis", "body": "OK pour moi"},
        )

        assert "sophie@example.com" in text
        assert "OK pour moi" in text

    def test_a_forward_names_the_new_recipient(self, interaction: DraftCritiqueInteraction) -> None:
        text = critique(
            interaction,
            "email_forward",
            {"to": "equipe@example.com", "subject": "Fwd: Devis"},
        )

        assert "equipe@example.com" in text

    def test_a_deletion_names_the_subject_and_the_sender(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "email_delete",
            {"subject": "Newsletter", "from": "news@example.com", "date": "2026-07-20T09:00:00Z"},
        )

        assert "Newsletter" in text
        assert "news@example.com" in text

    def test_a_missing_field_degrades_to_a_placeholder_not_a_crash(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "email", {})

        assert "?" in text


class TestEventDrafts:
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
                "attendees": "jean@example.com",
            },
        )

        assert "Comité" in text
        assert "Salle 3" in text
        assert "jean@example.com" in text
        # 08:00 UTC is 10:00 in Paris — a raw UTC hour would mislead the user.
        assert "10:00" in text
        assert "2026-07-20T08:00:00Z" not in text

    def test_an_event_without_optional_fields_still_summarises(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "event", {"summary": "Point", "start_datetime": "demain"})

        assert "Point" in text

    def test_an_update_falls_back_to_the_current_event_title(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "event_update",
            {
                "current_event": {"summary": "Ancien titre"},
                "start_datetime": "2026-07-20T08:00:00Z",
            },
        )

        assert "Ancien titre" in text
        assert "10:00" in text

    def test_an_update_prefers_the_new_title_when_given(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "event_update",
            {"summary": "Nouveau titre", "current_event": {"summary": "Ancien titre"}},
        )

        assert "Nouveau titre" in text
        assert "Ancien titre" not in text

    def test_a_deletion_reads_the_start_out_of_the_google_shape(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "event_delete",
            {
                "current_event": {
                    "summary": "Réunion",
                    "start": {"dateTime": "2026-07-20T08:00:00Z"},
                }
            },
        )

        assert "Réunion" in text
        assert "10:00" in text

    def test_a_deletion_accepts_the_flat_start_datetime_shape(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "event_delete",
            {"current_event": {"summary": "Réunion", "start_datetime": "2026-07-20T08:00:00Z"}},
        )

        assert "10:00" in text

    def test_an_all_day_deletion_does_not_invent_a_time(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "event_delete",
            {"current_event": {"summary": "Congé", "start": {"date": "2026-07-20"}}},
        )

        assert "Congé" in text


class TestContactDrafts:
    def test_a_creation_lists_every_provided_field(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "contact",
            {
                "name": "Ada Lovelace",
                "email": "ada@example.com",
                "phone": "+33600000000",
                "organization": "Analytical Engines",
            },
        )

        for expected in ("Ada Lovelace", "ada@example.com", "+33600000000", "Analytical Engines"):
            assert expected in text

    def test_an_update_reads_the_display_name_of_the_current_contact(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "contact_update",
            {"current_contact": {"names": [{"displayName": "Ada Lovelace"}]}},
        )

        assert "Ada Lovelace" in text

    def test_an_update_prefers_an_explicit_name(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "contact_update",
            {"name": "Grace Hopper", "current_contact": {"names": [{"displayName": "Ada"}]}},
        )

        assert "Grace Hopper" in text

    def test_a_contact_with_no_names_degrades_to_a_placeholder(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "contact_delete", {"current_contact": {"names": []}})

        assert "?" in text

    def test_a_deletion_names_the_contact(self, interaction: DraftCritiqueInteraction) -> None:
        text = critique(
            interaction,
            "contact_delete",
            {"current_contact": {"names": [{"displayName": "Ada Lovelace"}]}},
        )

        assert "Ada Lovelace" in text


class TestTaskDrafts:
    def test_a_creation_shows_title_due_date_and_notes(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "task",
            {"title": "Relancer le devis", "due": "2026-07-20T00:00:00Z", "notes": "avant midi"},
        )

        assert "Relancer le devis" in text
        assert "avant midi" in text
        assert "2026-07-20T00:00:00Z" not in text

    def test_an_update_falls_back_to_the_current_task_title(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "task_update", {"current_task": {"title": "Titre existant"}})

        assert "Titre existant" in text

    def test_a_deletion_names_the_task(self, interaction: DraftCritiqueInteraction) -> None:
        assert "Vieille tâche" in critique(interaction, "task_delete", {"title": "Vieille tâche"})


class TestDeletionDrafts:
    def test_a_file_deletion_names_the_file(self, interaction: DraftCritiqueInteraction) -> None:
        text = critique(interaction, "file_delete", {"file": {"name": "Budget 2026.xlsx"}})

        assert "Budget 2026.xlsx" in text

    def test_a_label_deletion_names_the_label(self, interaction: DraftCritiqueInteraction) -> None:
        # The regression: this used to fall through to the generic fallback,
        # so the user confirmed a deletion without knowing what was deleted.
        text = critique(
            interaction, "label_delete", {"label_id": "Label_9", "label_name": "pro/capge/2024"}
        )

        assert "pro/capge/2024" in text

    def test_a_label_deletion_warns_about_the_sublabels_it_takes_with_it(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "label_delete",
            {
                "label_name": "pro",
                "sublabels": [{"name": "pro/capge"}, {"name": "pro/interne"}],
            },
        )

        assert "pro/capge" in text
        assert "pro/interne" in text

    def test_a_label_deletion_tolerates_a_malformed_sublabel_list(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(
            interaction,
            "label_delete",
            {"label_name": "pro", "sublabels": ["not-a-dict", {}, {"name": "pro/ok"}]},
        )

        assert "pro/ok" in text


class TestUnknownAndShape:
    def test_an_unknown_draft_type_still_produces_a_question(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        text = critique(interaction, "quantum_teleport", {"anything": 1})

        assert text.strip()

    def test_every_critique_ends_with_the_available_actions(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        actions = HitlMessages.format_draft_critique_actions("fr", include_descriptions=False)
        text = critique(interaction, "email", {"to": "a@b.c", "subject": "S"})

        assert text.endswith(actions)
        assert "\n---\n" in text

    def test_the_summary_carries_the_draft_type_emoji(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        emoji = HitlMessages.get_draft_emoji("email")
        text = critique(interaction, "email", {"to": "a@b.c", "subject": "S"})

        assert text.startswith(emoji)

    def test_no_template_placeholder_leaks_into_the_user_text(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        # An unfilled "{name}" reaching the card is a broken sentence.
        for draft_type, content in (
            ("email", {"to": "a@b.c", "subject": "S"}),
            ("event", {"summary": "S", "start_datetime": "2026-07-20T08:00:00Z"}),
            ("label_delete", {"label_name": "pro"}),
            ("file_delete", {"file": {"name": "f.txt"}}),
        ):
            text = critique(interaction, draft_type, content)
            assert not re.search(r"\{[a-z_]+\}", text), draft_type


class TestEveryLanguage:
    @pytest.mark.parametrize("language", LANGUAGES)
    def test_a_label_deletion_is_summarised_in_every_language(
        self, interaction: DraftCritiqueInteraction, language: str
    ) -> None:
        text = critique(interaction, "label_delete", {"label_name": "pro/capge"}, language=language)
        generic = critique(interaction, "__no_such_type__", {}, language=language)

        assert "pro/capge" in text
        assert text != generic

    @pytest.mark.parametrize("language", LANGUAGES)
    def test_an_email_is_summarised_in_every_language(
        self, interaction: DraftCritiqueInteraction, language: str
    ) -> None:
        text = critique(
            interaction, "email", {"to": "a@b.c", "subject": "Sujet"}, language=language
        )

        assert "a@b.c" in text
        assert "Sujet" in text


class TestLadderCompleteness:
    """Every translated draft type must have a branch — no silent generic."""

    def test_each_translated_draft_type_produces_its_own_summary(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        from src.core.i18n_hitl import _DRAFT_SUMMARIES

        generic = critique(interaction, "__no_such_type__", {})
        orphans = [
            draft_type
            for draft_type in _DRAFT_SUMMARIES
            if critique(interaction, draft_type, {}) == generic
        ]

        assert orphans == [], (
            "these draft types have a translated summary that the fallback "
            f"critique never uses: {orphans}"
        )

    def test_the_guard_would_catch_a_missing_branch(
        self, interaction: DraftCritiqueInteraction
    ) -> None:
        # Oracle: an unknown type IS the generic text the guard compares against.
        generic = critique(interaction, "__no_such_type__", {})

        assert critique(interaction, "__another_unknown__", {}) == generic
        assert critique(interaction, "email", {}) != generic
