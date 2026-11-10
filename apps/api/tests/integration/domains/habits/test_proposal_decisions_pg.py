"""Deciding a habit proposal on a real PostgreSQL (ADR-375, review focus 2 and 3).

Accepting CARRIES OUT the proposal inside the decision's transaction: a routine
created or moved, the notification hours changed or the notifications switched
off. When the act no longer matches what the person was shown — the routine cap
reached, the routine gone or changed, the hours changed — nothing is written:
the proposal stays open and the refusal names a stable reason the card
translates. « Later » puts it off, « never » is a tombstone, and only the
owner's OPEN proposal can be decided at all.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from src.core.config import settings
from src.core.exceptions import ResourceConflictError, ResourceNotFoundError
from src.core.recurrence import RecurrenceSpec
from src.domains.habits.models import (
    HabitKind,
    HabitProposal,
    ProposalKind,
    ProposalStatus,
    UserHabit,
)
from src.domains.habits.proposal_decisions import ProposalVerdict, decide_proposal
from src.domains.habits.proposal_repository import HabitProposalRepository
from src.domains.scheduled_actions.models import ScheduledAction
from src.domains.users.models import User

pytestmark = pytest.mark.integration

NOW = datetime(2026, 11, 8, 20, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _heartbeat_handlers_installed() -> None:
    """The boot installs heartbeat's two handlers; a test process has no boot."""
    from src.domains.heartbeat import proposal_handlers

    proposal_handlers.install()


DAILY_0715 = {
    "freq": "daily",
    "interval": 1,
    "anchor_date": "2026-09-01",
    "times": {"mode": "at", "at": [{"hour": 7, "minute": 15}]},
}


async def _user(db: AsyncSession, *, language: str = "fr") -> User:
    user = User(
        email=f"decide-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 60,
        is_active=True,
        is_verified=True,
        timezone="Europe/Paris",
        language=language,
        habits_enabled=True,
        heartbeat_enabled=True,
        heartbeat_notify_start_hour=9,
        heartbeat_notify_end_hour=21,
    )
    db.add(user)
    await db.flush()
    return user


async def _proposal(
    db: AsyncSession, user: User, kind: ProposalKind, key: str, payload: dict[str, Any]
) -> uuid.UUID:
    """Open a proposal and COMMIT the setup: a refused decision rolls back its own work only."""
    repo = HabitProposalRepository(db)
    assert await repo.open(user.id, kind.value, key, payload)
    [row] = [row for row in await repo.list_for_user(user.id) if row.key == key]
    proposal_id = row.id
    await db.commit()
    return proposal_id


def _automate(domain: str = "weather", **over: Any) -> dict[str, Any]:
    facts: dict[str, Any] = {
        "domain": domain,
        "cadence": "weekdays",
        "weekday": None,
        "hour": 7,
        "minute": 30,
        "distinct_days": 14,
        "active_days": 22,
        "part_of_day": "morning",
        "existing_routine": None,
    }
    return {**facts, **over}


