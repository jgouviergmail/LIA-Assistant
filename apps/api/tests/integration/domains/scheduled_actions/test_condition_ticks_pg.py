"""Every condition trigger, over successive checks, on a real PostgreSQL (ADR-322).

The unit tests prove each evaluator's facts and each executor exit against
doubles. What none of them executes is the LEDGER's life in the table: the
``condition_state`` JSONB written by one check and read back by the next, the
re-arm stored on the row, the run history the daily cap counts. A key lost in
that round trip is a trigger that fires twice, or never again — silently.

Each of the five condition types goes through the same five checks, the
executor's own gate and repository against the real schema, only the SOURCE
replaced (the provider is not what is under test):

1. a first fact fires and is served by a run that answered;
2. the same fact seen again fires nothing, re-arms, and writes no run row;
3. a second fact fires on ITSELF alone;
4. a run that failed leaves it new, so the next check fires it again;
5. a source that cannot be read is said on the ledger, forgetting nothing.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.time_utils import now_utc
from src.domains.briefing.exceptions import ConnectorAccessError
from src.domains.briefing.schemas import (
    AgendaData,
    AgendaEventItem,
    DocumentItem,
    DocumentsData,
    ForecastAlert,
    ForecastAlertKind,
    MailItem,
    MailsData,
    TaskItem,
    TasksData,
)
from src.domains.scheduled_actions.models import ScheduledActionRun, ScheduledRunOutcome
from src.domains.scheduled_actions.repository import ScheduledActionRepository
from src.domains.scheduled_actions.runs import record_run
from src.domains.scheduled_actions.schemas import ConditionConfig, ScheduledActionCreate
from src.domains.scheduled_actions.service import ScheduledActionService
from src.domains.users.models import User
from src.infrastructure.scheduler.scheduled_action_executor import _condition_gate, _next_trigger

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

_EVALUATORS = "src.infrastructure.scheduler.condition_evaluators"
_FETCHERS = "src.domains.briefing.fetchers"


@dataclass(frozen=True)
class _Trigger:
    """One condition type: its stored config, its fetcher, and two source states."""

    config: ConditionConfig
    fetcher: str
    first: Callable[[], Any]
    """The source holding fact A."""
    second: Callable[[], Any]
    """The source holding fact B (with A, where the source lists several)."""
    old_label: str
    """What the note names for fact A."""
    new_label: str
    """What the note names for fact B."""


#: One instant for the whole module: a fact keyed on its start must see the
#: SAME start at every check, as a provider returns it.
ANCHOR = now_utc().replace(microsecond=0)


def _task(title: str, task_id: str) -> TaskItem:
    return TaskItem(
        title=title, due_date_iso="2026-09-01", days_until_due=-3, overdue=True, id=task_id
    )


def _mail(subject: str, mail_id: str) -> MailItem:
    return MailItem(
        sender_name="Alice", sender_email="alice@example.com", subject=subject,
        received_local="09:12", id=mail_id,
    )  # fmt: skip


def _event(title: str, event_id: str, in_hours: int) -> AgendaEventItem:
    return AgendaEventItem(
        title=title, start_local="14:00", end_local=None, location=None, id=event_id,
        start_at=ANCHOR + timedelta(hours=in_hours),
    )  # fmt: skip


def _alert(kind: ForecastAlertKind, in_hours: int) -> ForecastAlert:
    return ForecastAlert(
        kind=kind, time="14:00", starts_at=ANCHOR + timedelta(hours=in_hours),
        precipitation_percent=80,
    )  # fmt: skip


TRIGGERS: dict[str, _Trigger] = {
    "task_overdue": _Trigger(
        config=ConditionConfig(type="task_overdue"),
        fetcher="fetch_tasks",
        first=lambda: TasksData(items=[_task("Invoice", "t1")], overdue_count=1),
        second=lambda: TasksData(
            items=[_task("Invoice", "t1"), _task("Tax return", "t2")], overdue_count=2
        ),
        old_label="Invoice",
        new_label="Tax return",
    ),
    "mail_match": _Trigger(
        config=ConditionConfig(type="mail_match", query="quote"),
        fetcher="fetch_mails",
        first=lambda: MailsData(items=[_mail("Quote 1", "m1")], total_unread_today=1),
        second=lambda: MailsData(
            items=[_mail("Quote 1", "m1"), _mail("Quote 2", "m2")], total_unread_today=2
        ),
        old_label="Quote 1",
        new_label="Quote 2",
    ),
    "document_added": _Trigger(
        config=ConditionConfig(type="document_added"),
        fetcher="fetch_documents",
        first=lambda: DocumentsData(items=[DocumentItem(name="Plan", modified_local="x", id="d1")]),
        second=lambda: DocumentsData(
            items=[
                DocumentItem(name="Plan", modified_local="y", id="d1"),
                DocumentItem(name="Budget", modified_local="y", id="d2"),
            ]
        ),
        old_label="Plan",
        new_label="Budget",
    ),
    "calendar_event": _Trigger(
        config=ConditionConfig(type="calendar_event", within_hours=4),
        fetcher="fetch_agenda",
        first=lambda: AgendaData(events=[_event("Standup", "e1", 1)]),
        second=lambda: AgendaData(events=[_event("Standup", "e1", 1), _event("Review", "e2", 2)]),
        old_label="Standup",
        new_label="Review (14:00)",
    ),
    "weather_change": _Trigger(
        config=ConditionConfig(type="weather_change"),
        fetcher="fetch_forecast_alert",
        first=lambda: _alert(ForecastAlertKind.RAIN, 1),
        second=lambda: _alert(ForecastAlertKind.SNOW, 2),
        old_label="rain expected",
        new_label="snow expected around 14:00",
    ),
}


@asynccontextmanager
async def _nothing(*_args: Any, **_kwargs: Any) -> Any:
    yield None


@contextmanager
def _source(trigger: _Trigger, answer: Callable[[], Any] | Exception) -> Iterator[None]:
    """The source answers; the accounting and the register are the unit tests' concern.

    Both write through their OWN sessions on the application's engine, which
    this test's transaction cannot see or roll back.
    """
    fetch = (
        AsyncMock(side_effect=answer)
        if isinstance(answer, Exception)
        else AsyncMock(side_effect=lambda **_: answer())
    )
    with (
        patch(f"{_FETCHERS}.{trigger.fetcher}", fetch),
        patch(f"{_EVALUATORS}.out_of_turn_spend", MagicMock(side_effect=_nothing)),
        patch(f"{_EVALUATORS}.record_surface_consultations"),
    ):
        yield


async def _routine(session: AsyncSession, trigger: _Trigger) -> tuple[UUID, UUID]:
    user = User(
        email=f"ticks_{uuid4().hex}@example.com",
        hashed_password="x",
        is_active=True,
        timezone="Europe/Paris",
        language="fr",
    )
    session.add(user)
    await session.flush()
    action = await ScheduledActionService(session).create(
        UUID(str(user.id)),
        ScheduledActionCreate(
            title="Watch", action_prompt="tell me", trigger_kind="condition",
            condition_config=trigger.config,
        ),
        "Europe/Paris",
    )  # fmt: skip
    await session.commit()
    return UUID(str(user.id)), action.id


async def _check(
    session: AsyncSession, trigger: _Trigger, action_id: UUID, user_id: UUID, answer: Any
) -> Any:
    """One tick's gate, on the row as the table holds it."""
    repo = ScheduledActionRepository(session)
    action = await repo.get_by_id(action_id)
    assert action is not None
    await session.refresh(action)
    with _source(trigger, answer):
        return action, await _condition_gate(
            session, repo, action, user_id, started_at=now_utc(), due_at=action.next_trigger_at
        )


