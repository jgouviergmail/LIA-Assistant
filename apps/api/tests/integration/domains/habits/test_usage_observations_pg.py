"""Gathering one person's usage on a real PostgreSQL (ADR-375).

The rows are the ones LIA really writes: routines and their run history, the
treatments a linked run consulted, proactive notifications and their thumbs,
connectors, the activity rollup, an earlier refusal and a paused need. The
ports are the real readers ``agents`` and ``heartbeat`` install.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import settings
from src.domains.agents.effects import routine_reads
from src.domains.agents.effects.models import AgentTreatment, EffectSource, TreatmentOutcome
from src.domains.connectors.models import Connector, ConnectorStatus, ConnectorType
from src.domains.habits import usage_ports
from src.domains.habits.models import (
    HabitKind,
    HabitStatus,
    ProposalStatus,
    UserActivityDay,
    UserHabit,
)
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.habits.usage_observations import LedgerView, gather_usage_observations
from src.domains.heartbeat import feedback_summary
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.scheduled_actions.models import (
    ScheduledAction,
    ScheduledActionRun,
    ScheduledRunOutcome,
)
from src.domains.users.models import User

pytestmark = pytest.mark.integration

TODAY = date(2026, 11, 6)
DAILY_0745 = {
    "freq": "daily",
    "interval": 1,
    "anchor_date": "2026-09-01",
    "times": {"mode": "at", "at": [{"hour": 7, "minute": 45}]},
}


@pytest.fixture(autouse=True)
def _real_ports(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usage_ports, "_PORTS", usage_ports._Ports())
    usage_ports.install_routine_reads_reader(routine_reads.read_routine_run_domains)
    usage_ports.install_proactive_feedback_reader(feedback_summary.read_proactive_feedback)


async def _user(db: AsyncSession) -> User:
    user = User(
        email=f"usage-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        is_active=True,
        is_verified=True,
        timezone="Europe/Paris",
        heartbeat_enabled=True,
        heartbeat_notify_start_hour=8,
        heartbeat_notify_end_hour=22,
    )
    db.add(user)
    await db.flush()
    return user


async def _routine(db: AsyncSession, user_id: uuid.UUID, title: str) -> ScheduledAction:
    action = ScheduledAction(
        user_id=user_id,
        title=title,
        action_prompt="brief me",
        recurrence=DAILY_0745,
        user_timezone="Europe/Paris",
        next_trigger_at=datetime(2026, 11, 7, 6, 45, tzinfo=UTC),
        is_enabled=True,
    )
    db.add(action)
    await db.flush()
    return action


async def _run(
    db: AsyncSession,
    action: ScheduledAction,
    started: datetime,
    *,
    run_id: str | None,
    manual: bool = False,
) -> None:
    db.add(
        ScheduledActionRun(
            scheduled_action_id=action.id,
            user_id=action.user_id,
            slot_at=started,
            started_at=started,
            ended_at=started + timedelta(seconds=40),
            outcome=ScheduledRunOutcome.SUCCESS,
            attempts=1,
            manual=manual,
            run_id=run_id,
        )
    )


def _treatment(user_id: uuid.UUID, run_id: str, tool: str, at: datetime) -> AgentTreatment:
    return AgentTreatment(
        user_id=user_id,
        thread_id="thread-1",
        run_id=run_id,
        source=EffectSource.SCHEDULED,
        execution_mode="react",
        tool_name=tool,
        outcome=TreatmentOutcome.OK,
        duration_ms=120,
        occurred_at=at,
    )


async def test_one_night_of_observations_reads_every_source(db_session: AsyncSession) -> None:
    user = await _user(db_session)
    linked = await _routine(db_session, user.id, "Morning")
    unlinked = await _routine(db_session, user.id, "Old one")
    started = datetime(2026, 11, 5, 6, 45, tzinfo=UTC)
    await _run(db_session, linked, started, run_id="run-linked")
    await _run(
        db_session,
        linked,
        datetime(2026, 11, 4, 9, 40, tzinfo=UTC),
        run_id="run-manual",
        manual=True,
    )
    await _run(db_session, unlinked, started, run_id=None)
    db_session.add_all(
        [
            _treatment(user.id, "run-linked", "get_events_tool", started),
            _treatment(user.id, "run-linked", "get_emails_tool", started),
            # A chat turn of the same person is not the routine's reading.
            AgentTreatment(
                user_id=user.id,
                thread_id="t",
                run_id="chat-run",
                source=EffectSource.USER,
                execution_mode="react",
                tool_name="get_tasks_tool",
                outcome=TreatmentOutcome.OK,
                duration_ms=1,
                occurred_at=started,
            ),
            HeartbeatNotification(
                user_id=user.id,
                run_id=f"hb-{uuid.uuid4().hex}",
                content="x",
                content_hash="h1",
                sources_used="[]",
                created_at=datetime(2026, 11, 1, 9, tzinfo=UTC),
            ),
            HeartbeatNotification(
                user_id=user.id,
                run_id=f"hb-{uuid.uuid4().hex}",
                content="y",
                content_hash="h2",
                sources_used="[]",
                user_feedback="thumbs_up",
                created_at=datetime(2026, 11, 2, 9, tzinfo=UTC),
            ),
            # Older than the window: not counted.
            HeartbeatNotification(
                user_id=user.id,
                run_id=f"hb-{uuid.uuid4().hex}",
                content="z",
                content_hash="h3",
                sources_used="[]",
                created_at=datetime(2026, 9, 1, 9, tzinfo=UTC),
            ),
            Connector(
                user_id=user.id,
                connector_type=ConnectorType.GOOGLE_CALENDAR,
                status=ConnectorStatus.ACTIVE,
                scopes=[],
                credentials_encrypted="x",
            ),
            Connector(
                user_id=user.id,
                connector_type=ConnectorType.GOOGLE_GMAIL,
                status=ConnectorStatus.ERROR,
                scopes=[],
                credentials_encrypted="x",
            ),
            UserActivityDay(
                user_id=user.id, local_date=TODAY - timedelta(days=1), hour_counts={"9": 2, "23": 1}
            ),
            UserActivityDay(
                user_id=user.id, local_date=TODAY - timedelta(days=60), hour_counts={"9": 1}
            ),
            UserHabit(
                user_id=user.id,
                kind=HabitKind.RECURRING_REQUEST.value,
                key="email",
                payload={"version": 2},
                status=HabitStatus.PAUSED.value,
                last_observed_at=started,
            ),
        ]
    )
    await db_session.flush()
    proposals = HabitProposalRepository(db_session)
    await proposals.open(user.id, "automate_need", "task", {})
    (row,) = await proposals.list_for_user(user.id)
    await proposals.decide(row.id, user.id, ProposalStatus.REFUSED, None, now=started)

    ledger = LedgerView(
        readable=True,
        days_by_domain={"event": {TODAY - timedelta(days=k): [10.0] for k in (1, 3, 8, 10)}},
        intents={"event": "search"},
    )
    obs = await gather_usage_observations(
        db_session, user, ledger=ledger, today=TODAY, settings=settings
    )

    assert [need.domain for need in obs.needs] == ["event"]
    assert obs.needs[0].active_days == 4  # never fewer than the need's own days
    assert obs.need_status == {"email": "paused"}
    assert obs.asked_days == {"event": 4}
    views = {view.title: view for view in obs.routines}
    assert views["Morning"].read_domains == frozenset({"event", "email"})
    assert views["Morning"].times == (7.75,)
    assert views["Morning"].fixed_times is True  # its 07:45 is one listed moment
    assert [
        (run.manual, run.hour) for run in sorted(views["Morning"].runs, key=lambda r: r.day)
    ] == [(True, pytest.approx(10 + 40 / 60)), (False, pytest.approx(7.75))]
    assert views["Old one"].read_domains is None  # could serve, no run names its turn
    assert obs.presence == {TODAY - timedelta(days=1): frozenset({9, 23})}
    assert (obs.heartbeat_enabled, obs.heartbeat_window) == (True, (8, 22))
    assert (obs.proactive.sent, obs.proactive.reacted) == (2, 1)  # type: ignore[union-attr]
    assert obs.connector_categories == frozenset({"calendar"})
    assert obs.refusals == {"automate_need": 1}
    assert obs.ledger_readable is True


async def test_a_missing_port_is_an_unknown_never_a_zero(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(usage_ports, "_PORTS", usage_ports._Ports())
    user = await _user(db_session)
    action = await _routine(db_session, user.id, "Morning")
    await _run(db_session, action, datetime(2026, 11, 5, 6, 45, tzinfo=UTC), run_id="run-1")
    await db_session.flush()

    obs = await gather_usage_observations(
        db_session,
        user,
        ledger=LedgerView(readable=True, days_by_domain={}, intents={}),
        today=TODAY,
        settings=SimpleNamespace(**{**settings.model_dump(), "recurrence_window_days": 35}),
    )

    assert obs.routines[0].read_domains is None
    assert obs.proactive is None
