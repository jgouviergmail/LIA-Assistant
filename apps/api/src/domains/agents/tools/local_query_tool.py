"""
LocalQueryEngineTool - Declarative query execution on Data Registry data.

Allows the LLM to generate JSON queries that are executed deterministically
on accumulated Registry items, enabling cross-domain analysis without
requiring new tools for each use case.

Key Differences from Other Tools:
- Does NOT use OAuth or API clients
- Does NOT need ToolRuntime for external access
- Operates purely on in-memory Registry data
- Data is injected by parallel_executor via injected_registry_items

Architecture:
    Planner generates ExecutionStep with LocalQuery
         ↓
    parallel_executor injects accumulated_registry into injected_registry_items
         ↓
    local_query_engine_tool receives data + query
         ↓
    QueryExecutor runs deterministic query
         ↓
    UnifiedToolOutput returned

Security:
- No eval/exec - declarative DSL only
- Pydantic validation - strict schema enforcement
- Read-only - no mutation of source data
- No external access - operates on provided data only

Data Registry Integration:
    Query results are registered in ContextTypeRegistry to enable:
    - Contextual references to filtered/aggregated results
    - Data persistence for response_node
    - Cross-domain queries composition

Usage in Planner:
    {
        "step_id": "find_duplicates",
        "step_type": "TOOL",
        "agent_name": "query_agent",
        "tool_name": "local_query_engine_tool",
        "parameters": {
            "source": "registry",
            "query": {
                "operation": "similarity",
                "target_type": "CONTACT",
                "similarity_field": "payload.names",
                "similarity_threshold": 0.85
            },
            "output_as_registry": true
        },
        "depends_on": ["search_contacts"]
    }
"""

from typing import Annotated, Any

import structlog
from langchain_core.tools import InjectedToolArg, tool
from pydantic import BaseModel

from src.core.config import get_settings
from src.domains.agents.constants import AGENT_QUERY, CONTEXT_DOMAIN_QUERY, TOOL_LOCAL_QUERY_ENGINE
from src.domains.agents.context.registry import ContextTypeDefinition, ContextTypeRegistry
from src.domains.agents.data_registry.models import RegistryItem
from src.domains.agents.orchestration.query_engine import (
    AggregateFunction,
    LocalQuery,
    QueryExecutor,
    QueryOperation,
)
from src.domains.agents.tools.output import UnifiedToolOutput
from src.domains.agents.utils.rate_limiting import rate_limit
from src.infrastructure.observability.decorators import track_tool_metrics
from src.infrastructure.observability.metrics_agents import (
    agent_tool_duration_seconds,
    agent_tool_invocations,
)

logger = structlog.get_logger(__name__)


# ============================================================================
# DATA REGISTRY INTEGRATION
# ============================================================================


class QueryResultItem(BaseModel):
    """Schema for LocalQueryEngine result data in context registry."""

    query_id: str  # Unique query identifier
    operation: str  # Query operation (filter, sort, group, etc.)
    total: int  # Total results count
    summary: str = ""  # Human-readable summary


# Register Query context type for Data Registry support
# This enables contextual references to query results
ContextTypeRegistry.register(
    ContextTypeDefinition(
        domain=CONTEXT_DOMAIN_QUERY,
        agent_name=AGENT_QUERY,
        item_schema=QueryResultItem,
        primary_id_field="query_id",
        display_name_field="summary",
        reference_fields=["operation", "summary"],
        icon="🔍",
    )
)


