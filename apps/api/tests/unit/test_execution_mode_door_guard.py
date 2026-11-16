"""A turn's engine has ONE door, and its request ONE reader (ADR-070).

``LiaRuntimeContext.requested_execution_mode`` is what the turn was ASKED to run
in: a choice the router turns into an engine. Anything else that decides from it
decides from a choice instead of a fact — the sandbox would allow a script to a
turn the planner runs, a register would file a pipeline act as a loop's. So:

- the request is read by the router, which settles the engine, and by the context
  module that answers it;
- the settled engine is read through ``executed_mode_of`` alone;
- it is settled by the router (a new turn) and the context builder (a resumed one).

A rename makes the type checker refuse the old attribute; ``getattr`` with a
string escapes it, which is how two readers kept the old name alive. This guard
reads the AST for every shape.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

_SRC = Path(__file__).resolve().parents[2] / "src"
_CONTEXT = "domains/agents/context/runtime_context.py"
_BUILDER = "domains/agents/context/runtime_context_builder.py"
_ROUTER = "domains/agents/nodes/router_node_v3.py"

#: Who may read the request: the router decides from it, the door falls back on it.
_REQUEST_READERS = frozenset({_ROUTER, _CONTEXT})
#: Who may settle the engine: the router for a new turn, the builder for a resumed one.
_SETTLERS = frozenset({_ROUTER, _BUILDER})
#: Who may read the settled engine: the door.
_ENGINE_READERS = frozenset({_CONTEXT})


def _getattr_name(node: ast.Call) -> str | None:
    """The attribute a ``getattr(x, "<name>", ...)`` call reads, as a literal."""
    if (
        isinstance(node.func, ast.Name)
        and node.func.id == "getattr"
        and len(node.args) >= 2
        and isinstance(node.args[1], ast.Constant)
        and isinstance(node.args[1].value, str)
    ):
        return node.args[1].value
    return None


def offending_uses(source: str, module: str) -> list[str]:
    """Every use of the request or the engine ``module`` is not entitled to.

    Args:
        source: A Python module.
        module: Its path relative to ``src``.

    Returns:
        The offending expressions, as source text.
    """
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and _getattr_name(node) in {
            "requested_execution_mode",
            "turn_engine",
        }:
            found.append(ast.unparse(node))
        elif isinstance(node, ast.Attribute) and isinstance(node.ctx, ast.Load):
            if node.attr == "requested_execution_mode" and module not in _REQUEST_READERS:
                found.append(ast.unparse(node))
            elif node.attr == "settle" and _on_turn_engine(node) and module not in _SETTLERS:
                found.append(ast.unparse(node))
            elif (
                node.attr == "executed" and _on_turn_engine(node) and module not in _ENGINE_READERS
            ):
                found.append(ast.unparse(node))
    return found


def _on_turn_engine(node: ast.Attribute) -> bool:
    return isinstance(node.value, ast.Attribute) and node.value.attr == "turn_engine"


class TestTheGuardSeesTheShapes:
    """A guard that matches nothing guards nothing."""

    @pytest.mark.parametrize(
        "snippet",
        [
            "if context.requested_execution_mode == 'react': pass",
            "mode = getattr(context, 'requested_execution_mode', '')",
            "engine = context.turn_engine.executed",
            "context.turn_engine.settle('react')",
            "holder = getattr(context, 'turn_engine', None)",
        ],
    )
    def test_each_forbidden_shape_is_seen(self, snippet: str) -> None:
        assert len(offending_uses(snippet, "domains/agents/tools/some_tool.py")) == 1

    @pytest.mark.parametrize(
        "snippet",
        [
            "mode = executed_mode_of(context)",
            # Other objects legitimately carry a mode of their own.
            "mode = request.execution_mode",
            "mode = getattr(user, 'execution_mode', None)",
            "kind = getattr(plan, 'execution_mode', 'sequential')",
        ],
    )
    def test_other_reads_are_not_flagged(self, snippet: str) -> None:
        assert offending_uses(snippet, "domains/agents/tools/some_tool.py") == []

    def test_the_entitled_modules_are_not_flagged(self) -> None:
        assert offending_uses("context.turn_engine.settle('react')", _ROUTER) == []
        assert offending_uses("mode = context.requested_execution_mode", _ROUTER) == []
        assert offending_uses("engine = context.turn_engine.executed", _CONTEXT) == []


def test_no_module_reads_the_request_or_the_engine_but_its_door() -> None:
    modules = list(_SRC.rglob("*.py"))
    assert len(modules) > 1000, "the guard lost its subject"
    offenders = {
        relative: uses
        for path in modules
        if (relative := path.relative_to(_SRC).as_posix())
        and (uses := offending_uses(path.read_text(encoding="utf-8"), relative))
    }
    assert offenders == {}, (
        "Read a turn's engine through executed_mode_of; only the router decides from "
        f"the request. Offenders: {offenders}"
    )
