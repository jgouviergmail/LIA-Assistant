"""Migrations must never fail because of their console output (audit F047).

An emoji or any non-ASCII passed to ``print()`` raises ``UnicodeEncodeError``
under a CP1252 Windows console, so ``task db:migrate`` (or a bare
``alembic upgrade``) fails for OUTPUT reasons alone — migration
``2025_11_05_1513`` did exactly this with ``print("✅ ...")``. Migrations must
emit progress via the Alembic logger with ASCII-safe messages; this guard forbids
``print()`` from re-appearing in any migration, killing the class at the source.
"""

from __future__ import annotations

import ast
from pathlib import Path

VERSIONS_DIR = Path(__file__).resolve().parents[2] / "alembic" / "versions"


def _print_call_lines(source: str) -> list[int]:
    """Line numbers of every ``print(...)`` call in *source*."""
    tree = ast.parse(source)
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
    ]


def test_no_migration_uses_print() -> None:
    """No Alembic migration may call print() — it breaks under CP1252 (F047)."""
    offenders: dict[str, list[int]] = {}
    for path in sorted(VERSIONS_DIR.glob("*.py")):
        lines = _print_call_lines(path.read_text(encoding="utf-8"))
        if lines:
            offenders[path.name] = lines
    assert not offenders, (
        "Migrations must not print() — a non-ASCII message raises "
        "UnicodeEncodeError under a CP1252 console (F047). Use "
        '`logging.getLogger("alembic.runtime.migration")` with ASCII messages. '
        f"Offenders (file -> lines): {offenders}"
    )


def test_guard_detects_a_synthetic_print(tmp_path: Path) -> None:
    """The AST scan actually catches a print() call (proves the guard works)."""
    sample = tmp_path / "sample.py"
    sample.write_text("def upgrade():\n    print('boom')\n", encoding="utf-8")
    assert _print_call_lines(sample.read_text(encoding="utf-8")) == [2]
