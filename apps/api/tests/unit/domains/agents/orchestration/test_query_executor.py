"""Unit tests for the LocalQuery deterministic execution engine.

``QueryExecutor`` is what the ``local_query_engine_tool`` runs when the planner
asks the assistant to reason over already-fetched data ("which of these emails
is the most recent", "group my contacts by company", "how many are unread").
It is pure computation on in-memory registry items — no network, no I/O — so a
regression here produces a CONFIDENTLY WRONG answer with no error anywhere.

The module docstring promises two properties that the tests below pin
explicitly, because both had drifted:

- *deterministic* — DISTINCT went through a ``set``, whose iteration order
  varies with the interpreter's hash seed, so the same query returned the same
  values in a different order from one process to the next.
- *"None values at end"* on sort — true ascending, false descending: sorting
  "most recent first" surfaced the items that have no date AT THE TOP, and a
  ``limit`` then returned only those.
"""

from datetime import date

import pytest

from src.domains.agents.orchestration.query_engine.executor import QueryExecutor
from src.domains.agents.orchestration.query_engine.models import (
    AggregateFunction,
    ComparisonOperator,
    Condition,
    LocalQuery,
    QueryOperation,
    ValueType,
)

pytestmark = pytest.mark.unit


# ============================================================================
# FIXTURES
# ============================================================================


def _item(item_type: str = "email", **payload: object) -> dict:
    """Registry-item-shaped dict (``type`` + ``payload``)."""
    return {"type": item_type, "payload": payload}


CONTACTS = [
    _item(
        "contact",
        names="Jane Doe",
        emailAddresses=[{"value": "jane@example.com"}],
        company="ACME",
        age=34,
    ),
    _item(
        "contact",
        names="John Smith",
        emailAddresses=[{"value": "john@other.org"}],
        company="Globex",
        age=41,
    ),
    _item(
        "contact",
        names="Janet Doe",
        emailAddresses=[{"value": "janet@example.com"}],
        company="ACME",
        age=29,
    ),
]


# ============================================================================
# TYPE PRE-FILTER
# ============================================================================


class TestTypeFilter:
    """``target_type`` narrows the working set before any operation."""

    MIXED = [_item("CONTACT", names="Jane"), _item("EMAIL", subject="Hello")]

    def test_without_target_type_every_item_is_considered(self) -> None:
        result = QueryExecutor(self.MIXED).execute(LocalQuery(operation=QueryOperation.FILTER))
        assert result.total == 2

    def test_target_type_keeps_only_matching_items(self) -> None:
        from src.domains.agents.data_registry.models import RegistryItemType

        result = QueryExecutor(self.MIXED).execute(
            LocalQuery(operation=QueryOperation.FILTER, target_type=RegistryItemType.CONTACT)
        )
        assert result.total == 1
        assert result.items[0]["payload"]["names"] == "Jane"


# ============================================================================
# FILTER
# ============================================================================


