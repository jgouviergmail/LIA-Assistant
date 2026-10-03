"""What a card draws of a registry item: its payload and its display-only fields.

A tool may withhold a field from the model and still owe it to the person —
the e-mail body under ``detail=metadata`` (ADR-287 amendment). It puts the
field under ``FIELD_DISPLAY_ONLY``; ``take_display_fields`` moves it to
``RegistryItemMeta.display`` when the registry item is built, before any copy
of the payload is taken, so every model projection — which reads payloads,
never ``meta`` — is clean by construction. The card renderers read items
through ``card_payload`` and see the message whole.
"""

from __future__ import annotations

from typing import Any

from src.core.field_names import FIELD_DISPLAY_ONLY
from src.domains.agents.data_registry.mcp_metadata import authoritative_mcp_source

__all__ = ["card_payload", "display_fields", "restore_display_fields", "take_display_fields"]


def take_display_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """Remove the display-only fields from ``payload`` and return them.

    Args:
        payload: A registry payload being built (mutated in place).

    Returns:
        The withheld fields, empty when the tool withheld nothing.
    """
    display = payload.pop(FIELD_DISPLAY_ONLY, None)
    return dict(display) if isinstance(display, dict) else {}


def display_fields(item: object) -> dict[str, Any]:
    """The display-only fields of a registry item (object or JSON dump).

    Args:
        item: A registry item.

    Returns:
        Its ``meta.display``, empty when it carries none.
    """
    if isinstance(item, dict):
        meta = item.get("meta")
        display = meta.get("display") if isinstance(meta, dict) else None
    else:
        display = getattr(getattr(item, "meta", None), "display", None)
    return display if isinstance(display, dict) else {}


def restore_display_fields(payload: dict[str, Any]) -> dict[str, Any]:
    """A payload carrying its display fields under ``FIELD_DISPLAY_ONLY``, for a card.

    A resolved reference travels as a bare payload (no ``meta``): it keeps its
    display fields under the transient key, which every model reader skips.

    Args:
        payload: The payload.

    Returns:
        A new dict with the display fields merged in, or the payload itself.
    """
    display = payload.get(FIELD_DISPLAY_ONLY)
    if not isinstance(display, dict):
        return payload
    return {**{k: v for k, v in payload.items() if k != FIELD_DISPLAY_ONLY}, **display}


def card_payload(item: object) -> dict[str, Any] | None:
    """The payload a card draws: the item's payload with its display fields.

    Accepts a ``RegistryItem`` or its JSON dump (the checkpointed shape).

    Args:
        item: A registry item.

    Returns:
        A new dict when the item carries display fields, the payload itself
        otherwise; ``None`` when the item has no payload.
    """
    payload = item.get("payload") if isinstance(item, dict) else getattr(item, "payload", None)
    if not isinstance(payload, dict):
        return None
    display = display_fields(item)
    if source := authoritative_mcp_source(item, display):
        return {**payload, **display, "_mcp_source": source}
    return {**payload, **display} if display else payload
