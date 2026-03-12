"""
LocalQueryEngine DSL Models.

Provides Pydantic models for the declarative JSON DSL that allows the LLM
to generate queries executed deterministically on Registry data.

Security:
- No eval/exec - purely declarative DSL
- Pydantic validation - strict schema, no arbitrary fields
- Read-only operations - no mutation of source data

Usage:
    query = LocalQuery(
        operation=QueryOperation.FILTER,
        target_type=RegistryItemType.CONTACT,
        conditions=[
            Condition(field="payload.emailAddresses[0].value", operator=ComparisonOperator.CONTAINS, value="@gmail.com")
        ],
        limit=10
    )
"""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domains.agents.data_registry.models import RegistryItemType


class QueryOperation(str, Enum):
    """
    Available query operations.

    Each operation has specific semantics:
    - FILTER: Return items matching all conditions (AND logic)
    - GROUP: Group items by a field value
    - SORT: Sort items by a field
    - SIMILARITY: Find items with similar field values (Levenshtein)
    - AGGREGATE: Calculate aggregate values (count, sum, avg, min, max, distinct)
    """

    FILTER = "filter"
    GROUP = "group"
    SORT = "sort"
    SIMILARITY = "similarity"
    AGGREGATE = "aggregate"


class ComparisonOperator(str, Enum):
    """
    Comparison operators for conditions.

    Supports standard comparisons and string operations.
    """

    # Equality
    EQ = "eq"  # ==
    NE = "ne"  # !=

    # Numeric comparison
    GT = "gt"  # >
    GE = "ge"  # >=
    LT = "lt"  # <
    LE = "le"  # <=

    # String operations
    CONTAINS = "contains"  # substring match
    STARTS_WITH = "starts_with"
    ENDS_WITH = "ends_with"
    MATCHES = "matches"  # regex (simple patterns only)

    # Collection operations
    IN = "in"  # value in list
    NOT_IN = "not_in"  # value not in list (for cross-domain filtering)

    # Null checks
    IS_NULL = "is_null"
    IS_NOT_NULL = "is_not_null"


class ValueType(str, Enum):
    """
    Type hints for automatic value casting.

    AUTO (default) uses heuristics to infer type.
    Explicit types force casting before comparison.
    """

    AUTO = "auto"  # Infer type from value
    STRING = "string"
    INT = "int"
    FLOAT = "float"
    DATE = "date"  # ISO 8601 (YYYY-MM-DD)
    DATETIME = "datetime"  # ISO 8601 (YYYY-MM-DDTHH:MM:SS)
    BOOL = "bool"


class AggregateFunction(str, Enum):
    """
    Aggregate functions for AGGREGATE operation.

    DISTINCT is critical for cross-domain queries (extract unique values for NOT_IN).
    """

    COUNT = "count"
    SUM = "sum"
    AVG = "avg"
    MIN = "min"
    MAX = "max"
    DISTINCT = "distinct"  # Returns unique values - critical for cross-domain


class Condition(BaseModel):
    """
    A single condition for filtering.

    All conditions in a query are combined with AND logic.
    For OR logic, use multiple queries (V1 limitation).

    Attributes:
        field: Dot-notation path to field (e.g., "payload.emailAddresses[0].value")
        operator: Comparison operator
        value: Value to compare against (None for IS_NULL/IS_NOT_NULL)
        value_type: How to cast the value before comparison
        case_sensitive: Whether string comparisons are case-sensitive

    Example:
        Condition(
            field="payload.names",
            operator=ComparisonOperator.CONTAINS,
            value="dupont",
            case_sensitive=False
        )
    """

    field: str = Field(
        ...,
        description="Dot-notation path to field (e.g., 'payload.emailAddresses[0].value')",
    )
    operator: ComparisonOperator = Field(
        ...,
        description="Comparison operator to use",
    )
    value: Any = Field(
        default=None,
        description="Value to compare against (None for IS_NULL/IS_NOT_NULL)",
    )
    value_type: ValueType = Field(
        default=ValueType.AUTO,
        description="How to cast the value before comparison",
    )
    case_sensitive: bool = Field(
        default=True,
        description="Whether string comparisons are case-sensitive",
    )

    model_config = ConfigDict(extra="forbid")  # SECURITY: Reject unknown fields from LLM


