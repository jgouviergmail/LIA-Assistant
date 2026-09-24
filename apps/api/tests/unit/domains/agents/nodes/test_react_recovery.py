"""A declared gap buys a bounded recovery pass (ADR-310).

Measured on 2026-09-23: a forecast tool served the wrong day, the ReAct loop saw
it, and ended the turn on « I could not get it » — with 66 iterations left and a
web search it never tried. The loop now closes its final message with an
``<unresolved>`` block, and a declared gap re-opens the loop once instead of
ending it. These tests pin the protocol: what counts as a declaration, when a
pass is taken, what the model is shown, and what reaches the thread.
"""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.messages import (
    AIMessage,
    HumanMessage,
    RemoveMessage,
    SystemMessage,
    ToolMessage,
)

from src.core.config import settings
from src.domains.agents.nodes import react_recovery as rr

pytestmark = pytest.mark.unit

GAP = "Mon texte.\n<unresolved>\n- Forecast for 2026-09-25: tool served 2026-09-24\n</unresolved>"


def _state(last: Any, passes: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "messages": [
            HumanMessage("q", id="h1"),
            ToolMessage("r", tool_call_id="c", id="t1"),
            last,
        ],
        "react_iteration": 3,
        "react_max_iterations_effective": 70,
        "react_elapsed_seconds": 1.0,
        "react_recovery_passes": passes or [],
    }


class TestTheDeclaration:
    def test_the_lines_of_the_block_are_the_declaration(self) -> None:
        assert rr.declared_unresolved(AIMessage(GAP)) == (
            "Forecast for 2026-09-25: tool served 2026-09-24",
        )

    def test_no_block_declares_nothing(self) -> None:
        assert rr.declared_unresolved(AIMessage("All good.")) == ()
        assert rr.declared_unresolved(None) == ()

    @pytest.mark.parametrize(
        "line",
        [
            "none",
            "None.",
            "-",
            "aucun",
            "Rien.",
            "nada",
            "nessuno",
            "无",
            "N/A",
            "",
            # The final review measured each of these as a one-fact declaration:
            # the lone « none » of the spec, in the forms the six languages write.
            "无。",
            "没有。",
            "—",
            "–",
            "nessuna",
            "keins",
            "keines",
        ],
    )
    def test_a_nothing_line_declares_nothing(self, line: str) -> None:
        assert rr.declared_unresolved(AIMessage(f"<unresolved>{line}</unresolved>")) == ()

    def test_case_bullets_and_several_blocks(self) -> None:
        text = "<thought><UNRESOLVED>1. A</UNRESOLVED></thought>\n<unresolved>* B\n* A</unresolved>"
        assert rr.declared_unresolved(AIMessage(text)) == ("A", "B")

    def test_list_content_is_read_as_text(self) -> None:
        message = AIMessage(content=[{"type": "text", "text": "<unresolved>A</unresolved>"}])
        assert rr.declared_unresolved(message) == ("A",)

    def test_a_tag_named_in_the_reasoning_opens_no_block(self) -> None:
        """Measured on dev (2026-09-24, the runtime proof): the model's <thought> said
        « declare the missing fact in <unresolved> », then the real block came —
        read from the first opening, the prose between them became 12 « facts »."""
        text = (
            "<thought>NEXT_OP: declare the missing fact in <unresolved> and give the method."
            "</thought>\nNo route without both ends.\n- Weather: cloudy\n"
            "<unresolved>\n- Brother's address: contacts not configured\n"
            "- Starting point: location unavailable\n</unresolved>"
        )
        assert rr.declared_unresolved(AIMessage(text)) == (
            "Brother's address: contacts not configured",
            "Starting point: location unavailable",
        )

    def test_the_placeholder_the_prompt_shows_declares_nothing(self) -> None:
        """The prompt shows the block as « <unresolved>...</unresolved> »: echoed
        in a thought, it is a placeholder, not a fact."""
        for placeholder in ("...", "…"):
            text = f"<thought>close with <unresolved>{placeholder}</unresolved></thought>OK"
            assert rr.declared_unresolved(AIMessage(text)) == ()


