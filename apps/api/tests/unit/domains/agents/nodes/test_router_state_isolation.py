"""The router decides; it never writes to the conversation.

The router's decision is a structured `RouterOutput`. If it ever leaked into
``state["messages"]``, the user would read raw routing JSON in their chat —
``{"intention": "action", "confidence": 0.9, ...}`` — instead of an answer.

That invariant used to be checked only by end-to-end tests that invoked the
whole graph against a real provider (``tests/unit/test_router_state.py``), so
in practice it was never checked at all: every one of them was skipped for want
of an API key. The invariant is a property of ONE node's return value, and that
is testable here, hermetically, in milliseconds.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from src.domains.agents.analysis.query_intelligence import QueryIntelligence, UserGoal
from src.domains.agents.constants import (
    STATE_KEY_MESSAGES,
    STATE_KEY_ROUTING_HISTORY,
)
from src.domains.agents.nodes.draft_sequence import draft_turn_reset
from src.domains.agents.nodes.router_node_v3 import get_router_v3_edge, router_node_v3
from src.domains.agents.utils.react_budget import react_turn_reset

pytestmark = pytest.mark.unit


def _intelligence(**overrides: Any) -> QueryIntelligence:
    """A REAL QueryIntelligence — the router serializes it into the state.

    A duck-typed stand-in silently omits `to_serializable_dict()`, which the
    router calls to persist the analysis; using the production dataclass keeps
    that contract honest (and the state round-trip representative).
    """
    base: dict[str, Any] = {
        "original_query": "cherche jean",
        "english_query": "find jean",
        "immediate_intent": "search",
        "immediate_confidence": 0.9,
        "user_goal": next(iter(UserGoal)),
        "goal_reasoning": "the user is looking for a contact",
        "domains": ["contact"],
        "primary_domain": "contact",
        "turn_type": "ACTION",
        "route_to": "planner",
        "confidence": 0.9,
        "reasoning_trace": ["domain=contact", "intent=search", "route=planner"],
    }
    base.update(overrides)
    return QueryIntelligence(**base)


@pytest.fixture
def analyzer() -> MagicMock:
    """Stub QueryAnalyzerService — the router's only collaborator."""
    service = MagicMock()
    service.analyze_full = AsyncMock(return_value=_intelligence())
    return service


@pytest.fixture(autouse=True)
def patched_analyzer(analyzer: MagicMock):
    """Route every `get_query_analyzer_service()` call to the stub.

    The router imports it lazily inside the coroutine, so the source module is
    the correct patch target.
    """
    with patch(
        "src.domains.agents.services.query_analyzer_service.get_query_analyzer_service",
        return_value=analyzer,
    ):
        yield analyzer


def _state(*messages: Any) -> dict[str, Any]:
    """Minimal state: the router only reads the message list."""
    return {STATE_KEY_MESSAGES: list(messages)}


def _config() -> dict[str, Any]:
    return {"configurable": {}, "metadata": {"run_id": "run-test"}}


class TestRouterDoesNotTouchMessages:
    """The core invariant."""

    async def test_state_update_carries_no_messages_key(self) -> None:
        """A `messages` key here would be MERGED into the conversation."""
        update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        assert STATE_KEY_MESSAGES not in update, (
            "the router returned a messages update — its routing decision would "
            "be appended to the user's chat"
        )

    async def test_decision_lands_in_routing_history(self) -> None:
        """Where it does belong: an append-only decision log."""
        update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        history = update[STATE_KEY_ROUTING_HISTORY]
        assert len(history) == 1
        decision = history[0]
        assert decision.intention == "action"
        assert decision.next_node == "planner"
        assert decision.context_label == "contact"
        assert decision.domains == ["contact"]

    async def test_history_appends_rather_than_replaces(self) -> None:
        """A turn must not erase the previous turns' decisions."""
        previous = MagicMock()
        state = _state(HumanMessage(content="et maintenant ?"))
        state[STATE_KEY_ROUTING_HISTORY] = [previous]

        update = await router_node_v3(state, _config())

        history = update[STATE_KEY_ROUTING_HISTORY]
        assert len(history) == 2
        assert history[0] is previous

    async def test_no_routing_field_leaks_into_any_message(self) -> None:
        """Belt and braces: the raw JSON keys must appear nowhere in messages.

        This is the shape the end-to-end tests asserted on the final answer;
        asserting it on the node's own output catches the leak at its source.
        """
        original = [HumanMessage(content="cherche jean"), AIMessage(content="D'accord.")]
        update = await router_node_v3(_state(*original), _config())

        emitted = " ".join(
            str(getattr(message, "content", "")) for message in update.get(STATE_KEY_MESSAGES, [])
        )
        for key in ("intention", "confidence", "context_label", "next_node", "reasoning"):
            assert f'"{key}"' not in emitted


