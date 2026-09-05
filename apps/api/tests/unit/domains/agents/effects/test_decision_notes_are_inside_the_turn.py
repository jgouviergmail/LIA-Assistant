"""A note that arrives after the row is written is a note nobody reads.

This guard exists because the defect it catches was REAL and silent: the first
wiring of lot 6 put ``note_answered`` after the ``async with`` that opens the
decision recorder. ``__aexit__`` runs first, so the row was written before the
answer was noted — and **every turn on the instance would have been recorded as
``interrupted``**. Nothing fails, nothing logs, and the register quietly says the
assistant never answered anyone.

No behavioural test catches it cheaply: the streaming entry point is a 1000-line
async generator, and a test that drove it end to end would be pinning an
enormous amount of unrelated machinery to assert one ordering. So the oracle is
structural — every ``note_*`` call in the module must sit lexically INSIDE the
``async with`` that opens the recorder — and it holds for every future edit, not
just for this one.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit]

SERVICE = Path(__file__).resolve().parents[5] / "src" / "domains" / "agents" / "api" / "service.py"

#: The helpers that enrich the turn's live record. Each one is useless — worse,
#: misleading — once the row has been written.
NOTE_CALLS = frozenset({"note_answered", "note_request_message", "note_route", "note_plan"})

#: What opens the record. A ``note_*`` outside its body arrives too late.
RECORDER = "decision_recorder"


def _tree() -> ast.Module:
    return ast.parse(SERVICE.read_text(encoding="utf-8"))


def _recorder_blocks(tree: ast.Module) -> list[ast.AsyncWith]:
    """Every ``async with`` whose items include the decision recorder."""
    blocks: list[ast.AsyncWith] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncWith):
            continue
        for item in node.items:
            call = item.context_expr
            if (
                isinstance(call, ast.Call)
                and isinstance(call.func, ast.Name)
                and call.func.id == RECORDER
            ):
                blocks.append(node)
    return blocks


def _note_calls(tree: ast.Module) -> list[ast.Call]:
    """Every call to one of the turn's note helpers."""
    return [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in NOTE_CALLS
    ]


def _spans(block: ast.AsyncWith) -> tuple[int, int]:
    """The block BODY's line span — the items themselves are not inside it."""
    lines = [
        line
        for statement in block.body
        for node in ast.walk(statement)
        if (line := getattr(node, "end_lineno", None) or getattr(node, "lineno", None))
    ]
    return block.body[0].lineno, max(lines)


class TestEveryNoteLandsBeforeTheRowIsWritten:
    def test_the_guard_reads_something(self) -> None:
        """Anti-vacuity: a rename or a refactor must fail this file, not mute it."""
        tree = _tree()

        assert _recorder_blocks(tree), "the decision recorder is no longer opened here"
        assert _note_calls(tree), "no note_* call found — the turn records nothing"

    def test_no_note_arrives_after_the_recorder_has_exited(self) -> None:
        tree = _tree()
        blocks = _recorder_blocks(tree)
        spans = [_spans(block) for block in blocks]

        stragglers = [
            call.lineno
            for call in _note_calls(tree)
            if not any(start <= call.lineno <= end for start, end in spans)
        ]

        assert not stragglers, (
            f"note_* called at line(s) {stragglers}, outside the decision recorder's body. "
            "__aexit__ has already written the row by then, so the note is lost and the "
            "turn is recorded as `interrupted` whatever actually happened."
        )
