"""Disabling a feature must not disable its private-payload retention clock."""

import inspect
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.config import settings
from src.core.constants import SCHEDULER_JOB_PEERS_DELIVERY_SWEEP
from src.domains.peers import capability_notifications as notifications
from src.infrastructure.scheduler import peer_message_delivery as delivery
from src.infrastructure.startup import schedulers

pytestmark = pytest.mark.unit


def test_retention_job_exists_even_with_peers_disabled(monkeypatch):
    monkeypatch.setattr(settings, "peers_enabled", False)
    scheduler = MagicMock()
    schedulers.register_peer_maintenance(scheduler)
    call = scheduler.add_job.call_args
    assert call.args == (delivery.sweep_pending_deliveries,)
    assert call.kwargs["id"] == SCHEDULER_JOB_PEERS_DELIVERY_SWEEP
    assert call.kwargs["seconds"] == settings.peers_delivery_sweep_seconds
    assert call.kwargs["max_instances"] == 1
    assert "register_peer_maintenance(scheduler)" in inspect.getsource(schedulers.init_scheduler)


@pytest.mark.asyncio
async def test_disabled_sweep_reaps_but_never_claims_messages(monkeypatch):
    monkeypatch.setattr(settings, "peers_enabled", False)
    reap = AsyncMock()
    database = MagicMock(side_effect=AssertionError("Disabled delivery opened a transaction"))
    monkeypatch.setattr(delivery, "maintain_capability_transfers", reap)
    monkeypatch.setattr(delivery, "get_db_context", database)
    counters = await delivery.sweep_pending_deliveries()
    reap.assert_awaited_once()
    database.assert_not_called()
    assert not any(counters.values())


@pytest.mark.asyncio
async def test_disabled_capability_reaper_expires_payloads_without_notifications(
    monkeypatch,
):
    monkeypatch.setattr(settings, "peers_enabled", False)
    db = AsyncMock()

    @asynccontextmanager
    async def context():
        yield db

    monkeypatch.setattr(notifications, "get_db_context", context)
    notify = AsyncMock()
    monkeypatch.setattr(notifications, "deliver_capability_receipt", notify)
    await notifications.maintain_capability_transfers()
    assert db.execute.await_count == 2
    db.scalars.assert_not_awaited()
    notify.assert_not_awaited()


@pytest.mark.asyncio
async def test_disabled_direct_receipt_never_archives_or_publishes(monkeypatch):
    monkeypatch.setattr(settings, "peers_enabled", False)
    database = MagicMock(side_effect=AssertionError("Disabled notification opened a transaction"))
    monkeypatch.setattr(notifications, "get_db_context", database)
    await notifications.deliver_capability_receipt(uuid4())
    database.assert_not_called()
