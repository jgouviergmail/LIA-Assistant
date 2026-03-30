"""
Memory Resolver - Handles memory facts retrieval and reference resolution.

This service encapsulates memory-related operations extracted from QueryAnalyzerService:
1. Memory facts retrieval via semantic search
2. Memory reference resolution via MemoryReferenceResolutionService

Design Philosophy:
- SRP: Single responsibility for memory operations
- Composition: Used by QueryAnalyzerService as a component
- Fail-safe: Returns None on errors, doesn't crash the analysis pipeline
"""

import structlog
from langchain_core.runnables import RunnableConfig

from src.domains.agents.services.memory_reference_resolution_service import (
    ResolvedReferences,
)

logger = structlog.get_logger(__name__)


class MemoryResolver:
    """
    Resolves memory facts and references for query analysis.

    This service handles two distinct memory operations:
    1. Semantic search for relevant memory facts
    2. Resolution of personal references (e.g., "my wife" → "Jane Smith")
    """

    async def retrieve_and_resolve(
        self,
        query: str,
        user_id: str,
        config: RunnableConfig,
    ) -> tuple[list[str] | None, ResolvedReferences | None]:
        """
        Retrieve memory facts and resolve references in one operation.

        Args:
            query: User's original query
            user_id: User ID for memory retrieval
            config: RunnableConfig for callback propagation

        Returns:
            Tuple of (memory_facts, resolved_references)
            - memory_facts: List of relevant memory facts or None on error
            - resolved_references: Resolved references or None if no resolution
        """
        # Step 1: Retrieve memory facts
        memory_facts = await self._retrieve_memory_facts(query, user_id, config)

        # Step 2: Resolve references using memory facts
        resolved_references = None
        if memory_facts:
            resolved_references = await self._resolve_memory_references(query, memory_facts, config)

        return memory_facts, resolved_references

    async def _retrieve_memory_facts(
        self,
        query: str,
        user_id: str,
        config: RunnableConfig,
    ) -> list[str] | None:
        """
        Retrieve relevant memory facts via semantic search.

        Uses get_memory_facts_for_query() from memory_injection middleware.
        Fail-safe: Returns None on errors.

        Args:
            query: User's query
            user_id: User ID
            config: RunnableConfig for callback propagation

        Returns:
            List of memory facts or None on error
        """
        from src.core.config import settings

        if not query:
            return None

        try:
            from src.domains.agents.middleware.memory_injection import (
                get_memory_facts_for_query,
            )

            memory_facts = await get_memory_facts_for_query(
                user_id=user_id,
                query=query,
                limit=settings.memory_max_results,
                min_score=settings.memory_min_search_score,
            )

            if memory_facts:
                logger.info(
                    "memory_facts_retrieved",
                    facts_count=len(memory_facts),
                )

            return memory_facts

        except Exception as e:
            logger.warning(
                "memory_facts_retrieval_failed",
                error=str(e),
            )
            return None

    async def _resolve_memory_references(
        self,
        query: str,
        memory_facts: list[str],
        config: RunnableConfig,
    ) -> ResolvedReferences | None:
        """
        Resolve personal references using dedicated MemoryReferenceResolutionService.

        This provides more accurate resolution than the query_analyzer LLM because
        it uses a dedicated prompt focused specifically on memory resolution.

        Args:
            query: User's original query
            memory_facts: List of memory facts from semantic search
            config: RunnableConfig for callback propagation

        Returns:
            ResolvedReferences with mappings, or None if resolution failed/disabled
        """
        from src.domains.agents.services.memory_reference_resolution_service import (
            get_memory_reference_resolution_service,
        )

        try:
            service = get_memory_reference_resolution_service()

            # Format memory facts as string for the service
            memory_facts_str = "\n".join(f"- {fact}" for fact in memory_facts)

            result = await service.resolve_pre_planner(
                query=query,
                memory_facts=memory_facts_str,
                config=config,
            )

            return result

        except Exception as e:
            logger.warning(
                "memory_reference_resolution_failed",
                query_preview=query[:50],
                error=str(e),
            )
            return None


# =============================================================================
# SINGLETON
# =============================================================================

_resolver: MemoryResolver | None = None


def get_memory_resolver() -> MemoryResolver:
    """Get singleton MemoryResolver instance."""
    global _resolver
    if _resolver is None:
        _resolver = MemoryResolver()
    return _resolver


def reset_memory_resolver() -> None:
    """Reset singleton (for testing)."""
    global _resolver
    _resolver = None


__all__ = [
    "MemoryResolver",
    "get_memory_resolver",
    "reset_memory_resolver",
]