class TestFilter:
    """Conditions are ANDed; every comparison operator has to behave."""

    def test_no_condition_returns_everything(self) -> None:
        result = QueryExecutor(CONTACTS).execute(LocalQuery(operation=QueryOperation.FILTER))
        assert result.total == 3

    def test_conditions_are_combined_with_and(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(
                        field="payload.company", operator=ComparisonOperator.EQ, value="ACME"
                    ),
                    Condition(field="payload.age", operator=ComparisonOperator.LT, value=30),
                ],
            )
        )
        assert [i["payload"]["names"] for i in result.items] == ["Janet Doe"]

    @pytest.mark.parametrize(
        ("operator", "value", "expected"),
        [
            (ComparisonOperator.EQ, "ACME", 2),
            (ComparisonOperator.NE, "ACME", 1),
            (ComparisonOperator.CONTAINS, "CM", 2),
            (ComparisonOperator.STARTS_WITH, "AC", 2),
            (ComparisonOperator.ENDS_WITH, "ex", 1),
            (ComparisonOperator.MATCHES, "^Glo", 1),
            (ComparisonOperator.IN, ["ACME", "Initech"], 2),
            (ComparisonOperator.NOT_IN, ["ACME"], 1),
        ],
    )
    def test_string_operators(
        self, operator: ComparisonOperator, value: object, expected: int
    ) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[Condition(field="payload.company", operator=operator, value=value)],
            )
        )
        assert result.total == expected

    @pytest.mark.parametrize(
        ("operator", "value", "expected"),
        [
            (ComparisonOperator.GT, 30, 2),
            (ComparisonOperator.GE, 34, 2),
            (ComparisonOperator.LT, 34, 1),
            (ComparisonOperator.LE, 34, 2),
        ],
    )
    def test_numeric_operators(
        self, operator: ComparisonOperator, value: int, expected: int
    ) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[Condition(field="payload.age", operator=operator, value=value)],
            )
        )
        assert result.total == expected

    def test_ordering_operators_reject_missing_values_instead_of_raising(self) -> None:
        """A missing field must exclude the item, never crash the whole query."""
        items = [_item("contact", names="No age")]
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(field="payload.age", operator=ComparisonOperator.GT, value=10)
                ],
            )
        )
        assert result.total == 0

    def test_null_operators(self) -> None:
        items = [_item("contact", names="A", note=None), _item("contact", names="B", note="x")]
        executor = QueryExecutor(items)

        is_null = executor.execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(field="payload.note", operator=ComparisonOperator.IS_NULL, value=None)
                ],
            )
        )
        is_not_null = executor.execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(
                        field="payload.note", operator=ComparisonOperator.IS_NOT_NULL, value=None
                    )
                ],
            )
        )

        assert is_null.total == 1
        assert is_not_null.total == 1

    def test_string_comparison_is_case_sensitive_by_default(self) -> None:
        """``Condition.case_sensitive`` defaults to True — the LLM must opt out."""
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(field="payload.company", operator=ComparisonOperator.EQ, value="acme")
                ],
            )
        )
        assert result.total == 0

    def test_case_insensitive_flag_relaxes_the_comparison(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(
                        field="payload.company",
                        operator=ComparisonOperator.EQ,
                        value="acme",
                        case_sensitive=False,
                    )
                ],
            )
        )
        assert result.total == 2

    def test_case_insensitive_in_operator_lowercases_both_sides(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(
                        field="payload.company",
                        operator=ComparisonOperator.IN,
                        value=["acme", "initech"],
                        case_sensitive=False,
                    )
                ],
            )
        )
        assert result.total == 2

    def test_in_operator_accepts_a_comma_separated_string(self) -> None:
        """Jinja templates render lists as CSV; the operator must still work."""
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(
                        field="payload.company",
                        operator=ComparisonOperator.IN,
                        value="ACME, Initech",
                    )
                ],
            )
        )
        assert result.total == 2

    def test_in_operator_rejects_a_scalar_target(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(field="payload.company", operator=ComparisonOperator.IN, value="ACME")
                ],
            )
        )
        assert result.total == 0

    def test_invalid_regex_excludes_instead_of_raising(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(
                operation=QueryOperation.FILTER,
                conditions=[
                    Condition(
                        field="payload.company",
                        operator=ComparisonOperator.MATCHES,
                        value="[unclosed",
                    )
                ],
            )
        )
        assert result.total == 0


# ============================================================================
# SORT
# ============================================================================


