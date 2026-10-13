"""Native workers abort remote work on failed renewal and never leak their scope."""

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.domains.rag_spaces import source_worker_runtime as runtime
from src.domains.rag_spaces.source_worker_lease import (
    SourceLeaseLost,
    SourceWorkerLease,
    current_source_worker,
    source_worker_scope,
)

pytestmark = pytest.mark.unit


def scope():
    return SourceWorkerLease("drive", uuid4(), uuid4(), uuid4(), "native-owned")


async def test_legacy_remote_call_does_not_renew_or_install_a_scope(monkeypatch):
    renewal = AsyncMock()
    monkeypatch.setattr(runtime, "renew_native_source", renewal)
    assert await runtime.source_worker_external(AsyncMock(return_value="value")) == "value"
    renewal.assert_not_awaited()


async def test_failed_initial_renewal_never_starts_provider(monkeypatch):
    provider = AsyncMock()
    monkeypatch.setattr(runtime, "renew_native_source", AsyncMock(side_effect=SourceLeaseLost()))
    with source_worker_scope(scope()), pytest.raises(SourceLeaseLost):
        await runtime.source_worker_external(provider)
    provider.assert_not_awaited()
    assert current_source_worker() is None


@pytest.mark.parametrize("mismatch", ["source", "kind", "owner"])
async def test_native_heartbeat_refuses_a_different_target_before_sql(monkeypatch, mismatch):
    from src.domains.rag_spaces import jobs_repository

    lease = scope()
    db = AsyncMock()
    fence = AsyncMock(side_effect=SourceLeaseLost())
    monkeypatch.setattr(jobs_repository, "require_source_worker", fence)
    source_id = uuid4() if mismatch == "source" else lease.source_id
    table = (
        jobs_repository.MAIL_SOURCE_TABLE
        if mismatch == "kind"
        else jobs_repository.DRIVE_SOURCE_TABLE
    )
    worker_id = "other" if mismatch == "owner" else lease.worker_id
    with source_worker_scope(lease), pytest.raises(SourceLeaseLost):
        await jobs_repository.RAGJobsRepository(db).heartbeat_source(
            source_id, 60, table=table, worker_id=worker_id
        )
    db.execute.assert_not_awaited()


async def test_native_heartbeat_false_cannot_be_ignored(monkeypatch):
    from unittest.mock import MagicMock

    from src.domains.rag_spaces import jobs_repository

    db = AsyncMock()
    db.execute.return_value = MagicMock(rowcount=0)
    monkeypatch.setattr(jobs_repository, "require_source_worker", AsyncMock())
    lease = scope()
    with source_worker_scope(lease), pytest.raises(SourceLeaseLost):
        await jobs_repository.RAGJobsRepository(db).heartbeat_source(lease.source_id, 60)
    assert db.execute.await_args.args[1]["wid"] == lease.worker_id


async def test_failed_periodic_renewal_cancels_inflight_provider(monkeypatch):
    entered = asyncio.Event()
    cancelled = asyncio.Event()
    never = asyncio.Event()

    async def provider():
        entered.set()
        try:
            await never.wait()
        finally:
            cancelled.set()

    async def renewal():
        if entered.is_set():
            raise SourceLeaseLost()

    monkeypatch.setattr(runtime, "renew_native_source", renewal)
    monkeypatch.setattr(runtime, "_heartbeat_interval", lambda: 0.001)
    with source_worker_scope(scope()), pytest.raises(SourceLeaseLost):
        await asyncio.wait_for(runtime.source_worker_external(provider), timeout=1)
    assert cancelled.is_set()
    assert current_source_worker() is None


async def test_success_and_cancellation_join_the_renewal_task(monkeypatch):
    renewal = AsyncMock()
    monkeypatch.setattr(runtime, "renew_native_source", renewal)
    with source_worker_scope(scope()):
        assert await runtime.source_worker_external(AsyncMock(return_value="done")) == "done"
        task = asyncio.create_task(runtime.source_worker_external(lambda: asyncio.sleep(10)))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert current_source_worker() is None
    assert not [task for task in asyncio.all_tasks() if task.get_name() == "native-source-renewal"]


async def test_source_and_document_renewals_continue_during_a_slow_call(monkeypatch):
    # The slow call lasts until both renewals ran three times, never a fixed delay:
    # a 15 ms sleep against Windows' ~15.6 ms timer granularity let a loaded run
    # observe two renewals only.
    counts = {"source": 0, "document": 0}
    renewed = asyncio.Event()

    def counting(key: str):
        async def renew() -> None:
            counts[key] += 1
            if min(counts.values()) > 2:
                renewed.set()

        return renew

    monkeypatch.setattr(runtime, "renew_native_source", counting("source"))
    monkeypatch.setattr(runtime, "_heartbeat_interval", lambda: 0.001)
    with source_worker_scope(scope()):
        await asyncio.wait_for(
            runtime.source_worker_external(renewed.wait, renewal=counting("document")),
            timeout=5,
        )
    assert counts["source"] > 2
    assert counts["document"] > 2


async def test_document_renewal_loss_cancels_the_operation(monkeypatch):
    monkeypatch.setattr(runtime, "renew_native_source", AsyncMock())
    monkeypatch.setattr(runtime, "_heartbeat_interval", lambda: 0.001)
    document_renewal = AsyncMock(side_effect=[None, SourceLeaseLost()])
    stopped = asyncio.Event()

    async def operation():
        try:
            await asyncio.sleep(10)
        finally:
            stopped.set()

    with source_worker_scope(scope()), pytest.raises(SourceLeaseLost):
        await asyncio.wait_for(
            runtime.source_worker_external(operation, renewal=document_renewal), 1
        )
    assert stopped.is_set()