async def _serve(session: AsyncSession, action: Any, gate: Any, *, succeeded: bool) -> None:
    """What the executor writes once the run answered — or failed."""
    repo = ScheduledActionRepository(session)
    due_at = action.next_trigger_at
    if succeeded:
        await repo.mark_execution_success(
            action, _next_trigger(action, due_at), condition_state=gate.served_state
        )
    else:
        await repo.mark_execution_failure(
            action, "boom", _next_trigger(action, due_at), max_consecutive_failures=99,
            condition_state=gate.unserved_state,
        )  # fmt: skip
    await record_run(
        session, action, due_at=due_at, started_at=now_utc(),
        outcome=ScheduledRunOutcome.SUCCESS if succeeded else ScheduledRunOutcome.FAILURE,
        attempts=1, error=None if succeeded else "boom",
    )  # fmt: skip
    await session.commit()


async def _ledger(session: AsyncSession, action_id: UUID) -> dict[str, Any]:
    """The ledger as PostgreSQL stores it — no identity map in between."""
    row = (
        await session.execute(
            text("SELECT condition_state FROM scheduled_actions WHERE id = :id"), {"id": action_id}
        )
    ).one()
    return dict(row.condition_state or {})


async def _runs(session: AsyncSession, action_id: UUID) -> int:
    return int(
        (
            await session.execute(
                select(func.count())
                .select_from(ScheduledActionRun)
                .where(ScheduledActionRun.scheduled_action_id == action_id)
            )
        ).scalar_one()
    )