class TestSort:
    """Ordering, and where the items MISSING the sort field end up."""

    DATED = [
        _item("email", subject="oldest", date="2026-01-01"),
        _item("email", subject="newest", date="2026-07-01"),
        _item("email", subject="middle", date="2026-04-01"),
    ]
    WITH_HOLES = [
        _item("email", subject="dated-old", date="2026-01-01"),
        _item("email", subject="undated"),
        _item("email", subject="dated-new", date="2026-07-01"),
    ]

    def _sorted_subjects(
        self, items: list[dict], order: str, limit: int | None = None
    ) -> list[str]:
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.SORT,
                sort_by="payload.date",
                sort_order=order,
                limit=limit,
            )
        )
        return [i["payload"]["subject"] for i in result.items]

    def test_ascending_order(self) -> None:
        assert self._sorted_subjects(self.DATED, "asc") == ["oldest", "middle", "newest"]

    def test_descending_order(self) -> None:
        assert self._sorted_subjects(self.DATED, "desc") == ["newest", "middle", "oldest"]

    def test_missing_values_go_last_when_ascending(self) -> None:
        assert self._sorted_subjects(self.WITH_HOLES, "asc")[-1] == "undated"

    def test_missing_values_go_last_when_descending(self) -> None:
        """Regression: "most recent first" used to return the UNDATED items first."""
        assert self._sorted_subjects(self.WITH_HOLES, "desc")[-1] == "undated"

    def test_limit_after_a_descending_sort_returns_real_data(self) -> None:
        """The user-visible consequence: "top 1 most recent" must not be a hole."""
        assert self._sorted_subjects(self.WITH_HOLES, "desc", limit=1) == ["dated-new"]

    def test_sort_without_field_is_a_noop(self) -> None:
        result = QueryExecutor(self.DATED).execute(LocalQuery(operation=QueryOperation.SORT))
        assert [i["payload"]["subject"] for i in result.items] == [
            "oldest",
            "newest",
            "middle",
        ]

    def test_mixed_types_fall_back_to_string_comparison(self) -> None:
        items = [
            _item("email", subject="int", score=10),
            _item("email", subject="str", score="abc"),
            _item("email", subject="none"),
        ]
        result = QueryExecutor(items).execute(
            LocalQuery(operation=QueryOperation.SORT, sort_by="payload.score", sort_order="asc")
        )
        assert [i["payload"]["subject"] for i in result.items][-1] == "none"

    def test_sort_applies_conditions_first(self) -> None:
        result = QueryExecutor(self.DATED).execute(
            LocalQuery(
                operation=QueryOperation.SORT,
                sort_by="payload.date",
                sort_order="desc",
                conditions=[
                    Condition(
                        field="payload.subject", operator=ComparisonOperator.NE, value="newest"
                    )
                ],
            )
        )
        assert [i["payload"]["subject"] for i in result.items] == ["middle", "oldest"]


# ============================================================================
# GROUP
# ============================================================================


class TestGroup:
    """Grouping feeds Jinja templates in downstream plan steps."""

    def test_groups_by_field_value(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(operation=QueryOperation.GROUP, group_by="payload.company")
        )
        groups = {g["key"]: g["count"] for g in result.items}
        assert groups == {"ACME": 2, "Globex": 1}
        assert result.total == 2

    def test_group_members_are_exposed_under_members_not_items(self) -> None:
        """``items`` would resolve to ``dict.items`` in the Jinja sandbox."""
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(operation=QueryOperation.GROUP, group_by="payload.company")
        )
        assert all("members" in group for group in result.items)
        assert all("items" not in group for group in result.items)

    def test_missing_values_land_in_the_null_bucket(self) -> None:
        items = [_item("contact", names="A"), _item("contact", names="B", company="ACME")]
        result = QueryExecutor(items).execute(
            LocalQuery(operation=QueryOperation.GROUP, group_by="payload.company")
        )
        assert {g["key"] for g in result.items} == {"_null_", "ACME"}

    def test_group_without_field_reports_an_error(self) -> None:
        result = QueryExecutor(CONTACTS).execute(LocalQuery(operation=QueryOperation.GROUP))
        assert result.items == []
        assert "error" in result.meta


# ============================================================================
# AGGREGATE
# ============================================================================