class LocalQuery(BaseModel):
    """
    A query to execute on Registry data.

    Supports filtering, grouping, sorting, similarity detection, and aggregation.
    All queries are read-only and deterministic.

    Attributes:
        operation: Type of query operation
        target_type: Filter by registry item type (optional)
        conditions: List of conditions (AND logic)
        group_by: Field to group by (GROUP operation)
        sort_by: Field to sort by (SORT operation)
        sort_order: Ascending or descending (SORT operation)
        similarity_field: Field to compare for similarity (SIMILARITY operation)
        similarity_threshold: Minimum similarity ratio 0-1 (SIMILARITY operation)
        aggregate_fn: Aggregate function (AGGREGATE operation)
        aggregate_field: Field to aggregate (AGGREGATE operation)
        limit: Maximum results to return
        offset: Number of results to skip (pagination)

    Example - Filter contacts by email domain:
        LocalQuery(
            operation=QueryOperation.FILTER,
            target_type=RegistryItemType.CONTACT,
            conditions=[
                Condition(
                    field="payload.emailAddresses[0].value",
                    operator=ComparisonOperator.ENDS_WITH,
                    value="@gmail.com"
                )
            ],
            limit=10
        )

    Example - Find duplicate contacts by similar names:
        LocalQuery(
            operation=QueryOperation.SIMILARITY,
            target_type=RegistryItemType.CONTACT,
            similarity_field="payload.names",
            similarity_threshold=0.85
        )

    Example - Get distinct email domains:
        LocalQuery(
            operation=QueryOperation.AGGREGATE,
            target_type=RegistryItemType.EMAIL,
            aggregate_fn=AggregateFunction.DISTINCT,
            aggregate_field="payload.snippet"
        )
    """

    operation: QueryOperation = Field(
        ...,
        description="Type of query operation to perform",
    )
    target_type: RegistryItemType | None = Field(
        default=None,
        description="Filter by registry item type (CONTACT, EMAIL, EVENT, etc.)",
    )
    conditions: list[Condition] = Field(
        default_factory=list,
        description="Conditions to filter by (AND logic)",
    )

    # GROUP operation
    group_by: str | None = Field(
        default=None,
        description="Field path to group by (GROUP operation)",
    )

    # SORT operation
    sort_by: str | None = Field(
        default=None,
        description="Field path to sort by (SORT operation)",
    )
    sort_order: Literal["asc", "desc"] = Field(
        default="asc",
        description="Sort direction (SORT operation)",
    )

    # SIMILARITY operation
    similarity_field: str | None = Field(
        default=None,
        description="Field path to compare for similarity (SIMILARITY operation)",
    )
    similarity_threshold: float = Field(
        default=0.85,
        ge=0.0,
        le=1.0,
        description="Minimum similarity ratio 0-1 (SIMILARITY operation). See QUERY_ENGINE_SIMILARITY_THRESHOLD in settings.",
    )

    # AGGREGATE operation
    aggregate_fn: AggregateFunction | None = Field(
        default=None,
        description="Aggregate function to apply (AGGREGATE operation)",
    )
    aggregate_field: str | None = Field(
        default=None,
        description="Field path to aggregate (AGGREGATE operation)",
    )

    # Pagination
    limit: int | None = Field(
        default=None,
        ge=1,
        le=1000,
        description="Maximum number of results (1-1000)",
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Number of results to skip (pagination)",
    )

    model_config = ConfigDict(extra="forbid")  # SECURITY: Reject unknown fields from LLM

    @field_validator("similarity_threshold")
    @classmethod
    def validate_similarity_threshold(cls, v: float) -> float:
        """Ensure similarity threshold is in valid range."""
        if not 0.0 <= v <= 1.0:
            raise ValueError(f"similarity_threshold must be between 0 and 1, got {v}")
        return v

    @field_validator("target_type", mode="before")
    @classmethod
    def normalize_target_type(cls, v: str | None) -> str | None:
        """
        Normalize LLM-generated target_type to valid RegistryItemType enum values.

        LLMs often generate lowercase/plural variations that don't match the enum:
        - "places" → "PLACE"
        - "contacts" → "CONTACT"
        - "emails" → "EMAIL"

        This validator ensures graceful handling of these variations.
        """
        if v is None:
            return None

        # Already valid uppercase - return as-is
        if isinstance(v, str) and v.isupper():
            return v

        # Normalize: lowercase string → uppercase enum value
        v_lower = v.lower() if isinstance(v, str) else str(v).lower()

        # Map common LLM variations to enum values (plural → singular, lowercase → uppercase)
        NORMALIZATION_MAP = {
            # Plural → Singular
            "places": "PLACE",
            "contacts": "CONTACT",
            "emails": "EMAIL",
            "events": "EVENT",
            "tasks": "TASK",
            "files": "FILE",
            "calendars": "CALENDAR",
            "locations": "LOCATION",
            "weathers": "WEATHER",
            "notes": "NOTE",
            "drafts": "DRAFT",
            "charts": "CHART",
            # Lowercase singular → uppercase
            "place": "PLACE",
            "contact": "CONTACT",
            "email": "EMAIL",
            "event": "EVENT",
            "task": "TASK",
            "file": "FILE",
            "calendar": "CALENDAR",
            "location": "LOCATION",
            "weather": "WEATHER",
            "note": "NOTE",
            "draft": "DRAFT",
            "chart": "CHART",
            # Special types (new convention: domain + "s")
            "wikipedia": "WIKIPEDIA_ARTICLE",  # singular domain
            "wikipedias": "WIKIPEDIA_ARTICLE",  # domain + "s" pattern (canonical)
            "wikipedia_article": "WIKIPEDIA_ARTICLE",  # legacy singular
            "wikipedia_articles": "WIKIPEDIA_ARTICLE",  # legacy plural
            "perplexity": "SEARCH_RESULT",  # singular domain
            "perplexitys": "SEARCH_RESULT",  # domain + "s" pattern (canonical)
            "search_result": "SEARCH_RESULT",  # legacy singular
            "search_results": "SEARCH_RESULT",  # legacy plural
            "query": "SEARCH_RESULT",  # local query domain
            "querys": "SEARCH_RESULT",  # domain + "s" pattern
            "calendar_slot": "CALENDAR_SLOT",
            "calendar_slots": "CALENDAR_SLOT",
        }

        return NORMALIZATION_MAP.get(v_lower, v.upper())

    @field_validator("conditions", mode="before")
    @classmethod
    def normalize_conditions(cls, v: list | dict | None) -> list:
        """
        Normalize conditions to always be a list.

        LLMs sometimes generate a single condition as a dict instead of a list:
        - {"field": "name", "operator": "eq", "value": "John"} → [{"field": ...}]

        This validator ensures graceful handling.
        """
        if v is None:
            return []

        # Already a list - return as-is
        if isinstance(v, list):
            return v

        # Single dict → wrap in list
        if isinstance(v, dict):
            return [v]

        # Unexpected type - let Pydantic handle the error
        return v


