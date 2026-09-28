"""A model output cut at its budget never enters the thread (ADR-275, amended).

Measured on production, 2026-09-25 → 26. The third ReAct call of a relayed
phone call ran to its output budget: 20 000 tokens, 71 822 characters, no tool
call. The loop took that text for the answer, and the thread kept it — ONE
thread per account, shared by the chat, the voice relays and every routine. The
model then copied it into later calls: the next morning, seven routines out of
seven stopped after one iteration, ran no tool and sent no e-mail, and two
different instructions came back with exactly 73 193 characters. Every register
said « success ». It ended when the owner reset the conversation by hand.

The rule has three halves, one per class below:

- a cut output is neither an answer nor a plan: it never reaches ``messages``;
- the ONE stop predicate ends the loop on it, and the router obeys;
- the finalize node says so, and the answer is synthesised from what the tools
  DID return (ADR-248 invariant 1's path) — a recovery draft is handed back.

The last class replays the incident on the real nodes, router and reducer.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from prometheus_client import REGISTRY

from src.core.turn_verdicts import verdict_collector
from src.domains.agents.constants import NODE_REACT_FINALIZE
from src.domains.agents.models import (
    MessagesState,
    add_messages_with_truncate,
    create_initial_state,
)
from src.domains.agents.nodes import react_nodes as rn
from src.domains.agents.nodes.react_output_guard import model_call_update
from src.domains.agents.nodes.routing import route_from_react_call_model
from src.domains.agents.utils.react_budget import react_exit_reason, react_turn_reset

pytestmark = [pytest.mark.unit]

#: What the incident's cut messages looked like: text running to the budget.
DEGENERATE = "Voici la synthèse du rapport. " * 400
_COUNTER = "react_output_truncated_total"


def _cut(content: str = DEGENERATE, **extra: Any) -> AIMessage:
    return AIMessage(content=content, response_metadata={"finish_reason": "length"}, **extra)


def _counted() -> float:
    return REGISTRY.get_sample_value(_COUNTER) or 0.0


def _loop_state(
    *messages: BaseMessage,
    truncated: bool = False,
    iteration: int = 2,
    budget: int = 70,
    passes: list[dict[str, Any]] | None = None,
) -> MessagesState:
    """A real ``MessagesState``, built by the production constructor."""
    state = create_initial_state(uuid.uuid4(), session_id="s", run_id="r")
    state["messages"] = list(messages)
    state["react_iteration"] = iteration
    state["react_max_iterations_effective"] = budget
    state["react_elapsed_seconds"] = 3.0
    state["react_output_truncated"] = truncated
    state["react_recovery_passes"] = passes or []
    return state


class TestACutOutputNeverEntersTheThread:
    def test_the_cut_text_is_not_written_to_the_messages(self) -> None:
        update = model_call_update(_cut(), iteration=0, elapsed_seconds=1.5)

        assert "messages" not in update, (
            "whatever a node writes to `messages` is checkpointed with the thread "
            "and replayed to every later call of the account — the contagion channel"
        )
        assert update["react_output_truncated"] is True
        assert update["react_iteration"] == 1, "the call happened and was billed"
        assert update["react_elapsed_seconds"] == 1.5

    def test_tool_calls_carried_by_a_cut_output_plan_nothing(self) -> None:
        """The budget stopped the model mid-plan: running part of a plan it could
        not finish would act on a decision it never completed (ADR-275: a cut is
        a refusal, never a rescue)."""
        cut = _cut(
            "",
            tool_calls=[{"id": "c1", "name": "send_email_to_me_tool", "args": {"subject": "x"}}],
        )

        update = model_call_update(cut, iteration=3, elapsed_seconds=9.0)

        assert "messages" not in update
        assert update["react_output_truncated"] is True

    def test_a_complete_output_is_written_exactly_as_before(self) -> None:
        answer = AIMessage(
            content="Sunny, 21 degrees.", response_metadata={"finish_reason": "stop"}
        )

        update = model_call_update(answer, iteration=2, elapsed_seconds=4.0)

        assert update == {
            "messages": [answer],
            "react_iteration": 3,
            "react_elapsed_seconds": 4.0,
        }

    async def test_the_cut_is_counted_and_shown_on_the_turn_panel(self) -> None:
        before = _counted()

        async with verdict_collector() as verdicts:
            model_call_update(_cut(), iteration=0, elapsed_seconds=0.1)

        assert _counted() == before + 1
        assert [(v.kind, v.detail) for v in verdicts] == [("output_truncated", "react_agent")]


class TestTheLoopStopsOnIt:
    def test_the_predicate_names_the_cut(self) -> None:
        assert react_exit_reason(_loop_state(HumanMessage("q"), truncated=True)) == (
            "output_truncated"
        )

    def test_the_cut_is_named_even_when_a_budget_ran_out_on_the_same_call(self) -> None:
        """Both are true; only one explains an answer with nothing in it."""
        state = _loop_state(HumanMessage("q"), truncated=True, iteration=70, budget=70)

        assert react_exit_reason(state) == "output_truncated"

    def test_a_turn_that_was_not_cut_is_judged_as_before(self) -> None:
        assert react_exit_reason(_loop_state(HumanMessage("q"))) is None

    def test_the_router_finalizes_and_tells_the_register_why(self) -> None:
        """Even behind a message that still carries calls: the cut decides."""
        stale_plan = AIMessage("", tool_calls=[{"id": "c1", "name": "t", "args": {}}])
        state = _loop_state(HumanMessage("q"), stale_plan, truncated=True)

        with patch("src.domains.agents.nodes.routing.note_stop_reason") as noted:
            decision = route_from_react_call_model(state)

        assert decision == NODE_REACT_FINALIZE
        noted.assert_called_once_with("output_truncated")


class TestTheFinalizeSaysSo:
    async def test_the_answer_comes_from_the_tools_and_names_the_cut(self) -> None:
        state = _loop_state(
            HumanMessage("q", id="h1"),
            AIMessage("", id="a1", tool_calls=[{"id": "c1", "name": "search", "args": {}}]),
            ToolMessage(content="3 results", tool_call_id="c1", id="t1"),
            truncated=True,
        )

        result = await rn.react_finalize_node(state, {})

        react_result = result["react_agent_result"]
        assert react_result["final_message"] == "", (
            "an empty final message makes the response node synthesise from the "
            "tool results that came back — the path ADR-248 invariant 1 opened"
        )
        assert react_result["truncation"] == {"reason": "output_truncated", "iterations": 2}
        assert "abandoned_calls" not in react_result, "every call of the turn was answered"
        assert "messages" not in result

    async def test_a_recovery_draft_is_handed_back_rather_than_traded_for_nothing(self) -> None:
        """ADR-310: the draft left the thread AT the pass; a pass whose call was cut
        has no answer of its own, so the complete draft the turn had stands."""
        state = _loop_state(
            HumanMessage("q", id="h1"),
            truncated=True,
            passes=[{"anchor_id": "h1", "draft": "Draft answer.", "unresolved": ["the forecast"]}],
        )

        result = await rn.react_finalize_node(state, {})

        react_result = result["react_agent_result"]
        assert react_result["final_message"] == "Draft answer."
        assert react_result["recovery"] == {"passes": 1, "outcome": "cut"}

    async def test_a_complete_answer_given_as_the_budget_runs_out_is_not_called_cut(self) -> None:
        """No regression: reaching the iteration budget ON a final answer is a
        finished turn — reporting the budget there would call it interrupted."""
        state = _loop_state(
            HumanMessage("q", id="h1"),
            AIMessage("Your stopover lasts 3 h 40.", id="f1"),
            iteration=6,
            budget=6,
        )

        result = await rn.react_finalize_node(state, {})

        assert result["react_agent_result"]["final_message"] == "Your stopover lasts 3 h 40."
        assert "truncation" not in result["react_agent_result"]


# ---------------------------------------------------------------------------
# The incident, replayed: real nodes, real router, real reducer, scripted model.
# ---------------------------------------------------------------------------


def _apply_model_call(state: MessagesState, update: Mapping[str, Any]) -> None:
    """Merge what ``model_call_update`` returns, the way the graph does: the
    ``messages`` channel through its reducer, and only when it is written."""
    if "messages" in update:
        state["messages"] = add_messages_with_truncate(state["messages"], update["messages"])
    state["react_iteration"] = update["react_iteration"]
    state["react_elapsed_seconds"] = update["react_elapsed_seconds"]
    if "react_output_truncated" in update:
        state["react_output_truncated"] = update["react_output_truncated"]


@pytest.fixture
def model(monkeypatch: pytest.MonkeyPatch) -> dict[str, list[Any]]:
    """A scripted model: each call pops the next reply and records what it was sent."""
    script: dict[str, list[Any]] = {"replies": [], "sent": []}
    monkeypatch.setattr(rn, "get_llm", lambda *_a, **_k: MagicMock())
    monkeypatch.setattr(rn, "_rebuild_wrapped_tools", lambda *_a, **_k: [])

    async def fake_stream(
        _llm: object, messages: list[BaseMessage], emit: object, config: object
    ) -> AIMessage:
        script["sent"].append(list(messages))
        reply: AIMessage = script["replies"].pop(0)
        return reply

    monkeypatch.setattr(
        "src.infrastructure.llm.reasoning_stream.stream_reasoning_events", fake_stream
    )
    return script


def _turn_start(state: MessagesState, question: HumanMessage) -> None:
    """What the router does at a new turn: reset the loop, append the question."""
    state.update(react_turn_reset())
    state["react_max_iterations_effective"] = 70
    state["messages"] = add_messages_with_truncate(state["messages"], [question])


def _texts(messages: list[BaseMessage]) -> str:
    return "\n".join(str(message.content) for message in messages)


class TestTheIncidentReplayed:
    async def test_one_cut_output_no_longer_contaminates_the_turns_that_follow(
        self, model: dict[str, list[Any]]
    ) -> None:
        state = create_initial_state(uuid.uuid4(), session_id="s", run_id="r")
        state["react_system_blocks"] = ["You are LIA."]

        # 25/09 20:29 — the relayed call's model output runs to its budget.
        _turn_start(state, HumanMessage("Find a restaurant near the station.", id="h1"))
        model["replies"] = [_cut(id="cut-1")]
        _apply_model_call(state, await rn.react_call_model_node(state, config={}))

        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
        assert DEGENERATE.strip() not in _texts(state["messages"])
        finalized = await rn.react_finalize_node(state, {})
        assert finalized["react_agent_result"]["final_message"] == ""
        assert finalized["react_agent_result"]["truncation"]["reason"] == "output_truncated"

        # 26/09 05:00 — the next turn of the same thread: a morning routine.
        _turn_start(state, HumanMessage("Summarise today's operations report.", id="h2"))
        assert react_exit_reason(state) is None, "the previous turn's cut does not end this one"
        model["replies"] = [AIMessage("Report summarised.", id="ok-2")]
        _apply_model_call(state, await rn.react_call_model_node(state, config={}))

        sent_to_the_model = _texts(model["sent"][-1])
        assert DEGENERATE.strip() not in sent_to_the_model, (
            "the model of the next turn must never be shown the cut text: that is "
            "what it copied, verbatim, into seven routines"
        )
        assert route_from_react_call_model(state) == NODE_REACT_FINALIZE
        answered = await rn.react_finalize_node(state, {})
        assert answered["react_agent_result"]["final_message"] == "Report summarised."
        assert "truncation" not in answered["react_agent_result"]
