"""Unit tests for the ExecutionPlan reference resolver.

``ReferenceResolver`` (in ``orchestration/condition_evaluator.py``, instantiated
by ``parallel_executor``) is the engine that passes data BETWEEN plan steps:
``$steps.search.results[0].id``, ``context.emails[1].id``, ``items[0].value``,
wildcards (``[*]``), JSONPath filters (``[?(@.name=='Bob')]``), and references
embedded inside a larger string. A regression here does not raise — it feeds the
WRONG value into the next step (e.g. "reply to the email I just found" replies
to a different one), so every navigation shape is pinned explicitly.

The comma-separated path already has a home in ``tests/agents``; this module
covers everything else, in the unit suite so it also counts toward the gate.
"""

from typing import Any

import pytest

from src.domains.agents.orchestration.condition_evaluator import ReferenceResolver

pytestmark = pytest.mark.unit


@pytest.fixture
def resolver() -> ReferenceResolver:
    return ReferenceResolver()


# ============================================================================
# is_reference — the dispatcher that decides what gets resolved
# ============================================================================


class TestIsReference:
    @pytest.mark.parametrize(
        "value",
        [
            "$steps.search.id",
            "$contexts.emails",
            "$context.emails",
            "context.emails",
            "items[0].id",
            "emails[0].id",
            "contacts[2].resource_name",
        ],
    )
    def test_recognised_reference_forms(self, resolver: ReferenceResolver, value: str) -> None:
        assert resolver.is_reference(value) is True

    @pytest.mark.parametrize(
        "value",
        ["plain string", "user@example.com", "", "steps.x", "$stepsX", 42, None, ["$steps.x"]],
    )
    def test_non_references(self, resolver: ReferenceResolver, value: Any) -> None:
        assert resolver.is_reference(value) is False

    def test_items_reference_is_distinguished(self, resolver: ReferenceResolver) -> None:
        assert resolver.is_items_reference("items[3].value") is True
        assert resolver.is_items_reference("emails[3].value") is False


# ============================================================================
# resolve — $steps
# ============================================================================


class TestResolveSteps:
    STEPS = {
        "search": {
            "results": [{"id": "a1", "name": "Alpha"}, {"id": "b2", "name": "Bravo"}],
            "count": 2,
        }
    }

    def test_scalar_field(self, resolver: ReferenceResolver) -> None:
        assert resolver.resolve("$steps.search.count", self.STEPS) == 2

    def test_indexed_field(self, resolver: ReferenceResolver) -> None:
        assert resolver.resolve("$steps.search.results[0].id", self.STEPS) == "a1"
        assert resolver.resolve("$steps.search.results[1].name", self.STEPS) == "Bravo"

    def test_unknown_step_raises_with_available_list(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="non-existent step"):
            resolver.resolve("$steps.missing.id", self.STEPS)

    def test_missing_path_raises_keyerror(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(KeyError):
            resolver.resolve("$steps.search.nonexistent", self.STEPS)

    def test_index_out_of_bounds_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(KeyError):
            resolver.resolve("$steps.search.results[9].id", self.STEPS)

    def test_malformed_steps_reference_raises_valueerror(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="Invalid reference format"):
            resolver.resolve("$steps.", self.STEPS)


# ============================================================================
# resolve — context / DOMAIN[N]
# ============================================================================


class TestResolveContext:
    CONTEXT = {"emails": [{"id": "e1"}, {"id": "e2"}], "note": {"deep": {"value": "x"}}}

    @pytest.mark.parametrize("prefix", ["$contexts", "$context", "context"])
    def test_all_three_context_prefixes(self, resolver: ReferenceResolver, prefix: str) -> None:
        assert resolver.resolve(f"{prefix}.emails[0].id", {}, context=self.CONTEXT) == "e1"

    def test_nested_context_path(self, resolver: ReferenceResolver) -> None:
        assert resolver.resolve("context.note.deep.value", {}, context=self.CONTEXT) == "x"

    def test_context_reference_without_context_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="context not provided"):
            resolver.resolve("context.emails[0].id", {}, context=None)