async def _routines(db: AsyncSession, user_id: uuid.UUID) -> list[ScheduledAction]:
    result = await db.execute(
        select(ScheduledAction)
        .where(ScheduledAction.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    return list(result.scalars().all())


async def _status(db: AsyncSession, proposal_id: uuid.UUID) -> HabitProposal:
    row = await db.get(HabitProposal, proposal_id, populate_existing=True)
    assert row is not None
    return row


async def _need(db: AsyncSession, user_id: uuid.UUID) -> UserHabit:
    row = await db.scalar(
        select(UserHabit)
        .where(UserHabit.user_id == user_id, UserHabit.key == "weather")
        .execution_options(populate_existing=True)
    )
    assert row is not None
    return row


def _weather_need(user: User) -> UserHabit:
    return UserHabit(
        user_id=user.id,
        kind=HabitKind.RECURRING_REQUEST.value,
        key="weather",
        payload={"version": 2},
        last_observed_at=NOW,
    )


async def _routine(db: AsyncSession, user: User, title: str = "Matin") -> ScheduledAction:
    action = ScheduledAction(
        user_id=user.id,
        title=title,
        action_prompt="Fais le point",
        recurrence=DAILY_0715,
        user_timezone="Europe/Paris",
        next_trigger_at=NOW + timedelta(hours=11),
        is_enabled=True,
    )
    db.add(action)
    await db.flush()
    return action


async def _decide(
    db: AsyncSession, user_id: uuid.UUID, proposal_id: uuid.UUID, verdict: ProposalVerdict
) -> Any:
    owner = await db.get(User, user_id, populate_existing=True)
    assert owner is not None
    return await decide_proposal(db, owner, proposal_id, verdict, settings=settings, now=NOW)


def _shift(routine_id: str, *, from_hour: int = 7, from_minute: int = 15) -> dict[str, Any]:
    return {
        "routine_id": routine_id,
        "routine_title": "Matin",
        "from_hour": from_hour,
        "from_minute": from_minute,
        "hour": 9,
        "minute": 30,
        "manual_runs": 4,
        "manual_days": 4,
    }


def _window(start: int, end: int) -> dict[str, Any]:
    return {
        "start": start,
        "end": end,
        "new_start": start - 2,
        "new_end": end + 2,
        "outside_days": 9,
        "outside_share": 0.31,
    }


class TestAcceptingCarriesItOut:
    async def test_an_automation_creates_its_routine_in_the_persons_language(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session, language="en")
        user_id = user.id
        db_session.add(_weather_need(user))
        proposal_id = await _proposal(
            db_session, user, ProposalKind.AUTOMATE_NEED, "weather", _automate()
        )

        decision = await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)

        [routine] = await _routines(db_session, user_id)
        assert decision.routine_id == routine.id
        assert routine.title == "My weather"
        assert "weather" in routine.action_prompt.lower()
        spec = RecurrenceSpec.model_validate(routine.recurrence)
        assert (spec.freq, spec.byweekday) == ("weekly", (1, 2, 3, 4, 5))
        assert [(m.hour, m.minute) for m in spec.times.at] == [(7, 30)]
        assert routine.user_timezone == "Europe/Paris"
        proposal = await _status(db_session, proposal_id)
        assert proposal.status == ProposalStatus.ACCEPTED.value
        assert proposal.resurface_after == NOW + timedelta(
            days=settings.habits_proposal_resurface_days
        )
        assert (await _need(db_session, user_id)).positive_signals == 1

    @pytest.mark.parametrize(
        ("cadence", "weekday", "freq", "days"),
        [("daily", None, "daily", ()), ("weekly", 6, "weekly", (7,))],
    )
    async def test_the_routine_fires_on_the_days_the_need_is_asked(
        self,
        db_session: AsyncSession,
        cadence: str,
        weekday: int | None,
        freq: str,
        days: tuple[int, ...],
    ) -> None:
        user = await _user(db_session)
        user_id = user.id
        facts = _automate(cadence=cadence, weekday=weekday)
        proposal_id = await _proposal(
            db_session, user, ProposalKind.AUTOMATE_NEED, "weather", facts
        )

        await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)

        [routine] = await _routines(db_session, user_id)
        spec = RecurrenceSpec.model_validate(routine.recurrence)
        assert (spec.freq, spec.byweekday) == (freq, days)
        # A weekly need is served for the week ahead, a daily one for the day.
        assert ("semaine" in routine.action_prompt) is (cadence == "weekly")

    async def test_a_moved_routine_keeps_its_other_times(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        user_id = user.id
        routine = await _routine(db_session, user)
        routine_id = routine.id
        routine.recurrence = {
            **DAILY_0715,
            "times": {"mode": "at", "at": [{"hour": 7, "minute": 15}, {"hour": 18, "minute": 0}]},
        }
        proposal_id = await _proposal(
            db_session, user, ProposalKind.SHIFT_ROUTINE, str(routine_id), _shift(str(routine_id))
        )

        decision = await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)

        [moved] = await _routines(db_session, user_id)
        spec = RecurrenceSpec.model_validate(moved.recurrence)
        assert [(m.hour, m.minute) for m in spec.times.at] == [(9, 30), (18, 0)]
        assert decision.routine_id == routine_id

    async def test_the_notification_hours_are_extended(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        user_id = user.id
        proposal_id = await _proposal(
            db_session, user, ProposalKind.EXTEND_NOTIFICATION_WINDOW, "heartbeat", _window(9, 21)
        )

        await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)

        owner = await db_session.get(User, user_id, populate_existing=True)
        assert owner is not None
        assert (owner.heartbeat_notify_start_hour, owner.heartbeat_notify_end_hour) == (7, 23)
        assert (await _status(db_session, proposal_id)).status == ProposalStatus.ACCEPTED.value

    async def test_silent_notifications_are_switched_off(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        user_id = user.id
        proposal_id = await _proposal(
            db_session,
            user,
            ProposalKind.REVIEW_NOTIFICATIONS,
            "heartbeat",
            {"sent": 24, "window_days": 35},
        )

        await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)

        owner = await db_session.get(User, user_id, populate_existing=True)
        assert owner is not None and owner.heartbeat_enabled is False

    @pytest.mark.parametrize("kind", [ProposalKind.FIX_ROUTINE, ProposalKind.CONNECT_SOURCE])
    async def test_a_proposal_that_opens_a_screen_changes_nothing_else(
        self, db_session: AsyncSession, kind: ProposalKind
    ) -> None:
        user = await _user(db_session)
        user_id = user.id
        routine = await _routine(db_session, user)
        routine_id = routine.id
        facts: dict[str, Any] = (
            {
                "routine_id": str(routine_id),
                "routine_title": "Matin",
                "failures": 4,
                "disabled": False,
            }
            if kind is ProposalKind.FIX_ROUTINE
            else {"category": "email", "domain": "email", "days": 5}
        )
        proposal_id = await _proposal(db_session, user, kind, "k", facts)

        decision = await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)

        assert decision.routine_id == (routine_id if kind is ProposalKind.FIX_ROUTINE else None)
        [unchanged] = await _routines(db_session, user_id)
        assert unchanged.recurrence == DAILY_0715


