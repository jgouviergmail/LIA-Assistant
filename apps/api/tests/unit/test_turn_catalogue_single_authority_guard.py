"""A turn's tool catalogue has ONE builder, and only it sets the request snapshot.

Every reason a tool is withheld — a switched-off capability, an unconnected
provider, an application operation the account may not run — is applied in
``services/turn_catalogue.build_turn_catalogue``. The capability filter once
lived in the pipeline planner alone, so the ReAct loop bound and ran the tools
of a capability an administrator had switched off; and putting the old
expression back on the line that sets the snapshot failed no test.

Read from the AST of ``src/``:

- ``request_tool_manifests_ctx.set(...)`` takes ``await build_turn_catalogue(...)``
  and nothing else;
- ``build_request_tool_manifests(...)`` — the unfiltered base — is called by the
  turn catalogue alone.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"
TURN_CATALOGUE = SRC / "domains" / "agents" / "services" / "turn_catalogue.py"


def _calls_in(text_marker: str) -> list[tuple[Path, ast.Call]]:
    """Every call in ``src/`` whose file mentions ``text_marker``."""
    found: list[tuple[Path, ast.Call]] = []
    for path in SRC.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        if text_marker not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.Call):
                found.append((path, node))
    return found


def _is_snapshot_set(call: ast.Call) -> bool:
    func = call.func
    return (
        isinstance(func, ast.Attribute)
        and func.attr == "set"
        and isinstance(func.value, ast.Name)
        and func.value.id == "request_tool_manifests_ctx"
    )


def _named(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def test_the_snapshot_is_set_from_the_turn_catalogue_only() -> None:
    sets = [
        (path, call)
        for path, call in _calls_in("request_tool_manifests_ctx")
        if _is_snapshot_set(call)
    ]
    assert sets, "the guard matches nothing: the snapshot setter was renamed"
    for path, call in sets:
        (argument,) = call.args
        assert (
            isinstance(argument, ast.Await)
            and isinstance(argument.value, ast.Call)
            and _named(argument.value) == "build_turn_catalogue"
        ), f"{path.relative_to(SRC)}:{call.lineno} sets the snapshot without the turn catalogue"


def test_the_unfiltered_base_is_built_by_the_turn_catalogue_alone() -> None:
    callers = {
        (path, call.lineno)
        for path, call in _calls_in("build_request_tool_manifests")
        if _named(call) == "build_request_tool_manifests"
    }
    assert {path for path, _line in callers} == {TURN_CATALOGUE}, sorted(
        f"{path.relative_to(SRC)}:{line}" for path, line in callers
    )
