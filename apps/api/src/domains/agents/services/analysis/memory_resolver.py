"""
Memory Resolver - Handles memory facts retrieval and reference resolution.

This service encapsulates memory-related operations extracted from QueryAnalyzerService:
1. Memory facts retrieval via semantic search (broad, for planner context)
2. Reference extraction via lightweight LLM (identifies what needs resolution)
3. Targeted memory search per reference (precise, parallel embeddings)
4. Memory reference resolution via MemoryReferenceResolutionService

Architecture (3-phase reference resolution):
    Phase 1: LLM nano extracts references ("ma femme", "mon fils") from query
    Phase 2: Embed each reference separately → targeted memory search (parallel)
    Phase 3: LLM resolves references using targeted facts

    Phase 1 and broad memory retrieval run in parallel.
    Phase 2 searches run in parallel via asyncio.gather.

    This produces higher similarity scores than embedding the full query,
    allowing a higher search threshold and less noise.

Design Philosophy:
- SRP: Single responsibility for memory operations
- Composition: Used by QueryAnalyzerService as a component
- Fail-safe: Returns None on errors, doesn't crash the analysis pipeline
"""

import asyncio

import structlog
from langchain_core.messages import HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel, Field

from src.core.config import settings as app_settings
from src.core.constants import MEMORY_REFERENCE_EXTRACTION_TIMEOUT_SECONDS
from src.core.llm_config_helper import get_llm_config_for_agent
from src.domains.agents.prompts.prompt_loader import load_prompt
from src.domains.agents.services.memory_reference_resolution_service import (
    ResolvedReferences,
)
from src.infrastructure.llm import get_llm
from src.infrastructure.llm.invoke_helpers import enrich_config_with_node_metadata
from src.infrastructure.llm.structured_output import get_structured_output

logger = structlog.get_logger(__name__)


class _ReferenceList(BaseModel):
    """Structured output schema for memory reference extraction."""

    references: list[str] = Field(
        default_factory=list,
        description="Personal/relational references needing resolution",
    )


