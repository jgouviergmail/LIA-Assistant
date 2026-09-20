"""Every module that can make a paid Google call declares which ledger receives it.

The same defect as the model's spend roads, one family over: accounting is
ambient, so a file that reaches a Maps Platform client says nothing about
whether a tracker was there to receive the euro. On 2026-09-19 the dev ledger
held 3 020 Google rows — every one from a chat turn — while four surfaces
outside a turn (the heartbeat's departure advice, the briefing's weather, a
meeting's reverse geocoding, the static-map proxies) had been paying Google
for months with no row anywhere.

The list this guard walks is the IMPORT graph, complete by construction: a
module cannot call a client it has not imported. Each importer is declared
on a road, a stale declaration fails, an ``ACCOUNTED`` module must actually
open an accounting door, and a ``CALLER`` must name an accountant that does.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from src.domains.google_api.spend_roads import (
    ACCOUNTING_DOORS,
    CALLER_ROAD_ACCOUNTANTS,
    GOOGLE_SPEND_ROADS,
    NOT_A_PAID_CALL,
    PAID_GOOGLE_MODULES,
    SpendRoad,
)

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"

_IMPORT = re.compile(
    r"^\s*(?:from|import)\s+src\.("
    + "|".join(re.escape(m.replace("/", ".")) for m in PAID_GOOGLE_MODULES)
    + r")\b",
    re.MULTILINE,
)


def _importers() -> set[str]:
    """Every module of ``src`` that imports a paid Google entry.

    The clients themselves are the family (they import the counter to record
    what they bill); a relay that builds a client is an importer like any
    other and declares its road.
    """
    found: set[str] = set()
    for path in _SRC.rglob("*.py"):
        relative = path.relative_to(_SRC).as_posix()
        if relative.startswith("domains/connectors/clients/google_"):
            continue
        if _IMPORT.search(path.read_text(encoding="utf-8", errors="ignore")):
            found.add(relative)
    return found


def _declared() -> set[str]:
    return set(GOOGLE_SPEND_ROADS) | set(NOT_A_PAID_CALL)


def _calls(module: str) -> set[str]:
    """The names this module CALLS — an AST call, never a substring."""
    tree = ast.parse((_SRC / module).read_text(encoding="utf-8"))
    return {
        node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
    }


class TestEveryImporterIsOnARoad:
    def test_no_importer_is_undeclared(self) -> None:
        undeclared = sorted(_importers() - _declared())
        assert not undeclared, (
            f"modules reaching a paid Google entry with no road declared: {undeclared} — "
            "declare each in GOOGLE_SPEND_ROADS (TURN, ACCOUNTED or CALLER) or in "
            "NOT_A_PAID_CALL with the reason it makes no paid call"
        )

    def test_no_declaration_outlives_its_import(self) -> None:
        stale = sorted(_declared() - _importers())
        assert not stale, f"declared but no longer imports a paid Google entry: {stale}"

    def test_a_module_appears_in_one_table_only(self) -> None:
        overlap = sorted(set(GOOGLE_SPEND_ROADS) & set(NOT_A_PAID_CALL))
        assert not overlap, f"classified twice: {overlap}"

    def test_no_instance_road(self) -> None:
        """Every Maps Platform call serves one person; nobody may bill nobody."""
        instance = [m for m, road in GOOGLE_SPEND_ROADS.items() if road is SpendRoad.INSTANCE]
        assert not instance, f"a Google spend with no account to bill: {instance}"


class TestTheRoadsTerminateOnARealLedger:
    def test_every_accounted_module_opens_an_accounting_door(self) -> None:
        for module, road in GOOGLE_SPEND_ROADS.items():
            if road is not SpendRoad.ACCOUNTED:
                continue
            assert (
                _calls(module) & ACCOUNTING_DOORS
            ), f"{module} is declared ACCOUNTED but opens none of {sorted(ACCOUNTING_DOORS)}"

    def test_every_caller_names_an_accountant_that_accounts(self) -> None:
        for module, road in GOOGLE_SPEND_ROADS.items():
            if road is not SpendRoad.CALLER:
                continue
            accountants = CALLER_ROAD_ACCOUNTANTS.get(module)
            assert accountants, f"{module} is a CALLER but names no accountant"
            for accountant in accountants:
                assert (_SRC / accountant).exists(), f"{module} names {accountant}, absent"
                assert (
                    _calls(accountant) & ACCOUNTING_DOORS
                ), f"{module} sends its spend to {accountant}, which opens no accounting door"

    def test_every_accountant_serves_a_caller(self) -> None:
        stale = sorted(
            set(CALLER_ROAD_ACCOUNTANTS)
            - {m for m, road in GOOGLE_SPEND_ROADS.items() if road is SpendRoad.CALLER}
        )
        assert not stale, f"accountant declared for a module not on the CALLER road: {stale}"

    def test_every_turn_module_is_a_tool_or_a_tool_relay(self) -> None:
        """A TURN road is only true where a tool executor publishes the tracker."""
        for module, road in GOOGLE_SPEND_ROADS.items():
            if road is not SpendRoad.TURN:
                continue
            assert module.startswith("domains/agents/tools/") or module in {
                "domains/connectors/street_view.py",
                "infrastructure/security/web_risk.py",
            }, f"{module} claims the ambient tracker of a turn but is not run by a tool"

    def test_every_exemption_says_why(self) -> None:
        for module, reason in NOT_A_PAID_CALL.items():
            assert len(reason.split()) >= 8, f"{module}: a reason, not a box ticked"
