"""No code iterates a session dependency with ``async for`` (2026-10-25).

``get_db_session`` and ``get_db`` are FastAPI ``yield`` dependencies: whatever
ends their caller must be thrown INTO them — FastAPI does it through a context
manager — so that their rollback branch runs and the session closes with the
block. Iterated with ``async for`` they receive nothing: a failure never reached
the rollback, and a ``break`` left the generator suspended, its commit and close
waiting for the garbage collector. ``core/dependencies.get_db`` did it for every
route, the unverified-account sweep for itself. A route depends on ``get_db``;
any other code opens its session with ``get_db_context()``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

#: The ``yield`` dependencies that hand out a database session.
SESSION_DEPENDENCIES = frozenset({"get_db_session", "get_db"})


def _called_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    if isinstance(call.func, ast.Name):
        return call.func.id
    return None


def iterated_session_dependencies(tree: ast.AST) -> list[int]:
    """The line of every ``async for`` over a session dependency."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFor)
        and isinstance(node.iter, ast.Call)
        and _called_name(node.iter) in SESSION_DEPENDENCIES
    ]


def test_the_guard_sees_the_shapes_it_names() -> None:
    delegated = (
        "async def get_db():\n"
        "    async for session in get_db_session():\n"
        "        yield session\n"
    )
    swept = (
        "async def sweep():\n"
        "    async for session in session_module.get_db_session():\n"
        "        await session.execute(statement)\n"
        "        break\n"
    )
    entered = (
        "async def sweep():\n"
        "    async with get_db_context() as session:\n"
        "        await session.execute(statement)\n"
    )

    assert iterated_session_dependencies(ast.parse(delegated)) == [2]
    assert iterated_session_dependencies(ast.parse(swept)) == [2]
    assert iterated_session_dependencies(ast.parse(entered)) == []


def test_no_module_iterates_a_session_dependency() -> None:
    offenders = sorted(
        f"{path.relative_to(SRC).as_posix()}:{line}"
        for path in SRC.rglob("*.py")
        for line in iterated_session_dependencies(ast.parse(path.read_text(encoding="utf-8")))
    )

    assert not offenders, (
        "a session dependency iterated with `async for` never receives what ends "
        "its caller: enter it as a context manager, or open the session with "
        f"get_db_context(): {offenders}"
    )
