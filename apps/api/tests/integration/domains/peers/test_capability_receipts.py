"""Real SQL proves transfer fencing, durable identities and ownership deletion."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, func, update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.domains.peers.capability_contracts import TransferStatus
from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.peers.capability_repository import (
    CapabilityTransferRepository,
    TransferClaimLost,
    TransferLease,
)
from src.domains.users.models import User
from src.domains.users.resource_release import build_capability_origin_scrub
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def transfer(db: AsyncSession) -> PeerCapabilityTransfer:
    sender, recipient = UserFactory.create(), UserFactory.create()
    db.add_all([sender, recipient])
    await db.flush()
    receipt = PeerCapabilityTransfer(
        sender_id=sender.id,
        recipient_id=recipient.id,
        source_id=uuid4(),
        idempotency_key=uuid4(),
        kind="skill",
        name="example",
        digest="a" * 64,
        status="preparing",
        snapshot={"public": True},
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    db.add(receipt)
    await db.flush()
    return receipt


async def test_claim_is_scoped_and_only_one_owner_can_install(
    async_session: AsyncSession,
) -> None:
    receipt = await transfer(async_session)
    assert receipt.sender_id is not None
    sender_id = receipt.sender_id
    repo = CapabilityTransferRepository(async_session)
    assert await repo.claim(receipt.id, uuid4(), receipt.digest, uuid4(), ttl_seconds=60) is None
    assert (
        await repo.claim(receipt.id, receipt.sender_id, "b" * 64, uuid4(), ttl_seconds=60) is None
    )
    lease = await repo.claim(receipt.id, receipt.sender_id, receipt.digest, uuid4(), ttl_seconds=60)
    assert lease is not None
    assert (
        await repo.claim(receipt.id, receipt.sender_id, receipt.digest, uuid4(), ttl_seconds=60)
        is None
    )
    await repo.finish(lease, TransferStatus.INSTALLED)
    async_session.expire_all()
    fresh = await repo.owned(lease.transfer_id, sender_id)
    assert fresh is not None and fresh.status == "installed" and fresh.snapshot is None
    with pytest.raises(TransferClaimLost):
        await repo.finish(lease, TransferStatus.FAILED)


async def test_expired_owner_cannot_publish_after_takeover(
    async_session: AsyncSession,
) -> None:
    receipt = await transfer(async_session)
    assert receipt.sender_id is not None
    sender_id = receipt.sender_id
    transfer_id, digest = receipt.id, receipt.digest
    repo = CapabilityTransferRepository(async_session)
    first = await repo.claim(transfer_id, sender_id, digest, uuid4(), ttl_seconds=60)
    assert first is not None
    await async_session.execute(
        update(PeerCapabilityTransfer)
        .where(PeerCapabilityTransfer.id == transfer_id)
        .values(lease_expires_at=datetime.now(UTC) - timedelta(hours=1))
    )
    second = await repo.claim(transfer_id, sender_id, digest, uuid4(), ttl_seconds=60)
    assert second is not None and second.fence > first.fence
    with pytest.raises(TransferClaimLost):
        await repo.fence_publication(first, ttl_seconds=60)
    await repo.fence_publication(second, ttl_seconds=60)
    await repo.finish(second, TransferStatus.PARTIAL)


async def test_confirmation_has_a_fixed_retention_deadline_not_renewed_by_retry(
    async_session: AsyncSession,
) -> None:
    receipt = await transfer(async_session)
    assert receipt.sender_id is not None
    sender_id, transfer_id, digest = receipt.sender_id, receipt.id, receipt.digest
    repo = CapabilityTransferRepository(async_session)
    lease = await repo.claim(
        transfer_id, sender_id, digest, uuid4(), ttl_seconds=60, retry_seconds=600
    )
    assert lease is not None
    current = await repo.owned(transfer_id, sender_id)
    assert current is not None
    deadline = current.expires_at
    await repo.finish(lease, TransferStatus.PARTIAL)
    lease = await repo.claim(
        transfer_id, sender_id, digest, uuid4(), ttl_seconds=60, retry_seconds=3600
    )
    assert lease is not None
    current = await repo.owned(transfer_id, sender_id)
    assert current is not None and current.expires_at == deadline


async def test_completed_component_identity_survives_retry_and_sender_deletion(
    async_session: AsyncSession,
) -> None:
    receipt = await transfer(async_session)
    repo = CapabilityTransferRepository(async_session)
    component = await repo.reserve_component(
        receipt.id, kind="skill", key="example", fingerprint=receipt.digest
    )
    resource_id = uuid4()
    component.resource_id, component.installed = resource_id, True
    await async_session.flush()
    repeated = await repo.reserve_component(
        receipt.id, kind="skill", key="example", fingerprint=receipt.digest
    )
    assert (
        repeated.id == component.id and repeated.installed and repeated.resource_id == resource_id
    )
    with pytest.raises(ValueError):
        await repo.reserve_component(receipt.id, kind="skill", key="example", fingerprint="b" * 64)
    transfer_id, recipient_id = receipt.id, receipt.recipient_id
    await async_session.execute(delete(User).where(User.id == receipt.sender_id))
    async_session.expire_all()
    fresh = await async_session.get(PeerCapabilityTransfer, transfer_id)
    assert fresh is not None and fresh.sender_id is None
    assert len(await repo.components(transfer_id)) == 1
    await async_session.execute(delete(User).where(User.id == recipient_id))
    assert await repo.components(transfer_id) == []


async def test_sender_scrub_clears_pending_bytes_and_invalidates_its_live_lease(
    async_session: AsyncSession,
) -> None:
    receipt = await transfer(async_session)
    assert receipt.sender_id is not None
    sender_id, transfer_id = receipt.sender_id, receipt.id
    repo = CapabilityTransferRepository(async_session)
    lease = await repo.claim(transfer_id, sender_id, receipt.digest, uuid4(), ttl_seconds=60)
    assert lease is not None
    await repo.reserve_component(
        transfer_id, kind="skill", key="example", fingerprint=receipt.digest
    )
    await async_session.execute(build_capability_origin_scrub(sender_id))
    async_session.expire_all()
    fresh = await async_session.get(PeerCapabilityTransfer, transfer_id)
    assert fresh is not None and fresh.sender_id is None
    assert fresh.snapshot is None and fresh.lease_owner is None and fresh.status == "cancelled"
    assert len(await repo.components(transfer_id)) == 1
    with pytest.raises(TransferClaimLost):
        await repo.fence_publication(lease, ttl_seconds=60)


async def test_independent_workers_cannot_both_claim_the_same_transfer(
    async_engine: AsyncEngine,
    committed_user_ids: list[UUID],
) -> None:
    maker = async_sessionmaker(async_engine, expire_on_commit=False, autoflush=False)
    async with maker() as db:
        receipt = await transfer(db)
        assert receipt.sender_id is not None
        committed_user_ids.extend([receipt.sender_id, receipt.recipient_id])
        sender_id, transfer_id, digest = receipt.sender_id, receipt.id, receipt.digest
        await db.commit()

    async def worker() -> TransferLease | None:
        async with maker() as db:
            result = await CapabilityTransferRepository(db).claim(
                transfer_id, sender_id, digest, uuid4(), ttl_seconds=60
            )
            await db.commit()
            return result

    results = await asyncio.gather(worker(), worker())
    assert sum(result is not None for result in results) == 1


async def test_lease_expiry_is_observed_even_inside_an_open_transaction(
    async_session: AsyncSession,
) -> None:
    receipt = await transfer(async_session)
    assert receipt.sender_id is not None
    repo = CapabilityTransferRepository(async_session)
    lease = await repo.claim(receipt.id, receipt.sender_id, receipt.digest, uuid4(), ttl_seconds=60)
    assert lease is not None
    await async_session.execute(
        update(PeerCapabilityTransfer)
        .where(PeerCapabilityTransfer.id == receipt.id)
        .values(lease_expires_at=func.clock_timestamp() + timedelta(milliseconds=30))
    )
    await asyncio.sleep(0.06)
    with pytest.raises(TransferClaimLost):
        await repo.fence_publication(lease, ttl_seconds=60)
