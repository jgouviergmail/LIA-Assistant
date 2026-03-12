"""
Memory Reference Resolution Service - Pre-Planner Entity Resolution.

Resolves implicit memory-based references (relational, temporal, contextual)
to concrete entity names BEFORE the planner generates the execution plan.

This service is complementary to reference_resolver.py which handles
contextual references (ordinals, demonstratives like "le premier", "celui-ci").

Use Cases:
    1. "recherche l'adresse de mon frère"
       → memory contains "J'ai un frère... jean dupond"
       → resolved_query: "recherche l'adresse de jean dupond"
       → mappings: {"mon frère": "jean dupond"}

    2. "envoie un email à ma femme"
       → memory contains "Mon épouse s'appelle Corinne"
       → resolved_query: "envoie un email à Corinne"
       → mappings: {"ma femme": "Corinne"}

Architecture:
    Router ──memory_facts──► MemoryReferenceResolutionService
                                     │
                                     ▼ LLM micro-call (gpt-4.1-mini)
                             ResolvedReferences
                                     │
                                     ▼
                              Planner (enriched query)

Key Features:
    - LLM-based extraction (robust, multilingual)
    - Fail-safe: returns original query if no resolution
    - Timeout protection: 500ms max, fallback to original
    - Stores mappings for natural responses ("ton frère (jean)")

Configuration:
    - NOTE: Memory reference resolution is always enabled
    - settings.memory_reference_resolution_llm_model: LLM model to use
    - settings.memory_reference_resolution_timeout_ms: Max timeout

References:
    - Related: reference_resolver.py (contextual references)
"""

import asyncio
import re
from dataclasses import dataclass, field

from langchain_core.runnables import RunnableConfig

from src.core.config import get_settings
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# DATA STRUCTURES
# =============================================================================


@dataclass
class ResolvedReferences:
    """
    Result of memory-based reference resolution.

    Attributes:
        original_query: User's original query (unchanged)
        enriched_query: Query with references replaced by resolved names
        mappings: Dict mapping references to resolved names
                  Example: {"mon frère": "jean dupond"}

    Usage:
        >>> result = ResolvedReferences(
        ...     original_query="recherche l'adresse de mon frère",
        ...     enriched_query="recherche l'adresse de jean dupond",
        ...     mappings={"mon frère": "jean dupond"},
        ... )
        >>> # Planner uses enriched_query
        >>> # Response node uses mappings for natural phrasing
    """

    original_query: str
    enriched_query: str
    mappings: dict[str, str] = field(default_factory=dict)

    def has_resolutions(self) -> bool:
        """Check if any references were resolved."""
        return len(self.mappings) > 0

    def format_for_response(self, reference: str) -> str:
        """
        Format a reference for natural response.

        Example:
            >>> result.format_for_response("mon frère")
            "ton frère (jean dupond)"

        Args:
            reference: Original reference text

        Returns:
            Natural phrasing with resolved name in parentheses
        """
        if reference in self.mappings:
            resolved = self.mappings[reference]
            # Transform possessive: "mon" → "ton", "ma" → "ta"
            display_ref = (
                reference.replace("mon ", "ton ").replace("ma ", "ta ").replace("mes ", "tes ")
            )
            return f"{display_ref} ({resolved})"
        return reference


# =============================================================================
# RELATIONAL PATTERNS
# =============================================================================

# Patterns for detecting relational references in user queries
# Format: (regex_pattern, reference_type)
# Supports French with multiple possessive forms

