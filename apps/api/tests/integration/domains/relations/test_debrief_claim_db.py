"""The debrief claim against real PostgreSQL — exclusivity, leases, fencing.

Every oracle here is a PostgreSQL behaviour a mock cannot exercise: the
``ON CONFLICT … DO UPDATE … WHERE`` really refusing a second claimant, the
unique constraint really being the arbiter, and an ``UPDATE … WHERE
claim_owner = :owner`` really writing nothing when the row has moved on.

A unit test with a stubbed session would assert the shape of a statement
nobody executed — which is how a claim that never claimed anything ships
green.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.relations.debrief.models import DebriefState
from src.domains.relations.debrief.repository import RelationDebriefRepository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 9, 7, 9, 0, tzinfo=UTC)
TODAY = date(2026, 9, 7)
YESTERDAY = date(2026, 9, 6)
KEY = "gerard dupont"
LEASE = 120


@pytest.fixture
async def owner_user(async_session: AsyncSession):
    """One active user owning the debriefs under test."""
    from src.domains.users.models import User

    user = User(
        email="debrief_owner@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Debrief Owner",
    )
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def _claim(
    session: AsyncSession,
    user,
    *,
    local_date: date = TODAY,
    language: str = "fr",
    scope_digest: str = "scope-a",
    force: bool = False,
    now: datetime = NOW,
):
    return await RelationDebriefRepository(session).claim(
        user.id,
        name_key=KEY,
        display_name="Gérard Dupont",
        local_date=local_date,
        language=language,
        scope_digest=scope_digest,
        lease_seconds=LEASE,
        force=force,
        now=now,
    )


async def _settle_ready(session: AsyncSession, user, owner, *, generated_at=NOW) -> bool:
    return await RelationDebriefRepository(session).settle_ready(
        user.id,
        name_key=KEY,
        owner=owner,
        display_name="Gérard Dupont",
        body={"headline": "ok"},
        usage={
            "tokens_in": 10,
            "tokens_out": 20,
            "tokens_cache": 0,
            "cost_eur": 0.001,
            "model_name": "gpt-4.1-mini",
        },
        evidence_digest="ev-1",
        sections_used=["open_loops"],
        unavailable=[],
        generated_at=generated_at,
    )


class TestOneBuildAtATime:
    """Two tabs on the same person must never spend two LLM calls."""

    async def test_a_second_claimant_is_refused_while_the_lease_holds(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        first = await _claim(async_session, owner_user)
        await async_session.commit()
        assert first is not None

        second = await _claim(async_session, owner_user)
        await async_session.commit()
        assert second is None

    async def test_todays_settled_debrief_is_not_rebuilt(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        owner = await _claim(async_session, owner_user)
        assert owner is not None
        assert await _settle_ready(async_session, owner_user, owner)
        await async_session.commit()

        again = await _claim(async_session, owner_user, now=NOW + timedelta(hours=6))
        await async_session.commit()
        assert again is None

    async def test_a_dead_builder_releases_the_row_when_its_lease_expires(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        """A hard kill must not wedge a relationship until the end of time."""
        assert await _claim(async_session, owner_user) is not None
        await async_session.commit()

        later = NOW + timedelta(seconds=LEASE + 1)
        assert await _claim(async_session, owner_user, now=later) is not None
        await async_session.commit()


class TestWhatMakesAStoredAnswerStale:
    """The three things that make a stored text contradict the user's settings."""

    async def test_a_new_local_day_is_rebuildable(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        owner = await _claim(async_session, owner_user, local_date=YESTERDAY)
        assert owner is not None
        assert await _settle_ready(async_session, owner_user, owner)
        await async_session.commit()

        assert await _claim(async_session, owner_user, local_date=TODAY) is not None

    async def test_a_language_change_is_rebuildable(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        """A French debrief injected into an English turn is simply wrong."""
        owner = await _claim(async_session, owner_user)
        assert owner is not None
        assert await _settle_ready(async_session, owner_user, owner)
        await async_session.commit()

        assert await _claim(async_session, owner_user, language="en") is not None

    async def test_a_scope_change_is_rebuildable(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        """The scope decides what the debrief was allowed to read."""
        owner = await _claim(async_session, owner_user)
        assert owner is not None
        assert await _settle_ready(async_session, owner_user, owner)
        await async_session.commit()

        assert await _claim(async_session, owner_user, scope_digest="scope-b") is not None

    async def test_a_forced_rebuild_ignores_all_three(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        owner = await _claim(async_session, owner_user)
        assert owner is not None
        assert await _settle_ready(async_session, owner_user, owner)
        await async_session.commit()

        assert await _claim(async_session, owner_user, force=True) is not None


class TestAFailureIsRecoverableButNotFree:
    """A gap the reader can see must be repairable — after a cooldown."""

    async def test_a_failed_build_waits_out_its_cooldown(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        owner = await _claim(async_session, owner_user)
        assert owner is not None
        cooldown_until = NOW + timedelta(minutes=10)
        assert await RelationDebriefRepository(async_session).settle_failed(
            owner_user.id, name_key=KEY, owner=owner, held_until=cooldown_until
        )
        await async_session.commit()

        assert await _claim(async_session, owner_user, now=NOW + timedelta(minutes=1)) is None
        await async_session.commit()
        assert await _claim(async_session, owner_user, now=NOW + timedelta(minutes=11)) is not None

    async def test_an_empty_relationship_is_not_retried_the_same_day(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        """Nothing to say is an ANSWER, not a failure — it costs no retry."""
        owner = await _claim(async_session, owner_user)
        assert owner is not None
        assert await RelationDebriefRepository(async_session).settle_empty(
            owner_user.id, name_key=KEY, owner=owner, sections_used=[], unavailable=[]
        )
        await async_session.commit()

        assert await _claim(async_session, owner_user, now=NOW + timedelta(hours=3)) is None


class TestAStaleWriterWritesNothing:
    """The fencing token: whoever lost the row may not overwrite the winner."""

    async def test_settling_with_a_lost_claim_is_refused(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        stale_owner = await _claim(async_session, owner_user)
        assert stale_owner is not None
        await async_session.commit()

        # The lease expires and a second builder takes over.
        fresh_owner = await _claim(
            async_session, owner_user, now=NOW + timedelta(seconds=LEASE + 1)
        )
        assert fresh_owner is not None and fresh_owner != stale_owner
        await async_session.commit()

        # The first builder finally finishes. It owns nothing any more.
        assert not await _settle_ready(async_session, owner_user, stale_owner)
        await async_session.commit()

        stored = await RelationDebriefRepository(async_session).get(owner_user.id, KEY)
        assert stored is not None
        assert stored.state is DebriefState.BUILDING
        assert stored.claim_owner == fresh_owner


class TestAnUnchangedRebuildKeepsItsDate:
    """A verified "nothing changed" moves the DAY, never the words' timestamp."""

    async def test_touch_carries_the_day_without_moving_generated_at(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        first_owner = await _claim(async_session, owner_user, local_date=YESTERDAY)
        assert first_owner is not None
        written_at = NOW - timedelta(days=1)
        assert await _settle_ready(async_session, owner_user, first_owner, generated_at=written_at)
        await async_session.commit()

        owner = await _claim(async_session, owner_user, local_date=TODAY)
        assert owner is not None
        assert await RelationDebriefRepository(async_session).carry_forward(
            owner_user.id,
            name_key=KEY,
            owner=owner,
            local_date=TODAY,
            state=DebriefState.READY,
        )
        await async_session.commit()

        stored = await RelationDebriefRepository(async_session).get(owner_user.id, KEY)
        assert stored is not None
        assert stored.state is DebriefState.READY
        assert stored.generated_for == TODAY
        assert stored.generated_at == written_at
        assert stored.body == {"headline": "ok"}


class TestWhatTheChatDirectoryReads:
    """The injection list: ready debriefs, bounded by an age, never by "today"."""

    async def test_only_ready_rows_within_the_age_are_listed(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        repo = RelationDebriefRepository(async_session)
        owner = await _claim(async_session, owner_user, local_date=YESTERDAY)
        assert owner is not None
        assert await _settle_ready(async_session, owner_user, owner)
        await async_session.commit()

        assert [
            row.name_key for row in await repo.list_injectable(owner_user.id, not_before=YESTERDAY)
        ] == [KEY]
        assert await repo.list_injectable(owner_user.id, not_before=TODAY) == []

    async def test_a_build_in_flight_is_never_injected(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        assert await _claim(async_session, owner_user) is not None
        await async_session.commit()

        listed = await RelationDebriefRepository(async_session).list_injectable(
            owner_user.id, not_before=YESTERDAY
        )
        assert listed == []


class TestAnIdentityThatNoLongerExists:
    """A merge or a split changes who is who — the old debrief must go."""

    async def test_deleting_by_key_removes_the_row(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        repo = RelationDebriefRepository(async_session)
        assert await _claim(async_session, owner_user) is not None
        await async_session.commit()

        assert await repo.delete_for_keys(owner_user.id, [KEY]) == 1
        await async_session.commit()
        assert await repo.get(owner_user.id, KEY) is None

    async def test_deleting_nothing_is_a_no_op(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        repo = RelationDebriefRepository(async_session)
        assert await repo.delete_for_keys(owner_user.id, []) == 0
        assert await repo.delete_for_keys(owner_user.id, [""]) == 0


class TestAFailedRebuildLeavesThePreviousAnswerStanding:
    """Replacing a usable debrief with an empty panel turns "I could not
    refresh this" into "there is nothing" — the same lie, one layer up."""

    async def test_a_failure_keeps_the_body_and_its_date(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        repo = RelationDebriefRepository(async_session)
        first = await _claim(async_session, owner_user, local_date=YESTERDAY)
        assert first is not None
        written_at = NOW - timedelta(days=1)
        assert await _settle_ready(async_session, owner_user, first, generated_at=written_at)
        await async_session.commit()

        second = await _claim(async_session, owner_user, local_date=TODAY)
        assert second is not None
        assert await repo.settle_failed(
            owner_user.id, name_key=KEY, owner=second, held_until=NOW + timedelta(minutes=10)
        )
        await async_session.commit()

        stored = await repo.get(owner_user.id, KEY)
        assert stored is not None
        assert stored.state is DebriefState.FAILED
        # The words the reader could still use are exactly where they were.
        assert stored.body == {"headline": "ok"}
        assert stored.generated_at == written_at
        assert stored.evidence_digest == "ev-1"

    async def test_an_emptied_relationship_does_clear_its_body(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        """The opposite case: the old text describes data that is gone."""
        repo = RelationDebriefRepository(async_session)
        first = await _claim(async_session, owner_user, local_date=YESTERDAY)
        assert first is not None
        assert await _settle_ready(async_session, owner_user, first)
        await async_session.commit()

        second = await _claim(async_session, owner_user, local_date=TODAY)
        assert second is not None
        assert await repo.settle_empty(
            owner_user.id, name_key=KEY, owner=second, sections_used=[], unavailable=[]
        )
        await async_session.commit()

        stored = await repo.get(owner_user.id, KEY)
        assert stored is not None
        assert stored.state is DebriefState.EMPTY
        assert stored.body is None
        assert stored.generated_at is None

    async def test_carry_forward_never_promotes_an_empty_row(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        """An unchanged empty relationship stays empty — never a bodyless "ready"."""
        repo = RelationDebriefRepository(async_session)
        first = await _claim(async_session, owner_user, local_date=YESTERDAY)
        assert first is not None
        assert await repo.settle_empty(
            owner_user.id, name_key=KEY, owner=first, sections_used=[], unavailable=[]
        )
        await async_session.commit()

        second = await _claim(async_session, owner_user, local_date=TODAY)
        assert second is not None
        assert await repo.carry_forward(
            owner_user.id,
            name_key=KEY,
            owner=second,
            local_date=TODAY,
            state=DebriefState.EMPTY,
        )
        await async_session.commit()

        stored = await repo.get(owner_user.id, KEY)
        assert stored is not None
        assert stored.state is DebriefState.EMPTY
        assert stored.generated_for == TODAY
        assert stored.body is None


class TestTheStoredSpellingIsTheCanonicalOne:
    """The card and the chat must name the same person the same way.

    The claim writes whatever spelling the request carried; the settle replaces
    it with the one the card resolved. Without that, opening a relationship by
    a raw counterparty string — a phone number, an all-lowercase echo — would
    have the chat block greet somebody by it.
    """

    async def test_settling_replaces_the_claimed_spelling(
        self, async_session: AsyncSession, owner_user
    ) -> None:
        repo = RelationDebriefRepository(async_session)
        owner = await repo.claim(
            owner_user.id,
            name_key=KEY,
            display_name="0612345678",
            local_date=TODAY,
            language="fr",
            scope_digest="scope-a",
            lease_seconds=LEASE,
            now=NOW,
        )
        assert owner is not None
        assert await repo.settle_ready(
            owner_user.id,
            name_key=KEY,
            owner=owner,
            display_name="Gérard Dupont",
            body={"headline": "ok"},
            usage=None,
            evidence_digest="ev-1",
            sections_used=[],
            unavailable=[],
            generated_at=NOW,
        )
        await async_session.commit()

        stored = await repo.get(owner_user.id, KEY)
        assert stored is not None
        assert stored.display_name == "Gérard Dupont"
