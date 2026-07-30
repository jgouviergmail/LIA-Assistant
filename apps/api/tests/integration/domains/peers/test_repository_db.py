"""PeersRepository integration tests — real-PostgreSQL constraint semantics.

The pair-canonical model only holds if the DATABASE enforces it: UNIQUE on
(user_a, user_b), CHECK user_a < user_b, the share UNIQUE triple and the
atomic share upsert are PostgreSQL behaviors that an in-memory substitute
cannot exercise (same rationale as conversations/test_feedback_persistence).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.peers.models import (
    PeerConnection,
    PeerConnectionStatus,
    PeerDomainShare,
    PeerMessage,
    PeerMessageStatus,
    PeerShareDomain,
    PeerShareLevel,
    canonical_pair,
)
from src.domains.peers.repository import PeersRepository

pytestmark = pytest.mark.integration


@pytest.fixture
async def two_users(async_session: AsyncSession):
    """Two active users forming the pair under test."""
    from src.domains.users.models import User

    user_a = User(
        email="peer_a@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Peer Alpha",
    )
    user_b = User(
        email="peer_b@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Peer Beta",
    )
    async_session.add_all([user_a, user_b])
    await async_session.commit()
    await async_session.refresh(user_a)
    await async_session.refresh(user_b)
    return user_a, user_b


class TestPairConstraints:
    """The database, not the application, makes bad pairs unrepresentable."""

    async def test_duplicate_pair_rejected_whatever_the_order(
        self, async_session: AsyncSession, two_users
    ):
        """GIVEN an existing pair row, inserting the same pair again (canonical
        order — the only order the CHECK admits) violates the UNIQUE."""
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        await repo.insert_pair_request(user_a.id, user_b.id, None, now=datetime.now(UTC))
        await async_session.commit()

        lo, hi = canonical_pair(user_a.id, user_b.id)
        async_session.add(
            PeerConnection(
                user_a_id=lo,
                user_b_id=hi,
                requested_by_id=user_b.id,
                requested_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()

    async def test_self_pair_rejected_by_check(self, async_session: AsyncSession, two_users):
        """A row where user_a == user_b violates ck_peer_connections_pair_order."""
        user_a, _ = two_users
        async_session.add(
            PeerConnection(
                user_a_id=user_a.id,
                user_b_id=user_a.id,
                requested_by_id=user_a.id,
                requested_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()

    async def test_reversed_pair_rejected_by_check(self, async_session: AsyncSession, two_users):
        """A non-canonical ordering (user_a > user_b) violates the CHECK, which
        is what makes the UNIQUE meaningful across argument orders."""
        user_a, user_b = two_users
        lo, hi = canonical_pair(user_a.id, user_b.id)
        async_session.add(
            PeerConnection(
                user_a_id=hi,
                user_b_id=lo,
                requested_by_id=user_a.id,
                requested_at=datetime.now(UTC),
            )
        )
        with pytest.raises(IntegrityError):
            await async_session.commit()
        await async_session.rollback()


class TestRequestReuse:
    """Re-requests transition the existing row — never a second row (spec §5.3)."""

    async def test_declined_row_revives_back_to_pending(
        self, async_session: AsyncSession, two_users
    ):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        now = datetime.now(UTC)
        connection = await repo.insert_pair_request(user_a.id, user_b.id, "hello", now=now)
        declined = await repo.transition_status(
            connection.id,
            PeerConnectionStatus.DECLINED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        assert declined is not None
        await async_session.commit()

        revived = await repo.revive_request(connection.id, user_b.id, None, now=datetime.now(UTC))
        await async_session.commit()

        assert revived is not None
        assert revived.id == connection.id  # same row, transitioned
        assert revived.status == PeerConnectionStatus.PENDING.value
        assert revived.requested_by_id == user_b.id
        assert revived.responded_at is None
        assert revived.context_message is None

        rows = (await async_session.execute(select(PeerConnection))).scalars().all()
        assert len(rows) == 1

    async def test_transition_claims_exactly_once(self, async_session: AsyncSession, two_users):
        """The conditional UPDATE claims the row once — the second claim loses
        (two concurrent responders cannot both win, spec §13)."""
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        now = datetime.now(UTC)
        connection = await repo.insert_pair_request(user_a.id, user_b.id, None, now=now)
        await async_session.commit()

        first = await repo.transition_status(
            connection.id,
            PeerConnectionStatus.ACCEPTED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        second = await repo.transition_status(
            connection.id,
            PeerConnectionStatus.DECLINED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        assert first is not None and first.status == PeerConnectionStatus.ACCEPTED.value
        assert second is None  # lost the claim — row already left pending

    async def test_revive_refuses_non_terminal_rows(self, async_session: AsyncSession, two_users):
        """Reviving a PENDING row must fail: only declined/removed are revivable."""
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await repo.insert_pair_request(
            user_a.id, user_b.id, None, now=datetime.now(UTC)
        )
        await async_session.commit()
        revived = await repo.revive_request(connection.id, user_b.id, None, now=datetime.now(UTC))
        assert revived is None


class TestShareUpsert:
    """Share upserts are atomic and idempotent on the UNIQUE triple."""

    async def test_upsert_share_updates_level_in_place(
        self, async_session: AsyncSession, two_users
    ):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        now = datetime.now(UTC)
        connection = await repo.insert_pair_request(user_a.id, user_b.id, None, now=now)
        accepted = await repo.transition_status(
            connection.id,
            PeerConnectionStatus.ACCEPTED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        assert accepted is not None
        await async_session.commit()

        await repo.upsert_share(
            connection.id,
            user_a.id,
            PeerShareDomain.CALENDAR.value,
            PeerShareLevel.AVAILABILITY.value,
        )
        await repo.upsert_share(
            connection.id, user_a.id, PeerShareDomain.CALENDAR.value, PeerShareLevel.DETAILS.value
        )
        await async_session.commit()

        shares = (await async_session.execute(select(PeerDomainShare))).scalars().all()
        assert len(shares) == 1
        assert shares[0].level == PeerShareLevel.DETAILS.value


class TestMessageDeliveryTransitions:
    """The delivery ledger claims exactly once and scrubs on success (spec §8)."""

    async def _accepted_connection(self, repo, async_session, user_a, user_b):
        now = datetime.now(UTC)
        connection = await repo.insert_pair_request(user_a.id, user_b.id, None, now=now)
        accepted = await repo.transition_status(
            connection.id,
            PeerConnectionStatus.ACCEPTED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        assert accepted is not None
        await async_session.commit()
        return accepted

    async def test_claim_transitions_and_second_claim_sees_nothing(
        self, async_session: AsyncSession, two_users
    ):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await self._accepted_connection(repo, async_session, user_a, user_b)
        await repo.enqueue_message(connection.id, user_a.id, user_b.id, "coucou")
        await async_session.commit()

        claimed = await repo.claim_pending_messages()
        assert len(claimed) == 1
        assert claimed[0].status == PeerMessageStatus.DELIVERING.value
        # Same-transaction second claim: the row already left pending.
        assert await repo.claim_pending_messages() == []
        await async_session.commit()

    async def test_delivered_scrubs_content(self, async_session: AsyncSession, two_users):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await self._accepted_connection(repo, async_session, user_a, user_b)
        message = await repo.enqueue_message(connection.id, user_a.id, user_b.id, "secret")
        await async_session.commit()
        (claimed,) = await repo.claim_pending_messages()
        assert await repo.mark_message_delivered(claimed.id, now=datetime.now(UTC)) is True
        await async_session.commit()

        row = await async_session.get(PeerMessage, message.id)
        await async_session.refresh(row)
        assert row.status == PeerMessageStatus.DELIVERED.value
        assert row.content is None  # scrubbed — spec §8.4
        assert row.delivered_at is not None
        # Finishing twice loses the claim cleanly.
        assert await repo.mark_message_delivered(claimed.id, now=datetime.now(UTC)) is False

    async def test_failure_retries_until_the_cap(self, async_session: AsyncSession, two_users):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await self._accepted_connection(repo, async_session, user_a, user_b)
        message = await repo.enqueue_message(connection.id, user_a.id, user_b.id, "x")
        await async_session.commit()

        (claimed,) = await repo.claim_pending_messages()
        assert (
            await repo.mark_message_failed(claimed.id, "llm_error", max_attempts=2)
            == PeerMessageStatus.PENDING.value
        )
        await async_session.commit()
        (reclaimed,) = await repo.claim_pending_messages()
        assert reclaimed.id == message.id
        assert (
            await repo.mark_message_failed(reclaimed.id, "llm_error", max_attempts=2)
            == PeerMessageStatus.FAILED.value
        )
        await async_session.commit()
        row = await async_session.get(PeerMessage, message.id)
        await async_session.refresh(row)
        assert row.attempts == 2
        assert row.last_error == "llm_error"

    async def test_stale_delivering_recovers_to_pending(
        self, async_session: AsyncSession, two_users
    ):
        from datetime import timedelta

        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await self._accepted_connection(repo, async_session, user_a, user_b)
        await repo.enqueue_message(connection.id, user_a.id, user_b.id, "x")
        await async_session.commit()
        await repo.claim_pending_messages()
        await async_session.commit()

        recovered = await repo.recover_stale_delivering(
            older_than=datetime.now(UTC) + timedelta(minutes=1)
        )
        await async_session.commit()
        assert recovered == 1
        (reclaimed,) = await repo.claim_pending_messages()
        assert reclaimed.status == PeerMessageStatus.DELIVERING.value