class TestAnActThatNoLongerMatchesIsRefused:
    async def _refused(
        self, db_session: AsyncSession, user_id: uuid.UUID, proposal_id: uuid.UUID, reason: str
    ) -> None:
        with pytest.raises(ResourceConflictError) as refused:
            await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)
        assert refused.value.detail == {
            "error_code": "PROPOSAL_ACTION_REFUSED",
            "reason": reason,
        }
        assert (await _status(db_session, proposal_id)).status == ProposalStatus.OPEN.value

    async def test_a_full_account_keeps_the_proposal_open(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        user = await _user(db_session)
        user_id = user.id
        monkeypatch.setattr(
            "src.domains.scheduled_actions.service.SCHEDULED_ACTIONS_MAX_PER_USER", 0
        )
        db_session.add(_weather_need(user))
        proposal_id = await _proposal(
            db_session, user, ProposalKind.AUTOMATE_NEED, "weather", _automate()
        )

        await self._refused(db_session, user_id, proposal_id, "routine_limit")

        assert await _routines(db_session, user_id) == []
        assert (await _need(db_session, user_id)).positive_signals == 0

    async def test_a_routine_deleted_since_cannot_be_moved(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        user_id = user.id
        gone = str(uuid.uuid4())
        proposal_id = await _proposal(
            db_session, user, ProposalKind.SHIFT_ROUTINE, gone, _shift(gone)
        )
        await self._refused(db_session, user_id, proposal_id, "routine_gone")

    async def test_a_routine_whose_time_changed_since_is_not_moved(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session)
        user_id = user.id
        routine = await _routine(db_session, user)
        routine_id = routine.id
        proposal_id = await _proposal(
            db_session,
            user,
            ProposalKind.SHIFT_ROUTINE,
            str(routine_id),
            _shift(str(routine_id), from_hour=6, from_minute=0),
        )
        await self._refused(db_session, user_id, proposal_id, "routine_changed")
        [unchanged] = await _routines(db_session, user_id)
        assert unchanged.recurrence == DAILY_0715

    async def test_hours_changed_since_are_not_overwritten(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        user_id = user.id
        proposal_id = await _proposal(
            db_session, user, ProposalKind.EXTEND_NOTIFICATION_WINDOW, "heartbeat", _window(8, 21)
        )
        await self._refused(db_session, user_id, proposal_id, "settings_changed")
        owner = await db_session.get(User, user_id, populate_existing=True)
        assert owner is not None
        assert (owner.heartbeat_notify_start_hour, owner.heartbeat_notify_end_hour) == (9, 21)


class TestPuttingOffAndRefusing:
    async def test_later_reopens_after_the_snooze(self, db_session: AsyncSession) -> None:
        user = await _user(db_session)
        user_id = user.id
        proposal_id = await _proposal(
            db_session, user, ProposalKind.AUTOMATE_NEED, "weather", _automate()
        )

        decision = await _decide(db_session, user_id, proposal_id, ProposalVerdict.DISMISS)

        assert decision.proposal.status == ProposalStatus.DISMISSED.value
        assert decision.proposal.resurface_after == NOW + timedelta(
            days=settings.habits_proposal_snooze_days
        )
        assert await _routines(db_session, user_id) == []

    async def test_never_is_a_tombstone_and_a_signal_against_the_need(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session)
        user_id = user.id
        db_session.add(_weather_need(user))
        proposal_id = await _proposal(
            db_session, user, ProposalKind.AUTOMATE_NEED, "weather", _automate()
        )

        decision = await _decide(db_session, user_id, proposal_id, ProposalVerdict.REFUSE)

        assert decision.proposal.status == ProposalStatus.REFUSED.value
        assert decision.proposal.resurface_after is None
        need = await _need(db_session, user_id)
        assert (need.positive_signals, need.negative_signals) == (0, 1)


class TestOnlyTheOwnersOpenProposal:
    async def test_a_strangers_proposal_does_not_exist(self, db_session: AsyncSession) -> None:
        owner, stranger = await _user(db_session), await _user(db_session)
        owner_id, stranger_id = owner.id, stranger.id
        proposal_id = await _proposal(
            db_session, owner, ProposalKind.AUTOMATE_NEED, "weather", _automate()
        )
        with pytest.raises(ResourceNotFoundError):
            await _decide(db_session, stranger_id, proposal_id, ProposalVerdict.ACCEPT)
        assert await _routines(db_session, owner_id) == []
        assert (await _status(db_session, proposal_id)).status == ProposalStatus.OPEN.value

    async def test_a_decided_proposal_cannot_be_decided_again(
        self, db_session: AsyncSession
    ) -> None:
        user = await _user(db_session)
        user_id = user.id
        proposal_id = await _proposal(
            db_session, user, ProposalKind.AUTOMATE_NEED, "weather", _automate()
        )
        await _decide(db_session, user_id, proposal_id, ProposalVerdict.DISMISS)
        with pytest.raises(ResourceConflictError) as refused:
            await _decide(db_session, user_id, proposal_id, ProposalVerdict.ACCEPT)
        assert refused.value.detail == {"error_code": "PROPOSAL_NOT_OPEN"}
        assert await _routines(db_session, user_id) == []


async def test_two_clicks_at_once_create_one_routine(async_engine: AsyncEngine) -> None:
    """Review focus 2: the chat card and the inbox accept together — one routine."""
    maker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with maker() as db:
        user = await _user(db)
        user_id = user.id
        proposal_id = await _proposal(db, user, ProposalKind.AUTOMATE_NEED, "weather", _automate())

    async def accept() -> str:
        async with maker() as db:
            try:
                await _decide(db, user_id, proposal_id, ProposalVerdict.ACCEPT)
                return "accepted"
            except ResourceConflictError:
                return "conflict"

    try:
        outcomes = await asyncio.gather(accept(), accept())
        assert sorted(outcomes) == ["accepted", "conflict"]
        async with maker() as db:
            count = await db.scalar(
                select(func.count())
                .select_from(ScheduledAction)
                .where(ScheduledAction.user_id == user_id)
            )
            assert count == 1
    finally:
        async with maker() as db:
            await db.execute(delete(User).where(User.id == user_id))
            await db.commit()