class TestRouterClearsPerTurnState:
    """Stale per-turn values are how a previous turn's verdict leaks forward."""

    @pytest.mark.parametrize(
        "key,expected",
        [
            ("plan_approved", None),
            ("plan_rejection_reason", None),
            ("validation_result", None),
            ("semantic_validation", None),
            ("planner_iteration", 0),
            ("clarification_response", None),
            ("clarification_field", None),
            ("needs_replan", False),
            ("initiative_iteration", 0),
            ("initiative_results", []),
            # A plan, its steps and the planner's verdict: kept, a later turn
            # restated the plan's failures and was judged on its verdict.
            ("execution_plan", None),
            ("completed_steps", {}),
            ("planning_result", None),
        ],
    )
    async def test_per_turn_key_is_reset(self, key: str, expected: Any) -> None:
        state = _state(HumanMessage(content="cherche jean"))
        state.update(
            {
                "plan_approved": True,
                "plan_rejection_reason": "stale reason",
                "validation_result": {"stale": True},
                "semantic_validation": {"stale": True},
                "planner_iteration": 3,
                "clarification_response": "the previous turn's answer",
                "clarification_field": "subject",
                "needs_replan": True,
                "initiative_iteration": 2,
                "initiative_results": [{"stale": True}],
                "execution_plan": {"stale": True},
                "completed_steps": {"step_1": {"success": False}},
                "planning_result": {"success": False},
            }
        )

        update = await router_node_v3(state, _config())

        assert update[key] == expected


class TestRouterResetsTheReactTurn:
    """The ReAct counters restart from the ONE declaration, never from a list.

    Measured on production, 2026-09-11: ``react_tool_seconds`` was missing from
    the hand-maintained reset above, so the checkpoint carried six days of tool
    time (913.8 s) into every new turn and each one died at iteration 1 with its
    tool calls abandoned. The cases below are DERIVED from the declaration: a
    counter added there is tested here without anyone editing this file.
    """

    @pytest.mark.parametrize("key,expected", sorted(react_turn_reset().items()))
    async def test_every_declared_counter_restarts(self, key: str, expected: Any) -> None:
        stale = {
            "react_iteration": 7,
            "react_elapsed_seconds": 240.0,
            "react_tool_seconds": 913.79,
            "react_productive_iterations": 40,
            "react_call_digests": {"digest": 3},
            "react_read_results": {"digest": {"content": "old", "expires_at": 1.0}},
            "react_read_observations": {"digest": {"tool_name": "old", "outcome": "failed"}},
            "react_last_productive_message_id": "previous-generation",
            "requested_outcome_evidence": [{"tool_name": "old", "success": True}],
            "semantic_value_bindings": [{"source_ref": "previous-turn"}],
            "semantic_source_observations": {"previous-turn": {"value": "old"}},
            "semantic_source_valid_after": "2026-10-05T10:00:00+00:00",
            "react_scripts": [{"purpose": "last turn's script", "code": "print(1)"}],
            # ADR-310: a pass of the previous turn would forbid this turn's own.
            "react_recovery_passes": [{"anchor_id": "t9", "draft": "old", "unresolved": ["A"]}],
            # ADR-275: a cut output of the previous turn would end this one at once.
            "react_output_truncated": True,
            # ADR-327: a skill the previous turn activated would skip this turn's runner.
            "react_activated_skills": ["skill-generator"],
            # ADR-385: a note of the previous turn would be shown again in this one.
            "react_turn_notes": [
                {
                    "id": "n9",
                    "text": "old",
                    "written_at": "2026-11-13T17:42:00+00:00",
                    "anchor_id": "t9",
                    "passes_before": 0,
                }
            ],
        }
        state = _state(HumanMessage(content="cherche jean"))
        state.update(stale)
        assert state[key] != expected, "precondition: the stale value differs from the reset"

        update = await router_node_v3(state, _config())

        assert update[key] == expected

    async def test_an_exhausted_tool_budget_does_not_survive_the_turn_start(self) -> None:
        """The incident, on the node: the value that killed three attempts."""
        from src.core.config import settings
        from src.domains.agents.utils.react_budget import react_exit_reason

        state = _state(HumanMessage(content="rappelle-moi samedi"))
        state["react_tool_seconds"] = float(settings.react_tool_budget_seconds) + 13.79
        state["react_iteration"] = 1

        update = await router_node_v3(state, _config())

        assert react_exit_reason({**state, **update}) is None


