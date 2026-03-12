"""
LangChain v1 tools for Perplexity AI operations.

LOT 10: Perplexity API integration for advanced web search and Q&A.

Note: Perplexity uses API key authentication (not OAuth).
User-specific API keys are retrieved from the database via ConnectorService.

API Reference:
- https://docs.perplexity.ai/guides/getting-started

Architecture:
- Uses APIKeyConnectorTool base class for user-specific API key retrieval
- API keys stored encrypted in database per user
- Falls back to error message if user hasn't configured connector

Features:
- Real-time web search with AI synthesis
- Citations from authoritative sources
- Support for recency filtering (day, week, month, year)

Data Registry Integration:
    Perplexity results are registered in ContextTypeRegistry to enable:
    - Contextual references ("the search result", "those citations")
    - Data persistence for response_node
    - Cross-domain queries with LocalQueryEngine
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import settings
from src.core.time_utils import get_current_datetime_context
from src.domains.agents.constants import (
    AGENT_PERPLEXITY,
    AGENT_QUERY,
    CONTEXT_DOMAIN_PERPLEXITY,
)
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
    generate_registry_id,
)
from src.domains.agents.tools.base import APIKeyConnectorTool
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.connectors.clients.perplexity_client import PerplexityClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.domains.users.service import UserService
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class PerplexitySearchItem(BaseModel):
    """Schema for Perplexity search data in context registry."""

    query: str  # Original search query
    answer: str  # AI-synthesized answer
    citations: list[str] = []  # Source URLs
    model: str = "sonar"  # Model used


# Register Perplexity context type for Data Registry support
# This enables contextual references like "the search result", "those citations"
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_PERPLEXITY,
        agent_name=AGENT_PERPLEXITY,
        item_schema=PerplexitySearchItem,
        primary_id_field="query",
        display_name_field="query",
        reference_fields=["query", "answer"],
        icon="🔎",
    )
)


# ============================================================================
# PERPLEXITY TOOL IMPLEMENTATION CLASSES
# ============================================================================


class PerplexityBaseTool(APIKeyConnectorTool[PerplexityClient]):
    """Base tool for Perplexity operations with user context."""

    def create_client_factory(
        self,
        user_uuid: UUID,
        credentials: APIKeyCredentials,
        connector_service: Any,
    ) -> Any:
        """
        Create factory that initializes client with user settings.

        Fetches user profile to get timezone and language preferences.
        """

        async def create_client() -> PerplexityClient:
            # Get user settings using the shared DB session
            # connector_service.db is the AsyncSession
            user_service = UserService(connector_service.db)
            user = await user_service.get_user_by_id(user_uuid)

            return self.client_class(
                api_key=credentials.api_key,
                user_id=user_uuid,
                model=settings.perplexity_search_model,
                user_timezone=user.timezone,
                user_language=user.language,
            )

        return create_client


class PerplexitySearchTool(PerplexityBaseTool):
    """Tool for web search using user's Perplexity API key."""

    connector_type = ConnectorType.PERPLEXITY
    client_class = PerplexityClient
    registry_enabled = True  # Enable Data Registry mode

    # Note: create_client_factory is inherited from PerplexityBaseTool

    def create_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
    ) -> PerplexityClient:
        """
        Create Perplexity client (synchronous fallback).

        Note: This is only used if create_client_factory is NOT used.
        In the standard flow, create_client_factory takes precedence.
        """
        return PerplexityClient(
            api_key=credentials.api_key,
            user_id=user_id,
            model=settings.perplexity_search_model,
        )

    async def execute_api_call(
        self,
        client: PerplexityClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute Perplexity search API call."""
        query = kwargs["query"]
        recency = kwargs.get("recency", "none")
        include_citations = kwargs.get("include_citations", True)

        # Convert recency filter - validate against Perplexity API accepted values
        # Valid values: day, week, month, year, or None
        VALID_RECENCY_VALUES = {"day", "week", "month", "year"}
        if recency == "none" or recency is None:
            recency_filter = None
        elif recency in VALID_RECENCY_VALUES:
            recency_filter = recency
        elif recency == "latest":
            # Map "latest" to "day" (most recent period)
            recency_filter = "day"
            logger.debug("recency_mapped", original=recency, mapped="day")
        else:
            # Unknown value - default to no filter
            logger.warning("recency_invalid_value", value=recency, using=None)
            recency_filter = None

        # Generate system prompt with current datetime context
        current_datetime = get_current_datetime_context(
            timezone_str=client.user_timezone,
            language=client.user_language,
        )
        system_prompt = f"Current date and time: {current_datetime}"

        result = await client.search(
            query=query,
            search_recency_filter=recency_filter,
            return_citations=include_citations,
            return_related_questions=True,
            system_prompt=system_prompt,
        )

        # Format response
        response_data = {
            "success": True,
            "data": {
                "answer": result.get("answer", ""),
                "citations": result.get("citations", []),
                "related_questions": result.get("related_questions", []),
                "query": query,
                "model": result.get("model", "sonar"),
            },
        }

        # Add recency info if filtered
        if recency_filter:
            response_data["data"]["recency_filter"] = recency_filter

        logger.info(
            "perplexity_search_success",
            user_id=str(user_id),
            query=query[:50] if len(query) > 50 else query,
            citations_count=len(result.get("citations", [])),
            recency=recency_filter,
            timezone=client.user_timezone,
        )

        return response_data

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format Perplexity search as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Perplexity search request failed"),
                error_code=result.get("error", "PERPLEXITY_SEARCH_ERROR"),
                metadata={"status": "error"},
            )

        data = result.get("data", {})
        query = data.get("query", "")
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        related_questions = data.get("related_questions", [])
        model = data.get("model", "sonar")

        # Generate unique ID based on query
        item_id = generate_registry_id(
            RegistryItemType.SEARCH_RESULT,
            f"perplexity_search_{query}",
        )

        # Create registry item
        registry_item = RegistryItem(
            id=item_id,
            type=RegistryItemType.SEARCH_RESULT,
            payload={
                "query": query,
                "answer": answer,
                "citations": citations,
                "related_questions": related_questions,
                "model": model,
                "source": "perplexity",
                "type": "web_search",
            },
            meta=RegistryItemMeta(
                source="perplexity",
                domain=CONTEXT_DOMAIN_PERPLEXITY,
                tool_name="perplexity_search",
            ),
        )

        # Build summary for LLM
        summary_parts = [f"Résultat de recherche Perplexity pour '{query}':\n"]
        summary_parts.append(answer)

        # Add citations if present
        if citations:
            summary_parts.append(f"\n\nSources ({len(citations)}):")
            for i, citation in enumerate(citations[:5], 1):
                summary_parts.append(f"  [{i}] {citation}")
            if len(citations) > 5:
                summary_parts.append(f"  ... et {len(citations) - 5} autres sources")

        # Add related questions if present
        if related_questions:
            summary_parts.append("\n\nQuestions connexes:")
            for q in related_questions[:3]:
                summary_parts.append(f"  - {q}")

        summary = "\n".join(summary_parts)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            metadata={
                "query": query,
                "citations_count": len(citations),
                "model": model,
                "type": "web_search",
            },
        )


class PerplexityAskTool(PerplexityBaseTool):
    """Tool for asking questions using user's Perplexity API key."""

    connector_type = ConnectorType.PERPLEXITY
    client_class = PerplexityClient
    registry_enabled = True  # Enable Data Registry mode

    # Note: create_client_factory is inherited from PerplexityBaseTool

    def create_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
    ) -> PerplexityClient:
        """Create Perplexity client (synchronous fallback)."""
        return PerplexityClient(
            api_key=credentials.api_key,
            user_id=user_id,
            model=settings.perplexity_search_model,
        )

    async def execute_api_call(
        self,
        client: PerplexityClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute Perplexity ask API call."""
        question = kwargs["question"]
        context = kwargs.get("context", "")

        # Generate current datetime context
        current_datetime = get_current_datetime_context(
            timezone_str=client.user_timezone,
            language=client.user_language,
        )
        datetime_context = f"Current date and time: {current_datetime}"

        # Build system prompt
        system_prompt_parts = [datetime_context]

        if context:
            system_prompt_parts.append(
                f"You are an expert in {context}. "
                f"Provide accurate, well-researched answers focused on this domain."
            )

        system_prompt = "\n\n".join(system_prompt_parts)

        result = await client.ask(
            question=question,
            system_prompt=system_prompt,
            temperature=0.2,
        )

        response_data = {
            "success": True,
            "data": {
                "answer": result.get("answer", ""),
                "citations": result.get("citations", []),
                "question": question,
                "model": result.get("model", "sonar"),
            },
        }

        if context:
            response_data["data"]["context"] = context

        logger.info(
            "perplexity_ask_success",
            user_id=str(user_id),
            question=question[:50] if len(question) > 50 else question,
            context=context if context else "none",
            citations_count=len(result.get("citations", [])),
            timezone=client.user_timezone,
        )

        return response_data

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format Perplexity ask as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Perplexity ask request failed"),
                error_code=result.get("error", "PERPLEXITY_ASK_ERROR"),
                metadata={"status": "error"},
            )

        data = result.get("data", {})
        question = data.get("question", "")
        answer = data.get("answer", "")
        citations = data.get("citations", [])
        context = data.get("context", "")
        model = data.get("model", "sonar")

        # Generate unique ID based on question
        item_id = generate_registry_id(
            RegistryItemType.SEARCH_RESULT,
            f"perplexity_ask_{question}",
        )

        # Create registry item
        registry_item = RegistryItem(
            id=item_id,
            type=RegistryItemType.SEARCH_RESULT,
            payload={
                "question": question,
                "answer": answer,
                "citations": citations,
                "context": context,
                "model": model,
                "source": "perplexity",
                "type": "ask",
            },
            meta=RegistryItemMeta(
                source="perplexity",
                domain=CONTEXT_DOMAIN_PERPLEXITY,
                tool_name="perplexity_ask",
            ),
        )

        # Build summary for LLM
        context_part = f" (contexte: {context})" if context else ""
        summary_parts = [f"Réponse Perplexity pour '{question}'{context_part}:\n"]
        summary_parts.append(answer)

        # Add citations if present
        if citations:
            summary_parts.append(f"\n\nSources ({len(citations)}):")
            for i, citation in enumerate(citations[:5], 1):
                summary_parts.append(f"  [{i}] {citation}")
            if len(citations) > 5:
                summary_parts.append(f"  ... et {len(citations) - 5} autres sources")

        summary = "\n".join(summary_parts)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates={item_id: registry_item},
            metadata={
                "question": question,
                "context": context,
                "citations_count": len(citations),
                "model": model,
                "type": "ask",
            },
        )


# ============================================================================
# TOOL INSTANCES (singletons - stateless, credentials fetched per request)
# ============================================================================

_perplexity_search_tool_impl = PerplexitySearchTool(
    tool_name="perplexity_search",
    operation="web_search",
)

_perplexity_ask_tool_impl = PerplexityAskTool(
    tool_name="perplexity_ask",
    operation="ask",
)


# ============================================================================
# TOOL 1: WEB SEARCH
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="perplexity_search",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def perplexity_search_tool(
    query: Annotated[str, "Search query or question to answer"],
    recency: Annotated[
        str,
        "Filter by recency: 'day', 'week', 'month', 'year', or 'none' (default: none)",
    ] = "none",
    include_citations: Annotated[bool, "Include source URLs (default: True)"] = True,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Search the web using Perplexity AI.

    Performs a real-time web search and synthesizes an answer with citations.
    Best for:
    - Current events and news
    - Facts that may have changed recently
    - Questions requiring up-to-date information
    - Research with source verification

    Args:
        query: Search query or question (e.g., "Latest AI news", "Who won the election?")
        recency: Filter results by time period:
            - "day": Last 24 hours
            - "week": Last 7 days
            - "month": Last 30 days
            - "year": Last 365 days
            - "none": No time filter (default)
        include_citations: Whether to include source URLs (default: True)
        runtime: Tool runtime (injected)

    Returns:
        Search results with synthesized answer and citations

    Examples:
        - perplexity_search("What are the latest developments in AI?")
        - perplexity_search("Stock market news today", recency="day")
        - perplexity_search("Climate change report 2024", recency="year")
    """
    return await _perplexity_search_tool_impl.execute(
        runtime,
        query=query,
        recency=recency,
        include_citations=include_citations,
    )


# ============================================================================
# TOOL 2: ASK QUESTION
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="perplexity_ask",
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def perplexity_ask_tool(
    question: Annotated[str, "Question to answer"],
    context: Annotated[
        str,
        "Optional context or domain to focus the answer (e.g., 'technology', 'finance')",
    ] = "",
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Ask a question using Perplexity AI with optional context.

    Uses Perplexity's AI to answer questions with web search backing.
    Allows custom context to focus the answer on specific domains.

    Args:
        question: Question to answer (e.g., "How does machine learning work?")
        context: Optional domain/context to focus answer (e.g., "medical", "legal")
        runtime: Tool runtime (injected)

    Returns:
        Answer with citations

    Examples:
        - perplexity_ask("What causes inflation?")
        - perplexity_ask("Best practices for REST API design", context="software engineering")
        - perplexity_ask("Treatment options for diabetes", context="medical")
    """
    return await _perplexity_ask_tool_impl.execute(
        runtime,
        question=question,
        context=context,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "perplexity_search_tool",
    "perplexity_ask_tool",
]
