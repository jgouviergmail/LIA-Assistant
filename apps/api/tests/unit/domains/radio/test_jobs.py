"""The radio's background jobs: the newsroom obeys the switch, the sweep never deletes on doubt."""

from __future__ import annotations

import contextlib
import os
import time
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from prometheus_client import REGISTRY
from structlog.testing import capture_logs

from src.core.config import settings
from src.domains.feature_switches.registry import PlatformCapability
from src.domains.radio import jobs as jobs_module
from src.domains.radio.live_store import ACTIVE_KEY
from src.domains.radio.media import prepare, session_dir
from src.domains.radio.newsroom.collector import CollectorLimits, PassReport
from src.domains.radio.settings_view import collector_limits, radio_runtime
from tests.unit.domains.radio.fakes import FakeRedis

pytestmark = pytest.mark.unit

REPORT = PassReport(
    feeds_read=3,
    feeds_failed=1,
    items_new=12,
    texts_ready=4,
    texts_unavailable=0,
    purged=2,
    cut=False,
)
ROBOTS = object()
CLIENT = object()


class Switch:
    """Stands for ``is_capability_enabled``: answers as set, records what was asked."""

    def __init__(self, enabled: bool) -> None:
        self.enabled = enabled
        self.asked: list[PlatformCapability] = []

    async def __call__(self, capability: PlatformCapability) -> bool:
        self.asked.append(capability)
        return self.enabled


class Pass:
    """Stands for ``collect_pass``: records its arguments, answers or raises."""

    def __init__(self, error: Exception | None = None, *, report: PassReport = REPORT) -> None:
        self.error = error
        self.report = report
        self.calls: list[dict[str, Any]] = []

    async def __call__(
        self,
        store: object,
        client: object,
        robots: object,
        *,
        now: datetime,
        limits: CollectorLimits,
    ) -> PassReport:
        self.calls.append(
            {"store": store, "client": client, "robots": robots, "now": now, "limits": limits}
        )
        if self.error is not None:
            raise self.error
        return self.report


class Client:
    """Stands for ``newsroom_client``: one client per pass, closed when it ends."""

    def __init__(self) -> None:
        self.opened = 0
        self.closed = 0

    @contextlib.asynccontextmanager
    async def __call__(self) -> AsyncIterator[object]:
        self.opened += 1
        try:
            yield CLIENT
        finally:
            self.closed += 1


async def robots() -> object:
    return ROBOTS


@pytest.fixture
def newsroom(monkeypatch: pytest.MonkeyPatch) -> Client:
    client = Client()
    monkeypatch.setattr(jobs_module, "newsroom_robots", robots)
    monkeypatch.setattr(jobs_module, "newsroom_client", client)
    return client


