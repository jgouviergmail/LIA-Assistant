"""Unit tests for the polymorphic value extractors in ``tools/runtime_helpers``.

``extract_value`` / ``extract_value_by_path`` pull fields out of tool results
that may be either dicts (JSON tool output) or Pydantic models. The FOR_EACH
orchestration path relies on them: ``task_orchestrator_node`` calls
``extract_value_by_path(result_data, field_path)`` to find the collection to
iterate over ("reply to each of these emails"). A wrong extraction there does
not raise — the loop silently iterates over nothing.

The sharp edge is a dict key that collides with a dict METHOD name
(``items``, ``values``, ``keys``, ``get`` …): attribute access must never win
over the dict entry, or ``extract_value({"items": [...]}, "items")`` returns
the bound ``dict.items`` method instead of the list.
"""

import pytest
from pydantic import BaseModel

from src.domains.agents.tools.runtime_helpers import extract_value, extract_value_by_path

pytestmark = pytest.mark.unit


# ============================================================================
# extract_value — dicts
# ============================================================================


class TestExtractValueDict:
    DATA = {
        "name": "Alpha",
        "emailAddresses": [{"value": "a@x.com"}, {"value": "b@x.com"}],
        "nested": {"deep": {"leaf": 42}},
    }

    def test_simple_key(self) -> None:
        assert extract_value(self.DATA, "name") == "Alpha"

    def test_index_into_list(self) -> None:
        assert extract_value(self.DATA, "emailAddresses", 0, "value") == "a@x.com"
        assert extract_value(self.DATA, "emailAddresses", 1, "value") == "b@x.com"

    def test_nested_dict_path(self) -> None:
        assert extract_value(self.DATA, "nested", "deep", "leaf") == 42

    def test_missing_key_returns_default(self) -> None:
        assert extract_value(self.DATA, "missing", default="fallback") == "fallback"

    def test_out_of_bounds_index_returns_default(self) -> None:
        assert extract_value(self.DATA, "emailAddresses", 9, "value") is None

    def test_index_on_non_list_returns_default(self) -> None:
        assert extract_value(self.DATA, "name", 0) is None

    def test_none_midway_returns_default(self) -> None:
        assert extract_value({"a": None}, "a", "b", default="d") == "d"


# ============================================================================
# extract_value — the dict-method collision (regression)
# ============================================================================


class TestExtractValueMethodCollision:
    """A dict key must beat a dict method of the same name."""

    @pytest.mark.parametrize("key", ["items", "values", "keys", "get", "update", "copy", "pop"])
    def test_key_colliding_with_a_dict_method_returns_the_value(self, key: str) -> None:
        data = {key: "the-real-value"}
        assert extract_value(data, key) == "the-real-value"

    def test_items_key_holding_a_list_is_indexable(self) -> None:
        """The FOR_EACH case: a result keyed ``items`` must iterate, not vanish."""
        data = {"items": [{"id": "first"}, {"id": "second"}]}

        collection = extract_value(data, "items")
        assert isinstance(collection, list)
        assert extract_value(data, "items", 0, "id") == "first"

    def test_collision_does_not_return_a_bound_method(self) -> None:
        result = extract_value({"values": [1, 2, 3]}, "values")
        assert result == [1, 2, 3]
        assert not callable(result)


# ============================================================================
# extract_value — Pydantic models
# ============================================================================


class TestExtractValuePydantic:
    class Email(BaseModel):
        value: str

    class Contact(BaseModel):
        name: str
        emailAddresses: list[TestExtractValuePydantic.Email]

    def test_attribute_access_on_a_model(self) -> None:
        contact = self.Contact(name="Bob", emailAddresses=[self.Email(value="bob@x.com")])
        assert extract_value(contact, "name") == "Bob"
        assert extract_value(contact, "emailAddresses", 0, "value") == "bob@x.com"

    def test_missing_attribute_returns_default(self) -> None:
        contact = self.Contact(name="Bob", emailAddresses=[])
        assert extract_value(contact, "phone", default="none") == "none"


# ============================================================================
# extract_value_by_path — the string front-end used by FOR_EACH
# ============================================================================


class TestExtractValueByPath:
    DATA = {
        "start": {"dateTime": "2026-07-20T09:00:00Z"},
        "names": [{"displayName": "Alpha"}],
        "items": [{"id": "x1"}, {"id": "x2"}],
    }

    def test_simple_path(self) -> None:
        assert extract_value_by_path(self.DATA, "start.dateTime") == "2026-07-20T09:00:00Z"

    def test_indexed_path_converts_digits_to_int(self) -> None:
        assert extract_value_by_path(self.DATA, "names.0.displayName") == "Alpha"

    def test_for_each_over_a_field_named_items(self) -> None:
        """Regression: ``field_path == "items"`` must return the LIST, so the
        FOR_EACH loop in task_orchestrator_node iterates instead of finding a
        bound method and silently doing nothing."""
        collection = extract_value_by_path(self.DATA, "items")

        assert isinstance(collection, list)
        assert len(collection) == 2

    def test_empty_path_returns_default(self) -> None:
        assert extract_value_by_path(self.DATA, "", default="d") == "d"

    def test_missing_path_returns_default(self) -> None:
        assert extract_value_by_path(self.DATA, "nope.nope", default="d") == "d"
