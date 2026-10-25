"""Who a connection's NAME designates is decided by one rule, never re-derived.

The defect this closes: the router recognised a first name (``name_mentions``)
while three tools compared the folded FULL name themselves, so a question the
router sent to a connected user's tool was refused by that tool. The three
sites now resolve through ``shared/name_resolution``; a module that folds and
compares names on its own again is a second rule waiting to disagree.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[4] / "src"

#: Every module that designates a connected user by name.
RESOLVING_MODULES = (
    "domains/agents/tools/peers_read_tools.py",
    "domains/agents/tools/peers_tools.py",
    "domains/workboard/service.py",
)


@pytest.mark.parametrize("module", RESOLVING_MODULES)
def test_connection_names_are_never_folded_and_compared_locally(module: str) -> None:
    tree = ast.parse((SRC / module).read_text(encoding="utf-8"))
    folds = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "fold_name"
    ]
    assert not folds, (
        f"{module} folds names itself (lines {folds}): resolve them through "
        "shared/name_resolution so the router and the tools agree on who exists."
    )
