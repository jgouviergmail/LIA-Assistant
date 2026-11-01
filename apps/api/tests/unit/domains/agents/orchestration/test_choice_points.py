"""A plan acting on the FIRST item a lookup finds is found before it runs (ADR-367 amendment).

« Reply to Marc's email » with nothing shown is planned as a lookup and an act
on ``[0]``: when the lookup finds several, the first is a guess. The places are
found in the plan itself, so the lookup can run first and the person be asked.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.choice_points import ChoicePoint, choice_points
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

pytestmark = pytest.mark.unit

ACTS = {"create_mailbox_reply_draft_tool", "delete_event_tool", "send_email_tool"}


def _acts(tool_name: str) -> bool:
    return tool_name in ACTS


def _step(
    step_id: str, tool: str, depends_on: list[str] | None = None, **fields: Any
) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="email_agent",
        tool_name=tool,
        parameters=fields.pop("parameters", {}),
        depends_on=depends_on or [],
        **fields,
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", user_id="u", steps=list(steps))


LOOKUP = _step("find", "get_emails_tool", parameters={"query": "from:marc", "max_results": 5})


def _reply(reference: str = "$steps.find.emails[0].id") -> ExecutionStep:
    return _step(
        "reply",
        "create_mailbox_reply_draft_tool",
        depends_on=["find"],
        parameters={"message_id": reference, "content_instruction": "I will be late"},
    )


class TestAnActOnTheFirstFoundItem:
    def test_the_incident_plan_is_a_choice_point(self) -> None:
        assert choice_points(_plan(LOOKUP, _reply()), _acts) == [
            ChoicePoint(act_step_id="reply", source_step_id="find", list_path="emails")
        ]

    def test_the_template_form_is_read_too(self) -> None:
        plan = _plan(LOOKUP, _reply("{{ steps.find.emails[0].id }}"))
        assert [p.source_step_id for p in choice_points(plan, _acts)] == ["find"]

    def test_several_reads_of_the_first_item_are_one_point(self) -> None:
        reply = _step(
            "reply",
            "send_email_tool",
            depends_on=["find"],
            parameters={
                "to": "$steps.find.emails[0].from",
                "subject": "$steps.find.emails[0].subject",
            },
        )
        assert len(choice_points(_plan(LOOKUP, reply), _acts)) == 1


class TestNoChoiceWhereThePlanSaysWhich:
    def test_a_read_step_on_the_first_item_is_no_act(self) -> None:
        details = _step(
            "open",
            "get_email_details_tool",
            depends_on=["find"],
            parameters={"message_id": "$steps.find.emails[0].id"},
        )
        assert choice_points(_plan(LOOKUP, details), _acts) == []

    def test_another_position_is_the_person_s_own(self) -> None:
        assert choice_points(_plan(LOOKUP, _reply("$steps.find.emails[1].id")), _acts) == []

    def test_a_list_the_plan_iterates_over_is_its_subject(self) -> None:
        each = _step(
            "each",
            "send_email_tool",
            depends_on=["find"],
            for_each="$steps.find.emails",
            parameters={"to": "$item.from"},
        )
        assert choice_points(_plan(LOOKUP, _reply(), each), _acts) == []

    def test_a_list_another_step_reads_whole_is_its_subject(self) -> None:
        summary = _step(
            "sum",
            "send_email_tool",
            depends_on=["find"],
            parameters={"content_instruction": "Summarise $steps.find.emails"},
        )
        assert choice_points(_plan(LOOKUP, _reply(), summary), _acts) == []

    def test_a_lookup_downstream_of_an_act_is_not_run_ahead(self) -> None:
        deleted = _step("del", "delete_event_tool", parameters={"event_id": "e1"})
        lookup = _step("find", "get_emails_tool", depends_on=["del"], parameters={"query": "x"})
        assert choice_points(_plan(deleted, lookup, _reply()), _acts) == []

    def test_an_act_iterating_itself_is_not_a_first_item_pick(self) -> None:
        each = _step(
            "reply",
            "create_mailbox_reply_draft_tool",
            depends_on=["find"],
            for_each="$steps.find.emails",
            parameters={"message_id": "$item.id"},
        )
        assert choice_points(_plan(LOOKUP, each), _acts) == []
