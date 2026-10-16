"""The clock the linearity guards read: precise below a tick, and blind to waiting."""

from __future__ import annotations

import time

import pytest

from tests.support.thread_clock import thread_time

pytestmark = pytest.mark.unit

#: Shorter than one Windows scheduler tick (15.6 ms), the step ``GetThreadTimes``
#: moves by: a tick clock reads such a span as nothing or as a whole tick (×3.9).
SPAN_SECONDS = 0.004
#: How far above the wall a precise clock may read the span. The cycle counter's
#: unit is calibrated, and on a saturated host it read 4.11 ms over 4.00 ms
#: (2026-10-16); a guard judges ratios, which a constant unit leaves untouched.
TOLERANCE = 1.25


def _busy(seconds: float) -> tuple[float, float]:
    """Spin for ``seconds`` of wall time; return the CPU read and the wall elapsed."""
    started_cpu, started = thread_time(), time.perf_counter()
    while (elapsed := time.perf_counter() - started) < seconds:
        pass
    return thread_time() - started_cpu, elapsed


def test_a_span_shorter_than_a_tick_reads_its_own_cost() -> None:
    """Neither nothing nor a whole tick: what ran, and never more than the span."""
    for _ in range(5):
        cpu, wall = _busy(SPAN_SECONDS)
        assert 0 < cpu <= wall * TOLERANCE, f"{cpu * 1000:.2f} ms of CPU over {wall * 1000:.2f} ms"


def test_waiting_is_not_work() -> None:
    """A descheduled thread spends nothing: the load of a busy host is not the code's."""
    started = thread_time()
    time.sleep(0.05)
    spent = thread_time() - started
    assert spent < 0.005, f"{spent * 1000:.1f} ms of CPU read over 50 ms asleep"
