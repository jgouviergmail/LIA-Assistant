"""
Resolved context formatting for reference turns.

This module provides functions for formatting resolved context items
(from reference resolution like "show me the second one") for both
LLM prompts and HTML injection.

Usage:
    from src.domains.agents.formatters.resolved_context import (
        format_resolved_context_for_prompt,
        generate_html_for_resolved_context,
        detect_domain_from_item,
    )
"""

from typing import Any

from src.core.constants import DEFAULT_USER_DISPLAY_TIMEZONE
from src.core.i18n import resolve_language
from src.domains.agents.data_registry.card_payload import restore_display_fields
from src.domains.agents.display.config import config_for_viewport
from src.domains.agents.display.html_renderer import get_html_renderer
from src.domains.agents.formatters.text_summary import generate_text_summary_for_items

_PAYLOAD_SIGNATURES: tuple[tuple[str, tuple[frozenset[str], ...], str | None], ...] = (
    ("sms_messages", (frozenset(["body_offset", "owner_id", "received_at"]),), None),
    (
        "contacts",
        (frozenset(["resource_name"]), frozenset(["names"]), frozenset(["emailAddresses"])),
        None,
    ),
    ("emails", (frozenset(["id", "subject"]), frozenset(["from", "to"])), None),
    ("events", (frozenset(["start"]), frozenset(["end"])), None),
    ("places", (frozenset(["place_id"]), frozenset(["formatted_address"])), None),
    ("drive", (frozenset(["mimeType"]), frozenset(["webViewLink"])), None),
    ("wikipedia", (frozenset(["extract"]), frozenset(["pageid"])), None),
    ("perplexity", (frozenset(["citations"]),), "perplexity"),
    ("weather", (frozenset(["temperature"]), frozenset(["forecast"])), None),
    ("tasks", (frozenset(["notes", "title"]), frozenset(["status", "title"])), None),
    ("routes", (frozenset(["travel_mode"]), frozenset(["destination", "origin"])), None),
)


def detect_domain_from_item(item: dict[str, Any]) -> str:
    """
    Detect the display token of a single item from its payload structure.

    Used for resolved_context items which are raw payloads without type info.

    The returned token is consumed ONLY by the display layer
    (``HtmlRenderer`` / ``generate_text_summary_for_items``), which is
    alias-tolerant: it registers both the canonical result_key AND legacy
    singular/display aliases for the same card. The tokens returned here are
    therefore a MIX of canonical result_keys (``contacts``, ``emails``,
    ``events``, ``places``, ``tasks``, ``routes``) and legacy display aliases
    (``drive`` for the file domain, ``wikipedia``/``perplexity``/``weather``
    for their plural result_keys). This is NOT the canonical domain vocabulary
    and is NEVER compared on a condition axis — see ADR-102. Do not reuse it
    where a canonical name/result_key is expected.

    Args:
        item: Dict representing an item payload

    Returns:
        A display token (e.g. ``contacts``, ``emails``, ``places``, ``drive``)
        or ``other`` when no pattern matches.
    """
    if not isinstance(item, dict):
        return "other"

    for domain, signatures, source in _PAYLOAD_SIGNATURES:
        if source is not None and item.get("source") == source:
            return domain
        if any(signature.issubset(item) for signature in signatures):
            return domain
    return "other"


def format_resolved_context_for_prompt(
    resolved_context: dict[str, Any],
    use_text_summary: bool = False,
    user_viewport: str = "desktop",
    user_language: str | None = None,
) -> str:
    """
    Format resolved context items for LLM prompt.

    V3 Architecture:
    - use_text_summary=True: Returns concise text summary (HTML injected post-LLM)
    - use_text_summary=False: Returns Markdown (legacy mode)

    IMPORTANT: This function NEVER returns HTML. HTML is injected AFTER LLM
    via generate_html_for_resolved_context().

    When a user makes a reference to previous results (e.g., "show me the second one"),
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
        return "No item resolved for this reference."

    # Detect domain type from first item
    first_item = items[0] if items else {}
    domain = detect_domain_from_item(first_item)

    # Pure HTML mode - always use the text summary
    # HTML is injected AFTER the LLM via generate_html_for_resolved_context()
    return generate_text_summary_for_items(items, domain, resolve_language(user_language))


def generate_html_for_resolved_context(
    resolved_context: dict[str, Any],
    user_viewport: str = "desktop",
    user_language: str | None = None,
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
    config.language = resolve_language(user_language)
    config.timezone = user_timezone

    html_renderer = get_html_renderer()
    # The card draws what the level withheld from the model (ADR-287 amendment).
    cards = [restore_display_fields(item) if isinstance(item, dict) else item for item in items]
    return html_renderer.render(domain, {"items": cards}, config)
