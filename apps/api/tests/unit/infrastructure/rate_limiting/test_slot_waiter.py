"""Bounded wait for a distributed rate-limit slot.

The existing ``RedisRateLimiter.acquire`` answers yes/no and returns; it never
waits. That is right for an HTTP guard — a rejected request should be rejected
now — and wrong for background work against a provider quota, where the honest
answer is "in a moment".

This module is what turns the one into the other, and every test below pins a
property that decides whether an outage is caused or avoided:

- it is a SHAPER, not a gate: a caller is never blocked forever, and a wait
  that expires still lets the work through;
- Redis being unavailable must not stop embeddings — the limiter is an
  optimisation, not a dependency;
- disabling it costs no Redis round-trip at all.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from src.infrastructure.rate_limiting.slot_waiter import SlotOutcome, wait_for_slot

pytestmark = pytest.mark.unit

_TARGET = "src.infrastructure.rate_limiting.slot_waiter.get_rate_limiter"


def _limiter(*answers: bool) -> AsyncMock:
    limiter = AsyncMock()
    limiter.acquire = AsyncMock(side_effect=list(answers))
    return limiter


class TestSlotIsAvailable:
    async def test_returns_true_without_waiting_when_the_slot_is_free(self) -> None:
        limiter = _limiter(True)
        slept: list[float] = []

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            with patch("asyncio.sleep", AsyncMock(side_effect=lambda s: slept.append(s))):
                granted = await wait_for_slot(
                    "k", max_calls=10, window_seconds=60, timeout_seconds=2
                )

        assert granted is SlotOutcome.ACQUIRED
        assert slept == [], "a free slot must cost no delay at all"
        assert limiter.acquire.await_count == 1

    async def test_waits_and_retries_until_a_slot_frees(self) -> None:
        limiter = _limiter(False, False, True)
        slept: list[float] = []

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            with patch("asyncio.sleep", AsyncMock(side_effect=lambda s: slept.append(s))):
                granted = await wait_for_slot(
                    "k", max_calls=1, window_seconds=60, timeout_seconds=5, poll_seconds=0.2
                )

        assert granted is SlotOutcome.ACQUIRED
        assert limiter.acquire.await_count == 3
        assert slept == [0.2, 0.2]


class TestItNeverBlocksForever:
    async def test_gives_up_after_the_deadline_and_says_so(self) -> None:
        """False means "we waited our share" — the CALLER decides what to do,
        and for embeddings it proceeds: throttling our own background work into
        oblivion would be a worse outage than a provider 429.

        The clock is SIMULATED rather than mocked away: a fake sleep that does
        not advance time makes the deadline unreachable and the loop spin, so
        the oracle has to move the clock by exactly what the code slept.
        """
        limiter = _limiter(*[False] * 50)
        slept: list[float] = []
        now = [1000.0]

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            with patch("asyncio.sleep", fake_sleep):
                with patch(
                    "src.infrastructure.rate_limiting.slot_waiter.time.monotonic",
                    lambda: now[0],
                ):
                    granted = await wait_for_slot(
                        "k",
                        max_calls=1,
                        window_seconds=60,
                        timeout_seconds=1.0,
                        poll_seconds=0.25,
                    )

        assert granted is SlotOutcome.EXPIRED
        assert sum(slept) <= 1.0 + 1e-9, "the wait must respect its own budget"
        assert limiter.acquire.await_count == 5, "4 waits of 0.25s, then one last probe"

    async def test_the_final_poll_is_clipped_to_what_is_left_of_the_budget(self) -> None:
        """A poll longer than the remaining time would overshoot the deadline."""
        limiter = _limiter(*[False] * 10)
        slept: list[float] = []
        now = [0.0]

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            with patch("asyncio.sleep", fake_sleep):
                with patch(
                    "src.infrastructure.rate_limiting.slot_waiter.time.monotonic",
                    lambda: now[0],
                ):
                    await wait_for_slot(
                        "k",
                        max_calls=1,
                        window_seconds=60,
                        timeout_seconds=0.6,
                        poll_seconds=0.25,
                    )

        assert slept == [0.25, 0.25, pytest.approx(0.1)]

    async def test_a_zero_timeout_is_a_single_non_blocking_probe(self) -> None:
        limiter = _limiter(False)
        slept: list[float] = []

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            with patch("asyncio.sleep", AsyncMock(side_effect=lambda s: slept.append(s))):
                granted = await wait_for_slot(
                    "k", max_calls=1, window_seconds=60, timeout_seconds=0
                )

        assert granted is SlotOutcome.EXPIRED
        assert limiter.acquire.await_count == 1
        assert slept == []


class TestItFailsOpen:
    async def test_a_redis_failure_never_blocks_the_caller(self) -> None:
        """The limiter shapes traffic; it does not own the right to stop it.
        A Redis outage that silenced every embedding would turn a degraded
        provider into a degraded assistant."""
        limiter = AsyncMock()
        limiter.acquire = AsyncMock(side_effect=RuntimeError("redis down"))

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            granted = await wait_for_slot("k", max_calls=1, window_seconds=60, timeout_seconds=5)

        assert granted is SlotOutcome.UNAVAILABLE

    async def test_a_limiter_that_cannot_be_built_is_not_an_error(self) -> None:
        with patch(_TARGET, AsyncMock(side_effect=RuntimeError("no redis"))):
            granted = await wait_for_slot("k", max_calls=1, window_seconds=60, timeout_seconds=5)

        assert granted is SlotOutcome.UNAVAILABLE


class TestItCanBeDisabled:
    @pytest.mark.parametrize("max_calls", [0, -1])
    async def test_a_non_positive_limit_means_OFF_and_touches_no_redis(
        self, max_calls: int
    ) -> None:
        """An operator turning the shaper off must not pay a round-trip for it,
        and must not be told the slot was refused."""
        built = AsyncMock()

        with patch(_TARGET, built):
            granted = await wait_for_slot(
                "k", max_calls=max_calls, window_seconds=60, timeout_seconds=5
            )

        assert granted is SlotOutcome.DISABLED
        built.assert_not_awaited()


class TestTheWaitCannotBecomeItsOwnLoad:
    async def test_a_zero_poll_interval_is_floored(self) -> None:
        """A shaper that spins on Redis would be load, not relief.

        `min(poll_seconds, remaining)` with a zero interval sleeps zero and
        loops — thousands of probes across a sub-second budget, against the very
        component the shaper exists to protect.
        """
        limiter = _limiter(*([False] * 200))
        slept: list[float] = []
        now = [0.0]

        async def fake_sleep(seconds: float) -> None:
            slept.append(seconds)
            now[0] += seconds

        with patch(_TARGET, AsyncMock(return_value=limiter)):
            with patch("asyncio.sleep", AsyncMock(side_effect=fake_sleep)):
                with patch("time.monotonic", side_effect=lambda: now[0]):
                    await wait_for_slot(
                        "k",
                        max_calls=1,
                        window_seconds=60,
                        timeout_seconds=1.0,
                        poll_seconds=0.0,
                    )

        assert slept, "a refused slot must wait before probing again"
        # `1e-9`: the LAST wait is legitimately clipped to what remains of the
        # budget, and floating-point accumulation lands it a hair under.
        assert min(slept) >= 0.01 - 1e-9, "the poll interval has a floor"
        assert limiter.acquire.await_count <= 101


class TestTheOutcomeDistinguishesWhatAnOperatorMustDo:
    """`expired` and `unavailable` ask for opposite actions.

    Raising the budget will not fix a Redis outage, and restarting Redis will
    not fix a budget too small for the number of users. A boolean collapsed the
    two into one indistinguishable "false".
    """

    async def test_a_full_shaper_and_a_missing_redis_are_not_the_same_verdict(
        self,
    ) -> None:
        full = _limiter(False)
        with patch(_TARGET, AsyncMock(return_value=full)):
            with patch("asyncio.sleep", AsyncMock()):
                expired = await wait_for_slot(
                    "k", max_calls=1, window_seconds=60, timeout_seconds=0
                )

        with patch(_TARGET, AsyncMock(side_effect=RuntimeError("redis down"))):
            unavailable = await wait_for_slot(
                "k", max_calls=1, window_seconds=60, timeout_seconds=0
            )

        assert expired is SlotOutcome.EXPIRED
        assert unavailable is SlotOutcome.UNAVAILABLE
        assert expired is not unavailable

    async def test_every_outcome_is_a_distinct_metric_label(self) -> None:
        """The counter is labelled with `.value`; two equal labels would merge
        two different situations into one line on the chart."""
        values = [outcome.value for outcome in SlotOutcome]
        assert len(values) == len(set(values)) == 4
