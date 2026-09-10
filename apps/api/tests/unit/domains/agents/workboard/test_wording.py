"""A ticket is « 工单 » in Chinese, never « 任务 » — the task domain's noun.

The two nouns met in one prompt block (the summary headings), in the effect
register and in the notifications: a reader could not tell a workboard ticket
from a provider to-do. One word per thing, in every table that names it.
"""

from __future__ import annotations

import pytest

from src.core.i18n_drafts import DRAFT_RESULT_NOUNS, DRAFT_SUCCESS_MESSAGES
from src.core.i18n_effects import EFFECT_LABELS
from src.core.i18n_proactive import ProactiveMessages
from src.core.i18n_treatments import TREATMENT_DOMAIN_LABELS
from src.core.i18n_workboard import WorkboardMessages
from src.domains.agents.formatters.text_summary import DOMAIN_LABELS

pytestmark = pytest.mark.unit

ZH = "zh-CN"
TASK_NOUN = "任务"
TICKET_NOUN = "工单"


def _wordings() -> list[tuple[str, str]]:
    return [
        ("draft noun", DRAFT_RESULT_NOUNS[ZH]["ticket"]["singular"]),
        ("draft success", DRAFT_SUCCESS_MESSAGES[ZH]["ticket_delete"]),
        ("treatment domain", TREATMENT_DOMAIN_LABELS[ZH]["ticket"]),
        ("summary heading", DOMAIN_LABELS[ZH]["tickets"]),
        ("notification title", ProactiveMessages.notification_title("workboard", ZH)),
        ("notification assigned", ProactiveMessages.workboard_body("assigned", "T", ZH)),
        ("notification run failed", ProactiveMessages.workboard_body("run_failed", "T", ZH)),
        ("intent sentence", WorkboardMessages.finish_in_chat("T", "id", ZH)),
        *[
            (key, EFFECT_LABELS[ZH][key])
            for key in (
                "effects.labels.create_ticket_tool",
                "effects.labels.update_ticket_tool",
                "effects.labels.comment_ticket_tool",
                "effects.labels.draft.ticket_delete",
            )
        ],
    ]


@pytest.mark.parametrize(("where", "wording"), _wordings(), ids=[w for w, _ in _wordings()])
def test_a_ticket_is_a_work_ticket_never_a_task(where: str, wording: str) -> None:
    assert TICKET_NOUN in wording, where
    assert TASK_NOUN not in wording, where


def test_the_task_domain_keeps_its_own_noun() -> None:
    """The harmonisation must not have touched the to-do domain."""
    assert DRAFT_RESULT_NOUNS[ZH]["task"]["singular"] == TASK_NOUN
    assert DOMAIN_LABELS[ZH]["tasks"] == TASK_NOUN


class TestTheFrenchNameIsNotTheDashboard:
    """« Tableau de bord » is the app's OWN dashboard, at `/dashboard`.

    Every other language named a work board (`Aufgabenboard`, `Tablero de
    trabajo`, `Bacheca`, `工单板`); French alone named the instrument panel, so
    a reader of « Traitements » saw the register call the workboard by the name
    of a different screen. The frontend already treats « Workboard » as a proper
    noun in French (`locales/fr/translation.json`), and the register follows it.
    """

    def test_it_does_not_borrow_the_dashboards_name(self) -> None:
        assert "Tableau de bord" not in TREATMENT_DOMAIN_LABELS["fr"]["ticket"]

    def test_every_language_names_the_board(self) -> None:
        for language in ("fr", "en", "de", "es", "it", "zh-CN"):
            assert TREATMENT_DOMAIN_LABELS[language]["ticket"].strip()
