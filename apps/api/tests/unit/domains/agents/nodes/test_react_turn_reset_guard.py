"""A counter the stop predicate reads is reset at turn start — by declaration.

Measured on production, 2026-09-11. ``react_tool_seconds`` (ADR-256) was
charged by ``react_execute_tools_node`` as ``previous + spent`` and restored by
the checkpoint on every turn, but the router's turn-start reset — a
hand-maintained list written before ADR-256 — never named it. Over six days of
ordinary use one conversation accumulated 913.8 s against a 900 s budget, and
from then on EVERY ReAct turn of that thread stopped at iteration 1 with its
tool calls abandoned: three attempts to create a reminder, all « ko », no error
anywhere. ``react_productive_iterations`` (ADR-248) had the same gap, pointing
the other way: the adaptive budget of ADR-238 was silently extended to the
ceiling from the first turns on.

A routine (one thread per ``scheduled_action`` for its whole life) and a
workboard ticket (one thread per ticket) would have reached the same wall,
slower, and then run every execution without doing anything.

The rule this module keeps: **what a ReAct turn starts with is declared ONCE**
(:func:`react_turn_reset`), the router spreads the declaration, and any key the
stop predicate reads must be in it or be exempted with a written reason. The
hand-maintained list is the thing that failed; a second copy of it is not a fix.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest

from src.domains.agents import models as agent_models
from src.domains.agents.nodes import routing
from src.domains.agents.utils import react_budget
from src.domains.agents.utils.react_budget import (
    REACT_TURN_KEYS_OWNED_BY_SETUP,
    react_exit_reason,
    react_iteration_budget,
    react_turn_reset,
)

pytestmark = [pytest.mark.unit]


#: The functions that DECIDE whether a ReAct loop may keep going — the predicate,
#: the routing edge that applies it — plus the two readers ``react_finalize_node``
#: uses to EXPLAIN. Anything they read from the state and that a previous turn
#: could have left behind must be reset.
_DECIDERS = (
    react_budget.react_exit_reason,
    react_budget.react_iteration_budget,
    react_budget.loop_compute_seconds,
    react_budget.loop_tool_seconds,
    routing.route_from_react_call_model,
)


def _state_keys_read_by(fn: Any) -> set[str]:
    """Every ``state.get("k")`` / ``state["k"]`` literal key inside ``fn``."""
    tree = ast.parse(inspect.getsource(fn))
    keys: set[str] = set()
    for node in ast.walk(tree):
        # state.get("k", …)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "state"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            keys.add(node.args[0].value)
        # state["k"]
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "state"
            and isinstance(node.slice, ast.Constant)
            and isinstance(node.slice.value, str)
        ):
            keys.add(node.slice.value)
    return keys


def _non_literal_state_reads(fn: Any) -> list[str]:
    """Every ``state.get(<expr>)`` / ``state[<expr>]`` whose key is NOT a string literal."""
    tree = ast.parse(inspect.getsource(fn))
    found: list[str] = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "state"
            and node.args
            and not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str))
        ):
            found.append(ast.unparse(node))
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "state"
            and not (isinstance(node.slice, ast.Constant) and isinstance(node.slice.value, str))
        ):
            found.append(ast.unparse(node))
    return found


def _messages_state_keys() -> set[str]:
    tree = ast.parse(inspect.getsource(agent_models.MessagesState))
    cls = tree.body[0]
    assert isinstance(cls, ast.ClassDef)
    return {
        node.target.id
        for node in cls.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }


class TestTheDeclaration:
    """One declaration, read by the router and by this guard."""

    def test_names_the_two_counters_the_incident_found(self) -> None:
        reset = react_turn_reset()

        assert reset["react_tool_seconds"] == 0.0
        assert reset["react_productive_iterations"] == 0

    def test_keeps_the_counters_the_router_already_reset(self) -> None:
        """Moving the list must not lose an entry on the way."""
        reset = react_turn_reset()

        assert reset["react_iteration"] == 0
        assert reset["react_elapsed_seconds"] == 0.0
        assert reset["react_call_digests"] == {}

    def test_every_declared_key_is_a_messages_state_field(self) -> None:
        """An undeclared key is silently dropped by LangGraph: the reset would
        be written and never persisted."""
        missing = set(react_turn_reset()) - _messages_state_keys()

        assert not missing, f"reset keys absent from MessagesState: {sorted(missing)}"

    def test_each_call_returns_fresh_containers(self) -> None:
        """The router MERGES its return into the state; a shared dict instance
        would let one turn's digests leak into the next through the object."""
        first = react_turn_reset()
        second = react_turn_reset()

        assert first["react_call_digests"] is not second["react_call_digests"]

    def test_setup_owned_keys_are_disjoint_from_the_reset(self) -> None:
        """A key cannot be both reset by the router and owned by the setup node:
        two writers at turn start is how the two fell out of sync."""
        assert not set(react_turn_reset()) & REACT_TURN_KEYS_OWNED_BY_SETUP


