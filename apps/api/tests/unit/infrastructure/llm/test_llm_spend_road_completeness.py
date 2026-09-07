"""Every module that spends on a model declares which ledger receives it.

Nine times during the audit that produced this guard, reading a file was
enough to reach the wrong conclusion. Tracking in this codebase is **ambient**:
a node inside a turn records its spend through a ``TrackingContext`` its
ancestor published, so the file itself mentions nothing. Grepping for the
tracker therefore produces false positives (a tracked module that names
nothing) and false negatives (an untracked module that names a helper it never
reaches).

Measured 2026-09-07 on production: 84 personality translations ran between
2025-12-11 and 2026-02-05, while ``token_usage_logs`` recorded 5 976 rows
across 17 other surfaces over the same window. Those 84 model calls left no
trace in any ledger — not the user's, not the instance's. Nothing was broken;
nothing had ever been told where that spend should go.

So the road is DECLARED, not inferred, and this guard refuses an omission:

- every module that CALLS ``get_llm`` names its road;
- every declared module still exists and still calls it (a stale entry is how
  a classification survives the code it described).

Both halves matter. Without the second, deleting a spend site leaves a
declaration that makes the registry look complete while covering nothing.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

#: The source tree this guard is responsible for.
_SRC = Path(__file__).resolve().parents[4] / "src"

#: Where ``get_llm`` is defined; it does not spend, it hands out clients.
_FACTORY = "infrastructure/llm/factory.py"


def _calls_get_llm(path: Path) -> bool:
    """Does this module CALL ``get_llm``, rather than merely name it?

    Reads an AST call node, never a substring: a docstring, an import or a
    string mentioning the helper is not a spend site, and a guard that matched
    the NAME would classify all three (the failure mode recorded for
    ``require_superuser``).

    Args:
        path: Module to inspect.

    Returns:
        True when the module contains at least one call to ``get_llm``.
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
        if name == "get_llm":
            return True
    return False


def _spend_sites() -> set[str]:
    """Every module of ``src`` that calls ``get_llm``, as posix-relative paths."""
    sites: set[str] = set()
    for path in _SRC.rglob("*.py"):
        relative = path.relative_to(_SRC).as_posix()
        if relative == _FACTORY:
            continue
        if _calls_get_llm(path):
            sites.add(relative)
    return sites


class TestEverySpendSiteNamesItsLedger:
    """The registry is complete in both directions."""

    def test_no_spend_site_is_undeclared(self) -> None:
        """A new module that spends must say where its euros are recorded."""
        from src.infrastructure.llm.spend_roads import LLM_SPEND_ROADS

        undeclared = _spend_sites() - set(LLM_SPEND_ROADS)
        assert not undeclared, (
            "modules calling get_llm without a declared spend road: "
            f"{sorted(undeclared)} — add each to LLM_SPEND_ROADS with the road "
            "its spend actually takes (turn / proactive / instance)"
        )

    def test_no_declaration_outlives_its_module(self) -> None:
        """A classification that no longer describes anything is removed."""
        from src.infrastructure.llm.spend_roads import LLM_SPEND_ROADS

        stale = set(LLM_SPEND_ROADS) - _spend_sites()
        assert not stale, f"declared but no longer calls get_llm: {sorted(stale)}"

    def test_every_road_is_a_known_destination(self) -> None:
        """Roads come from the enum, so a typo cannot invent a ledger."""
        from src.infrastructure.llm.spend_roads import LLM_SPEND_ROADS, SpendRoad

        for module, road in LLM_SPEND_ROADS.items():
            assert isinstance(road, SpendRoad), f"{module}: {road!r} is not a SpendRoad"


