"""Source identity follows consumed evidence, not exposure bookkeeping."""

from contextlib import asynccontextmanager
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.core.constants import RELATION_DEBRIEF_BODY_VERSION
from src.domains.habits import portrait_source as habits_source
from src.domains.habits.models import UserHabit
from src.domains.habits.repository import HabitsRepository
from src.domains.interests import portrait_source as interests_source
from src.domains.interests.models import UserInterest
from src.domains.interests.repository import InterestRepository
from src.domains.journals.source_state import portrait_source_state
from src.domains.relations.debrief import portrait_source as debrief_source
from src.domains.relations.debrief.models import DebriefState, RelationDebrief
from src.domains.shared import portrait_sources
from src.domains.users.models import User

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


def authorize_source(monkeypatch, db, source):
    @asynccontextmanager
    async def context():
        yield db

    allowed = AsyncMock(return_value=True)
    monkeypatch.setattr(source, "_allowed", allowed)
    monkeypatch.setattr(source, "get_db_context", context)
    monkeypatch.setattr(
        portrait_sources,
        "_REGISTRY",
        {
            source.KEY: (
                getattr(source, f"read_{source.KEY}"),
                replace(source.FRESHNESS, allowed=allowed),
            )
        },
    )


async def owner(db):
    user = User(email=f"source-semantics-{uuid4().hex}@example.test", hashed_password="x")
    db.add(user)
    await db.flush()
    return user


async def test_interest_notification_cooldown_does_not_change_evidence_identity(
    async_session, monkeypatch
):
    db = async_session
    user = await owner(db)
    authorize_source(monkeypatch, db, interests_source)
    interest = UserInterest(
        user_id=user.id,
        topic="Observing migratory birds",
        category="other",
        last_mentioned_at=datetime.now(UTC),
    )
    db.add(interest)
    await db.flush()
    before = await portrait_source_state(db, user)
    rendered_before = await interests_source.read_interests(user_id=user.id, language="en")
    previous_stamp = interest.updated_at
    await InterestRepository(db).mark_notified(interest)
    await db.flush()
    assert interest.updated_at != previous_stamp
    rendered_after = await interests_source.read_interests(user_id=user.id, language="en")
    assert rendered_before.text == rendered_after.text
    assert await portrait_source_state(db, user) == before


async def test_habit_profile_changed_without_mirror_row_changes_is_stale(
    async_session, monkeypatch
):
    db = async_session
    user = await owner(db)
    authorize_source(monkeypatch, db, habits_source)
    now = datetime.now(UTC)
    repo = HabitsRepository(db)
    await repo.upsert_profile(user.id, {"sparse": True, "active_days_fraction": 0.25}, now, None)
    before = await portrait_source_state(db, user)
    rendered_before = await habits_source.read_habits(user_id=user.id, language="en")
    assert rendered_before.used == 1
    assert await repo.list_habits(user.id) == []
    await repo.upsert_profile(
        user.id, {"sparse": True, "active_days_fraction": 0.5}, now + timedelta(seconds=1), None
    )
    user_id = user.id
    db.expire_all()
    # Scalar snapshot ownership survives expire_all without lazy IO.
    user = await db.get(User, user_id)
    rendered_after = await habits_source.read_habits(user_id=user.id, language="en")
    assert rendered_before.text != rendered_after.text
    assert await portrait_source_state(db, user) != before


async def test_identical_habit_profile_recompute_keeps_evidence_identity(
    async_session, monkeypatch
):
    db = async_session
    user = await owner(db)
    authorize_source(monkeypatch, db, habits_source)
    now = datetime.now(UTC)
    repo = HabitsRepository(db)
    payload = {"sparse": True, "active_days_fraction": 0.25}
    await repo.upsert_profile(user.id, payload, now, None)
    before = await portrait_source_state(db, user)
    await repo.upsert_profile(user.id, payload, now + timedelta(hours=1), now)
    assert await portrait_source_state(db, user) == before


async def test_habit_offer_bookkeeping_preserves_identity_but_consumed_intent_changes_it(
    async_session, monkeypatch
):
    db = async_session
    user = await owner(db)
    authorize_source(monkeypatch, db, habits_source)
    now = datetime.now(UTC)
    habit = UserHabit(
        user_id=user.id,
        kind="recurring_request",
        key="calendar",
        payload={"shape": "weekly", "usual_intent": "Prepare next week's calendar"},
        last_observed_at=now,
    )
    db.add(habit)
    await db.flush()
    before = await portrait_source_state(db, user)
    repo = HabitsRepository(db)
    await repo.touch_habit(habit, now + timedelta(hours=1))
    await repo.record_feedback(habit.id, user.id, positive=True)
    habit.payload = {**habit.payload, "last_offered_at": now.isoformat(), "ignored_offers": 1}
    await db.flush()
    assert await portrait_source_state(db, user) == before
    habit.payload = {**habit.payload, "usual_intent": "Review completed calendar events"}
    await db.flush()
    assert await portrait_source_state(db, user) != before


async def test_debrief_cost_and_lease_bookkeeping_preserve_identity_but_state_changes_it(
    async_session, monkeypatch
):
    db = async_session
    user = await owner(db)
    authorize_source(monkeypatch, db, debrief_source)
    now = datetime.now(UTC)
    debrief = RelationDebrief(
        user_id=user.id,
        name_key="alex",
        display_name="Alex",
        generated_for=now.date(),
        generated_at=now,
        language="en",
        scope_digest="a" * 64,
        state=DebriefState.READY,
        body={
            "version": RELATION_DEBRIEF_BODY_VERSION,
            "headline": "Plans remain tentative",
            "where_we_stand": "Alex suggested a meeting and the date has yet to be confirmed.",
        },
    )
    db.add(debrief)
    await db.flush()
    before = await portrait_source_state(db, user)
    debrief.usage = {"cost_eur": 0.02}
    debrief.claim_owner = uuid4()
    debrief.held_until = now + timedelta(hours=1)
    await db.flush()
    assert await portrait_source_state(db, user) == before
    debrief.state = DebriefState.BUILDING
    await db.flush()
    assert await portrait_source_state(db, user) != before
