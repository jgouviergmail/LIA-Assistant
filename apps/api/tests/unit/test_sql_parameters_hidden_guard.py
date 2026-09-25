"""Guard: every SQLAlchemy engine the application builds hides its bound parameters.

Without ``hide_parameters=True`` SQLAlchemy writes the bound values of a failed
statement into the exception's text — ``[parameters: ('Jean Dupont',
'jean.dupont@example.org')]``, measured on the dev database on 2026-09-24 — and
into every statement it echoes when ``LOG_LEVEL_SQLALCHEMY`` is raised to
INFO. A bound value is a message body, a name, an address, a memory: whatever
the row holds. The flag is not a verbosity setting to tune per deployment, it
is the boundary, so it is written as a literal ``True`` at every construction
and this guard reads it there.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[2] / "src"

_ENGINE_FACTORIES = frozenset(
    {"create_async_engine", "create_engine", "engine_from_config", "async_engine_from_config"}
)


def _engine_constructions() -> list[tuple[str, int, ast.Call]]:
    found: list[tuple[str, int, ast.Call]] = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.id
                if isinstance(func, ast.Name)
                else func.attr if isinstance(func, ast.Attribute) else ""
            )
            if name in _ENGINE_FACTORIES:
                found.append((str(path.relative_to(SRC)).replace("\\", "/"), node.lineno, node))
    return found


def test_the_scan_sees_the_application_engine() -> None:
    """A guard that finds nothing guards nothing."""
    assert any(
        path == "infrastructure/database/session.py" for path, _, _ in _engine_constructions()
    )


def test_every_engine_hides_its_parameters() -> None:
    offenders = [
        f"{path}:{line}"
        for path, line, call in _engine_constructions()
        if not any(
            keyword.arg == "hide_parameters"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value is True
            for keyword in call.keywords
        )
    ]
    assert not offenders, (
        "an engine renders bound values into its errors and echoed statements — "
        f"pass hide_parameters=True: {offenders}"
    )