class TestEverythingTheDeciderReadsIsReset:
    """The guard: the hand-maintained list can no longer miss a counter."""

    @pytest.mark.parametrize("decider", _DECIDERS, ids=lambda fn: fn.__name__)
    def test_every_react_key_read_is_reset_or_exempted(self, decider: Any) -> None:
        read = {k for k in _state_keys_read_by(decider) if k.startswith("react_")}
        covered = set(react_turn_reset()) | REACT_TURN_KEYS_OWNED_BY_SETUP

        assert read, f"{decider.__name__} reads no react_* key — the guard has lost its subject"
        leaked = read - covered
        assert not leaked, (
            f"{decider.__name__} reads {sorted(leaked)} from the state, which nothing "
            "resets at turn start: the value restored from the checkpoint is the "
            "previous turns' total (measured: 913.8 s of tool time, every ReAct turn "
            "of the thread dead at iteration 1). Add it to react_turn_reset() or, if "
            "the setup node computes it, to REACT_TURN_KEYS_OWNED_BY_SETUP with the reason."
        )

    @pytest.mark.parametrize("decider", _DECIDERS, ids=lambda fn: fn.__name__)
    def test_a_decider_reads_the_state_by_literal_key_only(self, decider: Any) -> None:
        """The guard above reads literals. A read through a constant or a
        variable would be invisible to it — and therefore a way to add an
        unreset counter without failing the build. Refuse the shape."""
        assert not _non_literal_state_reads(decider), (
            f"{decider.__name__} reads the state through a non-literal key; the reset "
            "guard cannot see it. Read with a string literal so the guard can."
        )

    def test_the_setup_exemption_is_really_written_by_the_setup_node(self) -> None:
        """An exemption names a writer; the writer must exist."""
        from src.domains.agents.nodes import react_nodes

        source = inspect.getsource(react_nodes.react_setup_node)
        for key in REACT_TURN_KEYS_OWNED_BY_SETUP:
            assert (
                f'"{key}"' in source
            ), f"{key} is exempted as setup-owned but react_setup_node never writes it"


class TestTheInitialStateAgreesWithTheReset:
    """A new conversation starts where every turn restarts — one declaration."""

    def test_create_initial_state_starts_every_counter_at_its_reset_value(self) -> None:
        import uuid

        from src.domains.agents.models import create_initial_state

        state = create_initial_state(uuid.uuid4(), session_id="s", run_id="r")

        for key, expected in react_turn_reset().items():
            assert state[key] == expected, key

    def test_create_initial_state_spreads_the_declaration_rather_than_copying_it(self) -> None:
        """Equal values today are not enough: a copy is what drifted last time."""
        from src.domains.agents import models

        source = inspect.getsource(models.create_initial_state)

        assert "react_turn_reset()" in source, (
            "create_initial_state lists the ReAct counters by hand; spread "
            "react_turn_reset() so the initial state and the turn reset cannot disagree"
        )


