"""User-defined chat slash shortcuts (UX Actions program, SLASH admin lot).

Per-user `/shortcut` entries persisted in the ``users.chat_shortcuts`` JSONB
column (arbitration: one nullable JSONB column per feature; writes are full
NEW-list replacements — the JSONB new-dict rule). Two layers, mirroring
``domains/briefing/preferences``:

- ``ChatShortcut`` / ``ChatShortcutsPayload`` — the STRICT request/response
  schemas (malformed ids, oversized text, duplicates → 422);
- ``sanitize_chat_shortcuts`` — the TOLERANT reader for the stored JSONB: a
  malformed entry is dropped, never a 500 on the chat page.

The id charset (lowercase letters, digits, hyphens) makes collisions with the
skill-provided commands impossible BY CONSTRUCTION: those are namespaced
``skill:<name>`` and a colon cannot appear in a user id. Collisions with the
frontend's static commands are resolved client-side (statics win) — the
backend stays agnostic of a registry it does not own.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.constants import (
    CHAT_SHORTCUT_ID_MAX_LENGTH,
    CHAT_SHORTCUT_TEXT_MAX_LENGTH,
)

# Lowercase slug: letters/digits, hyphen-separated, no leading/trailing hyphen.
_SHORTCUT_ID_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


class ChatShortcut(BaseModel):
    """One user-defined slash shortcut."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(
        ...,
        min_length=1,
        max_length=CHAT_SHORTCUT_ID_MAX_LENGTH,
        description="Slug typed after the slash (lowercase letters, digits, hyphens).",
    )
    text: str = Field(
        ...,
        min_length=1,
        max_length=CHAT_SHORTCUT_TEXT_MAX_LENGTH,
        description="Text inserted into the chat input when the shortcut is picked.",
    )

    @field_validator("id")
    @classmethod
    def _slug_shape(cls, value: str) -> str:
        if not _SHORTCUT_ID_RE.fullmatch(value):
            raise ValueError("Shortcut id must be a lowercase slug (letters, digits, hyphens)")
        return value

    @field_validator("text")
    @classmethod
    def _text_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Shortcut text must not be blank")
        return value


class ChatShortcutsPayload(BaseModel):
    """Full-replace payload/response — duplicates are a 422, the cap is
    enforced in the router (it reads a runtime setting)."""

    model_config = ConfigDict(frozen=True)

    shortcuts: list[ChatShortcut] = Field(
        default_factory=list,
        description="The complete ordered list of the user's shortcuts.",
    )

    @field_validator("shortcuts")
    @classmethod
    def _unique_ids(cls, value: list[ChatShortcut]) -> list[ChatShortcut]:
        ids = [shortcut.id for shortcut in value]
        if len(set(ids)) != len(ids):
            raise ValueError("Duplicate shortcut ids")
        return value


class ChatShortcutsResponse(ChatShortcutsPayload):
    """Read shape: the sanitized list plus the runtime count cap, so the
    settings UI can show "N of MAX" without guessing a server constant."""

    max_count: int = Field(..., description="Maximum shortcuts per user (runtime setting).")


def sanitize_chat_shortcuts(raw: Any) -> ChatShortcutsPayload:
    """Tolerant reader for the stored ``users.chat_shortcuts`` value.

    Args:
        raw: The JSONB column value (possibly None, non-list, or containing
            malformed entries — the chat page must render regardless).

    Returns:
        The valid entries, first occurrence winning on duplicate ids.
    """
    if not isinstance(raw, list):
        return ChatShortcutsPayload()
    seen: set[str] = set()
    valid: list[ChatShortcut] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        try:
            shortcut = ChatShortcut.model_validate(entry)
        except ValueError:
            continue
        if shortcut.id in seen:
            continue
        seen.add(shortcut.id)
        valid.append(shortcut)
    return ChatShortcutsPayload(shortcuts=valid)
