"""The repeated-output bench sees a loop and only a loop (lot 26): proven on its controls."""

from __future__ import annotations

import pytest

from scripts.agents.measure_repeated_output import flags, plain, shape

pytestmark = pytest.mark.unit

LINE_LOOP = "Intro of the answer here.\n" + "\n".join(
    ["Here is the full list of the meetings."] * 4
)
TAIL_LOOP = "A normal answer. " + "and then again the same loop with no end here " * 12
SENTENCE_LOOP = " ".join(["The dentist appointment is confirmed for tomorrow morning."] * 5)
CLEAN = "Hello. Here is your answer: three meetings tomorrow, one at the dentist at 10. Bye!"
TABLE = "| Day | Hour |\n|---|---|\n| Mon | 10 |\n| Tue | 11 |\n| Wed | 12 |\n| Thu | 13 |"


@pytest.mark.parametrize(
    ("text", "kind"),
    [(LINE_LOOP, "line_loop"), (TAIL_LOOP, "tail_loop"), (SENTENCE_LOOP, "sentence_repeat")],
)
def test_each_loop_is_seen(text: str, kind: str) -> None:
    assert kind in flags(text)


@pytest.mark.parametrize("text", [CLEAN, TABLE])
def test_ordinary_answers_are_not_flagged(text: str) -> None:
    assert flags(text) == []


def test_a_style_block_is_no_answer_text() -> None:
    styled = (
        "<style>.a{color:red}.a{color:red}.a{color:red}.a{color:red}.a{color:red}</style><p>Hi.</p>"
    )
    assert "color" not in plain(styled) and flags(styled) == []


def test_the_shape_reveals_no_word() -> None:
    dated = "".join(f"Item {n}. Wednesday 21 October 2026 · " for n in range(8))
    result = shape(dated)
    assert (
        "Wednesday" not in result
        and "October" not in result
        and result.endswith(tuple("x0123456789"))
    )