class TestThePredicate:
    def test_a_declared_gap_with_a_pass_left_recovers(self) -> None:
        assert rr.should_recover(_state(AIMessage(GAP, id="d1"))) is True

    def test_a_message_with_tool_calls_never_recovers(self) -> None:
        message = AIMessage(GAP, id="d1", tool_calls=[{"id": "c2", "name": "t", "args": {}}])
        assert rr.should_recover(_state(message)) is False

    def test_a_clean_answer_never_recovers(self) -> None:
        assert rr.should_recover(_state(AIMessage("All good.", id="d1"))) is False

    def test_no_pass_left(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "react_recovery_passes_max", 1)
        passes = [{"anchor_id": "t1", "draft": "x", "unresolved": ["A"]}]
        assert rr.should_recover(_state(AIMessage(GAP, id="d2"), passes)) is False

    def test_zero_switches_it_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(settings, "react_recovery_passes_max", 0)
        assert rr.should_recover(_state(AIMessage(GAP, id="d1"))) is False

    def test_a_budget_reached_never_recovers(self) -> None:
        state = _state(AIMessage(GAP, id="d1"))
        state["react_iteration"] = 70
        assert rr.should_recover(state) is False

    def test_a_draft_without_an_id_never_recovers(self) -> None:
        assert rr.should_recover(_state(AIMessage(GAP))) is False

    def test_a_draft_with_no_predecessor_never_recovers(self) -> None:
        assert rr.should_recover({"messages": [AIMessage(GAP, id="d1")]}) is False


class TestTheNode:
    async def test_the_draft_leaves_the_thread_and_travels_in_the_pass(self) -> None:
        update = await rr.react_recovery_node(_state(AIMessage(GAP, id="d1")), {})

        assert update["messages"] == [RemoveMessage(id="d1")]
        (record,) = update["react_recovery_passes"]
        assert record == {
            "anchor_id": "t1",
            "draft": GAP,
            "unresolved": ["Forecast for 2026-09-25: tool served 2026-09-24"],
        }

    async def test_a_second_pass_is_appended_never_replaced(self) -> None:
        first = {"anchor_id": "t0", "draft": "x", "unresolved": ["A"]}
        update = await rr.react_recovery_node(_state(AIMessage(GAP, id="d2"), [first]), {})
        assert update["react_recovery_passes"][0] == first
        assert len(update["react_recovery_passes"]) == 2


class TestWhatTheModelIsShown:
    PASS = {
        "anchor_id": "t1",
        "draft": "Mon texte. <unresolved>A\nB</unresolved>",
        "unresolved": ["A", "B"],
    }

    def test_the_draft_then_the_directive_follow_the_anchor(self) -> None:
        sent = [
            SystemMessage("s"),
            HumanMessage("q", id="h1"),
            ToolMessage("r", tool_call_id="c", id="t1"),
        ]
        out = rr.with_recovery_directives(sent, [self.PASS])

        assert [m.id for m in out[:3]] == [None, "h1", "t1"]
        draft, directive = out[3], out[4]
        assert isinstance(draft, AIMessage) and draft.content == self.PASS["draft"]
        assert isinstance(directive, HumanMessage)
        assert "- A\n- B" in str(directive.content)
        assert "RECOVERY LADDER" in str(directive.content)

    def test_the_roles_keep_alternating_after_the_question(self) -> None:
        """A draft right after the question: never two human messages in a row."""
        out = rr.with_recovery_directives(
            [HumanMessage("q", id="h1")], [{**self.PASS, "anchor_id": "h1"}]
        )
        assert [type(m).__name__ for m in out] == ["HumanMessage", "AIMessage", "HumanMessage"]

    def test_the_directive_never_splits_the_question_from_its_context(self) -> None:
        """ADR-308: the turn's context is a system message glued to its question."""
        sent = [SystemMessage("s"), HumanMessage("q", id="h1"), SystemMessage("ctx")]
        out = rr.with_recovery_directives(sent, [{**self.PASS, "anchor_id": "h1"}])
        assert [type(m).__name__ for m in out] == [
            "SystemMessage",
            "HumanMessage",
            "SystemMessage",
            "AIMessage",
            "HumanMessage",
        ]

    def test_two_passes_each_follow_their_own_anchor(self) -> None:
        sent = [
            HumanMessage("q", id="h1"),
            AIMessage("", id="a2", tool_calls=[{"id": "c2", "name": "t", "args": {}}]),
            ToolMessage("r2", tool_call_id="c2", id="t2"),
        ]
        first = {**self.PASS, "anchor_id": "h1", "draft": "D1"}
        second = {**self.PASS, "anchor_id": "t2", "draft": "D2"}
        out = rr.with_recovery_directives(sent, [first, second])
        assert [getattr(m, "id", None) or m.content for m in out if isinstance(m, AIMessage)] == [
            "D1",
            "a2",
            "D2",
        ]

    def test_two_passes_on_one_anchor_keep_their_order(self) -> None:
        """A pass whose reply calls no tool leaves the SAME predecessor for the next
        draft, so two records share one anchor (final review, 2026-09-24): each
        inserted at the anchor, the later pass was shown BEFORE the earlier."""
        sent = [SystemMessage("s"), HumanMessage("q", id="h1")]
        first = {**self.PASS, "anchor_id": "h1", "draft": "D1"}
        second = {**self.PASS, "anchor_id": "h1", "draft": "D2"}
        out = rr.with_recovery_directives(sent, [first, second])
        assert [m.content for m in out if isinstance(m, AIMessage)] == ["D1", "D2"]
        assert [type(m).__name__ for m in out] == [
            "SystemMessage",
            "HumanMessage",
            "AIMessage",
            "HumanMessage",
            "AIMessage",
            "HumanMessage",
        ]

    def test_nothing_is_written_to_the_given_list(self) -> None:
        sent = [HumanMessage("q", id="h1")]
        rr.with_recovery_directives(sent, [{**self.PASS, "anchor_id": "h1"}])
        assert len(sent) == 1

    def test_a_missing_anchor_still_shows_the_directive(self) -> None:
        out = rr.with_recovery_directives(
            [HumanMessage("q", id="h1")], [{**self.PASS, "anchor_id": "zz"}]
        )
        assert isinstance(out[-2], AIMessage) and isinstance(out[-1], HumanMessage)

    def test_no_pass_leaves_the_messages_as_they_are(self) -> None:
        sent = [HumanMessage("q", id="h1")]
        assert rr.with_recovery_directives(sent, []) == sent