class TestResolveDomainReference:
    """``emails[0].id`` — the LLM's shorthand, resolved from context."""

    CONTEXT = {"emails": [{"id": "e1"}, {"id": "e2"}], "flag": True}

    def test_domain_index_field(self, resolver: ReferenceResolver) -> None:
        assert resolver.resolve("emails[1].id", {}, context=self.CONTEXT) == "e2"

    def test_unknown_domain_lists_available_domains(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="not found in context"):
            resolver.resolve("contacts[0].id", {}, context=self.CONTEXT)

    def test_domain_that_is_not_a_list_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="not a list"):
            resolver.resolve("flag[0].id", {}, context=self.CONTEXT)

    def test_index_out_of_bounds_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            resolver.resolve("emails[9].id", {}, context=self.CONTEXT)

    def test_empty_domain_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="empty"):
            resolver.resolve("emails[0].id", {}, context={"emails": []})

    def test_missing_context_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="context not provided"):
            resolver.resolve("emails[0].id", {}, context=None)


# ============================================================================
# resolve — items[N] (registry)
# ============================================================================


class TestResolveItemsReference:
    """``items[N].field`` reads the Nth registry item's payload, insertion-ordered."""

    def _registry(self) -> dict[str, dict[str, Any]]:
        return {
            "place_new": {"payload": {"name": "New"}, "meta": {"timestamp": "2026-07-20T10:00Z"}},
            "place_old": {"payload": {"name": "Old"}, "meta": {"timestamp": "2026-07-20T09:00Z"}},
        }

    def test_index_reads_in_timestamp_order(self, resolver: ReferenceResolver) -> None:
        """Oldest first: index 0 is the earliest-timestamped item, not dict order."""
        assert resolver.resolve("items[0].name", {}, registry=self._registry()) == "Old"
        assert resolver.resolve("items[1].name", {}, registry=self._registry()) == "New"

    def test_nested_field_in_payload(self, resolver: ReferenceResolver) -> None:
        registry = {"x": {"payload": {"location": {"lat": 48.8}}}}
        assert resolver.resolve("items[0].location.lat", {}, registry=registry) == 48.8

    def test_missing_registry_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="registry not provided"):
            resolver.resolve("items[0].name", {}, registry=None)

    def test_empty_registry_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="empty"):
            resolver.resolve("items[0].name", {}, registry={})

    def test_index_out_of_bounds_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(ValueError, match="out of bounds"):
            resolver.resolve("items[5].name", {}, registry=self._registry())

    def test_items_without_timestamps_keep_insertion_order(
        self, resolver: ReferenceResolver
    ) -> None:
        registry = {"a": {"payload": {"n": 1}}, "b": {"payload": {"n": 2}}}
        assert resolver.resolve("items[0].n", {}, registry=registry) == 1


# ============================================================================
# _navigate_path — the JSONPath-lite engine
# ============================================================================


class TestNavigatePath:
    DATA = {
        "contacts": [
            {"name": "Alpha", "emails": [{"value": "a@x.com"}]},
            {"name": "Bravo", "emails": [{"value": "b@x.com"}]},
            {"name": "Charlie", "emails": [{"value": "c@x.com"}]},
        ]
    }

    def test_field_then_index_then_field(self, resolver: ReferenceResolver) -> None:
        assert resolver._navigate_path(self.DATA, "contacts[1].name", "ref") == "Bravo"

    def test_deep_nested_index(self, resolver: ReferenceResolver) -> None:
        assert resolver._navigate_path(self.DATA, "contacts[0].emails[0].value", "ref") == "a@x.com"

    def test_wildcard_extracts_field_from_every_item(self, resolver: ReferenceResolver) -> None:
        assert resolver._navigate_path(self.DATA, "contacts[*].name", "ref") == [
            "Alpha",
            "Bravo",
            "Charlie",
        ]

    def test_wildcard_with_nested_path(self, resolver: ReferenceResolver) -> None:
        assert resolver._navigate_path(self.DATA, "contacts[*].emails[0].value", "ref") == [
            "a@x.com",
            "b@x.com",
            "c@x.com",
        ]

    def test_trailing_wildcard_returns_the_array(self, resolver: ReferenceResolver) -> None:
        result = resolver._navigate_path(self.DATA, "contacts[*]", "ref")
        assert isinstance(result, list)
        assert len(result) == 3

    def test_wildcard_on_non_array_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(KeyError):
            resolver._navigate_path({"contacts": "not-a-list"}, "contacts[*].name", "ref")

    def test_jsonpath_filter_finds_the_matching_item(self, resolver: ReferenceResolver) -> None:
        assert (
            resolver._navigate_path(self.DATA, "contacts[?(@.name=='Bravo')].name", "ref")
            == "Bravo"
        )

    def test_jsonpath_filter_is_case_insensitive(self, resolver: ReferenceResolver) -> None:
        assert (
            resolver._navigate_path(
                self.DATA, "contacts[?(@.name=='bravo')].emails[0].value", "ref"
            )
            == "b@x.com"
        )

    def test_jsonpath_filter_no_match_raises(self, resolver: ReferenceResolver) -> None:
        with pytest.raises(KeyError):
            resolver._navigate_path(self.DATA, "contacts[?(@.name=='Zeta')].name", "ref")

    def test_missing_field_raises_with_the_original_reference(
        self, resolver: ReferenceResolver
    ) -> None:
        with pytest.raises(KeyError, match="original-ref"):
            resolver._navigate_path(self.DATA, "contacts[0].phone", "original-ref")


