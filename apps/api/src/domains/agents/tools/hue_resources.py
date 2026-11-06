"""What the Hue tools share: finding a resource by its name, and saying why not (ADR-369).

A command the bridge cannot address is a declared failure, read by every reader of the verdict.
"""

from __future__ import annotations

from typing import Any

from src.core.field_names import FIELD_ERROR, FIELD_ERROR_CODE, FIELD_SUCCESS
from src.core.i18n import _
from src.domains.agents.tools.base import ConnectorTool
from src.domains.agents.tools.common import ToolErrorCode
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.philips_hue_client import HUE_COLOR_MAP


def find_resource_by_name(
    resources: list[dict[str, Any]],
    name_or_id: str,
) -> dict[str, Any] | None:
    """
    Find a Hue resource by exact name or ID.

    Performs strict matching only — no fuzzy or partial matching.
    The planner is responsible for resolving user descriptions to exact
    device names via IoT discovery context injection.

    Search order:
    1. Exact ID match
    2. Case-insensitive exact name match on metadata.name

    Args:
        resources: List of Hue API resource dicts.
        name_or_id: Resource name or ID to search for.

    Returns:
        Matching resource dict, or None if not found.
    """
    # Try exact ID match first
    for r in resources:
        if r.get("id") == name_or_id:
            return r

    # Try case-insensitive name match
    search = name_or_id.strip().lower()
    for r in resources:
        resource_name = r.get("metadata", {}).get("name", "").strip().lower()
        if resource_name == search:
            return r

    return None


def unreadable_colour(color: str, language: str) -> dict[str, Any]:
    """The payload of a colour nobody can read: refused, never sent as nothing and told as done."""
    return {
        FIELD_SUCCESS: False,
        FIELD_ERROR_CODE: ToolErrorCode.INVALID_INPUT.value,
        FIELD_ERROR: _("Color '{color}' not recognized. Available: {available}", language).format(
            color=color, available=", ".join(HUE_COLOR_MAP)
        ),
        ConnectorTool._LANGUAGE_RESULT_KEY: language,
    }


def not_found(message: str, language: str) -> dict[str, Any]:
    """The payload of a command whose target the bridge does not hold.

    The refusal is DECLARED (``success`` false, a typed code) so that every
    reader of the verdict sees a failure: answered as a success saying it failed,
    the effect register settled the act SUCCEEDED and the ReAct directive told
    the response model it had switched the light.

    Args:
        message: The localised sentence naming what the bridge does hold.
        language: The user's language, read back by the formatter.

    Returns:
        The refusal payload ``format_registry_response`` turns into a failure.
    """
    return {
        FIELD_SUCCESS: False,
        FIELD_ERROR_CODE: ToolErrorCode.NOT_FOUND.value,
        FIELD_ERROR: message,
        ConnectorTool._LANGUAGE_RESULT_KEY: language,
    }


def refusal(result: dict[str, Any], fallback: str) -> UnifiedToolOutput:
    """A refused command as the failure it is, its code kept.

    Args:
        result: The refusal payload of ``execute_api_call``.
        fallback: The localised sentence used when the payload names no error.

    Returns:
        A failure the runtime failures directive words from its code.
    """
    return UnifiedToolOutput.failure(
        message=result.get(FIELD_ERROR) or fallback,
        error_code=str(result.get(FIELD_ERROR_CODE) or ToolErrorCode.NOT_FOUND.value),
    )


__all__ = ["find_resource_by_name", "not_found", "refusal", "unreadable_colour"]
