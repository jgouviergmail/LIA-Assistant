"""The engine a turn runs in has ONE door: ``executed_mode_of`` (ADR-070).

The run's context carries what the turn was ASKED to run in. What actually plans
it — the pipeline or the ReAct loop — is settled once, by the router for a new
turn and by the context builder for a resumed one, on a live holder the context
shares with every reader (a sub-agent included). Tools, registers and metric
labels read the engine through the door, never the request: a request is a
choice, an engine is a fact.
"""

from __future__ import annotations

import dataclasses
import uuid

import pytest

from src.domains.agents.context.runtime_context import (
    derive_sub_agent_context,
    executed_mode_of,
)
from src.domains.agents.context.runtime_context_builder import build_runtime_context
from tests.fixtures.conversation_cases import conversation_target
from tests.helpers.runtime_context import make_runtime_context

pytestmark = pytest.mark.unit


class TestTheDoor:
    def test_an_unsettled_turn_answers_what_it_was_asked(self) -> None:
        context = make_runtime_context(requested_execution_mode="react")

        assert executed_mode_of(context) == "react"

    def test_the_settled_engine_wins_over_the_request(self) -> None:
        """ReAct asked on an instance where the loop is off: the planner runs."""
        context = make_runtime_context(requested_execution_mode="react")
        context.turn_engine.settle("pipeline")

        assert executed_mode_of(context) == "pipeline"

    def test_settling_the_same_engine_twice_is_harmless(self) -> None:
        context = make_runtime_context()

        assert context.turn_engine.settle("react") == "react"
        assert context.turn_engine.settle("react") == "react"
        assert executed_mode_of(context) == "react"

    def test_a_turn_never_changes_engine(self) -> None:
        """A second settlement — a router meeting a resumed turn, a compacted
        replay deciding again — keeps the first: tools already ran in it."""
        context = make_runtime_context()
        context.turn_engine.settle("react")

        assert context.turn_engine.settle("pipeline") == "react"
        assert executed_mode_of(context) == "react"

    @pytest.mark.parametrize("value", ["auto", "", "loop"])
    def test_only_an_engine_settles(self, value: str) -> None:
        context = make_runtime_context()

        with pytest.raises(ValueError):
            context.turn_engine.settle(value)

    def test_a_sub_agent_shares_its_parent_s_engine(self) -> None:
        parent = make_runtime_context(requested_execution_mode="react")
        child = derive_sub_agent_context(parent, thread_id="sub-1")
        parent.turn_engine.settle("pipeline")

        assert executed_mode_of(child) == "pipeline"

    def test_the_holder_is_never_shared_between_two_contexts(self) -> None:
        """A default shared by every context would leak one turn's engine into the next."""
        first = make_runtime_context()
        second = make_runtime_context()
        first.turn_engine.settle("react")

        assert executed_mode_of(second) == "pipeline"

    def test_the_context_stays_frozen(self) -> None:
        context = make_runtime_context()

        with pytest.raises(dataclasses.FrozenInstanceError):
            context.requested_execution_mode = "react"  # type: ignore[misc]


class TestTheBuilderSettlesAResumedTurn:
    """A resumed turn never meets the router: its engine comes from the state."""

    @staticmethod
    def _build(state: dict[str, object], *, resuming: bool, requested: str = "pipeline"):
        return build_runtime_context(
            state=state,  # type: ignore[arg-type]
            target=conversation_target(uuid.uuid4(), uuid.uuid4()),
            user_execution_mode=requested,
            resuming=resuming,
        )

    def test_a_resumed_turn_keeps_the_engine_it_started_with(self) -> None:
        """The person may have changed their choice while LIA waited for them."""
        context = self._build(
            {"messages": [], "execution_mode": "react"}, resuming=True, requested="pipeline"
        )

        assert executed_mode_of(context) == "react"

    def test_a_new_turn_never_inherits_the_previous_turn_s_engine(self) -> None:
        """The restored state carries the PREVIOUS turn's mode until the router runs."""
        context = self._build(
            {"messages": [], "execution_mode": "react"}, resuming=False, requested="pipeline"
        )

        assert executed_mode_of(context) == "pipeline"
        assert context.turn_engine.executed is None

    @pytest.mark.parametrize("stored", [None, "auto", "garbage"])
    def test_a_resume_without_a_recorded_engine_settles_nothing(self, stored: object) -> None:
        context = self._build({"messages": [], "execution_mode": stored}, resuming=True)

        assert context.turn_engine.executed is None

    def test_the_request_reaches_the_context(self) -> None:
        context = self._build({"messages": []}, resuming=False, requested="react")

        assert context.requested_execution_mode == "react"
