"""Real committed outbox/ledger with a bounded synthetic transport."""

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.ingestion.delivery_types import DeliveryDisposition, DeliveryResult
from src.domains.ingestion.models import IngestionDelivery, IngestionReceipt
from src.domains.notifications.models import UserFCMToken
from src.domains.sms.ingestion import SmsIngestionService
from src.domains.users.models import User
from tests.integration.test_application_memory_independent_transactions import (
    committed_actor as committed_actor,
)
from tests.integration.test_sms_ingestion import authority, message

pytestmark = pytest.mark.integration


async def seed(engine, owner, *, late=False):
    async with AsyncSession(engine, expire_on_commit=False) as db:
        user = await db.get(User, owner)
        device = UserFCMToken(
            user_id=owner,
            token=f"synthetic:{uuid4()}",
            device_type="web",
            created_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        db.add(device)
        actor = await authority(db, user)
        await SmsIngestionService(db).ingest(actor, [message(body="Private original body")])
        if late:
            db.add(
                UserFCMToken(
                    user_id=owner,
                    token=f"synthetic:{uuid4()}",
                    device_type="ios",
                    created_at=datetime.now(UTC) + timedelta(seconds=1),
                )
            )
        await db.commit()
        return device.id


def sessions(engine):
    @asynccontextmanager
    async def factory():
        async with AsyncSession(engine, expire_on_commit=False) as db:
            yield db

    return factory


async def test_snapshot_and_network_have_no_owner_lock(async_engine, committed_actor):
    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    device = await seed(async_engine, committed_actor, late=True)
    sent = []

    class Transport:
        async def send(self, envelope):
            async with AsyncSession(async_engine) as db:
                await db.execute(text("SET LOCAL lock_timeout='150ms'"))
                await db.scalar(select(User.id).where(User.id == committed_actor).with_for_update())
            assert "Private original body" not in repr(envelope)
            sent.append(envelope)
            return DeliveryResult(DeliveryDisposition.ACCEPTED)

    worker = IngestionDeliveryWorker(sessions(async_engine), Transport())
    await worker.run_once(limit=10)
    assert {x.destination_key for x in sent} == {"sse", f"device:{device}"}
    async with AsyncSession(async_engine) as db:
        effects = list(
            (
                await db.scalars(select(AgentEffect).where(AgentEffect.user_id == committed_actor))
            ).all()
        )
        assert (await db.get(UserFCMToken, device)).last_used_at is not None
        assert len(effects) == 2
        assert all(
            x.status == EffectStatus.SUCCEEDED and x.source.value == "scheduled" for x in effects
        )
        assert all(x.tool_name == "sms_notification" for x in effects)
        assert all("Private original body" not in (x.label or "") for x in effects)


@pytest.mark.parametrize(
    "disposition", [DeliveryDisposition.RETRYABLE, DeliveryDisposition.UNKNOWN]
)
async def test_only_known_failed_device_can_retry(async_engine, committed_actor, disposition):
    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    device = await seed(async_engine, committed_actor)
    sent = []

    class Transport:
        async def send(self, envelope):
            sent.append(envelope.destination_key)
            return DeliveryResult(
                disposition if envelope.device_id else DeliveryDisposition.ACCEPTED,
                error_code="SYNTHETIC_FAILURE",
                retry_after_seconds=60,
            )

    worker = IngestionDeliveryWorker(sessions(async_engine), Transport())
    now = datetime.now(UTC)
    await worker.run_once(now=now, limit=10)
    await worker.run_once(now=now + timedelta(seconds=61), limit=10)
    assert sent.count("sse") == 1
    assert sent.count(f"device:{device}") == (
        2 if disposition == DeliveryDisposition.RETRYABLE else 1
    )
    async with AsyncSession(async_engine) as db:
        rows = list(
            (
                await db.scalars(
                    select(AgentEffect)
                    .where(AgentEffect.user_id == committed_actor)
                    .order_by(AgentEffect.claimed_at)
                )
            ).all()
        )
        if disposition == DeliveryDisposition.UNKNOWN:
            assert any(x.status == EffectStatus.ABANDONED for x in rows)
        else:
            assert rows[-1].retry_of is not None


@pytest.mark.parametrize("change", ["push_off", "deleted_receipt", "account_inactive"])
async def test_fresh_policy_cancels_before_any_transport(async_engine, committed_actor, change):
    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    await seed(async_engine, committed_actor)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, committed_actor)
        if change == "push_off":
            user.sms_preferences = {"push_enabled": False}
        elif change == "account_inactive":
            user.is_active = False
        else:
            receipt = await db.scalar(
                select(IngestionReceipt).where(IngestionReceipt.user_id == committed_actor)
            )
            receipt.verdict = "deleted"
        await db.commit()

    class Transport:
        async def send(self, envelope):
            pytest.fail("A withdrawn source must never reach transport")

    await IngestionDeliveryWorker(sessions(async_engine), Transport()).run_once(limit=10)
    async with AsyncSession(async_engine) as db:
        assert set(
            (
                await db.scalars(
                    select(IngestionDelivery.state).where(
                        IngestionDelivery.user_id == committed_actor
                    )
                )
            ).all()
        ) == {"cancelled"}


