"""
LangChain v1 tools for Brave Search operations.

Brave Search API integration for web and news search.

Note: Brave uses API key authentication (not OAuth).
User-specific API keys are retrieved from the database via ConnectorService.

API Reference:
- https://api.search.brave.com/app/documentation/web-search
- https://api.search.brave.com/app/documentation/news-search

Architecture:
- Uses APIKeyConnectorTool base class for user-specific API key retrieval
- API keys stored encrypted in database per user
- Falls back to error message if user hasn't configured connector

Data Registry Integration:
    Brave results are registered in ContextTypeRegistry to enable:
    - Contextual references ("the search result", "those links")
    - Data persistence for response_node
    - Cross-domain queries with LocalQueryEngine
"""

from typing import Annotated, Any
from uuid import UUID

import structlog
from langchain.tools import ToolRuntime
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.domains.agents.constants import (
    AGENT_BRAVE,
    CONTEXT_DOMAIN_BRAVE,
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
from src.domains.connectors.clients.brave_search_client import BraveSearchClient
from src.domains.connectors.models import ConnectorType
from src.domains.connectors.schemas import APIKeyCredentials
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class BraveSearchItem(BaseModel):
    """Schema for Brave Search data in context registry."""

    title: str  # Result title
    url: str  # Result URL
    description: str = ""  # Result snippet
    age: str | None = None  # Article age (news only)


# Register Brave context type for Data Registry support
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_BRAVE,
        agent_name=AGENT_BRAVE,
        item_schema=BraveSearchItem,
        primary_id_field="url",
        display_name_field="title",
        reference_fields=["title", "url", "description"],
        icon="🔍",
    )
)


# ============================================================================
# BRAVE TOOL IMPLEMENTATION CLASSES
# ============================================================================


