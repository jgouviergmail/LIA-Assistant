"""The person's attention, read on real rows: every hold is named, and an unanswered
opening holds the next one back for a while, never for its whole reply window."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.conversations.models import ConversationMessage
from src.domains.conversations.repository import ConversationRepository
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.proactive_discussions.models import DiscussionOpeningRecord
from src.domains.proactive_discussions.publication_types import OpeningDraft
from src.domains.proactive_discussions.repository import DiscussionRepository
from src.domains.proactive_discussions.schemas import EngageDecision
from src.domains.proactive_discussions.write_schemas import DiscussionPolicyPatch
from src.domains.reminders.models import Reminder
from src.infrastructure.proactive import discussion_attention
from src.infrastructure.proactive.discussion_attention import attention_hold, unanswered_opening
from src.infrastructure.proactive.discussion_persistence import publication_repository

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 20, 10, tzinfo=UTC)


@pytest.fixture
def quiet_turns(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No turn streams and no approval waits: Redis is the external level read last."""

    class NoApproval:
        def __init__(self, redis_client: object, ttl_seconds: int) -> None:
            self.redis = redis_client

        async def has_interrupt(self, thread_id: str) -> bool:
            return False

    monkeypatch.setattr(discussion_attention, "get_redis_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(discussion_attention, "get_active_run", AsyncMock(return_value=None))
    monkeypatch.setattr(discussion_attention, "HITLStore", NoApproval)
    yield


async def _alert(async_engine: AsyncEngine, owner: UUID, *, at: datetime) -> None:
    async with AsyncSession(async_engine) as db:
        db.add(
            HeartbeatNotification(
                user_id=owner,
                run_id="fictional-heartbeat-run",
                content="A fictional proactive notification",
                content_hash="0" * 64,
                sources_used="calendar",
                created_at=at,
            )
        )
        await db.commit()


async def _publish(
    async_engine: AsyncEngine, owner: UUID, *, at: datetime, pending_seconds: int | None = None
) -> UUID:
    """A real opening, published at ``at`` through the publication path."""
    async with AsyncSession(async_engine) as db:
        await ConversationRepository(db).create_with_audit(owner, "Fictional conversation")
        repository = DiscussionRepository(db)
        await repository.update_policy(
            owner, DiscussionPolicyPatch(enabled=True), expected_revision=0
        )
        claim = await repository.claim_run(owner, now=at, lease_seconds=60)
        await db.commit()
    assert claim is not None
    async with AsyncSession(async_engine) as db:
        receipt = await publication_repository(db).commit_opening(
            claim,
            OpeningDraft(
                decision=EngageDecision(
                    action="engage", topic="project", reason="follow-up", references=("event:1",)
                ),
                text="How did your project go?",
                fingerprint="event:1:v2",
            ),
            now=at,
            pending_seconds=pending_seconds,
        )
        await db.commit()
    return receipt.opening_id


async def _write(
    async_engine: AsyncEngine, owner: UUID, *, at: datetime, automated: bool = False
) -> None:
    """A message of the person (or of a routine run in their name) in their conversation."""
    async with AsyncSession(async_engine) as db:
        conversation = await ConversationRepository(db).get_active_for_user(owner)
        if conversation is None:
            conversation = await ConversationRepository(db).create_with_audit(
                owner, "Fictional conversation"
            )
        db.add(
            ConversationMessage(
                conversation_id=conversation.id,
                role="user",
                content="A fictional message",
                message_metadata={FIELD_IS_AUTOMATED_SOURCE: True} if automated else {},
                created_at=at,
            )
        )
        await db.commit()


async def _hold(async_engine: AsyncEngine, owner: UUID, *, now: datetime) -> str | None:
    async with AsyncSession(async_engine) as db:
        return await attention_hold(db, owner, now=now)


async def test_a_recent_alert_no_longer_holds_an_opening_back_by_default(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    # Owner decision 2026-10-21: « no alert in the last 30 minutes » kept discussions
    # silent on every account LIA notifies often.
    now = datetime.now(UTC)
    await _alert(async_engine, discussion_owner, at=now - timedelta(minutes=1))
    assert await _hold(async_engine, discussion_owner, now=now) is None


async def test_an_operator_gap_makes_a_recent_alert_hold_it_back(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    gap = 30
    monkeypatch.setattr(settings, "discussion_attention_alert_gap_minutes", gap)
    now = datetime.now(UTC)
    await _alert(async_engine, discussion_owner, at=now - timedelta(minutes=gap - 1))
    assert await _hold(async_engine, discussion_owner, now=now) == "recent_alert"
    # Past the gap, the same alert no longer counts.
    assert await _hold(async_engine, discussion_owner, now=now + timedelta(minutes=gap)) is None


async def test_a_message_the_person_just_wrote_is_named(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    await _write(async_engine, discussion_owner, at=NOW - timedelta(minutes=1))
    assert await _hold(async_engine, discussion_owner, now=NOW) == "recent_turn"


async def test_a_reminder_about_to_ring_is_named(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    async with AsyncSession(async_engine) as db:
        db.add(
            Reminder(
                user_id=discussion_owner,
                content="A fictional reminder",
                original_message="Remind me of the fictional thing",
                recurrence={"freq": "once"},
                trigger_at=NOW + timedelta(seconds=30),
            )
        )
        await db.commit()
    assert await _hold(async_engine, discussion_owner, now=NOW) == "reminder_due"


async def test_an_unanswered_opening_holds_the_next_one_only_for_its_hold(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
    quiet_turns: None,
) -> None:
    # Owner decision 2026-10-23: an hour, no longer the opening's whole reply window
    # (24 h: « Dernier passage 11:22 » and nothing until the next morning).
    monkeypatch.setattr(settings, "discussion_attention_opening_gap_minutes", 0)
    hold = timedelta(minutes=settings.discussion_attention_unanswered_opening_minutes)
    await _publish(async_engine, discussion_owner, at=NOW)
    assert (
        await _hold(async_engine, discussion_owner, now=NOW + hold - timedelta(seconds=1))
        == "pending_opening"
    )
    assert await _hold(async_engine, discussion_owner, now=NOW + hold) is None


async def test_a_reply_frees_the_person_before_any_run_binds_it(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
    quiet_turns: None,
) -> None:
    monkeypatch.setattr(settings, "discussion_attention_opening_gap_minutes", 0)
    await _publish(async_engine, discussion_owner, at=NOW)
    replied = NOW + timedelta(minutes=1)
    await _write(async_engine, discussion_owner, at=replied)
    later = replied + timedelta(
        minutes=settings.discussion_attention_recent_turn_minutes, seconds=1
    )
    # Still inside the hold: only the reply can be what frees the person.
    assert later < NOW + timedelta(minutes=settings.discussion_attention_unanswered_opening_minutes)
    assert await _hold(async_engine, discussion_owner, now=later) is None
    async with AsyncSession(async_engine) as db:
        assert await unanswered_opening(db, discussion_owner, now=later) is None


async def test_a_routine_message_is_no_reply(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    await _publish(async_engine, discussion_owner, at=NOW)
    await _write(async_engine, discussion_owner, at=NOW + timedelta(minutes=1), automated=True)
    assert (
        await _hold(async_engine, discussion_owner, now=NOW + timedelta(minutes=2))
        == "pending_opening"
    )


async def test_an_answered_opening_holds_only_through_the_gap_between_openings(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    gap = 30
    monkeypatch.setattr(settings, "discussion_attention_opening_gap_minutes", gap)
    opening = await _publish(async_engine, discussion_owner, at=NOW)
    async with AsyncSession(async_engine) as db:
        await db.execute(
            update(DiscussionOpeningRecord)
            .where(DiscussionOpeningRecord.id == opening)
            .values(state="engaged")
        )
        await db.commit()
    assert (
        await _hold(async_engine, discussion_owner, now=NOW + timedelta(minutes=gap - 1))
        == "recent_opening"
    )


async def test_the_page_states_since_when_and_until_when_an_opening_holds(
    async_engine: AsyncEngine, discussion_owner: UUID
) -> None:
    hold = timedelta(minutes=settings.discussion_attention_unanswered_opening_minutes)
    await _publish(async_engine, discussion_owner, at=NOW)
    async with AsyncSession(async_engine) as db:
        held = await unanswered_opening(db, discussion_owner, now=NOW + timedelta(minutes=1))
    assert held is not None
    assert (held.since, held.until) == (NOW, NOW + hold)


async def test_an_opening_never_holds_past_its_own_reply_window(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "discussion_attention_unanswered_opening_minutes", 120)
    await _publish(async_engine, discussion_owner, at=NOW, pending_seconds=1800)
    async with AsyncSession(async_engine) as db:
        held = await unanswered_opening(db, discussion_owner, now=NOW + timedelta(minutes=1))
    assert held is not None and held.until == NOW + timedelta(seconds=1800)


async def test_no_hold_at_all_when_the_operator_sets_none(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "discussion_attention_unanswered_opening_minutes", 0)
    await _publish(async_engine, discussion_owner, at=NOW)
    async with AsyncSession(async_engine) as db:
        assert (
            await unanswered_opening(db, discussion_owner, now=NOW + timedelta(minutes=1)) is None
        )


async def _conversation(async_engine: AsyncEngine, owner: UUID) -> None:
    async with AsyncSession(async_engine) as db:
        await ConversationRepository(db).create_with_audit(owner, "Fictional conversation")
        await db.commit()


def _approval(waiting: bool) -> type:
    class Approval:
        def __init__(self, redis_client: object, ttl_seconds: int) -> None:
            self.redis = redis_client

        async def has_interrupt(self, thread_id: str) -> bool:
            return waiting

    return Approval


async def test_a_turn_streaming_in_the_conversation_is_named_unless_it_is_the_runs_own(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _conversation(async_engine, discussion_owner)
    monkeypatch.setattr(discussion_attention, "get_redis_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(
        discussion_attention, "get_active_run", AsyncMock(return_value={"stream_id": "a-turn"})
    )
    monkeypatch.setattr(discussion_attention, "HITLStore", _approval(False))
    assert await _hold(async_engine, discussion_owner, now=NOW) == "turn_streaming"
    async with AsyncSession(async_engine) as db:
        assert await attention_hold(db, discussion_owner, now=NOW, lease_owner="a-turn") is None


async def test_an_approval_waiting_in_the_conversation_is_named(
    async_engine: AsyncEngine, discussion_owner: UUID, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _conversation(async_engine, discussion_owner)
    monkeypatch.setattr(discussion_attention, "get_redis_cache", AsyncMock(return_value=object()))
    monkeypatch.setattr(discussion_attention, "get_active_run", AsyncMock(return_value=None))
    monkeypatch.setattr(discussion_attention, "HITLStore", _approval(True))
    assert await _hold(async_engine, discussion_owner, now=NOW) == "approval_pending"
