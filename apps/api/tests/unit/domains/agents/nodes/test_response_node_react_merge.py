"""Regression test: the ReAct answer must survive when Initiative also wrote
agent_results (ADR-070).

On the ReAct nominal path (react_finalize -> initiative -> response) the Initiative
node writes ``{turn}:initiative`` into agent_results *before* response_node runs. The
previous ``if not agent_results`` guard would then skip injecting the ReAct answer,
silently dropping the user-facing reply. ``merge_react_synthesis_result`` merges the
ReAct entry without overwriting the Initiative entry.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.runnables import RunnableLambda

from src.core.field_names import FIELD_TOOL_DATA
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes.response_node import (
    _apply_react_passthrough,
    _build_response_chain,
)
from src.domains.agents.orchestration.tool_data_projection import merge_react_synthesis_result


@pytest.mark.unit
class TestMergeReactSynthesisResult:
    def test_injects_react_entry_into_empty_results(self) -> None:
        merged = merge_react_synthesis_result(None, "the answer", 4, {"item_1": object()})
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "the answer"

    def test_preserves_initiative_entry_and_adds_react(self) -> None:
        existing: dict[str, Any] = {"4:initiative": {"status": "success", "data": {"x": 1}}}
        merged = merge_react_synthesis_result(existing, "the answer", 4, {})
        assert "4:initiative" in merged  # not dropped
        assert "4:react_agent" in merged  # added
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "the answer"

    def test_idempotent_on_react_key(self) -> None:
        existing: dict[str, Any] = {"4:react_agent": {"data": {"react_synthesis": "first"}}}
        merged = merge_react_synthesis_result(existing, "second", 4, {})
        assert merged["4:react_agent"]["data"]["react_synthesis"] == "first"

    def test_does_not_mutate_input(self) -> None:
        existing: dict[str, Any] = {"4:initiative": {"status": "success"}}
        merge_react_synthesis_result(existing, "answer", 4, {})
        assert "4:react_agent" not in existing

    def test_a_long_react_thread_keeps_a_bounded_history(self) -> None:
        """The ReAct write keeps the recent turns only, like the pipeline's writers.

        Unbounded, every ReAct turn's answer and registry items rode every later
        checkpoint: production measured 4.65 MB of a 5.3 MB state in agent_results.
        """
        from src.core.config import settings

        bound = settings.max_agent_results
        current = bound + 6
        existing: dict[str, Any] = {
            f"{turn}:react_agent": {"data": {"react_synthesis": f"turn {turn}"}}
            for turn in range(1, current)
        }
        merged = merge_react_synthesis_result(existing, "now", current, {})
        assert len(merged) <= bound
        assert merged[f"{current}:react_agent"]["data"]["react_synthesis"] == "now"
        assert f"{current - 1}:react_agent" in merged
        assert "1:react_agent" not in merged

    def test_the_bound_never_separates_the_current_turn(self) -> None:
        """The initiative entry of the turn stays beside its ReAct answer."""
        from src.core.config import settings

        bound = settings.max_agent_results
        current = bound + 3
        existing: dict[str, Any] = {
            f"{turn}:react_agent": {"data": {"react_synthesis": f"turn {turn}"}}
            for turn in range(1, current)
        }
        existing[f"{current}:initiative"] = {"status": "success", "data": {}}
        merged = merge_react_synthesis_result(existing, "now", current, {})
        assert len(merged) <= bound
        assert f"{current}:initiative" in merged
        assert f"{current}:react_agent" in merged

    def test_a_bound_smaller_than_the_turn_never_drops_the_answer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An operator's tiny bound trims the history, never the turn's own answer."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "max_agent_results", 1)
        existing: dict[str, Any] = {
            "1:react_agent": {"data": {"react_synthesis": "old"}},
            "2:initiative": {"status": "success", "data": {}},
        }
        merged = merge_react_synthesis_result(existing, "now", 2, {})
        assert merged["2:react_agent"]["data"]["react_synthesis"] == "now"
        assert "2:initiative" in merged
        assert "1:react_agent" not in merged

    def test_another_turn_s_pipeline_data_blocks_leave_the_state(self) -> None:
        """The ReAct turn's write is the one the checkpoint keeps (ADR-347).

        A data block serves its own turn's response alone; an earlier pipeline
        turn's blocks would otherwise ride every later ReAct turn's save.
        """
        record = {"tool": "get_route_matrix_tool", "text": "{}"}

        def entry() -> dict[str, Any]:
            return {"data": {"step_results": [{"result": "ok", FIELD_TOOL_DATA: [record]}]}}

        merged = merge_react_synthesis_result(
            {"3:plan_executor": entry(), "4:initiative": entry()}, "the answer", 4, {}
        )

        assert merged["3:plan_executor"]["data"]["step_results"] == [{"result": "ok"}]
        assert merged["4:initiative"] == entry()


def _react_state(final_message: str) -> MessagesState:
    state = create_initial_state(uuid4(), session_id="s", run_id="r")
    state["react_agent_result"] = {"final_message": final_message, "iteration_count": 2}
    state["current_turn_id"] = 4
    state["current_turn_registry"] = {}
    return state


@pytest.mark.unit
class TestTheAnswerIsMergedAlone:
    """The data block carries the loop's answer, never the acts (ADR-263 §23)."""

    def test_the_answer_is_merged_without_any_act(self) -> None:
        state = _react_state("Voilà : un chat tigré.")

        _result, merged = _apply_react_passthrough(state, "run-1")

        assert merged
        assert state["agent_results"]["4:react_agent"]["data"] == {
            "react_synthesis": "Voilà : un chat tigré."
        }

    def test_an_empty_answer_merges_nothing(self) -> None:
        state = _react_state("")

        _result, merged = _apply_react_passthrough(state, "run-1")

        assert not merged
        assert "4:react_agent" not in (state.get("agent_results") or {})