async def test_hub_sms_count_matches_archive_and_failure_is_unknown(
    async_engine, committed_actor, monkeypatch
):
    from src.domains.notifications import hub_counts

    await seed(async_engine, committed_actor)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, committed_actor)
    counts = await hub_counts.resolve_hub_counts(user)
    assert counts.sms == 1

    async def unavailable(owner):
        raise OSError("synthetic database failure")

    monkeypatch.setattr(hub_counts, "_sms", unavailable)
    counts = await hub_counts.resolve_hub_counts(user)
    assert counts.sms is None


async def test_two_workers_never_send_the_same_destination_twice(async_engine, committed_actor):
    import asyncio

    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    await seed(async_engine, committed_actor)
    entered, release = asyncio.Event(), asyncio.Event()
    sent = []

    class Transport:
        async def send(self, envelope):
            sent.append(envelope.destination_key)
            if len(sent) == 1:
                entered.set()
                await release.wait()
            return DeliveryResult(DeliveryDisposition.ACCEPTED)

    a = IngestionDeliveryWorker(sessions(async_engine), Transport())
    b = IngestionDeliveryWorker(sessions(async_engine), Transport())
    running = asyncio.create_task(a.run_once(limit=10))
    await asyncio.wait_for(entered.wait(), 5)
    await b.run_once(limit=10)
    release.set()
    await running
    assert len(sent) == len(set(sent)) == 2


async def test_crash_after_send_abandons_ledger_without_repeating_destination(
    async_engine, committed_actor
):
    import asyncio

    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    await seed(async_engine, committed_actor)
    sent = []

    class Transport:
        async def send(self, envelope):
            sent.append(envelope.destination_key)
            if len(sent) == 1:
                raise asyncio.CancelledError()
            return DeliveryResult(DeliveryDisposition.ACCEPTED)

    worker = IngestionDeliveryWorker(sessions(async_engine), Transport())
    now = datetime.now(UTC)
    with pytest.raises(asyncio.CancelledError):
        await worker.run_once(now=now, limit=10)
    await worker.run_once(now=now + timedelta(seconds=61), limit=10)
    assert len(sent) == len(set(sent)) == 2
    async with AsyncSession(async_engine) as db:
        states = list(
            (
                await db.scalars(
                    select(AgentEffect.status).where(AgentEffect.user_id == committed_actor)
                )
            ).all()
        )
        assert set(states) == {EffectStatus.ABANDONED, EffectStatus.SUCCEEDED}


async def test_disable_during_network_fences_the_late_acknowledgement(
    async_engine, committed_actor
):
    from src.domains.sms.management_commands import cancel_sms_deliveries
    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    await seed(async_engine, committed_actor)
    sent = []

    class Transport:
        async def send(self, envelope):
            sent.append(envelope.destination_key)
            async with AsyncSession(async_engine) as db:
                await db.scalar(select(User).where(User.id == committed_actor).with_for_update())
                await cancel_sms_deliveries(db, committed_actor)
                await db.commit()
            return DeliveryResult(DeliveryDisposition.ACCEPTED)

    await IngestionDeliveryWorker(sessions(async_engine), Transport()).run_once(limit=10)
    assert len(sent) == 1
    async with AsyncSession(async_engine) as db:
        states = list(
            (
                await db.scalars(
                    select(AgentEffect.status).where(AgentEffect.user_id == committed_actor)
                )
            ).all()
        )
        assert states == [EffectStatus.ABANDONED]


