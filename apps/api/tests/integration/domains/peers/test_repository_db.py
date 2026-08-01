"""PeersRepository integration tests — real-PostgreSQL constraint semantics.

The pair-canonical model only holds if the DATABASE enforces it: UNIQUE on
(user_a, user_b), CHECK user_a < user_b, the share UNIQUE triple and the
atomic share upsert are PostgreSQL behaviors that an in-memory substitute
cannot exercise (same rationale as conversations/test_feedback_persistence).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

    async def test_delivered_keeps_both_texts(self, async_session: AsyncSession, two_users):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await self._accepted_connection(repo, async_session, user_a, user_b)
        message = await repo.enqueue_message(connection.id, user_a.id, user_b.id, "secret")
        await async_session.commit()
        (claimed,) = await repo.claim_pending_messages()
        assert (
            await repo.mark_message_delivered(
                claimed.id, now=datetime.now(UTC), delivered_text="Il sera en retard."
            )
            is True
        )
        await async_session.commit()

        row = await async_session.get(PeerMessage, message.id)
        await async_session.refresh(row)
        assert row.status == PeerMessageStatus.DELIVERED.value
        # ADR-186: the directive is no longer erased here, and what the
        # recipient's assistant said is recorded next to it. Each side reads
        # only its own; the retention reaper clears both later.
        assert row.content == "secret"
        assert row.delivered_text == "Il sera en retard."
        assert row.delivered_at is not None
        assert row.expires_at is not None  # stamped at enqueue
        # Finishing twice loses the claim cleanly.
        assert (
            await repo.mark_message_delivered(claimed.id, now=datetime.now(UTC), delivered_text="x")
            is False
        )

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


@pytest.fixture
async def accepted_pair(async_session: AsyncSession, two_users):
    """An ACCEPTED connection plus the two users it links."""
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
    return accepted, user_a, user_b


class TestDeliveredMessageActivity:
    """The CRM timeline spine (spec §11, D2).

    Every oracle here is a PostgreSQL behavior the unit tier cannot reach: the
    CASE counterpart join that resolves identity by foreign key, the NOT IN
    block exclusion applied BEFORE the cap, and the delivered-only filter.
    """

    async def _deliver(self, repo, async_session, connection, sender, recipient, *, when):
        """Enqueue → claim → mark delivered, and return the ledger row."""
        message = await repo.enqueue_message(connection.id, sender.id, recipient.id, "hello")
        await async_session.commit()
        await repo.claim_pending_messages()
        await async_session.commit()
        assert await repo.mark_message_delivered(
            message.id, now=when, delivered_text="ce que son assistant a dit"
        )
        await async_session.commit()
        return message

    async def test_both_directions_resolve_the_other_participant(
        self, async_session: AsyncSession, accepted_pair
    ):
        """GIVEN one message each way, THEN each row names the OTHER user and
        its direction is expressed relative to the caller."""
        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)
        base = datetime.now(UTC)
        await self._deliver(
            repo, async_session, connection, user_a, user_b, when=base - timedelta(hours=2)
        )
        await self._deliver(
            repo, async_session, connection, user_b, user_a, when=base - timedelta(hours=1)
        )

        seen_by_a = await repo.list_delivered_message_activity(user_a.id, limit=10)
        assert [item.direction for item in seen_by_a] == ["received", "sent"]  # newest first
        assert {item.peer_id for item in seen_by_a} == {user_b.id}
        assert {item.peer_display_name for item in seen_by_a} == {"Peer Beta"}

        # The same two rows, mirrored, for the other side of the pair.
        seen_by_b = await repo.list_delivered_message_activity(user_b.id, limit=10)
        assert [item.direction for item in seen_by_b] == ["sent", "received"]
        assert {item.peer_id for item in seen_by_b} == {user_a.id}

    async def test_undelivered_messages_never_appear(
        self, async_session: AsyncSession, accepted_pair
    ):
        """A message that never arrived is not an exchange — and its text was
        never archived either, so counting it would promise unreadable content."""
        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)
        await repo.enqueue_message(connection.id, user_a.id, user_b.id, "pending one")
        await async_session.commit()

        assert await repo.list_delivered_message_activity(user_a.id, limit=10) == []

    async def test_blocked_peer_is_excluded_before_the_cap(
        self, async_session: AsyncSession, accepted_pair
    ):
        """Blocking must not leave a hole in an otherwise full page: the
        exclusion belongs in the WHERE clause, not in a post-filter."""
        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)
        await self._deliver(repo, async_session, connection, user_b, user_a, when=datetime.now(UTC))
        assert len(await repo.list_delivered_message_activity(user_a.id, limit=10)) == 1

        await repo.create_block(user_a.id, user_b.id)
        await async_session.commit()
        assert await repo.list_delivered_message_activity(user_a.id, limit=10) == []
        # The block is directional: the blocked side keeps its own timeline.
        assert len(await repo.list_delivered_message_activity(user_b.id, limit=10)) == 1

    async def test_narrows_to_the_given_spellings_and_asks_nothing_for_none(
        self, async_session: AsyncSession, accepted_pair
    ):
        """A page for ONE person is narrowed in SQL — the caller must never
        have to slice it out of a global page (that would show a total with
        no rows behind it)."""
        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)
        await self._deliver(repo, async_session, connection, user_b, user_a, when=datetime.now(UTC))

        matching = await repo.list_delivered_message_activity(
            user_a.id, limit=10, peer_names=["Peer Beta"]
        )
        assert len(matching) == 1
        assert (
            await repo.list_delivered_message_activity(
                user_a.id, limit=10, peer_names=["Quelqu'un d'autre"]
            )
            == []
        )
        # An EMPTY list asks for nothing — never for everything.
        assert await repo.list_delivered_message_activity(user_a.id, limit=10, peer_names=[]) == []
        # No filter at all still returns the whole timeline (overview path).
        assert len(await repo.list_delivered_message_activity(user_a.id, limit=10)) == 1

    @pytest.mark.parametrize("unusable", ["   ", "?"])
    async def test_a_nameless_peer_never_costs_a_real_row_its_place(
        self, async_session: AsyncSession, accepted_pair, unusable
    ):
        """The unusable-name exclusion belongs in SQL, like the block one.

        Dropped in Python it runs AFTER the LIMIT, so the newest row being a
        nameless peer empties a page that had a perfectly good row waiting
        behind it — and the page then disagrees with the aggregate, which
        excludes those peers in SQL.
        """
        from src.domains.users.models import User

        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)
        base = datetime.now(UTC)

        # A second, NAMED peer of the same caller, with the OLDER message.
        third = User(
            email="peer_c@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Peer Gamma",
        )
        async_session.add(third)
        await async_session.commit()
        await async_session.refresh(third)
        other_pair = await repo.insert_pair_request(user_a.id, third.id, None, now=base)
        accepted = await repo.transition_status(
            other_pair.id,
            PeerConnectionStatus.ACCEPTED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=base,
        )
        assert accepted is not None
        await async_session.commit()
        await self._deliver(
            repo, async_session, accepted, third, user_a, when=base - timedelta(hours=2)
        )
        # The NEWEST message comes from the peer who then loses their name.
        await self._deliver(
            repo, async_session, connection, user_b, user_a, when=base - timedelta(hours=1)
        )
        nameless = await async_session.get(User, user_b.id)
        assert nameless is not None
        nameless.full_name = unusable
        await async_session.commit()

        page = await repo.list_delivered_message_activity(user_a.id, limit=1)

        assert [item.peer_display_name for item in page] == ["Peer Gamma"]
        # And the aggregate agrees on exactly who exists.
        assert [
            row.raw_name for row in await repo.aggregate_delivered_messages_by_peer(user_a.id)
        ] == ["Peer Gamma"]

    async def test_cap_keeps_the_most_recent_deliveries(
        self, async_session: AsyncSession, accepted_pair
    ):
        """The cap is applied on a DESC delivery order, so it truncates the
        tail of the timeline, never its head."""
        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)
        base = datetime.now(UTC)
        for hours in (3, 2, 1):
            await self._deliver(
                repo,
                async_session,
                connection,
                user_b,
                user_a,
                when=base - timedelta(hours=hours),
            )

        capped = await repo.list_delivered_message_activity(user_a.id, limit=2)
        assert len(capped) == 2
        assert capped[0].occurred_at > capped[1].occurred_at
        assert capped[0].occurred_at == base - timedelta(hours=1)


class TestAcceptedPeerProfiles:
    """The CRM bridge: one read that carries identity AND the connection."""

    async def test_returns_the_other_side_with_its_acceptance_instant(
        self, async_session: AsyncSession, accepted_pair
    ):
        connection, user_a, user_b = accepted_pair
        repo = PeersRepository(async_session)

        (seen_by_a,) = await repo.list_accepted_peer_profiles(user_a.id)
        assert seen_by_a.peer_id == user_b.id
        assert seen_by_a.peer_display_name == "Peer Beta"
        assert seen_by_a.connection_id == connection.id
        assert seen_by_a.connected_since is not None

        # Mirrored for the other side — the pair row is symmetric.
        (seen_by_b,) = await repo.list_accepted_peer_profiles(user_b.id)
        assert seen_by_b.peer_id == user_a.id
        assert seen_by_b.peer_display_name == "Peer Alpha"

    async def test_a_pending_or_removed_pair_is_not_a_connection(
        self, async_session: AsyncSession, two_users
    ):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        connection = await repo.insert_pair_request(
            user_a.id, user_b.id, None, now=datetime.now(UTC)
        )
        await async_session.commit()
        assert await repo.list_accepted_peer_profiles(user_a.id) == []

        await repo.transition_status(
            connection.id,
            PeerConnectionStatus.REMOVED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=datetime.now(UTC),
        )
        await async_session.commit()
        assert await repo.list_accepted_peer_profiles(user_a.id) == []

    async def test_a_peer_with_no_usable_name_is_dropped(
        self, async_session: AsyncSession, accepted_pair
    ):
        """A nameless connection cannot become a CRM card — the panel would
        have nothing to title it with."""
        _connection, user_a, user_b = accepted_pair
        user_b.full_name = "   "
        async_session.add(user_b)
        await async_session.commit()

        assert await PeersRepository(async_session).list_accepted_peer_profiles(user_a.id) == []


class TestMessageRetention:
    """The row outlives the words (ADR-186) — the telephony reaper's contract."""

    async def _delivered_message(self, repo, async_session, user_a, user_b, *, expires_at):
        now = datetime.now(UTC)
        connection = await repo.insert_pair_request(user_a.id, user_b.id, None, now=now)
        await repo.transition_status(
            connection.id,
            PeerConnectionStatus.ACCEPTED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        message = await repo.enqueue_message(connection.id, user_a.id, user_b.id, "ma directive")
        await async_session.commit()
        (claimed,) = await repo.claim_pending_messages()
        await repo.mark_message_delivered(claimed.id, now=now, delivered_text="son rendu")
        message.expires_at = expires_at
        async_session.add(message)
        await async_session.commit()
        return message

    async def test_expired_texts_are_cleared_and_the_row_survives(
        self, async_session: AsyncSession, two_users
    ):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        message = await self._delivered_message(
            repo, async_session, user_a, user_b, expires_at=datetime.now(UTC) - timedelta(days=1)
        )

        assert await repo.purge_expired_message_texts(now=datetime.now(UTC)) == 1
        await async_session.commit()

        row = await async_session.get(PeerMessage, message.id)
        await async_session.refresh(row)
        assert row.content is None and row.delivered_text is None
        # The FACT survives: counts, timeline and audit outlive the words.
        assert row.status == PeerMessageStatus.DELIVERED.value
        assert row.delivered_at is not None

    async def test_a_message_within_its_horizon_keeps_its_words(
        self, async_session: AsyncSession, two_users
    ):
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        message = await self._delivered_message(
            repo, async_session, user_a, user_b, expires_at=datetime.now(UTC) + timedelta(days=1)
        )

        assert await repo.purge_expired_message_texts(now=datetime.now(UTC)) == 0
        row = await async_session.get(PeerMessage, message.id)
        await async_session.refresh(row)
        assert row.content == "ma directive"
        assert row.delivered_text == "son rendu"

    async def test_the_reaper_is_idempotent(self, async_session: AsyncSession, two_users):
        """A second sweep must not keep reporting work it already did."""
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        await self._delivered_message(
            repo, async_session, user_a, user_b, expires_at=datetime.now(UTC) - timedelta(days=1)
        )
        assert await repo.purge_expired_message_texts(now=datetime.now(UTC)) == 1
        await async_session.commit()
        assert await repo.purge_expired_message_texts(now=datetime.now(UTC)) == 0

    async def test_a_cancelled_message_keeps_the_senders_directive(
        self, async_session: AsyncSession, two_users
    ):
        """ "Here is what you tried to pass on, and it did not leave" is worth
        more than a blank line — and they are the sender's own words."""
        user_a, user_b = two_users
        repo = PeersRepository(async_session)
        now = datetime.now(UTC)
        connection = await repo.insert_pair_request(user_a.id, user_b.id, None, now=now)
        await repo.transition_status(
            connection.id,
            PeerConnectionStatus.ACCEPTED,
            expected_from=(PeerConnectionStatus.PENDING.value,),
            now=now,
        )
        message = await repo.enqueue_message(connection.id, user_a.id, user_b.id, "jamais parti")
        await async_session.commit()
        (claimed,) = await repo.claim_pending_messages()
        await repo.cancel_message(claimed.id, "cancelled_blocked")
        await async_session.commit()

        row = await async_session.get(PeerMessage, message.id)
        await async_session.refresh(row)
        assert row.status == PeerMessageStatus.CANCELLED.value
        assert row.content == "jamais parti"
        assert row.last_error == "cancelled_blocked"
