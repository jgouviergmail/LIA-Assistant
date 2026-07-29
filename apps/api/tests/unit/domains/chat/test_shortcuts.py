"""User-defined chat slash shortcuts (UX Actions program, SLASH admin lot) —
strict schema validation and the tolerant JSONB reader.

The id charset is the collision defense: ``skill:<name>`` commands carry a
colon, which the slug pattern rejects, so a user shortcut can never shadow a
skill command BY CONSTRUCTION (pinned below).
"""

import pytest
from pydantic import ValidationError

from src.core.constants import (
    CHAT_SHORTCUT_ID_MAX_LENGTH,
    CHAT_SHORTCUT_TEXT_MAX_LENGTH,
)
from src.domains.chat.shortcuts import (
    ChatShortcut,
    ChatShortcutsPayload,
    sanitize_chat_shortcuts,
)


class TestChatShortcutSchema:
    def test_accepts_a_plain_slug(self) -> None:
        shortcut = ChatShortcut(id="meteo-eze", text="Quelle est la météo à Èze ?")
        assert shortcut.id == "meteo-eze"

    @pytest.mark.parametrize(
        "bad_id",
        [
            "skill:quiz",  # colon — the skill namespace stays unreachable
            "Meteo",  # uppercase
            "-lead",  # leading hyphen
            "trail-",  # trailing hyphen
            "a b",  # whitespace
            "é",  # non-ASCII
            "",  # empty
            "x" * (CHAT_SHORTCUT_ID_MAX_LENGTH + 1),  # over the length cap
        ],
    )
    def test_rejects_malformed_ids(self, bad_id: str) -> None:
        with pytest.raises(ValidationError):
            ChatShortcut(id=bad_id, text="whatever")

    def test_rejects_blank_or_oversized_text(self) -> None:
        with pytest.raises(ValidationError):
            ChatShortcut(id="ok", text="   ")
        with pytest.raises(ValidationError):
            ChatShortcut(id="ok", text="x" * (CHAT_SHORTCUT_TEXT_MAX_LENGTH + 1))

    def test_payload_rejects_duplicate_ids(self) -> None:
        with pytest.raises(ValidationError):
            ChatShortcutsPayload(
                shortcuts=[
                    ChatShortcut(id="dup", text="a"),
                    ChatShortcut(id="dup", text="b"),
                ]
            )


class TestSanitizeChatShortcuts:
    def test_null_column_means_no_shortcuts(self) -> None:
        assert sanitize_chat_shortcuts(None).shortcuts == []

    def test_non_list_value_means_no_shortcuts(self) -> None:
        assert sanitize_chat_shortcuts({"id": "x"}).shortcuts == []
        assert sanitize_chat_shortcuts("garbage").shortcuts == []

    def test_drops_malformed_entries_keeps_valid_ones(self) -> None:
        # A malformed stored entry must never 500 the chat page.
        payload = sanitize_chat_shortcuts(
            [
                {"id": "ok-one", "text": "premier"},
                {"id": "BAD ID", "text": "dropped"},
                "not-a-dict",
                {"id": "ok-two"},  # missing text — dropped
                {"id": "ok-three", "text": "troisième"},
            ]
        )
        assert [s.id for s in payload.shortcuts] == ["ok-one", "ok-three"]

    def test_first_occurrence_wins_on_duplicates(self) -> None:
        payload = sanitize_chat_shortcuts(
            [
                {"id": "dup", "text": "kept"},
                {"id": "dup", "text": "shadowed"},
            ]
        )
        assert len(payload.shortcuts) == 1
        assert payload.shortcuts[0].text == "kept"

    def test_round_trips_the_router_write_shape(self) -> None:
        # The router persists [{id, text}] — the reader must accept exactly
        # what the writer stores (serialization round-trip rule).
        stored = [{"id": "meteo", "text": "Quelle est la météo ?"}]
        payload = sanitize_chat_shortcuts(stored)
        assert [{"id": s.id, "text": s.text} for s in payload.shortcuts] == stored
