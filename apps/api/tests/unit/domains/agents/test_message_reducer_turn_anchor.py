"""The truncation reducer never evicts the current turn's question (Lot A).

Measured defect (2026-09-02): ``add_messages_with_truncate`` bounds state at
``max_messages_history`` by keeping the LAST N messages. A single ReAct turn
producing 2 messages per iteration therefore evicts its own ``HumanMessage``
at iteration ``ceil(max_messages_history / 2)`` — verified at exactly 75 with
the default 150. Downstream, ``_window_messages_for_react`` looks for the last
HumanMessage to split history from the current loop; with none left it
short-circuits entirely, and the model finishes the turn with no stated goal.

The fix pins the last HumanMessage (the turn anchor) back into the kept
window, right after any leading SystemMessages, on BOTH truncation branches
(token trim and count cap). Below the cap the reducer's output is unchanged.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from src.core.config import settings
from src.domains.agents.models import add_messages_with_truncate

pytestmark = [pytest.mark.unit]


def _react_turn_growth(n_iterations: int, payload: str = "r" * 200) -> list:
    """Feed a ReAct-shaped turn through the reducer, iteration by iteration."""
    state: list = []
    for i in range(n_iterations):
        new: list = []
        if i == 0:
            new.append(HumanMessage(content="Prepare my day.", id="human-turn"))
        new.append(
            AIMessage(
                content="",
                id=f"ai-{i}",
                tool_calls=[{"name": "t", "args": {}, "id": f"c{i}"}],
            )
        )
        new.append(ToolMessage(content=payload, id=f"tm-{i}", tool_call_id=f"c{i}", name="t"))
        state = add_messages_with_truncate(state, new)
    return state


def _has(state: list, msg_id: str) -> bool:
    return any(getattr(m, "id", None) == msg_id for m in state)


class TestTurnAnchorSurvivesCountCap:
    def test_anchor_survives_past_the_eviction_iteration(self) -> None:
        """At ceil(cap/2)+ iterations the question used to vanish; it must stay."""
        cap = settings.max_messages_history
        state = _react_turn_growth(cap // 2 + 5)
        assert _has(state, "human-turn"), "turn anchor evicted by the count cap"
        # The bound itself still holds (anchor re-pinned WITHIN the budget +1).
        assert len(state) <= cap + 1

    def test_anchor_survives_at_the_hard_ceiling(self) -> None:
        state = _react_turn_growth(90)
        assert _has(state, "human-turn")

    def test_anchor_sits_before_the_kept_loop_messages(self) -> None:
        """Chronology: the question precedes every kept AI/Tool message."""
        state = _react_turn_growth(90)
        ids = [getattr(m, "id", None) for m in state]
        anchor_idx = ids.index("human-turn")
        first_loop_idx = min(
            i for i, m in enumerate(state) if isinstance(m, (AIMessage, ToolMessage))
        )
        assert anchor_idx < first_loop_idx

    def test_windowing_regains_its_function_after_anchor(self) -> None:
        """The ReAct windowing must never short-circuit on an anchored state."""
        from src.domains.agents.nodes.react_nodes import _window_messages_for_react

        state = _react_turn_growth(90)
        windowed = _window_messages_for_react(state)
        # The split point exists again: last_human_idx != -1, so history
        # SystemMessage hygiene applies (list processed, not returned as-is).
        assert any(isinstance(m, HumanMessage) for m in windowed)


class TestTokenTrimBranch:
    def test_anchor_repinned_after_token_trim(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Huge tool payloads trigger the TOKEN trim before the count cap."""
        monkeypatch.setattr("src.core.config.settings.max_tokens_history", 2_000)
        state = _react_turn_growth(10, payload="word " * 400)  # ~500 tokens each
        assert _has(state, "human-turn"), "turn anchor evicted by the token trim"

    def test_anchor_inserted_after_leading_system_messages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A compaction-summary SystemMessage keeps its leading position."""
        monkeypatch.setattr("src.core.config.settings.max_tokens_history", 2_000)
        summary = SystemMessage(content="[Conversation history compacted ...]", id="sum")
        state: list = [summary]
        state = add_messages_with_truncate(state, [HumanMessage(content="Q", id="human-turn")])
        for i in range(10):
            state = add_messages_with_truncate(
                state,
                [
                    AIMessage(
                        content="",
                        id=f"ai-{i}",
                        tool_calls=[{"name": "t", "args": {}, "id": f"c{i}"}],
                    ),
                    ToolMessage(
                        content="word " * 400,
                        id=f"tm-{i}",
                        tool_call_id=f"c{i}",
                        name="t",
                    ),
                ],
            )
        assert _has(state, "human-turn")
        ids = [getattr(m, "id", None) for m in state]
        assert ids.index("sum") < ids.index("human-turn")


class TestNoBehaviourChangeBelowTheCap:
    def test_normal_conversation_unchanged(self) -> None:
        """A plain conversation over the cap keeps dropping OLDEST turns only."""
        cap = settings.max_messages_history
        state: list = []
        n_turns = cap // 2 + 10
        for k in range(n_turns):
            state = add_messages_with_truncate(
                state,
                [
                    HumanMessage(content=f"Q{k}", id=f"h{k}"),
                    AIMessage(content=f"A{k}", id=f"a{k}"),
                ],
            )
        assert len(state) <= cap + 1
        # The CURRENT question is the anchor and is naturally in the window.
        assert _has(state, f"h{n_turns - 1}")
        # The oldest turns were dropped, newest kept: normal sliding window.
        assert not _has(state, "h0")

    def test_below_cap_result_identical(self) -> None:
        """Under every threshold the reducer output is byte-identical."""
        state: list = []
        for k in range(5):
            state = add_messages_with_truncate(
                state,
                [
                    HumanMessage(content=f"Q{k}", id=f"h{k}"),
                    AIMessage(content=f"A{k}", id=f"a{k}"),
                ],
            )
        assert [m.id for m in state] == [x for k in range(5) for x in (f"h{k}", f"a{k}")]

    def test_no_human_message_is_a_noop(self) -> None:
        """With no HumanMessage anywhere there is no anchor to pin."""
        state: list = []
        for i in range(8):
            state = add_messages_with_truncate(
                state,
                [
                    AIMessage(
                        content="",
                        id=f"ai-{i}",
                        tool_calls=[{"name": "t", "args": {}, "id": f"c{i}"}],
                    ),
                    ToolMessage(content="r", id=f"tm-{i}", tool_call_id=f"c{i}", name="t"),
                ],
            )
        assert not any(isinstance(m, HumanMessage) for m in state)


class TestConfigCouplingWarning:
    def test_predicate_flags_exposed_configuration(self) -> None:
        from src.domains.agents.models import react_budget_exceeds_state_window

        # 90 iterations x 2 messages > 150-message window: exposed.
        assert react_budget_exceeds_state_window(90, 150) is True
        # 15 iterations stays comfortably inside: safe.
        assert react_budget_exceeds_state_window(15, 150) is False
        # Boundary: eviction at ceil(150/2) = 75 — 74 safe, 75 exposed.
        assert react_budget_exceeds_state_window(74, 150) is False
        assert react_budget_exceeds_state_window(75, 150) is True
