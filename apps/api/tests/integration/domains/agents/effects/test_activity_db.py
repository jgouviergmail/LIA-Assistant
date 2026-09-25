"""The activity read against a real PostgreSQL (ADR-318).

Only the database can say that the four statements describe the SAME set: the
page, its exact total, the per-outcome breakdown and the per-domain count —
under one period and one authorship filter, with another account's rows in the
same tables. A total counted over everything and printed beside a filtered list
describes a set the reader cannot see (ADR-185).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.activity import read_activity
from src.domains.agents.effects.models import AgentEffect, EffectSource, EffectStatus
from src.domains.agents.effects.origin import RegisterOrigin
from src.domains.agents.effects.repository import EffectLedgerRepository
from src.domains.agents.effects.schemas import ClaimRequest
from src.domains.agents.effects.treatment_repository import TreatmentRepository
from src.domains.agents.effects.treatments import Treatment
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime.now(UTC)


async def _user(db: AsyncSession, name: str) -> User:
    row = User(
        email=f"activity-{name}-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name=f"Activity {name}",
    )
    db.add(row)
    await db.flush()
    return row


async def _action(
    db: AsyncSession, user: User, key: str, *, source: str, outcome: EffectStatus
) -> AgentEffect:
    repository = EffectLedgerRepository(db)
    claimed = await repository.claim(
        ClaimRequest(
            user_id=user.id,
            thread_id="thread-activity",
            run_id=f"run-{key}",
            source=source,
            execution_mode="pipeline",
            tool_name="control_hue_light_tool",
            mutation_policy="reversible",
            idempotency_key=f"{user.id}-{key}",
            args_digest="a" * 64,
        )
    )
    assert claimed.claim_token is not None
    if outcome is EffectStatus.SUCCEEDED:
        await repository.close_success(claimed.effect.id, claimed.claim_token)
    elif outcome is EffectStatus.FAILED:
        await repository.close_failure(claimed.effect.id, claimed.claim_token, error_code="E1")
    await db.flush()
    return claimed.effect


def _read(user: User, tool_name: str, *, source: str, when: datetime) -> Treatment:
    return Treatment(
        user_id=str(user.id),
        thread_id="thread-activity",
        run_id=f"run-{tool_name}",
        source=source,
        execution_mode="pipeline",
        tool_name=tool_name,
        mutation_policy=None,
        outcome="ok",
        duration_ms=4,
        occurred_at=when,
    )


@pytest.fixture
async def seeded(async_session: AsyncSession) -> tuple[User, User]:
    person, stranger = await _user(async_session, "person"), await _user(async_session, "other")
    await _action(
        async_session,
        person,
        "typed-ok",
        source=EffectSource.USER.value,
        outcome=EffectStatus.SUCCEEDED,
    )
    await _action(
        async_session,
        person,
        "typed-ko",
        source=EffectSource.USER.value,
        outcome=EffectStatus.FAILED,
    )
    await _action(
        async_session,
        person,
        "sweep",
        source=EffectSource.PROACTIVE.value,
        outcome=EffectStatus.SUCCEEDED,
    )
    old = await _action(
        async_session,
        person,
        "last-month",
        source=EffectSource.USER.value,
        outcome=EffectStatus.SUCCEEDED,
    )
    await async_session.execute(
        update(AgentEffect)
        .where(AgentEffect.id == old.id)
        .values(claimed_at=NOW - timedelta(days=40))
    )
    await _action(
        async_session,
        stranger,
        "theirs",
        source=EffectSource.USER.value,
        outcome=EffectStatus.SUCCEEDED,
    )
    user_source = EffectSource.USER.value
    await TreatmentRepository(async_session).record_batch(
        [
            _read(person, "get_emails_tool", source=user_source, when=NOW),
            _read(person, "get_emails_tool", source=user_source, when=NOW),
            _read(person, "get_current_weather_tool", source=user_source, when=NOW),
            _read(person, "get_events_tool", source=EffectSource.PROACTIVE.value, when=NOW),
            _read(person, "get_emails_tool", source=user_source, when=NOW - timedelta(days=40)),
            _read(stranger, "get_emails_tool", source=user_source, when=NOW),
        ]
    )
    await async_session.flush()
    return person, stranger


def _week() -> tuple[datetime, datetime]:
    return NOW - timedelta(days=7), NOW + timedelta(minutes=1)


class TestTheFourFiguresDescribeOneSet:
    async def test_the_period_and_the_account(
        self, async_session: AsyncSession, seeded: tuple[User, User]
    ) -> None:
        person, _stranger = seeded
        since, until = _week()

        report = await read_activity(
            async_session,
            person.id,
            since=since,
            until=until,
            origin=RegisterOrigin.ALL,
            status=None,
            limit=50,
        )

        assert report.actions_total == 3
        assert len(report.actions) == 3
        assert report.actions_by_status == {"succeeded": 2, "failed": 1}
        assert report.consultations_by_domain == {"email": 2, "event": 1, "weather": 1}
        assert report.consultations_total == 4

    async def test_the_page_is_capped_and_the_total_is_not(
        self, async_session: AsyncSession, seeded: tuple[User, User]
    ) -> None:
        person, _stranger = seeded
        since, until = _week()

        report = await read_activity(
            async_session,
            person.id,
            since=since,
            until=until,
            origin=RegisterOrigin.ALL,
            status=None,
            limit=1,
        )

        assert len(report.actions) == 1
        assert report.actions_total == 3

    async def test_the_status_narrows_the_list_never_the_breakdown(
        self, async_session: AsyncSession, seeded: tuple[User, User]
    ) -> None:
        person, _stranger = seeded
        since, until = _week()

        report = await read_activity(
            async_session,
            person.id,
            since=since,
            until=until,
            origin=RegisterOrigin.ALL,
            status=EffectStatus.FAILED,
            limit=50,
        )

        assert report.actions_total == 1
        assert [row.status for row in report.actions] == [EffectStatus.FAILED]
        assert report.actions_by_status == {"succeeded": 2, "failed": 1}

    async def test_the_authorship_filter_is_the_tabs_own(
        self, async_session: AsyncSession, seeded: tuple[User, User]
    ) -> None:
        person, _stranger = seeded
        since, until = _week()

        mine = await read_activity(
            async_session,
            person.id,
            since=since,
            until=until,
            origin=RegisterOrigin.MINE,
            status=None,
            limit=50,
        )
        initiative = await read_activity(
            async_session,
            person.id,
            since=since,
            until=until,
            origin=RegisterOrigin.INITIATIVE,
            status=None,
            limit=50,
        )

        assert (mine.actions_total, initiative.actions_total) == (2, 1)
        assert mine.consultations_by_domain == {"email": 2, "weather": 1}
        assert initiative.consultations_by_domain == {"event": 1}

    async def test_an_empty_period_is_zero_everywhere(
        self, async_session: AsyncSession, seeded: tuple[User, User]
    ) -> None:
        person, _stranger = seeded

        report = await read_activity(
            async_session,
            person.id,
            since=NOW - timedelta(days=400),
            until=NOW - timedelta(days=300),
            origin=RegisterOrigin.ALL,
            status=None,
            limit=50,
        )

        assert (report.actions_total, report.actions, report.actions_by_status) == (0, [], {})
        assert report.consultations_total == 0