class TestAFreshTurnAfterAnExhaustedThread:
    """The incident, replayed on the predicate itself."""

    def test_the_reset_clears_an_exhausted_tool_budget(self) -> None:
        from src.core.config import settings

        stale = {
            "messages": [],
            "react_iteration": 1,
            "react_max_iterations_effective": 90,
            "react_elapsed_seconds": 5.06,
            # The production value, restored by the checkpoint on every turn.
            "react_tool_seconds": float(settings.react_tool_budget_seconds) + 13.79,
            "react_productive_iterations": 40,
            "react_call_digests": {"abc": 3},
        }
        assert react_exit_reason(stale) == "tool_budget", "precondition: the stale thread is dead"

        fresh = {**stale, **react_turn_reset()}

        assert react_exit_reason(fresh) is None

    def test_the_reset_restores_the_adaptive_iteration_budget(self, monkeypatch: Any) -> None:
        """ADR-238's saving on a simple query was silently lost once the productive
        counter outgrew the allowance: the reset gives it back."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "react_progress_extension_enabled", True, raising=False)
        allowance = min(3, int(settings.react_agent_max_iterations))
        stale = {
            "react_max_iterations_effective": allowance,
            "react_productive_iterations": int(settings.react_agent_max_iterations),
        }
        assert react_iteration_budget(stale) > allowance, "precondition: the stale counter inflates"

        fresh = {**stale, **react_turn_reset()}
        # The setup node re-computes the allowance for the new turn; it is the
        # same value for the same query, and is not part of the router reset.
        fresh["react_max_iterations_effective"] = allowance

        assert react_iteration_budget(fresh) == allowance


class TestThroughTheRealCheckpointer:
    """The incident replayed on LangGraph itself: one thread, two turns.

    Turn 1 charges the tool counter the way ``react_execute_tools_node`` does
    (``previous + spent``) and the checkpointer persists it. Turn 2 runs the REAL
    router on the same ``thread_id``; the exhausted counter must not survive
    into the value the stop predicate reads. ``InMemorySaver`` uses the same
    serializer as the PostgreSQL saver, so what is proved here is the merge and
    the round-trip, not a stub of either.
    """

    @pytest.fixture
    def compiled(self) -> Any:
        from unittest.mock import AsyncMock, MagicMock, patch

        from langgraph.checkpoint.memory import InMemorySaver
        from langgraph.graph import END, START, StateGraph

        from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
        from src.domains.agents.context.runtime_context import LiaRuntimeContext
        from src.domains.agents.models import MessagesState
        from src.domains.agents.nodes.router_node_v3 import router_node_v3

        intelligence = QueryIntelligence(
            original_query="rappelle-moi samedi",
            english_query="remind me on saturday",
            immediate_intent="create",
            immediate_confidence=0.9,
            user_goal=next(iter(UserGoal)),
            goal_reasoning="the user wants a reminder",
            domains=["reminder"],
            primary_domain="reminder",
            turn_type="ACTION",
            route_to="planner",
            confidence=0.9,
            reasoning_trace=["domain=reminder"],
        )
        analyzer = MagicMock()
        analyzer.analyze_full = AsyncMock(return_value=intelligence)

        async def charge_tools(state: dict[str, Any]) -> dict[str, Any]:
            # Exactly what react_execute_tools_node writes: previous + spent.
            return {
                "react_tool_seconds": float(state.get("react_tool_seconds") or 0.0) + 913.79,
                "react_productive_iterations": int(state.get("react_productive_iterations") or 0)
                + 1,
            }

        def build(entry: str) -> Any:
            # The typed run context of ADR-231: the router reads it for the
            # execution mode, and a graph run without one is refused.
            graph = StateGraph(MessagesState, context_schema=LiaRuntimeContext)
            graph.add_node("charge_tools", charge_tools)
            graph.add_node("router", router_node_v3)
            graph.add_edge(START, entry)
            graph.add_edge(entry, END)
            return graph

        saver = InMemorySaver()
        turn_one = build("charge_tools").compile(checkpointer=saver)
        turn_two = build("router").compile(checkpointer=saver)
        patcher = patch(
            "src.domains.agents.services.query_analyzer_service.get_query_analyzer_service",
            return_value=analyzer,
        )
        patcher.start()
        try:
            yield turn_one, turn_two
        finally:
            patcher.stop()

    async def test_the_router_overwrites_what_the_checkpoint_restored(self, compiled: Any) -> None:
        import uuid

        from langchain_core.messages import HumanMessage

        from src.domains.agents.context.runtime_context import LiaRuntimeContext

        turn_one, turn_two = compiled
        thread_id = "one-conversation-for-six-days"
        config = {"configurable": {"thread_id": thread_id}}
        context = LiaRuntimeContext(
            user_id=uuid.uuid4(), thread_id=thread_id, conversation_id=thread_id
        )

        await turn_one.ainvoke(
            {"messages": [HumanMessage(content="turn 1")]}, config, context=context
        )
        persisted = (await turn_one.aget_state(config)).values
        assert persisted["react_tool_seconds"] == pytest.approx(913.79)
        assert react_exit_reason(persisted) == "tool_budget", "precondition: the thread is dead"

        await turn_two.ainvoke(
            {"messages": [HumanMessage(content="turn 2")]}, config, context=context
        )
        restarted = (await turn_two.aget_state(config)).values

        assert restarted["react_tool_seconds"] == 0.0
        assert restarted["react_productive_iterations"] == 0
        assert react_exit_reason(restarted) is None