@pytest.mark.parametrize("condition_type", sorted(TRIGGERS))
async def test_a_trigger_fires_once_per_fact_across_checks(
    async_session: AsyncSession, condition_type: str
) -> None:
    trigger = TRIGGERS[condition_type]
    user_id, action_id = await _routine(async_session, trigger)

    # 1. The first fact fires, and a run that answered serves it.
    action, gate = await _check(async_session, trigger, action_id, user_id, trigger.first)
    assert gate is not None
    await _serve(async_session, action, gate, succeeded=True)
    first = await _ledger(async_session, action_id)
    assert len(first["seen"]) == 1
    assert first["last_fired_at"] is not None
    assert await _runs(async_session, action_id) == 1

    # 2. Seen again: nothing fires, the routine is re-armed, no run row.
    action, gate = await _check(async_session, trigger, action_id, user_id, trigger.first)
    assert gate is None
    again = await _ledger(async_session, action_id)
    assert again["seen"] == first["seen"]
    assert again["last_fired_at"] == first["last_fired_at"]
    assert action.next_trigger_at is not None and action.next_trigger_at > now_utc()
    assert await _runs(async_session, action_id) == 1

    # 3. A second fact fires on itself alone — and the run fails.
    action, gate = await _check(async_session, trigger, action_id, user_id, trigger.second)
    assert gate is not None
    assert gate.note is not None
    assert trigger.new_label in gate.note
    assert trigger.old_label not in gate.note
    await _serve(async_session, action, gate, succeeded=False)
    assert (await _ledger(async_session, action_id))["seen"] == first["seen"]

    # 4. Unserved, it is still new at the next check.
    action, gate = await _check(async_session, trigger, action_id, user_id, trigger.second)
    assert gate is not None
    assert gate.note is not None
    assert trigger.new_label in gate.note
    await _serve(async_session, action, gate, succeeded=True)
    served = await _ledger(async_session, action_id)
    assert len(served["seen"]) == 2
    assert await _runs(async_session, action_id) == 3

    # 5. An unreadable source is said on the ledger and forgets nothing.
    down = ConnectorAccessError("source", "network", "down")
    action, gate = await _check(async_session, trigger, action_id, user_id, down)
    assert gate is None
    broken = await _ledger(async_session, action_id)
    assert broken["last_check_error"] == "unavailable"
    assert broken["seen"] == served["seen"]


async def test_a_network_failure_of_the_forecast_reads_as_unavailable(
    async_session: AsyncSession,
) -> None:
    # Not an exception the fetcher already classified: the raw transport error.
    trigger = TRIGGERS["weather_change"]
    user_id, action_id = await _routine(async_session, trigger)

    _action, gate = await _check(
        async_session, trigger, action_id, user_id, httpx.ConnectError("down")
    )

    assert gate is None
    assert (await _ledger(async_session, action_id))["last_check_error"] == "unavailable"
