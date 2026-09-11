"""A state reader never asks for an attribute its producer does not declare.

``get_qi_attr(state, "x")`` ends in ``getattr(obj, "x", default)``: when the
attribute does not exist the call returns the DEFAULT, silently. Nothing
raises, nothing is logged, and the caller reads the absence as a value.

Measured on production 2026-09-11: the recurrence gate asked for ``intent``
while ``QueryIntelligence`` declares ``immediate_intent``. The read returned
``None`` for every turn, ``None != "action"`` held for every turn, and the
recurrence ledger recorded ZERO occurrences against 227 actionable turns —
under 40 green unit tests, because the test fixtures built the very key the
reader expected instead of the shape the producer emits.

This guard closes the CLASS, not the instance: every literal attribute read
through ``get_qi_attr`` must exist on ``QueryIntelligence``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.agents.analysis.query_intelligence import QueryIntelligence

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[2] / "src"


def _declared_names() -> set[str]:
    """Every name a ``QueryIntelligence`` instance actually answers to."""
    return set(QueryIntelligence.__dataclass_fields__) | {
        name for name in dir(QueryIntelligence) if not name.startswith("__")
    }


def _callee_name(node: ast.Call) -> str | None:
    """``f(...)`` → ``f``; ``mod.f(...)`` → ``f`` — a module-qualified call
    reads the same attribute and must not slip past the guard."""
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _attr_argument(node: ast.Call) -> ast.expr | None:
    """The ``attr`` argument, positional or keyword."""
    if len(node.args) >= 2:
        return node.args[1]
    for keyword in node.keywords:
        if keyword.arg == "attr":
            return keyword.value
    return None


def _literal_reads() -> list[tuple[str, int, str]]:
    """(file, line, attribute) for every ``get_qi_attr(state, "literal")``."""
    reads: list[tuple[str, int, str]] = []
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or _callee_name(node) != "get_qi_attr":
                continue
            attr = _attr_argument(node)
            if isinstance(attr, ast.Constant) and isinstance(attr.value, str):
                reads.append((str(path.relative_to(_SRC)), node.lineno, attr.value))
    return reads


def test_every_qi_read_names_a_declared_attribute() -> None:
    declared = _declared_names()
    dead = [
        f"{path}:{line} reads {attr!r}"
        for path, line, attr in _literal_reads()
        if attr not in declared
    ]
    assert dead == [], (
        "These reads resolve to the default forever — the attribute is not on "
        f"QueryIntelligence. Declared: {sorted(QueryIntelligence.__dataclass_fields__)}. "
        f"Offenders: {dead}"
    )


def test_the_guard_can_see_a_real_read() -> None:
    """The guard is worthless if its AST scan matches nothing."""
    assert _literal_reads(), "no get_qi_attr call found — the scan is broken"


def test_the_guard_reads_every_call_shape(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Positional, keyword and module-qualified reads are all seen — the
    shapes a refactor produces without anyone deciding to dodge the guard."""
    (tmp_path / "reader.py").write_text(
        'a = get_qi_attr(state, "one")\n'
        'b = get_qi_attr(state, attr="two")\n'
        'c = helpers.get_qi_attr(state, "three", default=None)\n'
        "d = get_qi_attr(state, dynamic_name)\n",
        encoding="utf-8",
    )
    monkeypatch.setattr("tests.unit.test_qi_attr_contract_guard._SRC", tmp_path)
    assert sorted(attr for _p, _l, attr in _literal_reads()) == ["one", "three", "two"]
