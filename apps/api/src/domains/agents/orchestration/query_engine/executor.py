"""
QueryExecutor - Deterministic execution engine for LocalQuery DSL.

Executes queries on Registry data without any network or filesystem access.
All operations are read-only and deterministic.

Security:
- No eval/exec - only predefined operations
- No network access - operates only on in-memory data
- No filesystem access - pure computation
- Read-only - never modifies source data

Performance:
- O(N) for filter/sort operations
- O(N²) for similarity detection (acceptable for <1000 items)
- Pagination via limit/offset

Usage:
    from src.domains.agents.orchestration.query_engine import QueryExecutor, LocalQuery

    executor = QueryExecutor(registry_items)
    result = executor.execute(query)
"""

from __future__ import annotations

import re
from datetime import date, datetime
from difflib import SequenceMatcher
from typing import Any

import structlog

from src.domains.agents.orchestration.query_engine.models import (
    AggregateFunction,
    ComparisonOperator,
    Condition,
    LocalQuery,
    QueryOperation,
    QueryResult,
    ValueType,
)

logger = structlog.get_logger(__name__)


class QueryExecutor:
    """
    Deterministic query executor for LocalQuery DSL.

    Executes filter, sort, group, similarity, and aggregate operations
    on Registry items. All operations are read-only.

    Attributes:
        _items: Source items to query (immutable during execution)

    Example:
        executor = QueryExecutor(registry_items)

        # Filter contacts by email domain
        result = executor.execute(LocalQuery(
            operation=QueryOperation.FILTER,
            target_type=RegistryItemType.CONTACT,
            conditions=[
                Condition(
                    field="payload.emailAddresses[0].value",
                    operator=ComparisonOperator.ENDS_WITH,
                    value="@gmail.com"
                )
            ]
        ))

        # Find duplicates by name similarity
        # Note: payload.names is a string (extracted displayName), not an array
        result = executor.execute(LocalQuery(
            operation=QueryOperation.SIMILARITY,
            similarity_field="payload.names",
            similarity_threshold=0.85
        ))
    """

    def __init__(self, data_items: list[Any]):
        """
        Initialize executor with source data.

        Args:
            data_items: List of RegistryItem objects or dicts to query
        """
        self._items = data_items

    def execute(self, query: LocalQuery) -> QueryResult:
        """
        Execute a LocalQuery and return results.

        Args:
            query: The query to execute

        Returns:
            QueryResult with matching items and metadata

        Raises:
            ValueError: If query is malformed
        """
        # 1. Pre-filter by type if specified
        items = self._filter_by_type(self._items, query.target_type)

        logger.debug(
            "query_execution_started",
            operation=query.operation.value,
            target_type=query.target_type.value if query.target_type else None,
            items_count=len(items),
            conditions_count=len(query.conditions),
        )

        # 2. Execute the main operation
        try:
            match query.operation:
                case QueryOperation.FILTER:
                    items = self._execute_filter(items, query.conditions)
                    meta = {"op": "filter", "conditions_applied": len(query.conditions)}

                case QueryOperation.SORT:
                    # Apply conditions first if present
                    if query.conditions:
                        items = self._execute_filter(items, query.conditions)
                    items = self._execute_sort(items, query.sort_by, query.sort_order)
                    meta = {"op": "sort", "sort_by": query.sort_by, "sort_order": query.sort_order}

                case QueryOperation.SIMILARITY:
                    items = self._execute_similarity(
                        items, query.similarity_field, query.similarity_threshold
                    )
                    meta = {
                        "op": "similarity",
                        "field": query.similarity_field,
                        "threshold": query.similarity_threshold,
                    }

                case QueryOperation.GROUP:
                    return self._execute_group(items, query.group_by)

                case QueryOperation.AGGREGATE:
                    return self._execute_aggregate(items, query.aggregate_fn, query.aggregate_field)

                case _:
                    logger.error("unknown_query_operation", operation=query.operation)
                    return QueryResult(items=[], total=0, meta={"error": "Unknown operation"})

        except Exception as e:
            logger.error(
                "query_execution_error",
                operation=query.operation.value,
                error=str(e),
                exc_info=True,
            )
            return QueryResult(items=[], total=0, meta={"error": str(e)})

        # 3. Apply pagination
        total = len(items)
        if query.offset:
            items = items[query.offset :]
        if query.limit:
            items = items[: query.limit]

        logger.debug(
            "query_execution_completed",
            operation=query.operation.value,
            total_before_pagination=total,
            returned_count=len(items),
        )

        return QueryResult(items=items, total=total, meta=meta)

    def _filter_by_type(self, items: list[Any], target_type: Any) -> list[Any]:
        """
        Filter items by RegistryItemType.

        Args:
            items: Items to filter
            target_type: RegistryItemType or None

        Returns:
            Filtered items (or all items if target_type is None)
        """
        if not target_type:
            return items

        target_type_str = target_type.value if hasattr(target_type, "value") else str(target_type)

        results = []
        for item in items:
            item_type = self._get_field_value(item, "type")
            if item_type == target_type_str:
                results.append(item)

        return results

    def _execute_filter(self, items: list[Any], conditions: list[Condition]) -> list[Any]:
        """
        Filter items by conditions (AND logic).

        Args:
            items: Items to filter
            conditions: List of conditions (all must match)

        Returns:
            Items matching all conditions
        """
        if not conditions:
            return items

        results = []
        for item in items:
            if all(self._evaluate_condition(item, c) for c in conditions):
                results.append(item)

        return results

    def _execute_sort(self, items: list[Any], field: str | None, order: str) -> list[Any]:
        """
        Sort items by a field.

        Args:
            items: Items to sort
            field: Field path to sort by
            order: "asc" or "desc"

        Returns:
            Sorted items (None values at end)
        """
        if not field:
            return items

        def sort_key(item: Any) -> tuple[bool, Any]:
            val = self._get_field_value(item, field)
            # Put None values at the end
            return (val is None, val if val is not None else "")

        try:
            return sorted(items, key=sort_key, reverse=(order == "desc"))
        except TypeError:
            # Mixed types - fall back to string comparison
            def safe_sort_key(item: Any) -> tuple[bool, str]:
                val = self._get_field_value(item, field)
                return (val is None, str(val) if val is not None else "")

            return sorted(items, key=safe_sort_key, reverse=(order == "desc"))

    def _execute_similarity(
        self, items: list[Any], field: str | None, threshold: float
    ) -> list[Any]:
        """
        Find items with similar field values using Levenshtein distance.

        O(N²) complexity - acceptable for <1000 items.

        Args:
            items: Items to compare
            field: Field path to compare
            threshold: Minimum similarity ratio (0-1)

        Returns:
            Items that have at least one similar pair
        """
        if not field:
            logger.warning("similarity_missing_field")
            return []

        # Extract (item, value) pairs where value is not None
        extracted: list[tuple[Any, str]] = []
        for item in items:
            val = self._get_field_value(item, field)
            if val is not None:
                extracted.append((item, str(val)))

        if len(extracted) < 2:
            return []

        # Find all similar pairs (O(N²))
        similar_indices: set[int] = set()
        for i, (_, val_a) in enumerate(extracted):
            for j, (_, val_b) in enumerate(extracted):
                if i >= j:  # Skip self and already-compared pairs
                    continue
                ratio = SequenceMatcher(None, val_a.lower(), val_b.lower()).ratio()
                if ratio >= threshold:
                    similar_indices.add(i)
                    similar_indices.add(j)

        logger.debug(
            "similarity_detection_complete",
            total_items=len(extracted),
            similar_items=len(similar_indices),
            threshold=threshold,
        )

        return [extracted[idx][0] for idx in sorted(similar_indices)]

    def _execute_group(self, items: list[Any], field: str | None) -> QueryResult:
        """
        Group items by a field value.

        Args:
            items: Items to group
            field: Field path to group by

        Returns:
            QueryResult with groups as items
        """
        if not field:
            logger.warning("group_missing_field")
            return QueryResult(items=[], total=0, meta={"error": "Missing group_by field"})

        groups: dict[str, list[Any]] = {}
        for item in items:
            key = str(self._get_field_value(item, field) or "_null_")
            groups.setdefault(key, []).append(item)

        # Convert to list of group dicts
        # CRITICAL: Use "members" not "items" - "items" conflicts with dict.items method in Jinja2
        # Jinja2 SandboxedEnvironment resolves .items to dict.items method, not dict["items"] key
        group_list = [{"key": k, "members": v, "count": len(v)} for k, v in groups.items()]

        return QueryResult(
            items=group_list,
            total=len(groups),
            meta={"op": "group", "group_by": field, "groups_count": len(groups)},
        )

    def _execute_aggregate(
        self, items: list[Any], fn: AggregateFunction | None, field: str | None
    ) -> QueryResult:
        """
        Execute an aggregate function.

        Args:
            items: Items to aggregate
            fn: Aggregate function (count, sum, avg, min, max, distinct)
            field: Field path to aggregate (not required for count)

        Returns:
            QueryResult with aggregated value
        """
        if not fn:
            logger.warning("aggregate_missing_function")
            return QueryResult(items=[], total=0, meta={"error": "Missing aggregate_fn"})

        # Extract values for field-based aggregations
        values: list[Any] = []
        if field:
            values = [self._get_field_value(item, field) for item in items]
            values = [v for v in values if v is not None]

        result: Any
        match fn:
            case AggregateFunction.COUNT:
                result = len(items)

            case AggregateFunction.DISTINCT:
                # Return list of unique values - CRITICAL for cross-domain queries
                result = list(set(values))

            case AggregateFunction.SUM:
                numeric_values = [v for v in values if isinstance(v, int | float)]
                result = sum(numeric_values) if numeric_values else 0

            case AggregateFunction.AVG:
                numeric_values = [v for v in values if isinstance(v, int | float)]
                result = sum(numeric_values) / len(numeric_values) if numeric_values else 0

            case AggregateFunction.MIN:
                try:
                    result = min(values) if values else None
                except TypeError:
                    # Mixed types - convert to strings
                    result = min(str(v) for v in values) if values else None

            case AggregateFunction.MAX:
                try:
                    result = max(values) if values else None
                except TypeError:
                    result = max(str(v) for v in values) if values else None

            case _:
                result = None

        return QueryResult(
            items=[result],
            total=1,
            meta={
                "op": "aggregate",
                "aggregation": fn.value if fn else None,
                "field": field,
                "distinct_values": result if fn == AggregateFunction.DISTINCT else None,
            },
        )

    def _evaluate_condition(self, item: Any, cond: Condition) -> bool:
        """
        Evaluate a single condition against an item.

        Args:
            item: Item to evaluate
            cond: Condition to check

        Returns:
            True if condition matches
        """
        raw_val = self._get_field_value(item, cond.field)
        val = self._cast_value(raw_val, cond.value_type)
        target = self._cast_value(cond.value, cond.value_type)

        # Case-insensitive string comparison
        if not cond.case_sensitive and isinstance(val, str) and isinstance(target, str):
            val = val.lower()
            target = target.lower()

        try:
            match cond.operator:
                case ComparisonOperator.EQ:
                    return val == target

                case ComparisonOperator.NE:
                    return val != target

                case ComparisonOperator.GT:
                    if val is None or target is None:
                        return False
                    return val > target

                case ComparisonOperator.GE:
                    if val is None or target is None:
                        return False
                    return val >= target

                case ComparisonOperator.LT:
                    if val is None or target is None:
                        return False
                    return val < target

                case ComparisonOperator.LE:
                    if val is None or target is None:
                        return False
                    return val <= target

                case ComparisonOperator.CONTAINS:
                    if val is None or target is None:
                        return False
                    return str(target) in str(val)

                case ComparisonOperator.STARTS_WITH:
                    if val is None:
                        return False
                    return str(val).startswith(str(target))

                case ComparisonOperator.ENDS_WITH:
                    if val is None:
                        return False
                    return str(val).endswith(str(target))

                case ComparisonOperator.MATCHES:
                    if val is None or target is None:
                        return False
                    try:
                        return bool(re.search(str(target), str(val)))
                    except re.error:
                        logger.warning("invalid_regex_pattern", pattern=target)
                        return False

                case ComparisonOperator.IN:
                    # =================================================================
                    # FIX Issue #dupond-15h55: Handle comma-separated string as list
                    # =================================================================
                    # Problem: Jinja templates produce comma-separated strings like:
                    #   "addr1,addr2,addr3"
                    # But IN operator expected a list/tuple/set.
                    #
                    # Solution: If target is a string containing commas, split it
                    # into a list. This supports planner-generated filters using
                    # GROUP results with Jinja templates.
                    # =================================================================
                    if isinstance(target, str) and "," in target:
                        target = [t.strip() for t in target.split(",") if t.strip()]
                        logger.debug(
                            "in_operator_converted_csv_to_list",
                            original_length=len(target),
                            values_preview=target[:3] if target else [],
                        )
                    if not isinstance(target, list | tuple | set):
                        return False
                    # Case-insensitive for strings if configured
                    if not cond.case_sensitive and isinstance(val, str):
                        return val.lower() in [
                            t.lower() if isinstance(t, str) else t for t in target
                        ]
                    return val in target

                case ComparisonOperator.NOT_IN:
                    # FIX Issue #dupond-15h55: Same CSV handling as IN operator
                    if isinstance(target, str) and "," in target:
                        target = [t.strip() for t in target.split(",") if t.strip()]
                    if not isinstance(target, list | tuple | set):
                        return True
                    # Case-insensitive for strings if configured
                    if not cond.case_sensitive and isinstance(val, str):
                        return val.lower() not in [
                            t.lower() if isinstance(t, str) else t for t in target
                        ]
                    return val not in target

                case ComparisonOperator.IS_NULL:
                    return val is None

                case ComparisonOperator.IS_NOT_NULL:
                    return val is not None

                case _:
                    logger.warning("unknown_comparison_operator", operator=cond.operator)
                    return False

        except (TypeError, ValueError) as e:
            logger.debug(
                "condition_evaluation_error",
                field=cond.field,
                operator=cond.operator.value,
                error=str(e),
            )
            return False

    def _get_field_value(self, item: Any, path: str) -> Any:
        """
        Get a value from an item using dot-notation path.

        Supports:
        - Simple paths: "type", "id"
        - Nested paths: "payload.emailAddresses[0].value"
        - Array access: "addresses[0]"

        Args:
            item: Item to extract value from
            path: Dot-notation path

        Returns:
            Value at path or None if not found
        """
        # Convert item to dict if it's a Pydantic model
        if hasattr(item, "model_dump"):
            current = item.model_dump()
        elif hasattr(item, "dict"):
            current = item.dict()
        else:
            current = item

        # Parse path parts
        parts = self._parse_path(path)

        for part in parts:
            if current is None:
                return None

            if isinstance(part, int):
                # Array index access
                if isinstance(current, list | tuple) and 0 <= part < len(current):
                    current = current[part]
                else:
                    return None
            else:
                # Dict/object key access
                if isinstance(current, dict):
                    current = current.get(part)
                elif hasattr(current, part):
                    current = getattr(current, part)
                else:
                    return None

        return current

    def _parse_path(self, path: str) -> list[str | int]:
        """
        Parse a dot-notation path into parts.

        "payload.emailAddresses[0].value" -> ["payload", "emailAddresses", 0, "value"]

        Args:
            path: Dot-notation path

        Returns:
            List of string keys and integer indices
        """
        parts: list[str | int] = []
        # Regex to match: word, or word[index]
        pattern = r"([a-zA-Z_][a-zA-Z0-9_]*)(?:\[(\d+)\])?"

        for segment in path.split("."):
            match = re.match(pattern, segment)
            if match:
                parts.append(match.group(1))
                if match.group(2) is not None:
                    parts.append(int(match.group(2)))
            else:
                # Fallback: treat entire segment as key
                parts.append(segment)

        return parts

    def _cast_value(self, value: Any, vtype: ValueType) -> Any:
        """
        Cast a value to the specified type.

        Graceful degradation: returns original value if casting fails.

        Args:
            value: Value to cast
            vtype: Target type

        Returns:
            Cast value or original if casting fails
        """
        if value is None:
            return None

        if vtype == ValueType.AUTO:
            return self._auto_cast(value)

        try:
            match vtype:
                case ValueType.INT:
                    return int(value)

                case ValueType.FLOAT:
                    return float(value)

                case ValueType.STRING:
                    return str(value)

                case ValueType.BOOL:
                    if isinstance(value, bool):
                        return value
                    if isinstance(value, str):
                        return value.lower() in ("true", "1", "yes", "on")
                    return bool(value)

                case ValueType.DATE:
                    if isinstance(value, date):
                        return value
                    if isinstance(value, datetime):
                        return value.date()
                    # Parse ISO format (YYYY-MM-DD)
                    return datetime.fromisoformat(str(value)[:10]).date()

                case ValueType.DATETIME:
                    if isinstance(value, datetime):
                        return value
                    # Parse ISO format
                    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))

        except (ValueError, TypeError) as e:
            logger.debug(
                "value_cast_failed",
                value=str(value)[:50],
                target_type=vtype.value,
                error=str(e),
            )
            return value

        return value

    def _auto_cast(self, value: Any) -> Any:
        """
        Automatically infer and cast value type.

        Heuristics:
        - Booleans: "true", "false"
        - Integers: digit strings
        - Floats: numeric strings with decimal
        - Dates: ISO format strings (YYYY-MM-DD)

        Args:
            value: Value to auto-cast

        Returns:
            Cast value or original if no type detected
        """
        if not isinstance(value, str):
            return value

        # Boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        # Integer
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return int(value)

        # Float
        try:
            if "." in value:
                return float(value)
        except ValueError:
            pass

        # Date (ISO format heuristic)
        if len(value) >= 10 and value[4] == "-" and value[7] == "-":
            try:
                return datetime.fromisoformat(value[:10]).date()
            except ValueError:
                pass

        return value


# Exports
__all__ = ["QueryExecutor", "QueryResult"]
