"""Systemic guard: no bare enum member as the RESULT of a SQLAlchemy ``case()``.

A ``case()`` result that is a bare enum member (``case((cond, Status.FAILED),
else_=Status.STOPPED)``) is bound as ``NullType``: SQLAlchemy runs no bind
processor on it, so a ``native_enum=False`` column — which stores the member
NAME — receives the member VALUE. The write commits garbage or, with a
``RETURNING`` on the column, fails and rolls the transition back. Measured in
production on 2026-09-05 (``domains/meetings/repository.py::fail_or_retry``):
one stuck meeting re-driven every 15 minutes for two hours.

The convention is to carry the column's type on the literal::

    case((cond, literal(Status.FAILED, Model.status.type)), else_=...)

This test scans every ``case(`` call under ``src/`` and fails on any result
(a ``whens`` tuple's second element, or ``else_``) that is an attribute of a
name looking like an enum class and is not wrapped in ``literal(`` / ``cast(``
/ ``type_coerce(``. The name heuristic is deliberately broad: a false positive
costs one ``literal(...)`` wrapper, a false negative costs an incident.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC_DIR = Path(__file__).parents[1] / "src"

# A class name that reads as an enum of stored states.
_ENUM_CLASS_RE = re.compile(
    r".*(Status|State|Kind|Type|Provider|Format|Selection|Mode|Source|Level|Outcome|Category)$"
)
_TYPED_WRAPPERS = frozenset({"literal", "cast", "type_coerce"})


def _is_bare_enum_member(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and bool(_ENUM_CLASS_RE.match(node.value.id))
        and node.attr.isupper()
    )


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def _case_results(call: ast.Call) -> list[ast.AST]:
    """The result expressions of one ``case()`` call: each when's value and ``else_``."""
    results: list[ast.AST] = []
    for arg in call.args:
        if isinstance(arg, ast.Tuple) and len(arg.elts) == 2:
            results.append(arg.elts[1])
    for keyword in call.keywords:
        if keyword.arg == "else_":
            results.append(keyword.value)
    return results


def bare_enum_case_results(tree: ast.AST) -> list[int]:
    """Line numbers of ``case()`` results that are bare enum members."""
    offenders: list[int] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or _call_name(node) != "case":
            continue
        for result in _case_results(node):
            if _is_bare_enum_member(result):
                offenders.append(result.lineno)
    return offenders


def test_the_scanner_flags_a_bare_member_and_accepts_a_typed_literal() -> None:
    bad = ast.parse(
        "stmt = update(M).values(status=case((M.n >= 3, MeetingStatus.FAILED), "
        "else_=MeetingStatus.STOPPED))"
    )
    good = ast.parse(
        "stmt = update(M).values(status=case((M.n >= 3, literal(MeetingStatus.FAILED, T)), "
        "else_=literal(MeetingStatus.STOPPED, T)))"
    )
    integer_result = ast.parse("total = case((Doc.status == DocStatus.READY, 1), else_=0)")
    assert bare_enum_case_results(bad) == [1, 1]
    assert bare_enum_case_results(good) == []
    assert bare_enum_case_results(integer_result) == []


def test_no_sql_case_in_src_returns_a_bare_enum_member() -> None:
    offenders: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "case(" not in source:
            continue
        tree = ast.parse(source, filename=str(path))
        for lineno in bare_enum_case_results(tree):
            offenders.append(f"{path.relative_to(SRC_DIR).as_posix()}:{lineno}")
    assert not offenders, (
        "Bare enum members as case() results (bound as NullType, the VALUE is written "
        "where the column stores the NAME) — wrap them in "
        "`literal(member, Model.column.type)`:\n  " + "\n  ".join(offenders)
    )
