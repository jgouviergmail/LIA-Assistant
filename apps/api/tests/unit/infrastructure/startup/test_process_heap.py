"""The startup heap is frozen last, and the lifespan says so (ADR-283 amendment 2026-10-12)."""

from __future__ import annotations

import ast
import gc
from pathlib import Path

import pytest

from src.infrastructure.startup import process_heap

pytestmark = pytest.mark.unit

MAIN = Path(__file__).resolve().parents[4] / "src" / "main.py"


class TestFreezeStartupHeap:
    def test_everything_alive_leaves_the_collector(self) -> None:
        before = gc.get_freeze_count()
        gc.unfreeze()
        try:
            keep = [[] for _ in range(10)]  # tracked containers, alive at the freeze

            frozen = process_heap.freeze_startup_heap()

            # The count can only shrink after the call: a frozen object that is
            # deallocated leaves the permanent generation (measured off by one
            # under xdist, a temporary released after the count was read).
            assert 0 < gc.get_freeze_count() <= frozen
            assert frozen >= 10
            # What was alive at the freeze is no longer tracked by any generation.
            kept = {id(container) for container in keep}
            assert not any(id(obj) in kept for obj in gc.get_objects())
            del keep
        finally:
            gc.unfreeze()
            assert gc.get_freeze_count() == 0
            if before:
                gc.freeze()

    def test_a_second_call_freezes_what_was_allocated_since(self) -> None:
        gc.unfreeze()
        try:
            first = process_heap.freeze_startup_heap()
            later = [[] for _ in range(5)]  # tracked containers allocated after the freeze
            second = process_heap.freeze_startup_heap()
            assert second >= first + 5
            del later
        finally:
            gc.unfreeze()


def _lifespan_statements() -> list[ast.stmt]:
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "lifespan":
            return node.body
    raise AssertionError("main.lifespan not found")


def _calls(stmt: ast.stmt) -> list[str]:
    return [ast.unparse(n.func) for n in ast.walk(stmt) if isinstance(n, ast.Call)]


class TestTheLifespanFreezesLast:
    def test_the_freeze_is_the_last_startup_call_before_the_yield(self) -> None:
        body = _lifespan_statements()
        yield_index = next(
            i
            for i, stmt in enumerate(body)
            if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Yield)
        )
        startup_calls = [
            (i, call) for i, stmt in enumerate(body[:yield_index]) for call in _calls(stmt)
        ]
        freeze_positions = [
            i for i, call in startup_calls if call == "process_heap.freeze_startup_heap"
        ]

        assert freeze_positions, "the lifespan does not freeze the startup heap"
        after_freeze = {
            call
            for i, call in startup_calls
            if i > freeze_positions[-1] and not call.startswith("logger.")
        }
        assert (
            not after_freeze
        ), f"startup work after the freeze would not be frozen: {after_freeze}"
