"""How much more a function costs on four times its input, on the thread's CPU (ADR-326).

The linearity guards run a function at n and at 4n and judge the RATIO: linear work
grows ×4, quadratic ×16, and a function may take at most ``MAX_GROWTH`` times longer.
Three guards carried their own copy of that measurement until one of them, timing a
single call per size on ``time.thread_time``, judged noise: Windows advances that clock
by 15.6 ms ticks, so a 9 ms call read 0 or 15.6 ms (audit A12). This is the one copy.

What makes the ratio a measurement, each part paid for by a false verdict:

- **the thread's CPU, never the wall** (``tests.support.thread_clock``, precise on
  every host): a host busy with the parallel suite deschedules the thread, and a wall
  clock counts the wait as work;
- **interleaved pairs, the median pair decides**: three small and three large runs
  taken in turn, so a change of load meets both sizes and one stretched pair is
  outvoted — measured one size after the other, with every core saturated, the
  minima of a quadratic filter read ×5.4 at worst, under the ×8 it must fail
  (2026-10-16);
- **floors**: under ``FLOOR_SECONDS`` at the large size the ratio is noise and is not
  judged; the small size is read as at least ``SMALL_FLOOR_SECONDS``, from which a
  quadratic function still takes ×16, twice what the criterion admits — so a witness
  whose small run falls under that floor judges a quadratic function only once its
  large run reaches sixteen floors (measured: 1.5 ms → 26.5 ms read ×5.3, a pass);
- **batches**, for a caller whose calls are short: the per-call CPU averaged over
  ``batch`` calls.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

# Re-exported on purpose: the clock this measurement reads, which a test scripts.
from tests.support.thread_clock import thread_time as thread_time

#: Below this many seconds of CPU per call at the large size, the ratio is noise.
FLOOR_SECONDS = 0.02
#: The small size is read as at least this (a 3 ms run under xdist on a loaded host
#: is not measurable to a factor of 8 — measured 2026-09-30: ×8.2 for an exponent of 1.01).
SMALL_FLOOR_SECONDS = FLOOR_SECONDS / 4
#: A function may take at most this many times longer on four times the input.
MAX_GROWTH = 8.0
#: Whatever the growth, one call at the large size must stay under this (wall clock).
CEILING_SECONDS = 1.5
#: Interleaved small/large pairs; the median one decides.
PAIRS = 3


@dataclass(frozen=True)
class Growth:
    """The median pair of one measurement.

    Attributes:
        small: CPU seconds per call at the small size.
        large: CPU seconds per call at the large size.
        elapsed: The fastest single call at the large size, on the wall clock.
    """

    small: float
    large: float
    elapsed: float

    @property
    def ratio(self) -> float:
        """How many times longer the large size took, the small one read at its floor."""
        return self.large / max(self.small, SMALL_FLOOR_SECONDS)

    @property
    def judged(self) -> bool:
        """Whether the large size cost enough for its ratio to be more than noise."""
        return self.large >= FLOOR_SECONDS

    @property
    def linear(self) -> bool:
        """The criterion: unjudged, or at most ``MAX_GROWTH`` times longer."""
        return not self.judged or self.ratio <= MAX_GROWTH

    def describe(self) -> str:
        """The measurement in one line, for a failing assertion."""
        return (
            f"×{self.ratio:.1f} for ×4 the input "
            f"({self.small * 1000:.1f} ms → {self.large * 1000:.1f} ms CPU per call)"
        )


def _per_call[T](call: Callable[[T], object], argument: T, batch: int) -> tuple[float, float]:
    """CPU seconds per call over ``batch`` calls, and the first call's wall seconds."""
    started_cpu = thread_time()
    started_wall = time.perf_counter()
    call(argument)
    elapsed = time.perf_counter() - started_wall
    for _ in range(batch - 1):
        call(argument)
    return (thread_time() - started_cpu) / batch, elapsed


def measure_growth[T](call: Callable[[T], object], small: T, large: T, *, batch: int = 1) -> Growth:
    """Measure ``call`` at a small input and at four times it, in interleaved pairs.

    Args:
        call: The function under judgement.
        small: The small input.
        large: Four times the small input.
        batch: Calls averaged into each reading — more for a short call.

    Returns:
        The median pair: its per-call CPU at each size and the best large wall time.
    """
    pairs: list[tuple[float, float, float]] = []
    for _ in range(PAIRS):
        small_cpu, _ = _per_call(call, small, batch)
        large_cpu, large_wall = _per_call(call, large, batch)
        pairs.append((small_cpu, large_cpu, large_wall))
    ordered = sorted(pairs, key=lambda pair: pair[1] / max(pair[0], SMALL_FLOOR_SECONDS))
    median_small, median_large, _ = ordered[PAIRS // 2]
    return Growth(median_small, median_large, min(pair[2] for pair in pairs))
