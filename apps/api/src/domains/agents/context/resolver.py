"""
Generic Reference Resolver for tool context items.

Resolves user references like "2", "deuxième", "dernier", "Jean Dupond"
to actual items in context lists using multiple resolution strategies.

Strategies (priority order):
    1. Numeric index: "2", "2ème", "deuxième"
    2. Keywords: "premier", "dernier", "last"
    3. Fuzzy match: "Jean" → "Jean Dupond"

All strategies are configuration-driven via ContextTypeDefinition.reference_fields.
"""

import re
from difflib import SequenceMatcher
from typing import Any

from src.core.config import settings
from src.core.i18n_patterns import (
    get_keyword_map,
    get_ordinal_map,
    get_ordinal_suffix_patterns,
)
from src.domains.agents.context.registry import ContextTypeDefinition
from src.domains.agents.context.schemas import ResolutionResult
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


class ReferenceResolver:
    """
    Generic reference resolver for ANY context type.

    Auto-adapts resolution strategies based on ContextTypeDefinition.
    Supports multilingual ordinals and keywords (fr, en, es, de, it, zh-CN).

    Example:
        >>> definition = ContextTypeRegistry.get_definition("contacts")
        >>> resolver = ReferenceResolver(definition)
        >>> result = resolver.resolve("2ème", items)
        >>> # ResolutionResult(success=True, item={...}, confidence=1.0, match_type="index")
    """

    def __init__(self, definition: ContextTypeDefinition) -> None:
        """
        Initialize resolver with context definition.

        Loads multilingual ordinal and keyword maps from i18n_patterns module.
        All supported languages are combined for universal recognition.

        Args:
            definition: ContextTypeDefinition from registry.
        """
        self.definition = definition
        self.confidence_threshold = settings.tool_context_confidence_threshold

        # Load multilingual patterns (all languages combined for universal recognition)
        self._ordinal_map = get_ordinal_map()  # Supports: fr, en, es, de, it, zh-CN
        self._keyword_map = get_keyword_map()  # Supports: fr, en, es, de, it, zh-CN
        self._ordinal_patterns = get_ordinal_suffix_patterns()  # Regex patterns for all languages

    def resolve(self, reference: str, items: list[dict[str, Any]]) -> ResolutionResult:
        """
        Resolve reference against items using multiple strategies.

        Strategies (priority order):
        1. Numeric index ("2", "2ème")
        2. Ordinal words ("deuxième", "second")
        3. Keywords ("premier", "dernier")
        4. Fuzzy match on reference_fields

        Args:
            reference: User reference string.
            items: List of indexed items from context.

        Returns:
            ResolutionResult with resolved item or error.

        Example:
            >>> items = [
            ...     {"index": 1, "name": "Jean Dupond"},
            ...     {"index": 2, "name": "Marie Martin"},
            ... ]
            >>> result = resolver.resolve("2", items)
            >>> # Success: item = {"index": 2, "name": "Marie Martin"}
        """
        if not items:
            return ResolutionResult.error_result(
                error="no_context",
                message="Aucun item dans le contexte actuel.",
            )

        # Normalize reference: lowercase and extract meaningful words
        ref_normalized = reference.strip().lower()

        # Generic article/demonstrative extraction
        # Handles patterns like:
        # - "la première" / "the first" → ordinal (article + ordinal)
        # - "cet email" / "this contact" → demonstrative (demonstrative + noun)
        words = ref_normalized.split()
        if len(words) > 1:
            first_word = words[0]
            last_word = words[-1]
            # Priority 1: Check if FIRST word is a demonstrative/keyword (cet, this, celui-ci)
            # This handles "cet email", "this contact" patterns
            if first_word in self._keyword_map:
                ref_normalized = first_word
            # Priority 2: Check if LAST word is ordinal/keyword (e.g., "the first")
            elif last_word in self._ordinal_map or last_word in self._keyword_map:
                ref_normalized = last_word

        # Strategy 1: Numeric index
        index_result = self._parse_numeric_index(ref_normalized, len(items))
        if index_result:
            item = self._get_item_by_index(items, index_result)
            if item:
                logger.debug(
                    "reference_resolved_by_index",
                    reference=reference,
                    index=index_result,
                    context_type=self.definition.context_type,
                )
                return ResolutionResult.success_result(
                    item=item, confidence=1.0, match_type="index"
                )

        # Strategy 2: Ordinal words
        ordinal_index = self._ordinal_map.get(ref_normalized)
        if ordinal_index:
            item = self._get_item_by_index(items, ordinal_index)
            if item:
                logger.debug(
                    "reference_resolved_by_ordinal",
                    reference=reference,
                    ordinal=ref_normalized,
                    index=ordinal_index,
                    context_type=self.definition.context_type,
                )
                return ResolutionResult.success_result(
                    item=item, confidence=1.0, match_type="keyword"
                )

        # Strategy 3: Keywords (premier, dernier, last, último, etc.)
        keyword_index = self._keyword_map.get(ref_normalized)
        if keyword_index:
            item = self._get_item_by_index(items, keyword_index)
            if item:
                logger.debug(
                    "reference_resolved_by_keyword",
                    reference=reference,
                    keyword=ref_normalized,
                    actual_index=keyword_index if keyword_index > 0 else len(items),
                    context_type=self.definition.context_type,
                )
                return ResolutionResult.success_result(
                    item=item, confidence=1.0, match_type="keyword"
                )

        # Strategy 4: Fuzzy match on reference_fields
        fuzzy_result = self._fuzzy_match(reference, items)
        if fuzzy_result:
            return fuzzy_result

        # Not found
        logger.debug(
            "reference_not_resolved",
            reference=reference,
            context_type=self.definition.context_type,
            items_count=len(items),
        )

        return ResolutionResult.error_result(
            error="not_found",
            message=f"'{reference}' non trouvé dans la liste. "
            f"Utilisez un numéro (1-{len(items)}), un nom, ou 'premier'/'dernier'.",
        )

    def _parse_numeric_index(self, ref: str, max_index: int) -> int | None:
        """
        Parse numeric index from reference.

        Supports multilingual ordinal suffixes:
        - Plain numbers: "2", "10"
        - French: "2ème", "2eme", "1er", "1ère"
        - English: "1st", "2nd", "3rd", "4th"
        - Spanish: "2º", "3ª"
        - German: "2.", "3-ter"
        - Italian: "2º", "3esimo"
        - Chinese: "第2"

        Args:
            ref: Normalized reference string.
            max_index: Maximum valid index (items count).

        Returns:
            1-based index if valid, None otherwise.

        Example:
            >>> self._parse_numeric_index("2ème", 5)
            2
            >>> self._parse_numeric_index("2nd", 5)
            2
            >>> self._parse_numeric_index("10", 5)
            None  # Out of range
        """
        # Use multilingual ordinal suffix patterns
        for pattern in self._ordinal_patterns:
            match = re.match(pattern, ref)
            if match:
                index = int(match.group(1))
                # Validate range
                if 1 <= index <= max_index:
                    return index

        return None

    def _get_item_by_index(self, items: list[dict[str, Any]], index: int) -> dict[str, Any] | None:
        """
        Get item by 1-based index (supports negative for "last").

        Args:
            items: List of items.
            index: 1-based index (or -1 for last).

        Returns:
            Item if found, None otherwise.
        """
        if index == -1:
            return items[-1] if items else None

        # Find item with matching "index" field
        for item in items:
            if item.get("index") == index:
                return item

        return None

    def _fuzzy_match(self, reference: str, items: list[dict[str, Any]]) -> ResolutionResult | None:
        """
        Fuzzy match reference against reference_fields.

        Uses SequenceMatcher (Python stdlib) for string similarity.

        Args:
            reference: User reference string.
            items: List of items to search.

        Returns:
            ResolutionResult if match found above threshold, None otherwise.

        Logic:
            1. For each item, check all reference_fields
            2. Calculate similarity ratio (0.0-1.0)
            3. Track best match
            4. If confidence >= threshold → Success
            5. If multiple high-confidence matches → Ambiguous
        """
        ref_lower = reference.lower().strip()
        matches: list[tuple[dict[str, Any], float]] = []  # (item, confidence)

        for item in items:
            best_score = 0.0

            # Check all reference_fields
            for field in self.definition.reference_fields:
                value = item.get(field)

                # String fields
                if isinstance(value, str):
                    score = self._string_similarity(ref_lower, value.lower())
                    best_score = max(best_score, score)

                # List fields (emails, phones, tags)
                elif isinstance(value, list):
                    for v in value:
                        if isinstance(v, str):
                            score = self._string_similarity(ref_lower, v.lower())
                            best_score = max(best_score, score)

            # Track if above threshold
            if best_score >= self.confidence_threshold:
                matches.append((item, best_score))

        if not matches:
            return None

        # Sort by confidence (descending)
        matches.sort(key=lambda x: x[1], reverse=True)
        best_item, best_confidence = matches[0]

        # Check for ambiguity (multiple high-confidence matches)
        ambiguous_threshold = settings.hitl_fuzzy_match_ambiguity_threshold
        ambiguous_matches = [
            m
            for m in matches
            if abs(m[1] - best_confidence) <= ambiguous_threshold and m[0] != best_item
        ]

        if ambiguous_matches:
            # Ambiguous - return candidates
            candidates = [
                {
                    "index": best_item.get("index"),
                    "name": best_item.get(self.definition.display_name_field),
                    "confidence": best_confidence,
                }
            ] + [
                {
                    "index": m[0].get("index"),
                    "name": m[0].get(self.definition.display_name_field),
                    "confidence": m[1],
                }
                for m in ambiguous_matches
            ]

            logger.debug(
                "reference_ambiguous",
                reference=reference,
                candidates_count=len(candidates),
                context_type=self.definition.context_type,
            )

            return ResolutionResult.error_result(
                error="ambiguous",
                message=f"Plusieurs correspondances trouvées pour '{reference}'. "
                f"Précisez: {', '.join(c['name'] for c in candidates)}",
                candidates=candidates,
            )

        # Single best match
        logger.debug(
            "reference_resolved_by_fuzzy",
            reference=reference,
            matched_name=best_item.get(self.definition.display_name_field),
            confidence=best_confidence,
            context_type=self.definition.context_type,
        )

        return ResolutionResult.success_result(
            item=best_item, confidence=best_confidence, match_type="fuzzy"
        )

    def _string_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate string similarity using SequenceMatcher.

        Args:
            s1: First string (normalized).
            s2: Second string (normalized).

        Returns:
            Similarity ratio (0.0-1.0).

        Examples:
            >>> self._string_similarity("jean", "jean dupond")
            0.8  # High similarity (substring match)
            >>> self._string_similarity("marie", "marie martin")
            0.85
        """
        # Exact match
        if s1 == s2:
            return 1.0

        # Substring match (boost score)
        if s1 in s2 or s2 in s1:
            # Calculate ratio but boost for substring
            ratio = SequenceMatcher(None, s1, s2).ratio()
            return min(1.0, ratio + 0.2)  # Boost by 0.2

        # Standard Levenshtein-like ratio
        return SequenceMatcher(None, s1, s2).ratio()
