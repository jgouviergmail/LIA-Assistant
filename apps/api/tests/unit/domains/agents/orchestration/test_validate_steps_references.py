"""Unit tests for the "ghost dependency" gate (``validate_steps_references``).

The planner writes cross-step references as ``$steps.<step_id>.<result_key>``.
A *ghost dependency* is a reference that names the right DATA under the wrong
STEP — e.g. asking for ``events`` from the step that produced ``contacts``. Left
unchecked it feeds the wrong entity into the next call (a recipient, an event
id…), so the gate rejects the plan and returns correction feedback.

The gate is wired (``PlanSemanticValidator``) and had no test at all.

The sharp edge: the reference regex captures ANY ``$steps.X.Y``, but ``Y`` is
only a result_key some of the time. It is just as often a plain output FIELD —
``count``, ``success`` — which the catalogue documents as legitimate
(``reference_examples`` of get_contacts_tool literally lists ``"count"``).
Treating a field access as a domain reference rejects a perfectly valid plan.
``total`` stays in the parametrization below on purpose: the discriminator must
skip ANY non-result_key segment, including one no manifest advertises.
``get_domain_from_result_key`` is the discriminator: it resolves result_keys and
returns ``None`` for field names.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.orchestration.semantic_validator import (
    _get_expected_result_key_for_tool,
    validate_steps_references,
)

pytestmark = pytest.mark.unit


def _step(
    step_id: str,
    tool_name: str,
    agent_name: str,
    parameters: dict | None = None,
    depends_on: list[str] | None = None,
) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name=agent_name,
        tool_name=tool_name,
        parameters=parameters or {},
        depends_on=depends_on or [],
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="plan_1", user_id="user_1", steps=list(steps))


CONTACTS_STEP = _step("step_1", "get_contacts_tool", "contact_agent", {"query": "jean"})
EVENTS_STEP = _step("step_2", "get_events_tool", "event_agent", {"query": "today"})


def _consumer(parameters: dict, depends_on: list[str]) -> ExecutionStep:
    return _step("step_9", "send_email_tool", "email_agent", parameters, depends_on)


# ============================================================================
# result_key resolution (the mapping the gate is built on)
# ============================================================================


class TestExpectedResultKey:
    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("get_contacts_tool", "contacts"),
            ("get_events_tool", "events"),
            ("get_emails_tool", "emails"),
        ],
    )
    def test_known_tools_resolve(self, tool_name: str, expected: str) -> None:
        assert _get_expected_result_key_for_tool(tool_name) == expected

    def test_unknown_tool_resolves_to_none(self) -> None:
        assert _get_expected_result_key_for_tool("not_a_real_tool") is None

    def test_empty_name_resolves_to_none(self) -> None:
        assert _get_expected_result_key_for_tool("") is None


# ============================================================================
# Ghost dependencies (true positives — must keep firing)
# ============================================================================


class TestGhostDependencyDetection:
    def test_reference_to_the_wrong_step_is_rejected(self) -> None:
        """step_1 produces contacts, not events — and step_2 does."""
        plan = _plan(
            CONTACTS_STEP,
            EVENTS_STEP,
            _consumer({"body": "$steps.step_1.events[0].summary"}, ["step_1", "step_2"]),
        )
        is_valid, feedback = validate_steps_references(plan)

        assert is_valid is False
        assert feedback is not None
        assert "GHOST_DEPENDENCY" in feedback
        assert "step_1 produces 'contacts', not 'events'" in feedback

    def test_feedback_points_at_the_correct_step(self) -> None:
        plan = _plan(
            CONTACTS_STEP,
            EVENTS_STEP,
            _consumer({"body": "$steps.step_1.events[0].summary"}, ["step_1", "step_2"]),
        )
        _, feedback = validate_steps_references(plan)
        assert "Use '$steps.step_2.events'" in (feedback or "")

    def test_no_producing_step_is_reported_differently(self) -> None:
        """The data is nowhere in the plan — a different correction hint."""
        plan = _plan(
            CONTACTS_STEP,
            _consumer({"body": "$steps.step_1.weathers[0].temp"}, ["step_1"]),
        )
        is_valid, feedback = validate_steps_references(plan)

        assert is_valid is False
        assert "No step in the plan produces 'weathers'" in (feedback or "")


# ============================================================================
# Legitimate references (false positives — must NOT fire)
# ============================================================================


class TestLegitimateReferencesArePreserved:
    def test_correct_domain_reference_passes(self) -> None:
        plan = _plan(
            CONTACTS_STEP,
            _consumer({"to": "$steps.step_1.contacts[0].emailAddresses[0].value"}, ["step_1"]),
        )
        assert validate_steps_references(plan) == (True, None)

    @pytest.mark.parametrize("field", ["total", "count", "success", "message_count"])
    def test_scalar_output_field_is_not_a_ghost_dependency(self, field: str) -> None:
        """Regression: the second path segment is a plain output FIELD, not a
        result_key. ``get_contacts_tool`` documents ``"count"`` in its own
        ``reference_examples``, yet this gate used to reject it as a ghost
        dependency — rejecting a valid plan and forcing a wasted replan.
        """
        plan = _plan(
            CONTACTS_STEP,
            _consumer({"body": f"Found $steps.step_1.{field} matches"}, ["step_1"]),
        )
        assert validate_steps_references(plan) == (True, None)

    def test_plan_without_references_passes(self) -> None:
        plan = _plan(CONTACTS_STEP, _consumer({"to": "a@b.co"}, ["step_1"]))
        assert validate_steps_references(plan) == (True, None)

    def test_step_without_parameters_is_skipped(self) -> None:
        plan = _plan(CONTACTS_STEP, _step("step_2", "get_events_tool", "event_agent"))
        assert validate_steps_references(plan) == (True, None)

    def test_reference_to_an_unmapped_tool_is_skipped(self) -> None:
        """Without a known result_key for the producer there is nothing to
        compare against — fail-open rather than reject blindly."""
        plan = _plan(
            _step("step_1", "some_unmapped_tool", "query_agent", {"q": "x"}),
            _consumer({"body": "$steps.step_1.anything"}, ["step_1"]),
        )
        assert validate_steps_references(plan) == (True, None)

    def test_reference_to_an_absent_step_is_skipped(self) -> None:
        """Dangling step ids are the dependency validator's job, not this gate's."""
        plan = _plan(
            CONTACTS_STEP,
            _consumer({"body": "$steps.ghost_step.contacts"}, ["step_1"]),
        )
        assert validate_steps_references(plan) == (True, None)


# ============================================================================
# Multiple references
# ============================================================================


class TestMultipleReferences:
    def test_every_bad_reference_is_reported(self) -> None:
        plan = _plan(
            CONTACTS_STEP,
            EVENTS_STEP,
            _consumer(
                {
                    "to": "$steps.step_1.events[0].id",
                    "body": "$steps.step_2.contacts[0].name",
                },
                ["step_1", "step_2"],
            ),
        )
        is_valid, feedback = validate_steps_references(plan)

        assert is_valid is False
        assert "step_1 produces 'contacts', not 'events'" in (feedback or "")
        assert "step_2 produces 'events', not 'contacts'" in (feedback or "")

    def test_a_good_and_a_bad_reference_still_rejects(self) -> None:
        plan = _plan(
            CONTACTS_STEP,
            EVENTS_STEP,
            _consumer(
                {
                    "to": "$steps.step_1.contacts[0].emailAddresses[0].value",
                    "body": "$steps.step_1.events[0].summary",
                },
                ["step_1", "step_2"],
            ),
        )
        assert validate_steps_references(plan)[0] is False

    def test_mixing_a_scalar_field_with_a_ghost_reports_only_the_ghost(self) -> None:
        plan = _plan(
            CONTACTS_STEP,
            EVENTS_STEP,
            _consumer(
                {
                    "subject": "$steps.step_1.total found",
                    "body": "$steps.step_1.events[0].summary",
                },
                ["step_1", "step_2"],
            ),
        )
        is_valid, feedback = validate_steps_references(plan)

        assert is_valid is False
        assert "'events'" in (feedback or "")
        assert "total" not in (feedback or "")
