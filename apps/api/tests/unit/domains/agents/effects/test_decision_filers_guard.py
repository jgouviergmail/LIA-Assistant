"""Every accounting of its own names who files its run in the decision register.

ADR-263 amendment 2026-09-27. Joining the ledger to the decision register by run on dev
(2026-09-27, twelve days) found runs nobody filed: 47 radio sessions, 5 article
translations, 84 journal consolidations — each surface found by reading one
family of run ids at a time, which is not a method. The list is the guard: a
module that opens an accounting of its own (``TrackingContext`` or
``out_of_turn_spend``) is DECLARED — with the modules that file its run's row,
each checked to call a decision door — or with a written reason its run is not
a turn. A call is read from the AST, so an example in a docstring is not one.
"""

from __future__ import annotations

import ast
from functools import cache
from pathlib import Path

import pytest

from src.domains.agents.effects.decision_filers import DECISION_FILERS, NOT_A_TURN

pytestmark = pytest.mark.unit

SRC = Path(__file__).resolve().parents[5] / "src"
OPENERS = frozenset({"TrackingContext", "out_of_turn_spend"})
DOORS = frozenset({"record_decision", "record_decision_once", "decision_recorder"})


@cache
def _called(relative: str) -> frozenset[str]:
    tree = ast.parse((SRC / relative).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.add(node.func.attr)
    return frozenset(names)


def _openers() -> set[str]:
    found: set[str] = set()
    for path in SRC.rglob("*.py"):
        relative = path.relative_to(SRC).as_posix()
        if _called(relative) & OPENERS:
            found.add(relative)
    return found


def test_every_module_opening_an_accounting_is_declared_once() -> None:
    declared = set(DECISION_FILERS) | set(NOT_A_TURN)
    assert not set(DECISION_FILERS) & set(NOT_A_TURN), "declared twice"
    openers = _openers()
    assert openers - declared == set(), "an accounting nobody said who files"
    assert declared - openers == set(), "a declaration for a module that opens none"


@pytest.mark.parametrize("module", sorted(DECISION_FILERS))
def test_every_named_filer_calls_a_decision_door(module: str) -> None:
    filers = DECISION_FILERS[module]
    assert filers, "a declaration naming no filer certifies a gap"
    for filer in filers:
        assert _called(filer) & DOORS, f"{filer} files nothing in the decision register"


@pytest.mark.parametrize("module", sorted(NOT_A_TURN))
def test_every_run_that_is_not_a_turn_says_why(module: str) -> None:
    assert len(NOT_A_TURN[module].split()) >= 12, "a reason, not a label"
