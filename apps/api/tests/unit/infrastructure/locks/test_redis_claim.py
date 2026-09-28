"""The owner-token claim primitive (ADR-298, extracted from shared_flight).

One implementation of "SET NX with a token, compare-and-delete to release"
for every caller that must never delete a claim it no longer owns.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from src.infrastructure.locks import redis_claim
from src.infrastructure.locks.redis_claim import (
    REFRESH_SCRIPT,
    ClaimLost,
    acquire_claim,
    held_claim,
    release_claim,
    try_claim,
)

pytestmark = pytest.mark.unit


class FakeRedis:
    """SET NX / EVAL running the two owner scripts: compare-and-delete and
    compare-and-refresh."""

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

    async def eval(self, script: str, numkeys: int, *args):
        self.ops["eval"] += 1
        if script != REFRESH_SCRIPT:
            self.ops["release"] += 1
        if self.broken:
            raise ConnectionError("redis down")
        key, token = args[0], args[1]
        if self.store.get(key) != token:
            return 0
        if script == REFRESH_SCRIPT:
            self.ops["refresh"] += 1
            return 1
        del self.store[key]
        return 1


class TestTryClaim:
    async def test_a_free_key_is_taken_with_the_owner_token(self) -> None:
        redis = FakeRedis()
        assert await try_claim(redis, "k", "owner-1", ttl_seconds=5) is True
        assert redis.store["k"] == "owner-1"

    async def test_a_held_key_is_refused(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "owner-1", ttl_seconds=5)
        assert await try_claim(redis, "k", "owner-2", ttl_seconds=5) is False
        assert redis.store["k"] == "owner-1"

    async def test_a_cache_failure_propagates(self) -> None:
        """The primitive reports the truth; each caller decides whether a
        failure means "build anyway" (shared flight) or "refuse" (egress)."""
        with pytest.raises(ConnectionError):
            await try_claim(FakeRedis(broken=True), "k", "t", ttl_seconds=5)


class TestReleaseClaim:
    async def test_the_owner_releases(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "owner-1", ttl_seconds=5)
        assert await release_claim(redis, "k", "owner-1") is True
        assert "k" not in redis.store

    async def test_a_successor_claim_is_never_deleted(self) -> None:
        """SET NX then an unconditional DELETE is the forbidden shape."""
        redis = FakeRedis()
        redis.store["k"] = "successor"
        assert await release_claim(redis, "k", "stale-owner") is False
        assert redis.store["k"] == "successor"

    async def test_a_cache_failure_on_release_is_swallowed(self) -> None:
        """A claim that could not be released expires by its TTL."""
        assert await release_claim(FakeRedis(broken=True), "k", "t") is False


class TestAcquireClaim:
    async def test_waits_for_a_holder_then_takes_over(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=5)

        async def _holder_releases() -> None:
            await asyncio.sleep(0.03)
            await release_claim(redis, "k", "holder")

        asyncio.get_running_loop().create_task(_holder_releases())
        token = await acquire_claim(redis, "k", ttl_seconds=5, wait_seconds=1.0, poll_seconds=0.01)
        assert token is not None
        assert redis.store["k"] == token

    async def test_gives_up_when_the_budget_runs_out(self) -> None:
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=5)
        token = await acquire_claim(redis, "k", ttl_seconds=5, wait_seconds=0.05, poll_seconds=0.01)
        assert token is None
        assert redis.store["k"] == "holder"


class TestHeldClaim:
    """A claim held while its work runs: re-armed, taken back, or given up."""

    _TTL = 1  # the fake keeps no clock: only the refresh period matters here
    _REFRESH = 0.01

    async def _hold(self, redis: FakeRedis, body) -> None:
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        async with held_claim(
            redis, "k", "holder", ttl_seconds=self._TTL, refresh_seconds=self._REFRESH
        ):
            await body()

    async def test_the_claim_is_re_armed_while_the_work_runs_then_released(self) -> None:
        redis = FakeRedis()

        async def _work() -> None:
            await asyncio.sleep(self._REFRESH * 5)
            assert redis.store["k"] == "holder"

        await self._hold(redis, _work)

        assert redis.ops["refresh"] >= 2
        assert "k" not in redis.store

    async def test_an_expired_claim_nobody_took_is_taken_back(self) -> None:
        """A cache outage longer than the margin is nobody's loss."""
        redis = FakeRedis()

        async def _work() -> None:
            del redis.store["k"]  # expired while the cache was away
            await asyncio.sleep(self._REFRESH * 5)
            assert redis.store["k"] == "holder"

        await self._hold(redis, _work)

    async def test_a_successor_stops_the_work_and_keeps_its_claim(self) -> None:
        redis = FakeRedis()
        effects: list[str] = []

        async def _work() -> None:
            redis.store["k"] = "successor"  # expired, then taken by the next turn
            await asyncio.sleep(self._REFRESH * 50)
            effects.append("written beside the successor")

        with pytest.raises(ClaimLost) as lost:
            await self._hold(redis, _work)

        assert lost.value.reason == "taken_over"
        assert effects == []
        assert redis.store["k"] == "successor"
        # The successor's claim is not even asked to be released.
        assert redis.ops["release"] == 0

    async def test_an_unreachable_cache_stops_nothing(self) -> None:
        redis = FakeRedis()

        async def _work() -> None:
            redis.broken = True
            await asyncio.sleep(self._REFRESH * 5)
            redis.broken = False
            await asyncio.sleep(self._REFRESH * 5)

        await self._hold(redis, _work)

        assert "k" not in redis.store

    async def test_a_cancellation_that_is_not_the_keeper_s_stays_one(self) -> None:
        """Shutdown or a caller's timeout is no lost claim — and still releases."""
        redis = FakeRedis()
        started = asyncio.Event()

        async def _work() -> None:
            started.set()
            await asyncio.Event().wait()

        holder = asyncio.create_task(self._hold(redis, _work))
        await started.wait()
        holder.cancel()
        with pytest.raises(asyncio.CancelledError):
            await holder

        assert "k" not in redis.store


