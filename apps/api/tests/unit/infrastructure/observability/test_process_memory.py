"""Every worker publishes what IT holds: resident memory, one series per process.

The API runs under four uvicorn workers and prometheus_client's multiprocess
mode does not export ``process_*`` metrics, so until now the only memory
figure of the API was cAdvisor's, for the whole container. That figure could
say the container climbed from 2.5 to 5.3 GB over two days (measured 2026-09-08
→ 09-10) and nothing could say WHICH process, nor whether it was heap or cache.
``lia_worker_memory_bytes{kind}`` answers both — anon / file / shmem, read
from the kernel's own accounting — and the STT gauge beside it says whether a
model is what the worker holds.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from prometheus_client import REGISTRY

from src.infrastructure.observability import process_memory as pm

pytestmark = pytest.mark.unit

STATUS = """Name:\tpython3.14
VmRSS:\t 1197440 kB
RssAnon:\t 1127360 kB
RssFile:\t   69072 kB
RssShmem:\t    1008 kB
Threads:\t21
"""


def _series(kind: str) -> float | None:
    return REGISTRY.get_sample_value("lia_worker_memory_bytes", {"kind": kind})


class TestReadingTheKernelsAccounting:
    def test_parses_anon_file_and_shmem_into_bytes(self, tmp_path: Path) -> None:
        status = tmp_path / "status"
        status.write_text(STATUS, encoding="utf-8")

        memory = pm.read_resident_memory(status)

        assert memory == pm.ResidentMemory(
            anon=1127360 * 1024, file=69072 * 1024, shmem=1008 * 1024
        )
        assert memory.total == (1127360 + 69072 + 1008) * 1024

    def test_answers_none_where_there_is_no_proc(self, tmp_path: Path) -> None:
        assert pm.read_resident_memory(tmp_path / "absent") is None

    def test_answers_none_when_the_kernel_does_not_split_rss(self, tmp_path: Path) -> None:
        status = tmp_path / "status"
        status.write_text("Name:\tpython\nVmRSS:\t 1000 kB\n", encoding="utf-8")

        assert pm.read_resident_memory(status) is None


class TestPublishing:
    def test_each_kind_is_its_own_series(self) -> None:
        pm.publish_resident_memory(pm.ResidentMemory(anon=3, file=2, shmem=1))

        assert (_series("anon"), _series("file"), _series("shmem")) == (3.0, 2.0, 1.0)


class TestTheSampler:
    async def test_publishes_at_start_then_every_interval_until_cancelled(self) -> None:
        seen: list[int] = []

        def reader() -> pm.ResidentMemory | None:
            value = pm.ResidentMemory(anon=10 * (len(seen) + 1), file=0, shmem=0)
            seen.append(value.anon)
            return value

        task = asyncio.create_task(pm.sample_worker_memory(0.01, reader=reader))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert seen[:1] == [10]
        assert len(seen) >= 2
        assert _series("anon") == float(seen[-1])

    async def test_stops_on_its_own_where_the_kernel_offers_nothing(self) -> None:
        calls = 0

        def reader() -> pm.ResidentMemory | None:
            nonlocal calls
            calls += 1
            return None

        await asyncio.wait_for(pm.sample_worker_memory(60, reader=reader), timeout=1)

        assert calls == 1


class TestReapingTheSeriesOfDeadWorkers:
    """``liveall`` files are removed by ``mark_process_dead`` and by nothing else.

    A worker that the kernel OOM-kills never runs its shutdown, so its
    ``gauge_liveall_<pid>.db`` stays in the multiprocess directory and its last
    reading — the very reading that got it killed — keeps being exported, and
    keeps the alert firing, until the container restarts. Every live worker
    therefore reaps the live-gauge files of pids that no longer exist.
    """

    def test_removes_live_gauge_files_of_dead_pids_only(self, tmp_path: Path) -> None:
        (tmp_path / "gauge_liveall_111.db").write_bytes(b"")
        (tmp_path / "gauge_livesum_111.db").write_bytes(b"")
        (tmp_path / "counter_111.db").write_bytes(b"")
        (tmp_path / "gauge_liveall_222.db").write_bytes(b"")
        (tmp_path / "gauge_all_111.db").write_bytes(b"")

        reaped = pm.reap_dead_worker_series(tmp_path, alive=lambda pid: pid == 222)

        assert reaped == [111]
        assert sorted(f.name for f in tmp_path.iterdir()) == [
            "counter_111.db",
            "gauge_all_111.db",
            "gauge_liveall_222.db",
        ]

    def test_is_a_no_op_without_a_multiprocess_directory(self, tmp_path: Path) -> None:
        assert pm.reap_dead_worker_series(None, alive=lambda pid: False) == []
        assert pm.reap_dead_worker_series(tmp_path / "absent", alive=lambda pid: False) == []

    def test_liveness_is_read_from_procfs_never_from_a_signal(self, tmp_path: Path) -> None:
        proc = tmp_path / "proc"
        (proc / "4242").mkdir(parents=True)

        assert pm.pid_alive(4242, proc_root=proc) is True
        assert pm.pid_alive(4243, proc_root=proc) is False
        assert pm.pid_alive(4243, proc_root=tmp_path / "no-proc") is True

    async def test_the_sampler_reaps_before_it_publishes(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / "gauge_liveall_111.db").write_bytes(b"")
        monkeypatch.setenv("PROMETHEUS_MULTIPROC_DIR", str(tmp_path))
        monkeypatch.setattr(pm, "pid_alive", lambda pid: False)
        published: list[int] = []

        def reader() -> pm.ResidentMemory | None:
            published.append(int((tmp_path / "gauge_liveall_111.db").exists()))
            return pm.ResidentMemory(anon=1, file=0, shmem=0)

        task = asyncio.create_task(pm.sample_worker_memory(60, reader=reader))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert published == [0], "the ghost file must be gone BEFORE the first reading"

    async def test_a_transient_failed_reading_does_not_stop_the_sampler(self) -> None:
        readings: list[pm.ResidentMemory | None] = [
            pm.ResidentMemory(anon=1, file=0, shmem=0),
            None,
            pm.ResidentMemory(anon=3, file=0, shmem=0),
        ]
        seen = 0

        def reader() -> pm.ResidentMemory | None:
            nonlocal seen
            seen += 1
            return readings[min(seen, len(readings)) - 1]

        task = asyncio.create_task(pm.sample_worker_memory(0.01, reader=reader))
        await asyncio.sleep(0.08)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert seen >= 3
        assert _series("anon") == 3.0
