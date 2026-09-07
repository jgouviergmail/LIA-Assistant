"""Every euro this platform spends on a model answers to a ceiling.

``cost_bearers`` puts the ``llm`` family on :attr:`CostBearer.INSTANCE`: model
calls run on the keys in ``provider_api_keys``, a table with no ``user_id``, so
**the deployment pays for every one of them**. Two bounds therefore apply — what
one account may consume, and what the instance may spend in a day — and the only
thing outside them is what a person pays with their OWN connector key.

``LLM_SPEND_ROADS`` already names every module that obtains a model. This test
requires each of them to be BOUNDED as well as accounted, and measured before it
existed, 5 of the 46 were not:

- ``evaluation_pipeline`` spent for the operator with no ceiling at all;
- ``open_loop_extractor``, ``briefing/llm``, ``user_mcp/description_generation``
  and ``reminder_notification`` spent against a real account without asking it.

A module is bounded when it goes through a declared chokepoint, asks a ceiling
itself, or runs inside a turn whose ENTRANCE asks one. The third is why the
entrances are named here too: a road that delegates its bound must be able to
say to whom.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[4] / "src"

#: Filled by the test below; the CALLER branch needs the road of an accountant.
LLM_SPEND_ROADS_RAW: dict[str, str] = {}

#: Functions that ASK a ceiling. Any of them, called anywhere in a module,
#: bounds that module's spend.
_ASKS_A_CEILING = frozenset(
    {
        "enforce_usage_limit",
        "spend_blocked",
        "is_instance_spend_blocked",
        "check_user_allowed",
    }
)

#: Callers that are not doors but reach one while carrying the owner, so a
#: module going through them is bounded. Named rather than inferred: a wrapper
#: that stopped threading ``user_id`` would still look like a gate.
_BOUNDED_CALLERS = frozenset({"get_structured_output_with_retry"})

#: Where a turn is bounded. A ``TURN`` module spends inside one of these, which
#: asks the ceiling ONCE at the door rather than at every node — so the road is
#: legitimate, provided the door really asks.
TURN_ENTRANCES: tuple[str, ...] = (
    "domains/agents/api/router.py",
    "domains/agents/api/stream_gates.py",
)


def _called_names(path: Path) -> set[str]:
    """Every function name called anywhere in a module (plain or attribute)."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name):
            names.add(func.id)
        elif isinstance(func, ast.Attribute):
            names.add(func.attr)
    return names


def _spend_roads() -> dict[str, str]:
    """Read the declared roads without importing settings."""
    source = (_SRC / "infrastructure/llm/spend_roads.py").read_text(encoding="utf-8")
    return dict(re.findall(r'"([^"]+\.py)":\s*SpendRoad\.([A-Z]+)', source))


def _caller_accountants() -> dict[str, str]:
    """For each ``CALLER`` module, the module declared to account for it."""
    source = (_SRC / "infrastructure/llm/spend_roads.py").read_text(encoding="utf-8")
    block = source[source.index("CALLER_ROAD_ACCOUNTANTS") :]
    return dict(re.findall(r'"([^"]+[.]py)":\s*"([^"]+[.]py)"', block))


def _chokepoint_functions() -> set[str]:
    source = (_SRC / "infrastructure/llm/usage_guard.py").read_text(encoding="utf-8")
    block = source[source.index("LLM_CHOKEPOINTS") : source.index("def resolve_owner")]
    return set(re.findall(r'"([a-z_]+)"\s*\)', block))


