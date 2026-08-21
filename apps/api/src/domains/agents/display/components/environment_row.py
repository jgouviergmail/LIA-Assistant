"""Shared air-quality / pollen rendering for cards (2026-08).

Both the weather card and the place card show the same enrichment, and the
honesty rules are subtle enough that having them in one place is what keeps
them true everywhere:

- the provider's own localized CATEGORY wins — Google's universal index is
  inverted vs EPA (100 = excellent), so a label is never re-derived from a
  number;
- value and category come from the SAME index: national indexes (e.g.
  ``fra_atmo``) routinely ship a category with NO number, so the row renders
  on the category and never borrows another scale's figure;
- nothing to say ⇒ empty string, so callers can test-and-skip.
"""

from __future__ import annotations

from typing import Any

from src.core.i18n_v3 import V3Messages
from src.domains.agents.display.components.base import escape_html


def air_quality_text(data: dict[str, Any], language: str, fallback_label: Any = None) -> str:
    """Air-quality line for a card, or "" when there is nothing honest to show.

    Args:
        data: Card payload carrying ``aqi`` / ``aqi_category`` / ``aqi_label``
            (or the legacy numeric ``aqi`` / ``air_quality``).
        language: User language for the row label.
        fallback_label: Optional callable ``(value, language) -> str`` used to
            label a LEGACY numeric payload that has no provider category
            (the weather card's historical EPA table).

    Returns:
        e.g. ``"Qualité de l'air: 66 (Bonne …, Universal AQI)"`` or
        ``"Qualité de l'air: Moyen (IQA (FR))"``.
    """
    aqi = data.get("aqi") if data.get("aqi") is not None else data.get("air_quality")
    category = data.get("aqi_category") or ""
    index_label = data.get("aqi_label") or ""

    if not category and aqi in (None, ""):
        return ""
    if not category and fallback_label is not None:
        category = fallback_label(aqi, language)

    value_part = escape_html(str(aqi)) if aqi not in (None, "") else ""
    qualifiers = [escape_html(str(category))] if value_part and category else []
    if index_label:
        qualifiers.append(escape_html(str(index_label)))
    suffix = f" ({', '.join(qualifiers)})" if qualifiers else ""
    head = value_part or escape_html(str(category))
    return f"{V3Messages.get_air_quality(language)}: {head}{suffix}"


def pollen_text(data: dict[str, Any], language: str) -> str:
    """In-season pollen line, or "" when there is nothing to show.

    Only types the provider marked in season WITH an index reach the payload,
    so every entry here is a real signal.
    """
    pollen = data.get("pollen") or []
    if not isinstance(pollen, list) or not pollen:
        return ""
    entries = [
        (
            f"{escape_html(str(item.get('name', '')))} "
            f"{escape_html(str(item.get('category', '')))}"
        ).strip()
        for item in pollen
        if isinstance(item, dict) and item.get("name")
    ]
    if not entries:
        return ""
    return f"{V3Messages.get_pollen(language)}: {', '.join(entries)}"
