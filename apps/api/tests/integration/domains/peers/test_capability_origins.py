"""Origins follow the receiver's resource identity, never the source name."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.capability_contracts import CapabilityKind
from src.domains.peers.capability_models import (
    PeerCapabilityComponent,
    PeerCapabilityTransfer,
)
from src.domains.shared.capability_origins import capability_origins
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


async def test_origin_is_owned_batched_and_anonymized_after_sender_erasure(
    async_session: AsyncSession,
) -> None:
    sender, recipient = UserFactory.create(), UserFactory.create()
    sender.full_name = '<img src="https://example.test/tracker">'
    async_session.add_all([sender, recipient])
    await async_session.flush()
    shared_at = datetime.now(UTC)
    receipt = PeerCapabilityTransfer(
        sender_id=sender.id,
        recipient_id=recipient.id,
        source_id=uuid4(),
        idempotency_key=uuid4(),
        kind="skill",
        name="example",
        digest="1" * 64,
        status="partial",
        expires_at=shared_at + timedelta(minutes=5),
        transferred_at=shared_at,
    )
    async_session.add(receipt)
    await async_session.flush()
    resource_id = uuid4()
    async_session.add(
        PeerCapabilityComponent(
            transfer_id=receipt.id,
            kind="skill",
            key="example",
            resource_id=resource_id,
            fingerprint="1" * 64,
            installed=True,
        )
    )
    await async_session.flush()
    origins = await capability_origins(
        async_session, recipient.id, CapabilityKind.SKILL, [resource_id, uuid4()]
    )
    assert set(origins) == {resource_id}
    assert origins[resource_id].sender_display_name == sender.full_name
    assert origins[resource_id].shared_at == shared_at
    assert (
        await capability_origins(async_session, sender.id, CapabilityKind.SKILL, [resource_id])
        == {}
    )
    assert (
        await capability_origins(async_session, recipient.id, CapabilityKind.MCP, [resource_id])
        == {}
    )
    sender.deleted_at = datetime.now(UTC)
    await async_session.flush()
    origins = await capability_origins(
        async_session, recipient.id, CapabilityKind.SKILL, [resource_id]
    )
    assert origins[resource_id].sender_display_name is None
    assert origins[resource_id].shared_at == shared_at
