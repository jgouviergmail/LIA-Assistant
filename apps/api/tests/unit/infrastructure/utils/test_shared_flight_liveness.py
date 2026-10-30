"""Owner liveness in ``run_shared_flight`` (opt-in, the briefing only).

Measured (spec 2026-10-21 §0ter D-H4, E12): a waiter accepts nothing but a
COMPLETE published bundle, so one section missing at publication — failed, or
invalidated by a push at the owner's end — cost every waiter the whole 10 s
budget, then one uncoordinated rebuild EACH. With liveness on, the claim says
whether the owner is still working: a waiter keeps waiting while it is held
(up to a hard ceiling), builds once it is gone without a result, and only ONE
waiter does so. The clock and the poll sleeps are injected; the owner's claim
keeper runs on real time with a short TTL.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.locks.redis_claim import REFRESH_SCRIPT, RELEASE_SCRIPT
from src.infrastructure.utils import shared_flight
from src.infrastructure.utils.shared_flight import run_shared_flight

pytestmark = [pytest.mark.unit]

KEY = "shared_flight:test:liveness"


class ClaimRedis:
    """SET NX, GET and the two owner-token scripts of ``redis_claim``."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.ops: Counter[str] = Counter()

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.ops["set"] += 1
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key: str):
        self.ops["get"] += 1
        return self.store.get(key)

    async def eval(self, script: str, numkeys: int, *args: object):
        key, token = str(args[0]), str(args[1])
        owned = self.store.get(key) == token
        if script == RELEASE_SCRIPT:
            self.ops["release"] += 1
            if owned:
                del self.store[key]
            return int(owned)
        if script == REFRESH_SCRIPT:
            self.ops["refresh"] += 1
            return int(owned)
        raise AssertionError("unexpected script")


