"""A mechanical repair that nobody can measure is a repair nobody can question.

Sibling of ``test_parameter_bounds``: that one pins WHAT gets repaired, this one
pins that the repair is reported. The counter matters more than it looks — a
steady rate means the replan prompt keeps losing parameters while fixing an
unrelated issue, and this repair only hides it (ADR-195).

It also pins the one case where the repair must stand down: the field the user
was just asked about. The previous plan no longer speaks for it, and re-imposing
its value would undo the answer the clarification existed to collect.
"""

from __future__ import annotations

import pytest

from src.domains.agents.orchestration.plan_schemas import (
    ExecutionPlan,
    ExecutionStep,
    StepType,
)
from src.domains.agents.services.planner.parameter_restoration import (
    _parameters_the_clarification_supersedes,
    preserved_parameters_for_prompt,
    restore_and_report,
)
from src.infrastructure.observability.metrics_agents import (
    planner_fabricated_parameters_restored,
)

pytestmark = pytest.mark.unit


def _step(step_id: str, tool_name: str, **parameters: object) -> ExecutionStep:
    return ExecutionStep(
        step_id=step_id,
        step_type=StepType.TOOL,
        agent_name="emails_agent",
        tool_name=tool_name,
        parameters=dict(parameters),
    )


def _plan(*steps: ExecutionStep) -> ExecutionPlan:
    return ExecutionPlan(plan_id="p", user_id="u", session_id="s", steps=list(steps))


def _counter() -> float:
    return planner_fabricated_parameters_restored._value.get()


class TestTheRepairIsCounted:
    def test_a_repair_increments_the_counter_once_per_parameter(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com", cc="paul@example.org"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr", cc="paul@client.fr"))

        before = _counter()
        restored = restore_and_report(new, previous)

        assert sorted(restored) == ["s2.cc", "s2.to"]
        assert _counter() - before == 2

    def test_nothing_repaired_leaves_the_counter_untouched(self) -> None:
        """The common case by far — it must not inflate the signal."""
        new = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))

        before = _counter()

        assert restore_and_report(new, previous) == []
        assert _counter() == before

    def test_no_previous_plan_is_not_an_error(self) -> None:
        """A first pass has nothing to restore from, and that is normal."""
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))

        before = _counter()

        assert restore_and_report(new, None) == []
        assert _counter() == before


class TestTheClarifiedFieldStandsDown:
    def test_the_answer_the_user_just_gave_is_not_overwritten(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))

        assert restore_and_report(new, previous, clarification_field="to") == []
        assert new.steps[0].parameters["to"] == "jerome@example.com"

    def test_a_field_clarified_elsewhere_still_repairs_the_recipient(self) -> None:
        new = _plan(_step("s2", "send_email_tool", to="jerome@example.com"))
        previous = _plan(_step("s2", "send_email_tool", to="marie@client.fr"))

        assert restore_and_report(new, previous, clarification_field="subject") == ["s2.to"]


class TestFieldToParameterMapping:
    """A logical field and the parameter carrying it need not share a name."""

    def test_a_field_expands_to_every_parameter_that_carries_it(self) -> None:
        """The field 'body' reaches 'content_instruction' — its name alone would not."""
        superseded = _parameters_the_clarification_supersedes("body")

        assert "body" in superseded
        assert "content_instruction" in superseded

    def test_a_field_with_no_mapping_still_covers_itself(self) -> None:
        """`to` has no entry in the map; skipping only the map would skip nothing."""
        assert _parameters_the_clarification_supersedes("to") == frozenset({"to"})

    def test_no_clarification_supersedes_nothing(self) -> None:
        assert _parameters_the_clarification_supersedes(None) == frozenset()
        assert _parameters_the_clarification_supersedes("") == frozenset()


