"""The notary and its verdict, against a real PostgreSQL (ADR-263, lot 5).

The pure half of the chain — the encoding, the link, the walk — is pinned in
the unit suite, without a database, because it must be. What CANNOT be pinned
there is everything this file asserts: that the pending set is found through
the partial indexes and not by luck, that a claim and its close produce two
entries rather than one alteration alarm, that a second pass appends nothing,
that a row committed late is picked up rather than lost, and that a rewritten
or deleted register row is actually detected.

A mocked session would assert that the code CALLS SQLAlchemy. Only PostgreSQL
can assert that ``UNIQUE (user_id, seq)`` refuses the loser of a race, and only
a real row can be silently ``UPDATE``d to see whether the chain notices.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from sqlalchemy import delete, select, update
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.chain_link import ChainBreak
from src.domains.agents.effects.chain_repository import ChainRepository
from src.domains.agents.effects.chain_spec import GENESIS_KIND
from src.domains.agents.effects.chain_verify import verify_chain
from src.domains.agents.effects.models import (
    AgentEffect,
    AgentTreatment,
    EffectSource,
    LedgerChainEntry,
    TreatmentOutcome,
)
from src.domains.agents.effects.notary import notarise_account
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration

_LIMIT = 500


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account whose chain is under test."""
    row = User(
        email=f"notary-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Notary Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


@pytest.fixture
async def other(async_session: AsyncSession) -> User:
    """A second account, to prove chains do not touch each other."""
    row = User(
        email=f"notary-b-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Other Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _request(user: User, key: str, **overrides: object) -> ClaimRequest:
    base: dict[str, object] = {
        "user_id": user.id,
        "thread_id": "thread-A",
        "run_id": "run-1",
        "source": "user",
        "execution_mode": "react",
        "tool_name": "send_email_tool",
        "mutation_policy": "draft",
        "idempotency_key": key,
        "args_digest": "a" * 64,
    }
    base.update(overrides)
    return ClaimRequest(**base)  # type: ignore[arg-type]


async def _treatment(
    session: AsyncSession, user: User, *, tool: str = "get_emails_tool", minutes: int = 0
) -> AgentTreatment:
    """One consultation, written directly: the recorder is tested elsewhere."""
    row = AgentTreatment(
        user_id=user.id,
        thread_id="thread-A",
        run_id="run-1",
        source=EffectSource.USER,
        execution_mode="react",
        tool_name=tool,
        mutation_policy="read",
        outcome=TreatmentOutcome.OK,
        duration_ms=12,
        occurred_at=datetime.now(UTC) - timedelta(minutes=minutes),
    )
    session.add(row)
    await session.flush()
    return row


async def _entries(session: AsyncSession, user: User) -> list[LedgerChainEntry]:
    rows = await session.execute(
        select(LedgerChainEntry)
        .where(LedgerChainEntry.user_id == user.id)
        .order_by(LedgerChainEntry.seq)
    )
    return list(rows.scalars().all())


class TestAFirstPassOpensTheChain:
    async def test_the_first_entry_is_a_genesis_that_covers_nothing(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Silence would let a reader assume the whole history was notarised."""
        await _treatment(async_session, user)

        done = await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        assert done.opened is True
        assert done.entries == 2, "one genesis plus one consultation"
        rows = await _entries(async_session, user)
        assert rows[0].kind == GENESIS_KIND
        assert rows[0].subject_id is None
        assert rows[0].prev_hash is None
        assert rows[0].seq == 1

    async def test_the_genesis_states_how_many_rows_predate_the_chain(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A retroactively notarised row attests to its state at OPENING, not
        at creation. The count is what tells a reader which of the two it is."""
        from src.domains.agents.effects.chain_repository import genesis_digest

        await _treatment(async_session, user)
        await _treatment(async_session, user, tool="get_events_tool")

        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        rows = await _entries(async_session, user)
        assert rows[0].payload_digest == genesis_digest(user.id, uncovered=2)
        assert rows[0].payload_digest != genesis_digest(user.id, uncovered=0)

    async def test_an_account_with_nothing_pending_gets_no_chain(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A chain nobody needed is a row nobody can explain."""
        done = await notarise_account(async_session, user.id, limit=_LIMIT)

        assert (done.entries, done.opened) == (0, False)
        assert await _entries(async_session, user) == []


class TestTheChainCoversWhatItClaimsTo:
    async def test_a_claim_and_its_close_are_TWO_entries(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """One digest taken at claim time would turn every legitimate close
        into a tampering alarm. That is why coverage is split in two stages."""
        repository = EffectLedgerRepository(async_session)
        outcome = await repository.claim(_request(user, "call-1"))
        assert outcome.claim_token is not None
        await repository.close_success(outcome.effect.id, outcome.claim_token, provider_ref="msg-1")
        await async_session.flush()

        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        kinds = [row.kind for row in await _entries(async_session, user)]
        assert kinds == [GENESIS_KIND, "effect.claimed", "effect.settled"]

    async def test_a_normal_lifecycle_verifies_CLEAN(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The whole design fails if closing an effect reads as tampering."""
        repository = EffectLedgerRepository(async_session)
        outcome = await repository.claim(_request(user, "call-1"))
        assert outcome.claim_token is not None
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await repository.close_success(outcome.effect.id, outcome.claim_token)
        await async_session.flush()
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        audit = await verify_chain(async_session, user.id, deep=True)
        assert audit.ok, f"{audit.reason} at seq {audit.broken_at_seq}"
        assert audit.entries == 3
        assert audit.payloads_checked == 2

    async def test_a_still_open_claim_contributes_only_its_claim_stage(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """An effect in flight has no outcome to notarise yet."""
        repository = EffectLedgerRepository(async_session)
        await repository.claim(_request(user, "call-1"))
        await async_session.flush()

        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        kinds = [row.kind for row in await _entries(async_session, user)]
        assert kinds == [GENESIS_KIND, "effect.claimed"]

    async def test_a_refusal_is_notarised_in_both_stages_at_once(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A refusal is inserted already closed: it has a claim AND an outcome
        from the first instant, and both are facts worth notarising."""
        repository = EffectLedgerRepository(async_session)
        await repository.refuse(_request(user, "call-1"), error_code="not_authorised")
        await async_session.flush()

        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        kinds = [row.kind for row in await _entries(async_session, user)]
        assert kinds == [GENESIS_KIND, "effect.claimed", "effect.settled"]


class TestAPassIsIdempotentAndCatchesUp:
    async def test_a_second_pass_appends_NOTHING(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        done = await notarise_account(async_session, user.id, limit=_LIMIT)

        assert (done.entries, done.opened) == (0, False)
        assert len(await _entries(async_session, user)) == 2

    async def test_a_row_created_after_a_pass_is_picked_up_by_the_next(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The marker, not a watermark: a watermark would skip a row whose
        transaction committed after the notary read the clock."""
        await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        late = await _treatment(async_session, user, tool="get_events_tool", minutes=30)
        done = await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        assert done.entries == 1, "the late row was not notarised"
        rows = await _entries(async_session, user)
        assert rows[-1].subject_id == late.id
        assert (await verify_chain(async_session, user.id, deep=True)).ok

    async def test_a_pass_over_its_ceiling_leaves_the_rest_pending(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A backlog is worked in ticks, never in one long transaction."""
        for index in range(5):
            await _treatment(async_session, user, tool="get_emails_tool", minutes=index)

        done = await notarise_account(async_session, user.id, limit=2)
        await async_session.flush()

        assert done.entries == 3, "genesis plus the two the ceiling allowed"
        _, pending = await ChainRepository(async_session).counts()
        assert pending == 3

    async def test_the_oldest_pending_row_is_chained_FIRST(
        self, async_session: AsyncSession, user: User
    ) -> None:
        newest = await _treatment(async_session, user, minutes=0)
        oldest = await _treatment(async_session, user, tool="get_events_tool", minutes=90)

        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        subjects = [row.subject_id for row in await _entries(async_session, user)]
        assert subjects == [None, oldest.id, newest.id]


class TestAnAlteredREGISTERRowIsDetected:
    async def test_a_rewritten_row_breaks_the_chain_at_its_own_position(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The question the chain exists for. A shallow walk cannot see this."""
        treatment = await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(
            update(AgentTreatment)
            .where(AgentTreatment.id == treatment.id)
            .values(tool_name="something_else_tool")
        )
        await async_session.flush()

        audit = await verify_chain(async_session, user.id, deep=True)

        assert not audit.ok
        assert audit.reason is ChainBreak.PAYLOAD
        assert audit.broken_at_seq == 2

    async def test_a_shallow_walk_does_NOT_see_a_rewritten_row(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Stated rather than hidden: shallow verifies the chain, not the data.
        Believing otherwise is how an audit becomes theatre."""
        treatment = await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()
        await async_session.execute(
            update(AgentTreatment)
            .where(AgentTreatment.id == treatment.id)
            .values(tool_name="something_else_tool")
        )
        await async_session.flush()

        assert (await verify_chain(async_session, user.id)).ok

    async def test_a_DELETED_row_breaks_the_chain(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Deleting the evidence must be as visible as editing it."""
        treatment = await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(delete(AgentTreatment).where(AgentTreatment.id == treatment.id))
        await async_session.flush()

        audit = await verify_chain(async_session, user.id, deep=True)

        assert not audit.ok
        assert audit.reason is ChainBreak.PAYLOAD

    async def test_a_closed_effect_edited_after_notarisation_is_caught(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The outcome stage covers `status`: a FAILED turned SUCCEEDED is the
        alteration that would most change what a user believes happened."""
        repository = EffectLedgerRepository(async_session)
        outcome = await repository.claim(_request(user, "call-1"))
        assert outcome.claim_token is not None
        await repository.close_failure(
            outcome.effect.id, outcome.claim_token, error_code="provider_error"
        )
        await async_session.flush()
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(
            update(AgentEffect)
            .where(AgentEffect.id == outcome.effect.id)
            .values(status="succeeded")
        )
        await async_session.flush()

        audit = await verify_chain(async_session, user.id, deep=True)

        assert not audit.ok
        assert audit.reason is ChainBreak.PAYLOAD
        assert audit.broken_at_seq == 3, "the OUTCOME entry, not the claim"


class TestAnAlteredENTRYIsDetected:
    async def test_a_rewritten_entry_is_caught_without_touching_the_rows(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(
            update(LedgerChainEntry)
            .where(LedgerChainEntry.user_id == user.id, LedgerChainEntry.seq == 2)
            .values(payload_digest="f" * 64)
        )
        await async_session.flush()

        audit = await verify_chain(async_session, user.id)

        assert not audit.ok
        assert audit.reason is ChainBreak.ENTRY_HASH
        assert audit.broken_at_seq == 2

    async def test_a_deleted_entry_leaves_a_gap_that_is_caught(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Someone removing the entry that covers a row they edited."""
        await _treatment(async_session, user)
        await _treatment(async_session, user, tool="get_events_tool", minutes=5)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(
            delete(LedgerChainEntry).where(
                LedgerChainEntry.user_id == user.id, LedgerChainEntry.seq == 2
            )
        )
        await async_session.flush()

        audit = await verify_chain(async_session, user.id)

        assert not audit.ok
        assert audit.reason is ChainBreak.SEQUENCE


class TestChainsAreIndependentPerAccount:
    async def test_two_accounts_hold_two_chains_that_both_verify(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        await _treatment(async_session, user)
        await _treatment(async_session, other)

        await notarise_account(async_session, user.id, limit=_LIMIT)
        await notarise_account(async_session, other.id, limit=_LIMIT)
        await async_session.flush()

        assert (await verify_chain(async_session, user.id, deep=True)).ok
        assert (await verify_chain(async_session, other.id, deep=True)).ok
        assert [row.seq for row in await _entries(async_session, user)] == [1, 2]
        assert [row.seq for row in await _entries(async_session, other)] == [1, 2]

    async def test_erasing_one_account_leaves_the_others_chain_INTACT(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        """This is the decision the whole design turns on: inalterability and
        the right to erasure coexist because a chain is per ACCOUNT. A global
        chain would keep a permanent, unfixable hole at every deletion."""
        await _treatment(async_session, user)
        await _treatment(async_session, other)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await notarise_account(async_session, other.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(delete(User).where(User.id == user.id))
        await async_session.flush()

        assert await _entries(async_session, user) == [], "the chain outlived the account"
        assert (await verify_chain(async_session, other.id, deep=True)).ok

    async def test_an_account_with_no_chain_verifies_OK(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Nothing done, nothing to prove — never an incident."""
        audit = await verify_chain(async_session, user.id, deep=True)

        assert audit.ok
        assert audit.entries == 0
        assert audit.head_hash is None


class TestTwoNotariesCannotForkAChain:
    """Owns its data end to end — its own sessions, commits and cleanup.

    The shared ``async_session`` runs inside a transaction the suite rolls
    back, so a row written there is invisible to a second connection and the
    contention could not even be set up.
    """

    async def test_the_loser_of_a_race_is_REFUSED_and_the_work_stays_pending(
        self, async_engine: object
    ) -> None:
        import asyncio

        from sqlalchemy.exc import IntegrityError
        from sqlalchemy.ext.asyncio import async_sessionmaker

        maker = async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]
        owner = User(
            email=f"race-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Race Owner",
        )
        async with maker() as setup:
            setup.add(owner)
            await setup.flush()
            await _treatment(setup, owner)
            await setup.commit()

        async def one_pass() -> str:
            """A whole pass on its own connection, exactly as the job runs it."""
            async with maker() as session:
                try:
                    await notarise_account(session, owner.id, limit=_LIMIT)
                    await session.commit()
                except IntegrityError:
                    await session.rollback()
                    return "refused"
                return "won"

        try:
            # Both read the same empty head before either has committed: the
            # interleaving leader election is meant to prevent, and that the
            # schema must survive anyway. The loser BLOCKS on the unique index
            # until the winner commits, then is refused.
            verdicts = await asyncio.wait_for(asyncio.gather(one_pass(), one_pass()), timeout=30)

            assert sorted(verdicts) == ["refused", "won"], verdicts
            async with maker() as reader:
                rows = await _entries(reader, owner)
                assert [row.seq for row in rows] == [1, 2], "the chain forked"
                audit = await verify_chain(reader, owner.id, deep=True)
                assert audit.ok
                _, pending = await ChainRepository(reader).counts()
                assert pending == 0, "the winner's work was rolled back too"
        finally:
            async with maker() as cleanup:
                await cleanup.execute(delete(User).where(User.id == owner.id))
                await cleanup.commit()

    async def test_a_pass_notarises_the_other_accounts_despite_one_failure(
        self, async_engine: object
    ) -> None:
        """One account's rolled-back transaction must not cost anyone else's."""
        from unittest.mock import patch

        from sqlalchemy.ext.asyncio import async_sessionmaker

        from src.domains.agents.effects import notary as notary_module

        maker = async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]
        owners = [
            User(
                email=f"pass-{index}-{uuid.uuid4().hex[:8]}@test.local",
                hashed_password="x",
                is_active=True,
                is_superuser=False,
                full_name=f"Pass Owner {index}",
            )
            for index in range(2)
        ]
        async with maker() as setup:
            for owner in owners:
                setup.add(owner)
            await setup.flush()
            for owner in owners:
                await _treatment(setup, owner)
            await setup.commit()

        failing = sorted(owners, key=lambda row: str(row.id))[0].id
        real = notary_module.notarise_account

        async def _sometimes_fails(db: object, user_id: uuid.UUID, **kwargs: object) -> object:
            if user_id == failing:
                raise OperationalError("boom", None, Exception("boom"))
            return await real(db, user_id, **kwargs)  # type: ignore[arg-type]

        try:
            with patch.object(notary_module, "notarise_account", _sometimes_fails):
                async with maker() as session:
                    report = await notary_module.run_notary_pass(session)

            assert report.failed == 1
            assert report.accounts >= 1, "the healthy account was not notarised"
            async with maker() as reader:
                for owner in owners:
                    rows = await _entries(reader, owner)
                    assert (rows == []) is (owner.id == failing)
        finally:
            async with maker() as cleanup:
                for owner in owners:
                    await cleanup.execute(delete(User).where(User.id == owner.id))
                await cleanup.commit()


class TestVerificationIsHonestAboutWhatItDidNotCheck:
    async def test_an_entry_under_a_SUPERSEDED_encoding_is_not_judged(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Recomputing it with today's rules would report a break that never
        happened. An audit device whose false positives train an operator to
        ignore it is worse than no device at all."""
        await _treatment(async_session, user)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        await async_session.execute(
            update(LedgerChainEntry)
            .where(LedgerChainEntry.user_id == user.id, LedgerChainEntry.seq == 2)
            .values(digest_version=99)
        )
        await async_session.flush()

        audit = await verify_chain(async_session, user.id, deep=True)

        assert audit.ok, "an older encoding was judged by today's rules"
        assert audit.payloads_skipped == 1
        assert audit.payloads_checked == 0

    async def test_a_verification_spanning_several_PAGES_holds(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The page seam is the one place a paginated verifier can silently
        accept a chain it never checked."""
        from src.core.config import settings

        for index in range(9):
            await _treatment(async_session, user, minutes=index)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()

        with patch.object(settings, "ledger_chain_verify_page", 2):
            audit = await verify_chain(async_session, user.id, deep=True)

        assert audit.ok
        assert audit.entries == 10, "genesis plus nine consultations"
        assert audit.payloads_checked == 9

    async def test_a_break_on_a_LATER_page_is_still_found(
        self, async_session: AsyncSession, user: User
    ) -> None:
        from src.core.config import settings

        for index in range(9):
            await _treatment(async_session, user, minutes=index)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()
        await async_session.execute(
            update(LedgerChainEntry)
            .where(LedgerChainEntry.user_id == user.id, LedgerChainEntry.seq == 8)
            .values(payload_digest="f" * 64)
        )
        await async_session.flush()

        with patch.object(settings, "ledger_chain_verify_page", 2):
            audit = await verify_chain(async_session, user.id, deep=True)

        assert not audit.ok
        assert audit.broken_at_seq == 8
        assert audit.reason is ChainBreak.ENTRY_HASH


class TestTheVerdictSurfaces:
    async def test_a_user_sees_what_is_sealed_and_what_is_NOT_yet(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """« verified » must never be read as « all of it »: notarising is
        asynchronous, so the newest rows are not covered yet."""
        from src.domains.agents.effects.chain_router import _verify_one

        await _treatment(async_session, user, minutes=10)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()
        await _treatment(async_session, user, tool="get_events_tool", minutes=0)
        await async_session.flush()

        status = await _verify_one(async_session, user.id, deep=True)

        assert status.ok
        assert status.pending == 1, "the window is not disclosed"
        assert status.sealed_until is not None
        assert status.head_hash is not None and len(status.head_hash) == 64

    async def test_an_account_that_has_done_nothing_is_not_an_incident(
        self, async_session: AsyncSession, user: User
    ) -> None:
        from src.domains.agents.effects.chain_router import _verify_one

        status = await _verify_one(async_session, user.id, deep=True)

        assert (status.ok, status.entries, status.pending) == (True, 0, 0)
        assert status.sealed_until is None

    async def test_an_administrator_sweep_puts_the_BROKEN_chain_first(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        """An operator opening this must not have to scroll to find it."""
        from src.domains.agents.effects.chain_router import verify_chains

        await _treatment(async_session, user)
        await _treatment(async_session, other)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await notarise_account(async_session, other.id, limit=_LIMIT)
        await async_session.flush()
        await async_session.execute(
            update(LedgerChainEntry)
            .where(LedgerChainEntry.user_id == other.id, LedgerChainEntry.seq == 2)
            .values(entry_hash="f" * 64)
        )
        await async_session.flush()

        sweep = await verify_chains(
            user_ids=[user.id, other.id], deep=True, db=async_session, admin=user
        )

        assert [row.user_id for row in sweep.rows] == [str(other.id), str(user.id)]
        assert sweep.rows[0].ok is False and sweep.rows[1].ok is True

    async def test_the_admin_sweep_verifies_every_chain_when_none_is_named(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        from src.domains.agents.effects.chain_router import verify_chains

        await _treatment(async_session, user)
        await _treatment(async_session, other)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await notarise_account(async_session, other.id, limit=_LIMIT)
        await async_session.flush()

        sweep = await verify_chains(user_ids=None, deep=False, db=async_session, admin=user)

        assert {row.user_id for row in sweep.rows} >= {str(user.id), str(other.id)}
        assert all(row.ok for row in sweep.rows)

    async def test_a_sweep_STATES_how_many_accounts_it_did_not_reach(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        """Fifty green rows must never be read as an answer about five hundred
        accounts. The cap is stated, never applied in silence (ADR-185)."""
        from unittest.mock import patch as _patch

        from src.domains.agents.effects import chain_router
        from src.domains.agents.effects.chain_router import verify_chains

        await _treatment(async_session, user)
        await _treatment(async_session, other)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await notarise_account(async_session, other.id, limit=_LIMIT)
        await async_session.flush()

        with _patch.object(chain_router, "MAX_ADMIN_ACCOUNTS", 1):
            sweep = await verify_chains(user_ids=None, deep=False, db=async_session, admin=user)

        assert sweep.accounts_checked == 1
        assert sweep.accounts_with_chain >= 2, "the exact total came from the page length"
        assert sweep.limit == 1

    async def test_a_NAMED_list_is_capped_too(
        self, async_session: AsyncSession, user: User, other: User
    ) -> None:
        """An unbounded list of ids is the same unbounded work wearing a
        different hat."""
        from unittest.mock import patch as _patch

        from src.domains.agents.effects import chain_router
        from src.domains.agents.effects.chain_router import verify_chains

        await _treatment(async_session, user)
        await _treatment(async_session, other)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await notarise_account(async_session, other.id, limit=_LIMIT)
        await async_session.flush()

        with _patch.object(chain_router, "MAX_ADMIN_ACCOUNTS", 1):
            sweep = await verify_chains(
                user_ids=[user.id, other.id], deep=True, db=async_session, admin=user
            )

        assert sweep.accounts_checked == 1

    async def test_the_STATUS_endpoint_checks_nothing_and_says_so(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A page opening must not run an audit nobody asked for — and must not
        imply one either, which is why this payload carries no verdict."""
        from src.domains.agents.effects.chain_router import ChainSeal, own_chain_seal

        await _treatment(async_session, user, minutes=10)
        await notarise_account(async_session, user.id, limit=_LIMIT)
        await async_session.flush()
        await _treatment(async_session, user, tool="get_events_tool", minutes=0)
        await async_session.flush()

        seal = await own_chain_seal(db=async_session, user=user)

        assert isinstance(seal, ChainSeal)
        assert (seal.entries, seal.pending) == (2, 1)
        assert seal.sealed_until is not None
        assert not hasattr(seal, "ok"), "a status must not look like a verdict"

    async def test_the_status_distinguishes_OFF_from_NOT_YET(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """« Nothing sealed » is otherwise ambiguous between a switched-off
        instance and a notary that has simply not passed."""
        from src.core.config import settings
        from src.domains.agents.effects.chain_router import own_chain_seal

        with patch.object(settings, "ledger_chain_enabled", False):
            off = await own_chain_seal(db=async_session, user=user)
        with patch.object(settings, "ledger_chain_enabled", True):
            on = await own_chain_seal(db=async_session, user=user)

        assert (off.sealing_enabled, on.sealing_enabled) == (False, True)
        assert off.entries == on.entries == 0


class TestTheDigestSurvivesTheDatabaseRoundTrip:
    """An instant sealed by one CONNECTION must verify from another.

    The canonical encoding normalises every datetime to UTC, and a unit test
    pins that on in-memory values. What it cannot pin is what the DRIVER hands
    back: if a ``TIMESTAMPTZ`` came back rendered in the session's zone, the
    same row would digest differently depending on which connection read it,
    and every verification from a differently configured session would report a
    tampering that never happened.

    Two real sessions, then — one per zone. Reusing a single session would prove
    nothing at all: SQLAlchemy's identity map would hand the second read the
    very object the first one built.
    """

    async def test_a_chain_sealed_in_one_ZONE_verifies_from_another(
        self, async_engine: object
    ) -> None:
        from sqlalchemy import text as sql_text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        maker = async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]
        owner = User(
            email=f"zones-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Zone Owner",
        )
        async with maker() as setup:
            setup.add(owner)
            await setup.flush()
            await _treatment(setup, owner)
            await setup.commit()

        try:
            async with maker() as sealing:
                await sealing.execute(sql_text("SET TIME ZONE 'Europe/Paris'"))
                await notarise_account(sealing, owner.id, limit=_LIMIT)
                await sealing.commit()

            async with maker() as verifying:
                # A zone deliberately absurd and far from both UTC and Paris.
                await verifying.execute(sql_text("SET TIME ZONE 'Pacific/Kiritimati'"))
                audit = await verify_chain(verifying, owner.id, deep=True)

            assert audit.ok, f"{audit.reason} at seq {audit.broken_at_seq}"
            assert audit.payloads_checked == 1
        finally:
            async with maker() as cleanup:
                await cleanup.execute(delete(User).where(User.id == owner.id))
                await cleanup.commit()

    async def test_a_row_read_by_two_connections_digests_the_SAME(
        self, async_engine: object
    ) -> None:
        """Stability, said plainly: two reads of an untouched row must agree,
        or every verification is a coin toss."""
        from sqlalchemy import text as sql_text
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from src.domains.agents.effects.chain_spec import TREATMENT_RECORDED, digest_of

        maker = async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]
        owner = User(
            email=f"stable-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Stable Owner",
        )
        async with maker() as setup:
            setup.add(owner)
            await setup.flush()
            row = await _treatment(setup, owner)
            treatment_id = row.id
            await setup.commit()

        try:
            digests = []
            for zone in ("UTC", "America/Santiago"):
                async with maker() as reader:
                    await reader.execute(sql_text(f"SET TIME ZONE '{zone}'"))
                    found = (
                        await reader.execute(
                            select(AgentTreatment).where(AgentTreatment.id == treatment_id)
                        )
                    ).scalar_one()
                    digests.append(digest_of(found, TREATMENT_RECORDED))

            assert digests[0] == digests[1], "the same row digested two ways"
        finally:
            async with maker() as cleanup:
                await cleanup.execute(delete(User).where(User.id == owner.id))
                await cleanup.commit()