class TestTheInstanceRoadIsNotAnEscapeHatch:
    """``instance`` means "nobody owns this euro", never "unclassified"."""

    def test_instance_road_modules_have_no_account_to_bill(self) -> None:
        """Each instance-road module carries a written reason.

        The reason is the whole protection: ``instance`` is the road that skips
        per-account accounting, so choosing it must be an argued decision. A
        module placed there by default would silently leave a user's quota
        untouched by a spend made on their behalf.
        """
        from src.infrastructure.llm.spend_roads import (
            INSTANCE_ROAD_REASONS,
            LLM_SPEND_ROADS,
            SpendRoad,
        )

        instance_modules = {
            module for module, road in LLM_SPEND_ROADS.items() if road is SpendRoad.INSTANCE
        }
        missing = instance_modules - set(INSTANCE_ROAD_REASONS)
        assert not missing, f"instance road without a written reason: {sorted(missing)}"

        stale = set(INSTANCE_ROAD_REASONS) - instance_modules
        assert (
            not stale
        ), f"reason kept for a module no longer on the instance road: {sorted(stale)}"

        for module, reason in INSTANCE_ROAD_REASONS.items():
            assert reason.strip(), f"{module} is on the instance road without a reason"


class TestTheCallerRoadTerminates:
    """``caller`` names who accounts, so the road graph cannot loop or dangle."""

    def test_every_caller_road_module_names_its_accountant(self) -> None:
        from src.infrastructure.llm.spend_roads import (
            CALLER_ROAD_ACCOUNTANTS,
            LLM_SPEND_ROADS,
            SpendRoad,
        )

        delegating = {
            module for module, road in LLM_SPEND_ROADS.items() if road is SpendRoad.CALLER
        }
        missing = delegating - set(CALLER_ROAD_ACCOUNTANTS)
        assert not missing, f"caller road without a named accountant: {sorted(missing)}"

        stale = set(CALLER_ROAD_ACCOUNTANTS) - delegating
        assert not stale, f"accountant named for a module not on the caller road: {sorted(stale)}"

    def test_every_named_accountant_actually_accounts(self) -> None:
        """The named module must reach a tracking door, not merely exist.

        Without this, ``caller`` degrades into "someone else's problem" — the
        shape that let meeting synthesis, reminder notifications and interest
        clustering each believe another layer was counting.
        """
        from src.infrastructure.llm.spend_roads import CALLER_ROAD_ACCOUNTANTS

        for module, accountant in CALLER_ROAD_ACCOUNTANTS.items():
            path = _SRC / accountant
            assert path.is_file(), f"{module}: accountant {accountant} does not exist"
            assert _calls_any(
                path, ACCOUNTING_DOORS
            ), f"{module}: named accountant {accountant} calls no tracking door"


