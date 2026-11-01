"""A tool's choice is written by the person's page alone (spec 2026-10-30 D3, D6).

« Never copied by an install or a share »: a copy is a new server, and no code path but
the page's service may write a choice — so a library install, a peer share or a plugin
can never carry one, whatever it copies. Proven structurally, over every module: the
repository's two writes are called from ``behavior_service.py`` and nowhere else, and
nothing builds a choice row by hand.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"
_WRITES = {"set_choice", "clear_choice"}


def _writers() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for path in _SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
            if name in _WRITES or name == "UserMCPToolChoice":
                found.setdefault(path.relative_to(_SRC).as_posix(), set()).add(name)
    return found


def test_only_the_page_s_service_writes_a_tool_choice() -> None:
    assert _writers() == {"domains/user_mcp/behavior_service.py": _WRITES}
