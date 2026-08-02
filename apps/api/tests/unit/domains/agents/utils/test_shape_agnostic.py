"""``read_field`` must behave identically on both shapes a record can take.

It replaced three identical private copies. The tests below are the union of
what those three needed, so any future divergence is caught here rather than in
one of the call sites.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.domains.agents.utils.shape_agnostic import read_field

pytestmark = pytest.mark.unit


class TestReadField:
    def test_reads_from_an_object(self) -> None:
        assert read_field(SimpleNamespace(name="Alice"), "name") == "Alice"

    def test_reads_from_a_mapping(self) -> None:
        assert read_field({"name": "Alice"}, "name") == "Alice"

    def test_absent_field_yields_the_default(self) -> None:
        assert read_field(SimpleNamespace(), "name") is None
        assert read_field({}, "name") is None
        assert read_field({}, "name", "fallback") == "fallback"

    def test_a_falsy_value_is_returned_as_is(self) -> None:
        """0 / False / "" are values, not absences — the classic trap."""
        assert read_field({"count": 0}, "count", 99) == 0
        assert read_field({"flag": False}, "flag", True) is False
        assert read_field({"text": ""}, "text", "x") == ""

    def test_an_unexpected_shape_never_raises(self) -> None:
        """A malformed record must not cost the whole turn."""
        assert read_field("not a record", "name") is None
        assert read_field(None, "name", "d") == "d"
        assert read_field(42, "name") is None

    def test_an_explicit_none_is_reported_as_the_default(self) -> None:
        """Documented limitation, pinned so it stays a decision."""
        assert read_field({"name": None}, "name", "d") == "d"

    @pytest.mark.parametrize("name", ["items", "keys", "values", "get", "copy"])
    def test_a_key_shadowing_a_dict_method_still_reads_the_value(self, name: str) -> None:
        """A dict carries attributes of its own, and they are NOT the data.

        Reading a mapping through getattr first would answer with the bound
        built-in method — truthy, so every caller's `if` would take the wrong
        branch and any string formatting would print `<built-in method items>`.
        """
        assert read_field({name: "payload"}, name) == "payload"
        assert read_field({}, name, "fallback") == "fallback"
