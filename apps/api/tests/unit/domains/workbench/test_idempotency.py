"""A send or a create happens once per submission (ADR-369, ADR-221).

The composer mints one key per message; the route claims it in Redis BEFORE the
provider is called. A second submission with the same key never reaches the
provider: it is told what became of the first — done (with its id), still
pending, or unknown (its answer was lost, so it may have left). Only a CERTAIN
failure frees the key, so the person may try again; a lost answer never does.
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest

from src.core.exceptions import BaseAPIException, ConnectorAPIError, ExternalServiceError
from src.domains.workbench import idempotency
from src.domains.workbench.idempotency import run_once, submission_key
from tests.unit.domains.workbench.fakes import FakeRedis

pytestmark = pytest.mark.unit

USER = uuid4()
_REQUEST = httpx.Request("POST", "https://provider.example/send")


@pytest.fixture
def redis() -> FakeRedis:
    return FakeRedis()


@pytest.fixture(autouse=True)
def _wired(redis: FakeRedis) -> Any:
    with patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=redis)):
        yield


def _detail(raised: pytest.ExceptionInfo[BaseAPIException]) -> Any:
    return raised.value.detail


async def test_a_first_submission_runs_and_remembers_its_result(redis: FakeRedis) -> None:
    key = uuid4()
    calls = AsyncMock(return_value={"id": "sent-1"})

    result = await run_once(USER, key, calls, tool="mail", record=lambda sent: {"id": sent["id"]})

    assert result == {"id": "sent-1"}
    calls.assert_awaited_once()
    assert '"state": "done"' in redis.store[submission_key(USER, key)]


async def test_a_replay_of_a_done_submission_never_calls_the_provider(redis: FakeRedis) -> None:
    key = uuid4()
    await run_once(
        USER,
        key,
        AsyncMock(return_value={"id": "sent-1"}),
        tool="mail",
        record=lambda sent: {"id": sent["id"]},
    )
    second = AsyncMock()

    with pytest.raises(BaseAPIException) as raised:
        await run_once(USER, key, second, tool="mail")

    second.assert_not_awaited()
    assert raised.value.status_code == 409
    assert _detail(raised) == {"code": "already_submitted", "outcome": "done", "id": "sent-1"}


async def test_a_replay_while_the_first_runs_says_pending(redis: FakeRedis) -> None:
    key = uuid4()
    started = asyncio.Event()
    release = asyncio.Event()

    async def slow() -> dict[str, str]:
        started.set()
        await release.wait()
        return {"id": "slow"}

    first = asyncio.create_task(run_once(USER, key, slow, tool="mail"))
    await started.wait()
    with pytest.raises(BaseAPIException) as raised:
        await run_once(USER, key, AsyncMock(), tool="mail")
    release.set()
    await first

    assert _detail(raised) == {"code": "already_submitted", "outcome": "pending"}


async def test_a_lost_answer_is_unknown_and_its_replay_says_so(redis: FakeRedis) -> None:
    key = uuid4()

    async def lost() -> None:
        try:
            raise httpx.ReadTimeout("lost", request=_REQUEST)
        except httpx.ReadTimeout as timeout:
            raise ExternalServiceError(service_name="google_gmail") from timeout

    with pytest.raises(ExternalServiceError):
        await run_once(USER, key, lost, tool="mail")
    with pytest.raises(BaseAPIException) as raised:
        await run_once(USER, key, AsyncMock(), tool="mail")

    assert _detail(raised) == {"code": "already_submitted", "outcome": "unknown"}


async def test_a_certain_failure_frees_the_key_for_another_try(redis: FakeRedis) -> None:
    key = uuid4()
    refused = AsyncMock(
        side_effect=ConnectorAPIError(connector_type="google_gmail", status_code=400, detail="x")
    )
    with pytest.raises(ConnectorAPIError):
        await run_once(USER, key, refused, tool="mail")

    retry = AsyncMock(return_value={"id": "sent-2"})
    assert await run_once(USER, key, retry, tool="mail") == {"id": "sent-2"}
    retry.assert_awaited_once()


async def test_a_cancelled_submission_is_written_unknown(redis: FakeRedis) -> None:
    key = uuid4()
    started = asyncio.Event()

    async def forever() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(run_once(USER, key, forever, tool="mail"))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert '"state": "unknown"' in redis.store[submission_key(USER, key)]


async def test_the_key_lives_as_long_as_the_setting_says(redis: FakeRedis) -> None:
    key = uuid4()
    await run_once(USER, key, AsyncMock(return_value=None), tool="mail")
    assert (
        redis.ttls[submission_key(USER, key)]
        == idempotency.settings.workbench_idempotency_ttl_seconds
    )


async def test_a_broken_cache_never_makes_the_send_fail() -> None:
    """Our own guard is never the reason a request fails (ADR-254 doctrine)."""
    broken = FakeRedis(broken=True)
    operation = AsyncMock(return_value={"id": "sent"})
    with (
        patch.object(idempotency, "get_redis_cache", AsyncMock(return_value=broken)),
        patch.object(idempotency, "workbench_idempotency_unguarded_total") as unguarded,
    ):
        assert await run_once(USER, uuid4(), operation, tool="mail") == {"id": "sent"}
    unguarded.labels.assert_called_once_with(tool="mail")


async def test_two_accounts_never_share_a_key() -> None:
    key = uuid4()
    assert submission_key(USER, key) != submission_key(uuid4(), key)
    assert submission_key(USER, key).startswith("workbench:idem:")


@pytest.mark.parametrize(
    "stored", ['{"state": "exploded"}', "{not json", '{"id": "x"}', '["state", "done"]']
)
async def test_an_unreadable_stored_outcome_reads_as_pending(redis: FakeRedis, stored: str) -> None:
    """Corrupted or foreign: the answer that never invites a second send."""
    key = uuid4()
    redis.store[submission_key(USER, key)] = stored
    second = AsyncMock()

    with pytest.raises(BaseAPIException) as raised:
        await run_once(USER, key, second, tool="mail")

    second.assert_not_awaited()
    assert _detail(raised) == {"code": "already_submitted", "outcome": "pending"}