class TestRouterEdge:
    """The edge reads the decision the node just wrote."""

    def test_edge_follows_the_last_decision(self) -> None:
        decision = MagicMock(next_node="planner")
        assert get_router_v3_edge({STATE_KEY_ROUTING_HISTORY: [decision]}) == "planner"

    def test_edge_defaults_to_response_without_history(self) -> None:
        """Fail-safe: answer the user rather than route nowhere."""
        assert get_router_v3_edge({}) == "response"
        assert get_router_v3_edge({STATE_KEY_ROUTING_HISTORY: []}) == "response"

    def test_edge_defaults_to_response_on_a_decision_without_next_node(self) -> None:
        assert get_router_v3_edge({STATE_KEY_ROUTING_HISTORY: [object()]}) == "response"


class TestRouterQueryExtraction:
    """What the router hands to the analyzer."""

    async def test_last_human_message_is_the_query(self, patched_analyzer: MagicMock) -> None:
        await router_node_v3(
            _state(
                HumanMessage(content="première demande"),
                AIMessage(content="réponse"),
                HumanMessage(content="deuxième demande"),
            ),
            _config(),
        )

        assert "deuxième demande" in str(patched_analyzer.analyze_full.await_args)

    async def test_empty_message_list_does_not_raise(self) -> None:
        """A turn with no message must not crash the graph's entry node."""
        update = await router_node_v3(_state(), _config())

        assert STATE_KEY_ROUTING_HISTORY in update


class TestRouterResetsTheDraftReview:
    """A new human message means the previous review was abandoned (ADR-288).

    The interrupt record expires after an hour; the checkpoint does not. A
    draft still pending there was re-presented by the next actionable turn,
    and the decisions banked along an abandoned sequence would have been
    executed by a later one. What a turn starts with is ONE declaration,
    spread here like the ReAct counters.
    """

    @pytest.mark.parametrize("key,expected", sorted(draft_turn_reset().items()))
    async def test_every_draft_key_restarts(self, key: str, expected: Any) -> None:
        state = _state(HumanMessage(content="cherche jean"))
        stale: dict[str, Any] = {
            "pending_draft_critique": {"draft_id": "stale"},
            "pending_drafts_queue": [{"draft_id": "stale-2"}],
            "pending_drafts_grouped": True,
            "confirmed_drafts": [{"draft_id": "stale", "action": "confirm"}],
            "draft_action_result": {"action": "confirm"},
            "draft_edit_iteration": 3,
            "draft_clarification_question": "stale?",
            "held_plan": {"plan_id": "stale", "held": {"s2": ["stale"]}},
            "executed_drafts": {"stale": {"status": "success"}},
        }
        assert key in stale, f"{key} needs a stale value in this test"
        state.update(stale)

        update = await router_node_v3(state, _config())

        assert update[key] == expected


