"""The one CPU growth measurement the linearity guards share is a measurement (audit A12).

Three guards (the text flatteners, the machine-tag filter, the compaction's URL trimming)
each carried their own copy of « ×4 the input, at most ×8 the CPU »; one of them timed a
single call per size on ``time.thread_time``, which Windows advances by 15.6 ms ticks, so
a 9 ms call read 0 or 15.6 ms and its ratio was noise. ``tests.support.cpu_growth`` is now
the one measurement: these tests pin its arithmetic on a scripted clock, prove it reads the
thread's cycle-precise clock, and prove it can fail — a criterion no quadratic function
fails proves nothing.
"""

from __future__ import annotations

import pytest

from tests.support import cpu_growth
from tests.support.cpu_growth import (
    FLOOR_SECONDS,
    MAX_GROWTH,
    SMALL_FLOOR_SECONDS,
    measure_growth,
)

pytestmark = pytest.mark.unit


class _ScriptedClock:
    """A thread clock that moves only when the measured work says so."""

    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _scripted(monkeypatch: pytest.MonkeyPatch) -> _ScriptedClock:
    clock = _ScriptedClock()
    monkeypatch.setattr(cpu_growth, "thread_time", clock)
    return clock


def test_a_linear_cost_reads_four_times_on_four_times_the_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = _scripted(monkeypatch)

    def work(size: int) -> None:
        clock.now += size * 1e-3  # one millisecond of the thread's CPU per unit

    growth = measure_growth(work, 10, 40, batch=4)

    assert growth.small == pytest.approx(0.010) and growth.large == pytest.approx(0.040)
    assert growth.judged and growth.ratio == pytest.approx(4.0) and growth.linear


def test_a_quadratic_cost_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _scripted(monkeypatch)

    def work(size: int) -> None:
        clock.now += size**2 * 1e-5

    growth = measure_growth(work, 20, 80)

    assert growth.judged and growth.ratio > MAX_GROWTH and not growth.linear


def test_a_cost_under_the_floor_is_not_judged(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sub-floor ratios are noise: they pass, and say they were not judged."""
    clock = _scripted(monkeypatch)

    def work(size: int) -> None:
        clock.now += size**2 * 1e-9

    growth = measure_growth(work, 20, 80)

    assert growth.large < FLOOR_SECONDS and not growth.judged and growth.linear


def test_the_small_size_is_read_as_at_least_its_floor(monkeypatch: pytest.MonkeyPatch) -> None:
    clock = _scripted(monkeypatch)

    def work(size: int) -> None:
        clock.now += 1e-6 if size == 1 else 0.03

    growth = measure_growth(work, 1, 4)

    assert growth.ratio == pytest.approx(0.03 / SMALL_FLOOR_SECONDS)


def test_the_median_pair_decides_whatever_one_pair_read(monkeypatch: pytest.MonkeyPatch) -> None:
    """One pair a change of load stretched does not make a linear cost quadratic."""
    clock = _scripted(monkeypatch)
    calls: list[int] = []

    def work(size: int) -> None:
        calls.append(size)
        stretched = len(calls) == 2  # the first large call meets a busy host
        clock.now += size * 1e-3 * (10 if stretched else 1)

    growth = measure_growth(work, 10, 40)

    assert growth.ratio == pytest.approx(4.0)


def test_the_measure_reads_the_thread_clock_of_the_support_module() -> None:
    """The cycle-precise clock, never ``time.thread_time``'s scheduler ticks."""
    from tests.support import thread_clock

    assert cpu_growth.thread_time is thread_clock.thread_time


def test_a_real_quadratic_function_is_refused_on_the_real_clock() -> None:
    """Sized so its SMALL run clears the small floor too (measured: 5.8 ms → 119 ms).

    Under that floor the small run is read as the floor itself, so a quadratic function
    starting below it is refused only once its large run reaches ×16 the floor: at
    1.5 ms → 26.5 ms the criterion read ×5.3, a pass.
    """

    def quadratic(items: list[int]) -> int:
        total = 0
        for left in items:
            for right in items:
                total += left ^ right
        return total

    growth = measure_growth(quadratic, list(range(600)), list(range(2_400)))

    assert growth.small >= SMALL_FLOOR_SECONDS, "the control's small run fell under its floor"
    assert growth.judged and not growth.linear, f"the criterion is blind: {growth.describe()}"
