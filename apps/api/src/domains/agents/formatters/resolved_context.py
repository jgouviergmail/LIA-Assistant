"""
Resolved context formatting for reference turns.

This module provides functions for formatting resolved context items
(from reference resolution like "montre moi le deuxième") for both
LLM prompts and HTML injection.

Usage:
    from src.domains.agents.formatters.resolved_context import (
        format_resolved_context_for_prompt,
        generate_html_for_resolved_context,
        detect_domain_from_item,
    )
"""

from typing import Any

from src.core.constants import DEFAULT_LANGUAGE, DEFAULT_USER_DISPLAY_TIMEZONE
from src.domains.agents.display.config import config_for_viewport
from src.domains.agents.display.html_renderer import get_html_renderer
from src.domains.agents.formatters.text_summary import generate_text_summary_for_items


def detect_domain_from_item(item: dict[str, Any]) -> str:
    """
    Detect domain type from a single item's payload structure.

    Domain names must match TYPE_TO_DOMAIN_MAP for consistency:
    - FILE → "drive" (not "files")
    - SEARCH_RESULT → "perplexity" (not "search")

    Used for resolved_context items which are raw payloads without type info.

    Args:
        item: Dict representing an item payload

    Returns:
        Domain name string (contacts, emails, calendar, places, drive, etc.)
    """
    if not isinstance(item, dict):
        return "other"

    # Order matters - check most specific patterns first
    if "resource_name" in item or "names" in item or "emailAddresses" in item:
        return "contacts"
    elif ("id" in item and "subject" in item) or ("from" in item and "to" in item):
        return "emails"
    elif "start" in item or "end" in item:
        return "events"
    elif "place_id" in item or "formatted_address" in item:
        return "places"
    elif "mimeType" in item or "webViewLink" in item:
        return "drive"  # Matches TYPE_TO_DOMAIN_MAP: FILE → "drive"
    elif "extract" in item or "pageid" in item:
        return "wikipedia"
    elif "citations" in item or item.get("source") == "perplexity":
        return "perplexity"  # Matches TYPE_TO_DOMAIN_MAP: SEARCH_RESULT → "perplexity"
    elif "temperature" in item or "forecast" in item:
        return "weather"
    elif "title" in item and ("notes" in item or "status" in item):
        return "tasks"  # Tasks have title + notes/status (more specific than just title+content)
    elif "travel_mode" in item or ("origin" in item and "destination" in item):
        return "routes"  # Matches TYPE_TO_DOMAIN_MAP: ROUTE → "routes"

    return "other"


def format_resolved_context_for_prompt(
    resolved_context: dict[str, Any],
    use_text_summary: bool = False,
    user_viewport: str = "desktop",
    user_language: str = DEFAULT_LANGUAGE,
) -> str:
    """
    Format resolved context items for LLM prompt.

    V3 Architecture:
    - use_text_summary=True: Returns concise text summary (HTML injected post-LLM)
    - use_text_summary=False: Returns Markdown (legacy mode)

    IMPORTANT: This function NEVER returns HTML. HTML is injected AFTER LLM
    via generate_html_for_resolved_context().

    When a user makes a reference to previous results (e.g., "montre moi le deuxième"),
    this function formats the resolved items for the LLM prompt.

    Args:
        resolved_context: Dict containing items, confidence, method, source_turn_id
        use_text_summary: If True, return concise text summary (for HTML post-injection)
        user_viewport: Device viewport type (mobile/tablet/desktop)
        user_language: User's language code (e.g., "fr", "en")

    Returns:
        Formatted string (text summary or Markdown) for LLM prompt
    """
    items = resolved_context.get("items", [])

    if not items:
        return "Aucun élément résolu pour cette référence."

    # Detect domain type from first item
    first_item = items[0] if items else {}
    domain = detect_domain_from_item(first_item)

    # Pure HTML mode - always use the text summary
    # HTML is injected AFTER the LLM via generate_html_for_resolved_context()
    return generate_text_summary_for_items(items, domain, user_language)


def generate_html_for_resolved_context(
    resolved_context: dict[str, Any],
    user_viewport: str = "desktop",
    user_language: str = DEFAULT_LANGUAGE,
    user_timezone: str = DEFAULT_USER_DISPLAY_TIMEZONE,
) -> str:
    """
    Generate HTML for resolved context items.

    Called AFTER LLM generation to inject structured HTML for REFERENCE turns.

    Args:
        resolved_context: Dict containing items from reference resolution
        user_viewport: Device viewport (mobile/tablet/desktop)
        user_language: Language code
        user_timezone: User's IANA timezone for datetime formatting

    Returns:
        HTML string ready for injection into response
    """
    items = resolved_context.get("items", [])

    if not items:
        return ""

    # Detect domain from first item
    first_item = items[0] if items else {}
    domain = detect_domain_from_item(first_item)

    if domain == "other":
        return ""

    # Get display config
    config = config_for_viewport(user_viewport)
    config.language = user_language
    config.timezone = user_timezone

    html_renderer = get_html_renderer()
    return html_renderer.render(domain, {"items": items}, config)
