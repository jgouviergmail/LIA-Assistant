"""Vocabulary guard for agent result statuses (ADR-303).

An enumeration is a contract between a producer and a reader. When one writes a
value the other has never heard of, nothing fails — the reader takes its
fallback branch and the feature dies in silence. Measured 2026-09-09 and still
true on v1.47.1: ``mappers.py`` published ``failed``, the response formatter
knew only ``success``/``error``/``connector_disabled``, so every failed plan
reached the model as « ❓ plan_executor: Statut inconnu (failed) » with the
error text dropped. Two other values of the same ``Literal`` —
``connector_disabled`` and ``pending`` — had no producer at all.

Three rules, each closing one half of that:

1. The ``Literal`` on the schema IS the enum — they cannot drift apart.
2. No reader compares a status against a value the vocabulary has retired.
3. Every member is produced somewhere and read somewhere else.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import get_args

import pytest

from src.domains.agents.constants import AgentResultStatus
from src.domains.agents.orchestration.schemas import AgentResult

pytestmark = [pytest.mark.unit]

AGENTS_DIR = Path(__file__).parents[4] / "src" / "domains" / "agents"

#: Values once compared against ``status`` that the vocabulary no longer holds.
#: ``failure`` never existed at all — a reader invented it (business_metrics).
RETIRED_STATUS_LITERALS = frozenset({"failed", "pending", "connector_disabled", "failure"})

#: Files whose ``status`` belongs to ANOTHER vocabulary, each with its reason.
#: A path is exempt only when its ``status`` provably names a different thing.
STATUS_COMPARE_ALLOWLIST: dict[str, str] = {
    "services/streaming/debug_metrics_stages.py": (
        "counts EffectStatus rows of agent_effects, not an AgentResult status"
    ),
    "emails/digest.py": (
        "DIGEST_STATUS_FIELD holds its own vocabulary (computed/cached/failed) "
        "stamped on an e-mail dict by EmailDigestService, never an AgentResult"
    ),
}


def _string_literals(node: ast.AST) -> set[str]:
    """Every string constant a comparison operand can carry."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return {node.value}
    if isinstance(node, ast.Tuple | ast.List | ast.Set):
        return {
            element.value
            for element in node.elts
            if isinstance(element, ast.Constant) and isinstance(element.value, str)
        }
    return set()


def _status_compare_violations(tree: ast.AST) -> list[tuple[int, list[str]]]:
    """``(lineno, retired values)`` for every comparison of a status to a dead value."""
    found: list[tuple[int, list[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Compare):
            continue
        operands = [node.left, *node.comparators]
        literals: set[str] = set()
        for operand in operands:
            literals |= _string_literals(operand)
        hit = literals & RETIRED_STATUS_LITERALS
        if hit and any("status" in ast.unparse(operand).lower() for operand in operands):
            found.append((node.lineno, sorted(hit)))
    return found


def _python_files() -> list[Path]:
    return sorted(path for path in AGENTS_DIR.rglob("*.py") if "__pycache__" not in path.parts)


class TestVocabularyIsOneThing:
    """The schema and the enum cannot drift."""

    def test_the_literal_and_the_enum_are_the_same_vocabulary(self) -> None:
        literal_values = set(get_args(AgentResult.model_fields["status"].annotation))
        assert literal_values == {member.value for member in AgentResultStatus}
        assert literal_values == {"success", "error"}


class TestNoReaderComparesADeadValue:
    """A retired value compared anywhere is a reader nobody will ever satisfy."""

    def test_no_reader_compares_status_against_a_retired_value(self) -> None:
        offenders: list[str] = []
        for path in _python_files():
            rel = path.relative_to(AGENTS_DIR).as_posix()
            if rel in STATUS_COMPARE_ALLOWLIST:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for lineno, hit in _status_compare_violations(tree):
                offenders.append(f"{rel}:{lineno} compares a status against {hit}")
        assert (
            not offenders
        ), "Compare against AgentResultStatus, never a retired value:\n" + "\n".join(offenders)

    def test_every_allowlisted_file_still_exists_and_still_needs_it(self) -> None:
        """An allowlist entry that no longer applies is a hole nobody notices."""
        for rel, reason in STATUS_COMPARE_ALLOWLIST.items():
            path = AGENTS_DIR / rel
            assert path.exists(), f"{rel} is allowlisted but gone — remove the entry"
            assert reason.strip(), f"{rel} is allowlisted without a reason"
            tree = ast.parse(path.read_text(encoding="utf-8"))
            assert _status_compare_violations(
                tree
            ), f"{rel} no longer compares a retired value — remove it from the allowlist"


class TestEveryMemberIsProducedAndRead:
    """A member nobody writes, or nobody reads, is a branch that cannot fire."""

    def test_every_member_lives_in_at_least_two_modules(self) -> None:
        texts = {
            path.relative_to(AGENTS_DIR).as_posix(): path.read_text(encoding="utf-8")
            for path in _python_files()
            if path.name != "constants.py"
        }
        for member in AgentResultStatus:
            pattern = re.compile(
                rf"AgentResultStatus\.{member.name}\b"
                rf'|status\s*=\s*"{member.value}"'
                rf'|"status":\s*"{member.value}"'
                rf'|==\s*"{member.value}"'
            )
            files = sorted(rel for rel, text in texts.items() if pattern.search(text))
            assert len(files) >= 2, (
                f"{member.name} appears in fewer than two modules: {files}. "
                "A status is a contract: it needs a producer and a reader."
            )


class TestTheScanItself:
    """A guard nobody checks rots — pin the scanner on synthetic input."""

    def test_the_scan_detects_synthetic_violations(self) -> None:
        snippet = (
            'if status == "failed":\n'
            "    pass\n"
            'if result.get("status") in ("failure", "error"):\n'
            "    pass\n"
        )
        found = [hit for _, hit in _status_compare_violations(ast.parse(snippet))]
        assert found == [["failed"], ["failure"]]

    def test_the_scan_ignores_unrelated_comparisons(self) -> None:
        snippet = (
            'if outcome == "failed":\n'  # not a status
            "    pass\n"
            'if status == "success":\n'  # a live value
            "    pass\n"
        )
        assert _status_compare_violations(ast.parse(snippet)) == []
