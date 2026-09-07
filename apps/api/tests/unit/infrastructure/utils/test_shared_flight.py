"""Coalescing across PROCESSES, not only inside one.

``single_flight`` shares work between callers on one event loop. Production
runs four uvicorn workers (``WEB_CONCURRENCY=4``), so the two requests of a
page load land on the same worker roughly one time in four — measured on the
deployed instance 2026-09-07: three overlapping pairs, none joined, and the
connectors opened up to five times for two page loads.

This seam adds the missing half. One caller CLAIMS the work in Redis; the
others wait for the result it publishes — the shared cache — and only build
themselves if that never arrives. Every failure mode falls back to building,
because the worst outcome of this seam must be the behaviour it replaces.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.utils.shared_flight import run_shared_flight

pytestmark = [pytest.mark.unit]


class FakeRedis:
    """The three operations a claim needs, with SET NX semantics."""

    def __init__(self, *, broken: bool = False) -> None:
        self.store: dict[str, str] = {}
        self.ops: Counter[str] = Counter()
        self.broken = broken

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False):
        self.ops["set"] += 1
        if self.broken:
            raise ConnectionError("redis down")
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def get(self, key: str):
        self.ops["get"] += 1
        if self.broken:
            raise ConnectionError("redis down")
        return self.store.get(key)

    async def eval(self, script: str, numkeys: int, *args):
        """Release conditioned on the owner token (compare-and-delete)."""
        self.ops["eval"] += 1
        if self.broken:
            raise ConnectionError("redis down")
        key, token = args[0], args[1]
        if self.store.get(key) == token:
            del self.store[key]
            return 1
        return 0


class Work:
    def __init__(self, *, delay: float = 0.05) -> None:
        self.runs = 0
        self._delay = delay

    async def __call__(self) -> str:
        self.runs += 1
        nth = self.runs
        await asyncio.sleep(self._delay)
        return f"built#{nth}"


def _reader(published: list[str | None]):
    """A shared-result reader that returns what has been published so far."""

    async def _read() -> str | None:
        return published[0]

    return _read


class TestTheClaimHolderBuilds:
    async def test_the_first_caller_builds_and_releases(self) -> None:
        redis = FakeRedis()
        work = Work()
        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            result = await run_shared_flight(
                "shared_flight:k", build=work, read_shared=_reader([None]), wait_budget_s=0.5
            )
        assert result.value == "built#1"
        assert result.claimed is True
        assert redis.store == {}, "the claim outlived the work it protected"


class TestTheOthersWaitForTheResult:
    async def test_a_second_caller_takes_the_published_result(self) -> None:
        """The point of the whole seam: the loser does NOT rebuild."""
        redis = FakeRedis()
        published: list[str | None] = [None]
        winner = Work(delay=0.05)
        loser = Work(delay=0.05)

        async def _winner() -> str:
            value = await winner()
            published[0] = value  # what filling the shared cache stands for
            return value

        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            first, second = await asyncio.gather(
                run_shared_flight(
                    "shared_flight:k",
                    build=_winner,
                    read_shared=_reader(published),
                    wait_budget_s=1.0,
                ),
                run_shared_flight(
                    "shared_flight:k",
                    build=loser,
                    read_shared=_reader(published),
                    wait_budget_s=1.0,
                ),
            )

        assert winner.runs == 1
        assert loser.runs == 0, "the second caller rebuilt what the first had published"
        assert {first.value, second.value} == {"built#1"}
        assert first.claimed != second.claimed

    async def test_a_waiter_builds_when_the_result_never_arrives(self) -> None:
        """A claim holder that dies must not strand anyone: the budget expires
        and the waiter does the work itself rather than returning nothing."""
        redis = FakeRedis()
        redis.store["shared_flight:k"] = "someone-elses-token"
        work = Work(delay=0.01)
        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            result = await run_shared_flight(
                "shared_flight:k", build=work, read_shared=_reader([None]), wait_budget_s=0.08
            )
        assert result.value == "built#1"
        assert result.claimed is False
        assert result.waited is True


class TestFailureNeverCostsMoreThanBeforeTheSeam:
    async def test_redis_down_builds_locally(self) -> None:
        work = Work()
        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(return_value=FakeRedis(broken=True)),
        ):
            result = await run_shared_flight(
                "shared_flight:k", build=work, read_shared=_reader([None]), wait_budget_s=0.2
            )
        assert result.value == "built#1"
        assert work.runs == 1

    async def test_no_redis_at_all_builds_locally(self) -> None:
        work = Work()
        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(side_effect=ConnectionError("no redis")),
        ):
            result = await run_shared_flight(
                "shared_flight:k", build=work, read_shared=_reader([None]), wait_budget_s=0.2
            )
        assert result.value == "built#1"

    async def test_a_failing_build_releases_the_claim(self) -> None:
        """Otherwise every other worker waits out the budget for nothing."""
        redis = FakeRedis()

        async def _boom() -> str:
            raise RuntimeError("connector exploded")

        with (
            patch(
                "src.infrastructure.utils.shared_flight.get_redis_cache",
                AsyncMock(return_value=redis),
            ),
            pytest.raises(RuntimeError),
        ):
            await run_shared_flight(
                "shared_flight:k", build=_boom, read_shared=_reader([None]), wait_budget_s=0.2
            )
        assert redis.store == {}, "a failed build kept the claim"


class TestTheClaimIsReleasedBYITSOWNER:
    async def test_a_claim_belonging_to_someone_else_is_not_deleted(self) -> None:
        """``SET NX`` followed by an unconditional ``DELETE`` is forbidden here
        (CLAUDE.md): a slow holder whose claim expired would otherwise delete
        the claim its successor has just taken."""
        redis = FakeRedis()
        work = Work(delay=0.01)
        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(return_value=redis),
        ):

            async def _steal() -> str:
                # A successor takes the key while this build is running.
                redis.store["shared_flight:k"] = "successor-token"
                return await work()

            await run_shared_flight(
                "shared_flight:k", build=_steal, read_shared=_reader([None]), wait_budget_s=0.2
            )
        assert (
            redis.store.get("shared_flight:k") == "successor-token"
        ), "the previous holder deleted a claim it no longer owned"


class TestTheHolderLooksBeforeItBuilds:
    """A claim taken is not proof the work is still needed.

    Found by testing for real, across two uvicorn processes sharing one Redis:
    four rounds out of five coalesced, and the fifth built twice. The holder had
    finished and RELEASED before the second caller reached the claim, so that
    caller took a free claim and rebuilt what was already published. Waiting
    protects against a claim that is held; only looking protects against one
    that has just been let go.
    """

    async def test_a_result_published_before_the_claim_was_taken_is_reused(self) -> None:
        redis = FakeRedis()
        work = Work()
        published: list[str | None] = ["already-there"]

        result = await self._run(redis, work, published)

        assert work.runs == 0, "rebuilt a result that was already published"
        assert result.value == "already-there"
        assert result.claimed is False

    async def test_the_claim_is_released_when_the_holder_steps_aside(self) -> None:
        redis = FakeRedis()
        await self._run(redis, Work(), ["already-there"])
        assert redis.store == {}, "stepped aside but kept the claim"

    async def test_nothing_published_still_builds(self) -> None:
        redis = FakeRedis()
        work = Work()
        result = await self._run(redis, work, [None])
        assert work.runs == 1
        assert result.claimed is True

    @staticmethod
    async def _run(redis, work, published):
        with patch(
            "src.infrastructure.utils.shared_flight.get_redis_cache",
            AsyncMock(return_value=redis),
        ):
            return await run_shared_flight(
                "shared_flight:k",
                build=work,
                read_shared=_reader(published),
                wait_budget_s=0.2,
            )
