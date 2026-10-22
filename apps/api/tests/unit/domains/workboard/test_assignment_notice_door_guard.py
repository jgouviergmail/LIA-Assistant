"""An assignment notice leaves through ONE door, after the commit.

Sent from inside a mutation, a notice deadlocked production on 2026-10-21: the
mutation fence holds the accounts' ``users`` rows FOR UPDATE, and the notice
claims its act in ``agent_effects`` on a connection of its own, whose foreign key
waits for the recipient's row. ``dispatch_committed_assignment_notices`` is the
only caller allowed: it runs after the caller's commit, on a session of its own.
"""

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "src"
DOOR_MODULE = SRC / "domains" / "workboard" / "assignment_notifications.py"


def _callers_of(name: str) -> list[str]:
    found: list[str] = []
    for path in SRC.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            target = node.func
            called = (
                target.id
                if isinstance(target, ast.Name)
                else target.attr if isinstance(target, ast.Attribute) else None
            )
            if called == name:
                found.append(f"{path.relative_to(SRC).as_posix()}:{node.lineno}")
    return found


def test_only_the_after_commit_door_sends_assignment_notices() -> None:
    callers = _callers_of("dispatch_assignment_notices")
    door = DOOR_MODULE.relative_to(SRC).as_posix()
    assert callers, "the door itself must still send them"
    assert all(caller.startswith(f"{door}:") for caller in callers), callers
