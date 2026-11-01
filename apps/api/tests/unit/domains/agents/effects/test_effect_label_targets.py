"""An effect's label names the shown item its call designates by id (ADR-367).

The incident of 2026-10-29 saved a reply draft to the wrong message, and the
register said only « a reply draft was saved »: the call named the message by
its provider id. Whoever runs the tools publishes the turn's registry; the
label, built at claim time, names the item as it was shown.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.i18n_effects import EFFECT_LABELS
from src.domains.agents.data_registry.models import RegistryItem, RegistryItemMeta, RegistryItemType
from src.domains.agents.effects.label_targets import item_title, publishing_label_items
from src.domains.agents.effects.labels import _NAMED_VARIANTS, build_effect_label

pytestmark = pytest.mark.unit

REGISTRY: dict[str, Any] = {
    "email_1": {
        "id": "email_1",
        "payload": {"id": "18f0", "message_id": "18f0", "subject": "Photos du week-end"},
        "meta": {"domain": "emails"},
    },
    "task_1": RegistryItem(
        id="task_1",
        type=RegistryItemType.TASK,
        payload={"id": "t-9", "task_id": "t-9", "title": "Appeler le garage"},
        meta=RegistryItemMeta(source="google_tasks", domain="tasks"),
    ),
    "draft_1": {
        "id": "draft_1",
        "payload": {"mailbox_draft_id": "r-1", "subject": "Devis cuisine", "to": "lea@example.com"},
        "meta": {"domain": "emails"},
    },
    "draft_2": {
        "id": "draft_2",
        "payload": {"mailbox_draft_id": "r-2", "subject": "Relance facture"},
        "meta": {"domain": "emails"},
    },
}


class TestTheItemAnIdDesignates:
    def test_a_published_item_is_named_by_its_own_words(self) -> None:
        with publishing_label_items(REGISTRY):
            assert item_title("18f0") == "Photos du week-end"
            assert item_title("t-9") == "Appeler le garage"  # a RegistryItem object too

    def test_nothing_is_named_outside_a_publishing_call(self) -> None:
        assert item_title("18f0") is None

    def test_an_unknown_or_malformed_id_names_nothing(self) -> None:
        with publishing_label_items(REGISTRY):
            assert item_title("unknown") is None
            assert item_title(None) is None
            assert item_title(42) is None


class TestTheLabelNamesTheTarget:
    def test_the_reply_draft_names_the_message_it_answers(self) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label("create_mailbox_reply_draft_tool", {"message_id": "18f0"})

        assert label == {
            "i18n_key": "effects.labels.create_mailbox_reply_draft_tool_named",
            "values": {"target": "Photos du week-end"},
        }

    def test_an_unknown_message_keeps_the_wording_that_names_nothing(self) -> None:
        label = build_effect_label("create_mailbox_reply_draft_tool", {"message_id": "18f0"})
        assert label == {"i18n_key": "effects.labels.create_mailbox_reply_draft_tool", "values": {}}

    def test_a_task_completed_by_id_is_named_by_its_title(self) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label("complete_task_tool", {"task_id": "t-9"})
        assert label["values"] == {"target": "Appeler le garage"}

    def test_without_the_item_the_id_is_shown_as_before(self) -> None:
        label = build_effect_label("complete_task_tool", {"task_id": "t-9"})
        assert label["values"] == {"target": "t-9"}

    def test_a_title_the_call_carries_wins(self) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label(
                "complete_task_tool", {"title": "Dentiste", "task_id": "t-9"}
            )
        assert label["values"] == {"target": "Dentiste"}


class TestEveryActOnAnItemNamesIt:
    """Lot 9 completed: no act on ONE item reads « a draft » when the item is known."""

    def test_a_forward_draft_names_the_message_and_its_recipient(self) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label(
                "create_mailbox_forward_draft_tool", {"message_id": "18f0", "to": "Lucie"}
            )
        assert label == {
            "i18n_key": "effects.labels.create_mailbox_forward_draft_tool_named",
            "values": {"target": "Photos du week-end", "recipient": "Lucie"},
        }

    def test_an_unknown_forwarded_message_names_the_recipient_as_before(self) -> None:
        label = build_effect_label(
            "create_mailbox_forward_draft_tool", {"message_id": "18f0", "to": "Lucie"}
        )
        assert label == {
            "i18n_key": "effects.labels.create_mailbox_forward_draft_tool",
            "values": {"target": "Lucie"},
        }

    def test_an_edited_draft_is_named_by_the_subject_it_was_shown_with(self) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label(
                "update_mailbox_draft_tool", {"mailbox_draft_id": "r-1", "instructions": "court"}
            )
        assert label == {
            "i18n_key": "effects.labels.update_mailbox_draft_tool_named",
            "values": {"target": "Devis cuisine"},
        }

    def test_trashed_drafts_are_named_when_every_one_is_known(self) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label(
                "delete_mailbox_drafts_tool", {"mailbox_draft_ids": ["r-1", "r-2"]}
            )
        assert label == {
            "i18n_key": "effects.labels.delete_mailbox_drafts_tool_named",
            "values": {"target": "Devis cuisine, Relance facture"},
        }

    @pytest.mark.parametrize(
        "arguments",
        [
            {"mailbox_draft_ids": ["r-1", "r-9"]},  # one draft nobody was shown
            {"query": "to:lea"},  # chosen by a search: the call names no draft
            {"all_drafts": True},
        ],
    )
    def test_a_deletion_naming_less_than_every_draft_names_none(
        self, arguments: dict[str, Any]
    ) -> None:
        with publishing_label_items(REGISTRY):
            label = build_effect_label("delete_mailbox_drafts_tool", arguments)
        assert label == {"i18n_key": "effects.labels.delete_mailbox_drafts_tool", "values": {}}

    @pytest.mark.parametrize("draft_type", ["email_reply", "email_forward"])
    def test_a_confirmed_send_names_the_message_it_answered(self, draft_type: str) -> None:
        content = {"to": "Marc", "original_subject": "Devis", "message_id": "18f0"}
        label = build_effect_label(f"draft:{draft_type}", {"draft": {"content": content}})
        assert label == {
            "i18n_key": f"effects.labels.draft.{draft_type}_named",
            "values": {"target": "Devis", "recipient": "Marc"},
        }

    def test_a_confirmed_send_without_its_original_subject_names_it_from_the_turn(
        self,
    ) -> None:
        content = {"to": "Marc", "message_id": "18f0"}
        with publishing_label_items(REGISTRY):
            label = build_effect_label("draft:email_reply", {"draft": {"content": content}})
        assert label["values"] == {"target": "Photos du week-end", "recipient": "Marc"}

    def test_a_confirmed_send_with_nothing_to_name_keeps_its_wording(self) -> None:
        label = build_effect_label("draft:email_reply", {"draft": {"content": {"to": "Marc"}}})
        assert label == {
            "i18n_key": "effects.labels.draft.email_reply",
            "values": {"recipient": "Marc"},
        }


def _named_key(tool_name: str) -> str:
    if tool_name.startswith("draft:"):
        return f"effects.labels.draft.{tool_name.removeprefix('draft:')}_named"
    return f"effects.labels.{tool_name}_named"


@pytest.mark.parametrize("tool_name", sorted(_NAMED_VARIANTS))
def test_every_named_wording_exists_in_all_six_languages(tool_name: str) -> None:
    key = _named_key(tool_name)
    for language, table in EFFECT_LABELS.items():
        assert "{target}" in table.get(key, ""), (language, key)
