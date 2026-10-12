"""Guard: the turn's resolved references have ONE home and ONE reader.

ADR-120 amendment 2026-10-11. They used to live twice — inside the turn's
query_intelligence and in a state key of their own written only when
non-empty — so the copy outlived its turn (4 of 10 production threads held one,
2026-10-11) and every reader picked a copy and guessed what its values were.
Now the checkpointed form is read through ``turn_references`` /
``read_resolved_references`` alone.
"""

from __future__ import annotations

import ast

import pytest

from src.domains.agents.models import MessagesState
from tests._repo_paths import find_apps_api_root

pytestmark = pytest.mark.unit

SRC = find_apps_api_root() / "src"
KEY = "resolved_references"

#: Modules allowed to read the raw checkpointed value, each with its reason.
#: (``resolved_references.py`` parses a value it is HANDED and reads no key.)
ALLOWED: dict[str, str] = {
    "domains/agents/analysis/query_intelligence_helpers.py": "reconstruction and turn_references",
}


def _raw_reads(tree: ast.AST) -> list[int]:
    lines: list[int] = []
    for node in ast.walk(tree):
        is_get = (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and bool(node.args)
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == KEY
        )
        is_subscript = (
            isinstance(node, ast.Subscript)
            and isinstance(node.slice, ast.Constant)
            and node.slice.value == KEY
        )
        if is_get or is_subscript:
            lines.append(node.lineno)
    return lines


def _reads_by_module() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in sorted(SRC.rglob("*.py")):
        lines = _raw_reads(ast.parse(path.read_text(encoding="utf-8")))
        if lines:
            found[path.relative_to(SRC).as_posix()] = lines
    return found


def test_the_checkpointed_value_has_one_reader() -> None:
    offenders = [
        f"{module}:{line}"
        for module, lines in _reads_by_module().items()
        if module not in ALLOWED
        for line in lines
    ]
    assert not offenders, (
        "Read the turn's references through turn_references(state) or "
        f"read_resolved_references(...), never the raw value: {offenders}"
    )


def test_every_allowance_is_still_needed() -> None:
    reads = _reads_by_module()
    assert [module for module in ALLOWED if module not in reads] == []


def test_the_state_carries_no_copy() -> None:
    assert KEY not in MessagesState.__annotations__