class TestRouterPublishesTheExchangeRhythm:
    """The rhythm is read ONCE per turn, by the router, and the loop reads the state (ADR-311).

    A HITL resumption re-enters the interrupted node, never the router, so the
    turn keeps the rhythm it started with even if the person changes it meanwhile:
    the tools bound at setup and the layout of every later call cannot disagree.
    """

    @pytest.fixture(autouse=True)
    def _no_response_prefetch(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """The router's response-context prefetch is not under test.

        With a person in the run context, it would start a background task that
        embeds the message with the provider and opens database sessions, which
        nothing in this test awaits.
        """
        prefetch = MagicMock()
        monkeypatch.setattr(
            "src.domains.agents.services.response_context.start_response_context_prefetch",
            prefetch,
        )
        return prefetch

    @pytest.mark.parametrize("rhythm", ["frequent", "occasional"])
    async def test_the_run_s_rhythm_lands_in_the_state(self, rhythm: str) -> None:
        from src.core.exchange_rhythm import ExchangeRhythm
        from tests.helpers.runtime_context import installed_runtime_context

        state = _state(HumanMessage(content="cherche jean"))
        state["exchange_rhythm"] = "stale value of the previous turn"

        with installed_runtime_context(exchange_rhythm=ExchangeRhythm(rhythm)):
            update = await router_node_v3(state, _config())

        assert update["exchange_rhythm"] == rhythm

    def test_it_is_a_declared_state_key(self) -> None:
        """An undeclared key is silently dropped by LangGraph (CLAUDE.md, State Management)."""
        from src.domains.agents.models import MessagesState

        assert "exchange_rhythm" in MessagesState.__annotations__


class TestTheRouterSettlesTheEngine:
    """An actionable turn leaves the router with ONE engine, in the state and on the
    context's holder: the routing edge reads the first, every tool, register and
    metric label the second (``executed_mode_of``)."""

    @pytest.fixture(autouse=True)
    def _no_response_prefetch(self, monkeypatch: pytest.MonkeyPatch) -> MagicMock:
        """Same reason as for the rhythm: a background prefetch nothing awaits."""
        prefetch = MagicMock()
        monkeypatch.setattr(
            "src.domains.agents.services.response_context.start_response_context_prefetch",
            prefetch,
        )
        return prefetch

    @pytest.mark.parametrize("requested", ["pipeline", "react"])
    async def test_an_actionable_turn_settles_the_requested_engine(self, requested: str) -> None:
        from tests.helpers.runtime_context import installed_runtime_context

        state = _state(HumanMessage(content="cherche jean"))
        state["execution_mode"] = "stale value of the previous turn"

        with installed_runtime_context(requested_execution_mode=requested) as context:
            update = await router_node_v3(state, _config())

        assert update["execution_mode"] == requested
        assert context.turn_engine.executed == requested

    async def test_the_loop_switched_off_settles_the_planner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What runs is what the registers file: the edge already plans such a turn in
        the pipeline (``graph._planning_node``), and the record said « react »."""
        from src.core.config import settings
        from tests.helpers.runtime_context import installed_runtime_context

        monkeypatch.setattr(settings, "react_agent_enabled", False)

        with installed_runtime_context(requested_execution_mode="react") as context:
            update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        assert update["execution_mode"] == "pipeline"
        assert context.turn_engine.executed == "pipeline"

    async def test_a_turn_already_settled_publishes_its_engine(self) -> None:
        """A router meeting a turn that already runs (a resumed one, a compacted
        replay) publishes the engine in force, never the request it reads now:
        the edge and the registers must keep agreeing."""
        from tests.helpers.runtime_context import installed_runtime_context

        with installed_runtime_context(requested_execution_mode="pipeline") as context:
            context.turn_engine.settle("react")
            update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        assert update["execution_mode"] == "react"
        assert context.turn_engine.executed == "react"

    @pytest.mark.parametrize(
        ("verdict", "engine"),
        [("direct", "pipeline"), ("computed", "react"), ("no_decision", "react")],
    )
    async def test_auto_plans_where_the_judged_shape_says(
        self, monkeypatch: pytest.MonkeyPatch, verdict: str, engine: str
    ) -> None:
        """ADR-390: the pipeline only for a shape judged direct; every doubt loops."""
        from src.domains.agents.services.engine_resolution import EngineReason
        from tests.helpers.runtime_context import installed_runtime_context

        judged = AsyncMock(return_value=EngineReason(verdict))
        monkeypatch.setattr("src.domains.agents.nodes.router_node_v3.judge_request_shape", judged)

        with installed_runtime_context(requested_execution_mode="auto") as context:
            update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        assert update["execution_mode"] == engine
        assert context.turn_engine.executed == engine
        judged.assert_awaited_once_with("cherche jean")

    @staticmethod
    def _judgement_that_never_answers(monkeypatch: pytest.MonkeyPatch) -> asyncio.Event:
        """Install a judgement that waits forever; the event says it was cancelled."""
        cancelled = asyncio.Event()

        async def pending(_request: str) -> None:
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.set()
                raise

        monkeypatch.setattr("src.domains.agents.nodes.router_node_v3.judge_request_shape", pending)
        return cancelled

    @staticmethod
    def _analysis_taking_a_beat(analyzer: MagicMock, **fields: Any) -> None:
        """The analysis yields once, as the real one does for seconds."""

        async def analyze(*_args: Any, **_kwargs: Any) -> QueryIntelligence:
            await asyncio.sleep(0)
            return _intelligence(**fields)

        analyzer.analyze_full = AsyncMock(side_effect=analyze)

    @staticmethod
    def _judgements_still_running() -> list[asyncio.Task[Any]]:
        return [
            task
            for task in asyncio.all_tasks()
            if task.get_name() == "execution_mode_shape" and not task.done()
        ]

    async def test_a_shape_the_analysis_reads_never_waits_for_the_judgement(
        self, analyzer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An act loops whatever the provider says: its judgement is cancelled and
        AWAITED, never left running beside the turn."""
        from tests.helpers.runtime_context import installed_runtime_context

        cancelled = self._judgement_that_never_answers(monkeypatch)
        self._analysis_taking_a_beat(analyzer, is_mutation_intent=True)

        with installed_runtime_context(requested_execution_mode="auto") as context:
            update = await router_node_v3(_state(HumanMessage(content="supprime jean")), _config())

        assert update["execution_mode"] == "react"
        assert context.turn_engine.executed == "react"
        assert cancelled.is_set()
        assert self._judgements_still_running() == []

    async def test_a_conversation_abandons_the_judgement(
        self, analyzer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """No engine plans a conversation: the state says what was asked."""
        from tests.helpers.runtime_context import installed_runtime_context

        cancelled = self._judgement_that_never_answers(monkeypatch)
        self._analysis_taking_a_beat(analyzer, route_to="response")

        with installed_runtime_context(requested_execution_mode="auto") as context:
            update = await router_node_v3(_state(HumanMessage(content="merci")), _config())

        assert update["execution_mode"] == "auto"
        assert context.turn_engine.executed is None
        assert cancelled.is_set()
        assert self._judgements_still_running() == []

    async def test_a_failed_analysis_never_leaves_the_judgement_behind(
        self, analyzer: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.helpers.runtime_context import installed_runtime_context

        cancelled = self._judgement_that_never_answers(monkeypatch)

        async def failing(*_args: Any, **_kwargs: Any) -> QueryIntelligence:
            await asyncio.sleep(0)
            raise RuntimeError("analysis down")

        analyzer.analyze_full = AsyncMock(side_effect=failing)

        with (
            installed_runtime_context(requested_execution_mode="auto"),
            pytest.raises(RuntimeError),
        ):
            await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        assert cancelled.is_set()
        assert self._judgements_still_running() == []

    @pytest.mark.parametrize(
        ("requested", "loop_on"), [("pipeline", True), ("react", True), ("auto", False)]
    )
    async def test_nothing_is_judged_when_no_choice_is_left(
        self, monkeypatch: pytest.MonkeyPatch, requested: str, loop_on: bool
    ) -> None:
        """An explicit engine, or « auto » on an instance without the loop: the
        provider is never billed for a judgement nothing would read."""
        from src.core.config import settings
        from tests.helpers.runtime_context import installed_runtime_context

        judged = AsyncMock()
        monkeypatch.setattr("src.domains.agents.nodes.router_node_v3.judge_request_shape", judged)
        monkeypatch.setattr(settings, "react_agent_enabled", loop_on)

        with installed_runtime_context(requested_execution_mode=requested):
            update = await router_node_v3(_state(HumanMessage(content="cherche jean")), _config())

        judged.assert_not_called()
        assert update["execution_mode"] == (requested if loop_on else "pipeline")

    async def test_the_engine_and_its_reason_reach_the_turn_s_record(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from src.domains.agents.effects.decisions import publish_turn, reset_turn, turn_decision
        from src.domains.agents.services.engine_resolution import EngineReason
        from tests.helpers.runtime_context import installed_runtime_context

        monkeypatch.setattr(
            "src.domains.agents.nodes.router_node_v3.judge_request_shape",
            AsyncMock(return_value=EngineReason.OPEN_ENDED),
        )
        record = turn_decision(
            run_id="run-test", user_id=None, thread_id="t", execution_mode="auto", automated=False
        )
        token = publish_turn(record)
        try:
            with installed_runtime_context(requested_execution_mode="auto"):
                await router_node_v3(_state(HumanMessage(content="organise ma semaine")), _config())
        finally:
            reset_turn(token)

        assert (record.execution_mode, record.requested_mode, record.resolution_reason) == (
            "react",
            "auto",
            "open_ended",
        )

    async def test_a_conversation_turn_settles_no_engine(self, analyzer: MagicMock) -> None:
        """No engine plans a conversation: the state keeps what was asked."""
        from tests.helpers.runtime_context import installed_runtime_context

        analyzer.analyze_full = AsyncMock(return_value=_intelligence(route_to="response"))

        with installed_runtime_context(requested_execution_mode="react") as context:
            update = await router_node_v3(_state(HumanMessage(content="merci")), _config())

        assert update["execution_mode"] == "react"
        assert context.turn_engine.executed is None