class TestAggregate:
    """Aggregations answer "how many", "what is the total", "which values"."""

    NUMBERS = [
        _item("email", score=10),
        _item("email", score=20),
        _item("email", score=None),
        _item("email"),
    ]

    def _aggregate(self, items: list[dict], fn: AggregateFunction, field: str | None = None):
        return QueryExecutor(items).execute(
            LocalQuery(operation=QueryOperation.AGGREGATE, aggregate_fn=fn, aggregate_field=field)
        )

    def test_count_ignores_the_field(self) -> None:
        assert self._aggregate(self.NUMBERS, AggregateFunction.COUNT).items == [4]

    def test_sum_skips_missing_and_non_numeric_values(self) -> None:
        assert self._aggregate(self.NUMBERS, AggregateFunction.SUM, "payload.score").items == [30]

    def test_avg_divides_by_the_numeric_count_only(self) -> None:
        assert self._aggregate(self.NUMBERS, AggregateFunction.AVG, "payload.score").items == [15]

    def test_sum_and_avg_of_an_empty_set_are_zero(self) -> None:
        assert self._aggregate([], AggregateFunction.SUM, "payload.score").items == [0]
        assert self._aggregate([], AggregateFunction.AVG, "payload.score").items == [0]

    def test_min_and_max(self) -> None:
        assert self._aggregate(self.NUMBERS, AggregateFunction.MIN, "payload.score").items == [10]
        assert self._aggregate(self.NUMBERS, AggregateFunction.MAX, "payload.score").items == [20]

    def test_min_and_max_of_an_empty_set_are_none(self) -> None:
        assert self._aggregate([], AggregateFunction.MIN, "payload.score").items == [None]

    def test_min_and_max_fall_back_to_strings_on_mixed_types(self) -> None:
        mixed = [_item("email", score=10), _item("email", score="abc")]
        assert self._aggregate(mixed, AggregateFunction.MIN, "payload.score").items == ["10"]

    def test_distinct_returns_unique_values(self) -> None:
        items = [
            _item("contact", company="ACME"),
            _item("contact", company="Globex"),
            _item("contact", company="ACME"),
        ]
        result = self._aggregate(items, AggregateFunction.DISTINCT, "payload.company")
        assert sorted(result.items[0]) == ["ACME", "Globex"]
        assert result.meta["distinct_values"] == result.items[0]

    def test_distinct_preserves_first_seen_order(self) -> None:
        """Determinism: a ``set`` reorders with the interpreter hash seed, so the
        same query returned the same values in a different order per process."""
        items = [
            _item("contact", company=name)
            for name in ("Zeta", "Alpha", "Mu", "Alpha", "Zeta", "Beta")
        ]
        result = self._aggregate(items, AggregateFunction.DISTINCT, "payload.company")
        assert result.items[0] == ["Zeta", "Alpha", "Mu", "Beta"]

    def test_aggregate_without_function_reports_an_error(self) -> None:
        result = QueryExecutor(CONTACTS).execute(LocalQuery(operation=QueryOperation.AGGREGATE))
        assert "error" in result.meta


# ============================================================================
# SIMILARITY
# ============================================================================


