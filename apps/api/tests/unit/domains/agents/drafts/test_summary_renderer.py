"""Every draft has a NAME, in the reader's language (ADR-276, lot 13).

The summary titles a HITL confirmation. The cascade this replaced ended in
``f"Draft ({type.value})"``, and measured on 2026-09-09 **nine of the
twenty-six types reached it**: someone asked to approve a ticket deletion read
``📄 Brouillon créé: Draft (ticket_delete)``.

Three orders of assertion, because one alone would not have caught it:

- the dispatch table is COMPLETE, and the boot assert says so (ADR-085);
- no type, in any of the six languages, renders the fallback — that is the
  property the old code broke, and it is checked over the whole product;
- the nine that were missing are pinned by their exact sentence, so a
  translation cannot silently become an English one.
"""

from __future__ import annotations

import pytest

from src.core.i18n import SUPPORTED_LANGUAGES
from src.domains.agents.drafts.models import Draft, DraftType
from src.domains.agents.drafts.summary_renderer import (
    _SUMMARY_RENDERERS,
    assert_summary_renderer_completeness,
    render_summary,
)

pytestmark = pytest.mark.unit


#: One plausible content per type: what the tools actually store.
CONTENTS: dict[DraftType, dict[str, object]] = {
    DraftType.EMAIL: {"to": "alice@example.com", "subject": "Point d'étape"},
    DraftType.EMAIL_REPLY: {"to": "alice@example.com", "subject": "Re: Devis"},
    DraftType.EMAIL_FORWARD: {"to": "bob@example.com", "subject": "Fwd: Contrat"},
    DraftType.EMAIL_DELETE: {"subject": "Newsletter"},
    DraftType.EVENT: {"summary": "Réunion", "start_datetime": "2026-06-01T09:00:00+02:00"},
    DraftType.EVENT_UPDATE: {"current_event": {"summary": "Réunion"}},
    DraftType.EVENT_DELETE: {"event": {"summary": "Dentiste"}},
    DraftType.CONTACT: {"name": "Marie Dupont"},
    DraftType.CONTACT_UPDATE: {"current_contact": {"names": [{"displayName": "Marie"}]}},
    DraftType.CONTACT_DELETE: {"contact": {"names": [{"displayName": "Marie"}]}},
    DraftType.TASK: {"title": "Préparer le rapport"},
    DraftType.TASK_UPDATE: {"current_task": {"title": "Rapport"}},
    DraftType.TASK_DELETE: {"title": "Ancienne tâche"},
    DraftType.FILE_DELETE: {"file": {"name": "rapport.pdf"}},
    DraftType.LABEL_DELETE: {"label_name": "pro/archive"},
    DraftType.REMINDER_DELETE: {"content": "Appeler le médecin"},
    DraftType.PHONE_CALL: {"callee_name": "Paul", "objective": "Sa disponibilité"},
    DraftType.SCHEDULED_ACTION: {"title": "Revue de presse"},
    DraftType.DEVOPS_TASK: {"server": "prod-rpi5", "task": "Redémarre le conteneur"},
    DraftType.PEER_MESSAGE: {"recipient_name": "Marie Dupont", "message": "Comment va-t-il ?"},
    DraftType.VACATION_RESPONDER: {"enable": True, "subject": "Absent"},
    DraftType.EMAIL_FILTER: {"criteria": {"from": "news@x.com"}},
    DraftType.TOOL_CALL: {"tool_label": "era: cancel subscription"},
    DraftType.SPREADSHEET_WRITE: {"spreadsheet_title": "Budget", "sheet_name": "Dépenses"},
    DraftType.DOCUMENT_APPEND: {"document_title": "Compte-rendu"},
    DraftType.TICKET_DELETE: {"title": "Réserver la salle"},
}


def _summary(draft_type: DraftType, language: str = "fr") -> str:
    return render_summary(Draft(type=draft_type, content=dict(CONTENTS[draft_type])), language)


class TestTheTableIsComplete:
    @pytest.mark.parametrize("draft_type", list(DraftType))
    def test_every_draft_type_has_a_renderer(self, draft_type: DraftType) -> None:
        assert draft_type in _SUMMARY_RENDERERS, f"DraftType.{draft_type.name} has no summary"

    def test_the_boot_assert_passes_on_the_real_table(self) -> None:
        assert_summary_renderer_completeness()

    def test_the_boot_assert_names_what_is_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        incomplete = dict(_SUMMARY_RENDERERS)
        incomplete.pop(DraftType.TICKET_DELETE)
        monkeypatch.setattr(
            "src.domains.agents.drafts.summary_renderer._SUMMARY_RENDERERS", incomplete
        )

        with pytest.raises(AssertionError, match="ticket_delete"):
            assert_summary_renderer_completeness()

    def test_the_case_table_here_covers_every_type(self) -> None:
        """A new type with no content below would be tested against nothing."""
        assert set(CONTENTS) == set(DraftType)