# ============================================================================
# resolve_args — the dict/list recursion the executor actually calls
# ============================================================================


class TestResolveArgs:
    STEPS = {"search": {"contacts": [{"email": "a@x.com"}, {"email": "b@x.com"}]}}

    def test_direct_reference_argument(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args({"to": "$steps.search.contacts[0].email"}, self.STEPS)
        assert resolved["to"] == "a@x.com"

    def test_non_reference_values_pass_through(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args({"subject": "Hello", "count": 3}, self.STEPS)
        assert resolved == {"subject": "Hello", "count": 3}

    def test_nested_dict_is_resolved(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args(
            {"message": {"to": "$steps.search.contacts[1].email"}}, self.STEPS
        )
        assert resolved["message"]["to"] == "b@x.com"

    def test_list_of_references_is_resolved_elementwise(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args(
            {"recipients": ["$steps.search.contacts[0].email", "literal@x.com"]}, self.STEPS
        )
        assert resolved["recipients"] == ["a@x.com", "literal@x.com"]

    def test_wildcard_reference_yields_a_list(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args({"all": "$steps.search.contacts[*].email"}, self.STEPS)
        assert resolved["all"] == ["a@x.com", "b@x.com"]


# ============================================================================
# Embedded references — inside a larger string (Gmail query building)
# ============================================================================


class TestEmbeddedReferences:
    STEPS = {"search": {"contacts": [{"email": "a@x.com"}, {"email": "b@x.com"}]}}

    def test_detects_a_parenthesised_reference(self, resolver: ReferenceResolver) -> None:
        assert resolver._has_embedded_reference("from:($steps.search.contacts[*].email) to:me")

    def test_detects_an_inline_reference(self, resolver: ReferenceResolver) -> None:
        assert resolver._has_embedded_reference("from:$steps.search.contacts[0].email")

    def test_plain_string_has_no_embedded_reference(self, resolver: ReferenceResolver) -> None:
        assert resolver._has_embedded_reference("from:me to:you") is False

    def test_parenthesised_list_becomes_an_or_query(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args(
            {"query": "from:($steps.search.contacts[*].email)"}, self.STEPS
        )
        assert resolved["query"] == "from:(a@x.com OR b@x.com)"

    def test_scalar_embedded_reference_is_wrapped(self, resolver: ReferenceResolver) -> None:
        resolved = resolver.resolve_args(
            {"query": "subject:hi from:$steps.search.contacts[0].email"}, self.STEPS
        )
        assert "a@x.com" in resolved["query"]

    def test_unresolvable_embedded_reference_keeps_the_original(
        self, resolver: ReferenceResolver
    ) -> None:
        """Failure is non-fatal for embedded refs: the literal is left for debugging."""
        resolved = resolver.resolve_args({"query": "from:($steps.missing.email) to:me"}, self.STEPS)
        assert "$steps.missing.email" in resolved["query"]
