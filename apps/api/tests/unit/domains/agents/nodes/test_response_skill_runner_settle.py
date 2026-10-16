"""A skill runner's settlement reads how the loop ended (ADR-303).

The runner catches a provider failure itself and hands back a result with no
message; that result used to reach ``settle_skill_runner`` with zero iterations
and be counted as « no tool called » — a failure filed as a model's choice.
"""

from __future__ import annotations

import pytest
from prometheus_client import REGISTRY

from src.domains.agents.nodes.response_skill_runner import (
    settle_skill_runner,
    settle_third_party_runner,
)
from src.domains.agents.tools.react_runner import ReactSubAgentResult, SubAgentOutcome


def _count(outcome: str) -> float:
    return REGISTRY.get_sample_value("skill_runner_outcomes_total", {"outcome": outcome}) or 0.0


@pytest.mark.unit
class TestTheScriptSkillRunner:
    def test_a_failure_the_runner_caught_is_an_error_never_a_silent_runner(self) -> None:
        errors, silent = _count("error"), _count("no_tool_call")
        sections: list[str] = []
        failed = ReactSubAgentResult(
            final_message="",
            messages=[],
            iteration_count=0,
            outcome=SubAgentOutcome.ERROR,
            failure_kind="timeout",
        )

        settled = settle_skill_runner(failed, "run-1", "board_game", "Play X.", sections)

        assert settled == (None, None, None)
        # The instructions reach the response the passive way, as for a raised failure.
        assert sections == ["Play X."]
        assert _count("error") == pytest.approx(errors + 1)
        assert _count("no_tool_call") == pytest.approx(silent)

    def test_a_run_that_said_nothing_after_its_scripts_yields_nothing(self) -> None:
        sections: list[str] = []
        empty = ReactSubAgentResult(
            final_message="", messages=[], iteration_count=2, outcome=SubAgentOutcome.EMPTY
        )

        assert settle_skill_runner(empty, "run-1", "board_game", "Play X.", sections) == (
            None,
            None,
            None,
        )
        assert sections == []

    def test_an_answer_written_by_the_closing_pass_is_the_answer(self) -> None:
        closed = ReactSubAgentResult(
            final_message="The board after twelve moves.",
            messages=[],
            iteration_count=12,
            closed_on_budget=True,
        )

        answer, react_result, _registry = settle_skill_runner(
            closed, "run-1", "board_game", "Play X.", []
        )

        assert answer == "The board after twelve moves."
        assert react_result == {
            "final_message": "The board after twelve moves.",
            "iteration_count": 12,
            "mode": "react",
        }


@pytest.mark.unit
def test_a_third_party_runner_that_failed_is_counted_as_an_error() -> None:
    errors = _count("error")
    failed = ReactSubAgentResult(
        final_message="", messages=[], outcome=SubAgentOutcome.ERROR, failure_kind="api_error"
    )

    assert settle_third_party_runner(failed, "run-1", "outside_skill") == (None, None, None)
    assert _count("error") == pytest.approx(errors + 1)