RELATIONAL_PATTERNS: list[tuple[str, str]] = [
    # Family - Core
    (r"\b(?:mon|ma)\s+frère\b", "brother"),
    (r"\b(?:mon|ma)\s+sœur\b", "sister"),
    (r"\b(?:mon|ma)\s+(?:femme|épouse)\b", "wife"),
    (r"\b(?:mon|ma)\s+(?:mari|époux)\b", "husband"),
    (r"\b(?:mon|ma)\s+(?:fils)\b", "son"),
    (r"\b(?:mon|ma)\s+(?:fille)\b", "daughter"),
    (r"\b(?:mon|ma)\s+(?:père|papa)\b", "father"),
    (r"\b(?:mon|ma)\s+(?:mère|maman)\b", "mother"),
    # Family - Extended
    (r"\b(?:mon|ma)\s+(?:grand-père|papy|papi)\b", "grandfather"),
    (r"\b(?:mon|ma)\s+(?:grand-mère|mamie|mamy)\b", "grandmother"),
    (r"\b(?:mon|ma)\s+(?:oncle|tonton)\b", "uncle"),
    (r"\b(?:mon|ma)\s+(?:tante|tata)\b", "aunt"),
    (r"\b(?:mon|ma)\s+(?:cousin|cousine)\b", "cousin"),
    (r"\b(?:mon|ma)\s+(?:neveu)\b", "nephew"),
    (r"\b(?:mon|ma)\s+(?:nièce)\b", "niece"),
    # Social
    (r"\b(?:mon|ma)\s+(?:ami|amie|pote|copain|copine)\b", "friend"),
    (r"\b(?:mon|ma)\s+(?:meilleur(?:e)?\s+ami(?:e)?)\b", "best_friend"),
    (r"\b(?:mon|ma)\s+(?:collègue)\b", "colleague"),
    (r"\b(?:mon|ma)\s+(?:patron|boss|chef)\b", "boss"),
    (r"\b(?:mon|ma)\s+(?:médecin|docteur)\b", "doctor"),
    (r"\b(?:mon|ma)\s+(?:dentiste)\b", "dentist"),
    (r"\b(?:mon|ma)\s+(?:avocat)\b", "lawyer"),
    (r"\b(?:mon|ma)\s+(?:comptable)\b", "accountant"),
    # Generic possessive + name (e.g., "mon ami Jean")
    (r"\b(?:mon|ma)\s+(?:ami|amie)\s+(\w+)\b", "friend_named"),
]


# =============================================================================
# SERVICE
# =============================================================================


