"""Briefing grid preferences (UXR Lot 5, B4).

Per-user visibility + ordering of the 9 dashboard cards, persisted in the
``users.briefing_preferences`` JSONB column (arbitration: one nullable JSONB
column per feature; writes are plain NEW-dict replacements — the JSONB
new-dict rule). Two layers:

- ``BriefingPreferences`` — the STRICT request/response schema (unknown or
  duplicated section names are a 422);
- ``sanitize_briefing_preferences`` — the TOLERANT reader for the stored
  JSONB: unknown names are filtered (a section removed in a future release
  must never 500 the dashboard), the order is deduped and completed
  canonically so future sections surface by default at their canonical
  position.

``new_account_briefing_preferences`` writes the grid a brand-new account
starts with (the weather card alone where the instance serves the weather,
owner decision 2026-10-22); a NULL column
— an account created before that date whose grid was never saved — still means
every card visible.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.briefing.constants import (
    NEW_ACCOUNT_VISIBLE_SECTIONS,
    SECTION_DISPLAY_ORDER_DEFAULT,
    SECTION_NAMES,
)
from src.domains.connectors.keyless import keyless_ceiling_reason
from src.domains.connectors.models import ConnectorType


class BriefingPreferences(BaseModel):
    """User-facing grid preferences — strict vocabulary, no duplicates."""

    model_config = ConfigDict(frozen=True)

    hidden: list[str] = Field(
        default_factory=list,
        description="Sections the user hid — never fetched nor cache-read.",
    )
    order: list[str] = Field(
        default_factory=list,
        description="Display order; missing sections follow canonically.",
    )

    @field_validator("hidden", "order")
    @classmethod
    def _known_unique_sections(cls, value: list[str]) -> list[str]:
        unknown = [name for name in value if name not in SECTION_NAMES]
        if unknown:
            raise ValueError(f"Unknown briefing sections: {unknown}")
        if len(set(value)) != len(value):
            raise ValueError("Duplicate briefing sections")
        return value


def _clean_names(raw: Any) -> list[str]:
    """Known section names from an untrusted list, deduped, order kept."""
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    out: list[str] = []
    for name in raw:
        if isinstance(name, str) and name in SECTION_NAMES and name not in seen:
            seen.add(name)
            out.append(name)
    return out


def sanitize_briefing_preferences(raw: dict[str, Any] | None) -> BriefingPreferences:
    """Tolerant reader for the stored JSONB column.

    Args:
        raw: The ``users.briefing_preferences`` value (possibly None or
            malformed — the dashboard must render regardless).

    Returns:
        Preferences with a COMPLETE order (stored prefix first, then every
        missing section in canonical order) and a filtered hidden list.
    """
    payload: dict[str, Any] = raw if isinstance(raw, dict) else {}
    hidden = _clean_names(payload.get("hidden"))
    order = _clean_names(payload.get("order"))
    # Missing sections follow in the historical DISPLAY order — a NULL column
    # (or a future section) must never reshuffle the grid users know.
    order += [name for name in SECTION_DISPLAY_ORDER_DEFAULT if name not in order]
    return BriefingPreferences(hidden=hidden, order=order)


def new_account_briefing_preferences() -> dict[str, Any]:
    """The grid a brand-new account starts with: the weather card alone, where it can show.

    Stored exactly like a choice the person makes on the grid settings (the
    strict schema, dumped), so the settings show every other card switched off,
    ready to be switched back on. A card added by a later release is not in
    ``hidden`` and therefore shows, like on every other account.

    The weather card alone rests on the weather needing nothing but an address:
    the instance serves Google Weather on its platform key (ADR-307). A
    deployment without that key — the public demonstrator, where nobody can
    link a provider either — could never draw it, and a grid holding it alone
    would be empty: the account then starts with every card, as every account
    did before.

    Returns:
        A new dict for the ``users.briefing_preferences`` column.
    """
    if keyless_ceiling_reason(ConnectorType.GOOGLE_WEATHER) is not None:
        return BriefingPreferences().model_dump(mode="json")
    hidden = [
        name for name in SECTION_DISPLAY_ORDER_DEFAULT if name not in NEW_ACCOUNT_VISIBLE_SECTIONS
    ]
    return BriefingPreferences(hidden=hidden).model_dump(mode="json")
