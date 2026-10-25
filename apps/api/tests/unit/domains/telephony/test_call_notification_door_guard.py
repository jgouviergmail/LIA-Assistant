"""Guard: a phone call's notification leaves through ONE door (ADR-290 amendment 2026-10-24).

The chat meter reads a call's bill through the archived message's run id.
Three paths archived a call's words without it, so their bubbles showed no
cost although the call had one. ``telephony/call_notifications`` stamps the
call's run id on every dispatch of the phone-call task type; this guard
refuses any other ``.dispatch(task_type=...)`` naming that task type, whether
it is spelled as a literal or through a module constant.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.telephony.call_notifications import CALL_TASK_TYPE

_SRC = Path(__file__).resolve().parents[4] / "src"
_DOOR = _SRC / "domains" / "telephony" / "call_notifications.py"


def _module_strings(tree: ast.Module) -> dict[str, str]:
    """Module-level names bound to a string literal (``_TASK_TYPE = "…"``)."""
    bound: dict[str, str] = {}
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.Assign):
            targets, value = node.targets, node.value
        elif isinstance(node, ast.AnnAssign):
            targets, value = [node.target], node.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            for target in targets:
                if isinstance(target, ast.Name):
                    bound[target.id] = value.value
    return bound


def _task_type(call: ast.Call, strings: dict[str, str]) -> str | None:
    for keyword in call.keywords:
        if keyword.arg != "task_type":
            continue
        value = keyword.value
        if isinstance(value, ast.Constant) and isinstance(value.value, str):
            return value.value
        if isinstance(value, ast.Name):
            return strings.get(value.id)
    return None


def _call_dispatches_outside_the_door() -> list[str]:
    found: list[str] = []
    for path in sorted(_SRC.rglob("*.py")):
        if path == _DOOR:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        strings = _module_strings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "dispatch"
                and _task_type(node, strings) == CALL_TASK_TYPE
            ):
                found.append(f"{path.relative_to(_SRC).as_posix()}:{node.lineno}")
    return found


@pytest.mark.unit
def test_every_call_notification_leaves_through_the_door() -> None:
    assert _call_dispatches_outside_the_door() == []


@pytest.mark.unit
def test_the_guard_sees_both_spellings() -> None:
    """The guard reads a literal AND a module constant — the two shapes it replaced."""
    literal = ast.parse('d.dispatch(task_type="phone_call")')
    constant = ast.parse('_T = "phone_call"\nd.dispatch(task_type=_T)')
    for tree in (literal, constant):
        calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
        assert _task_type(calls[0], _module_strings(tree)) == CALL_TASK_TYPE
