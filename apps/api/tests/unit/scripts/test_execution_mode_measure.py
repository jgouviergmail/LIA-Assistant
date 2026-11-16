"""The automatic mode's shape judgement bench (ADR-390): how a judgement is read,
counted and held to the corpus's declared acceptance — and that a run never
spends past its budget.

The provider is injected: no test reaches a network or a database.
"""

from __future__ import annotations

import json
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

from scripts.agents import measure_execution_mode as bench
from scripts.agents.execution_mode_corpus import (
    PROPERTIES,
    PROPERTY_ACCEPTANCE,
    Case,
    PropertyAcceptance,
    Split,
)
from src.domains.agents.services.analysis.jev_execution_mode import shape_questions
from src.domains.agents.services.engine_resolution import EngineReason
from src.infrastructure.llm.decision_types import DecisionAttempt, DecisionCharge
from src.infrastructure.llm.typesafe_client import NoulAnswer

pytestmark = pytest.mark.unit

ABSENT = {"computed": 0.02, "cross_check": 0.03, "open_ended": 0.04, "named_in_text": 0.05}


def _case(
    case_id: str,
    *,
    shape: str = "S",
    split: Split = "validation",
    cross_check: bool = False,
    named_in_text: bool = False,
    needs_loop: bool = False,
    ambiguous: bool = False,
) -> Case:
    return Case(
        case_id,
        split,
        "fr",
        shape,
        f"request {case_id}",
        cross_check=cross_check,
        named_in_text=named_in_text,
        needs_loop=needs_loop,
        ambiguous=ambiguous,
    )


def _judged(
    case_id: str,
    verdict: EngineReason,
    *,
    draw: int = 0,
    nouls: dict[str, float] | None = None,
) -> bench.Judgement:
    return bench.Judgement(
        case_id=case_id,
        draw=draw,
        outcome="success",
        nouls=dict(ABSENT) if nouls is None else nouls,
        verdict=verdict,
        cost_eur=0.0001,
        duration_ms=150.0,
    )


def _attempt(nouls: dict[str, float], *, outcome: str = "success") -> DecisionAttempt:
    return DecisionAttempt(
        outcome=outcome,
        nouls={key: NoulAnswer(type="noul", noul=value) for key, value in nouls.items()},
        charge=DecisionCharge(
            model="jev", input_tokens=10, output_tokens=3, cost_usd=0.0002, cost_eur=0.0002
        ),
    )


class TestAJudgementIsReadByTheProductionVerdict:
    def test_every_property_judged_absent_lets_the_pipeline_plan(self) -> None:
        assert bench.read_judgement(_attempt(ABSENT)) == (dict(ABSENT), EngineReason.DIRECT)

    def test_a_property_present_names_its_reason(self) -> None:
        _nouls, verdict = bench.read_judgement(_attempt({**ABSENT, "cross_check": 0.97}))
        assert verdict is EngineReason.CROSS_CHECK

    def test_a_missing_answer_or_a_failure_is_no_decision(self) -> None:
        assert bench.read_judgement(_attempt({"computed": 0.01}))[1] is EngineReason.NO_DECISION
        assert bench.read_judgement(_attempt({}, outcome="timeout"))[1] is EngineReason.NO_DECISION

    def test_the_margins_the_operation_froze_decide(self) -> None:
        # A margin gate concludes at or below its threshold (absent) or at or above one
        # minus it (present): 0.30 is undecided at the default 0.20, absent at 0.40.
        attempt = _attempt({**ABSENT, "computed": 0.30})
        assert bench.read_judgement(attempt)[1] is EngineReason.COMPUTED
        widened = DecisionAttempt(
            outcome="success", nouls=attempt.nouls, thresholds={"computed": Decimal("0.40")}
        )
        assert bench.read_judgement(widened)[1] is EngineReason.DIRECT