class BraveSearchToolImpl(APIKeyConnectorTool[BraveSearchClient]):
    """Tool for web search using user's Brave Search API key."""

    connector_type = ConnectorType.BRAVE_SEARCH
    client_class = BraveSearchClient
    registry_enabled = True  # Enable Data Registry mode

    def create_client(
        self,
        credentials: APIKeyCredentials,
        user_id: UUID,
    ) -> BraveSearchClient:
        """Create Brave Search client."""
        return BraveSearchClient(
            api_key=credentials.api_key,
            user_id=user_id,
        )

    async def execute_api_call(
        self,
        client: BraveSearchClient,
        user_id: UUID,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Execute Brave Search API call."""
        query = kwargs["query"]
        endpoint = kwargs.get("endpoint", "web")
        count = kwargs.get("count", 5)
        freshness = kwargs.get("freshness")

        result = await client.search(
            query=query,
            endpoint=endpoint,
            count=count,
            freshness=freshness,
        )

        if result is None:
            return {
                "success": False,
                "message": "Brave Search API error",
                "error": "BRAVE_SEARCH_API_ERROR",
            }

        # Extract results based on endpoint
        if endpoint == "web":
            raw_results = result.get("web", {}).get("results", [])
        else:  # news
            raw_results = result.get("results", [])

        response_data = {
            "success": True,
            "data": {
                "query": query,
                "endpoint": endpoint,
                "results": raw_results,
                "total": len(raw_results),
                "requested_count": count,
            },
        }

        logger.info(
            "brave_search_success",
            user_id=str(user_id),
            query=query[:50] if len(query) > 50 else query,
            endpoint=endpoint,
            results_count=len(raw_results),
        )

        return response_data

    def format_registry_response(self, result: dict[str, Any]) -> UnifiedToolOutput:
        """Format Brave Search as Data Registry UnifiedToolOutput."""
        if not result.get("success"):
            return UnifiedToolOutput.failure(
                message=result.get("message", "Brave search request failed"),
                error_code=result.get("error", "BRAVE_SEARCH_ERROR"),
                metadata={"status": "error"},
            )

        data = result.get("data", {})
        query = data.get("query", "")
        endpoint = data.get("endpoint", "web")
        raw_results = data.get("results", [])
        requested_count = data.get("requested_count", 5)

        # Limit results to what was actually requested (LLM may ask for more than needed)
        limited_results = raw_results[:requested_count]

        # Build registry items
        registry_updates = {}
        formatted_results = []

        for i, item in enumerate(limited_results):
            item_id = generate_registry_id(
                RegistryItemType.SEARCH_RESULT,
                f"brave_{endpoint}_{query}_{i}",
            )

            brave_item = BraveSearchItem(
                title=item.get("title", ""),
                url=item.get("url", ""),
                description=item.get("description", ""),
                age=item.get("age"),
            )
            formatted_results.append(brave_item.model_dump())

            registry_item = RegistryItem(
                id=item_id,
                type=RegistryItemType.SEARCH_RESULT,
                payload={
                    **brave_item.model_dump(),
                    "source": "brave",
                    "endpoint": endpoint,
                },
                meta=RegistryItemMeta(
                    source="brave",
                    domain=CONTEXT_DOMAIN_BRAVE,
                    tool_name=f"brave_{endpoint}_search",
                ),
            )
            registry_updates[item_id] = registry_item

        # Build summary for LLM
        endpoint_label = "web" if endpoint == "web" else "actualités"
        summary_parts = [
            f"Résultats Brave Search ({endpoint_label}) pour '{query}' - {len(formatted_results)} résultat(s):\n"
        ]

        for i, item in enumerate(formatted_results, 1):
            summary_parts.append(f"  [{i}] {item['title']}")
            summary_parts.append(f"      {item['url']}")
            if item.get("description"):
                desc = item["description"][:100]
                if len(item["description"]) > 100:
                    desc += "..."
                summary_parts.append(f"      {desc}")
            if item.get("age"):
                summary_parts.append(f"      ({item['age']})")

        summary = "\n".join(summary_parts)

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            structured_data={
                "braves": formatted_results,
                "count": len(formatted_results),
                "query": query,
                "endpoint": endpoint,
            },
            metadata={
                "query": query,
                "endpoint": endpoint,
                "results_count": len(formatted_results),
            },
        )


# ============================================================================
# TOOL INSTANCES (singletons - stateless, credentials fetched per request)
# ============================================================================

_brave_search_tool_impl = BraveSearchToolImpl(
    tool_name="brave_search",
    operation="web_search",
)

_brave_news_tool_impl = BraveSearchToolImpl(
    tool_name="brave_news",
    operation="news_search",
)


# ============================================================================
# TOOL 1: WEB SEARCH
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="brave_search",
    agent_name=AGENT_BRAVE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def brave_search_tool(
    query: Annotated[str, "Search query - what to search for"],
    count: Annotated[
        int,
        "Number of results to return (1-10, default 5). Use the exact count the user requested.",
    ] = 5,
    freshness: Annotated[
        str | None,
        "Freshness filter: 'pd' (24h), 'pw' (7d), 'pm' (31d), 'py' (1y)",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Search the web using Brave Search API.

    Returns web search results with title, URL, and description.
    Use for finding information, facts, site content.

    IMPORTANT: Always respect the number of results the user asked for.
    If the user asks for "5 results", use count=5. Do not request more than needed.

    Args:
        query: Search query (e.g., "Python programming", "recette pates")
        count: Number of results to return (1-10, default: 5). Match the user's request.
        freshness: Optional freshness filter:
            - "pd": Past day (24 hours)
            - "pw": Past week (7 days)
            - "pm": Past month (31 days)
            - "py": Past year (365 days)
        runtime: Tool runtime (injected)

    Returns:
        Search results with title, URL, and description

    Examples:
        - brave_search("machine learning tutorials")
        - brave_search("restaurants paris", count=5)
        - brave_search("AI news", freshness="pw")
    """
    return await _brave_search_tool_impl.execute(
        runtime,
        query=query,
        endpoint="web",
        count=min(count, 10),
        freshness=freshness,
    )


# ============================================================================
# TOOL 2: NEWS SEARCH
# ============================================================================


@tool
@track_tool_metrics(
    tool_name="brave_news",
    agent_name=AGENT_BRAVE,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
async def brave_news_tool(
    query: Annotated[str, "News search query"],
    count: Annotated[
        int,
        "Number of news articles to return (1-10, default 5). Use the exact count the user requested.",
    ] = 5,
    freshness: Annotated[
        str | None,
        "Freshness filter: 'pd' (24h), 'pw' (7d), 'pm' (31d)",
    ] = None,
    runtime: Annotated[ToolRuntime, InjectedToolArg] = None,
) -> str:
    """
    Search news using Brave Search API.

    Returns news articles with title, URL, description, and age.
    Use for recent news, current events, articles.

    IMPORTANT: Always respect the number of results the user asked for.
    If the user asks for "5 articles", use count=5. Do not request more than needed.

    Args:
        query: News search query (e.g., "technology news", "climate change")
        count: Number of news articles to return (1-10, default: 5). Match the user's request.
        freshness: Optional freshness filter:
            - "pd": Past day (24 hours)
            - "pw": Past week (7 days)
            - "pm": Past month (31 days)
        runtime: Tool runtime (injected)

    Returns:
        News articles with title, URL, description, and age

    Examples:
        - brave_news("AI developments")
        - brave_news("stock market", freshness="pd")
        - brave_news("sports results", count=5)
    """
    return await _brave_news_tool_impl.execute(
        runtime,
        query=query,
        endpoint="news",
        count=min(count, 10),
        freshness=freshness,
    )


# ============================================================================
# EXPORTS
# ============================================================================

__all__ = [
    "brave_search_tool",
    "brave_news_tool",
    "BraveSearchItem",
]
