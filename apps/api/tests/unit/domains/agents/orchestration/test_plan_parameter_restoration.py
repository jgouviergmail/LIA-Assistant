"""A fabricated address is repaired from the previous plan, never re-invented.

Doctrine ADR-184: what is mechanically repairable is repaired BEFORE validation;
what cannot be repaired without inventing intent stays an error. Restoring a
value the previous plan already carried invents nothing — it had already passed
validation.

The defect, observed 2026-08-02: the user gave their address in a clarification,
the plan of that turn carried it (the placeholder guard stayed silent), then the
next replan lost it and re-invented ``jerome@example.com``. The planner HAD the
previous plan in its prompt and dropped the parameter anyway while fixing an
unrelated issue.

Why this cannot overwrite a change of mind: the trigger is not "the parameter
changed", it is "the parameter is an RFC 2606 reserved domain". Nobody ever asks
to write to example.com — such a value is, by construction, a fabrication. A
real new value is never touched (see the dedicated test below).
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_predicates import (
    detect_placeholder_contacts,
    restore_fabricated_parameters,
)
from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)

pytestmark = pytest.mark.unit


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", user_id="u", session_id="s", steps=list(steps))


def _step(step_id: str, tool: str, **parameters: object) -> ExecutionStep:
    """A step as every producer actually builds it, ``agent_name`` included.

    Not decoration: a TOOL step without an agent no longer builds at all (the
    model validates it), and it never reached a checkpoint intact either.
    """
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="emails_agent",
        tool_name=tool,
        parameters=dict(parameters),
    )


class TestRestoresWhatThePreviousPlanKnew:
    def test_a_fabricated_address_is_replaced_by_the_real_one(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com", subject="x"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr", subject="x"))

        restored = restore_fabricated_parameters(new, previous)

        assert restored == ["s2.to"]
        assert new.steps[0].parameters["to"] == "marie@client.fr"
        assert not detect_placeholder_contacts(new), "the plan must now pass its own guard"

    def test_a_fabricated_value_nested_in_a_list_is_replaced(self) -> None:
        """The common shape: `attendees` is always a list."""
        new = _plan(_step("s2", "create_event_tool", attendees=["jerome@example.com"]))
        previous = _plan(_step("s2", "create_event_tool", attendees=["marie@client.fr"]))

        restored = restore_fabricated_parameters(new, previous)

        assert restored == ["s2.attendees"]
        assert not detect_placeholder_contacts(new)

    def test_each_step_is_repaired_from_its_own_counterpart(self) -> None:
        new = _plan(
            _step("s2", "send_email_tool", to="a@example.com"),
            _step("s3", "send_email_tool", to="b@example.com"),
        )
        previous = _plan(
            _step("s2", "send_email_tool", to="un@client.fr"),
            _step("s3", "send_email_tool", to="deux@client.fr"),
        )

        assert restore_fabricated_parameters(new, previous) == ["s2.to", "s3.to"]
        assert new.steps[0].parameters["to"] == "un@client.fr"
        assert new.steps[1].parameters["to"] == "deux@client.fr"


class TestRefusesToActWhenItWouldGuess:
    """Every branch here leaves the plan untouched, so the guard still rejects it."""

    def test_a_real_value_is_never_overwritten(self) -> None:
        """THE safety property: a change of mind always wins."""
        new = _plan(_step("s2", "send_email_tool", to="nouveau@client.fr"))
        previous = _plan(_step("s2", "send_email_tool", to="ancien@client.fr"))

        assert restore_fabricated_parameters(new, previous) == []
        assert new.steps[0].parameters["to"] == "nouveau@client.fr"

    def test_free_text_parameters_are_left_alone(self) -> None:
        """Rewriting a drafted body would destroy what the user wrote."""
        new = _plan(
            _step("s2", "send_email_tool", to="ok@client.fr", body="écris à jerome@example.com")
        )
        previous = _plan(_step("s2", "send_email_tool", to="ok@client.fr", body="autre texte"))

        assert restore_fabricated_parameters(new, previous) == []
        assert new.steps[0].parameters["body"] == "écris à jerome@example.com"

    def test_no_previous_plan_means_nothing_to_restore(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))

        assert restore_fabricated_parameters(new, None) == []
        assert detect_placeholder_contacts(new), "the guard must still reject it"

    def test_same_step_id_but_a_different_tool_is_not_the_same_step(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "create_event_tool", to="marie@client.fr"))

        assert restore_fabricated_parameters(new, previous) == []

    def test_a_previous_fabrication_is_never_propagated(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="a@example.com"))
        previous = _plan(_step("s2", "send_email_tool", to="b@example.org"))

        assert restore_fabricated_parameters(new, previous) == []

    def test_a_parameter_absent_from_the_previous_plan_is_not_invented(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", subject="x"))

        assert restore_fabricated_parameters(new, previous) == []

    def test_a_step_absent_from_the_previous_plan_is_skipped(self) -> None:
        new = _plan(_step("s9", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))

        assert restore_fabricated_parameters(new, previous) == []

    def test_a_read_only_step_is_out_of_scope(self) -> None:
        """The detector exempts reads; the repair must agree with it."""
        new = _plan(_step("s1", "get_contacts_tool", query="jerome@example.com"))
        previous = _plan(_step("s1", "get_contacts_tool", query="marie@client.fr"))

        assert restore_fabricated_parameters(new, previous) == []
        assert new.steps[0].parameters["query"] == "jerome@example.com"


class TestToleratesTheCheckpointShape:
    def test_a_previous_plan_whose_steps_are_mappings(self) -> None:
        """After a resume, `plan.steps` holds dicts (see the checkpoint guard)."""

        class _Restored:
            steps = [
                {
                    "step_id": "s2",
                    "tool_name": "send_email_tool",
                    "parameters": {"to": "marie@client.fr"},
                }
            ]

        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))

        assert restore_fabricated_parameters(new, _Restored()) == ["s2.to"]
        assert new.steps[0].parameters["to"] == "marie@client.fr"


class TestTheClarifiedFieldIsNotReImposed:
    """A fresh answer outranks anything the previous plan carried for it.

    The prompt already works this way: ``_extract_preserved_parameters``
    excludes the clarified field from what the planner is asked to keep. A
    repair that re-imposed the old value would silently undo the very answer the
    user was just asked for — the exact opposite of what a clarification is for.
    """

    def test_the_clarified_parameter_is_left_alone(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))

        assert restore_fabricated_parameters(new, previous, skip_parameters={"to"}) == []
        assert new.steps[0].parameters["to"] == "jerome@example.com"

    def test_the_other_parameters_are_still_repaired(self) -> None:
        """Skipping one field must not disable the repair for the rest."""
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com", cc="paul@example.org"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr", cc="paul@client.fr"))

        assert restore_fabricated_parameters(new, previous, skip_parameters={"to"}) == ["s2.cc"]
        assert new.steps[0].parameters["to"] == "jerome@example.com"
        assert new.steps[0].parameters["cc"] == "paul@client.fr"

    def test_no_skip_list_repairs_everything(self) -> None:
        """The default is the plain repair — the guard is opt-in by the caller."""
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))

        assert restore_fabricated_parameters(new, previous) == ["s2.to"]


class TestNestedAndDegenerateShapes:
    """Parameters are not always flat strings, and previous plans are not always usable."""

    def test_a_fabricated_address_nested_in_a_dict_is_detected(self) -> None:
        """Some tools take structured recipients — the scan must reach inside.

        The list case was fixed during simulation; the dict case is its twin and
        would otherwise let a fabricated address through untouched.
        """
        new = _plan(_step("s2", "send_email_tool", recipient={"primary": "jerome@example.com"}))
        previous = _plan(_step("s2", "send_email_tool", recipient={"primary": "marie@client.fr"}))

        assert restore_fabricated_parameters(new, previous) == ["s2.recipient"]
        assert new.steps[0].parameters["recipient"] == {"primary": "marie@client.fr"}

    def test_a_previous_plan_with_no_identifiable_steps_repairs_nothing(self) -> None:
        """A shape carrying no step ids gives nothing to match against."""
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))

        class _Unusable:
            steps = [{"tool_name": "send_email_tool"}]  # no step_id

        assert restore_fabricated_parameters(new, _Unusable()) == []
        assert new.steps[0].parameters["to"] == "jerome@example.com"


class TestNameMatchingIsCaseInsensitive:
    """Both exemption lists must fold case, or they disagree with each other.

    The free-text list already lowered the parameter name; comparing the skip
    list raw beside it meant `To` was repairable while `to` was protected — a
    difference no reader would predict, surfacing as a bug report about one tool.
    """

    def test_the_clarified_field_is_skipped_whatever_its_case(self) -> None:
        new = _plan(_step("s2", "send_email_tool", To="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", To="marie@client.fr"))

        assert restore_fabricated_parameters(new, previous, skip_parameters={"to"}) == []
        assert new.steps[0].parameters["To"] == "jerome@example.com"

    def test_a_free_text_field_is_exempt_whatever_its_case(self) -> None:
        """A drafted body must never be overwritten, however the tool names it."""
        new = _plan(_step("s2", "send_email_tool", Body="Écris à contact@example.com"))
        previous = _plan(_step("s2", "send_email_tool", Body="Autre texte"))

        assert restore_fabricated_parameters(new, previous) == []
        assert new.steps[0].parameters["Body"] == "Écris à contact@example.com"
