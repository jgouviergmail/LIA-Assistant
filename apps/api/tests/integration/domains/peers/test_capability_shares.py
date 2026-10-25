"""Who a sender shared a capability with, read on real PostgreSQL (2026-10-24).

The sender's side of the origin: owned, batched in ONE query for a whole page,
one line per recipient (the newest share), anonymised once the recipient's
account is closed, and only for shares that were PUBLISHED.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.domains.peers.capability_models import PeerCapabilityTransfer
from src.domains.shared.capability_shares import capability_shares, share_again_allowed
from tests.fixtures.factories import UserFactory

pytestmark = pytest.mark.integration


def _receipt(
    sender: UUID,
    recipient: UUID,
    source: UUID,
    *,
    at: datetime | None,
    status: str = "installed",
    kind: str = "skill",
    digest: str = "1" * 64,
) -> PeerCapabilityTransfer:
    return PeerCapabilityTransfer(
        sender_id=sender,
        recipient_id=recipient,
        source_id=source,
        idempotency_key=uuid4(),
        kind=kind,
        name="example",
        digest=digest,
        status=status,
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
        transferred_at=at,
    )


async def test_shares_are_owned_published_newest_per_recipient_and_anonymised(
    async_session: AsyncSession,
) -> None:
    sender, first, second = UserFactory.create(), UserFactory.create(), UserFactory.create()
    async_session.add_all([sender, first, second])
    await async_session.flush()
    source, other_source = uuid4(), uuid4()
    now = datetime.now(UTC)
    older = now - timedelta(days=2)
    async_session.add_all(
        [
            _receipt(sender.id, first.id, source, at=older, status="partial", digest="a" * 64),
            _receipt(sender.id, first.id, source, at=now, digest="b" * 64),
            _receipt(sender.id, second.id, source, at=older, status="partial"),
            # Never published: a preview nobody sent is no share.
            _receipt(sender.id, second.id, other_source, at=None, status="preparing"),
            # Another kind is another card.
            _receipt(sender.id, first.id, source, at=now, kind="mcp"),
            # The recipient's own shares are not the sender's.
            _receipt(first.id, sender.id, source, at=now),
        ]
    )
    await async_session.flush()

    shares = await capability_shares(async_session, sender.id, "skill", [source, other_source])

    assert set(shares) == {source}
    by_recipient = {share.recipient_id: share for share in shares[source]}
    assert set(by_recipient) == {first.id, second.id}
    newest = by_recipient[first.id]
    assert (newest.shared_at, newest.complete) == (now, True)
    assert newest.recipient_display_name == first.full_name
    assert by_recipient[second.id].complete is False
    # Final for now, whatever the version.
    assert not newest.can_share_again and not by_recipient[second.id].can_share_again

    second.is_active = False
    await async_session.flush()
    shares = await capability_shares(async_session, sender.id, "skill", [source])
    closed = next(share for share in shares[source] if share.recipient_id == second.id)
    assert closed.recipient_display_name is None


async def test_a_page_of_cards_costs_one_query_whatever_its_size(
    async_engine: AsyncEngine, async_session: AsyncSession
) -> None:
    sender, recipient = UserFactory.create(), UserFactory.create()
    async_session.add_all([sender, recipient])
    await async_session.flush()
    sources = [uuid4() for _ in range(5)]
    async_session.add_all(
        [_receipt(sender.id, recipient.id, s, at=datetime.now(UTC)) for s in sources]
    )
    await async_session.flush()
    statements: list[str] = []

    def record(*args: object) -> None:
        statements.append(str(args[2]))

    event.listen(async_engine.sync_engine, "before_cursor_execute", record)
    try:
        for page in (sources[:1], sources):
            statements.clear()
            shares = await capability_shares(async_session, sender.id, "skill", page)
            assert len(shares) == len(page)
            assert len(statements) == 1
    finally:
        event.remove(async_engine.sync_engine, "before_cursor_execute", record)


async def test_the_policy_reads_only_that_recipient_and_skips_the_receipt_being_resumed(
    async_session: AsyncSession,
) -> None:
    sender, recipient, other = UserFactory.create(), UserFactory.create(), UserFactory.create()
    async_session.add_all([sender, recipient, other])
    await async_session.flush()
    source = uuid4()
    receipt = _receipt(sender.id, recipient.id, source, at=datetime.now(UTC), status="partial")
    async_session.add(receipt)
    await async_session.flush()

    async def allowed(to: UUID, excluding: UUID | None = None) -> bool:
        return await share_again_allowed(
            async_session,
            sender_id=sender.id,
            recipient_id=to,
            kind="skill",
            source_id=source,
            current_digest="2" * 64,
            excluding=excluding,
        )

    assert await allowed(recipient.id) is False
    assert await allowed(other.id) is True
    # Resuming the partial share itself is not sharing again.
    assert await allowed(recipient.id, excluding=receipt.id) is True
    # A share confirmed and still installing counts as given: the pair's lock
    # is released before the installation runs.
    async_session.add(_receipt(sender.id, other.id, source, at=None, status="installing"))
    await async_session.flush()
    assert await allowed(other.id) is False