@tool
@track_tool_metrics(
    tool_name=TOOL_LOCAL_QUERY_ENGINE,
    agent_name=AGENT_QUERY,
    duration_metric=agent_tool_duration_seconds,
    counter_metric=agent_tool_invocations,
)
@rate_limit(
    max_calls=lambda: get_settings().rate_limit_default_read_calls,
    window_seconds=lambda: get_settings().rate_limit_default_read_window,
    scope="user",
)
async def local_query_engine_tool(
    query: dict[str, Any],
    injected_registry_items: Annotated[list[Any], InjectedToolArg] = None,
    source: str = "registry",
    output_as_registry: bool = True,
) -> UnifiedToolOutput:
    """
    Execute a declarative query on Data Registry data.

    This tool allows filtering, sorting, grouping, similarity detection,
    and aggregation on accumulated Registry items without requiring
    external API calls.

    IMPORTANT: This tool operates on data from PREVIOUS steps.
    Use depends_on to ensure data is available before querying.

    Args:
        query: JSON query definition with:
            - operation: "filter" | "sort" | "group" | "similarity" | "aggregate"
            - target_type: "CONTACT" | "EMAIL" | "EVENT" (optional filter)
            - conditions: List of filter conditions (for filter/sort)
            - group_by: Field path (for group)
            - sort_by, sort_order: Field and direction (for sort)
            - similarity_field, similarity_threshold: (for similarity)
            - aggregate_fn, aggregate_field: (for aggregate)
            - limit, offset: Pagination

        injected_registry_items: Injected by parallel_executor (DO NOT SET)
            Contains accumulated RegistryItem objects from previous steps.

        source: Data source identifier:
            - "registry": All accumulated registry items (default)
            - "step:<step_id>": Items from a specific step (future)

        output_as_registry: Whether to include filtered items in registry_updates
            - True: Items are added to registry for frontend rendering
            - False: Only summary returned (for intermediate queries)

    Returns:
        UnifiedToolOutput with:
        - summary_for_llm: Human-readable summary of results
        - registry_updates: Filtered items (if output_as_registry=True)
        - tool_metadata: Query stats, distinct_values (for cross-domain)

    Examples:

    1. Filter contacts by email domain:
        {
            "operation": "filter",
            "target_type": "CONTACT",
            "conditions": [
                {"field": "payload.emailAddresses[0].value", "operator": "ends_with", "value": "@gmail.com"}
            ]
        }

    2. Find duplicate contacts by similar names:
        {
            "operation": "similarity",
            "target_type": "CONTACT",
            "similarity_field": "payload.names",
            "similarity_threshold": 0.85
        }

    3. Get distinct event dates (for cross-domain NOT_IN):
        {
            "operation": "aggregate",
            "target_type": "EVENT",
            "aggregate_fn": "distinct",
            "aggregate_field": "payload.start.date"
        }

    4. Sort emails by date descending:
        {
            "operation": "sort",
            "target_type": "EMAIL",
            "sort_by": "payload.internalDate",
            "sort_order": "desc",
            "limit": 10
        }

    Cross-Domain Pattern:
        Step 1: Get distinct dates from events
        Step 2: Filter weather for dates NOT_IN events
        The aggregate result exposes distinct_values in tool_metadata
        which can be referenced via $steps.<step_id>.distinct_values

    Note:
        - This tool is READ-ONLY
        - Operates on in-memory data only (no API calls)
        - Query validation via Pydantic (invalid queries rejected)
        - Similarity uses Levenshtein (syntactic, not semantic)
    """
    try:
        # 1. Validate query schema (Pydantic does the heavy lifting)
        try:
            parsed_query = LocalQuery(**query) if isinstance(query, dict) else query
        except Exception as e:
            logger.error(
                "local_query_invalid_schema",
                error=str(e),
                query=query,
            )
            return UnifiedToolOutput.failure(
                message=f"Query validation failed: {e}",
                error_code="query_validation_error",
                metadata={"error": str(e)},
            )

        # 2. Get registry items (injected by parallel_executor)
        registry_items = injected_registry_items or []

        if not registry_items:
            logger.warning(
                "local_query_no_registry_data",
                source=source,
                operation=parsed_query.operation.value,
            )
            return UnifiedToolOutput.failure(
                message="No registry data available. Ensure previous tools have populated the registry before using local_query_engine.",
                error_code="no_registry_data",
                metadata={"source": source},
            )

        logger.info(
            "local_query_execution_started",
            operation=parsed_query.operation.value,
            target_type=parsed_query.target_type.value if parsed_query.target_type else None,
            items_count=len(registry_items),
            conditions_count=len(parsed_query.conditions),
        )

        # 3. Execute query
        try:
            executor = QueryExecutor(registry_items)
            result = executor.execute(parsed_query)
        except Exception as e:
            logger.error(
                "local_query_execution_error",
                error=str(e),
                operation=parsed_query.operation.value,
                exc_info=True,
            )
            return UnifiedToolOutput.failure(
                message=f"Query execution failed: {e}",
                error_code="query_execution_error",
                metadata={"error": str(e)},
            )

        # 4. Build summary based on operation
        summary = _build_query_summary(parsed_query, result)

        # 5. Build registry_updates if requested
        registry_updates: dict[str, RegistryItem] = {}
        if output_as_registry and result.items:
            # For aggregations, items might be primitives (count, distinct list)
            # Only add to registry if items are actual RegistryItems
            if parsed_query.operation not in (QueryOperation.AGGREGATE, QueryOperation.GROUP):
                for item in result.items:
                    item_id = _extract_item_id(item)
                    if item_id and hasattr(item, "type"):
                        registry_updates[item_id] = item
                    elif isinstance(item, dict) and "id" in item:
                        # Already serialized RegistryItem dict
                        registry_updates[item["id"]] = item

        # 6. Build tool_metadata with cross-domain support
        tool_metadata = {
            "operation": parsed_query.operation.value,
            "total": result.total,
            "returned": len(result.items),
            "meta": result.meta,
        }

        # Expose distinct_values for cross-domain queries
        if result.meta.get("distinct_values") is not None:
            tool_metadata["distinct_values"] = result.meta["distinct_values"]

        # =================================================================
        # FIX Issue #dupond-15h55: Expose groups for GROUP operation
        # =================================================================
        # Problem: Planner generates Jinja templates like:
        #   {% for group in steps.group_by_address.groups %}
        # But groups were not exposed in tool_metadata/structured_data.
        #
        # Solution: Add result.items (list of {key, items, count}) to
        # tool_metadata["groups"] so parallel_executor can expose it
        # in structured_data for Jinja templates.
        # =================================================================
        if parsed_query.operation == QueryOperation.GROUP:
            tool_metadata["groups"] = result.items
            logger.info(
                "local_query_groups_exposed",
                operation="group",
                groups_count=len(result.items),
                group_keys=[g.get("key") for g in result.items] if result.items else [],
            )

        logger.info(
            "local_query_execution_completed",
            operation=parsed_query.operation.value,
            total=result.total,
            returned=len(result.items),
            registry_items_added=len(registry_updates),
        )

        return UnifiedToolOutput.data_success(
            message=summary,
            registry_updates=registry_updates,
            metadata=tool_metadata,
        )

    except Exception as e:
        logger.error(
            "local_query_unexpected_error",
            error=str(e),
            query=query,
            exc_info=True,
        )
        return UnifiedToolOutput.failure(
            message=f"Unexpected error: {e}",
            error_code="unexpected_error",
            metadata={"error": str(e)},
        )


