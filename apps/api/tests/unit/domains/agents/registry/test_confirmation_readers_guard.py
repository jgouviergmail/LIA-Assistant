"""Every reader that decides to ask from a manifest reads ONE predicate (spec 2026-10-30 D6).

A tool the person chose « never ask » for keeps the ``confirm`` policy its declaration
owes and carries ``approved_in_advance``. A reader that decided to ask from the policy
alone would ask the person a question they said they never want — or, read by a
second gate, refuse the call. So the policy is compared to ``"confirm"`` only by
``requires_confirmation``, and the approval given in advance is read only there and by
the effect gate's one point (``effects/preapproval.py``). A new reader fails here
until it goes through the predicate.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[5] / "src"
_RULE = "domains/agents/registry/confirmation_rule.py"
_GATE = "domains/agents/effects/preapproval.py"


@pytest.fixture(scope="module")
def modules() -> list[tuple[str, ast.Module]]:
    return [
        (path.relative_to(_SRC).as_posix(), ast.parse(path.read_text(encoding="utf-8")))
        for path in _SRC.rglob("*.py")
    ]


def _is_policy(node: ast.AST) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "mutation_policy"


def _is_confirm(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and node.value == "confirm"


def test_only_the_predicate_compares_a_manifest_s_policy_to_confirm(
    modules: list[tuple[str, ast.Module]],
) -> None:
    readers = {
        module
        for module, tree in modules
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare)
        and any(_is_policy(side) for side in (node.left, *node.comparators))
        and any(_is_confirm(side) for side in (node.left, *node.comparators))
    }

    assert readers == {_RULE}


def test_only_the_predicate_and_the_gate_read_an_approval_given_in_advance(
    modules: list[tuple[str, ast.Module]],
) -> None:
    readers = {
        module
        for module, tree in modules
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute)
        and node.attr == "approved_in_advance"
        and isinstance(node.ctx, ast.Load)
    }

    assert readers == {_RULE, _GATE}