class TestPreservationSurvivesTheCheckpointShape:
    """A clarification IS an interrupt — this runs on a resumed plan.

    A valid plan comes back with typed steps, so this is not the common path.
    But a step that no longer passes its own validation degrades to a mapping
    (see the checkpoint guard), attribute access raises, and the caller swallows
    it into a warning: the preservation would vanish in silence on the very turn
    where the user has just typed the value being lost.
    """

    class _Resumed:
        """An ExecutionPlan as it comes back from the checkpoint."""

        steps = [
            {
                "step_id": "step_1",
                "tool_name": "send_email_tool",
                "parameters": {"to": "marie@client.fr", "subject": "Retard"},
            }
        ]

    def test_a_resumed_plan_still_yields_its_parameters(self) -> None:
        preserved = preserved_parameters_for_prompt(self._Resumed(), "body")

        assert preserved.get("subject") == "Retard", (
            "the resumed shape yielded nothing — the planner would regenerate "
            "without the values the user already provided"
        )

    def test_the_object_shape_is_unchanged(self) -> None:
        """The nominal path must keep behaving exactly as before."""
        plan = _plan(_step("step_1", "send_email_tool", subject="Retard"))

        assert preserved_parameters_for_prompt(plan, "body").get("subject") == "Retard"

    def test_an_empty_or_absent_plan_is_not_an_error(self) -> None:
        """`ExecutionPlan` requires at least one step, so emptiness only ever
        arrives as an absent plan or a degraded mapping — both must be silent."""
        assert preserved_parameters_for_prompt(None, "body") == {}
        assert preserved_parameters_for_prompt({"steps": []}, "body") == {}
        assert preserved_parameters_for_prompt({}, "body") == {}

    def test_the_clarified_field_is_excluded_on_both_shapes(self) -> None:
        assert "to" not in preserved_parameters_for_prompt(self._Resumed(), "to")


class TestTheRepairIsWiredOnTheNominalPath:
    """A repair reachable only from a fallback is a repair that never runs.

    The nominal planning path goes through the LLM strategies, not through
    ``_plan_single_domain`` — that one is the panic-mode retry. The strategies
    called ``_build_plan`` without ``existing_plan``, so the repair was wired to
    the branch that almost never executes. Signature-level test on purpose: the
    defect was an omitted argument, which no behavioural test on the service
    would have caught.
    """

    @pytest.mark.parametrize("module_name", ["single_domain", "multi_domain"])
    def test_each_llm_strategy_forwards_the_previous_plan(self, module_name: str) -> None:
        import importlib
        import inspect

        module = importlib.import_module(
            f"src.domains.agents.services.planner.strategies.{module_name}"
        )
        source = inspect.getsource(module)
        call_start = source.index("_build_plan(")
        call = source[call_start : source.index(")", call_start)]

        assert "existing_plan" in call, (
            f"{module_name} calls _build_plan without existing_plan — the "
            f"fabricated-parameter repair cannot run on the nominal path"
        )
        assert "clarification_field" in call, (
            f"{module_name} calls _build_plan without clarification_field — the "
            f"repair would re-impose a value the user has just replaced"
        )


class TestWhatIsDeliberatelyNotRestatedToThePlanner:
    """Restating the wrong thing teaches the planner the wrong thing.

    Three filters, three distinct reasons — pinned because each one silently
    changes what the model sees on a replan.
    """

    def test_an_unresolved_reference_is_never_restated(self) -> None:
        """`$steps.step_1.email` is a promise, not a value.

        Handing it back as a "preserved parameter" would ask the planner to
        keep a placeholder it cannot resolve, and the user would receive a mail
        addressed to a literal reference.
        """
        plan = _plan(_step("step_1", "send_email_tool", to="$steps.step_0.contacts[0].email"))

        assert preserved_parameters_for_prompt(plan, "body") == {}

    def test_an_empty_value_is_not_restated(self) -> None:
        """An empty subject is an absence, not a decision worth preserving."""
        plan = _plan(_step("step_1", "send_email_tool", subject=""))

        assert preserved_parameters_for_prompt(plan, "body") == {}

    def test_a_non_preservable_parameter_is_left_out(self) -> None:
        """Ids and flags belong to the previous plan's plumbing, not the user's intent."""
        plan = _plan(_step("step_1", "send_email_tool", subject="Retard", draft_id="abc-123"))

        preserved = preserved_parameters_for_prompt(plan, "body")

        assert preserved == {"subject": "Retard"}, (
            "only user-provided content is worth restating; internal ids would "
            "invite the planner to reuse a resource from the previous attempt"
        )