class LocalQueryInput(BaseModel):
    """
    Input schema for LocalQueryEngineTool.

    This is the complete input that the LLM generates for the tool.

    Attributes:
        source: Where to get data from:
            - "registry": Accumulated registry items (default)
            - "step:<step_id>": Specific step output
            - "steps": All completed_steps (INTELLIPLANNER B+)
        query: The query to execute
        output_as_registry: Whether to output results as new registry items

    Example:
        LocalQueryInput(
            source="registry",
            query=LocalQuery(
                operation=QueryOperation.FILTER,
                target_type=RegistryItemType.CONTACT,
                conditions=[...]
            ),
            output_as_registry=True
        )

    Example - INTELLIPLANNER B+ (query completed_steps):
        LocalQueryInput(
            source="steps",
            query=LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(field="calendars[0].id", operator=ComparisonOperator.IS_NOT_NULL)
                ]
            )
        )
    """

    source: str = Field(
        default="registry",
        description="Data source: 'registry' for accumulated items, 'step:<step_id>' for specific step, 'steps' for all completed_steps",
    )
    query: LocalQuery = Field(
        ...,
        description="The query to execute",
    )
    output_as_registry: bool = Field(
        default=True,
        description="Whether to include filtered results in registry_updates",
    )

    model_config = ConfigDict(extra="forbid")  # SECURITY: Reject unknown fields from LLM

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        """Validate source format."""
        # INTELLIPLANNER B+: Accept "steps" for completed_steps access
        if v in ("registry", "steps"):
            return v
        if v.startswith("step:"):
            step_id = v[5:]
            if not step_id:
                raise ValueError("step:<step_id> requires a non-empty step_id")
            return v
        raise ValueError(f"Invalid source '{v}'. Must be 'registry', 'steps', or 'step:<step_id>'")


class QueryResult(BaseModel):
    """
    Result of executing a LocalQuery.

    Attributes:
        items: List of matching items (or aggregated results)
        total: Total count before pagination
        meta: Additional metadata about the query execution
    """

    items: list[Any] = Field(
        default_factory=list,
        description="Matching items or aggregated results",
    )
    total: int = Field(
        default=0,
        description="Total count before pagination",
    )
    meta: dict[str, Any] = Field(
        default_factory=dict,
        description="Query execution metadata",
    )


# Exports
__all__ = [
    "QueryOperation",
    "ComparisonOperator",
    "ValueType",
    "AggregateFunction",
    "Condition",
    "LocalQuery",
    "LocalQueryInput",
    "QueryResult",
]
