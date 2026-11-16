"""The decision provider judges a request's shape for the automatic mode (ADR-390).

Four Noul questions, one call. The pipeline may plan the turn only when all four
properties are judged ABSENT at their margins; a property present, an undecided
answer, a missing one or any failure is a verdict for the loop.
"""

from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.domains.agents.services.analysis.jev_execution_mode import (
    judge_request_shape,
    property_absent,
    shape_verdict,
)
from src.domains.agents.services.engine_resolution import EngineReason
from src.infrastructure.llm.decision_types import DecisionAttempt
from src.infrastructure.llm.typesafe_client import NoulAnswer

pytestmark = pytest.mark.unit

_MODULE = "src.domains.agents.services.analysis.jev_execution_mode"


def _attempt(
    computed: float = 0.03,
    cross_check: float = 0.03,
    open_ended: float = 0.03,
    named_in_text: float = 0.03,
    *,
    outcome: str = "success",
    thresholds: dict[str, Decimal] | None = None,
) -> DecisionAttempt:
    nouls = {
        key: NoulAnswer(type="noul", noul=value)
        for key, value in (
            ("computed", computed),
            ("cross_check", cross_check),
            ("open_ended", open_ended),
            ("named_in_text", named_in_text),
        )
    }
    return DecisionAttempt(outcome=outcome, nouls=nouls, thresholds=thresholds or {})


class TestTheVerdict:
    def test_every_property_judged_absent_lets_the_pipeline_plan(self) -> None:
        assert shape_verdict(_attempt()) is EngineReason.DIRECT

    @pytest.mark.parametrize(
        ("scores", "reason"),
        [
            ({"computed": 0.95}, EngineReason.COMPUTED),
            ({"computed": 0.30}, EngineReason.COMPUTED),  # undecided at the 0.20 margin
            ({"cross_check": 0.87}, EngineReason.CROSS_CHECK),
            ({"cross_check": 0.51}, EngineReason.CROSS_CHECK),
            ({"open_ended": 0.88}, EngineReason.OPEN_ENDED),
            ({"named_in_text": 0.91}, EngineReason.NAMED_IN_TEXT),
        ],
    )
    def test_a_property_present_or_undecided_is_the_loop(
        self, scores: dict[str, float], reason: EngineReason
    ) -> None:
        assert shape_verdict(_attempt(**scores)) is reason

    @pytest.mark.parametrize(
        ("noul", "absent"),
        [(0.48, True), (0.49, False), (0.51, False), (0.52, False), (0.03, True)],
    )
    def test_a_property_is_absent_only_at_or_below_its_margin(
        self, noul: float, absent: bool
    ) -> None:
        """One door for « judged absent », read by the verdict and by the bench: at
        the 0.48 margin, 0.49-0.51 is undecided and 0.52 present."""
        assert property_absent({}, "named_in_text", noul) is absent

    def test_the_margins_the_operation_froze_are_read(self) -> None:
        """An administrator who narrowed a margin narrows the pipeline's lane."""
        attempt = _attempt(computed=0.15, thresholds={"computed": Decimal("0.10")})

        assert shape_verdict(attempt) is EngineReason.COMPUTED

    @pytest.mark.parametrize("outcome", ["disabled", "missing_key", "timeout", "failed"])
    def test_no_answer_is_no_decision(self, outcome: str) -> None:
        assert shape_verdict(_attempt(outcome=outcome)) is EngineReason.NO_DECISION

    def test_a_missing_answer_is_no_decision(self) -> None:
        attempt = _attempt()
        attempt.nouls.pop("cross_check")

        assert shape_verdict(attempt) is EngineReason.NO_DECISION


class TestTheJudgement:
    @pytest.fixture
    def tracker(self) -> SimpleNamespace:
        return SimpleNamespace(user_id="00000000-0000-4000-8000-000000000001", run_id="run-1")

    async def test_without_an_accountable_turn_nothing_is_asked(self) -> None:
        with (
            patch(f"{_MODULE}.current_tracker") as current,
            patch(f"{_MODULE}.choose_many_with_jev", AsyncMock()) as choose,
        ):
            current.get.return_value = None
            verdict = await judge_request_shape("Quels sont mes rendez-vous de demain ?")

        assert verdict is EngineReason.NO_DECISION
        choose.assert_not_awaited()

    async def test_the_request_is_asked_once_with_the_four_questions(
        self, tracker: SimpleNamespace
    ) -> None:
        with (
            patch(f"{_MODULE}.current_tracker") as current,
            patch(f"{_MODULE}.choose_many_with_jev", AsyncMock(return_value=_attempt())) as choose,
            patch(f"{_MODULE}.record_action", AsyncMock()),
            patch(f"{_MODULE}.count_jev_outcome") as counted,
        ):
            current.get.return_value = tracker
            verdict = await judge_request_shape("Quels sont mes rendez-vous de demain ?")

        assert verdict is EngineReason.DIRECT
        kwargs = choose.await_args.kwargs
        assert set(kwargs["questions"]) == {
            "computed",
            "cross_check",
            "open_ended",
            "named_in_text",
        }
        assert kwargs["state"] == {"request": "Quels sont mes rendez-vous de demain ?"}
        assert kwargs["run_id"] == "run-1"
        counted.assert_called_once()
        assert counted.call_args.args[1] == "direct"

    async def test_a_failure_of_the_provider_is_a_verdict_for_the_loop(
        self, tracker: SimpleNamespace
    ) -> None:
        with (
            patch(f"{_MODULE}.current_tracker") as current,
            patch(f"{_MODULE}.choose_many_with_jev", AsyncMock(side_effect=RuntimeError("down"))),
        ):
            current.get.return_value = tracker
            verdict = await judge_request_shape("Organise ma semaine.")

        assert verdict is EngineReason.NO_DECISION

    async def test_an_empty_request_is_never_sent(self, tracker: SimpleNamespace) -> None:
        with (
            patch(f"{_MODULE}.current_tracker") as current,
            patch(f"{_MODULE}.choose_many_with_jev", AsyncMock()) as choose,
        ):
            current.get.return_value = tracker
            verdict = await judge_request_shape("   ")

        assert verdict is EngineReason.NO_DECISION
        choose.assert_not_awaited()
