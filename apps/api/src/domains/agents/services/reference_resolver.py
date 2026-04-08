"""
Reference resolver service for contextual follow-up questions.

Extracts and resolves linguistic references (ordinals, demonstratives)
to previous agent results.

ARCHITECTURE NOTE (2026-01-03):
This service uses ENGLISH-ONLY patterns because all queries are translated
to English via Semantic Pivot BEFORE reaching this service.
- Input: French "detail du premier" → Semantic Pivot → "details of the first"
- This service operates on the English-translated query only
- No need for multilingual patterns (simpler, more reliable)

This service is stateless - all request state is passed via method parameters.

Created: 2025-01
Refactored: 2026-01-03 - English-only patterns, removed multilingual complexity
"""

import re
from dataclasses import dataclass, field
from typing import Any

import structlog

from src.core.config import Settings, get_settings

logger = structlog.get_logger(__name__)

# Mapping from API payload field names to tool parameter names by domain.
# The LLM sees "id" in the payload but tools expect "event_id", "message_id", etc.
# Without this alias, the LLM invents $steps references instead of using the value.
_DOMAIN_ID_ALIASES: dict[str, dict[str, str]] = {
    "event": {"id": "event_id"},
    "email": {"id": "message_id"},
    "contact": {"resourceName": "resource_name"},
    "task": {"id": "task_id"},
    "file": {"id": "file_id"},
}


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class ExtractedReference:
    """Single extracted reference from user query."""

    type: str  # ordinal, demonstrative, comparative
    text: str  # Original text matched
    index: int | None  # Resolved index if ordinal (-1 for last)
    pattern: str  # Pattern that matched


@dataclass
class ExtractedReferences:
    """Collection of extracted references from a query."""

    references: list[ExtractedReference] = field(default_factory=list)

    def has_explicit(self) -> bool:
        """Check if there are any explicit references."""
        return len(self.references) > 0

    def get_ordinals(self) -> list[ExtractedReference]:
        """Get all ordinal references."""
        return [r for r in self.references if r.type == "ordinal"]

    def get_demonstratives(self) -> list[ExtractedReference]:
        """Get all demonstrative references."""
        return [r for r in self.references if r.type == "demonstrative"]


