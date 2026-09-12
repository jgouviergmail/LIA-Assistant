"""Per-worker resident memory, one Prometheus series per process.

The API runs under several uvicorn workers and prometheus_client's multiprocess
mode does not export ``process_*`` metrics, so the only memory figure the
platform had was cAdvisor's, for the WHOLE container. Measured 2026-09-08 →
09-10 on production: the container climbed from 2.5 to 5.3 GB over two days
and nothing could say which process held it, nor whether it was heap or page
cache. Answering that took a shell on the host and ``/proc/<pid>/status``.

This module publishes what that shell read — ``RssAnon`` (heap: Python
objects, model weights, ONNX arenas), ``RssFile`` (mapped libraries) and
``RssShmem`` — from the kernel's own accounting, under
``lia_worker_memory_bytes{kind}`` with ``multiprocess_mode="liveall"``, so a
panel shows one line per live worker. The sampler runs in every worker's
event loop and reads one small file per period; where there is no ``/proc``
(a Windows checkout) it publishes nothing and returns.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from prometheus_client import Gauge, multiprocess

from src.infrastructure.observability.logging import get_logger

logger = get_logger(__name__)

PROC_ROOT = Path("/proc")
PROC_SELF_STATUS = PROC_ROOT / "self" / "status"
MULTIPROC_DIR_ENV = "PROMETHEUS_MULTIPROC_DIR"

# The three RSS components the kernel splits (``Documentation/filesystems/proc.rst``).
_STATUS_FIELDS: dict[str, str] = {"RssAnon": "anon", "RssFile": "file", "RssShmem": "shmem"}

worker_memory_bytes = Gauge(
    "lia_worker_memory_bytes",
    "Resident memory of this worker process by kind (anon = heap, file = mapped "
    "libraries, shmem = shared), from /proc/self/status",
    ["kind"],
    # One series per LIVE worker: the question this answers is "which process
    # grew", which a sum across workers hides by construction.
    multiprocess_mode="liveall",
)


@dataclass(frozen=True, slots=True)
class ResidentMemory:
    """The resident set of one process, in bytes, as the kernel splits it."""

    anon: int
    file: int
    shmem: int

    @property
    def total(self) -> int:
        """The whole resident set (``VmRSS``)."""
        return self.anon + self.file + self.shmem


def read_resident_memory(status_path: Path = PROC_SELF_STATUS) -> ResidentMemory | None:
    """Read the process's resident memory from a ``/proc/<pid>/status`` file.

    Args:
        status_path: The status file; the running process's own by default.

    Returns:
        The three RSS components in bytes, or ``None`` where the file does not
        exist (no procfs) or does not split RSS (a kernel older than 4.5).
    """
    try:
        text = status_path.read_text(encoding="utf-8")
    except OSError:
        return None
    kilobytes: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        kind = _STATUS_FIELDS.get(key)
        if kind is None:
            continue
        digits = rest.strip().split(" ", 1)[0]
        if digits.isdigit():
            kilobytes[kind] = int(digits) * 1024
    if set(kilobytes) != set(_STATUS_FIELDS.values()):
        return None
    return ResidentMemory(anon=kilobytes["anon"], file=kilobytes["file"], shmem=kilobytes["shmem"])


def publish_resident_memory(memory: ResidentMemory) -> None:
    """Set the three series of ``lia_worker_memory_bytes`` for this process."""
    worker_memory_bytes.labels(kind="anon").set(memory.anon)
    worker_memory_bytes.labels(kind="file").set(memory.file)
    worker_memory_bytes.labels(kind="shmem").set(memory.shmem)


def pid_alive(pid: int, *, proc_root: Path = PROC_ROOT) -> bool:
    """Whether ``pid`` exists, read from procfs.

    Never a signal: ``os.kill(pid, 0)`` is a liveness probe on POSIX and a
    TerminateProcess on Windows. Where there is no procfs the answer is
    ``True`` — nothing is ever reaped on a guess.

    Args:
        pid: The process id to look up.
        proc_root: The procfs mount; injectable for tests.

    Returns:
        ``True`` when the process exists or cannot be checked.
    """
    if not proc_root.is_dir():
        return True
    return (proc_root / str(pid)).is_dir()


def reap_dead_worker_series(
    multiproc_dir: Path | None,
    *,
    alive: Callable[[int], bool] | None = None,
) -> list[int]:
    """Drop the live-gauge files of worker processes that no longer exist.

    ``multiprocess_mode="live*"`` files are removed by ``mark_process_dead``
    and by nothing else, and a worker the kernel OOM-kills never reaches its
    shutdown: its last reading — the one that got it killed — would keep being
    exported, and keep ``ApiWorkerMemoryHigh`` firing, until the container
    restarts. Counters and non-live gauges are left alone, as
    ``mark_process_dead`` leaves them.

    Args:
        multiproc_dir: ``PROMETHEUS_MULTIPROC_DIR``, or ``None`` outside
            multiprocess mode.
        alive: The liveness predicate; ``pid_alive`` unless injected.

    Returns:
        The pids whose live series were dropped, ascending.
    """
    if multiproc_dir is None or not multiproc_dir.is_dir():
        return []
    is_alive = alive or pid_alive
    dead: set[int] = set()
    for file in multiproc_dir.glob("gauge_live*_*.db"):
        pid_text = file.stem.rsplit("_", 1)[-1]
        if pid_text.isdigit() and not is_alive(int(pid_text)):
            dead.add(int(pid_text))
    for pid in sorted(dead):
        multiprocess.mark_process_dead(pid, str(multiproc_dir))
        logger.info("worker_memory_dead_series_reaped", pid=pid)
    return sorted(dead)


def _multiproc_dir() -> Path | None:
    value = os.environ.get(MULTIPROC_DIR_ENV)
    return Path(value) if value else None


async def sample_worker_memory(
    interval_seconds: float,
    *,
    reader: Callable[[], ResidentMemory | None] = read_resident_memory,
) -> None:
    """Publish this worker's resident memory now and then every period.

    Runs until cancelled. Returns on its own where the FIRST reading finds
    nothing to read — a checkout without procfs — so the task costs nothing
    there and the absence of series says so; a later failed reading is logged
    and retried at the next period. Each pass first reaps the live series of
    workers that died without a shutdown, so a killed worker's last figure
    never outlives it.

    Args:
        interval_seconds: Seconds between two readings.
        reader: The measurement; injectable for tests.
    """
    first = True
    while True:
        reap_dead_worker_series(_multiproc_dir())
        memory = reader()
        if memory is None:
            if first:
                logger.debug("worker_memory_sampler_unavailable", reason="no_procfs_rss_split")
                return
            logger.debug("worker_memory_reading_failed")
        else:
            publish_resident_memory(memory)
        first = False
        await asyncio.sleep(interval_seconds)
