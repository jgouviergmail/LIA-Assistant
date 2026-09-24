"""No code enters, as a context manager, a database session it did not open (ADR-304).

``AsyncSession.__aexit__`` CLOSES the session: it expunges every object the
session's owner had loaded, and the owner's later writes to them commit
nothing — in silence. The connector clients did exactly that to their callers
(``async with self.connector_service.db as db``) on every token refresh and
every invalidation, proved on PostgreSQL in
``tests/integration/domains/connectors/test_client_session_ownership.py``.

A session reached through an attribute or a bare name (``x.db``, ``session``)
belongs to someone else; it is USED, never entered. A session a block OPENS
is entered through its factory (``get_db_context()``, ``AsyncSessionLocal()``),
which this guard does not look at — a call is not a borrowed object.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: Names under which a session object is passed around in this codebase.
SESSION_NAMES = frozenset({"db", "session", "db_session", "_db", "_session", "async_session"})


def _entered_sessions(tree: ast.AST) -> list[tuple[int, str]]:
    """Every ``async with`` that enters a session object instead of opening one."""
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            expr = item.context_expr
            name = (
                expr.attr
                if isinstance(expr, ast.Attribute)
                else expr.id if isinstance(expr, ast.Name) else None
            )
            if name in SESSION_NAMES:
                found.append((node.lineno, ast.unparse(expr)))
    return found


def test_the_guard_sees_the_defect_it_names() -> None:
    """The scan catches the exact shape ADR-304 removed, and ignores a factory call."""
    borrowed = ast.parse(
        "async def f(self):\n    async with self.connector_service.db as db:\n        pass\n"
    )
    opened = ast.parse("async def f():\n    async with get_db_context() as db:\n        pass\n")
    assert _entered_sessions(borrowed) == [(2, "self.connector_service.db")]
    assert _entered_sessions(opened) == []


def test_no_module_enters_a_session_it_did_not_open() -> None:
    offenders = {
        f"{path.relative_to(SRC).as_posix()}:{line}": expr
        for path in sorted(SRC.rglob("*.py"))
        for line, expr in _entered_sessions(ast.parse(path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        "a session reached through an attribute or a name belongs to its opener — "
        "entering it closes it and expunges the opener's rows. Use it; to own "
        "one, open it (connectors: connector_unit_of_work, ADR-304): "
        f"{offenders}"
    )
