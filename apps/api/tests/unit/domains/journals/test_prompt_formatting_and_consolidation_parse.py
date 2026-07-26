"""Journal prompt building and consolidation parsing — the assistant's memory of itself.

Three pure surfaces decide what the journal LLM sees and what survives its
answer, and all three fail silently:

* ``_format_messages_for_extraction`` picks which turns of the conversation the
  reflection is written from. It must skip LIA's own proactive notifications —
  otherwise the assistant journals about messages the user never sent.
* ``_format_existing_entries_for_context`` / ``_format_all_entries`` embed the
  entry **IDs** in the prompt. The LLM copies those IDs back to target an
  update or a delete: a malformed header means the maintenance action lands on
  nothing, or on the wrong entry.
* ``_parse_consolidation_result`` reads the answer. A shape it does not
  recognise yields zero actions and no portrait — a consolidation run that
  costs tokens and changes nothing, with no error anywhere.

``_parse_journal_extraction_result`` already has its own suite; this file covers
the consolidation wrapper it feeds, which had none.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.domains.journals.consolidation_service import _format_all_entries
from src.domains.journals.extraction_service import (
    _format_existing_entries_for_context,
    _format_messages_for_extraction,
    _parse_consolidation_result,
)
from src.domains.journals.models import JournalEntry

pytestmark = pytest.mark.unit


def make_entry(**overrides: Any) -> JournalEntry:
    """A JournalEntry with every field the formatters read, none left to a default.

    Built in memory (never added to a session): the formatters are pure readers.
    """
    defaults: dict[str, Any] = {
        "id": uuid.UUID("11111111-1111-4111-8111-111111111111"),
        "user_id": uuid.uuid4(),
        "theme": "user_observations",
        "title": "Rythme de travail",
        "content": "L'utilisateur travaille tard le soir.",
        "mood": "reflective",
        "status": "active",
        "source": "conversation",
        "char_count": 37,
        "search_hints": ["rythme", "soir"],
        "injection_count": 4,
        "last_injected_at": datetime(2026, 7, 20, 8, 0, tzinfo=UTC),
        "created_at": datetime(2026, 7, 1, 9, 30, tzinfo=UTC),
        "confidence": "high",
        "evidence_count": 3,
        "contradiction_count": 1,
        "level": "L2",
    }
    defaults.update(overrides)
    return JournalEntry(**defaults)


# =============================================================================
# Conversation → extraction prompt
# =============================================================================


class TestFormatMessagesForExtraction:
    def test_keeps_the_user_and_assistant_turns_in_order(self) -> None:
        text = _format_messages_for_extraction(
            [HumanMessage(content="Bonjour"), AIMessage(content="Bonsoir plutôt")]
        )

        assert text == "USER: Bonjour\nASSISTANT: Bonsoir plutôt"

    def test_drops_the_assistants_own_proactive_notifications(self) -> None:
        # A heartbeat/interest push is LIA talking to itself: journaling about
        # it would build a self-referential reflection on a turn the user never
        # took part in.
        messages = [
            HumanMessage(content="Salut"),
            AIMessage(
                content="Tiens, un article sur le vélo",
                additional_kwargs={"proactive_notification": True},
            ),
            AIMessage(content="Bonjour !"),
        ]

        text = _format_messages_for_extraction(messages)

        assert "article sur le vélo" not in text
        assert text == "USER: Salut\nASSISTANT: Bonjour !"

    def test_a_falsy_proactive_flag_keeps_the_message(self) -> None:
        messages = [
            AIMessage(
                content="Réponse normale", additional_kwargs={"proactive_notification": False}
            )
        ]

        assert "Réponse normale" in _format_messages_for_extraction(messages)

    @pytest.mark.parametrize(
        "message",
        [
            SystemMessage(content="tu es LIA"),
            ToolMessage(content="{...}", tool_call_id="call_1"),
        ],
    )
    def test_system_and_tool_turns_never_reach_the_prompt(self, message: Any) -> None:
        # System scaffolding and raw tool payloads are not conversation, and a
        # tool result can carry PII the journal must not copy.
        assert _format_messages_for_extraction([message]) == ""

    def test_a_long_message_is_truncated_with_an_ellipsis(self) -> None:
        from src.domains.journals.constants import JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS

        long_text = "a" * (JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS + 500)

        text = _format_messages_for_extraction([HumanMessage(content=long_text)])

        assert text.endswith("...")
        assert len(text) == len("USER: ") + JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS + 3

    def test_a_message_at_the_limit_is_left_whole(self) -> None:
        from src.domains.journals.constants import JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS

        exact = "b" * JOURNAL_EXTRACTION_MESSAGE_MAX_CHARS

        text = _format_messages_for_extraction([HumanMessage(content=exact)])

        assert not text.endswith("...")

    def test_an_empty_conversation_yields_an_empty_block(self) -> None:
        assert _format_messages_for_extraction([]) == ""


# =============================================================================
# Existing entries → extraction prompt
# =============================================================================


class TestFormatExistingEntriesForContext:
    def test_says_so_explicitly_when_there_is_nothing_yet(self) -> None:
        assert _format_existing_entries_for_context([]) == "No existing entries yet."

    def test_the_header_carries_every_field_the_llm_reasons_on(self) -> None:
        entry = make_entry()

        text = _format_existing_entries_for_context([entry])

        for fragment in (
            f"id={entry.id}",
            "created=2026-07-01",
            "last_inj=2026-07-20",
            "uses=4",
            "conf=high",
            "ev=3/co=1",
            "level=L2",
            "user_observations",
            "reflective",
            "hints: rythme, soir",
        ):
            assert fragment in text, fragment

    def test_the_title_and_content_are_both_present(self) -> None:
        text = _format_existing_entries_for_context([make_entry()])

        assert "**Rythme de travail**" in text
        assert "L'utilisateur travaille tard le soir." in text

    def test_a_never_injected_entry_says_never(self) -> None:
        text = _format_existing_entries_for_context([make_entry(last_injected_at=None)])

        assert "last_inj=never" in text

    def test_an_entry_without_hints_omits_the_segment_here(self) -> None:
        # The extraction prompt stays silent; the consolidation prompt says
        # MISSING instead — that asymmetry is deliberate and pinned below.
        text = _format_existing_entries_for_context([make_entry(search_hints=None)])

        assert "hints" not in text

    def test_one_line_per_entry(self) -> None:
        entries = [make_entry(title=f"Entrée {i}") for i in range(3)]

        text = _format_existing_entries_for_context(entries)

        assert len(text.splitlines()) == 3


# =============================================================================
# All entries → consolidation prompt
# =============================================================================


class TestFormatAllEntries:
    def test_says_so_explicitly_when_there_is_nothing_to_review(self) -> None:
        assert _format_all_entries([]) == "No entries to review."

    def test_opens_with_a_copy_pasteable_id_reference_table(self) -> None:
        # The LLM copies these IDs verbatim to target update/delete actions.
        entries = [
            make_entry(id=uuid.UUID("22222222-2222-4222-8222-222222222222"), title="A"),
            make_entry(id=uuid.UUID("33333333-3333-4333-8333-333333333333"), title="B"),
        ]

        text = _format_all_entries(entries)
        header = text.split("\n\n---\n", 1)[0]

        assert "### ENTRY ID REFERENCE" in header
        assert "- 22222222-2222-4222-8222-222222222222  →  A" in header
        assert "- 33333333-3333-4333-8333-333333333333  →  B" in header

    def test_every_id_of_the_table_also_appears_in_its_entry_block(self) -> None:
        entries = [
            make_entry(id=uuid.UUID("22222222-2222-4222-8222-222222222222"), title="A"),
            make_entry(id=uuid.UUID("33333333-3333-4333-8333-333333333333"), title="B"),
        ]

        text = _format_all_entries(entries)
        body = text.split("\n\n---\n", 1)[1]

        for entry in entries:
            assert f"id={entry.id}" in body

    def test_the_char_count_is_exposed_so_the_llm_can_enforce_the_size_budget(self) -> None:
        text = _format_all_entries([make_entry(char_count=1234)])

        assert "1234 chars" in text

    def test_a_missing_hints_list_is_called_out_here(self) -> None:
        # Consolidation is where the assistant is asked to FIX its own entries,
        # so an absent hints list must be visible rather than silently omitted.
        text = _format_all_entries([make_entry(search_hints=None)])

        assert "hints: MISSING" in text

    def test_entries_are_separated_so_two_contents_never_merge(self) -> None:
        entries = [
            make_entry(title="A", content="premier"),
            make_entry(title="B", content="second"),
        ]

        body = _format_all_entries(entries).split("\n\n---\n", 1)[1]

        assert body.count("\n---\n") == len(entries) - 1


# =============================================================================
# Consolidation answer → actions + portraits
# =============================================================================


def _create_action(title: str = "Nouvelle entrée") -> dict[str, Any]:
    return {
        "action": "create",
        "theme": "self_reflection",
        "title": title,
        "content": "Contenu de la réflexion.",
        "mood": "reflective",
    }


class TestParseConsolidationResult:
    def test_the_legacy_bare_array_still_yields_its_actions(self) -> None:
        result = _parse_consolidation_result(json.dumps([_create_action()]))

        assert len(result.actions) == 1
        assert result.portrait_full is None
        assert result.portrait_brief is None

    def test_the_enriched_object_yields_actions_and_both_portraits(self) -> None:
        payload = {
            "actions": [_create_action()],
            "portrait_full": "Portrait long.",
            "portrait_brief": "Portrait court.",
        }

        result = _parse_consolidation_result(json.dumps(payload))

        assert len(result.actions) == 1
        assert result.portrait_full == "Portrait long."
        assert result.portrait_brief == "Portrait court."

    def test_portraits_are_trimmed(self) -> None:
        payload = {"actions": [], "portrait_full": "  Portrait.  ", "portrait_brief": "\nCourt\n"}

        result = _parse_consolidation_result(json.dumps(payload))

        assert result.portrait_full == "Portrait."
        assert result.portrait_brief == "Court"

    @pytest.mark.parametrize("blank", ["", "   ", "\n\t "])
    def test_a_blank_portrait_is_treated_as_absent(self, blank: str) -> None:
        # Persisting an empty portrait would blank the user's profile page.
        payload = {"actions": [], "portrait_full": blank, "portrait_brief": blank}

        result = _parse_consolidation_result(json.dumps(payload))

        assert result.portrait_full is None
        assert result.portrait_brief is None

    @pytest.mark.parametrize("wrong", [42, ["a"], {"x": 1}, None, True])
    def test_a_non_string_portrait_is_refused(self, wrong: Any) -> None:
        payload = {"actions": [], "portrait_full": wrong, "portrait_brief": wrong}

        result = _parse_consolidation_result(json.dumps(payload))

        assert result.portrait_full is None
        assert result.portrait_brief is None

    def test_one_portrait_can_arrive_without_the_other(self) -> None:
        payload = {"actions": [], "portrait_brief": "Court seulement."}

        result = _parse_consolidation_result(json.dumps(payload))

        assert result.portrait_full is None
        assert result.portrait_brief == "Court seulement."

    def test_a_fenced_answer_is_unwrapped(self) -> None:
        payload = {"actions": [_create_action()], "portrait_brief": "Court."}
        fenced = f"```json\n{json.dumps(payload)}\n```"

        result = _parse_consolidation_result(fenced)

        assert len(result.actions) == 1
        assert result.portrait_brief == "Court."

    def test_prose_around_the_json_does_not_break_the_parse(self) -> None:
        payload = {"actions": [_create_action()], "portrait_full": "Long."}
        noisy = f"Voici le résultat :\n{json.dumps(payload)}\nVoilà."

        result = _parse_consolidation_result(noisy)

        assert len(result.actions) == 1
        assert result.portrait_full == "Long."

    @pytest.mark.parametrize("garbage", ["", "not json at all", "null", "{"])
    def test_an_unparseable_answer_changes_nothing(self, garbage: str) -> None:
        result = _parse_consolidation_result(garbage)

        assert result.actions == []
        assert result.portrait_full is None
        assert result.portrait_brief is None

    def test_an_object_without_actions_keeps_the_portraits_it_did_send(self) -> None:
        payload = {"portrait_full": "Long.", "portrait_brief": "Court."}

        result = _parse_consolidation_result(json.dumps(payload))

        assert result.actions == []
        assert result.portrait_full == "Long."

    def test_a_schema_invalid_action_is_skipped_without_losing_the_valid_ones(self) -> None:
        # A hallucinated entry_id fails the UUID validator: that item is
        # dropped, the rest of the batch still applies.
        payload = {
            "actions": [
                {"action": "delete", "entry_id": "entry-42"},
                _create_action("Valide"),
            ],
            "portrait_brief": "Court.",
        }

        result = _parse_consolidation_result(json.dumps(payload))

        assert [action.title for action in result.actions] == ["Valide"]
        assert result.portrait_brief == "Court."

    def test_an_incomplete_create_survives_the_parser_on_purpose(self) -> None:
        # `theme`/`title`/`content` are documented "required for create" but are
        # nullable in the schema: completeness is enforced by the APPLIER
        # (`action.action == "create" and action.theme and action.title and
        # action.content`), and the gap between parsed and applied is visible in
        # the `journal_consolidation_completed` log. Pinned so nobody "fixes"
        # the schema into rejecting a batch that is otherwise usable.
        result = _parse_consolidation_result(json.dumps([{"action": "create"}]))

        assert len(result.actions) == 1
        assert result.actions[0].title is None
        assert result.actions[0].content is None