class TestTheReportCountsWhatTheCorpusDeclares:
    def test_the_pipeline_lane_counts_plannable_cases_judged_absent(self) -> None:
        cases = [_case("P1"), _case("P2")]
        rows = [_judged("P1", EngineReason.DIRECT), _judged("P2", EngineReason.COMPUTED)]

        split = bench.summarize(rows, cases)["validation"]

        assert (split.lane, split.plannable) == (1, 2)

    def test_a_needs_loop_case_judged_absent_is_a_leak_with_its_shape(self) -> None:
        cases = [_case("L1", shape="V", needs_loop=True, cross_check=True)]

        split = bench.summarize([_judged("L1", EngineReason.DIRECT)], cases)["validation"]

        assert split.leaks == [("L1", "V", 0)]

    def test_a_case_the_judgement_is_not_asked_about_is_left_to_the_analysis(self) -> None:
        # An act needs the loop, but no property says so: the router's analysis
        # sends it there before any judgement, so it is never the judgement's leak.
        cases = [_case("A1", shape="A", needs_loop=True)]

        split = bench.summarize([_judged("A1", EngineReason.DIRECT)], cases)["validation"]

        assert split.leaks == []
        assert split.left_to_analysis == [("A1", "A", 0)]

    def test_an_ambiguous_case_counts_neither_way(self) -> None:
        cases = [_case("A1", ambiguous=True, needs_loop=True)]

        split = bench.summarize([_judged("A1", EngineReason.DIRECT)], cases)["validation"]

        assert (split.lane, split.plannable, split.leaks) == (0, 0, [])

    def test_a_case_labelled_with_the_fourth_property_judged_absent_is_its_leak(self) -> None:
        cases = [_case("T1", shape="T", named_in_text=True, needs_loop=True)]

        split = bench.summarize([_judged("T1", EngineReason.DIRECT)], cases)["validation"]

        assert split.leaks == [("T1", "T", 0)]
        assert split.properties["named_in_text"].leaks == 1

    def test_the_separation_of_each_property_is_reported(self) -> None:
        """The margin is chosen on what separates the labelled cases from the
        plannable ones: the lowest labelled score, the highest plannable one."""
        cases = [
            _case("T1", shape="T", named_in_text=True, needs_loop=True),
            _case("T2", shape="T", named_in_text=True, needs_loop=True),
            _case("P1"),
        ]
        rows = [
            _judged("T1", EngineReason.NAMED_IN_TEXT, nouls={**ABSENT, "named_in_text": 0.93}),
            _judged("T2", EngineReason.NAMED_IN_TEXT, nouls={**ABSENT, "named_in_text": 0.71}),
            _judged("P1", EngineReason.DIRECT, nouls={**ABSENT, "named_in_text": 0.12}),
        ]

        separation = bench.summarize(rows, cases)["validation"].separation

        assert separation["named_in_text"] == (0.71, 0.12)
        assert separation["computed"] == (None, 0.02)

    def test_the_hard_negatives_count_the_property_s_own_judgement(self) -> None:
        """Another question may take a hard negative out of the lane; what the
        property answers for is its own judgement of it (the first round's lesson)."""
        acceptance = {"named_in_text": PropertyAcceptance(0, ("N1", "N2", "N3"), Fraction(5, 6))}
        cases = [_case("N1"), _case("N2"), _case("N3")]
        rows = [
            _judged("N1", EngineReason.DIRECT),
            _judged("N2", EngineReason.COMPUTED),  # out of the lane, the property absent
            _judged("N3", EngineReason.NAMED_IN_TEXT, nouls={**ABSENT, "named_in_text": 0.70}),
        ]

        split = bench.summarize(rows, cases, acceptance=acceptance)["validation"]

        count = split.properties["named_in_text"]
        assert (count.absent, count.lane, count.negatives) == (2, 1, 3)

    def test_the_margins_the_run_froze_decide_what_absent_means(self) -> None:
        acceptance = {"named_in_text": PropertyAcceptance(0, ("N1",), Fraction(5, 6))}
        rows = [_judged("N1", EngineReason.DIRECT, nouls={**ABSENT, "named_in_text": 0.45})]

        at_default = bench.summarize(rows, [_case("N1")], acceptance=acceptance)
        narrowed = bench.summarize(
            rows,
            [_case("N1")],
            acceptance=acceptance,
            thresholds={"named_in_text": Decimal("0.40")},
        )

        assert at_default["validation"].properties["named_in_text"].absent == 1
        assert narrowed["validation"].properties["named_in_text"].absent == 0

    def test_a_case_judged_differently_between_draws_is_unstable(self) -> None:
        cases = [_case("U1"), _case("S1")]
        rows = [
            _judged("U1", EngineReason.DIRECT, draw=0),
            _judged("U1", EngineReason.OPEN_ENDED, draw=1),
            _judged("S1", EngineReason.DIRECT, draw=0),
            _judged("S1", EngineReason.DIRECT, draw=1),
        ]

        assert bench.summarize(rows, cases)["validation"].unstable == ["U1"]


