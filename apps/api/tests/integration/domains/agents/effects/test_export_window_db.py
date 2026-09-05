"""A capped export keeps the END of the period, not its beginning (ADR-263).

Found on the developer instance, 2026-09-05, and it is the kind of defect no
unit test would ever have shown: every export read ordered oldest-first and then
applied its ceiling, so an export with no period returned **the first rows ever
written**. On an eight-month register the exported window was 31 January to
5 March — five weeks — and it listed eight models where the instance had since
used forty-three. Nothing lied: the header said ``truncated``. It simply
answered a question nobody asked.

Five repositories had it, two of them from before this programme. The rule is
now one implementation (``export_window.newest_window``) and these tests hold
each caller to it against real rows, because the property is about what SQL
returns and a mock would only prove the code calls SQLAlchemy.
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

pytestmark = pytest.mark.integration

_START = datetime(2026, 1, 1, 9, 0, tzinfo=UTC)
_TOTAL = 12
_CAP = 4


@pytest.fixture
async def user(async_session: AsyncSession) -> User:
    """The account whose history spans more rows than any ceiling."""
    row = User(
        email=f"window-{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_active=True,
        is_superuser=False,
        full_name="Window Owner",
    )
    async_session.add(row)
    await async_session.flush()
    return row


def _at(index: int) -> datetime:
    """One instant per row, a day apart, so a window is unambiguous."""
    return _START + timedelta(days=index)


class TestTheWindowIsTheMostRECENT:
    async def test_the_consultation_register_keeps_the_END_of_history(
        self, async_session: AsyncSession, user: User
    ) -> None:
        for index in range(_TOTAL):
            async_session.add(
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
        await async_session.flush()

        rows = await TreatmentRepository(async_session).list_for_export(
            user_id=user.id, since=None, until=None, limit=_CAP
        )

        assert [row.run_id for row in rows] == ["run-08", "run-09", "run-10", "run-11"]

    async def test_the_decision_register_keeps_the_END_of_history(
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

        rows = await repository.list_for_export(
            since=None, until=None, user_ids=[user.id], limit=_CAP
        )

        assert [row.run_id for row in rows] == ["run-08", "run-09", "run-10", "run-11"]

    async def test_the_inference_log_keeps_the_END_of_history(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The one the defect was found on: the exported models were real, but
        they were the models of the first five weeks."""
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

        rows = await ChatRepository(async_session).list_inference_for_export(
            since=None, until=None, user_ids=[user.id], limit=_CAP
        )

        assert [row.model_name for row in rows] == [
            "model-08",
            "model-09",
            "model-10",
            "model-11",
        ], "the export served the models of the oldest period"

    async def test_the_integrity_register_keeps_the_END_of_history(
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

        rows = await repository.list_for_export(
            since=None, until=None, user_ids=[user.id], limit=_CAP
        )

        assert [row.run_id for row in rows] == ["run-08", "run-09", "run-10", "run-11"]


class TestTheReadingStaysCHRONOLOGICAL:
    async def test_the_window_is_returned_oldest_first(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """A history reads forward. Keeping the end of it must not reverse it."""
        for index in range(_TOTAL):
            async_session.add(
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
        await async_session.flush()

        rows = await TreatmentRepository(async_session).list_for_export(
            user_id=user.id, since=None, until=None, limit=_CAP
        )

        assert [row.occurred_at for row in rows] == sorted(row.occurred_at for row in rows)


class TestAPeriodStillDecidesWhatIsCovered:
    async def test_a_period_smaller_than_the_ceiling_is_returned_whole(
        self, async_session: AsyncSession, user: User
    ) -> None:
        """The ceiling only bites when the period holds more rows than it."""
        for index in range(_TOTAL):
            async_session.add(
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
        await async_session.flush()

        rows = await TreatmentRepository(async_session).list_for_export(
            user_id=user.id, since=_at(2), until=_at(5), limit=_CAP
        )

        assert [row.run_id for row in rows] == ["run-02", "run-03", "run-04"]

    async def test_a_period_LARGER_than_the_ceiling_keeps_its_end(
        self, async_session: AsyncSession, user: User
    ) -> None:
        for index in range(_TOTAL):
            async_session.add(
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
        await async_session.flush()

        rows = await TreatmentRepository(async_session).list_for_export(
            user_id=user.id, since=_at(0), until=_at(8), limit=_CAP
        )

        assert [row.run_id for row in rows] == ["run-04", "run-05", "run-06", "run-07"]