def _chain_blocks(performed_actions_block: str, *, data: str = "the answer") -> list[BaseMessage]:
    """The messages the response chain would send, rendered by the real template."""
    chain = _build_response_chain(
        base_system_prompt="BASE",
        agent_results_summary=data,
        skills_context="",
        plan_rejection_reason=None,
        state=create_initial_state(uuid4(), session_id="s", run_id="r"),
        user_language="fr",
        llm=RunnableLambda(lambda _prompt: AIMessage(content="stub")),
        performed_actions_block=performed_actions_block,
    )
    messages: list[BaseMessage] = chain.first.format_messages(
        messages=[HumanMessage(content="génère un chat")]
    )
    return messages


@pytest.mark.unit
class TestTheActsHaveTheirOwnBlock:
    """The chain composes the acts directive (built by
    ``services/performed_actions_directive``) as a system block of its own,
    before the data it explains — never as lines of the data (ADR-263 §23)."""

    def test_the_block_sits_between_the_base_prompt_and_the_data(self) -> None:
        blocks = _chain_blocks("ACTIONS YOU PERFORMED THIS TURN")

        assert [type(block).__name__ for block in blocks] == [
            "SystemMessage",
            "SystemMessage",
            "SystemMessage",
            "HumanMessage",
            "HumanMessage",
        ]
        assert blocks[0].content == "BASE"
        assert blocks[1].content == "ACTIONS YOU PERFORMED THIS TURN"
        assert str(blocks[2].content).endswith("the answer")

    def test_a_turn_that_did_nothing_gets_no_block(self) -> None:
        blocks = _chain_blocks("")

        assert len(blocks) == 4

    def test_braces_in_an_act_reach_the_model_literally(self) -> None:
        """An act names what the person asked for, and a request may hold braces."""
        act = r"- Image générée : un chat {x} dans \frac{1}{2}"

        assert str(_chain_blocks(act)[1].content) == act