class MemoryResolver:
    """
    Resolves memory facts and references for query analysis.

    This service handles memory operations in two tracks:
    1. Broad retrieval: full query → semantic search → memory facts for planner
    2. Targeted resolution: extract references → per-reference search → resolve names
    """

    async def retrieve_and_resolve(
        self,
        query: str,
        user_id: str,
        config: RunnableConfig,
    ) -> tuple[list[str] | None, ResolvedReferences | None]:
        """
        Retrieve memory facts and resolve references.

        Runs broad retrieval and reference extraction in parallel.
        If references are found, performs targeted per-reference searches
        with a higher similarity threshold for precision.

        Args:
            query: User's original query
            user_id: User ID for memory retrieval
            config: RunnableConfig for callback propagation

        Returns:
            Tuple of (memory_facts, resolved_references)
            - memory_facts: List of relevant memory facts or None on error
            - resolved_references: Resolved references or None if no resolution
        """
        # Phase 1 + broad retrieval in parallel
        memory_facts, references = await asyncio.gather(
            self._retrieve_memory_facts(query, user_id, config),
            self._extract_references(query, config),
        )

        resolved_references = None

        if references:
            # Phase 2: targeted search per reference (parallel)
            targeted_facts = await self._search_memories_targeted(references, user_id, config)

            if targeted_facts:
                # Phase 3: resolve using targeted facts
                resolved_references = await self._resolve_memory_references(
                    query, targeted_facts, config
                )
            elif memory_facts:
                # Fallback: use broad facts if targeted search found nothing
                logger.info(
                    "memory_targeted_search_empty_falling_back_to_broad",
                    references=references,
                )
                resolved_references = await self._resolve_memory_references(
                    query, memory_facts, config
                )
        elif memory_facts:
            # No references extracted but we have broad facts → try resolution anyway
            # (handles cases the extraction LLM might miss)
            resolved_references = await self._resolve_memory_references(query, memory_facts, config)

        return memory_facts, resolved_references

    async def _extract_references(
        self,
        query: str,
        config: RunnableConfig,
    ) -> list[str]:
        """
        Extract personal/relational references that need identity resolution.

        Uses a lightweight LLM call to identify references like "ma femme",
        "mon fils", "le voisin" in the query. Language-agnostic (LLM handles
        any language).

        Args:
            query: User's original query
            config: RunnableConfig for callback propagation

        Returns:
            List of reference strings as they appear in the query, or empty list.
        """
        if not query:
            return []

        try:
            prompt_template = load_prompt("memory_reference_extraction_prompt", version="v1")
            prompt_text = prompt_template.format(query=query)

            llm = get_llm("memory_reference_extraction")
            agent_config = get_llm_config_for_agent(app_settings, "memory_reference_extraction")
            enriched_config = enrich_config_with_node_metadata(
                config, "memory_reference_extraction"
            )

            result = await asyncio.wait_for(
                get_structured_output(
                    llm=llm,
                    messages=[HumanMessage(content=prompt_text)],
                    schema=_ReferenceList,
                    provider=agent_config.provider,
                    node_name="memory_reference_extraction",
                    config=enriched_config,
                ),
                timeout=MEMORY_REFERENCE_EXTRACTION_TIMEOUT_SECONDS,
            )

            references = result.references if result else []

            if references:
                logger.info(
                    "memory_references_extracted",
                    query_preview=query[:80],
                    references=references,
                    count=len(references),
                )
            else:
                logger.debug(
                    "memory_no_references_detected",
                    query_preview=query[:80],
                )

            return references

        except TimeoutError:
            logger.warning(
                "memory_reference_extraction_timeout",
                query_preview=query[:50],
            )
            return []

        except Exception as e:
            logger.warning(
                "memory_reference_extraction_failed",
                query_preview=query[:50],
                error=str(e),
                error_type=type(e).__name__,
            )
            return []

    async def _search_memories_targeted(
        self,
        references: list[str],
        user_id: str,
        config: RunnableConfig,
    ) -> list[str] | None:
        """
        Search memories for each reference separately, in parallel.

        Each reference is embedded independently and searched with a higher
        threshold than the broad search, since the embedding is more focused.

        Args:
            references: List of reference terms to search for
            user_id: User ID
            config: RunnableConfig for callback propagation

        Returns:
            Deduplicated list of memory facts, or None if none found.
        """
        from src.core.config import settings
        from src.domains.agents.middleware.memory_injection import (
            get_memory_facts_for_query,
        )

        min_score = settings.memory_min_search_score

        async def search_one(ref: str) -> list[str]:
            try:
                facts = await get_memory_facts_for_query(
                    user_id=user_id,
                    query=ref,
                    limit=3,
                    min_score=min_score,
                )
                return facts or []
            except Exception as e:
                logger.warning(
                    "memory_targeted_search_failed",
                    reference=ref,
                    error=str(e),
                )
                return []

        # All reference searches in parallel
        results = await asyncio.gather(*[search_one(ref) for ref in references])

        # Deduplicate while preserving order
        seen: set[str] = set()
        merged: list[str] = []
        for facts in results:
            for fact in facts:
                if fact not in seen:
                    seen.add(fact)
                    merged.append(fact)

        if merged:
            logger.info(
                "memory_targeted_search_complete",
                references=references,
                facts_count=len(merged),
            )

        return merged if merged else None

    async def _retrieve_memory_facts(
        self,
        query: str,
        user_id: str,
        config: RunnableConfig,
    ) -> list[str] | None:
        """
        Retrieve relevant memory facts via broad semantic search.

        Uses the full query for embedding. Results are used for:
        1. Planner context injection (general memory awareness)
        2. Fallback for reference resolution if targeted search fails

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

        Args:
            query: User's original query
            memory_facts: List of memory facts (from targeted or broad search)
            config: RunnableConfig for callback propagation

        Returns:
            ResolvedReferences with mappings, or None if resolution failed
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