class VirtualClock:
    """``_now`` and ``_sleep`` for the waiter: each poll sleep advances virtual time."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds
        await asyncio.sleep(0)


@pytest.fixture
def redis() -> ClaimRedis:
    return ClaimRedis()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> VirtualClock:
    virtual = VirtualClock()
    monkeypatch.setattr(shared_flight, "_now", virtual.monotonic)
    monkeypatch.setattr(shared_flight, "_sleep", virtual.sleep)
    return virtual


def _cache(redis: ClaimRedis):
    return patch(
        "src.infrastructure.utils.shared_flight.get_redis_cache", AsyncMock(return_value=redis)
    )


class Published:
    """What the build publishes, read back by waiters."""

    def __init__(self) -> None:
        self.value: str | None = None

    async def read(self) -> str | None:
        return self.value


async def test_waiter_keeps_waiting_while_owner_holds_claim(
    redis: ClaimRedis, clock: VirtualClock
) -> None:
    published = Published()
    release = asyncio.Event()
    builds = 0

    async def build() -> str:
        nonlocal builds
        builds += 1
        await release.wait()
        published.value = "bundle"
        return "bundle"

    async def owner_outlives_the_old_budget() -> None:
        while clock.now < 1000.0 + 12.0:
            await asyncio.sleep(0)
        release.set()

    with _cache(redis):
        owner = asyncio.create_task(
            run_shared_flight(
                KEY, build=build, read_shared=published.read, wait_budget_s=60, owner_liveness=True
            )
        )
        await asyncio.sleep(0)
        watcher = asyncio.create_task(owner_outlives_the_old_budget())
        waited = await run_shared_flight(
            KEY, build=build, read_shared=published.read, wait_budget_s=60, owner_liveness=True
        )
        owned = await owner
        await watcher

    assert builds == 1
    assert owned.claimed is True
    assert waited.value == "bundle" and waited.waited is True and waited.claimed is False
    assert clock.now - 1000.0 > 10.0
    assert KEY not in redis.store


async def test_waiter_builds_when_claim_disappears(redis: ClaimRedis, clock: VirtualClock) -> None:
    redis.store[KEY] = "a-holder-that-died"
    published = Published()
    builds = 0

    async def build() -> str:
        nonlocal builds
        builds += 1
        published.value = "rebuilt"
        return "rebuilt"

    async def claim_expires() -> None:
        while clock.now < 1000.0 + 1.0:
            await asyncio.sleep(0)
        del redis.store[KEY]

    with _cache(redis):
        expiry = asyncio.create_task(claim_expires())
        result = await run_shared_flight(
            KEY, build=build, read_shared=published.read, wait_budget_s=60, owner_liveness=True
        )
        await expiry

    assert builds == 1
    assert result.value == "rebuilt" and result.claimed is True and result.waited is True


async def test_owner_claim_is_renewed_during_build(redis: ClaimRedis) -> None:
    published = Published()

    async def slow_build() -> str:
        await asyncio.sleep(0.8)  # longer than the 1 s claim's refresh period (1/3 s)
        return "done"

    with _cache(redis):
        result = await run_shared_flight(
            KEY,
            build=slow_build,
            read_shared=published.read,
            wait_budget_s=60,
            claim_ttl_s=1,
            owner_liveness=True,
        )

    assert result.value == "done" and result.claimed is True
    assert redis.ops["refresh"] >= 1
    assert KEY not in redis.store


async def test_poll_interval_backs_off_to_cap(redis: ClaimRedis, clock: VirtualClock) -> None:
    redis.store[KEY] = "someone-else"
    published = Published()

    async def build() -> str:
        return "fallback"

    with _cache(redis):
        result = await run_shared_flight(
            KEY, build=build, read_shared=published.read, wait_budget_s=3, owner_liveness=True
        )

    assert result.value == "fallback" and result.waited is True
    assert clock.sleeps[:5] == [0.02, 0.04, 0.08, 0.16, 0.25]
    assert set(clock.sleeps[4:]) == {0.25}


async def test_budget_is_a_hard_ceiling(redis: ClaimRedis, clock: VirtualClock) -> None:
    """A claim that never goes away still lets the waiter build at the ceiling."""
    redis.store[KEY] = "stuck-holder"

    async def build() -> str:
        return "own"

    with _cache(redis):
        result = await run_shared_flight(
            KEY, build=build, read_shared=Published().read, wait_budget_s=5, owner_liveness=True
        )

    assert result.value == "own" and result.claimed is False
    assert 5.0 <= clock.now - 1000.0 < 5.3


async def test_release_without_result_is_reclaimed_by_one_waiter(
    redis: ClaimRedis, clock: VirtualClock
) -> None:
    """E12 (spec D11): the owner publishes an incomplete bundle and releases."""
    published = Published()
    owner_may_finish = asyncio.Event()
    builds = 0

    async def build() -> str:
        nonlocal builds
        builds += 1
        nth = builds
        if nth == 1:
            await owner_may_finish.wait()
            return "incomplete"  # nothing published: a section was invalidated
        published.value = f"complete#{nth}"
        return published.value

    async def call() -> shared_flight.SharedFlightResult[str]:
        return await run_shared_flight(
            KEY, build=build, read_shared=published.read, wait_budget_s=60, owner_liveness=True
        )

    with _cache(redis):
        owner = asyncio.create_task(call())
        await asyncio.sleep(0)
        waiters = [asyncio.create_task(call()) for _ in range(3)]
        while clock.now < 1000.0 + 0.5:
            await asyncio.sleep(0)
        owner_may_finish.set()
        results = await asyncio.gather(owner, *waiters)

    assert builds == 2
    assert [r.value for r in results[1:]].count("complete#2") == 3
    assert sum(r.claimed for r in results[1:]) == 1


async def test_reclaiming_waiter_takes_the_settled_result(
    redis: ClaimRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The owner settles and releases between a waiter's read and its re-claim.

    Measured across four real processes: the waiter took the claim, looked for
    a COMPLETE result only, and re-read the source that had just failed.
    """
    clock = VirtualClock()

    async def generous_sleep(seconds: float) -> None:
        clock.sleeps.append(seconds)
        clock.now += seconds
        for _ in range(50):  # long enough for the owner to finish and release
            await asyncio.sleep(0)

    monkeypatch.setattr(shared_flight, "_now", clock.monotonic)
    monkeypatch.setattr(shared_flight, "_sleep", generous_sleep)
    complete = Published()  # a fresh owner's look: never set (a section failed)
    owner_may_finish = asyncio.Event()
    settled_value: list[str] = []
    builds = 0

    async def read_settled() -> str | None:
        if not settled_value:
            owner_may_finish.set()  # the waiter has looked: let the owner settle now
            return None
        return settled_value[0]

    async def build() -> str:
        nonlocal builds
        builds += 1
        await owner_may_finish.wait()
        settled_value.append("settled")
        return "owner"

    async def call() -> shared_flight.SharedFlightResult[str]:
        return await run_shared_flight(
            KEY,
            build=build,
            read_shared=complete.read,
            read_settled=read_settled,
            wait_budget_s=60,
            owner_liveness=True,
        )

    with _cache(redis):
        owner = asyncio.create_task(call())
        await asyncio.sleep(0)
        waited = await call()
        await owner

    assert builds == 1
    assert waited.value == "settled" and waited.claimed is False and waited.waited is True


