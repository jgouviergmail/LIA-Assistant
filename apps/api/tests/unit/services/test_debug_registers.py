"""The three registers, on the debug panel (B8, lot 7.5).

ADR-263 keeps three registers per turn: what it DID (`agent_effects`), what it
CONSULTED (`agent_treatments`) and the turn itself (`agent_decisions`), the
spine the other two hang off. The panel showed the first and nothing else, so a
turn that opened nine sources and answered from them looked, on screen, like a
turn that did nothing.

**The source is the LIVE record, not the database.** The debug payload is
emitted INSIDE `treatment_recorder` and `decision_recorder`, which write on
exit: a read of the tables at that instant returns nothing for the current turn,
and « nothing » there is a false negative, not an empty turn. Both registers
publish their in-flight object for exactly this reason, so the panel shows what
is ABOUT to be written.

Two claims this pins:

- a consultation records the CAPABILITY, never the call: the panel gets the
  tool name, the outcome and the duration, and never an argument;
- the turn's outcome starts at `interrupted` and only an explicit success moves
  it, so the panel must publish it as « so far » rather than as a verdict.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest

from src.core.turn_verdicts import note_verdict, verdict_collector
from src.domains.agents.effects.decisions import (
    DecisionOutcome,
    TurnDecision,
    publish_turn,
    reset_turn,
)
from src.domains.agents.effects.treatments import Treatment, observe, treatment_collector
from src.domains.agents.services.streaming.register_debug import registers_debug

pytestmark = pytest.mark.unit

_USER = uuid.uuid4()


@contextmanager
def turn_scope(decision: TurnDecision) -> Iterator[TurnDecision]:
    """Publish a turn for the body, exactly as `decision_recorder` does."""
    token = publish_turn(decision)
    try:
        yield decision
    finally:
        reset_turn(token)


def _treatment(tool: str, *, outcome: str = "ok", ms: int = 12) -> Treatment:
    return Treatment(
        user_id=str(_USER),
        thread_id="t",
        run_id="r",
        source="user",
        execution_mode="pipeline",
        tool_name=tool,
        mutation_policy="read",
        outcome=outcome,
        duration_ms=ms,
        occurred_at=datetime(2026, 9, 10, 12, 0, tzinfo=UTC),
    )


class TestWhatTheTurnConsulted:
    def test_it_lists_the_capabilities_in_the_order_they_were_consulted(self) -> None:
        with treatment_collector(run_id="r"):
            observe(_treatment("get_emails_tool"))
            observe(_treatment("get_events_tool"))

            payload = registers_debug()

        assert [entry["tool_name"] for entry in payload["treatments"]["entries"]] == [
            "get_emails_tool",
            "get_events_tool",
        ]

    def test_it_counts_what_failed_apart(self) -> None:
        with treatment_collector(run_id="r"):
            observe(_treatment("get_emails_tool"))
            observe(_treatment("get_events_tool", outcome="failed"))

            payload = registers_debug()

        assert payload["treatments"]["count"] == 2
        assert payload["treatments"]["failed_count"] == 1

    def test_it_carries_the_duration_and_the_policy_and_nothing_else(self) -> None:
        # The field set IS the privacy contract: « searched Marie's emails »
        # would record a search nobody asked to have recorded.
        with treatment_collector(run_id="r"):
            observe(_treatment("get_emails_tool", ms=87))

            entry = registers_debug()["treatments"]["entries"][0]

        assert entry == {
            "tool_name": "get_emails_tool",
            "mutation_policy": "read",
            "outcome": "ok",
            "duration_ms": 87,
        }

    def test_a_turn_that_consulted_nothing_says_zero_rather_than_nothing(self) -> None:
        with treatment_collector(run_id="r"):
            payload = registers_debug()

        assert payload["treatments"] == {"entries": [], "count": 0, "failed_count": 0}


class TestTheTurnsOwnRecord:
    def test_it_publishes_the_spine_of_the_turn(self) -> None:
        decision = TurnDecision(
            run_id="r",
            user_id=_USER,
            thread_id="t",
            execution_mode="react",
            route="actionable",
            plan_step_count=3,
        )
        with turn_scope(decision):
            payload = registers_debug()

        assert payload["decision"]["execution_mode"] == "react"
        assert payload["decision"]["route"] == "actionable"
        assert payload["decision"]["plan_step_count"] == 3
        assert payload["decision"]["source"] == "user"

    def test_the_outcome_is_published_as_what_is_known_so_far(self) -> None:
        # It starts at `interrupted` and only an explicit success moves it: a
        # turn that dies without saying how it ended must never read as
        # answered. The panel is emitted BEFORE the row is written, so the
        # value it shows is « so far », and the payload says so.
        decision = TurnDecision(run_id="r", user_id=_USER, thread_id="t")
        with turn_scope(decision):
            payload = registers_debug()

        assert payload["decision"]["outcome"] == DecisionOutcome.INTERRUPTED.value
        assert payload["decision"]["settled"] is False

    def test_a_stop_reason_reaches_the_panel_when_one_was_set(self) -> None:
        decision = TurnDecision(run_id="r", user_id=_USER, thread_id="t")
        decision.stop_reason = "max_iterations"
        with turn_scope(decision):
            payload = registers_debug()

        assert payload["decision"]["stop_reason"] == "max_iterations"


class TestNothingIsClaimedOutsideATurn:
    def test_no_turn_and_no_collector_produces_no_payload(self) -> None:
        # Emitting an empty block would say « this turn consulted nothing and
        # decided nothing », which is a claim about a turn that is not there.
        assert registers_debug() is None

    def test_a_collector_with_no_decision_still_reports_its_consultations(self) -> None:
        with treatment_collector(run_id="r"):
            observe(_treatment("get_emails_tool"))
            payload = registers_debug()

        assert payload["decision"] is None
        assert payload["treatments"]["count"] == 1


class TestTheSilentCorrections:
    async def test_it_lists_what_the_turn_had_to_repair(self) -> None:
        async with verdict_collector():
            note_verdict("reasoning_coerced", "high->medium")
            note_verdict("history_repaired", "tool_calls:removal")

            payload = registers_debug()

        assert [entry["kind"] for entry in payload["verdicts"]["entries"]] == [
            "reasoning_coerced",
            "history_repaired",
        ]
        assert payload["verdicts"]["count"] == 2

    async def test_a_turn_that_corrected_nothing_says_zero(self) -> None:
        async with verdict_collector():
            payload = registers_debug()

        assert payload["verdicts"] == {"entries": [], "count": 0, "dropped": 0}

    async def test_a_capped_list_says_it_is_capped(self) -> None:
        from src.core.turn_verdicts import MAX_VERDICTS_PER_TURN

        async with verdict_collector():
            for _ in range(MAX_VERDICTS_PER_TURN + 3):
                note_verdict("history_repaired")

            payload = registers_debug()

        # « 50 » with nothing beside it reads as an exact count (ADR-185).
        assert payload["verdicts"]["count"] == MAX_VERDICTS_PER_TURN
        assert payload["verdicts"]["dropped"] == 3

    async def test_a_collector_alone_is_enough_to_produce_a_payload(self) -> None:
        async with verdict_collector():
            note_verdict("quota_refused", "response")
            payload = registers_debug()

        assert payload["decision"] is None
        assert payload["verdicts"]["count"] == 1