def _calls_any(path: Path, names: frozenset[str]) -> bool:
    """Does this module CALL one of ``names``?

    AST again, and for a reason this file learned the hard way: several
    ``accounted`` modules mention ``track_proactive_tokens`` only in a
    docstring explaining that some other layer calls it. A substring check
    would read those as accounted and certify a module that counts nothing.

    Args:
        path: Module to inspect.
        names: Function names that constitute accounting.

    Returns:
        True when at least one is called.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError, UnicodeDecodeError:  # pragma: no cover - not our tree
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        called = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
        if called in names:
            return True
    return False


#: Calling any of these means the module opened accounting of its own.
ACCOUNTING_DOORS = frozenset(
    {
        "track_proactive_tokens",
        "track_proactive_tokens_from_result",
        "TrackingContext",
        "record_node_tokens",
        "record_instance_llm_spend",
        "record_instance_llm_call",
    }
)


class TestTheAccountedRoadActuallyAccounts:
    """``accounted`` is a claim about behaviour, so it is checked as one."""

    def test_every_accounted_module_opens_its_own_accounting(self) -> None:
        from src.infrastructure.llm.spend_roads import LLM_SPEND_ROADS, SpendRoad

        silent = sorted(
            module
            for module, road in LLM_SPEND_ROADS.items()
            if road is SpendRoad.ACCOUNTED and not _calls_any(_SRC / module, ACCOUNTING_DOORS)
        )
        assert not silent, (
            f"declared 'accounted' but calls no accounting door: {silent} — "
            "either wire one, or move the module to the 'caller' road and name "
            "the module that does account for it"
        )

    def test_every_instance_module_asks_the_ceiling_or_argues_why_not(self) -> None:
        """Recording is half a ledger; the other half is asking first.

        Measured 2026-09-07, on this codebase, after the road table was
        written: four of five instance modules called
        ``is_instance_spend_blocked`` and the fifth did not — and the guard
        next to this one checked only the RECORDING half, so the asymmetry was
        invisible. A road that records without asking spends past an exhausted
        ceiling and dutifully writes down that it did.
        """
        from src.infrastructure.llm.spend_roads import (
            INSTANCE_GATE_EXEMPT,
            LLM_SPEND_ROADS,
            SpendRoad,
        )

        gate = frozenset({"is_instance_spend_blocked"})
        ungated = sorted(
            module
            for module, road in LLM_SPEND_ROADS.items()
            if road is SpendRoad.INSTANCE
            and module not in INSTANCE_GATE_EXEMPT
            and not _calls_any(_SRC / module, gate)
        )
        assert not ungated, (
            f"declared 'instance' and never asks the ceiling: {ungated} — call "
            "is_instance_spend_blocked() before spending, or declare the "
            "module in INSTANCE_GATE_EXEMPT with the reason it cannot skip "
            "its call"
        )

    def test_no_gate_exemption_outlives_its_road(self) -> None:
        """An exemption for a module that is no longer instance-paid is stale."""
        from src.infrastructure.llm.spend_roads import (
            INSTANCE_GATE_EXEMPT,
            LLM_SPEND_ROADS,
            SpendRoad,
        )

        stale = sorted(
            module
            for module in INSTANCE_GATE_EXEMPT
            if LLM_SPEND_ROADS.get(module) is not SpendRoad.INSTANCE
        )
        assert not stale, f"exempted from a ceiling it no longer reaches: {stale}"

    def test_no_exemption_survives_the_gate_it_no_longer_skips(self) -> None:
        """A module that DOES ask must not keep an excuse for not asking.

        The other direction of the same rule: an exemption nobody needs reads
        as « this one is allowed to spend past the ceiling » long after it
        stopped doing so.
        """
        from src.infrastructure.llm.spend_roads import INSTANCE_GATE_EXEMPT

        gate = frozenset({"is_instance_spend_blocked"})
        pointless = sorted(
            module for module in INSTANCE_GATE_EXEMPT if _calls_any(_SRC / module, gate)
        )
        assert not pointless, (
            f"exempt from the ceiling gate and calling it anyway: {pointless} — "
            "remove the exemption"
        )

    def test_no_exemption_is_granted_without_an_argument(self) -> None:
        from src.infrastructure.llm.spend_roads import INSTANCE_GATE_EXEMPT

        for module, reason in INSTANCE_GATE_EXEMPT.items():
            assert len(reason.strip()) > 40, (
                f"{module}: « {reason} » is not an argument. The point of this "
                "field is that someone had to justify spending past a ceiling."
            )

    def test_an_exempt_module_still_records_what_it_spends(self) -> None:
        """The exemption covers the ASKING, never the ledger."""
        from src.infrastructure.llm.spend_roads import INSTANCE_GATE_EXEMPT

        doors = frozenset({"record_instance_llm_spend", "record_instance_llm_call"})
        silent = sorted(
            module for module in INSTANCE_GATE_EXEMPT if not _calls_any(_SRC / module, doors)
        )
        assert not silent, f"exempt from the gate AND recording nothing: {silent}"

    def test_every_instance_module_records_or_delegates(self) -> None:
        """The instance road must reach the deployment ledger, not merely exist.

        Same property as above, on the other road: an ``instance`` module that
        records nothing spends the deployment's money with no ceiling able to
        see it — which is precisely the state measured on 2026-09-07.
        """
        from src.infrastructure.llm.spend_roads import LLM_SPEND_ROADS, SpendRoad

        doors = frozenset({"record_instance_llm_spend", "record_instance_llm_call"})
        silent = sorted(
            module
            for module, road in LLM_SPEND_ROADS.items()
            if road is SpendRoad.INSTANCE and not _calls_any(_SRC / module, doors)
        )
        assert not silent, f"declared 'instance' but records nothing: {silent}"