class TestTheOutcome:
    PASSES = [{"anchor_id": "t1", "draft": "x", "unresolved": ["A", "B"]}]

    def test_no_pass_no_outcome(self) -> None:
        assert rr.recovery_outcome([], AIMessage("done"), cut=False) is None

    def test_every_outcome(self) -> None:
        assert rr.recovery_outcome(self.PASSES, AIMessage("done"), cut=False) == "resolved"
        partial = AIMessage("<unresolved>A</unresolved>")
        assert rr.recovery_outcome(self.PASSES, partial, cut=False) == "partial"
        same = AIMessage("<unresolved>A\nB</unresolved>")
        assert rr.recovery_outcome(self.PASSES, same, cut=False) == "still_unresolved"
        assert rr.recovery_outcome(self.PASSES, AIMessage(""), cut=True) == "cut"

    def test_a_pass_that_left_no_answer_resolved_nothing(self) -> None:
        """An empty reply declares nothing — and answers nothing: the draft's gaps
        stand (final review: it was counted `resolved`)."""
        for final in (AIMessage(""), AIMessage("  \n"), None):
            assert rr.recovery_outcome(self.PASSES, final, cut=False) == "still_unresolved"


class TestTheReport:
    """What the finalize node merges into react_agent_result, counted once."""

    PASSES = [
        {"anchor_id": "h1", "draft": "D1", "unresolved": ["A"]},
        {"anchor_id": "t2", "draft": "D2", "unresolved": ["A"]},
    ]

    def test_a_pass_that_left_no_answer_hands_back_the_last_draft(self) -> None:
        """The draft left the thread AT the pass; a pass that brings back nothing
        must not lose the answer the turn already had (final review)."""
        report = rr.recovery_report(
            {"react_recovery_passes": self.PASSES}, AIMessage(""), cut=False
        )
        assert report["final_message"] == "D2"
        assert report["recovery"] == {"passes": 2, "outcome": "still_unresolved"}

    def test_a_budget_cut_hands_back_the_last_draft(self) -> None:
        report = rr.recovery_report({"react_recovery_passes": self.PASSES}, AIMessage(""), cut=True)
        assert report["final_message"] == "D2"
        assert report["recovery"]["outcome"] == "cut"

    def test_a_real_answer_keeps_its_own_text(self) -> None:
        report = rr.recovery_report(
            {"react_recovery_passes": self.PASSES}, AIMessage("Sunny."), cut=False
        )
        assert "final_message" not in report

    def test_a_turn_without_a_pass_reports_nothing(self) -> None:
        assert rr.recovery_report({"react_recovery_passes": []}, AIMessage("x"), cut=False) == {}

    def test_a_pass_is_reported_and_counted(self) -> None:
        from src.infrastructure.observability.metrics_react import react_recovery_turns_total

        counter = react_recovery_turns_total.labels(outcome="resolved")
        before = counter._value.get()
        state = {"react_recovery_passes": TestTheOutcome.PASSES}

        report = rr.recovery_report(state, AIMessage("done"), cut=False)

        assert report == {"recovery": {"passes": 1, "outcome": "resolved"}}
        assert counter._value.get() == before + 1