class TestEverySpendSiteAnswersToACeiling:
    def test_the_turn_entrances_ask_a_ceiling(self) -> None:
        """Twenty-five modules delegate their bound to these doors."""
        for entrance in TURN_ENTRANCES:
            path = _SRC / entrance
            assert path.exists(), f"{entrance} is declared a turn entrance but does not exist"
            assert _called_names(path) & _ASKS_A_CEILING, (
                f"{entrance} is where a turn's spend is bounded, and it asks no ceiling — "
                "every TURN-road module behind it is unbounded"
            )

    def test_the_turn_entrances_ask_UNCONDITIONALLY(self) -> None:
        """Matching a NAME is not proof that the check runs.

        A ceiling nested inside a branch bounds only the turns that take that
        branch, and the module would still read as guarded. So the call must
        sit on the straight-line path of its function — no ``if``, ``for``,
        ``while`` or ``try`` between the function body and it.
        """
        for entrance in TURN_ENTRANCES:
            tree = ast.parse((_SRC / entrance).read_text(encoding="utf-8"))
            unconditional = False
            for node in ast.walk(tree):
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                for statement in node.body:
                    calls = {
                        getattr(call.func, "id", getattr(call.func, "attr", ""))
                        for call in ast.walk(statement)
                        if isinstance(call, ast.Call)
                    }
                    if calls & _ASKS_A_CEILING and not isinstance(
                        statement, ast.If | ast.For | ast.While | ast.Try | ast.With
                    ):
                        unconditional = True
            assert unconditional, (
                f"{entrance} asks a ceiling only inside a branch — the turns that "
                "do not take it spend unbounded, and the name alone hid that"
            )

    def test_every_declared_spend_site_is_bounded(self) -> None:
        roads = _spend_roads()
        assert roads, "no spend road declared at all"
        accountants = _caller_accountants()
        global LLM_SPEND_ROADS_RAW  # noqa: PLW0603 - read by the CALLER branch
        LLM_SPEND_ROADS_RAW = roads
        gates = _chokepoint_functions() | _ASKS_A_CEILING | _BOUNDED_CALLERS
        assert "get_structured_output" in gates, "the structured-output door is not declared"

        unbounded: list[str] = []
        for module, road in sorted(roads.items()):
            path = _SRC / module
            if not path.exists():
                unbounded.append(f"{module} (declared, absent)")
                continue
            if road == "TURN":
                # Bounded upstream, at the turn's entrance — asserted above.
                continue
            if road == "CALLER" and not (_called_names(path) & gates):
                # FOLLOWED, never assumed. ``CALLER_ROAD_ACCOUNTANTS`` names
                # the module that ACCOUNTS for the spend, which says nothing
                # about whether it BOUNDS it: measured 2026-09-07, two of the
                # seven accountants asked no ceiling at all, and exempting the
                # road wholesale hid both.
                # It asks nothing itself, so its declared accountant must.
                accountant = accountants.get(module)
                if accountant is None:
                    unbounded.append(f"{module} [CALLER, no accountant declared]")
                    continue
                if LLM_SPEND_ROADS_RAW.get(accountant) == "TURN":
                    continue
                if not (_called_names(_SRC / accountant) & gates):
                    unbounded.append(f"{module} [CALLER -> {accountant}, which asks nothing]")
                continue
            if not (_called_names(path) & gates):
                unbounded.append(f"{module} [{road}]")

        assert (
            not unbounded
        ), "these modules spend the deployment's money with no ceiling asked: " + ", ".join(
            unbounded
        )


class TestTheBoundedCallersReallyCarryTheOwner:
    """A wrapper counts as a gate only while it threads the account through.

    ``get_structured_output_with_retry`` is not itself a door: it delegates to
    the guarded one. If it stopped passing ``user_id`` down, every module
    trusting it would silently spend against no per-account ceiling — and this
    test would be the only thing that noticed.
    """

    def test_the_retry_wrapper_passes_the_owner_to_the_door(self) -> None:
        source = (_SRC / "infrastructure/llm/structured_output.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        wrapper = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef)
            and node.name == "get_structured_output_with_retry"
        )
        assert "user_id" in {arg.arg for arg in wrapper.args.kwonlyargs} | {
            arg.arg for arg in wrapper.args.args
        }, "the wrapper cannot name an owner it never receives"

        forwarded = [
            call
            for call in ast.walk(wrapper)
            if isinstance(call, ast.Call)
            and getattr(call.func, "id", getattr(call.func, "attr", "")) == "get_structured_output"
            and any(kw.arg == "user_id" for kw in call.keywords)
        ]
        assert forwarded, (
            "the retry wrapper calls the guarded door without passing user_id: "
            "every caller relying on it spends against no per-account ceiling"
        )