class TestTheNewsroomPass:
    async def test_switched_off_it_reads_nothing(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        switch, collect = Switch(False), Pass()
        monkeypatch.setattr(jobs_module, "is_capability_enabled", switch)
        monkeypatch.setattr(jobs_module, "collect_pass", collect)

        assert await jobs_module.run_newsroom_pass() is None
        assert switch.asked == [PlatformCapability.RADIO]
        assert collect.calls == [] and newsroom.opened == 0

    async def test_switched_on_it_runs_one_pass_under_the_settings(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        collect = Pass()
        monkeypatch.setattr(jobs_module, "is_capability_enabled", Switch(True))
        monkeypatch.setattr(jobs_module, "collect_pass", collect)

        assert await jobs_module.run_newsroom_pass() == REPORT
        [call] = collect.calls
        assert call["client"] is CLIENT and call["robots"] is ROBOTS
        assert call["limits"] == collector_limits()
        assert call["now"].tzinfo is not None
        assert (newsroom.opened, newsroom.closed) == (1, 1)

    async def test_a_failing_pass_is_logged_by_its_facts_and_never_raises(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        secret = "https://listener.example/private-feed"
        monkeypatch.setattr(jobs_module, "is_capability_enabled", Switch(True))
        monkeypatch.setattr(jobs_module, "collect_pass", Pass(RuntimeError(secret)))

        with capture_logs() as logs:
            assert await jobs_module.run_newsroom_pass() is None

        [entry] = [log for log in logs if log["event"] == "radio_newsroom_pass_failed"]
        assert entry["error_type"] == "RuntimeError"
        assert secret not in repr(logs)
        assert newsroom.closed == newsroom.opened == 1


def _aged(directory: Path, seconds: float) -> None:
    moment = time.time() - seconds
    os.utime(directory, (moment, moment))


class TestTheMediaSweep:
    async def test_it_spares_the_live_and_removes_the_abandoned(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        redis = FakeRedis()
        live, silent, crashed = uuid4(), uuid4(), uuid4()
        now = datetime.now(UTC).timestamp()
        await redis.zadd(ACTIVE_KEY, {str(live): now})
        # Published long before the live horizon: its worker died.
        await redis.zadd(ACTIVE_KEY, {str(silent): now - 10 * radio_runtime().live_horizon_s})
        for session in (live, silent, crashed):
            _aged(await prepare(tmp_path, session), settings.radio_media_orphan_age_seconds * 2)

        async def cache() -> FakeRedis:
            return redis

        monkeypatch.setattr(jobs_module, "get_redis_cache", cache)
        monkeypatch.setattr(jobs_module, "radio_media_root", lambda: tmp_path)

        assert await jobs_module.sweep_radio_media() == 2
        assert session_dir(tmp_path, live).exists()
        assert not session_dir(tmp_path, silent).exists()
        assert not session_dir(tmp_path, crashed).exists()

    async def test_without_the_live_sessions_it_removes_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        crashed = uuid4()
        _aged(await prepare(tmp_path, crashed), settings.radio_media_orphan_age_seconds * 2)

        async def unreachable() -> FakeRedis:
            raise ConnectionError("redis down")

        monkeypatch.setattr(jobs_module, "get_redis_cache", unreachable)
        monkeypatch.setattr(jobs_module, "radio_media_root", lambda: tmp_path)

        assert await jobs_module.sweep_radio_media() == 0
        assert session_dir(tmp_path, crashed).exists()

    async def test_a_disk_that_refuses_is_reported_not_raised(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        async def cache() -> FakeRedis:
            return FakeRedis()

        async def refused(*args: object, **kwargs: object) -> int:
            raise PermissionError("read-only file system")

        monkeypatch.setattr(jobs_module, "get_redis_cache", cache)
        monkeypatch.setattr(jobs_module, "sweep_orphans", refused)

        with capture_logs() as logs:
            assert await jobs_module.sweep_radio_media() == 0
        assert [
            log["error_type"] for log in logs if log["event"] == "radio_media_sweep_failed"
        ] == ["PermissionError"]


def sample(name: str, **labels: str) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


STAMP = "radio_newsroom_last_run_timestamp_seconds"


class TestTheNewsroomIsCounted:
    async def test_a_tick_while_switched_off_is_counted_and_stamped(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        monkeypatch.setattr(jobs_module, "is_capability_enabled", Switch(False))
        off = sample("radio_newsroom_passes_total", outcome="off")
        before = time.time()

        await jobs_module.run_newsroom_pass()

        assert sample("radio_newsroom_passes_total", outcome="off") == off + 1
        assert sample(STAMP) >= before  # an operator's switch is not a stall

    async def test_a_pass_publishes_what_it_did(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        monkeypatch.setattr(jobs_module, "is_capability_enabled", Switch(True))
        monkeypatch.setattr(jobs_module, "collect_pass", Pass())
        counted = {
            ("radio_newsroom_passes_total", "outcome", "completed"): 1,
            ("radio_newsroom_feed_readings_total", "outcome", "read"): REPORT.feeds_read,
            ("radio_newsroom_feed_readings_total", "outcome", "failed"): REPORT.feeds_failed,
            ("radio_newsroom_stories_total", "event", "new"): REPORT.items_new,
            ("radio_newsroom_stories_total", "event", "purged"): REPORT.purged,
            ("radio_newsroom_texts_total", "outcome", "ready"): REPORT.texts_ready,
            ("radio_newsroom_texts_total", "outcome", "unavailable"): REPORT.texts_unavailable,
        }
        before = {key: sample(key[0], **{key[1]: key[2]}) for key in counted}
        stamped_after = time.time()

        await jobs_module.run_newsroom_pass()

        for key, added in counted.items():
            assert sample(key[0], **{key[1]: key[2]}) == before[key] + added, key
        assert sample(STAMP) >= stamped_after

    async def test_a_pass_cut_by_its_deadline_says_so(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        monkeypatch.setattr(jobs_module, "is_capability_enabled", Switch(True))
        monkeypatch.setattr(jobs_module, "collect_pass", Pass(report=replace(REPORT, cut=True)))
        cut, completed = (
            sample("radio_newsroom_passes_total", outcome="cut"),
            sample("radio_newsroom_passes_total", outcome="completed"),
        )

        await jobs_module.run_newsroom_pass()

        assert sample("radio_newsroom_passes_total", outcome="cut") == cut + 1
        assert sample("radio_newsroom_passes_total", outcome="completed") == completed

    async def test_a_failed_pass_is_counted_and_leaves_the_stamp_to_age(
        self, monkeypatch: pytest.MonkeyPatch, newsroom: Client
    ) -> None:
        """The stall alert reads the stamp's age: a failing pass must never renew it."""
        monkeypatch.setattr(jobs_module, "is_capability_enabled", Switch(True))
        monkeypatch.setattr(jobs_module, "collect_pass", Pass(RuntimeError("down")))
        jobs_module.radio_newsroom_last_run_timestamp_seconds.set(1_000.0)
        failed = sample("radio_newsroom_passes_total", outcome="failed")

        await jobs_module.run_newsroom_pass()

        assert sample("radio_newsroom_passes_total", outcome="failed") == failed + 1
        assert sample(STAMP) == 1_000.0


class TestTheSweepIsCounted:
    async def test_every_directory_removed_is_counted(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        async def cache() -> FakeRedis:
            return FakeRedis()

        async def two_removed(*args: object, **kwargs: object) -> int:
            return 2

        monkeypatch.setattr(jobs_module, "get_redis_cache", cache)
        monkeypatch.setattr(jobs_module, "sweep_orphans", two_removed)
        removed = sample("radio_media_orphans_removed_total")

        assert await jobs_module.sweep_radio_media() == 2

        assert sample("radio_media_orphans_removed_total") == removed + 2