async def test_build_failure_releases_and_propagates(redis: ClaimRedis) -> None:
    async def broken() -> str:
        raise RuntimeError("source down")

    with _cache(redis), pytest.raises(RuntimeError):
        await run_shared_flight(
            KEY, build=broken, read_shared=Published().read, wait_budget_s=5, owner_liveness=True
        )
    assert KEY not in redis.store


async def test_no_cache_builds_locally_with_liveness() -> None:
    async def build() -> str:
        return "local"

    with patch(
        "src.infrastructure.utils.shared_flight.get_redis_cache",
        AsyncMock(side_effect=ConnectionError),
    ):
        result = await run_shared_flight(
            KEY, build=build, read_shared=Published().read, wait_budget_s=5, owner_liveness=True
        )
    assert result.value == "local" and result.claimed is False


async def test_an_owner_that_lost_its_claim_takes_the_successors_result(redis: ClaimRedis) -> None:
    """A lost claim stops the build; what a successor published is taken, never re-bought."""
    published = Published()
    builds: list[str] = []

    async def build() -> str:
        builds.append("build")
        if len(builds) == 1:
            redis.store[KEY] = "successor"  # a successor took the claim over...
            published.value = "successor-result"  # ...and published what it built
            await asyncio.sleep(5)  # stopped by the lost claim
        return "rebuilt"

    with _cache(redis):
        result = await run_shared_flight(
            KEY,
            build=build,
            read_shared=published.read,
            wait_budget_s=60,
            claim_ttl_s=1,
            owner_liveness=True,
        )

    assert result.value == "successor-result" and result.claimed is False
    assert builds == ["build"]


async def test_an_owner_that_lost_its_claim_to_a_silent_successor_builds_once_more(
    redis: ClaimRedis,
) -> None:
    """Nothing published by whoever took the claim: building without it is the floor."""
    published = Published()
    builds: list[str] = []

    async def build() -> str:
        builds.append("build")
        if len(builds) == 1:
            redis.store[KEY] = "successor"  # taken over, and nothing published yet
            await asyncio.sleep(5)  # stopped by the lost claim
        return "rebuilt"

    with _cache(redis):
        result = await run_shared_flight(
            KEY,
            build=build,
            read_shared=published.read,
            wait_budget_s=60,
            claim_ttl_s=1,
            owner_liveness=True,
        )

    assert result.value == "rebuilt" and result.claimed is False
    assert builds == ["build", "build"]
