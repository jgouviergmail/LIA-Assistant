"""A withheld ReAct answer still hands its turn's data to the response (ADR-336, ADR-248).

Measured 2026-11-15 (ADR-390 qualification, E06, « what day must I return the books
to the library? »): the loop read the reminder that held the day and wrote a correct
answer, and the person was told the day could not be found. The requested-result
coverage withheld the answer — the result sat in the domain the analyzer guessed,
whose only tool had failed — which routes the response to « synthesise from the
actual tool results ». The response received none: the turn's registry and its tool
results reached it only BESIDE a non-empty answer. A budget exit (ADR-248, invariant
1, whose directive says « the tool results already in this context ARE valid — use
them ») took the same path to the same nothing.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from uuid import uuid4

import pytest
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from src.core.context import request_tool_manifests_ctx
from src.domains.agents.data_registry.models import (
    RegistryItem,
    RegistryItemMeta,
    RegistryItemType,
)
from src.domains.agents.emails.catalogue_manifests import send_email_catalogue_manifest
from src.domains.agents.formatters.tool_data import with_tool_data_section
from src.domains.agents.models import MessagesState, create_initial_state
from src.domains.agents.nodes.response_node import _apply_react_passthrough
from src.domains.agents.reminders.catalogue_manifests import list_reminders_catalogue_manifest
from src.domains.agents.tasks.catalogue_manifests import get_tasks_catalogue_manifest
from src.domains.agents.utils.message_filters import TOOL_CALL_NOT_RUN
from src.domains.agents.weather.catalogue_manifests import (
    get_current_weather_catalogue_manifest,
    get_weather_forecast_catalogue_manifest,
)

pytestmark = pytest.mark.unit

TURN = 4
READ_DAY = "Rappel « Rapporter les livres à la médiathèque » : mardi 17 novembre, 10:00"
READ_BY_REGISTRY = "Nantes, mardi 17 novembre : partiellement ensoleillé"
EARLIER_TURN = "a result of the turn before"
FAILED = "No Tasks service is configured"
NOT_RUN = "This call did not run"
ACTED = "The e-mail was sent"


@pytest.fixture(autouse=True)
def _turn_catalogue() -> Iterator[None]:
    """The turn's offered tools, as the stream publishes them (real manifests)."""
    token = request_tool_manifests_ctx.set(
        [
            list_reminders_catalogue_manifest,
            get_tasks_catalogue_manifest,
            send_email_catalogue_manifest,
            get_current_weather_catalogue_manifest,
            get_weather_forecast_catalogue_manifest,
        ]
    )
    yield
    request_tool_manifests_ctx.reset(token)


def _weather_item() -> RegistryItem:
    return RegistryItem(
        id="weather_1",
        type=RegistryItemType.WEATHER,
        payload={"location": "Nantes", "date": "2026-11-17"},
        meta=RegistryItemMeta(source="weather", tool_name="get_weather_forecast_tool"),
    )


def _call(call_id: str, name: str) -> dict[str, Any]:
    return {"id": call_id, "name": name, "args": {}}


def _thread() -> list[BaseMessage]:
    return [
        HumanMessage(content="an earlier question"),
        AIMessage(content="", tool_calls=[_call("old", "list_reminders_tool")]),
        ToolMessage(content=EARLIER_TURN, tool_call_id="old", name="list_reminders_tool"),
        AIMessage(content="an earlier answer"),
        HumanMessage(content="Quel jour dois-je rapporter les livres à la médiathèque ?"),
        AIMessage(
            content="",
            tool_calls=[
                _call("c1", "list_reminders_tool"),
                _call("c2", "get_tasks_tool"),
                _call("c3", "get_current_weather_tool"),
                _call("c4", "get_weather_forecast_tool"),
                _call("c5", "send_email_tool"),
            ],
        ),
        ToolMessage(content=READ_DAY, tool_call_id="c1", name="list_reminders_tool"),
        ToolMessage(content=FAILED, tool_call_id="c2", name="get_tasks_tool", status="error"),
        ToolMessage(
            content=NOT_RUN,
            tool_call_id="c3",
            name="get_current_weather_tool",
            artifact=TOOL_CALL_NOT_RUN,
        ),
        ToolMessage(content=READ_BY_REGISTRY, tool_call_id="c4", name="get_weather_forecast_tool"),
        ToolMessage(content=ACTED, tool_call_id="c5", name="send_email_tool"),
    ]


def _state(final_message: str, *, registry: dict[str, Any] | None = None) -> MessagesState:
    state = create_initial_state(uuid4(), session_id="s", run_id="r")
    state["react_agent_result"] = {"final_message": final_message, "iteration_count": 3}
    state["current_turn_id"] = TURN
    state["current_turn_registry"] = registry if registry is not None else {}
    state["messages"] = _thread()
    return state


class TestAWithheldAnswerKeepsTheTurnsData:
    def test_what_the_loop_read_reaches_the_response(self) -> None:
        state = _state("", registry={"weather_1": _weather_item()})

        _result, merged = _apply_react_passthrough(state, "run")

        assert merged
        assert READ_DAY in with_tool_data_section("", state)

    def test_only_this_turn_s_successful_reads_are_handed(self) -> None:
        """A failure has its own channel (ADR-303), a call that never ran is no
        result, an act is stated by its own directive (ADR-263 §23), and an
        earlier turn's read answered an earlier question."""
        state = _state("", registry={"weather_1": _weather_item()})

        _apply_react_passthrough(state, "run")
        section = with_tool_data_section("", state)

        assert READ_DAY in section
        for absent in (FAILED, NOT_RUN, ACTED, EARLIER_TURN):
            assert absent not in section

    def test_a_read_the_registry_shows_is_not_handed_twice(self) -> None:
        registry = {"weather_1": _weather_item()}
        state = _state("", registry=registry)

        _apply_react_passthrough(state, "run")

        assert READ_BY_REGISTRY not in with_tool_data_section("", state)
        assert state["agent_results"][f"{TURN}:react_agent"]["registry_updates"] == registry

    def test_a_checkpointed_registry_is_read_the_same(self) -> None:
        """Restored from a checkpoint, the registry holds dicts, not models."""
        state = _state("", registry={"weather_1": _weather_item().model_dump(mode="json")})

        _apply_react_passthrough(state, "run")
        section = with_tool_data_section("", state)

        assert READ_DAY in section
        assert READ_BY_REGISTRY not in section

    def test_a_delivered_answer_is_handed_as_before(self) -> None:
        """The answer is authoritative; its reads are not repeated beside it."""
        state = _state("Mardi 17 novembre.", registry={"weather_1": _weather_item()})

        _apply_react_passthrough(state, "run")

        assert with_tool_data_section("", state) == ""

    def test_nothing_read_and_nothing_answered_hands_nothing(self) -> None:
        state = _state("")
        state["messages"] = [HumanMessage(content="Quel jour dois-je rapporter les livres ?")]

        _result, merged = _apply_react_passthrough(state, "run")

        assert not merged
        assert f"{TURN}:react_agent" not in (state.get("agent_results") or {})