class TestSimilarity:
    """Duplicate detection over a text field (O(N²) SequenceMatcher)."""

    def test_returns_both_members_of_a_similar_pair(self) -> None:
        items = [
            _item("contact", names="Jean Dupont"),
            _item("contact", names="Jean Dupond"),
            _item("contact", names="Marie Curie"),
        ]
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.SIMILARITY,
                similarity_field="payload.names",
                similarity_threshold=0.85,
            )
        )
        assert {i["payload"]["names"] for i in result.items} == {"Jean Dupont", "Jean Dupond"}

    def test_comparison_ignores_case(self) -> None:
        items = [_item("contact", names="ACME CORP"), _item("contact", names="acme corp")]
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.SIMILARITY,
                similarity_field="payload.names",
                similarity_threshold=0.99,
            )
        )
        assert len(result.items) == 2

    def test_threshold_of_one_keeps_only_identical_values(self) -> None:
        items = [_item("contact", names="Jean Dupont"), _item("contact", names="Jean Dupond")]
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.SIMILARITY,
                similarity_field="payload.names",
                similarity_threshold=1.0,
            )
        )
        assert result.items == []

    def test_fewer_than_two_comparable_values_yields_nothing(self) -> None:
        items = [_item("contact", names="Jean Dupont"), _item("contact")]
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.SIMILARITY,
                similarity_field="payload.names",
                similarity_threshold=0.5,
            )
        )
        assert result.items == []

    def test_similarity_without_field_yields_nothing(self) -> None:
        result = QueryExecutor(CONTACTS).execute(
            LocalQuery(operation=QueryOperation.SIMILARITY, similarity_threshold=0.5)
        )
        assert result.items == []

    def test_results_keep_the_source_order(self) -> None:
        items = [
            _item("contact", names="Bravo"),
            _item("contact", names="Zulu"),
            _item("contact", names="Bravo"),
        ]
        result = QueryExecutor(items).execute(
            LocalQuery(
                operation=QueryOperation.SIMILARITY,
                similarity_field="payload.names",
                similarity_threshold=0.99,
            )
        )
        assert [i["payload"]["names"] for i in result.items] == ["Bravo", "Bravo"]


# ============================================================================
# PAGINATION
# ============================================================================


class TestPagination:
    """``total`` counts the matches, ``items`` carries the requested window."""

    ITEMS = [_item("email", subject=str(i)) for i in range(10)]

    def test_limit_truncates_but_total_keeps_the_full_count(self) -> None:
        result = QueryExecutor(self.ITEMS).execute(
            LocalQuery(operation=QueryOperation.FILTER, limit=3)
        )
        assert result.total == 10
        assert [i["payload"]["subject"] for i in result.items] == ["0", "1", "2"]

    def test_offset_skips_from_the_head(self) -> None:
        result = QueryExecutor(self.ITEMS).execute(
            LocalQuery(operation=QueryOperation.FILTER, offset=8)
        )
        assert [i["payload"]["subject"] for i in result.items] == ["8", "9"]

    def test_offset_and_limit_compose(self) -> None:
        result = QueryExecutor(self.ITEMS).execute(
            LocalQuery(operation=QueryOperation.FILTER, offset=4, limit=2)
        )
        assert [i["payload"]["subject"] for i in result.items] == ["4", "5"]

    def test_offset_past_the_end_returns_nothing(self) -> None:
        result = QueryExecutor(self.ITEMS).execute(
            LocalQuery(operation=QueryOperation.FILTER, offset=99)
        )
        assert result.items == []
        assert result.total == 10


# ============================================================================
# PATH RESOLUTION & CASTING
# ============================================================================


class TestFieldPathResolution:
    """Dot paths with array indices are what the planner writes in conditions."""

    ITEM = _item(
        "contact",
        names="Jane",
        emailAddresses=[{"value": "jane@example.com"}, {"value": "j@work.com"}],
    )

    @pytest.mark.parametrize(
        ("path", "expected"),
        [
            ("type", "contact"),
            ("payload.names", "Jane"),
            ("payload.emailAddresses[0].value", "jane@example.com"),
            ("payload.emailAddresses[1].value", "j@work.com"),
        ],
    )
    def test_resolves_nested_and_indexed_paths(self, path: str, expected: str) -> None:
        assert QueryExecutor([])._get_field_value(self.ITEM, path) == expected

    @pytest.mark.parametrize(
        "path",
        [
            "payload.missing",
            "payload.emailAddresses[9].value",
            "payload.names.deeper",
            "missing.deeper",
        ],
    )
    def test_unresolvable_paths_return_none(self, path: str) -> None:
        assert QueryExecutor([])._get_field_value(self.ITEM, path) is None

    def test_reads_attributes_of_plain_objects(self) -> None:
        class Node:
            def __init__(self) -> None:
                self.type = "contact"

        assert QueryExecutor([])._get_field_value(Node(), "type") == "contact"

    def test_reads_pydantic_models_through_model_dump(self) -> None:
        from pydantic import BaseModel

        class Payload(BaseModel):
            names: str

        class Item(BaseModel):
            type: str
            payload: Payload

        item = Item(type="contact", payload=Payload(names="Jane"))
        assert QueryExecutor([])._get_field_value(item, "payload.names") == "Jane"


