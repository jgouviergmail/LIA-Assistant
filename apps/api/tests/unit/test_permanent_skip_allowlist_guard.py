"""Unconditional pytest skips are frozen behind a justified allowlist (audit F019).

The 2026-07 audit found permanent ``@pytest.mark.skip`` markers silently
neutralising whole test areas — the HITL middleware module, HITL SSE E2E,
LangGraph state metrics, checkpoint-table reset paths — with no gate noticing
new ones. This guard AST-scans ``tests/`` for *unconditional* skip markers
(``@pytest.mark.skip`` / module-level ``pytestmark = pytest.mark.skip``, never
``skipif`` nor runtime ``pytest.skip()`` gated on missing infra) and requires
every one to be declared in ``permanent_skips_allowlist.json`` with a category
and reason. A new permanent skip fails CI; a removed one must be dropped from
the allowlist (shrink-only), keeping the audit trail honest.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

API_DIR = Path(__file__).resolve().parents[2]
TESTS_DIR = API_DIR / "tests"
ALLOWLIST_PATH = Path(__file__).with_name("permanent_skips_allowlist.json")
VALID_CATEGORIES = {"dead", "coverage-gap", "tech-debt", "perf"}


def _is_unconditional_skip(node: ast.expr) -> bool:
    """True for ``pytest.mark.skip`` / ``pytest.mark.skip(...)`` (not skipif)."""
    target = node.func if isinstance(node, ast.Call) else node
    attrs: list[str] = []
    cur: ast.expr = target
    while isinstance(cur, ast.Attribute):
        attrs.append(cur.attr)
        cur = cur.value
    return attrs[:2] == ["skip", "mark"]


def _reason(node: ast.expr) -> str:
    if isinstance(node, ast.Call):
        for keyword in node.keywords:
            if keyword.arg == "reason" and isinstance(keyword.value, ast.Constant):
                return str(keyword.value.value)
        for arg in node.args:
            if isinstance(arg, ast.Constant):
                return str(arg.value)
    return "(no reason)"


def _is_pytest_skip_call(node: ast.AST) -> bool:
    """True for a ``pytest.skip(...)`` call expression."""
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "skip"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "pytest"
    )


def _find_unconditional_skip_calls(
    fn: ast.FunctionDef | ast.AsyncFunctionDef, rel: str, found: dict[str, str]
) -> None:
    """Record ``pytest.skip(...)`` calls that fire UNCONDITIONALLY (F019).

    A call sitting directly in the function body (or nested only inside ``with``
    blocks, which do not gate it) runs on every collection — a permanent skip in
    disguise, invisible to the decorator scan. Calls nested in ``if`` / ``try`` /
    ``except`` / ``for`` / ``while`` are conditional (legitimate infra gating,
    e.g. "Redis not available") and are deliberately left alone.
    """

    def scan(body: list[ast.stmt]) -> None:
        for stmt in body:
            if isinstance(stmt, ast.Expr) and _is_pytest_skip_call(stmt.value):
                found[f"{rel}::{fn.name}"] = _reason(stmt.value)
            elif isinstance(stmt, (ast.With, ast.AsyncWith)):
                scan(stmt.body)

    scan(fn.body)


def scan_unconditional_skips(tests_dir: Path) -> dict[str, str]:
    """Map ``<relpath>::<qualname>`` → reason for every unconditional skip.

    Covers both forms: static markers (``@pytest.mark.skip`` / module-level
    ``pytestmark``) AND unconditional ``pytest.skip()`` calls in a test body.
    """
    found: dict[str, str] = {}
    for file in sorted(tests_dir.rglob("test_*.py")):
        rel = file.relative_to(tests_dir.parent).as_posix()
        tree = ast.parse(file.read_text(encoding="utf-8", errors="replace"))
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "pytestmark" for t in node.targets
            ):
                value = node.value
                items = value.elts if isinstance(value, (ast.List, ast.Tuple)) else [value]
                for item in items:
                    if _is_unconditional_skip(item):
                        found[f"{rel}::<module>"] = _reason(item)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                for decorator in node.decorator_list:
                    if _is_unconditional_skip(decorator):
                        found[f"{rel}::{node.name}"] = _reason(decorator)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                _find_unconditional_skip_calls(node, rel, found)
    return found


def _allowlist() -> dict[str, dict[str, str]]:
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))["skips"]


def test_no_unlisted_permanent_skips() -> None:
    """Every unconditional skip in the suite must be justified in the allowlist."""
    current = set(scan_unconditional_skips(TESTS_DIR))
    allowed = set(_allowlist())
    unlisted = current - allowed
    assert not unlisted, (
        "New permanent skip(s) not in permanent_skips_allowlist.json (F019) — "
        "un-skip and fix, delete the dead test, or add a justified allowlist "
        f"entry: {sorted(unlisted)}"
    )


def test_allowlist_has_no_stale_entries() -> None:
    """The allowlist must not reference skips that no longer exist (shrink-only)."""
    current = set(scan_unconditional_skips(TESTS_DIR))
    allowed = set(_allowlist())
    stale = allowed - current
    assert not stale, (
        "Allowlist entries no longer match any skip — remove them from "
        f"permanent_skips_allowlist.json: {sorted(stale)}"
    )


def test_allowlist_entries_are_well_formed() -> None:
    """Each allowlist entry carries a known category and a non-empty reason."""
    for key, meta in _allowlist().items():
        assert (
            meta.get("category") in VALID_CATEGORIES
        ), f"{key}: bad category {meta.get('category')}"
        assert meta.get("reason", "").strip(), f"{key}: empty reason"


def test_scanner_detects_a_synthetic_skip(tmp_path: Path) -> None:
    """A synthetic unconditional skip must be picked up (proves the scanner works)."""
    sample = tmp_path / "test_sample.py"
    sample.write_text(
        "import pytest\n\n"
        "@pytest.mark.skip(reason='synthetic')\n"
        "def test_x():\n    pass\n\n"
        "@pytest.mark.skipif(True, reason='conditional')\n"
        "def test_y():\n    pass\n",
        encoding="utf-8",
    )
    found = scan_unconditional_skips(tmp_path)
    keys = {k.split("::")[-1] for k in found}
    assert "test_x" in keys  # unconditional skip caught
    assert "test_y" not in keys  # skipif ignored


def test_scanner_detects_unconditional_skip_calls(tmp_path: Path) -> None:
    """Unconditional ``pytest.skip()`` calls are caught; gated ones are ignored (F019)."""
    sample = tmp_path / "test_calls.py"
    sample.write_text(
        "import pytest\n\n"
        "def test_unconditional():\n"
        "    pytest.skip('always skips — disguised permanent skip')\n\n"
        "def test_gated():\n"
        "    import os\n"
        "    if not os.environ.get('DB'):\n"
        "        pytest.skip('legitimate infra gating')\n\n"
        "def test_gated_except():\n"
        "    try:\n"
        "        connect()\n"
        "    except OSError:\n"
        "        pytest.skip('service unavailable')\n",
        encoding="utf-8",
    )
    keys = {k.split("::")[-1] for k in scan_unconditional_skips(tmp_path)}
    assert "test_unconditional" in keys  # body-level call caught
    assert "test_gated" not in keys  # inside if → ignored
    assert "test_gated_except" not in keys  # inside except → ignored


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
