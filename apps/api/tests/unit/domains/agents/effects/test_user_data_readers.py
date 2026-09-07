"""No surface opens the person's data in silence.

Three were found one after another — the briefing, the relationship debrief,
the heartbeat sweep — each by someone noticing an absence rather than by a
test. Finding them one at a time is not a method, and the question the owner
asked («  is this happening anywhere else? ») deserves an instrument rather
than an inspection.

The list this guard walks is COMPLETE and enumerable: every ``task_type``
passed to the out-of-turn funnel. A fourteenth surface cannot be added without
answering, in writing, whether it opens the person's sources.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from src.domains.agents.effects.user_data_readers import (
    CONSULTATION_RECORDERS,
    NOT_A_READER,
)

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[5] / "src"

_FUNNELS = {"track_proactive_tokens", "track_proactive_tokens_from_result"}


def _string_constants() -> dict[str, str]:
    """Module-level ``NAME = "value"`` assignments across the tree.

    Several call sites pass a named constant rather than a literal, and a
    guard that only read literals declared those surfaces gone. Resolving the
    names keeps the list COMPLETE, which is the only property that makes this
    guard worth having.
    """
    constants: dict[str, str] = {}
    for path in _SRC.rglob("*.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError, UnicodeDecodeError:  # pragma: no cover - not our tree
            continue
        for node in tree.body:
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else (
                    [node.target]
                    if isinstance(node, ast.AnnAssign) and node.value is not None
                    else []
                )
            )
            value = getattr(node, "value", None)
            if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
                continue
            for target in targets:
                if isinstance(target, ast.Name):
                    constants[target.id] = value.value
    return constants


def _declared_task_types() -> set[str]:
    """Every ``task_type`` handed to the out-of-turn funnel, read from source.

    Three shapes, and all three are needed for the list to be COMPLETE: a
    literal, a named constant resolved from the tree, and — for the surfaces
    the proactive runner drives, where the argument is ``self.task.task_type``
    — the ``task_type`` a ``ProactiveTask`` subclass declares.
    """
    constants = _string_constants()
    found: set[str] = _runner_driven_task_types()
    for path in _SRC.rglob("*.py"):
        if path.name == "tracking.py" and path.parent.name == "proactive":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError, UnicodeDecodeError:  # pragma: no cover - not our tree
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name not in _FUNNELS:
                continue
            for keyword in node.keywords:
                if keyword.arg != "task_type":
                    continue
                value = keyword.value
                if isinstance(value, ast.Constant) and isinstance(value.value, str):
                    found.add(value.value)
                elif isinstance(value, ast.Name) and value.id in constants:
                    found.add(constants[value.id])
    return found


def _runner_driven_task_types() -> set[str]:
    """The ``task_type`` every ``ProactiveTask`` subclass declares.

    The runner passes ``self.task.task_type``, which no AST can resolve at the
    call site — but the tasks name themselves, and that declaration is what
    the register files their rows under.
    """
    found: set[str] = set()
    for path in _SRC.rglob("proactive_task.py"):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError, UnicodeDecodeError:  # pragma: no cover - not our tree
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.AnnAssign) or node.value is None:
                continue
            target = node.target
            if not isinstance(target, ast.Name) or target.id != "task_type":
                continue
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                found.add(node.value.value)
    return found


#: The seam a domain records through. It is the SEAM and not the register's
#: own function: ``agents`` imports ``relations``, so a domain that reached
#: back into the register would close a cycle — the dependency is inverted
#: (``domains/shared/consultation_sink``), and this is what a reader calls.
_RECORDERS = frozenset(
    {
        "record_surface_consultations",
        "record_consultation",
        "record_out_of_turn_consultation",
    }
)


def _calls_the_recorder(path: Path) -> bool:
    """Does this module CALL the consultation seam?

    An AST call, never a substring: a docstring saying a module records is not
    a module that records, and that is precisely the confusion this guard
    exists to refuse.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError, UnicodeDecodeError:  # pragma: no cover - not our tree
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if name in _RECORDERS:
            return True
    return False


class TestEverySurfaceAnswersTheQuestion:
    """Reader or not, in writing — never by omission."""

    def test_no_out_of_turn_surface_is_unclassified(self) -> None:
        classified = set(CONSULTATION_RECORDERS) | set(NOT_A_READER)
        unclassified = _declared_task_types() - classified
        assert not unclassified, (
            f"out-of-turn surfaces that say nothing about the person's data: "
            f"{sorted(unclassified)} — declare each in CONSULTATION_RECORDERS "
            "(with the module that records it) or in NOT_A_READER (with the "
            "reason it opens nothing)"
        )

    def test_no_classification_outlives_its_surface(self) -> None:
        """A declaration for a surface that no longer exists is a stale claim.

        Two populations meet in this registry, and both are enumerable:

        - the out-of-turn SPEND surfaces, named by their ``task_type`` — the
          list this guard was written for;
        - the direct-read surfaces of ``CONSULTATION_SURFACES``, which record
          consultations without necessarily spending anything (a documentary
          space reads Drive; the push wake probes a mailbox; geocoding an
          address costs Maps, not tokens).

        A key belonging to neither is a typo, and a typo here silently
        exempts a surface from the very question this registry asks.
        """
        from src.domains.shared.consultation_surfaces import CONSULTATION_SURFACES

        known = _declared_task_types() | set(CONSULTATION_SURFACES)
        classified = set(CONSULTATION_RECORDERS) | set(NOT_A_READER)
        stale = classified - known
        assert not stale, (
            f"declared but neither an out-of-turn task type nor a declared "
            f"consultation surface: {sorted(stale)}"
        )

    def test_a_surface_is_never_both(self) -> None:
        overlap = set(CONSULTATION_RECORDERS) & set(NOT_A_READER)
        assert not overlap, f"declared as reader AND non-reader: {sorted(overlap)}"


class TestTheDeclarationsAreTrue:
    """A pointer to a module that records nothing certifies a gap."""

    def test_every_named_recorder_actually_records(self) -> None:
        for surface, module in CONSULTATION_RECORDERS.items():
            path = _SRC / module
            assert path.is_file(), f"{surface}: {module} does not exist"
            assert _calls_the_recorder(path), (
                f"{surface}: {module} is named as its recorder but never calls "
                "record_consultation"
            )

    def test_every_non_reader_carries_a_written_reason(self) -> None:
        for surface, reason in NOT_A_READER.items():
            assert reason.strip(), f"{surface} is declared a non-reader with no reason"
            assert len(reason) > 40, (
                f"{surface}: « {reason} » is not an argument. The point of this "
                "field is that someone had to think about it."
            )
