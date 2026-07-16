"""The DB test fixtures isolate by SAVEPOINT, not by per-test schema rebuild (F049).

Recreating the whole schema (``drop_all`` + ``create_all`` over ~100 tables) inside
the function-scoped ``async_engine`` cost ~20 s per DB test and made the integration
suite unusable. The fix creates the schema ONCE (session-scoped ``_db_schema_ready``)
and isolates each test with an external transaction + SAVEPOINT rolled back at
teardown. This guard freezes that contract via the AST (so docstrings mentioning the
old approach never false-match) — a future edit cannot silently reintroduce the
per-test DDL (a ~80x slowdown) without failing here.
"""

from __future__ import annotations

import ast
from pathlib import Path

CONFTEST = Path(__file__).resolve().parents[1] / "conftest.py"
_TREE = ast.parse(CONFTEST.read_text(encoding="utf-8"))


def _fixture(name: str) -> ast.AsyncFunctionDef | ast.FunctionDef:
    for node in ast.walk(_TREE):
        if isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"fixture {name!r} not found in tests/conftest.py")


def _attr_names(node: ast.AST) -> set[str]:
    """All attribute/callable identifiers used in a node (ignores string literals)."""
    names: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute):
            names.add(sub.attr)
        elif isinstance(sub, ast.Name):
            names.add(sub.id)
    return names


def _keyword_args(node: ast.AST) -> set[str]:
    return {kw.arg for kw in ast.walk(node) if isinstance(kw, ast.keyword) and kw.arg}


def _decorator_scope(node: ast.AsyncFunctionDef | ast.FunctionDef) -> str | None:
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            for kw in dec.keywords:
                if kw.arg == "scope" and isinstance(kw.value, ast.Constant):
                    return kw.value.value
    return None


def test_async_engine_does_no_per_test_ddl() -> None:
    """The per-test ``async_engine`` must NOT drop/create the schema (F049)."""
    used = _attr_names(_fixture("async_engine"))
    assert "create_all" not in used and "drop_all" not in used, (
        "async_engine recreates the schema per test again (F049 regression) — the "
        "schema must be built once by the session-scoped _db_schema_ready fixture."
    )


def test_async_session_isolates_by_savepoint() -> None:
    """Per-test isolation must use an external transaction + SAVEPOINT (F049)."""
    node = _fixture("async_session")
    assert "join_transaction_mode" in _keyword_args(node), (
        "async_session no longer joins an external transaction with SAVEPOINT rollback "
        "(F049) — committing tests would then leak state without a per-test schema rebuild."
    )
    assert "rollback" in _attr_names(node)


def test_schema_is_created_once_per_session() -> None:
    """A session-scoped schema fixture must exist (built once, not per test)."""
    node = _fixture("_db_schema_ready")
    assert _decorator_scope(node) == "session", "_db_schema_ready must be session-scoped (F049)"
    assert "create_all" in _attr_names(node)  # it IS the single place that builds the schema
