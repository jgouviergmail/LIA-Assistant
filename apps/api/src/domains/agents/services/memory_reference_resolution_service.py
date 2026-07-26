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

        # No PII at INFO: query text may contain names (DEBUG only)
        logger.info(
            "memory_resolution_started",
            query_length=len(query),
            memory_facts_length=len(memory_facts),
        )
        logger.debug(
            "memory_resolution_started_details",
            query_preview=query[:80],
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
                # No PII at INFO: mappings are resolved person names (DEBUG only)
                logger.info(
                    "memory_resolution_complete",
                    mappings_count=len(result.mappings),
                )
                logger.debug(
                    "memory_resolution_complete_details",
                    original_query=query[:80],
                    enriched_query=result.enriched_query[:80],
                    mappings=result.mappings,
                )
            else:
                logger.debug(
                    "memory_resolution_no_references_found",
                    query_preview=query[:80],
                )

            return result

        except TimeoutError:
            from src.core.llm_config_helper import get_llm_config_for_agent

            _cfg = get_llm_config_for_agent(self._settings, "memory_reference_resolution")
            logger.warning(
                "memory_resolution_timeout",
                query_length=len(query),
                timeout_seconds=_cfg.timeout_seconds,
            )
            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )

        except Exception as e:
            logger.error(
                "memory_resolution_error",
                query_length=len(query),
                error=str(e),
            )
            return ResolvedReferences(
                original_query=query,
                enriched_query=query,
                mappings={},
            )

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
            timeout_ms: Deprecated — timeout is now read from centralized LLM config
            base_config: RunnableConfig for callback propagation

        Returns:
            ResolvedReferences with enriched_query and mappings
        """
        import json

        from src.core.llm_config_helper import get_llm_config_for_agent

        llm = get_llm("memory_reference_resolution")

        # Load and format the new unified prompt
        prompt_template = load_prompt("memory_reference_resolution_prompt", version="v1")
        full_prompt = prompt_template.format(
            memory_facts=memory_facts[:1000],
            query=query,
        )

        config = enrich_config_with_node_metadata(base_config or {}, "memory_reference_resolution")

        # Use timeout from centralized LLM config (DB/defaults), not hardcoded setting
        llm_config = get_llm_config_for_agent(self._settings, "memory_reference_resolution")
        timeout_seconds = llm_config.timeout_seconds

        logger.debug(
            "memory_resolution_llm_input",
            query=query,
            memory_facts_truncated=memory_facts[:1000],
            prompt_length=len(full_prompt),
        )

        try:
            result = await asyncio.wait_for(
                llm.ainvoke(full_prompt, config=config),
                timeout=timeout_seconds,
            )

            # Extract response text via BaseMessage.text (LangChain Core 1.2+).
            # Handles both str content and Gemini 3.x list[dict] content blocks.
            response = result.text.strip()

            logger.debug(
                "memory_resolution_llm_raw_response",
                response_preview=response[:500],
                response_length=len(response),
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
                full_response_length=len(response) if response else 0,
                error=str(e),
            )
            logger.debug(
                "memory_resolution_json_parse_error_details",
                query_preview=query[:50],
                response_preview=response[:200] if response else "",
            )

            # Fallback: try regex extraction when JSON is malformed
            # This handles cases where apostrophes/quotes break JSON structure
            fallback_result = self._fallback_regex_extraction(response, query)
            if fallback_result.has_resolutions():
                logger.info(
                    "memory_resolution_regex_fallback_success",
                    mappings_count=len(fallback_result.mappings),
                )
                logger.debug(
                    "memory_resolution_regex_fallback_details",
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
