"""The judge-read oracle of the automatic mode's end-to-end replay (ADR-390).

The keyword oracle counted a fact as stated when its words appeared anywhere: read
by a person on 2026-11-15, it scored « I could not find the day » above a forecast
naming it (E06) and « no reminder that day » above that very reminder (E08) as
complete. A judge now reads each fact; these tests hold what the judge is given,
how its verdict is read, and that every end-to-end fact the keywords check has
its sentence.
"""

from __future__ import annotations

from datetime import date

import pytest

from scripts.agents import execution_mode_oracle as oracle
from scripts.agents.execution_mode_corpus import E2E

pytestmark = pytest.mark.unit


class TestTheFactsMatchTheKeywordOracle:
    def test_every_end_to_end_case_has_one_sentence_per_keyword_fact(self) -> None:
        for case in E2E:
            assert len(oracle.FACTS.get(case.case_id, ())) == len(case.oracle), case.case_id

    def test_no_sentence_outlives_its_case(self) -> None:
        assert set(oracle.FACTS) <= {case.case_id for case in E2E}


class TestTheRunDayIsRendered:
    def test_a_day_offset_reads_as_its_date_and_weekday(self) -> None:
        assert (
            oracle.render("the books are due on {day+2}", date(2026, 11, 15))
            == "the books are due on 2026-11-17 (Tuesday)"
        )

    def test_a_sentence_without_a_day_is_left_as_it_is(self) -> None:
        assert oracle.render("Bastien Roux is the captain", date(2026, 11, 15)) == (
            "Bastien Roux is the captain"
        )


class TestTheVerdictIsReadNeverGuessed:
    def test_one_digit_per_fact(self) -> None:
        assert oracle.read_verdict("1 0 1", 3) == (True, False, True)

    def test_a_verdict_with_the_wrong_count_is_unreadable(self) -> None:
        assert oracle.read_verdict("1 0", 3) is None

    def test_anything_but_digits_is_unreadable(self) -> None:
        assert oracle.read_verdict("yes no yes", 3) is None

    def test_spaces_and_a_trailing_line_are_tolerated(self) -> None:
        assert oracle.read_verdict(" 1  1\n", 2) == (True, True)


def test_the_judge_reads_the_request_the_answer_and_numbered_facts() -> None:
    case = next(case for case in E2E if case.case_id == "E08")

    request = oracle.judge_request(case, "Le ticket est dû mardi.", date(2026, 11, 15))

    assert case.text in request
    assert "Le ticket est dû mardi." in request
    assert "1. " in request and "2. " in request
    assert "2026-11-17 (Tuesday)" in request
