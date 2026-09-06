"""What the catalogue publishes about a spoken schedule, and to whom.

Two rules, both paid for elsewhere in this codebase:

- **A bound the planner cannot see is a trap** (ADR-184): `max_results` was
  capped at 10 while the planner only ever saw `required: false`, so the model
  sized batches from the prompt, the validator rejected the plan for obeying
  it, and the response layer reported that verdict as a failure.
- **What is mechanically repairable is repaired**, not reported: an
  out-of-bounds number is clamped before validation, and only what cannot be
  repaired without inventing intent stays an error.

The bounds are per CONSUMER. A routine runs an agent pipeline and gets 12
firings a day; a reminder sends a notification and gets 48. Publishing one
number for both would make one of them wrong.
"""

from __future__ import annotations

import inspect

import pytest

from src.core.constants import RECURRENCE_REMINDER_LIMITS, RECURRENCE_ROUTINE_LIMITS
from src.core.recurrence import REPEAT_VALUES
from src.domains.agents.registry.recurrence_parameters import (
    RECURRENCE_DOCS,
    recurrence_parameters,
)
from src.domains.agents.services.planner.parameter_bounds import clamp_to_parameter_schema

pytestmark = pytest.mark.unit

ROUTINE = {
    p.name: p for p in recurrence_parameters(RECURRENCE_ROUTINE_LIMITS, repeat_required=True)
}
REMINDER = {
    p.name: p for p in recurrence_parameters(RECURRENCE_REMINDER_LIMITS, repeat_required=False)
}


class TestTheBoundsAreTheConsumersOwn:
    def test_a_reminder_may_step_faster_than_a_routine(self) -> None:
        assert _minimum(REMINDER["every_minutes"]) < _minimum(ROUTINE["every_minutes"])

    def test_a_reminder_may_fire_more_times_a_day(self) -> None:
        assert _maximum(REMINDER["times"]) > _maximum(ROUTINE["times"])

    def test_a_reminder_may_hold_a_longer_series(self) -> None:
        assert _maximum(REMINDER["max_occurrences"]) > _maximum(ROUTINE["max_occurrences"])

    def test_the_published_numbers_are_the_enforced_ones(self) -> None:
        """Not an approximation of them: the same object built them."""
        assert _minimum(ROUTINE["every_minutes"]) == RECURRENCE_ROUTINE_LIMITS.min_step_minutes
        assert _maximum(ROUTINE["times"]) == RECURRENCE_ROUTINE_LIMITS.max_times_per_day
        assert _maximum(ROUTINE["max_occurrences"]) == RECURRENCE_ROUTINE_LIMITS.max_series_count
        assert _minimum(REMINDER["every_minutes"]) == RECURRENCE_REMINDER_LIMITS.min_step_minutes
        assert _maximum(REMINDER["times"]) == RECURRENCE_REMINDER_LIMITS.max_times_per_day
        assert _maximum(REMINDER["max_occurrences"]) == RECURRENCE_REMINDER_LIMITS.max_series_count


class TestOutOfBoundsIsRepairedNotReported:
    """Measured 2026-09-06 through the planner's own clamp."""

    @pytest.mark.parametrize(
        ("name", "given", "expected", "table"),
        [
            ("every_minutes", 5, 15, "routine"),
            ("every_minutes", 1, 5, "reminder"),
            ("repeat_every", 0, 1, "routine"),
            ("max_occurrences", 900, 500, "routine"),
            ("max_occurrences", 5000, 1000, "reminder"),
        ],
    )
    def test_a_number_outside_its_bound_is_clamped(
        self, name: str, given: int, expected: int, table: str
    ) -> None:
        schema = (ROUTINE if table == "routine" else REMINDER)[name]
        assert clamp_to_parameter_schema(schema, given) == expected

    def test_a_value_inside_its_bound_is_untouched(self) -> None:
        assert clamp_to_parameter_schema(ROUTINE["every_minutes"], 30) == 30


