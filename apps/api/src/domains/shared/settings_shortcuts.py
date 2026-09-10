"""Pinned settings sections — the floating shortcuts dock (ADR-277).

A person pins up to ``settings_shortcuts_max_count`` sections of the settings
page; every screen of the application then shows them in a floating dock. The
tokens are the FRONTEND's vocabulary (``SettingsSectionToken`` in
``apps/web/src/lib/settings-sections.ts``): the backend keeps their SHAPE — a
lowercase slug — and never their list, which changes with the settings page
and would otherwise be a second table to drift. The frontend drops, at read
time, a token it no longer declares.

Lives in ``domains/shared`` because the profile DTO (``UserBase``) reads the
stored value through the tolerant reader below, and ``shared`` imports no
domain. Two layers, mirroring ``domains/chat/shortcuts``:

- ``SettingsShortcutsPayload`` — the STRICT request schema (malformed token,
  duplicate → 422; the COUNT cap is enforced by the router, which reads the
  runtime setting so the schema stays static);
- ``sanitize_settings_shortcuts`` — the TOLERANT reader of the stored JSONB: a
  malformed entry is dropped and the cap applied, never a 500 on ``/auth/me``.
"""

from __future__ import annotations

import re
from typing import Any, TypeGuard

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.constants import SETTINGS_SHORTCUT_TOKEN_MAX_LENGTH

# Lowercase slug: letters/digits, hyphen-separated, no leading/trailing hyphen
# — the shape of every settings section token.
_TOKEN_RE = re.compile(r"^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$")


def is_settings_shortcut_token(value: object) -> TypeGuard[str]:
    """Whether ``value`` has the shape of a settings section token.

    Args:
        value: Anything read from a request or from the column.

    Returns:
        True for a bounded lowercase slug — the shape, never the meaning.
    """
    return (
        isinstance(value, str)
        and len(value) <= SETTINGS_SHORTCUT_TOKEN_MAX_LENGTH
        and _TOKEN_RE.fullmatch(value) is not None
    )


class SettingsShortcutsPayload(BaseModel):
    """Full-replace payload: the complete ordered list of pinned tokens."""

    model_config = ConfigDict(frozen=True)

    shortcuts: list[str] = Field(
        default_factory=list,
        description="The complete ordered list of pinned settings section tokens.",
    )

    @field_validator("shortcuts")
    @classmethod
    def _well_formed_and_unique(cls, value: list[str]) -> list[str]:
        for token in value:
            if not is_settings_shortcut_token(token):
                raise ValueError(f"Not a settings section token: {token!r}")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate settings shortcuts")
        return value


class SettingsShortcutsResponse(SettingsShortcutsPayload):
    """Read shape: the sanitized list plus the runtime cap, so the settings
    section shows « N of MAX » without guessing a server constant."""

    max_count: int = Field(..., description="Maximum pinned sections per user (runtime setting).")


def sanitize_settings_shortcuts(raw: Any, *, max_count: int) -> list[str]:
    """Tolerant reader for the stored ``users.settings_shortcuts`` value.

    Args:
        raw: The JSONB column value (possibly None, non-list, or holding
            malformed entries — the profile must build regardless).
        max_count: The runtime cap; entries beyond it are dropped in order.

    Returns:
        The well-formed tokens, first occurrence winning on a duplicate, at
        most ``max_count`` of them.
    """
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    valid: list[str] = []
    for entry in raw:
        if not is_settings_shortcut_token(entry) or entry in seen:
            continue
        seen.add(entry)
        valid.append(entry)
        if len(valid) >= max_count:
            break
    return valid
