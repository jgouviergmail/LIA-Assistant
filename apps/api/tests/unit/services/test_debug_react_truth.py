"""What the panel says about a ReAct loop, and what actually governed it (B8, lot 7.2).

The section published `max_iterations = settings.react_agent_max_iterations` —
the hard CEILING — while the loop stops at `react_iteration_budget(state)`: the
ADR-238 domain-span allowance, extended block by block while the loop keeps
bringing results back (ADR-248). **The bound shown was not the bound enforced**,
which is exactly the trap ADR-184 exists to close, applied to the panel itself:
a reader saw « 4/25 » on a turn that stopped at 4 because its budget WAS 4, and
concluded the model had given up.

Three more things the loop knows and the panel could not say:

- **why it stopped.** `react_exit_reason` is THE predicate, resolved once in
  `react_finalize_node` and carried in the truncation; the panel showed
  iterations and left the reader to guess.
- **what it spent productively.** The extension is bought with results, so the
  productive count is what explains a budget that grew.
- **which capabilities it asked for and never got.** The abandoned calls were
  written to a log line and nowhere a person reading the panel could see them.
"""

from __future__ import annotations

import pytest

from src.domains.agents.services.streaming import debug_metrics_stages as stages

pytestmark = pytest.mark.unit


def _react(state: dict) -> dict:
    """The section this state produces."""
    payload: dict = {}
    stages.build_react_execution(payload, {"execution_mode": "react", **state})
    return payload["react_execution"]


class TestTheBoundShownIsTheBoundEnforced:
    def test_it_publishes_the_EFFECTIVE_budget_not_only_the_ceiling(self) -> None:
        from src.core.config import get_settings

        # ADR-238 narrowed this turn to four iterations; the ceiling is far
        # higher and did not stop anything.
        react = _react({"react_iteration": 4, "react_max_iterations_effective": 4})

        assert react["iteration_budget"] == 4
        assert react["iteration_ceiling"] == get_settings().react_agent_max_iterations

    def test_the_starting_allowance_is_named_beside_the_budget(self) -> None:
        # A budget of 8 that started at 4 is a loop that EARNED four more; the
        # two numbers together are the whole story, either alone is half of it.
        react = _react(
            {
                "react_iteration": 5,
                "react_max_iterations_effective": 4,
                "react_productive_iterations": 5,
            }
        )

        assert react["starting_budget"] == 4
        assert react["productive_iterations"] == 5
        assert react["iteration_budget"] >= 4

    def test_an_unnarrowed_turn_is_bounded_by_the_ceiling(self) -> None:
        from src.core.config import get_settings

        ceiling = get_settings().react_agent_max_iterations
        react = _react({"react_iteration": 2})

        # No ADR-238 value: the fallback IS the ceiling, and the section says so
        # rather than leaving `starting_budget` at a number nobody chose.
        assert react["iteration_budget"] == ceiling
        assert react["starting_budget"] == ceiling

    def test_the_budget_never_exceeds_the_ceiling(self) -> None:
        from src.core.config import get_settings

        ceiling = get_settings().react_agent_max_iterations
        react = _react(
            {
                "react_iteration": 99,
                "react_max_iterations_effective": ceiling,
                "react_productive_iterations": 999,
            }
        )

        assert react["iteration_budget"] <= ceiling


class TestWhyTheLoopStopped:
    def test_a_loop_that_ran_out_of_iterations_says_so(self) -> None:
        react = _react(
            {
                "react_iteration": 4,
                "react_agent_result": {"truncation": {"reason": "max_iterations", "iterations": 4}},
            }
        )

        assert react["exit_reason"] == "max_iterations"

    @pytest.mark.parametrize("reason", ["compute_budget", "tool_budget", "pending_tool_calls"])
    def test_every_stop_condition_reaches_the_panel_verbatim(self, reason: str) -> None:
        # Named separately on purpose: reporting a delegated overrun as
        # `compute_budget` tells the reader the model thought too long when a
        # sub-agent did (ADR-182's invented diagnosis, pointing the other way).
        react = _react(
            {"react_iteration": 1, "react_agent_result": {"truncation": {"reason": reason}}}
        )

        assert react["exit_reason"] == reason

    def test_a_loop_that_finished_on_its_own_says_answered(self) -> None:
        # No truncation is not « unknown »: the model stopped calling tools,
        # which is the loop ending the way it is meant to.
        react = _react({"react_iteration": 3, "react_agent_result": {"iteration_count": 3}})

        assert react["exit_reason"] == "answered"

    def test_a_turn_with_no_result_at_all_claims_nothing(self) -> None:
        # An interrupted turn never reaches the finalize node. Saying
        # « answered » there would be a claim nobody verified.
        react = _react({"react_iteration": 2})

        assert react["exit_reason"] is None


class TestWhatTheLoopAskedForAndNeverGot:
    def test_the_abandoned_calls_are_named(self) -> None:
        react = _react(
            {
                "react_iteration": 4,
                "react_agent_result": {
                    "truncation": {"reason": "max_iterations"},
                    "abandoned_calls": ["get_emails_tool", "get_events_tool"],
                },
            }
        )

        # The signal that says whether the budget is CALIBRATED, not merely
        # that it was hit.
        assert react["abandoned_calls"] == ["get_emails_tool", "get_events_tool"]

    def test_a_loop_that_abandoned_nothing_carries_an_empty_list(self) -> None:
        # An empty list, never a missing key: the section's rows must not
        # disagree about what a row is.
        react = _react({"react_iteration": 3, "react_agent_result": {"iteration_count": 3}})

        assert react["abandoned_calls"] == []


class TestTheSectionStillSaysWhatItSaidBefore:
    def test_the_existing_figures_are_untouched(self) -> None:
        react = _react(
            {
                "react_iteration": 3,
                "react_tool_names": ["get_emails_tool"],
                "react_elapsed_seconds": 12.5,
                "react_tool_seconds": 4.0,
                "react_call_digests": {"a": 1, "b": 2},
            }
        )

        assert react["iterations"] == 3
        assert react["elapsed_seconds"] == 12.5
        assert react["tool_seconds"] == 4.0
        assert react["tool_names"] == ["get_emails_tool"]
        assert react["executed_tool_calls"] == 2

    def test_a_pipeline_turn_still_draws_no_section_at_all(self) -> None:
        payload: dict = {}
        stages.build_react_execution(payload, {"execution_mode": "pipeline"})

        assert "react_execution" not in payload
