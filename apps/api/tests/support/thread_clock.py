"""The calling thread's own CPU time, precise on every host the suite runs on.

The linearity guards (ADR-326) compare what a function costs at n and at 4n.
They read the THREAD's CPU, never the wall: a host busy with other work — the
parallel suite itself — deschedules the thread, and a wall clock counts the
wait as work. Measured 2026-10-16 with every core saturated, on one linear
filter: ×3.7 to ×8.5 on the wall clock, ×3.88 to ×4.12 on its cycle counter.

``time.thread_time()`` is that clock on Linux and macOS. On Windows it reads
``GetThreadTimes()``, which moves by scheduler ticks of 15.6 ms: a 9 ms call
reads 0 or 15.6 ms, and batches spanning four ticks still read a linear filter
at ×6.5 against a threshold of ×8. The thread's cycle counter
(``QueryThreadCycleTime``) is precise and, like ``thread_time``, stands still
while the thread waits for a processor. Its rate is calibrated once against
``perf_counter`` over a few short busy spans: a span the scheduler interrupts
reads fewer cycles per second, never more, so the fastest span is the rate. A
guard judges a RATIO of two readings, which the rate cancels out of; the
conversion to seconds only places its floors.
"""

from __future__ import annotations

import sys
import time

if sys.platform == "win32":
    import ctypes
    from functools import cache

    _KERNEL32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _KERNEL32.GetCurrentThread.restype = ctypes.c_void_p
    _KERNEL32.QueryThreadCycleTime.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_ulonglong),
    ]
    _KERNEL32.QueryThreadCycleTime.restype = ctypes.c_int

    #: Busy spans timed to calibrate the cycle rate, and the length of each.
    _CALIBRATION_SPANS = 5
    _CALIBRATION_SECONDS = 0.002

    def _cycles() -> int:
        """The calling thread's cycle count."""
        cycles = ctypes.c_ulonglong()
        if not _KERNEL32.QueryThreadCycleTime(_KERNEL32.GetCurrentThread(), ctypes.byref(cycles)):
            raise ctypes.WinError(ctypes.get_last_error())
        return cycles.value

    @cache
    def _cycles_per_second() -> float:
        """The counter's rate: the fastest of a few short busy spans."""
        fastest = 0.0
        for _ in range(_CALIBRATION_SPANS):
            started_cycles, started = _cycles(), time.perf_counter()
            while (elapsed := time.perf_counter() - started) < _CALIBRATION_SECONDS:
                pass
            fastest = max(fastest, (_cycles() - started_cycles) / elapsed)
        return fastest

    def thread_time() -> float:
        """The calling thread's CPU time in seconds, read from its cycle counter."""
        # Calibrated BEFORE the reading it converts: the first call spins for the
        # calibration, and a count taken first would credit that spin to the span.
        rate = _cycles_per_second()
        return _cycles() / rate

else:

    def thread_time() -> float:
        """The calling thread's CPU time in seconds."""
        return time.thread_time()


__all__ = ["thread_time"]
