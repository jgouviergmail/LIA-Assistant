"""Once the person answered, a plan with waiting steps goes back to the orchestrator (spec D7).

The FOR_EACH confirmation already comes back this way (``route_from_for_each_confirm``):
the confirmation decides, the orchestrator resumes. A turn whose drafts nobody
waits on keeps its historical route to the initiative and the response.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from src.domains.agents.constants import NODE_DRAFT_CRITIQUE, NODE_TASK_ORCHESTRATOR
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes.hitl_dispatch_node import hitl_dispatch_node
from src.domains.agents.nodes.routing import route_from_hitl_dispatch
from src.domains.agents.orchestration.parallel_executor import PendingDraftInfo

pytestmark = [pytest.mark.unit]

_HELD = {"plan_id": "p", "held": {"s2": ["draft-1"]}, "pending": {"s1": ["draft-1"]}}


def _draft() -> dict[str, Any]:
    return PendingDraftInfo(
        draft_id="draft-1",
        draft_type="email",
        draft_content={"to": "a@x", "subject": "s", "body": "hello"},
        draft_summary="",
        registry_ids=[],
        tool_name="send_email_tool",
        step_id="s1",
    ).model_dump()


class TestTheRoute:
    def test_a_draft_on_screen_keeps_the_dispatch(self) -> None:
        state: Any = {"pending_draft_critique": _draft(), "held_plan": _HELD}

        assert route_from_hitl_dispatch(state) == NODE_DRAFT_CRITIQUE

    def test_a_settled_sequence_with_waiting_steps_resumes_the_plan(self) -> None:
        state: Any = {"draft_action_result": {"action": "confirm"}, "held_plan": _HELD}

        assert route_from_hitl_dispatch(state) == NODE_TASK_ORCHESTRATOR

    def test_waiting_steps_without_an_answer_never_re_enter_the_orchestrator(self) -> None:
        """Entered with no decision, the orchestrator would run the whole plan again."""
        state: Any = {"tool_confirmation_result": {"action": "confirm"}, "held_plan": _HELD}

        assert route_from_hitl_dispatch(state) == "initiative"

    def test_work_done_beside_the_acts_brings_the_answer_back_to_the_plan(self) -> None:
        """Spec D5 (2026-10-30): the answer must tell it, beside the act's account."""
        held_plan = {"plan_id": "p", "held": {}, "told": ["s1"], "resumed": [], "not_run": {}}
        state: Any = {"draft_action_result": {"action": "cancel"}, "held_plan": held_plan}

        assert route_from_hitl_dispatch(state) == NODE_TASK_ORCHESTRATOR

    @pytest.mark.parametrize(
        "held_plan",
        [
            None,
            {"plan_id": "p", "held": {}, "resumed": ["s2"], "not_run": {}},
            {"plan_id": "p", "held": {}, "told": [], "resumed": [], "not_run": {}},
        ],
    )
    def test_nothing_waiting_keeps_the_historical_route(self, held_plan: Any) -> None:
        state: Any = {"draft_action_result": {"action": "confirm"}, "held_plan": held_plan}

        assert route_from_hitl_dispatch(state) == "initiative"


class TestThroughTheRealDispatch:
    async def test_the_confirmation_lands_in_the_orchestrator_with_its_decision(self) -> None:
        reached: list[dict[str, Any]] = []

        def _orchestrator(state: MessagesState) -> dict[str, Any]:
            reached.append(
                {
                    "decision": (state.get("draft_action_result") or {}).get("action"),
                    "held": (state.get("held_plan") or {}).get("held"),
                }
            )
            return {}

        graph = StateGraph(MessagesState)
        graph.add_node(NODE_DRAFT_CRITIQUE, hitl_dispatch_node)
        graph.add_node(NODE_TASK_ORCHESTRATOR, _orchestrator)
        graph.add_node("initiative", lambda state: {})
        graph.add_edge(START, NODE_DRAFT_CRITIQUE)
        graph.add_conditional_edges(
            NODE_DRAFT_CRITIQUE,
            route_from_hitl_dispatch,
            {
                NODE_DRAFT_CRITIQUE: NODE_DRAFT_CRITIQUE,
                NODE_TASK_ORCHESTRATOR: NODE_TASK_ORCHESTRATOR,
                "initiative": "initiative",
            },
        )
        graph.add_edge(NODE_TASK_ORCHESTRATOR, END)
        graph.add_edge("initiative", END)
        compiled = graph.compile(checkpointer=InMemorySaver())
        config: RunnableConfig = {"configurable": {"thread_id": "t-back-to-plan"}}

        # The production builder: the graph is handed a whole state, as the stream does.
        state = create_initial_state(
            uuid.uuid4(), "s-back-to-plan", "r-back-to-plan", user_language="fr"
        )
        state["pending_draft_critique"] = _draft()
        state["held_plan"] = _HELD
        await compiled.ainvoke(state, config)
        await compiled.ainvoke(Command(resume={"action": "confirm"}), config)

        assert reached == [{"decision": "confirm", "held": {"s2": ["draft-1"]}}]
