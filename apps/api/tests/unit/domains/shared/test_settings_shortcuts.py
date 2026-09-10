"""Pinned settings sections (ADR-277) — the strict payload and the tolerant reader.

The tokens are the frontend's vocabulary: the backend keeps their SHAPE and
never their list, so the checks here are about shape, uniqueness and the cap
— and about the profile building whatever the column happens to hold.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import ValidationError

from src.core.config import settings
from src.core.constants import SETTINGS_SHORTCUT_TOKEN_MAX_LENGTH
from src.domains.shared.schemas import UserBase
from src.domains.shared.settings_shortcuts import (
    SettingsShortcutsPayload,
    is_settings_shortcut_token,
    sanitize_settings_shortcuts,
)

pytestmark = pytest.mark.unit


class TestTheStrictPayload:
    def test_accepts_section_tokens(self) -> None:
        payload = SettingsShortcutsPayload(shortcuts=["theme", "chat-shortcuts", "admin-users"])
        assert payload.shortcuts == ["theme", "chat-shortcuts", "admin-users"]

    @pytest.mark.parametrize(
        "bad",
        [
            "Theme",  # uppercase
            "-theme",  # leading hyphen
            "theme-",  # trailing hyphen
            "my shortcuts",  # whitespace
            "thème",  # non-ASCII
            "",  # empty
            "x" * (SETTINGS_SHORTCUT_TOKEN_MAX_LENGTH + 1),  # over the length cap
            "a:b",  # a namespace separator is not a slug
        ],
    )
    def test_rejects_a_malformed_token(self, bad: str) -> None:
        with pytest.raises(ValidationError):
            SettingsShortcutsPayload(shortcuts=[bad])

    def test_rejects_a_duplicate(self) -> None:
        with pytest.raises(ValidationError):
            SettingsShortcutsPayload(shortcuts=["theme", "theme"])

    def test_the_count_is_not_the_schema_s_business(self) -> None:
        # The cap reads a runtime setting; the router enforces it (the chat
        # shortcuts precedent), so the schema stays static.
        many = [f"section-{i}" for i in range(settings.settings_shortcuts_max_count + 3)]
        assert SettingsShortcutsPayload(shortcuts=many).shortcuts == many


class TestTheTolerantReader:
    def test_null_means_nothing_pinned(self) -> None:
        assert sanitize_settings_shortcuts(None, max_count=5) == []

    def test_a_non_list_means_nothing_pinned(self) -> None:
        assert sanitize_settings_shortcuts({"theme": True}, max_count=5) == []
        assert sanitize_settings_shortcuts("theme", max_count=5) == []

    def test_drops_the_malformed_and_keeps_the_order(self) -> None:
        raw: list[Any] = ["theme", 42, "BAD", None, "font", {"id": "x"}, "theme", "haptics"]
        assert sanitize_settings_shortcuts(raw, max_count=5) == ["theme", "font", "haptics"]

    def test_applies_the_cap_in_order(self) -> None:
        assert sanitize_settings_shortcuts(["a", "b", "c", "d"], max_count=2) == ["a", "b"]

    def test_the_shape_predicate_is_the_slug(self) -> None:
        assert is_settings_shortcut_token("eyes-style")
        assert not is_settings_shortcut_token("Eyes")
        assert not is_settings_shortcut_token(3)


class TestTheProfileReadsTheColumnAsStored:
    """A malformed stored value must never 500 ``/auth/me``."""

    @staticmethod
    def _base(**overrides: Any) -> UserBase:
        payload: dict[str, Any] = {
            "id": uuid.uuid4(),
            "email": "visiteur@client.fr",
            "is_active": True,
            "is_verified": True,
            "is_superuser": False,
            "created_at": datetime(2026, 1, 2, tzinfo=UTC),
            "updated_at": datetime(2026, 1, 3, tzinfo=UTC),
            **overrides,
        }
        return UserBase.model_validate(payload)

    def test_an_absent_value_is_an_empty_list(self) -> None:
        assert self._base().settings_shortcuts == []

    def test_a_null_column_is_an_empty_list(self) -> None:
        assert self._base(settings_shortcuts=None).settings_shortcuts == []

    def test_garbage_is_dropped_not_raised(self) -> None:
        base = self._base(settings_shortcuts=["theme", 1, "BAD", "font"])
        assert base.settings_shortcuts == ["theme", "font"]

    def test_the_runtime_cap_applies_on_read(self) -> None:
        cap = settings.settings_shortcuts_max_count
        stored = [f"section-{i}" for i in range(cap + 2)]
        assert self._base(settings_shortcuts=stored).settings_shortcuts == stored[:cap]