@dataclass
class ResolvedContext:
    """Result of context resolution."""

    items: list[Any]  # Resolved items
    confidence: float  # Resolution confidence (0.0-1.0)
    method: str  # Resolution method: explicit, lifecycle, none, error
    source_turn_id: int | None  # Turn ID from which items were resolved
    source_domain: str | None = (
        None  # Domain from which items were resolved (e.g., "places", "contacts")
    )

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "items": self.items,
            "confidence": self.confidence,
            "method": self.method,
            "source_turn_id": self.source_turn_id,
            "source_domain": self.source_domain,
        }

    def to_llm_context(self) -> str:
        """
        Format context for LLM consumption in planner prompts.

        Creates a clear, structured representation that the LLM can easily parse
        and use for cross-domain queries. Auto-serializes all relevant fields.

        ARCHITECTURE v3.2 (2026-01-03):
        - Extracts READY-TO-USE values for cross-domain queries
        - Explicitly tells LLM to use these values DIRECTLY
        - Prevents LLM from hallucinating "resolution" tools

        Returns:
            Formatted string for inclusion in LLM prompt.
        """
        if not self.items:
            return ""

        # Fields to exclude (internal/technical)
        exclude_fields = {
            "index",
            "_index",
            "meta",
            "_meta",
            "raw",
            "_raw",
            "etag",
            "kind",
            "selfLink",
            "iCalUID",
            "htmlLink",
            "creator",
            "organizer",
        }

        # Priority fields to show first (if present)
        priority_fields = [
            "id",
            "resource_name",
            "place_id",
            "message_id",
            "name",
            "summary",
            "title",
            "subject",
            "location",
            "address",
            "start",
            "end",
            "due",
            "date",
            "email",
            "phone",
            "attendees",
            "participants",
        ]

        # Cross-domain key fields (for READY-TO-USE section)
        cross_domain_keys = {
            "location": "places",
            "address": "places",
            "email": "emails",
            "name": "contacts",
            "summary": "general",
            "subject": "emails",
        }

        lines = []
        ready_to_use_values: dict[str, str] = {}
        id_aliases = _DOMAIN_ID_ALIASES.get(self.source_domain or "", {})

        # === HEADER ===
        lines.append(
            "RESOLVED CONTEXT (items already fetched — use their IDs directly in parameters, "
            "DO NOT create any resolve/context/reference step):"
        )
        lines.append(f"Source domain: {self.source_domain or 'unknown'}")
        lines.append(f"Items count: {len(self.items)}")

        for i, item in enumerate(self.items, 1):
            lines.append(f"\n  Item {i}:")
            if isinstance(item, dict):
                # Inject tool-parameter aliases for ID fields so the LLM can map directly.
                # Example: event payload has "id" but update_event_tool expects "event_id".
                for payload_field, param_name in id_aliases.items():
                    if payload_field in item and item[payload_field] is not None:
                        value = self._format_value(item[payload_field])
                        if value and param_name not in item:
                            lines.append(
                                f"    - {param_name}: {value}"
                                "  ← use this directly as tool parameter"
                            )

                # Collect fields: priority first, then rest
                shown_fields = set()
                field_lines = []

                # Priority fields first
                for field in priority_fields:
                    if field in item and item[field] is not None:
                        value = self._format_value(item[field])
                        if value:
                            field_lines.append(f"    - {field}: {value}")
                            shown_fields.add(field)
                            # Extract cross-domain values
                            if field in cross_domain_keys and len(self.items) == 1:
                                ready_to_use_values[field] = value

                # Remaining fields (sorted alphabetically)
                for field in sorted(item.keys()):
                    if field in shown_fields or field in exclude_fields:
                        continue
                    if field.startswith("_"):
                        continue
                    value = self._format_value(item[field])
                    if value:
                        field_lines.append(f"    - {field}: {value}")

                lines.extend(field_lines)
            else:
                # Non-dict item: just stringify
                lines.append(f"    {str(item)[:300]}")

        # === READY-TO-USE VALUES (explicit extraction for cross-domain) ===
        if ready_to_use_values:
            lines.append("\n" + "=" * 60)
            lines.append("READY-TO-USE VALUES (use these DIRECTLY in tool parameters):")
            lines.append("=" * 60)
            for field, value in ready_to_use_values.items():
                cross_domain_keys.get(field, "unknown")
                lines.append(f'  {field.upper()}: "{value}"')
                if field == "location":
                    lines.append(f'    → For places search: get_places_tool(query="{value}")')
                elif field == "email":
                    lines.append(f'    → For email search: get_emails_tool(query="{value}")')
                elif field == "name":
                    lines.append(f'    → For contacts: get_contacts_tool(query="{value}")')

        # === CRITICAL INSTRUCTION ===
        lines.append("\n" + "-" * 60)
        lines.append("CRITICAL: These items are ALREADY RESOLVED from conversation history.")
        lines.append(
            "DO NOT generate any 'resolve' or 'get_reference' tool - use values above DIRECTLY."
        )
        lines.append("-" * 60)

        return "\n".join(lines)

    def _format_value(self, value: Any, max_length: int = 200) -> str | None:
        """
        Format a value for LLM-readable output.

        Handles nested dicts, dates, lists, and truncation.
        Returns None for empty/None values.
        """
        if value is None:
            return None

        # Handle nested dict (e.g., start: {dateTime, formatted})
        if isinstance(value, dict):
            # Prefer formatted version
            if "formatted" in value:
                return str(value["formatted"])[:max_length]
            if "dateTime" in value:
                return str(value["dateTime"])[:max_length]
            if "displayName" in value:
                return str(value["displayName"])[:max_length]
            if "email" in value:
                return str(value["email"])[:max_length]
            # For small dicts, show as JSON
            if len(value) <= 3:
                try:
                    import json

                    return json.dumps(value, ensure_ascii=False)[:max_length]
                except Exception:
                    return str(value)[:max_length]
            return f"{{...{len(value)} fields}}"

        # Handle lists
        if isinstance(value, list):
            if not value:
                return None
            if len(value) <= 3:
                items = [self._format_value(v, max_length=50) or str(v)[:50] for v in value]
                return f"[{', '.join(items)}]"[:max_length]
            first_items = [self._format_value(v, max_length=30) or str(v)[:30] for v in value[:2]]
            return f"[{', '.join(first_items)}, ... +{len(value)-2} more]"

        # Handle strings and primitives
        value_str = str(value)
        if not value_str or value_str in ("None", "null", ""):
            return None
        if len(value_str) > max_length:
            return value_str[:max_length] + "..."
        return value_str