class TestWhatTheModelIsAllowedToSay:
    def test_the_frequency_is_a_closed_set_and_it_is_published(self) -> None:
        """An enum the validator enforces must reach the planner (ADR-226)."""
        values = [c.value for c in ROUTINE["repeat"].constraints if c.kind == "enum"]
        assert values == [list(REPEAT_VALUES)]

    def test_every_shaped_parameter_publishes_its_shape(self) -> None:
        """A pattern the translation applies, the planner can read."""
        for name in ("nth_weekday", "window_start", "window_end", "until_date", "starting_on"):
            patterns = [c.value for c in ROUTINE[name].constraints if c.kind == "pattern"]
            assert patterns, name

    def test_the_published_patterns_are_the_ones_the_translation_accepts(self) -> None:
        """Publishing a DIFFERENT shape is worse than publishing none: the
        planner would obey a contract the translation refuses."""
        from src.core.recurrence import CLOCK_PATTERN, DATE_PATTERN, NTH_WEEKDAY_PATTERN

        def pattern_of(name: str) -> str:
            return next(c.value for c in ROUTINE[name].constraints if c.kind == "pattern")

        assert pattern_of("window_start") == CLOCK_PATTERN
        assert pattern_of("until_date") == DATE_PATTERN
        assert pattern_of("nth_weekday") == NTH_WEEKDAY_PATTERN


class TestTheDeclarationIsShared:
    """One vocabulary for both tools, or they become dialects."""

    def test_both_tools_take_every_declared_parameter(self) -> None:
        from src.domains.agents.tools.automation_tools import create_scheduled_action_tool
        from src.domains.agents.tools.reminder_tools import create_reminder_tool

        for tool in (create_scheduled_action_tool, create_reminder_tool):
            signature = inspect.signature(tool.coroutine)  # type: ignore[arg-type]
            missing = set(RECURRENCE_DOCS) - set(signature.parameters)
            assert not missing, f"{tool.name}: {sorted(missing)}"

    def test_the_frequency_is_required_only_where_it_is_the_subject(self) -> None:
        """A routine IS a schedule; a reminder may also be a single instant."""
        assert ROUTINE["repeat"].required is True
        assert REMINDER["repeat"].required is False

    def test_every_parameter_carries_the_shared_description(self) -> None:
        for name, doc in RECURRENCE_DOCS.items():
            assert ROUTINE[name].description == doc


def _minimum(schema) -> int:
    return next(c.value for c in schema.constraints if c.kind == "minimum")


def _maximum(schema) -> int:
    return next(c.value for c in schema.constraints if c.kind in ("maximum", "max_length"))


class TestAnUnclearRhythmIsAskedAboutNotGuessed:
    """Test 30 of the design's test plan, made checkable.

    "Remind me often" names no frequency. Choosing one silently commits the
    reader to a rhythm they never asked for, on a capability that then acts by
    itself every day until they notice — the failure mode is not a wrong
    answer, it is an unnoticed one.

    What is verifiable HERE is that the instruction reaches the producer, on
    both tools and in both execution modes: a rule the model cannot see is a
    rule it cannot follow (ADR-184). Whether a given model then obeys it is a
    MEASUREMENT, and it belongs to `task recurrence:corpus:measure` — never to
    an assertion in this file, which would pin a provider's behaviour.
    """

    def test_the_instruction_is_published_to_both_tools(self) -> None:
        assert "ASK the reader" in ROUTINE["repeat"].description
        assert "ASK the reader" in REMINDER["repeat"].description

    def test_it_names_the_wordings_that_carry_no_rhythm(self) -> None:
        described = RECURRENCE_DOCS["repeat"]
        for vague in ("often", "from time to time", "regularly"):
            assert vague in described

    def test_the_tool_signatures_carry_it_too(self) -> None:
        """The manifest feeds the planner; the signature feeds ReAct. A rule
        present in one and absent from the other is a rule that applies in one
        execution mode only."""
        import typing

        from src.domains.agents.tools.automation_tools import create_scheduled_action_tool
        from src.domains.agents.tools.reminder_tools import create_reminder_tool

        for tool in (create_scheduled_action_tool, create_reminder_tool):
            hints = typing.get_type_hints(tool.coroutine, include_extras=True)  # type: ignore[arg-type]
            metadata = " ".join(str(m) for m in getattr(hints["repeat"], "__metadata__", ()))
            assert "ASK the reader" in metadata, tool.name
