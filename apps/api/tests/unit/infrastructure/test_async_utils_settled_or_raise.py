"""Reading a gather whose siblings all settled (briefing fresh review B3)."""

from __future__ import annotations

import pytest

from src.infrastructure.async_utils import settled_or_raise

pytestmark = pytest.mark.unit


def test_every_answer_comes_back_in_its_order() -> None:
    assert settled_or_raise(["a", None, 3]) == ["a", None, 3]


def test_the_first_failure_is_raised_as_it_was() -> None:
    first, second = ValueError("first"), KeyError("second")

    with pytest.raises(ValueError) as raised:
        settled_or_raise(["a", first, second])

    assert raised.value is first


def test_a_quiet_position_reads_its_failure_as_nothing() -> None:
    assert settled_or_raise(["a", RuntimeError("extras")], quiet={1}) == ["a", None]


def test_a_quiet_failure_never_hides_a_loud_one() -> None:
    loud = TimeoutError("weather")

    with pytest.raises(TimeoutError):
        settled_or_raise([RuntimeError("extras"), loud], quiet={0})
