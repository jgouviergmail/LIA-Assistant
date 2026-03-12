"""
LLM Serializer - Generic payload to text conversion.

Converts any registry item payload to a concise text summary for LLM context.
100% generic - no domain-specific logic, works with any payload structure.

Design principles:
- Zero maintenance: new connectors work automatically
- Simple heuristics: based on data structure, not field names
- Concise output: optimized for brief LLM comments and voice synthesis
- Universal filters: only exclude clearly technical fields

Usage:
    from src.domains.agents.display.llm_serializer import payload_to_text

    text = payload_to_text(contact_payload)
    # "jean dupond | email addresses: jean@x.com, jean.pro@y.com | phone numbers: +33 6..."
"""

from __future__ import annotations

import re
from typing import Any

from src.core.config import settings

# Content fields max length for truncation in LLM context
# Uses Wikipedia summary setting as reasonable default for all content fields
# (Wikipedia articles tend to have the longest summaries)
CONTENT_MAX_LENGTH = settings.wikipedia_summary_max_chars

# Threshold: if a "display name" field is longer than this, treat it as content
CONTENT_LENGTH_THRESHOLD = 200

# Fields that may contain long content (not metadata)
CONTENT_FIELDS: frozenset[str] = frozenset(
    {"summary", "answer", "extract", "content", "body", "description", "text", "snippet"}
)

# =============================================================================
# Configuration - Universal technical fields to exclude
# =============================================================================

# Fields to always skip (universal API conventions, not domain-specific)
SKIP_FIELDS: frozenset[str] = frozenset(
    {
        # IDs and references (including underscore/camelCase variants)
        # IMPORTANT: These MUST be excluded to prevent LLM confusion during intelligent filtering
        # The LLM should only see registry keys [file_a0cc71], not raw API IDs
        "id",
        "etag",
        "kind",
        "resourcename",
        "resource_name",  # Contacts: Google People API ID
        "fileid",
        "file_id",  # Drive: Google Drive file ID
        "placeid",
        "place_id",  # Places: Google Places ID
        "threadid",
        "thread_id",  # Gmail: thread ID
        "labelids",
        "label_ids",  # Gmail: label IDs
        "messageid",
        "message_id",  # Gmail: message ID
        "eventid",
        "event_id",  # Calendar: event ID
        # URL fields containing IDs (can confuse LLM)
        "webviewlink",
        "webcontentlink",
        "selflink",
        # Metadata
        "metadata",
        "sources",
        "memberships",
        # Media (not useful for text/voice - photos are rendered in cards, not comments)
        "photos",
        "coverphotos",
        "thumbnaillink",
        "photo_url",
        "photourl",
        "thumbnail_url",
        "thumbnailurl",
        "image_url",
        "imageurl",
        "icon_url",
        "iconurl",
        # Internal/technical
        "clientdata",
        "userdefined",
        "misckeywords",
        # Index field (internal for ordinal reference resolution)
        "index",
    }
)

# Patterns to skip (prefix/suffix matching)
SKIP_PATTERNS: tuple[str, ...] = (
    "_",  # Private fields
    "raw",  # Raw data
    "internal",  # Internal fields
)


# =============================================================================
# Main API
# =============================================================================


def payload_to_text(
    payload: dict[str, Any],
    max_items: int = 3,
    max_length: int = 60,
) -> str:
    """
    Convert a payload dict to concise text for LLM context.

    100% generic - works with any payload structure.
    Optimized for brief comments and voice synthesis.

    Args:
        payload: Any registry item payload
        max_items: Max items to show from lists (default: 3)
        max_length: Max length for string values (default: 60)

    Returns:
        Concise text summary, e.g.:
        "Jean Dupont | emails: jean@x.com (home) | phones: +33 6... (mobile) | addresses: 2 Rue... (home)"
    """
    if not payload or not isinstance(payload, dict):
        return ""

    # 1. Extract display name (first priority field found)
    display_name = _extract_display_name(payload)

    # 2. Serialize other fields
    parts = []
    for key, value in payload.items():
        if _should_skip(key, value):  # Pass value for content length check
            continue

        # Use longer max_length for content fields
        key_lower = key.lower()
        effective_max_length = CONTENT_MAX_LENGTH if key_lower in CONTENT_FIELDS else max_length

        summary = _summarize_value(key, value, max_items, effective_max_length)
        if summary:
            parts.append(summary)

    # 3. Build final text
    if parts:
        return f"{display_name} | {' | '.join(parts)}"
    return display_name