async def test_each_new_lease_uses_fresh_wall_time_after_slow_transport(
    async_engine, committed_actor, monkeypatch
):
    from src.infrastructure.scheduler import ingestion_delivery

    await seed(async_engine, committed_actor)
    clock = [datetime.now(UTC)]

    class WallClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return clock[0]

    monkeypatch.setattr(ingestion_delivery, "datetime", WallClock)
    sent = []

    class Transport:
        async def send(self, envelope):
            async with AsyncSession(async_engine) as db:
                lease = await db.scalar(
                    select(IngestionDelivery.lease_until).where(
                        IngestionDelivery.user_id == committed_actor,
                        IngestionDelivery.destination_key == envelope.destination_key,
                    )
                )
                assert (
                    lease > clock[0]
                ), "A newly launched send must not start with an expired lease"
            sent.append(envelope.destination_key)
            clock[0] += timedelta(seconds=61)
            return DeliveryResult(DeliveryDisposition.ACCEPTED)

    await ingestion_delivery.IngestionDeliveryWorker(sessions(async_engine), Transport()).run_once(
        limit=10
    )
    # Transport assertion failures become UNKNOWN: inspect the ledger as well,
    # otherwise swallowing the assertion would turn this probe into a false pass.
    assert len(sent) == 2
    async with AsyncSession(async_engine) as db:
        states = set(
            (
                await db.scalars(
                    select(AgentEffect.status).where(AgentEffect.user_id == committed_actor)
                )
            ).all()
        )
        assert states == {EffectStatus.SUCCEEDED}


async def test_permanently_invalid_device_is_deactivated_without_retry(
    async_engine, committed_actor
):
    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    device = await seed(async_engine, committed_actor)
    sent = []

    class Transport:
        async def send(self, envelope):
            sent.append(envelope.destination_key)
            return (
                DeliveryResult(DeliveryDisposition.PERMANENT, "DEVICE_INVALID")
                if envelope.device_id
                else DeliveryResult(DeliveryDisposition.ACCEPTED)
            )

    worker = IngestionDeliveryWorker(sessions(async_engine), Transport())
    now = datetime.now(UTC)
    await worker.run_once(now=now, limit=10)
    await worker.run_once(now=now + timedelta(days=1), limit=10)
    assert sent.count(f"device:{device}") == 1
    async with AsyncSession(async_engine) as db:
        assert not (await db.get(UserFCMToken, device)).is_active


async def test_sql_owner_lock_wait_is_bounded_before_transport(
    async_engine, committed_actor, monkeypatch
):
    import asyncio
    from time import monotonic

    from src.core.config import settings
    from src.domains.ingestion.delivery_repository import claim_next
    from src.infrastructure.scheduler.ingestion_delivery import IngestionDeliveryWorker

    await seed(async_engine, committed_actor)
    async with AsyncSession(async_engine) as db:
        claim = await claim_next(db, uuid4(), now=datetime.now(UTC))
        await db.commit()

    class Transport:
        async def send(self, envelope):
            pytest.fail("No send under a blocked SQL fence")

    monkeypatch.setitem(settings.__dict__, "ingestion_delivery_sql_timeout_seconds", 0.1)
    worker = IngestionDeliveryWorker(sessions(async_engine), Transport())
    async with AsyncSession(async_engine) as blocker:
        await blocker.scalar(select(User.id).where(User.id == committed_actor).with_for_update())
        started = monotonic()
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(worker._prepare(claim, datetime.now(UTC)), 0.8)
        assert (
            monotonic() - started < 0.5
        ), "The worker waited for the outer watchdog, not its own SQL deadline"
    async with AsyncSession(async_engine) as db:
        row = await db.get(IngestionDelivery, claim.id)
        assert row.state == "pending" and row.attempts == 0