# =============================================================================
# REFERENCE RESOLVER SERVICE
# =============================================================================


class ReferenceResolver:
    """
    Extracts and resolves linguistic references to previous results.

    Works with English patterns only (Semantic Pivot translates all queries to English).
    Domain-agnostic - works with any type of results (emails, contacts, events, files, etc.).

    Patterns:
    - Ordinals: "the first", "the second", "the 3rd"
    - Demonstratives: "this event", "that one" (TRUE anaphoric references)
    - Comparative: "the next one", "another"

    CRITICAL DISTINCTION (2026-01-03):
    - "this/that + NOUN" = demonstrative = anaphoric reference (points to existing item)
    - "the + NOUN" = definite article = search subject (what user wants to FIND)

    Example: "search for the restaurant of this appointment"
    - "this appointment" = TRUE reference (the appointment we already have) → DETECTED
    - "the restaurant" = search subject (what user wants to find) → NOT DETECTED

    Usage:
        resolver = get_reference_resolver()
        refs = resolver.extract_references("details of the first")
        if refs.has_explicit():
            # Resolve references to actual items
            ...
    """

    # =========================================================================
    # ORDINAL PATTERNS (English only)
    # =========================================================================
    # Pattern: (regex_pattern, resolved_index)
    # index=None means dynamic (extract from match)
    ORDINAL_PATTERNS: list[tuple[str, int | None]] = [
        (r"the\s*(?:1st|first)\b", 0),
        (r"the\s*(?:2nd|second)\b", 1),
        (r"the\s*(?:3rd|third)\b", 2),
        (r"the\s*(?:4th|fourth)\b", 3),
        (r"the\s*(?:5th|fifth)\b", 4),
        (r"the\s*(?:last)\b", -1),
        (r"the\s*(\d+)(?:st|nd|rd|th)?\b", None),  # Dynamic: "the 6th"
    ]

    # =========================================================================
    # DEMONSTRATIVE PATTERNS (English only)
    # =========================================================================
    # These are TRUE anaphoric references - they point to items we already have
    #
    # IMPORTANT: "the + NOUN" patterns are intentionally NOT included here
    # "the restaurant" in "search for the restaurant of this appointment"
    # is the SEARCH SUBJECT, not a reference to an existing item.
    # Including them caused over-aggressive query cleaning, breaking domain detection.
    DEMONSTRATIVE_PATTERNS: list[tuple[str, int]] = [
        # Demonstrative determiners (singular): "this event", "that contact"
        (r"\bthis\s+\w+", 0),
        (r"\bthat\s+\w+", 0),
        # Demonstrative determiners (plural): "these emails", "those contacts"
        (r"\bthese\s+\w+", 0),
        (r"\bthose\s+\w+", 0),
        # Demonstrative pronouns: "this one", "that one"
        (r"\bthis\s+one\b", 0),
        (r"\bthat\s+one\b", 0),
    ]

    # =========================================================================
    # COMPARATIVE PATTERNS (English only)
    # =========================================================================
    # Pattern: (regex_pattern, relation)
    # FIX 2025-12-26: Only match when followed by reference words, not "3 days"
    # "the next one" = reference ✅, "the next 3 days" = time duration ❌
    COMPARATIVE_PATTERNS: list[tuple[str, str]] = [
        (r"\banother\b", "other"),
        (r"\bthe\s+next\s+(?:one|result|item|contact|email|event)\b", "next"),
        (r"\bthe\s+previous\s+(?:one|result|item|contact|email|event)\b", "previous"),
    ]

    def __init__(self, settings: Settings | None = None):
        """
        Initialize ReferenceResolver.

        Args:
            settings: Optional settings. Uses global settings if not provided.
        """
        self.settings = settings or get_settings()

    def extract_references(self, query: str, english_only: bool = False) -> ExtractedReferences:
        """
        Extract all linguistic references from a query.

        Args:
            query: User query text (should be English after Semantic Pivot).
            english_only: Deprecated parameter, kept for backward compatibility.
                         All patterns are now English-only by design.

        Returns:
            ExtractedReferences containing all found references.

        Example:
            >>> resolver = ReferenceResolver()
            >>> refs = resolver.extract_references("details of the first one")
            >>> refs.references[0].type
            'ordinal'
            >>> refs.references[0].index
            0
        """
        references: list[ExtractedReference] = []
        query_lower = query.lower()

        # === ORDINAL PATTERNS ===
        # MULTI-ORDINAL FIX (2026-01-01): Use finditer to find ALL ordinals in query
        # "get details of the first and the second" → [0, 1]
        # Deduplicate by position to avoid "first" and "1st" matching the same location
        matched_positions: set[int] = set()

        for pattern, index in self.ORDINAL_PATTERNS:
            for match in re.finditer(pattern, query_lower):
                # Skip if we already matched at this position
                if match.start() in matched_positions:
                    continue

                matched_positions.add(match.start())

                # Handle dynamic index extraction
                resolved_index = index
                if index is None and match.groups():
                    try:
                        resolved_index = int(match.group(1)) - 1  # 1-based to 0-based
                    except (ValueError, IndexError):
                        resolved_index = 0

                references.append(
                    ExtractedReference(
                        type="ordinal",
                        text=match.group(0),
                        index=resolved_index,
                        pattern=pattern,
                    )
                )

        # Sort ordinal references by position in query to preserve user intent order
        ordinal_refs = [r for r in references if r.type == "ordinal"]
        other_refs = [r for r in references if r.type != "ordinal"]
        ordinal_refs.sort(key=lambda r: query_lower.find(r.text.lower()))
        references = ordinal_refs + other_refs

        # === DEMONSTRATIVE PATTERNS ===
        for pattern, index in self.DEMONSTRATIVE_PATTERNS:
            match = re.search(pattern, query_lower)  # type: ignore[assignment]
            if match:
                references.append(
                    ExtractedReference(
                        type="demonstrative",
                        text=match.group(0),
                        index=index,
                        pattern=pattern,
                    )
                )

        # === COMPARATIVE PATTERNS ===
        for pattern, _relation in self.COMPARATIVE_PATTERNS:
            match = re.search(pattern, query_lower)  # type: ignore[assignment]
            if match:
                references.append(
                    ExtractedReference(
                        type="comparative",
                        text=match.group(0),
                        index=None,  # Comparative needs context to resolve
                        pattern=pattern,
                    )
                )

        # Log extraction results
        if references:
            logger.debug(
                "references_extracted",
                query_preview=query[:50],
                reference_count=len(references),
                types=[r.type for r in references],
            )

        return ExtractedReferences(references=references)

    def has_references(self, query: str) -> bool:
        """
        Quick check if query contains any references.

        Args:
            query: User query text.

        Returns:
            True if query contains references, False otherwise.
        """
        return self.extract_references(query).has_explicit()

    def resolve_ordinal_to_item(
        self,
        ordinal_index: int,
        candidates: list[Any],
    ) -> tuple[Any | None, float]:
        """
        Resolve an ordinal index to a specific item from candidates.

        Args:
            ordinal_index: 0-based index, or -1 for last item.
            candidates: List of candidate items.

        Returns:
            Tuple of (resolved_item, confidence).
            Returns (None, 0.0) if resolution fails.

        Example:
            >>> resolver = ReferenceResolver()
            >>> items = [{"id": 1}, {"id": 2}, {"id": 3}]
            >>> item, conf = resolver.resolve_ordinal_to_item(1, items)
            >>> item["id"]
            2
        """
        if not candidates:
            return None, 0.0

        # Handle negative index (last item)
        if ordinal_index == -1:
            return candidates[-1], 1.0

        # Handle out of bounds
        if ordinal_index < 0 or ordinal_index >= len(candidates):
            logger.debug(
                "ordinal_out_of_bounds",
                ordinal_index=ordinal_index,
                candidates_count=len(candidates),
            )
            return None, 0.0

        return candidates[ordinal_index], 1.0


# =============================================================================
# SINGLETON PATTERN
# =============================================================================

_resolver_instance: ReferenceResolver | None = None


def get_reference_resolver() -> ReferenceResolver:
    """
    Get singleton ReferenceResolver instance.

    Returns:
        Global ReferenceResolver instance.

    Usage:
        resolver = get_reference_resolver()
        refs = resolver.extract_references(query)
    """
    global _resolver_instance
    if _resolver_instance is None:
        _resolver_instance = ReferenceResolver()
    return _resolver_instance


def reset_reference_resolver() -> None:
    """
    Reset singleton instance (for testing).

    Usage in tests:
        reset_reference_resolver()
        resolver = get_reference_resolver()  # Fresh instance
    """
    global _resolver_instance
    _resolver_instance = None
