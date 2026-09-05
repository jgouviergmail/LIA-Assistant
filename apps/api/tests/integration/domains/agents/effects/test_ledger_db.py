"""The ledger against a real PostgreSQL: one winner per key, fenced closes (ADR-263).

These are the properties the whole programme rests on, and none of them can be
proven without the database: the uniqueness that makes a second claim lose, and
the conditional UPDATE that makes a stale owner's close a no-op. A mocked
session would assert that the code CALLS SQLAlchemy, not that PostgreSQL
refuses the second write.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import AgentEffect, EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """One active user owning the ledger rows under test."""
    row = User(
        email=f"ledger-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Ledger Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _request(user: User, key: str = "call-1", **overrides: object) -> ClaimRequest:
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


class TestOneWinnerPerKey:
    async def test_the_same_key_is_claimed_once(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The defect two simulations reproduced: one approval, two executions."""
        repo = EffectLedgerRepository(async_session)
        first = await repo.claim(_request(user))
        second = await repo.claim(_request(user))

        assert first.claimed is True and first.claim_token is not None
        assert second.claimed is False and second.claim_token is None
        assert second.effect.id == first.effect.id

    async def test_the_loser_can_read_what_the_winner_did(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A resume serves the recorded result instead of re-executing."""
        repo = EffectLedgerRepository(async_session)
        won = await repo.claim(_request(user, key="call-served"))
        assert won.claim_token is not None
        await repo.close_success(
            won.effect.id, won.claim_token, provider_ref="m1", result_payload={"id": "m1"}
        )

        lost = await repo.claim(_request(user, key="call-served"))
        assert lost.claimed is False
        assert lost.effect.status is EffectStatus.SUCCEEDED
        assert repo.decrypted_result(lost.effect) == {"id": "m1"}

    async def test_another_thread_may_claim_the_same_key(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The key is unique PER THREAD: two conversations do not collide."""
        repo = EffectLedgerRepository(async_session)
        assert (await repo.claim(_request(user, key="shared"))).claimed is True
        other = await repo.claim(_request(user, key="shared", thread_id="thread-B"))
        assert other.claimed is True


class TestOnlyTheOwnerCloses:
    async def test_a_stale_token_cannot_close(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="call-2"))
        assert outcome.claim_token is not None

        assert await repo.close_success(outcome.effect.id, uuid.uuid4(), provider_ref="m1") is False
        await async_session.refresh(outcome.effect)
        assert outcome.effect.status is EffectStatus.CLAIMED

    async def test_the_owner_closes_once_and_only_once(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="call-3"))
        assert outcome.claim_token is not None

        assert (
            await repo.close_success(
                outcome.effect.id,
                outcome.claim_token,
                provider_ref="m1",
                result_payload={"id": "m1"},
            )
            is True
        )
        # A second close — a retry, a duplicated callback — changes nothing.
        assert (
            await repo.close_success(outcome.effect.id, outcome.claim_token, provider_ref="m2")
            is False
        )

        await async_session.refresh(outcome.effect)
        assert outcome.effect.status is EffectStatus.SUCCEEDED
        assert outcome.effect.provider_ref == "m1"
        assert outcome.effect.closed_at is not None

    async def test_the_kept_result_is_encrypted_at_rest(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="call-4"))
        assert outcome.claim_token is not None
        await repo.close_success(
            outcome.effect.id, outcome.claim_token, result_payload={"body": "secret words"}
        )

        await async_session.refresh(outcome.effect)
        assert outcome.effect.result_payload is not None
        assert "secret words" not in outcome.effect.result_payload
        assert repo.decrypted_result(outcome.effect) == {"body": "secret words"}
        assert outcome.effect.result_digest

    async def test_a_failure_is_recorded_as_a_failure(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Absence of an exception is not proof of delivery — and neither is its presence."""
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="call-5"))
        assert outcome.claim_token is not None

        assert (
            await repo.close_failure(outcome.effect.id, outcome.claim_token, error_code="timeout")
            is True
        )
        await async_session.refresh(outcome.effect)
        assert outcome.effect.status is EffectStatus.FAILED
        assert outcome.effect.error_code == "timeout"


class TestTakeoverAndRetry:
    async def test_a_live_claim_is_never_abandoned(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """Its owner may still be inside the tool's own timeout."""
        repo = EffectLedgerRepository(async_session)
        live = await repo.claim(_request(user, key="call-6"))
        assert (
            await repo.abandon_stale(
                live.effect.id, older_than=datetime.now(UTC) - timedelta(hours=1)
            )
            is False
        )

    async def test_a_stale_claim_is_abandoned_then_retried(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        stale = await repo.claim(_request(user, key="call-7"))

        assert (
            await repo.abandon_stale(
                stale.effect.id, older_than=datetime.now(UTC) + timedelta(seconds=1)
            )
            is True
        )
        await async_session.refresh(stale.effect)
        assert stale.effect.status is EffectStatus.ABANDONED

        retry = await repo.claim(_request(user, key="call-7:retry-1", retry_of=stale.effect.id))
        assert retry.claimed is True
        assert retry.effect.retry_of == stale.effect.id

    async def test_an_abandoned_claim_cannot_be_closed_by_its_old_owner(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The stale writer must not commit after a takeover."""
        repo = EffectLedgerRepository(async_session)
        stale = await repo.claim(_request(user, key="call-8"))
        assert stale.claim_token is not None
        await repo.abandon_stale(
            stale.effect.id, older_than=datetime.now(UTC) + timedelta(seconds=1)
        )

        assert (
            await repo.close_success(stale.effect.id, stale.claim_token, provider_ref="late")
            is False
        )


class TestRefusal:
    async def test_a_refusal_is_recorded_without_claiming_the_key(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The user may grant the authority and ask again — that must be claimable."""
        repo = EffectLedgerRepository(async_session)
        refused = await repo.refuse(_request(user, key="call-9"), error_code="no_authority")

        assert refused.status is EffectStatus.REFUSED
        assert refused.error_code == "no_authority"
        assert refused.closed_at is not None
        assert (await repo.claim(_request(user, key="call-9"))).claimed is True


class TestReading:
    async def test_a_run_reads_its_effects_oldest_first(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        for index in range(3):
            await repo.claim(_request(user, key=f"run-order-{index}"))

        rows = await repo.list_for_run("run-1")
        assert [r.idempotency_key for r in rows] == [
            "run-order-0",
            "run-order-1",
            "run-order-2",
        ]

    async def test_a_page_carries_the_exact_total(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A count shown to the user is exact, or it does not exist (ADR-185)."""
        repo = EffectLedgerRepository(async_session)
        for index in range(3):
            await repo.claim(_request(user, key=f"page-{index}"))

        rows, total = await repo.list_for_user(user.id, limit=2, offset=0)
        assert len(rows) == 2
        assert total == 3

    async def test_a_user_never_reads_another_user_ledger(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        await repo.claim(_request(user, key="mine"))

        stranger = uuid.uuid4()
        rows, total = await repo.list_for_user(stranger, limit=10, offset=0)
        assert rows == [] and total == 0


class TestBoundedPayload:
    async def test_an_oversized_result_is_cut_and_says_so(
        self, async_session: AsyncSession, user: User, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A resume must never mistake half a value for the whole one."""
        from src.core.config import settings

        monkeypatch.setattr(settings, "effect_result_payload_max_bytes", 1024, raising=False)
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="big-1"))
        assert outcome.claim_token is not None

        await repo.close_success(
            outcome.effect.id, outcome.claim_token, result_payload={"body": "x" * 5000}
        )
        await async_session.refresh(outcome.effect)

        assert outcome.effect.result_truncated is True
        served = repo.decrypted_result(outcome.effect)
        assert served["truncated"] is True
        assert len(served["text"]) <= 1024

    async def test_a_result_that_fits_is_kept_whole(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="small-1"))
        assert outcome.claim_token is not None

        await repo.close_success(
            outcome.effect.id, outcome.claim_token, result_payload={"body": "short"}
        )
        await async_session.refresh(outcome.effect)
        assert outcome.effect.result_truncated is False
        assert repo.decrypted_result(outcome.effect) == {"body": "short"}


class TestTwoIndependentActors:
    """Two workers, one key: PostgreSQL decides, not a Python check.

    This test owns its data end to end — its own sessions, its own commits, its
    own cleanup — because the shared ``async_session`` runs inside a
    transaction the suite rolls back: a user created there is invisible to a
    second connection, and the contention could not even be set up.
    """

    async def test_two_sessions_contend_and_exactly_one_wins(self, async_engine: object) -> None:
        from sqlalchemy import delete, select
        from sqlalchemy.ext.asyncio import async_sessionmaker

        maker = async_sessionmaker(async_engine, expire_on_commit=False)  # type: ignore[arg-type]
        owner = User(
            email=f"contend-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Contender",
        )
        async with maker() as setup:
            setup.add(owner)
            await setup.commit()

        try:
            request = _request(owner, key="contended")
            async with maker() as session_a:
                outcome_a = await EffectLedgerRepository(session_a).claim(request)
                await session_a.commit()
            async with maker() as session_b:
                outcome_b = await EffectLedgerRepository(session_b).claim(request)
                await session_b.commit()

            assert outcome_a.claimed is True
            assert outcome_b.claimed is False
            assert outcome_b.effect.id == outcome_a.effect.id

            async with maker() as reader:
                rows = (
                    (
                        await reader.execute(
                            select(AgentEffect).where(AgentEffect.idempotency_key == "contended")
                        )
                    )
                    .scalars()
                    .all()
                )
            assert len(rows) == 1
        finally:
            # The effects cascade with the user; the user is this test's to remove.
            async with maker() as cleanup:
                await cleanup.execute(delete(User).where(User.id == owner.id))
                await cleanup.commit()


class TestTheReadableLabel:
    """The human register's material rests encrypted and comes back structured.

    Nothing fills ``label`` before lot 3b, but the column and its round-trip are
    created now so that lot needs no second migration — and an unproven column
    is a column that breaks the day it is first used.
    """

    async def test_the_label_rests_encrypted_and_round_trips(
        self, async_session: AsyncSession, user: User
    ) -> None:
        import json

        from src.core.security.utils import decrypt_data

        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(
            _request(
                user,
                key="labelled",
                label={"i18n_key": "light_turned_off", "values": {"room": "Salon"}},
            )
        )

        assert outcome.claimed is True
        stored = outcome.effect.label
        assert stored is not None
        assert "Salon" not in stored, "a room name must not rest in clear"
        assert json.loads(decrypt_data(stored)) == {
            "i18n_key": "light_turned_off",
            "values": {"room": "Salon"},
        }

    async def test_no_label_stores_nothing(self, async_session: AsyncSession, user: User) -> None:
        repo = EffectLedgerRepository(async_session)
        outcome = await repo.claim(_request(user, key="unlabelled"))
        assert outcome.effect.label is None