def _build_query_summary(query: LocalQuery, result: Any) -> str:
    """Build human-readable summary based on query operation."""
    operation = query.operation
    total = result.total

    match operation:
        case QueryOperation.FILTER:
            conditions_desc = f" ({len(query.conditions)} conditions)" if query.conditions else ""
            type_desc = f" of type {query.target_type.value}" if query.target_type else ""
            return f"Filter{conditions_desc}: found {total} items{type_desc}"

        case QueryOperation.SORT:
            order_desc = "ascending" if query.sort_order == "asc" else "descending"
            return f"Sorted {total} items by {query.sort_by} ({order_desc})"

        case QueryOperation.GROUP:
            groups_count = result.meta.get("groups_count", 0)
            return f"Grouped items by {query.group_by}: {groups_count} groups"

        case QueryOperation.SIMILARITY:
            field = query.similarity_field or "unknown"
            threshold = query.similarity_threshold
            return f"Similarity on {field} (threshold {threshold}): found {total} similar items"

        case QueryOperation.AGGREGATE:
            fn = query.aggregate_fn.value if query.aggregate_fn else "unknown"
            field = query.aggregate_field or "items"

            if query.aggregate_fn == AggregateFunction.DISTINCT:
                distinct_values = result.meta.get("distinct_values", [])
                if isinstance(distinct_values, list):
                    if len(distinct_values) <= 5:
                        values_preview = ", ".join(str(v) for v in distinct_values)
                    else:
                        values_preview = f"{', '.join(str(v) for v in distinct_values[:5])}... (+{len(distinct_values) - 5} more)"
                    return f"Distinct values of {field}: {values_preview}"
                return f"Distinct values of {field}: {distinct_values}"

            if result.items:
                value = result.items[0]
                return f"{fn.upper()}({field}): {value}"
            return f"{fn.upper()}({field}): no result"

        case _:
            return f"Query completed: {total} results"


def _extract_item_id(item: Any) -> str | None:
    """Extract item ID from RegistryItem or dict."""
    if hasattr(item, "id"):
        return item.id
    if isinstance(item, dict):
        return item.get("id")
    return None


# Export the tool
__all__ = ["local_query_engine_tool"]
