"""An item the person designated is the one the plan acts on (ADR-367 amendment).

Measured on Docker dev 2026-10-31: « draft a reply to the second email » was
resolved on the list shown, then planned as a NEW inbox lookup and a reply to
its ``[1]`` — another message than the one designated.
"""

from __future__ import annotations

from typing import Any

import pytest

from src.domains.agents.orchestration.designation_repair import bind_designated_item
from src.domains.agents.orchestration.plan_schemas import ExecutionPlan, ExecutionStep, StepType

pytestmark = pytest.mark.unit

DESIGNATED = {"id": "msg-2", "subject": "Photos", "from": "Marc <marc@example.com>"}


def _acts(tool: str) -> bool:
    return not tool.startswith("get_")


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


LOOKUP = _step("find", "get_emails_tool", parameters={"query": "in:inbox", "max_results": 5})


def _reply(**parameters: Any) -> ExecutionStep:
    return _step(
        "reply", "create_mailbox_reply_draft_tool", depends_on=["find"], parameters=parameters
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", user_id="u", steps=list(steps))


def _bind(plan: ExecutionPlan) -> ExecutionPlan | None:
    return bind_designated_item(plan, [DESIGNATED], "emails", _acts)


class TestThePlanActsOnTheDesignatedItem:
    def test_a_position_of_a_new_lookup_is_bound_to_the_designated_item(self) -> None:
        repaired = _bind(_plan(LOOKUP, _reply(message_id="$steps.find.emails[1].id")))

        assert repaired is not None
        assert [step.step_id for step in repaired.steps] == ["reply"]  # no lookup any more
        assert repaired.steps[0].parameters == {"message_id": "msg-2"}
        assert repaired.steps[0].depends_on == []

    def test_a_field_inside_a_text_is_bound_too(self) -> None:
        reply = _reply(
            message_id="$steps.find.emails[0].id",
            content_instruction="Thank {{ steps.find.emails[0].from }} for « $steps.find.emails[0].subject »",
        )
        repaired = _bind(_plan(LOOKUP, reply))

        assert repaired is not None
        assert repaired.steps[0].parameters["content_instruction"] == (
            "Thank Marc <marc@example.com> for « Photos »"
        )


class TestAPlanWhoseIntentIsNotOneDesignation:
    def test_a_plan_naming_the_item_is_left_as_written(self) -> None:
        assert (
            _bind(
                _plan(
                    _step(
                        "reply",
                        "create_mailbox_reply_draft_tool",
                        parameters={"message_id": "msg-2"},
                    )
                )
            )
            is None
        )

    def test_two_lookups_of_the_domain_are_left_as_written(self) -> None:
        other = _step("other", "get_emails_tool", parameters={"query": "from:paul"})
        forward = _step(
            "fwd",
            "forward_email_tool",
            depends_on=["other"],
            parameters={"message_id": "$steps.other.emails[0].id", "to": "x@example.com"},
        )
        assert (
            _bind(_plan(LOOKUP, other, _reply(message_id="$steps.find.emails[1].id"), forward))
            is None
        )

    def test_a_lookup_another_step_reads_stays_and_so_does_the_plan(self) -> None:
        summary = _step(
            "sum",
            "send_email_tool",
            depends_on=["find"],
            parameters={"content_instruction": "Summarise $steps.find.emails"},
        )
        assert _bind(_plan(LOOKUP, _reply(message_id="$steps.find.emails[1].id"), summary)) is None

    def test_another_domain_s_lookup_is_not_the_item_s(self) -> None:
        contacts = _step("who", "get_contacts_tool", parameters={"query": "Paul"})
        send = _step(
            "send",
            "send_email_tool",
            depends_on=["who"],
            parameters={"to": "$steps.who.contacts[0].email", "content_instruction": "hi"},
        )
        assert _bind(_plan(contacts, send)) is None

    def test_a_field_the_item_does_not_carry_leaves_the_plan_as_written(self) -> None:
        assert _bind(_plan(LOOKUP, _reply(message_id="$steps.find.emails[1].threadId"))) is None

    def test_several_designated_items_are_not_one_designation(self) -> None:
        plan = _plan(LOOKUP, _reply(message_id="$steps.find.emails[1].id"))
        assert bind_designated_item(plan, [DESIGNATED, DESIGNATED], "emails", _acts) is None
