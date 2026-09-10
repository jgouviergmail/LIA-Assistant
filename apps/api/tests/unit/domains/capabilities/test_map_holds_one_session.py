"""The capability map reads one table at a time (cold review, 2026-09-10).

Measured on the dev instance with an instrumented session context:
`resolve_capabilities` gathered its eighteen counted probes with
`asyncio.gather`, **each on its own session**, and held EIGHTEEN session
contexts open at the same instant. The pool it draws from is
`database_pool_size` 20 plus `database_max_overflow` 10, so one page load took
most of it and a second reader queued on `database_pool_timeout`.

The measurement that settles it, five runs each, warm, over the counted probes:

| Strategy   | Best latency | Concurrent sessions |
|------------|--------------|---------------------|
| gather     | 10 ms        | 18                  |
| sequential | 21 ms        | 1                   |

Eleven milliseconds buys back seventeen simultaneous sessions on a page that
already costs hundreds. That is the codebase's own rule — « for a handful of
indexed queries, a plain sequential loop is fine and simpler » — applied to the
place that was breaking it.

The figure asserted below is the one that was INSTRUMENTED (session contexts).
`engine.pool.checkedout()` read 24 both before and after the change in a
standalone harness, so it measures something this call does not drive; a number
nobody can attribute is a number this docstring does not quote.

The second half of this module pins what the loop makes structural: the module
docstring promises every probe fails SOFT, and `gather(return_exceptions=False)`
delivered that only because each helper happened to carry its own `try`. A
helper written without one would have taken the whole page down. The guarantee
now lives where the promise is written.
"""

from __future__ import annotations

import asyncio
import uuid
from contextlib import ExitStack
from typing import Any
from unittest.mock import patch

import pytest

from src.domains.capabilities import service as svc

pytestmark = pytest.mark.unit


class _SessionTracker:
    """Counts how many session contexts are open at the same instant."""

    def __init__(self) -> None:
        self.live = 0
        self.peak = 0
        self.entries = 0

    def context(self, *_args: Any, **_kwargs: Any) -> Any:
        tracker = self

        class _Ctx:
            async def __aenter__(self) -> Any:
                tracker.live += 1
                tracker.entries += 1
                tracker.peak = max(tracker.peak, tracker.live)
                # A yield point INSIDE the context: without it every probe
                # would run to completion before the next starts, and a
                # gather would look sequential.
                await asyncio.sleep(0)
                return _FakeSession()

            async def __aexit__(self, *_exc: Any) -> bool:
                tracker.live -= 1
                return False

        return _Ctx()


class _FakeResult:
    @staticmethod
    def scalar() -> int:
        return 3


class _FakeSession:
    async def execute(self, *_args: Any, **_kwargs: Any) -> _FakeResult:
        await asyncio.sleep(0)
        return _FakeResult()


async def _resolve_with(tracker: _SessionTracker, **helpers: Any) -> list[svc.CapabilityProbe]:
    """Resolve the map with every database access counted.

    Args:
        tracker: Counts the session contexts.
        **helpers: Repository-counting helpers to override — a case that wants
            one to RAISE must be able to say so, and a harness that patches
            them unconditionally would silently shadow it.

    Returns:
        The probes.
    """
    user = type(
        "_User",
        (),
        {
            "id": uuid.uuid4(),
            "voice_enabled": False,
            "voice_mode_enabled": False,
            "heartbeat_enabled": False,
            "personality_id": None,
            "image_generation_enabled": False,
        },
    )()
    counters: dict[str, Any] = {
        "_count_peers": _one,
        "_count_workboard": _one,
        "_count_generated_files": _one,
    }
    counters.update(helpers)
    with ExitStack() as stack:
        stack.enter_context(patch.object(svc, "get_db_context", tracker.context))
        stack.enter_context(patch.object(svc, "disabled_capabilities", return_value=frozenset()))
        for name, helper in counters.items():
            stack.enter_context(patch.object(svc, name, helper))
        return await svc.resolve_capabilities(user)  # type: ignore[arg-type]


async def _one(_user_id: uuid.UUID) -> int:
    """A repository-counting helper that answers one, without a database."""
    return 1


class TestTheMapHoldsOneConnection:
    async def test_it_never_opens_two_sessions_at_once(self) -> None:
        tracker = _SessionTracker()

        await _resolve_with(tracker)

        assert tracker.peak == 1, (
            f"the map held {tracker.peak} sessions at once — measured 18 against a "
            "pool of 20+10, so two readers queue on the pool timeout"
        )

    async def test_it_still_reads_every_counted_node(self) -> None:
        # The point is the CONCURRENCY, never the coverage: a loop that stops
        # early would pass the assertion above and draw a blank map.
        tracker = _SessionTracker()

        probes = await _resolve_with(tracker)

        keys = {probe.key for probe in probes}
        assert svc.MAP_NODE_KEYS <= keys, sorted(svc.MAP_NODE_KEYS - keys)


class TestAProbeThatRaisesNeverTakesThePageDown:
    async def test_one_raising_probe_leaves_the_others_readable(self) -> None:
        """The docstring's promise, made structural.

        `gather(return_exceptions=False)` propagated: it only ever looked soft
        because every helper carried its own `try`. One helper written without
        one would have blanked the map.
        """
        tracker = _SessionTracker()

        async def boom(_user_id: uuid.UUID) -> int:
            raise RuntimeError("this table is unreachable")

        probes = await _resolve_with(tracker, _count_workboard=boom)

        by_key = {probe.key: probe for probe in probes}
        assert by_key["workboard"].active is False
        assert by_key["workboard"].detail == 0
        # And the rest of the map is intact.
        assert by_key["memory"].detail == 3

    async def test_a_raising_probe_is_reported_as_not_ready_never_as_absent(self) -> None:
        # « Unavailable » means the instance disabled it; a failed read must
        # not borrow that word, or a reader concludes the feature is off.
        tracker = _SessionTracker()

        async def boom(_user_id: uuid.UUID) -> int:
            raise RuntimeError("nope")

        probes = await _resolve_with(tracker, _count_peers=boom)

        peers = next(probe for probe in probes if probe.key == "peers")
        assert peers.available is True
        assert peers.active is False
