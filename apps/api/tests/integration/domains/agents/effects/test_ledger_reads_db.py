"""The register READ back, against a real PostgreSQL (ADR-263).

Every proof surface — the card under a bubble, the debug panel, the journal,
both exports — reads through these four queries. A mocked session would assert
that the code calls SQLAlchemy; only the database can say that the filters
select, that the aggregate counts the whole set rather than the page, and that
an encrypted label survives the round trip and comes back as a sentence.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import EffectStatus
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    row = User(
        email=f"reads-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Register Reader",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _request(user: User, key: str, **overrides: object) -> ClaimRequest:
    base: dict[str, object] = {
        "user_id": user.id,
        "thread_id": "thread-reads",
        "run_id": "run-reads",
        "source": "user",
        "execution_mode": "pipeline",
        "tool_name": "control_hue_light_tool",
        "mutation_policy": "reversible",
        "idempotency_key": key,
        "args_digest": "a" * 64,
    }
    base.update(overrides)
    return ClaimRequest(**base)  # type: ignore[arg-type]


async def _claim(session: AsyncSession, request: ClaimRequest) -> uuid.UUID:
    outcome = await EffectLedgerRepository(session).claim(request)
    await session.flush()
    assert outcome.claimed
    return outcome.effect.id


class TestReadingOneTurn:
    async def test_only_the_asked_run_comes_back(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _claim(async_session, _request(user, "k1", run_id="run-A"))
        await _claim(async_session, _request(user, "k2", run_id="run-B"))

        rows = await EffectLedgerRepository(async_session).list_for_run("run-A")

        assert [row.run_id for row in rows] == ["run-A"]

    async def test_rows_come_back_oldest_first(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _claim(async_session, _request(user, "k1", run_id="run-C"))
        await _claim(async_session, _request(user, "k2", run_id="run-C"))

        rows = await EffectLedgerRepository(async_session).list_for_run("run-C")

        assert len(rows) == 2
        assert rows[0].claimed_at <= rows[1].claimed_at


class TestTheJournalCountsTheWholeSet:
    async def test_the_total_is_not_the_page(self, async_session: AsyncSession, user: User) -> None:
        for index in range(5):
            await _claim(async_session, _request(user, f"page-{index}"))

        rows, total = await EffectLedgerRepository(async_session).list_for_user(
            user.id, limit=2, offset=0
        )

        assert len(rows) == 2
        assert total == 5, "the aggregate must count every row, not the page"

    async def test_a_page_beyond_the_end_is_empty_but_the_total_holds(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _claim(async_session, _request(user, "only-one"))

        rows, total = await EffectLedgerRepository(async_session).list_for_user(
            user.id, limit=10, offset=50
        )

        assert rows == []
        assert total == 1

    async def test_another_user_s_rows_never_appear(
        self, async_session: AsyncSession, user: User
    ) -> None:
        other = User(
            email=f"other-{uuid.uuid4().hex[:8]}@test.local",
            hashed_password="x",
            is_active=True,
            is_superuser=False,
            full_name="Someone Else",
        )
        async_session.add(other)
        await async_session.flush()
        await _claim(async_session, _request(user, "mine"))
        await _claim(async_session, _request(other, "theirs", thread_id="thread-other"))

        rows, total = await EffectLedgerRepository(async_session).list_for_user(
            user.id, limit=10, offset=0
        )

        assert total == 1
        assert all(row.user_id == user.id for row in rows)


class TestTheJournalFilterIsServerSide:
    """The count must follow the filter, or it describes a set nobody sees."""

    async def test_the_total_counts_only_the_filtered_rows(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = EffectLedgerRepository(async_session)
        for index in range(3):
            await _claim(async_session, _request(user, f"ok-{index}"))
        failing = _request(user, "ko-1")
        outcome = await repository.claim(failing)
        await async_session.flush()
        assert outcome.claim_token is not None
        await repository.close_failure(
            outcome.effect.id, outcome.claim_token, error_code="provider_refused"
        )
        await async_session.flush()

        _all_rows, all_total = await repository.list_for_user(user.id, limit=50, offset=0)
        failed_rows, failed_total = await repository.list_for_user(
            user.id, limit=50, offset=0, status=EffectStatus.FAILED
        )

        assert all_total == 4
        assert failed_total == 1, "the count must describe the filtered set"
        assert [row.status for row in failed_rows] == [EffectStatus.FAILED]

    async def test_a_filter_matching_nothing_counts_zero(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _claim(async_session, _request(user, "only-claimed"))

        rows, total = await EffectLedgerRepository(async_session).list_for_user(
            user.id, limit=50, offset=0, status=EffectStatus.SUCCEEDED
        )

        assert rows == []
        assert total == 0


class TestTheExportFilters:
    async def test_each_filter_narrows_the_set(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _claim(async_session, _request(user, "f1", tool_name="control_hue_light_tool"))
        await _claim(
            async_session,
            _request(user, "f2", tool_name="generate_image", mutation_policy="artefact"),
        )
        repository = EffectLedgerRepository(async_session)

        everything = await repository.list_for_export(limit=100)
        by_tool = await repository.list_for_export(tool_name="generate_image", limit=100)
        by_policy = await repository.list_for_export(mutation_policy="artefact", limit=100)

        assert len(everything) >= 2
        assert [row.tool_name for row in by_tool] == ["generate_image"]
        assert [row.mutation_policy for row in by_policy] == ["artefact"]

    async def test_the_period_bounds_apply(self, async_session: AsyncSession, user: User) -> None:
        await _claim(async_session, _request(user, "p1"))
        repository = EffectLedgerRepository(async_session)
        future = datetime.now(UTC) + timedelta(hours=1)

        assert await repository.list_for_export(since=future, limit=100) == []
        assert await repository.list_for_export(until=future, limit=100) != []

    async def test_the_cap_applies(self, async_session: AsyncSession, user: User) -> None:
        for index in range(4):
            await _claim(async_session, _request(user, f"cap-{index}"))

        rows = await EffectLedgerRepository(async_session).list_for_export(limit=2)

        assert len(rows) == 2


class TestTheOrphanCount:
    async def test_a_fresh_claim_is_not_an_orphan(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _claim(async_session, _request(user, "fresh"))
        threshold = datetime.now(UTC) - timedelta(minutes=15)

        assert await EffectLedgerRepository(async_session).count_claimed_orphans(threshold) == 0

    async def test_a_stale_claim_is_counted(self, async_session: AsyncSession, user: User) -> None:
        await _claim(async_session, _request(user, "stale"))
        threshold = datetime.now(UTC) + timedelta(minutes=1)

        assert await EffectLedgerRepository(async_session).count_claimed_orphans(threshold) == 1

    async def test_a_closed_effect_is_never_an_orphan(
        self, async_session: AsyncSession, user: User
    ) -> None:
        request = _request(user, "closed")
        outcome = await EffectLedgerRepository(async_session).claim(request)
        await async_session.flush()
        assert outcome.claim_token is not None
        await EffectLedgerRepository(async_session).close_success(
            outcome.effect.id, outcome.claim_token, provider_ref=None, result_payload={"ok": True}
        )
        await async_session.flush()
        threshold = datetime.now(UTC) + timedelta(minutes=1)

        assert await EffectLedgerRepository(async_session).count_claimed_orphans(threshold) == 0


class TestTheLabelSurvivesTheRoundTrip:
    async def test_it_rests_encrypted_and_reads_as_a_sentence(
        self, async_session: AsyncSession, user: User
    ) -> None:
        label = {
            "i18n_key": "effects.labels.control_hue_light_tool",
            "values": {"target": "Salon"},
        }
        effect_id = await _claim(async_session, _request(user, "labelled", label=label))
        rows = await EffectLedgerRepository(async_session).list_for_run("run-reads")
        stored = next(row for row in rows if row.id == effect_id)

        assert stored.label is not None
        assert "Salon" not in stored.label, "the label must rest encrypted"

        decrypted = EffectLedgerRepository.decrypted_label(stored)
        assert decrypted == label

        from src.core.i18n_effects import render_effect_label

        assert "Salon" in render_effect_label(decrypted, "fr")
        assert render_effect_label(decrypted, "de") != render_effect_label(decrypted, "fr")

    async def test_a_row_with_no_label_reads_as_nothing(
        self, async_session: AsyncSession, user: User
    ) -> None:
        effect_id = await _claim(async_session, _request(user, "unlabelled"))
        rows = await EffectLedgerRepository(async_session).list_for_run("run-reads")
        stored = next(row for row in rows if row.id == effect_id)

        assert EffectLedgerRepository.decrypted_label(stored) is None


class TestTheTurnSummaryReportsOnlyWhatHappened:
    async def test_a_refused_effect_is_absent_from_the_summary(
        self, async_session: AsyncSession, user: User
    ) -> None:
        from src.domains.agents.effects.turn_summary import REPORTED_STATUSES

        await EffectLedgerRepository(async_session).refuse(
            _request(user, "refused", run_id="run-refused"), error_code="confirmation_missing"
        )
        await async_session.flush()

        rows = await EffectLedgerRepository(async_session).list_for_run("run-refused")

        assert [row.status for row in rows] == [EffectStatus.REFUSED]
        assert EffectStatus.REFUSED not in REPORTED_STATUSES