def _keeper_firing_on(
    fire: asyncio.Event, reason: str = "taken_over"
) -> Callable[..., Awaitable[None]]:
    """A stand-in keeper that reports the claim lost when the test says so."""

    async def _keep(*_args: Any, on_stop: Callable[[str], None], **_kwargs: Any) -> None:
        await fire.wait()
        on_stop(reason)

    return _keep


def _keeper_slow_to_stop(
    running: asyncio.Event, stopping: asyncio.Event, let_it_stop: asyncio.Event
) -> Callable[..., Awaitable[None]]:
    """A stand-in keeper that, once cancelled, stops only when the test says so."""

    async def _keep(*_args: Any, **_kwargs: Any) -> None:
        try:
            running.set()
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            stopping.set()
            await let_it_stop.wait()
            raise

    return _keep


class _SlowReleaseRedis(FakeRedis):
    """A release that waits until the test lets it finish."""

    def __init__(self) -> None:
        super().__init__()
        self.releasing = asyncio.Event()
        self.let_release = asyncio.Event()

    async def eval(self, script: str, numkeys: int, *args):
        if script != REFRESH_SCRIPT:
            self.releasing.set()
            await self.let_release.wait()
        return await super().eval(script, numkeys, *args)


class TestHeldClaimEdges:
    """Whose cancellation is whose, how a hold ends, and what is never released."""

    _TTL = 1
    _REFRESH = 0.01

    @pytest.mark.parametrize("refresh", [0.0, -1.0, 1.0, 2.0])
    async def test_a_refresh_period_outside_the_ttl_is_refused(self, refresh: float) -> None:
        """At or past the TTL the claim could expire between two refreshes."""
        with pytest.raises(ValueError):
            async with held_claim(
                FakeRedis(), "k", "t", ttl_seconds=self._TTL, refresh_seconds=refresh
            ):
                pytest.fail("a refused period must not enter the block")

    async def test_a_hold_past_its_bound_is_stopped_and_released(self) -> None:
        """A wedged holder cannot keep the claim for the life of its process."""
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)

        with pytest.raises(ClaimLost) as lost:
            async with held_claim(
                redis,
                "k",
                "holder",
                ttl_seconds=self._TTL,
                refresh_seconds=self._REFRESH,
                max_hold_seconds=self._REFRESH * 2,
            ):
                await asyncio.sleep(self._REFRESH * 100)

        assert lost.value.reason == "hold_exhausted"
        assert "k" not in redis.store

    async def test_a_foreign_cancellation_landing_with_the_keeper_s_propagates(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A shutdown in the same step as the loss stays a cancellation."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire))
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()

        async def _hold() -> None:
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                entered.set()
                await asyncio.Event().wait()

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        await asyncio.sleep(0)  # the keeper runs and cancels the block
        holder.cancel()  # a shutdown lands before the block has resumed
        with pytest.raises(asyncio.CancelledError):
            await holder

    async def test_a_block_that_swallows_the_keeper_s_cancellation_still_loses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Its later effects ran unprotected: that is still a lost claim."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire))
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()

        async def _hold() -> None:
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                entered.set()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.Event().wait()

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        with pytest.raises(ClaimLost) as lost:
            await holder

        assert lost.value.reason == "taken_over"
        assert redis.ops["release"] == 0

    async def test_a_cancellation_during_the_unwind_propagates_once_released(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """While the unwind waits for the keeper, a cancellation is the caller's
        — and it used to skip the release, keeping the claim until its TTL."""
        keeper_running = asyncio.Event()
        keeper_stopping = asyncio.Event()
        let_it_stop = asyncio.Event()
        monkeypatch.setattr(
            redis_claim,
            "_keep_claim",
            _keeper_slow_to_stop(keeper_running, keeper_stopping, let_it_stop),
        )
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)

        async def _hold() -> None:
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                # A task cancelled before its first step never runs its own
                # handler: the block ends once the keeper is running.
                await keeper_running.wait()

        holder = asyncio.create_task(_hold())
        await keeper_stopping.wait()
        holder.cancel()
        await asyncio.sleep(0)  # delivered while the unwind waits for the keeper
        let_it_stop.set()
        with pytest.raises(asyncio.CancelledError):
            await holder

        assert "k" not in redis.store

    async def test_what_the_keeper_does_while_stopping_lands_before_the_release(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A re-take the keeper had under way when it was cancelled lands before
        the release, never after it — where it would hold the claim for a TTL."""
        redis = FakeRedis()
        keeper_running = asyncio.Event()

        async def _retakes_while_stopping(*_args: Any, **_kwargs: Any) -> None:
            try:
                keeper_running.set()
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                await asyncio.sleep(0)  # the re-take's round trip
                redis.store["k"] = "holder"
                raise

        monkeypatch.setattr(redis_claim, "_keep_claim", _retakes_while_stopping)
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)

        async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
            await keeper_running.wait()

        assert "k" not in redis.store
        assert not [
            task
            for task in asyncio.all_tasks()
            if task.get_name() == redis_claim.KEEPER_TASK_NAME and not task.done()
        ]

    async def test_a_block_that_turns_the_keeper_s_cancellation_into_a_failure_loses(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The failure used to propagate as the block's own, with the keeper's
        cancellation request left on the task — which then refuses to clear a
        later one (``uncancel`` stops at a leaked count)."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire))
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()
        requests_left: list[int] = []

        async def _hold() -> None:
            this = asyncio.current_task()
            assert this is not None
            try:
                async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                    entered.set()
                    try:
                        await asyncio.Event().wait()
                    except asyncio.CancelledError as exc:
                        raise RuntimeError("the block's own wrapping") from exc
            finally:
                requests_left.append(this.cancelling())

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        with pytest.raises(ClaimLost) as lost:
            await holder

        assert lost.value.reason == "taken_over"
        assert isinstance(lost.value.__cause__, RuntimeError)
        assert requests_left == [0]

    async def test_a_request_pending_before_the_hold_is_not_the_keeper_s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A task that swallowed a cancellation before taking the claim carries
        its request in: the keeper's own is still told apart from it."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire))
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()

        async def _hold() -> None:
            this = asyncio.current_task()
            assert this is not None
            this.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.sleep(0)
            assert this.cancelling() == 1
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                entered.set()
                await asyncio.Event().wait()

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        with pytest.raises(ClaimLost):
            await holder

    async def test_a_failure_made_of_the_keeper_s_cancellation_loses_beside_a_foreign_one(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Only a CANCELLATION leaving another request pending is somebody
        else's: a block that wrapped the keeper's into a failure lost the claim,
        whatever else was pending when it did."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire))
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()

        async def _hold() -> None:
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                entered.set()
                try:
                    await asyncio.Event().wait()
                except asyncio.CancelledError as exc:
                    raise RuntimeError("the block's own wrapping") from exc

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        await asyncio.sleep(0)  # the keeper runs and cancels the block
        holder.cancel()  # a foreign request lands before the block has resumed
        with pytest.raises(ClaimLost) as lost:
            await holder

        assert isinstance(lost.value.__cause__, RuntimeError)

    async def test_a_swallowed_loss_stays_a_loss_beside_a_foreign_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The block swallowed ONE cancellation carrying the keeper's request and
        a foreign one, then returned: its later effects ran unprotected all the
        same, so the exit is the loss — never a clean return."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire))
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()

        async def _hold() -> None:
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                entered.set()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.Event().wait()

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        await asyncio.sleep(0)  # the keeper runs and cancels the block
        holder.cancel()  # a foreign request lands before the block has resumed
        with pytest.raises(ClaimLost):
            await holder

    async def test_a_cancellation_during_the_release_of_a_swallowed_loss_is_the_caller_s(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The block swallowed the keeper's cancellation and returned; the
        caller's own lands while the claim is released. The keeper's request
        used to be withdrawn only after the release, so the task ended carrying
        two where one is the caller's."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire, "hold_exhausted"))
        redis = _SlowReleaseRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)
        entered = asyncio.Event()
        requests_left: list[int] = []

        async def _hold() -> None:
            this = asyncio.current_task()
            assert this is not None
            try:
                async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                    entered.set()
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.Event().wait()
            finally:
                requests_left.append(this.cancelling())

        holder = asyncio.create_task(_hold())
        await entered.wait()
        fire.set()
        await redis.releasing.wait()
        holder.cancel()  # the caller's cancellation, while the claim is released
        await asyncio.sleep(0)
        redis.let_release.set()
        with pytest.raises(asyncio.CancelledError):
            await holder

        assert requests_left == [1]
        assert "k" not in redis.store

    async def test_a_timeout_falling_in_that_release_stays_a_timeout(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """What the leaked request broke: ``asyncio.timeout`` recognises its own
        cancellation by the count, and a deadline falling while the claim was
        released left as a bare cancellation instead of ``TimeoutError``."""
        fire = asyncio.Event()
        monkeypatch.setattr(redis_claim, "_keep_claim", _keeper_firing_on(fire, "hold_exhausted"))
        redis = _SlowReleaseRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)

        deadlines: list[asyncio.Timeout] = []

        async def _hold() -> None:
            # Armed with no deadline, and set only once the release is under way:
            # a deadline armed before would land wherever the loop happened to be.
            async with asyncio.timeout(None) as deadline:
                deadlines.append(deadline)
                async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                    fire.set()
                    with contextlib.suppress(asyncio.CancelledError):
                        await asyncio.Event().wait()

        holder = asyncio.create_task(_hold())
        await redis.releasing.wait()
        deadlines[0].reschedule(asyncio.get_running_loop().time())
        await asyncio.sleep(0)  # the deadline fires while the claim is released
        await asyncio.sleep(0)
        redis.let_release.set()
        with pytest.raises(TimeoutError):
            await holder

        assert "k" not in redis.store

    @pytest.mark.parametrize(("deliveries", "waited"), [(2, True), (3, False)])
    async def test_the_release_is_waited_through_two_cancellations_never_a_third(
        self, monkeypatch: pytest.MonkeyPatch, deliveries: int, waited: bool
    ) -> None:
        """Two re-delivered cancellations are waited through; the third leaves
        the release to finish on its own — a shutdown is never held open for
        it — and the claim is released all the same."""
        running, stopping, let_it_stop = asyncio.Event(), asyncio.Event(), asyncio.Event()
        monkeypatch.setattr(
            redis_claim, "_keep_claim", _keeper_slow_to_stop(running, stopping, let_it_stop)
        )
        redis = FakeRedis()
        await try_claim(redis, "k", "holder", ttl_seconds=self._TTL)

        async def _hold() -> None:
            async with held_claim(redis, "k", "holder", ttl_seconds=self._TTL):
                await running.wait()

        holder = asyncio.create_task(_hold())
        await stopping.wait()
        for _ in range(deliveries):
            holder.cancel()
            await asyncio.sleep(0)
            await asyncio.sleep(0)

        assert holder.done() is not waited
        let_it_stop.set()
        with pytest.raises(asyncio.CancelledError):
            await holder
        await asyncio.gather(
            *(task for task in asyncio.all_tasks() if task.get_name() == "redis_claim_settle")
        )
        assert "k" not in redis.store
