"""A lease says LIA is busy; it never names a stream nobody writes (point 25b).

Two kinds of run hold a conversation's active-run lock. The chat producer
RELAYS its chunks through the run stream, so a client may follow it, reattach
to it, or stop it. A lease — a workboard ticket, a voice relay, a voice
delegation — runs the turn itself and publishes nothing there. It used to be
served exactly like the first kind: ``/runs/active`` and the 409 handed the
client its stream id, the client reattached to a stream that never received a
chunk, and Stop answered « cancelled » while nothing listened for the signal.

The lock records which kind it is, and every client-facing read goes through
one view of it. Only Redis is replaced here: the lock is taken by the real
broker functions and read by the real routes.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import suppress
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from src.core.config import settings
from src.domains.agents.api import router as agents_router
from src.domains.users.models import User
from src.infrastructure.streaming.run_stream_broker import (
    active_run_key,
    active_run_lease,
    heartbeat_active_run,
    public_active_run,
    register_active_run,
)

pytestmark = pytest.mark.unit

CONVERSATION = "c-1"


class _Locks:
    """The active-run lock and the cancel signal, in memory.

    ``SET NX`` and the two owner-conditional scripts behave as on the server;
    nothing else of Redis is needed by these routes.
    """

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    async def set(self, key: str, value: str, nx: bool = False, ex: int | None = None) -> Any:
        if nx and key in self.values:
            return None
        self.values[key] = value
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def eval(self, script: str, _numkeys: int, key: str, stream_id: str, *_args: Any) -> int:
        raw = self.values.get(key)
        if raw is None or json.loads(raw)["stream_id"] != stream_id:
            return 0
        if "DEL" in script:
            del self.values[key]
        return 1


@pytest.fixture
def locks(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Locks]:
    """Routes wired to the in-memory locks, for one conversation."""
    store = _Locks()
    monkeypatch.setattr(settings, "background_runs_enabled", True, raising=False)
    with (
        patch(
            "src.infrastructure.cache.get_conversation_id_cached",
            AsyncMock(return_value=CONVERSATION),
        ),
        patch("src.infrastructure.cache.redis.get_redis_cache", AsyncMock(return_value=store)),
    ):
        yield store


def _user() -> User:
    return User(id=uuid4(), email="visibility@test.local", hashed_password="x")


class TestALeaseNamesNoStream:
    async def test_lia_is_busy_but_there_is_no_stream_to_follow(self, locks: _Locks) -> None:
        async with active_run_lease(
            locks, CONVERSATION, run_id="run-1", stream_id="workboard:run-1"
        ) as acquired:
            assert acquired
            status = await agents_router.get_active_run_status(current_user=_user())

        assert status == {"active": True, "run_id": "run-1", "stream_id": None}

    async def test_stop_does_not_claim_to_cancel_what_nothing_listens_to(
        self, locks: _Locks
    ) -> None:
        async with active_run_lease(
            locks, CONVERSATION, run_id="run-1", stream_id="workboard:run-1"
        ):
            answer = await agents_router.cancel_active_run(current_user=_user())
            signals = [key for key in locks.values if key != active_run_key(CONVERSATION)]

        assert answer == {"cancelled": False}
        assert signals == []

    async def test_a_lease_stream_cannot_be_reattached(self, locks: _Locks) -> None:
        async with active_run_lease(
            locks, CONVERSATION, run_id="run-1", stream_id="workboard:run-1"
        ):
            with pytest.raises(HTTPException) as refused:
                await agents_router.reattach_run_stream(
                    "workboard:run-1", current_user=_user(), lia_session=None
                )

        assert refused.value.status_code == 404

    async def test_a_lease_that_re_takes_its_lock_stays_a_lease(
        self, locks: _Locks, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The heartbeat re-takes an EXPIRED lock with a payload of its own:
        written as a chat run's, the lease would hand out its stream again."""
        monkeypatch.setattr(settings, "background_runs_heartbeat_seconds", 0, raising=False)
        beat = asyncio.create_task(
            heartbeat_active_run(
                locks, CONVERSATION, "workboard:run-1", run_id="run-1", relayed=False
            )
        )
        for _ in range(5):
            await asyncio.sleep(0)
        beat.cancel()
        with suppress(asyncio.CancelledError):
            await beat

        retaken = json.loads(locks.values[active_run_key(CONVERSATION)])
        assert retaken["relayed"] is False


class TestAChatRunStillNamesItsStream:
    async def test_the_producer_s_stream_is_followed_and_stopped(self, locks: _Locks) -> None:
        await register_active_run(locks, CONVERSATION, run_id="s-1", stream_id="s-1")

        status = await agents_router.get_active_run_status(current_user=_user())
        stopped = await agents_router.cancel_active_run(current_user=_user())

        assert status == {"active": True, "run_id": "s-1", "stream_id": "s-1"}
        assert stopped == {"cancelled": True, "stream_id": "s-1"}

    async def test_a_lock_written_before_the_field_existed_reads_as_relayed(self) -> None:
        legacy = {"run_id": "s-1", "stream_id": "s-1"}

        assert public_active_run(legacy) == {"run_id": "s-1", "stream_id": "s-1"}
        assert public_active_run(None) is None
