"""The origin filter, against a real PostgreSQL (ADR-270).

A unit test can assert that the repository received a `RegisterOrigin`. Only the
database can say that the `source IN (...)` clause actually selects, that the
new ``proactive`` value round-trips through a column SQLAlchemy declares as an
enum without a check constraint, and — the property the whole tab rests on —
that the EXACT total is computed under the same filter as the page.

That last one is ADR-185's trap in its most direct form: a total counted over
everything, printed above a filtered list, describes a set the reader cannot
see. Both registers are checked, because a rule split in two is a rule that
will drift.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.models import EffectSource
from src.domains.agents.effects.origin import RegisterOrigin
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.agents.effects.treatment_repository import TreatmentRepository
from src.domains.agents.effects.treatments import Treatment
from src.domains.users.models import User

pytestmark = pytest.mark.integration


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    row = User(
        email=f"origin-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Origin Reader",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _claim_request(user: User, key: str, source: str) -> ClaimRequest:
    return ClaimRequest(  # type: ignore[arg-type]
        user_id=user.id,
        thread_id="thread-origin",
        run_id=f"run-{key}",
        source=source,
        execution_mode="pipeline",
        tool_name="control_hue_light_tool",
        mutation_policy="reversible",
        idempotency_key=key,
        args_digest="a" * 64,
    )


def _treatment(user: User, source: str, capability: str) -> Treatment:
    return Treatment(
        user_id=str(user.id),
        thread_id="thread-origin",
        run_id=f"run-{capability}",
        source=source,
        execution_mode="pipeline",
        tool_name=capability,
        mutation_policy=None,
        outcome="ok",
        duration_ms=3,
        occurred_at=datetime.now(UTC),
    )


class TestTheActionRegisterSplitsByAuthorship:
    async def test_the_initiative_reading_returns_only_lia_s_own(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = EffectLedgerRepository(async_session)
        for key, source in (
            ("typed", EffectSource.USER.value),
            ("routine", EffectSource.SCHEDULED.value),
            ("sweep", EffectSource.PROACTIVE.value),
        ):
            await repository.claim(_claim_request(user, key, source))
        await async_session.flush()

        rows, total = await repository.list_for_user(
            user.id, limit=50, offset=0, origin=RegisterOrigin.INITIATIVE
        )

        assert total == 1
        assert [row.source for row in rows] == [EffectSource.PROACTIVE]

    async def test_a_routine_stays_in_the_person_s_own_reading(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The non-regression the tab change turns on.

        A routine is the person's own instruction, deferred. Its rows must not
        move into a tab their owner never opened.
        """
        repository = EffectLedgerRepository(async_session)
        for key, source in (
            ("typed2", EffectSource.USER.value),
            ("routine2", EffectSource.SCHEDULED.value),
            ("sweep2", EffectSource.PROACTIVE.value),
        ):
            await repository.claim(_claim_request(user, key, source))
        await async_session.flush()

        rows, total = await repository.list_for_user(
            user.id, limit=50, offset=0, origin=RegisterOrigin.MINE
        )

        assert total == 2
        assert {row.source for row in rows} == {EffectSource.USER, EffectSource.SCHEDULED}

    async def test_the_total_is_counted_under_the_same_filter_as_the_page(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """ADR-185, in its most direct form.

        The page is capped at one row while three exist; the total must still
        describe the FILTERED set, never the whole register.
        """
        repository = EffectLedgerRepository(async_session)
        for index in range(3):
            await repository.claim(
                _claim_request(user, f"sweep-{index}", EffectSource.PROACTIVE.value)
            )
        await repository.claim(_claim_request(user, "typed3", EffectSource.USER.value))
        await async_session.flush()

        rows, total = await repository.list_for_user(
            user.id, limit=1, offset=0, origin=RegisterOrigin.INITIATIVE
        )

        assert len(rows) == 1
        assert total == 3


class TestTheConsultationRegisterSplitsTheSameWay:
    async def test_the_two_readings_partition_the_rows(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = TreatmentRepository(async_session)
        await repository.record_batch(
            [
                _treatment(user, EffectSource.USER.value, "briefing:mails"),
                _treatment(user, EffectSource.SCHEDULED.value, "get_events_tool"),
                _treatment(user, EffectSource.PROACTIVE.value, "get_tasks_tool"),
            ]
        )
        await async_session.flush()

        mine, mine_total = await repository.list_for_user(
            user.id, limit=50, offset=0, origin=RegisterOrigin.MINE
        )
        initiative, initiative_total = await repository.list_for_user(
            user.id, limit=50, offset=0, origin=RegisterOrigin.INITIATIVE
        )
        every, every_total = await repository.list_for_user(
            user.id, limit=50, offset=0, origin=RegisterOrigin.ALL
        )

        assert mine_total == 2
        assert initiative_total == 1
        assert every_total == 3
        assert mine_total + initiative_total == every_total, "a row belongs to neither tab"
        assert {row.tool_name for row in initiative} == {"get_tasks_tool"}
        assert len(every) == 3
        assert len(mine) == 2

    async def test_the_new_authorship_round_trips_through_the_column(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The value, not the member name, and no check constraint refused it.

        Measured on production 2026-09-07: these columns carry NO check
        constraint (``Enum(native_enum=False)`` leaves ``create_constraint``
        at False), so nothing but this test stands between the vocabulary and
        the data.
        """
        repository = TreatmentRepository(async_session)
        await repository.record_batch(
            [_treatment(user, EffectSource.PROACTIVE.value, "briefing:agenda")]
        )
        await async_session.flush()

        rows, _total = await repository.list_for_user(
            user.id, limit=10, offset=0, origin=RegisterOrigin.INITIATIVE
        )

        assert rows, "the proactive row did not come back"
        stored = rows[0].source
        assert getattr(stored, "value", stored) == "proactive"
