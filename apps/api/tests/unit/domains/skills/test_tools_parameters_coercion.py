"""Tests for :func:`_coerce_parameters` in :mod:`src.domains.skills.tools`.

Background
----------
Some LLMs (notably Qwen) serialize nested ``dict`` tool arguments as JSON
strings instead of structured objects, causing ``run_skill_script`` to be
invoked with ``parameters='{"location": "Paris"}'`` rather than the expected
``parameters={"location": "Paris"}``. Pydantic rejected the string, the ReAct
loop retried indefinitely, and eventually hit ``GraphRecursionError``.

The production fix accepts both shapes and normalizes them via
:func:`_coerce_parameters`. These tests freeze that contract so it cannot
regress.
"""

from __future__ import annotations

from src.domains.skills.tools import _coerce_parameters


class TestCoerceParametersAcceptsNative:
    """Native forms pass through unchanged."""

    def test_none_returns_none(self) -> None:
        coerced, err = _coerce_parameters(None)
        assert coerced is None
        assert err is None

    def test_empty_dict_returns_empty_dict(self) -> None:
        coerced, err = _coerce_parameters({})
        assert coerced == {}
        assert err is None

    def test_populated_dict_passthrough(self) -> None:
        value = {"location": "Paris", "days": 5}
        coerced, err = _coerce_parameters(value)
        assert coerced == value
        assert err is None


class TestCoerceParametersParsesJsonString:
    """JSON strings are parsed into dicts (Qwen-style serialization)."""

    def test_simple_json_object_string(self) -> None:
        coerced, err = _coerce_parameters('{"location": "Strasbourg"}')
        assert err is None
        assert coerced == {"location": "Strasbourg"}

    def test_nested_json_object_string(self) -> None:
        coerced, err = _coerce_parameters(
            '{"location": {"city": "Paris"}, "days": 5, "units": "metric"}'
        )
        assert err is None
        assert coerced == {
            "location": {"city": "Paris"},
            "days": 5,
            "units": "metric",
        }

    def test_empty_string_returns_none(self) -> None:
        coerced, err = _coerce_parameters("")
        assert coerced is None
        assert err is None

    def test_whitespace_only_string_returns_none(self) -> None:
        coerced, err = _coerce_parameters("   \n  ")
        assert coerced is None
        assert err is None


class TestCoerceParametersRejectsInvalid:
    """Invalid shapes yield a clean UnifiedToolOutput.failure — never raise."""

    def test_invalid_json_returns_failure(self) -> None:
        coerced, err = _coerce_parameters("{not-json}")
        assert coerced is None
        assert err is not None
        assert err.success is False
        assert err.error_code == "INVALID_INPUT"
        assert "not a valid JSON" in err.message

    def test_json_array_rejected(self) -> None:
        # parameters must decode to an object, not an array
        coerced, err = _coerce_parameters('["a", "b"]')
        assert coerced is None
        assert err is not None
        assert err.error_code == "INVALID_INPUT"
        assert "object (dict)" in err.message

    def test_json_scalar_rejected(self) -> None:
        coerced, err = _coerce_parameters('"just a string"')
        assert coerced is None
        assert err is not None
        assert err.error_code == "INVALID_INPUT"

    def test_non_dict_non_str_rejected(self) -> None:
        coerced, err = _coerce_parameters(42)  # type: ignore[arg-type]
        assert coerced is None
        assert err is not None
        assert err.error_code == "INVALID_INPUT"
        assert "dict or a JSON string" in err.message