# =============================================================================
# Internal helpers
# =============================================================================


def _extract_display_name(payload: dict[str, Any]) -> str:
    """
    Extract display name using common API conventions.
    Tries multiple patterns in priority order.
    """
    # Pattern 1: Google-style names array
    names = payload.get("names")
    if isinstance(names, list) and names:
        first = names[0]
        if isinstance(first, dict):
            name = first.get("displayName") or first.get("givenName")
            if name:
                return str(name)

    # Pattern 2: Direct name fields (priority order)
    for field in ("displayName", "name", "title", "subject", "summary", "query"):
        value = payload.get(field)
        if value and isinstance(value, str):
            return str(value[:60] + "..." if len(value) > 60 else value)

    return "(sans nom)"


def _should_skip(key: str, value: Any = None) -> bool:
    """
    Check if field should be skipped (technical/metadata).
    Uses simple rules, not domain-specific logic.

    Content fields (summary, answer, etc.) are NOT skipped if they contain long text,
    as they represent the main content (e.g., Wikipedia summaries, Perplexity answers).
    """
    key_lower = key.lower()

    # Exact match in skip set
    if key_lower in SKIP_FIELDS:
        return True

    # Pattern matching
    for pattern in SKIP_PATTERNS:
        if key_lower.startswith(pattern):
            return True

    # Content fields: skip only if short (used as display name), keep if long (actual content)
    if key_lower in CONTENT_FIELDS:
        if isinstance(value, str) and len(value) > CONTENT_LENGTH_THRESHOLD:
            return False  # Long content - keep it!
        return True  # Short - already used as display name

    # Skip display name fields (already extracted)
    if key_lower in ("names", "displayname", "name", "title", "subject"):
        return True

    return False


def _summarize_value(
    key: str,
    value: Any,
    max_items: int,
    max_length: int,
) -> str | None:
    """
    Summarize a field value based on its structure.
    Pure heuristics - no domain knowledge.
    """
    if value is None or value == "" or value == []:
        return None

    label = _humanize_key(key)

    # List of dicts → extract "value" or "name" fields
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            # Try common value fields
            for extract_key in (
                "value",
                "formattedValue",
                "person",
                "name",
                "displayName",
                "title",
                "formatted",
            ):
                if extract_key in first:
                    extracted = []
                    for v in value[:max_items]:
                        val = v.get(extract_key)
                        if val:
                            text = _truncate(str(val), max_length)
                            # Include type annotation when available (home/work/spouse/child...)
                            item_type = v.get("type", "")
                            if item_type:
                                text = f"{text} ({item_type})"
                            extracted.append(text)
                    if extracted:
                        suffix = f" (+{len(value) - max_items})" if len(value) > max_items else ""
                        return f"{label}: {', '.join(extracted)}{suffix}"

            # Dict without extractable field → just count
            return f"{label}: {len(value)}"

        # List of scalars
        items = [_truncate(str(v), max_length) for v in value[:max_items] if v]
        if items:
            suffix = f" (+{len(value) - max_items})" if len(value) > max_items else ""
            return f"{label}: {', '.join(items)}{suffix}"
        return f"{label}: {len(value)}"

    # Dict → try to extract a meaningful value
    if isinstance(value, dict):
        for extract_key in ("name", "displayName", "value", "formattedValue", "formatted", "text"):
            if extract_key in value and value[extract_key]:
                return f"{label}: {_truncate(str(value[extract_key]), max_length)}"
        # Non-empty dict without extractable field → skip (probably nested structure)
        return None

    # Scalar → direct value
    if isinstance(value, str | int | float | bool):
        str_val = str(value)
        if not str_val or str_val.lower() in ("none", "null", "false"):
            return None
        return f"{label}: {_truncate(str_val, max_length)}"

    return None


def _humanize_key(key: str) -> str:
    """
    Convert camelCase/snake_case to readable label.
    Examples: emailAddresses → email addresses, phone_number → phone number
    """
    # camelCase → spaces
    result = re.sub(r"([a-z])([A-Z])", r"\1 \2", key)
    # snake_case → spaces
    result = result.replace("_", " ")
    return result.lower()


def _truncate(text: str, max_length: int) -> str:
    """Truncate text with ellipsis if too long."""
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
