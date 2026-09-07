"""An extraction of a register is COMPLETE, and chronological (ADR-273).

This file replaces ``test_export_window_db``, which held the previous rule: a
capped export keeps the END of the period, not its beginning. That rule was
paid for — measured on the developer instance on 2026-09-05, an export with no
period returned the first five weeks of an eight-month register and listed
eight models where the instance had since used forty-three — and it is now
unfalsifiable, because there is no ceiling left to keep the end of. A test that
cannot fail is worse than no test: it reads as coverage.

What replaced it is what stays falsifiable, and it is the property the owner
asked for: **every matching row comes back, in chronological order**, for all
five records, over a set larger than one cursor partition. The partition size
is what bounds memory now, so a read that silently stopped at one partition —
the obvious way to get this wrong — fails here.

These are integration tests on purpose. The property is about what SQL and the
cursor do together; a mock would only prove the code calls SQLAlchemy.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agents.effects.decision_repository import DecisionRepository
from src.domains.agents.effects.decisions import TurnDecision
from src.domains.agents.effects.integrity import IntegrityKind
from src.domains.agents.effects.integrity_repository import IntegrityRepository
from src.domains.agents.effects.models import (
    AgentIntegrityEvent,
    AgentTreatment,
    EffectSource,
    TreatmentOutcome,
)
from src.domains.agents.effects.treatment_repository import TreatmentRepository
from src.domains.chat.models import TokenUsageLog
from src.domains.chat.repository import ChatRepository
from src.domains.users.models import User
from tests.integration.domains.agents.effects.streaming import collected

pytestmark = pytest.mark.integration

_START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)

#: More rows than one partition holds, so a read that stops at the first
#: partition — the obvious way to get a cursor wrong — is visible here.
_TOTAL = 12
_BATCH = 5


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account whose history spans more rows than one partition."""
    row = User(
        email=f"stream-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Stream Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _at(index: int) -> datetime:
    """One instant per row, a day apart, so an order is unambiguous."""
    return _START + timedelta(days=index)


def _runs(count: int = _TOTAL) -> list[str]:
    """The run ids, in the order a history reads."""
    return [f"run-{index:02d}" for index in range(count)]


async def _write_treatments(db: AsyncSession, user: User) -> None:
    for index in range(_TOTAL):
        db.add(
            AgentTreatment(
                user_id=user.id,
                thread_id="thread-A",
                run_id=f"run-{index:02d}",
                source=EffectSource.USER,
                execution_mode="pipeline",
                tool_name="get_emails_tool",
                mutation_policy="read",
                outcome=TreatmentOutcome.OK,
                duration_ms=1,
                occurred_at=_at(index),
            )
        )
    await db.flush()


class TestEveryRowComesBack:
    async def test_the_consultation_register_streams_whole(
        self, async_session: AsyncSession, user: User
    ) -> None:
        await _write_treatments(async_session, user)
        repository = TreatmentRepository(async_session)

        rows = await collected(
            repository.stream_for_export(
                TreatmentRepository.export_query(user_id=user.id), batch=_BATCH
            )
        )

        assert [row.run_id for row in rows] == _runs()

    async def test_the_decision_register_streams_whole(
        self, async_session: AsyncSession, user: User
    ) -> None:
        repository = DecisionRepository(async_session)
        for index in range(_TOTAL):
            await repository.record(
                TurnDecision(
                    run_id=f"run-{index:02d}",
                    user_id=user.id,
                    thread_id="thread-A",
                    execution_mode="pipeline",
                    started_at=_at(index),
                ),
                ended_at=_at(index) + timedelta(seconds=1),
            )
        await async_session.flush()

        rows = await collected(
            repository.stream_for_export(
                DecisionRepository.export_query(since=None, until=None, user_ids=[user.id]),
                batch=_BATCH,
            )
        )

        assert [row.run_id for row in rows] == _runs()

    async def test_the_inference_log_streams_whole(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The record the original defect was found on: the exported models
        were real, but they were the models of the first five weeks."""
        for index in range(_TOTAL):
            async_session.add(
                TokenUsageLog(
                    user_id=user.id,
                    run_id=f"run-{index:02d}",
                    node_name="response",
                    model_name=f"model-{index:02d}",
                    prompt_tokens=1,
                    completion_tokens=1,
                    cached_tokens=0,
                    created_at=_at(index),
                )
            )
        await async_session.flush()
        repository = ChatRepository(async_session)

        rows = await collected(
            repository.stream_inference_for_export(
                ChatRepository.inference_export_query(since=None, until=None, user_ids=[user.id]),
                batch=_BATCH,
            )
        )

        assert [row.model_name for row in rows] == [
            f"model-{index:02d}" for index in range(_TOTAL)
        ], "the export served part of the period"

    async def test_the_integrity_register_streams_whole(
        self, async_session: AsyncSession, user: User
    ) -> None:
        from sqlalchemy import update as sql_update

        repository = IntegrityRepository(async_session)
        for index in range(_TOTAL):
            await repository.record(
                kind=IntegrityKind.EFFECT_UNRECORDED,
                user_id=user.id,
                run_id=f"run-{index:02d}",
                detail=f"detail-{index:02d}",
            )
            await async_session.flush()
            await async_session.execute(
                sql_update(AgentIntegrityEvent)
                .where(AgentIntegrityEvent.run_id == f"run-{index:02d}")
                .values(occurred_at=_at(index))
            )
        await async_session.flush()

        rows = await collected(
            repository.stream_for_export(
                IntegrityRepository.export_query(since=None, until=None, user_ids=[user.id]),
                batch=_BATCH,
            )
        )

        assert [row.run_id for row in rows] == _runs()


class TestTheReadingStaysCHRONOLOGICAL:
    async def test_the_stream_is_oldest_first(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A history reads forward, whatever the partition boundaries fall on."""
        await _write_treatments(async_session, user)

        rows = await collected(
            TreatmentRepository(async_session).stream_for_export(
                TreatmentRepository.export_query(user_id=user.id), batch=_BATCH
            )
        )

        assert [row.occurred_at for row in rows] == sorted(row.occurred_at for row in rows)

    async def test_a_batch_of_one_reads_the_same_history(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The partition size bounds memory; it must not decide the answer."""
        await _write_treatments(async_session, user)
        repository = TreatmentRepository(async_session)

        one_at_a_time = await collected(
            repository.stream_for_export(TreatmentRepository.export_query(user_id=user.id), batch=1)
        )
        in_bulk = await collected(
            repository.stream_for_export(
                TreatmentRepository.export_query(user_id=user.id), batch=1000
            )
        )

        assert [row.run_id for row in one_at_a_time] == _runs()
        assert [row.run_id for row in in_bulk] == _runs()


class TestTheCountAndTheStreamAgree:
    async def test_the_exact_total_matches_what_the_stream_produced(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The header publishes the count and the body carries the rows.

        They come from one statement on purpose: a file whose first line
        disagrees with its own contents is worse than one that says it stopped.
        """
        from src.infrastructure.database.export_stream import count_all

        await _write_treatments(async_session, user)
        query = TreatmentRepository.export_query(user_id=user.id)

        total = await count_all(async_session, query)
        rows = await collected(
            TreatmentRepository(async_session).stream_for_export(query, batch=_BATCH)
        )

        assert total == len(rows) == _TOTAL

    async def test_a_period_narrows_both_the_same_way(
        self, async_session: AsyncSession, user: User
    ) -> None:
        from src.infrastructure.database.export_stream import count_all

        await _write_treatments(async_session, user)
        query = TreatmentRepository.export_query(user_id=user.id, since=_at(2), until=_at(5))

        total = await count_all(async_session, query)
        rows = await collected(
            TreatmentRepository(async_session).stream_for_export(query, batch=_BATCH)
        )

        assert total == 3
        assert [row.run_id for row in rows] == ["run-02", "run-03", "run-04"]