class TestNobodyReadsAnEnumValue:
    @pytest.mark.parametrize("draft_type", list(DraftType))
    @pytest.mark.parametrize("language", sorted(SUPPORTED_LANGUAGES))
    def test_no_type_in_no_language_falls_back(self, draft_type: DraftType, language: str) -> None:
        summary = _summary(draft_type, language)

        assert summary, f"{draft_type.value} has an empty summary in {language}"
        assert "Draft (" not in summary, f"{draft_type.value} still falls back in {language}"
        # The label key itself surfaces when a language is missing the entry:
        # ``get_draft_summary_label`` returns the key as its own last resort.
        assert summary != draft_type.value

    def test_an_unregistered_type_still_answers_something(self) -> None:
        """Defense in depth: the boot assert makes this unreachable."""

        class _Later(str):
            value = "something"

        draft = Draft(type=DraftType.EMAIL, content={})
        draft.type = _Later("something")  # type: ignore[assignment]
        assert render_summary(draft, "fr") == "Draft (something)"


class TestTheNineThatWereMissing:
    """Pinned sentences: a translation must not quietly become English.

    The French ones carry ``\\u00a0`` before their colon — the unbreakable
    space French typography requires, which the labels really contain.
    """

    @pytest.mark.parametrize(
        ("draft_type", "expected_fr", "expected_en"),
        [
            (
                DraftType.REMINDER_DELETE,
                "Suppression rappel\u00a0: Appeler le médecin",
                "Delete reminder: Appeler le médecin",
            ),
            (
                DraftType.TICKET_DELETE,
                "Suppression ticket\u00a0: Réserver la salle",
                "Delete ticket: Réserver la salle",
            ),
            (
                DraftType.SCHEDULED_ACTION,
                "Automatisation\u00a0: Revue de presse",
                "Automation: Revue de presse",
            ),
            (DraftType.PEER_MESSAGE, "Message à Marie Dupont", "Message to Marie Dupont"),
            (
                DraftType.VACATION_RESPONDER,
                "Réponse automatique\u00a0: Absent",
                "Auto-reply: Absent",
            ),
            (DraftType.EMAIL_FILTER, "Filtre email\u00a0: news@x.com", "Email filter: news@x.com"),
            (
                DraftType.TOOL_CALL,
                "Action\u00a0: era: cancel subscription",
                "Action: era: cancel subscription",
            ),
            (
                DraftType.SPREADSHEET_WRITE,
                "Écriture dans Budget (Dépenses)",
                "Write to Budget (Dépenses)",
            ),
            (DraftType.DOCUMENT_APPEND, "Ajout dans Compte-rendu", "Append to Compte-rendu"),
        ],
    )
    def test_the_sentence_is_the_one_written(
        self, draft_type: DraftType, expected_fr: str, expected_en: str
    ) -> None:
        assert _summary(draft_type, "fr") == expected_fr
        assert _summary(draft_type, "en") == expected_en

    def test_switching_the_responder_off_names_no_subject(self) -> None:
        """« Absence: (none) » would say less than the sentence it replaced."""
        draft = Draft(type=DraftType.VACATION_RESPONDER, content={"enable": False})

        assert render_summary(draft, "fr") == "Désactivation de la réponse automatique"


class TestValuesAreReadable:
    def test_a_recipient_list_is_joined(self) -> None:
        """``['a@x', 'b@x']`` is a Python spelling, on a card read by a person."""
        draft = Draft(
            type=DraftType.EMAIL,
            content={"to": ["paul@example.org", "marie@example.org"], "subject": "Lundi"},
        )

        assert render_summary(draft, "fr") == "Email à paul@example.org, marie@example.org"

    def test_a_missing_field_reads_as_the_shared_unknown(self) -> None:
        assert render_summary(Draft(type=DraftType.TASK, content={}), "en") == "Task: ?"

    def test_an_event_with_no_time_says_so_rather_than_nothing(self) -> None:
        draft = Draft(type=DraftType.EVENT, content={"summary": "Standup"})

        assert render_summary(draft, "en") == "Event: Standup on ?"

    @pytest.mark.parametrize(
        ("draft_type", "content"),
        [
            (DraftType.EVENT_DELETE, {"event": None}),
            (DraftType.EVENT_UPDATE, {"current_event": None}),
            (DraftType.CONTACT_DELETE, {"contact": None}),
            (DraftType.CONTACT_DELETE, {"contact": {"names": None}}),
            (DraftType.CONTACT_DELETE, {"contact": {"names": ["Marie"]}}),
            (DraftType.CONTACT_UPDATE, {"current_contact": None}),
            (DraftType.TASK_UPDATE, {"current_task": None}),
            (DraftType.FILE_DELETE, {"file": None}),
        ],
    )
    def test_a_null_where_a_dict_was_expected_names_the_unknown(
        self, draft_type: DraftType, content: dict[str, object]
    ) -> None:
        """A key that EXISTS and holds null is not a missing key: ``get(k, {})``
        answers None there, and the read behind it would raise inside a
        confirmation nobody could then read."""
        assert "?" in render_summary(Draft(type=draft_type, content=content), "en")