class TestTheDeclaredAcceptance:
    def test_one_leak_and_a_lane_of_half_pass(self) -> None:
        split = bench.SplitReport(lane=2, plannable=4, leaks=[("L1", "V", 0)])
        assert bench.failed_criteria({"validation": split}) == []

    def test_two_leaks_of_one_shape_fail(self) -> None:
        split = bench.SplitReport(lane=4, plannable=4, leaks=[("L1", "V", 0), ("L2", "V", 1)])
        assert bench.failed_criteria({"validation": split}) == [
            "validation: 2 needs-loop cases judged plannable (at most 1)",
            "validation: two leaks of shape V",
        ]

    def test_a_thin_lane_fails(self) -> None:
        split = bench.SplitReport(lane=1, plannable=4)
        assert bench.failed_criteria({"validation": split}) == [
            "validation: 1/4 plannable cases judged plannable (at least half)"
        ]

    def test_any_adversarial_leak_fails(self) -> None:
        split = bench.SplitReport(lane=1, plannable=1, leaks=[("X1", "I", 0)])
        assert bench.failed_criteria({"adversarial": split}) == [
            "adversarial: an instruction moved X1 to the pipeline"
        ]

    def test_a_property_declared_unforgiving_fails_on_one_leak(self) -> None:
        """The general bound allows one leak; the fourth property declared none."""
        acceptance = {"named_in_text": PropertyAcceptance(0, (), Fraction(5, 6))}
        split = bench.SplitReport(
            lane=4,
            plannable=4,
            leaks=[("T1", "T", 0)],
            properties={"named_in_text": bench.PropertyCount(leaks=1)},
        )

        assert bench.failed_criteria({"validation": split}, acceptance=acceptance) == [
            "validation: 1 draw(s) labelled named_in_text judged plannable (at most 0)"
        ]

    def test_hard_negatives_judged_present_too_often_fail(self) -> None:
        acceptance = {"named_in_text": PropertyAcceptance(0, ("N1",), Fraction(5, 6))}
        split = bench.SplitReport(
            lane=4,
            plannable=4,
            properties={"named_in_text": bench.PropertyCount(absent=4, negatives=6)},
        )

        assert bench.failed_criteria({"validation": split}, acceptance=acceptance) == [
            "validation: named_in_text judged absent on 4/6 draws of its hard negatives "
            "(at least 5/6)"
        ]


class TestTheCorpusMatchesTheJudgement:
    def test_the_properties_are_the_questions_in_the_verdict_s_order(self) -> None:
        """A property the corpus labels but nobody asks is a leak nobody can see."""
        assert tuple(shape_questions()) == PROPERTIES

    def test_every_declared_acceptance_names_a_property_and_real_cases(self) -> None:
        from scripts.agents.execution_mode_corpus import CASES

        by_id = {case.case_id: case for case in CASES}
        for name, acceptance in PROPERTY_ACCEPTANCE.items():
            assert name in PROPERTIES
            for case_id in acceptance.hard_negatives:
                negative = by_id[case_id]
                assert negative.split == "validation", case_id
                assert not negative.needs_loop and not negative.ambiguous, case_id


class TestTheRowsCanBeKeptForCalibration:
    def test_each_judgement_is_one_json_line_of_facts(self, tmp_path: Path) -> None:
        target = tmp_path / "rows.jsonl"

        bench.write_rows([_judged("C1", EngineReason.DIRECT)], target)

        (line,) = target.read_text(encoding="utf-8").splitlines()
        assert json.loads(line) == {
            "case_id": "C1",
            "draw": 0,
            "outcome": "success",
            "nouls": ABSENT,
            "verdict": "direct",
            "cost_eur": 0.0001,
            "duration_ms": 150.0,
        }


class TestARunNeverSpendsPastItsBudget:
    async def test_it_stops_once_the_budget_is_spent(self) -> None:
        asked: list[str] = []

        async def ask(request: str) -> DecisionAttempt:
            asked.append(request)
            return _attempt(ABSENT)

        cases = [_case(f"C{index}") for index in range(5)]
        rows = await bench.run(cases, draws=1, ask=ask, budget_eur=0.0005)

        # Each call costs €0.0002: the third reaches the budget and the run stops there.
        assert len(asked) == 3
        assert [row.case_id for row in rows] == ["C0", "C1", "C2"]

    async def test_every_draw_asks_every_case(self) -> None:
        async def ask(request: str) -> DecisionAttempt:
            return _attempt(ABSENT)

        rows = await bench.run([_case("C0"), _case("C1")], draws=2, ask=ask, budget_eur=1.0)

        assert [(row.case_id, row.draw) for row in rows] == [
            ("C0", 0),
            ("C1", 0),
            ("C0", 1),
            ("C1", 1),
        ]
