"""The message-timestamp bench (lot 17): its corpus, the two arms, and how an answer is read."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from scripts.agents import measure_message_timestamps as bench

pytestmark = pytest.mark.unit

#: A zone away from UTC: a stamp proven in UTC proves nothing about a person's clock.
ZONE = ZoneInfo("Asia/Tokyo")
NOW = datetime(2026, 11, 13, 9, 30, tzinfo=UTC)


def test_the_corpus_measures_time_and_keeps_controls() -> None:
    timed = [scenario for scenario in bench.CORPUS if scenario.time_bound]
    controls = [scenario for scenario in bench.CORPUS if not scenario.time_bound]

    assert len(timed) >= 6 and len(controls) >= 3
    assert len({scenario.key for scenario in bench.CORPUS}) == len(bench.CORPUS)
    for scenario in bench.CORPUS:
        assert scenario.history, scenario.key
        assert scenario.expected in {"YES", "NO"} or scenario.expected.isdigit(), scenario.key
        # Every message was written before the question is asked.
        assert all(said.ago > timedelta(0) for said in scenario.history), scenario.key


def test_both_answers_are_expected_somewhere_so_a_constant_answer_cannot_win() -> None:
    verdicts = {scenario.expected for scenario in bench.CORPUS if scenario.time_bound}

    assert {"YES", "NO"} <= verdicts


def test_a_stamp_is_the_wall_time_in_the_persons_zone() -> None:
    sent = datetime(2026, 11, 10, 0, 12, tzinfo=UTC)  # 09:12 in Tokyo

    assert bench.stamp("Hello", sent, ZONE) == "[Tue 10 Nov 2026, 09:12] Hello"


def test_the_plain_arm_is_the_history_as_production_sends_it() -> None:
    scenario = bench.CORPUS[0]

    messages = bench.history_messages(scenario, now=NOW, zone=ZONE, stamped=False)

    assert [type(message) for message in messages] == [
        HumanMessage if said.role == "person" else AIMessage for said in scenario.history
    ]
    assert [message.content for message in messages] == [said.text for said in scenario.history]


def test_the_stamped_arm_prefixes_each_message_with_when_it_was_written() -> None:
    scenario = bench.CORPUS[0]

    messages = bench.history_messages(scenario, now=NOW, zone=ZONE, stamped=True)

    for message, said in zip(messages, scenario.history, strict=True):
        assert message.content == bench.stamp(said.text, NOW - said.ago, ZONE)


def test_the_person_arm_stamps_only_the_persons_messages() -> None:
    """Production's variant: a turn begins with the person; LIA's answer follows at once."""
    scenario = bench.CORPUS[0]

    messages = bench.history_messages(scenario, now=NOW, zone=ZONE, stamped="person")

    for message, said in zip(messages, scenario.history, strict=True):
        expected = (
            bench.stamp(said.text, NOW - said.ago, ZONE) if said.role == "person" else said.text
        )
        assert message.content == expected
    assert bench.ARMS == ("plain", "stamped", "stamped_person", "stamped_person_now")


def test_the_production_arm_stamps_the_current_question_with_the_present() -> None:
    """Production stamps the question too: its bytes must not change once earlier."""
    scenario = bench.CORPUS[0]

    question = bench.current_question(scenario, now=NOW, zone=ZONE, arm="stamped_person_now")

    assert question.content == bench.stamp(scenario.question, NOW, ZONE)
    for arm in ("plain", "stamped", "stamped_person"):
        plain = bench.current_question(scenario, now=NOW, zone=ZONE, arm=arm)
        assert plain.content == scenario.question


def test_the_stamped_arm_alone_says_what_the_stamps_are() -> None:
    plain = bench.system_prompt(NOW, ZONE, stamped=False)
    stamped = bench.system_prompt(NOW, ZONE, stamped=True)

    # Both know the present, as production's <TemporalContext> does.
    assert "Fri 13 Nov 2026, 18:30" in plain and "Fri 13 Nov 2026, 18:30" in stamped
    assert bench.STAMP_SENTENCE not in plain
    assert bench.STAMP_SENTENCE in stamped
    # The person arm says it the way production would: SOME earlier messages carry one.
    person = bench.system_prompt(NOW, ZONE, stamped="person")
    assert bench.PERSON_STAMP_SENTENCE in person and bench.STAMP_SENTENCE not in person
    # Production's arm stamps the question too, and says so: no « current has none ».
    production = bench.system_prompt(NOW, ZONE, stamped="person", question_stamped=True)
    assert bench.PRODUCTION_STAMP_SENTENCE in production
    assert bench.PERSON_STAMP_SENTENCE not in production


@pytest.mark.parametrize(
    ("answer", "verdict"),
    [
        ("YES — it is still ahead of you.", "YES"),
        ("No. It took place on Tuesday.", "NO"),
        ("**No**, that was two days ago.", "NO"),
        ("4 days ago, on Monday.", "4"),
        ("It was 3 days ago.", "3"),
        ("I cannot tell from what you told me.", None),
        ("", None),
    ],
)
def test_an_answer_is_read_by_its_first_verdict(answer: str, verdict: str | None) -> None:
    assert bench.verdict(answer) == verdict


def test_the_tally_splits_time_bound_questions_from_the_controls() -> None:
    timed = next(scenario for scenario in bench.CORPUS if scenario.time_bound)
    control = next(scenario for scenario in bench.CORPUS if not scenario.time_bound)
    rows = [
        bench.Outcome("family", "stamped", timed.key, timed.expected, timed.expected),
        bench.Outcome("family", "stamped", control.key, None, control.expected),
        bench.Outcome("family", "plain", timed.key, "999", timed.expected),
    ]

    tally = bench.tally(rows)

    assert tally[("family", "stamped")] == {"time_bound": (1, 1), "controls": (0, 1)}
    assert tally[("family", "plain")] == {"time_bound": (0, 1), "controls": (0, 0)}


def test_a_run_can_ask_some_arms_and_refuses_an_unknown_one() -> None:
    assert bench.chosen_arms(None) == bench.ARMS
    assert bench.chosen_arms("plain,stamped_person_now") == ("plain", "stamped_person_now")
    with pytest.raises(SystemExit):
        bench.chosen_arms("plain,everything")