class TestValueCasting:
    """Explicit ``value_type`` and the AUTO heuristic."""

    @pytest.mark.parametrize(
        ("raw", "vtype", "expected"),
        [
            ("42", ValueType.INT, 42),
            ("4.5", ValueType.FLOAT, 4.5),
            (42, ValueType.STRING, "42"),
            ("yes", ValueType.BOOL, True),
            ("nope", ValueType.BOOL, False),
            (True, ValueType.BOOL, True),
            ("2026-07-20", ValueType.DATE, date(2026, 7, 20)),
            ("2026-07-20T09:00:00Z", ValueType.DATE, date(2026, 7, 20)),
        ],
    )
    def test_explicit_casts(self, raw: object, vtype: ValueType, expected: object) -> None:
        assert QueryExecutor([])._cast_value(raw, vtype) == expected

    def test_failed_cast_degrades_to_the_original_value(self) -> None:
        assert QueryExecutor([])._cast_value("not-a-number", ValueType.INT) == "not-a-number"

    def test_none_stays_none(self) -> None:
        assert QueryExecutor([])._cast_value(None, ValueType.INT) is None

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("true", True),
            ("FALSE", False),
            ("42", 42),
            ("-7", -7),
            ("4.5", 4.5),
            ("2026-07-20", date(2026, 7, 20)),
            ("hello", "hello"),
        ],
    )
    def test_auto_cast_heuristics(self, raw: str, expected: object) -> None:
        assert QueryExecutor([])._cast_value(raw, ValueType.AUTO) == expected

    def test_auto_cast_leaves_non_strings_untouched(self) -> None:
        assert QueryExecutor([])._cast_value(7, ValueType.AUTO) == 7

    def test_auto_cast_truncates_datetimes_to_their_date(self) -> None:
        """Documented limitation: AUTO compares ISO datetimes at DAY granularity."""
        assert QueryExecutor([])._cast_value("2026-07-20T23:59:00Z", ValueType.AUTO) == date(
            2026, 7, 20
        )


# ============================================================================
# ROBUSTNESS
# ============================================================================


class TestRobustness:
    """A malformed query degrades into an error result, never an exception."""

    def test_execution_error_is_captured_in_the_result(self) -> None:
        executor = QueryExecutor(CONTACTS)

        def _boom(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("engine exploded")

        executor._execute_filter = _boom  # type: ignore[method-assign]
        result = executor.execute(LocalQuery(operation=QueryOperation.FILTER))

        assert result.items == []
        assert result.total == 0
        assert "engine exploded" in result.meta["error"]

    def test_source_items_are_never_mutated(self) -> None:
        """The engine is documented read-only; downstream steps reuse the registry."""
        import copy

        source = copy.deepcopy(CONTACTS)
        QueryExecutor(source).execute(
            LocalQuery(operation=QueryOperation.SORT, sort_by="payload.age", sort_order="desc")
        )
        assert source == CONTACTS

    def test_empty_dataset_is_handled_by_every_operation(self) -> None:
        executor = QueryExecutor([])
        for query in (
            LocalQuery(operation=QueryOperation.FILTER),
            LocalQuery(operation=QueryOperation.SORT, sort_by="payload.age"),
            LocalQuery(operation=QueryOperation.GROUP, group_by="payload.company"),
            LocalQuery(operation=QueryOperation.SIMILARITY, similarity_field="payload.names"),
            LocalQuery(operation=QueryOperation.AGGREGATE, aggregate_fn=AggregateFunction.COUNT),
        ):
            executor.execute(query)  # must not raise
