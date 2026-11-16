"""The measured count decides what the cap decided (FOR_EACH approval).

Measured 2026-11-15 (ADR-390 qualification, E13, « who are the people named in my
tickets? »): reading five tickets one by one asked a « bulk operation »
confirmation. Membership of the approval list is decided before the providers
run, on the cap (``for_each_max``, ten), the only number known then; the providers
then measured five, and the published rule asks a READ for approval only from
``FOR_EACH_WARNING_THRESHOLD`` items. The count was restated in the question and
the question was asked anyway. Once measured, the same rule decides again; a step
nothing measured keeps the decision its cap made, and a resumed approval narrows
the plan's list to the steps the person confirmed.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.core.config import settings
from src.domains.agents.nodes.for_each_hitl_prep import (
    affected_count,
    confirmed_hitl_steps,
    still_requiring_approval,
)

pytestmark = pytest.mark.unit

READ_SOURCE = "$steps.step_1.tickets"
NESTED_SOURCE = "$steps.step_2.tickets"
SEND_SOURCE = "$steps.step_1.contacts"


def _cap() -> int:
    return settings.for_each_warning_threshold + 5


def _step(step_id: str, tool_name: str, source: str, *, cap: int | None = None) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "tool_name": tool_name,
        "for_each_max": cap if cap is not None else _cap(),
        "for_each_source": source,
    }


class TestTheMeasuredCountDecides:
    def test_a_read_measured_under_the_published_threshold_asks_nothing(self) -> None:
        steps = [_step("step_2", "get_ticket_tool", READ_SOURCE)]

        kept = still_requiring_approval(
            steps, {READ_SOURCE: settings.for_each_warning_threshold - 1}
        )

        assert kept == []

    def test_a_read_measured_at_the_threshold_still_asks(self) -> None:
        steps = [_step("step_2", "get_ticket_tool", READ_SOURCE)]

        kept = still_requiring_approval(steps, {READ_SOURCE: settings.for_each_warning_threshold})

        assert kept == steps

    def test_a_read_measured_above_its_cap_still_asks(self) -> None:
        steps = [_step("step_2", "get_ticket_tool", READ_SOURCE, cap=2)]

        kept = still_requiring_approval(steps, {READ_SOURCE: 3})

        assert kept == steps

    def test_an_act_still_asks(self) -> None:
        """Measured or not, an act over several items is confirmed first."""
        steps = [_step("step_2", "send_email_tool", SEND_SOURCE)]

        kept = still_requiring_approval(
            steps, {SEND_SOURCE: max(1, settings.for_each_mutation_threshold)}
        )

        assert kept == steps

    def test_a_step_nothing_measured_keeps_its_cap_s_decision(self) -> None:
        steps = [_step("step_3", "search_memories_tool", NESTED_SOURCE)]

        assert still_requiring_approval(steps, {READ_SOURCE: 2}) == steps


class TestTheCountTheQuestionStates:
    def test_only_the_steps_still_asked_are_counted(self) -> None:
        asked = [_step("step_3", "send_email_tool", SEND_SOURCE)]

        assert affected_count(asked, {READ_SOURCE: 4, SEND_SOURCE: 3}) == 3

    def test_an_unmeasured_step_counts_its_cap(self) -> None:
        asked = [_step("step_3", "search_memories_tool", NESTED_SOURCE)]

        assert affected_count(asked, {READ_SOURCE: 4}) == _cap()

    def test_nothing_left_to_ask_counts_nothing(self) -> None:
        """The orchestrator's « nothing to confirm » path then runs the plan."""
        assert affected_count([], {READ_SOURCE: 4}) == 0


class TestAResumedApprovalNarrowsThePlan:
    def test_the_plan_s_list_keeps_the_steps_the_person_confirmed(self) -> None:
        read = _step("step_2", "get_ticket_tool", READ_SOURCE)
        nested = _step("step_3", "search_memories_tool", NESTED_SOURCE)

        assert confirmed_hitl_steps({"steps": [nested]}, [read, nested]) == [nested]

    def test_a_context_that_confirmed_every_step_keeps_them_all(self) -> None:
        steps = [_step("step_2", "get_ticket_tool", READ_SOURCE)]

        assert confirmed_hitl_steps({"steps": steps}, steps) == steps
