"""One reading of « did this tool call succeed? », shared by every reader (ADR-303).

Three readers used to answer that question differently on the same payload:
the consultation register read the payload and said ``failed``, the metrics
decorator never looked and said ``success="true"``, and the ReAct loop read
``success`` on a dict only — so a Pydantic ``UnifiedToolOutput.failure`` fell
through to ``bool(model)`` and counted as productive. Measured in production on
2026-09-09: four 403s recorded ``failed`` by the register and ``success="true"``
by Prometheus, from the same four calls.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.core.tool_outcome import (
    TOOL_ERROR_CODE_MAX_CHARS,
    error_code_of,
    explicit_success,
)

pytestmark = [pytest.mark.unit]


class _Output:
    """A ``UnifiedToolOutput``-shaped object (the real one is Pydantic)."""

    def __init__(self, success: bool, error_code: str | None = None) -> None:
        self.success = success
        self.error_code = error_code


class TestExplicitSuccess:
    """False ONLY when the tool said so — silence is never a failure."""

    @pytest.mark.parametrize(
        ("result", "expected"),
        [
            ({"success": False, "error_code": "FORBIDDEN"}, False),
            ({"success": True}, True),
            ({"data": [1, 2]}, True),
            (_Output(False, "TIMEOUT"), False),
            (_Output(True), True),
            ("plain text", True),
            ([], True),
            (None, True),
        ],
    )
    def test_explicit_success(self, result: object, expected: bool) -> None:
        assert explicit_success(result) is expected


class TestErrorCodeOf:
    """The code labels a metric and a log — never the message, never PII."""

    def test_reads_a_dict(self) -> None:
        payload = {"success": False, "error_code": "FORBIDDEN", "error": "secret url"}
        assert error_code_of(payload) == "FORBIDDEN"

    def test_reads_an_object(self) -> None:
        assert error_code_of(_Output(False, "TIMEOUT")) == "TIMEOUT"

    def test_absent_code_is_none(self) -> None:
        assert error_code_of({"success": False}) is None
        assert error_code_of("plain text") is None


class TestLayerBoundary:
    """``core`` is imported by infrastructure AND by domains — it imports neither."""

    def test_core_module_imports_no_layer_below(self) -> None:
        source = (Path(__file__).parents[3] / "src" / "core" / "tool_outcome.py").read_text(
            encoding="utf-8"
        )
        modules = [
            node.module or ""
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom)
        ]
        assert not [
            module for module in modules if module.startswith(("src.domains", "src.infrastructure"))
        ]


class TestThePredicateNeverBreaksWhatItObserves:
    """Reading a result must never turn a SUCCESSFUL call into a failure.

    ``_record_returned_outcome`` runs INSIDE the decorator's ``try``, so an
    exception raised while reading the payload would be caught by the tool's
    own error path: the call succeeded, the caller gets an exception, and the
    metrics record a failure that never happened. An observer never changes
    what it observes — so the predicate is TOTAL (ADR-303 cold review).
    """

    class _Exploding:
        @property
        def success(self) -> bool:
            raise RuntimeError("attribute access blew up")

        @property
        def error_code(self) -> str:
            raise RuntimeError("attribute access blew up")

    def test_an_unreadable_payload_is_not_a_declared_failure(self) -> None:
        assert explicit_success(self._Exploding()) is True

    def test_an_unreadable_code_is_none(self) -> None:
        assert error_code_of(self._Exploding()) is None


class TestWhatTravelsIsBounded:
    """A code reaches a metric label and a log line — it is bounded, or it is a leak."""

    def test_a_runaway_code_is_cut(self) -> None:
        code = error_code_of({"error_code": "C" * 9000})
        assert code is not None
        assert len(code) == TOOL_ERROR_CODE_MAX_CHARS

    def test_a_non_string_code_is_still_bounded(self) -> None:
        code = error_code_of({"error_code": {"nested": "x" * 9000}})
        assert code is not None
        assert len(code) <= TOOL_ERROR_CODE_MAX_CHARS