class MemoryReferenceResolutionService:
    """
    Resolves memory-based relational references to concrete entity names.

    Uses a fast LLM micro-call to extract entity names from memory facts.
    Fail-safe: always returns original query if resolution fails.

    Thread-safe: No mutable instance state.

    Example:
        >>> service = MemoryReferenceResolutionService()
        >>> result = await service.resolve_pre_planner(
        ...     query="recherche l'adresse de mon frère",
        ...     memory_facts="J'ai un frère né en 1981 qui s'appelle jean dupond",
        ...     user_language="fr",
        ... )
        >>> result.enriched_query
        "recherche l'adresse de jean dupond"
        >>> result.mappings
        {"mon frère": "jean dupond"}
    """

    def __init__(self) -> None:
        """Initialize MemoryReferenceResolutionService."""
        self._settings = get_settings()

    async def resolve_pre_planner(
        self,
        query: str,
        memory_facts: str | None,
        user_language: str = "fr",
        config: RunnableConfig | None = None,
    ) -> ResolvedReferences:
        """
        Resolve memory-based references before planner execution.

        Uses a single LLM call to detect AND resolve personal references
        (e.g., "my wife", "mon frère") using memory facts. No hardcoded patterns.

        Args:
            query: User's original query (any language)
            memory_facts: Formatted memory facts from semantic search (or None)
            user_language: User's language code (unused, LLM handles multilingual)
            config: RunnableConfig from graph (for token tracking propagation)

        Returns:
            ResolvedReferences with:
            - original_query: Unchanged user query
            - enriched_query: Query with references replaced by names
            - mappings: Dict of reference → resolved name

        Fail-Safe Behavior:
            - If memory_facts is None/empty → returns original query
            - If LLM call fails → returns original query
            - If timeout → returns original query
        """
        # Fail-safe: no memory facts means no resolution possible
        if not memory_facts or not memory_facts.strip():
            logger.debug(
                "memory_resolution_skipped_no_facts",
                query_preview=query[:50],
            )
            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )

        logger.info(
            "memory_resolution_started",
            query_preview=query[:80],
            memory_facts_length=len(memory_facts),
        )

        try:
            # Single LLM call to detect AND resolve all references
            result = await self._resolve_all_via_llm(
                query=query,
                memory_facts=memory_facts,
                timeout_ms=self._settings.memory_reference_resolution_timeout_ms,
                base_config=config,
            )

            if result and result.mappings:
                logger.info(
                    "memory_resolution_complete",
                    original_query=query[:80],
                    enriched_query=result.enriched_query[:80],
                    mappings_count=len(result.mappings),
                    mappings=result.mappings,
                )
            else:
                logger.debug(
                    "memory_resolution_no_references_found",
                    query_preview=query[:80],
                )

            return result

        except TimeoutError:
            logger.warning(
                "memory_resolution_timeout",
                query_preview=query[:50],
                timeout_ms=self._settings.memory_reference_resolution_timeout_ms,
            )
            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )

        except Exception as e:
            logger.error(
                "memory_resolution_error",
                query_preview=query[:50],
                error=str(e),
            )
            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )

    def _detect_relational_references(self, query: str) -> list[str]:
        """
        Detect relational references in the query.

        Args:
            query: User query text

        Returns:
            List of detected reference strings (e.g., ["mon frère", "ma femme"])
        """
        detected: list[str] = []
        query_lower = query.lower()

        for pattern, _ref_type in RELATIONAL_PATTERNS:
            match = re.search(pattern, query_lower, re.IGNORECASE)
            if match:
                # Get the full matched text
                matched_text = match.group(0).strip()
                if matched_text not in detected:
                    detected.append(matched_text)

        return detected

    async def _resolve_reference_via_llm(
        self,
        reference: str,
        memory_facts: str,
        timeout_ms: int = 500,
        base_config: RunnableConfig | None = None,
    ) -> str | None:
        """
        Resolve a single reference using LLM micro-call.

        Args:
            reference: Reference to resolve (e.g., "mon frère")
            memory_facts: Memory facts to search in
            timeout_ms: Max timeout in milliseconds
            base_config: RunnableConfig from graph (for callback propagation).
                         If provided, TokenTrackingCallback and LangfuseCallback
                         are preserved for proper token counting.

        Returns:
            Resolved name (e.g., "jean dupond") or None if not found

        Raises:
            asyncio.TimeoutError: If LLM call exceeds timeout
        """
        # Get LLM for micro-call (uses configured provider/model from settings)
        llm = get_llm("memory_reference_resolution")

        # Load and format prompt from external file
        prompt_template = load_prompt("memory_reference_resolution_prompt", version="v1")
        full_prompt = prompt_template.format(
            memory_facts=memory_facts[:1000],  # Truncate to avoid token explosion
            reference=reference,
        )

        # Enrich config for proper token tracking
        # This ensures tokens are attributed to "memory_reference_resolution" node in metrics
        # CRITICAL: Use base_config (if provided) to preserve TokenTrackingCallback & LangfuseCallback
        # Without this, tokens from this LLM call are NOT counted in the final response total
        config = enrich_config_with_node_metadata(base_config or {}, "memory_reference_resolution")

        # Call with timeout
        timeout_seconds = timeout_ms / 1000.0

        try:
            result = await asyncio.wait_for(
                llm.ainvoke(full_prompt, config=config),
                timeout=timeout_seconds,
            )

            # Extract response content (ensure string)
            raw_content = result.content if hasattr(result, "content") else str(result)
            response = raw_content if isinstance(raw_content, str) else str(raw_content)
            response = response.strip()

            # Check for "NONE" or empty response
            if not response or response.upper() == "NONE":
                logger.debug(
                    "memory_resolution_llm_no_match",
                    reference=reference,
                )
                return None

            # Clean up response (remove quotes, trailing punctuation)
            response = response.strip("\"'.,;:")

            # Validate response looks like a name (at least 2 chars, no weird chars)
            if len(response) < 2 or any(c in response for c in ["[", "]", "{", "}"]):
                logger.warning(
                    "memory_resolution_invalid_response",
                    reference=reference,
                    response=response[:50],
                )
                return None

            return response

        except TimeoutError:
            raise  # Re-raise for caller to handle

        except Exception as e:
            logger.error(
                "memory_resolution_llm_error",
                reference=reference,
                error=str(e),
            )
            return None

    def _fallback_regex_extraction(self, response: str, original_query: str) -> ResolvedReferences:
        """
        Fallback regex extraction when JSON parsing fails.

        Extracts resolved_query and mappings using regex patterns.
        This handles cases where apostrophes/quotes break JSON structure.

        Args:
            response: Raw LLM response (malformed JSON)
            original_query: Original user query (for fallback)

        Returns:
            ResolvedReferences with extracted data, or empty if extraction fails
        """
        if not response:
            return ResolvedReferences(
                original_query=original_query,
                enriched_query=original_query,
                mappings={},
            )

        # Extract resolved_query value
        # Pattern: "resolved_query": "..."
        resolved_query = original_query
        resolved_query_match = re.search(
            r'"resolved_query"\s*:\s*"([^"]*(?:\\"[^"]*)*)"',
            response,
        )
        if resolved_query_match:
            resolved_query = resolved_query_match.group(1)
            # Unescape JSON escapes
            resolved_query = resolved_query.replace('\\"', '"').replace("\\n", "\n")

        # Extract mappings - look for key-value pairs in the mappings object
        # Pattern: "my wife": "Jane Smith"
        mappings: dict[str, str] = {}

        # Find the mappings section
        mappings_section_match = re.search(r'"mappings"\s*:\s*\{([^}]*)', response)
        if mappings_section_match:
            mappings_content = mappings_section_match.group(1)

            # Extract individual key-value pairs
            # Pattern: "key": "value"
            pair_pattern = re.compile(r'"([^"]+)"\s*:\s*"([^"]*)"')
            for match in pair_pattern.finditer(mappings_content):
                key = match.group(1)
                value = match.group(2)
                # Unescape JSON escapes
                key = key.replace('\\"', '"')
                value = value.replace('\\"', '"')
                mappings[key] = value

        return ResolvedReferences(
            original_query=original_query,
            enriched_query=resolved_query,
            mappings=mappings,
        )

    async def _resolve_all_via_llm(
        self,
        query: str,
        memory_facts: str,
        timeout_ms: int = 1000,
        base_config: RunnableConfig | None = None,
    ) -> ResolvedReferences:
        """
        Single LLM call to detect AND resolve all personal references.

        Uses a JSON-output prompt that instructs the LLM to:
        1. Detect personal references (my wife, mon frère, etc.)
        2. Resolve them using memory facts
        3. Return both the enriched query and mappings

        Args:
            query: User query (any language)
            memory_facts: Memory facts to search in
            timeout_ms: Max timeout in milliseconds
            base_config: RunnableConfig for callback propagation

        Returns:
            ResolvedReferences with enriched_query and mappings
        """
        import json

        llm = get_llm("memory_reference_resolution")

        # Load and format the new unified prompt
        prompt_template = load_prompt("memory_reference_resolution_prompt", version="v1")
        full_prompt = prompt_template.format(
            memory_facts=memory_facts[:1000],
            query=query,
        )

        config = enrich_config_with_node_metadata(base_config or {}, "memory_reference_resolution")
        timeout_seconds = timeout_ms / 1000.0

        try:
            result = await asyncio.wait_for(
                llm.ainvoke(full_prompt, config=config),
                timeout=timeout_seconds,
            )

            raw_content = result.content if hasattr(result, "content") else str(result)
            response = (
                raw_content.strip() if isinstance(raw_content, str) else str(raw_content).strip()
            )

            # Parse JSON response
            # Handle potential markdown code blocks
            if response.startswith("```"):
                response = response.split("```")[1]
                if response.startswith("json"):
                    response = response[4:]
                response = response.strip()

            parsed = json.loads(response)

            resolved_query = parsed.get("resolved_query", query)
            mappings = parsed.get("mappings", {})

            # Validate mappings is a dict
            if not isinstance(mappings, dict):
                mappings = {}

            return ResolvedReferences(
                original_query=query,
                enriched_query=resolved_query,
                mappings=mappings,
            )

        except json.JSONDecodeError as e:
            logger.warning(
                "memory_resolution_json_parse_error",
                query_preview=query[:50],
                response_preview=response[:200] if response else "",
                full_response_length=len(response) if response else 0,
                error=str(e),
            )

            # Fallback: try regex extraction when JSON is malformed
            # This handles cases where apostrophes/quotes break JSON structure
            fallback_result = self._fallback_regex_extraction(response, query)
            if fallback_result.has_resolutions():
                logger.info(
                    "memory_resolution_regex_fallback_success",
                    mappings_count=len(fallback_result.mappings),
                    mappings=fallback_result.mappings,
                )
                return fallback_result

            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )

        except TimeoutError:
            raise  # Re-raise for caller

        except Exception as e:
            logger.error(
                "memory_resolution_llm_error_unified",
                query_preview=query[:50],
                error=str(e),
            )
            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )


# =============================================================================
# SINGLETON
# =============================================================================

_service_instance: MemoryReferenceResolutionService | None = None


def get_memory_reference_resolution_service() -> MemoryReferenceResolutionService:
    """
    Get singleton MemoryReferenceResolutionService instance.

    Returns:
        Global MemoryReferenceResolutionService instance

    Usage:
        service = get_memory_reference_resolution_service()
        result = await service.resolve_pre_planner(query, memory_facts)
    """
    global _service_instance
    if _service_instance is None:
        _service_instance = MemoryReferenceResolutionService()
    return _service_instance


def reset_memory_reference_resolution_service() -> None:
    """Reset singleton instance (for testing)."""
    global _service_instance
    _service_instance = None
