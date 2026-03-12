"""
LocalQueryEngine - Deterministic query execution for Data Registry items.

Provides a declarative JSON DSL that allows the LLM to generate queries
executed deterministically on accumulated Registry items. This enables
cross-domain analysis without requiring new tools for each use case.

Architecture:
    Planner generates LocalQuery JSON
         ↓
    LocalQueryEngineTool receives query
         ↓
    QueryExecutor executes on Registry data
         ↓
    StandardToolOutput returned to response_node

Security:
- No eval/exec - purely declarative DSL
- Pydantic validation - strict schema enforcement
- Read-only operations - no mutation of source data
- No network/filesystem access

Supported Operations:
- FILTER: Filter items by conditions (AND logic)
- SORT: Sort items by field value
- GROUP: Group items by field value
- SIMILARITY: Find items with similar values (Levenshtein)
- AGGREGATE: Count, sum, avg, min, max, distinct

Example Usage:
    from src.domains.agents.orchestration.query_engine import (
        QueryExecutor,
        LocalQuery,
        QueryOperation,
        ComparisonOperator,
        Condition,
    )

    # Find duplicate contacts by similar names
    query = LocalQuery(
        operation=QueryOperation.SIMILARITY,
        target_type=RegistryItemType.CONTACT,
        similarity_field="payload.names",
        similarity_threshold=0.85
    )

    executor = QueryExecutor(registry_items)
    result = executor.execute(query)
    # result.items contains contacts with similar names

Cross-Domain Pattern (V1):
    # Step 1: Get distinct dates from events
    step1 = LocalQuery(
        operation=QueryOperation.AGGREGATE,
        target_type=RegistryItemType.EVENT,
        aggregate_fn=AggregateFunction.DISTINCT,
        aggregate_field="payload.start.date"
    )

    # Step 2: Filter weather for dates NOT IN events
    step2 = LocalQuery(
        operation=QueryOperation.FILTER,
        target_type=RegistryItemType.WEATHER,
        conditions=[
            Condition(
                field="payload.date",
                operator=ComparisonOperator.NOT_IN,
                value="$steps.step1.distinct_values"  # Resolved by Planner
            )
        ]
    )

Limitations (V1):
- Conditions use AND logic only (OR via multiple queries)
- Similarity is syntactic only (no semantic/embedding)
- No JOIN operations (use NOT_IN for cross-domain)
"""

from src.domains.agents.orchestration.query_engine.executor import (
    QueryExecutor,
    QueryResult,
)
from src.domains.agents.orchestration.query_engine.models import (
    AggregateFunction,
    ComparisonOperator,
    Condition,
    LocalQuery,
    LocalQueryInput,
    QueryOperation,
    ValueType,
)

__all__ = [
    # Executor
    "QueryExecutor",
    "QueryResult",
    # Models
    "QueryOperation",
    "ComparisonOperator",
    "ValueType",
    "AggregateFunction",
    "Condition",
    "LocalQuery",
    "LocalQueryInput",
]
