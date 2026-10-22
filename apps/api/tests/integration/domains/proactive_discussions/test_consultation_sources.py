"""Native source reads, including empty archives, are observable without text leaks."""

from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.domains.agents.effects.treatments import treatment_collector
from src.domains.habits.discussion_source import HabitDiscussionSource
from src.domains.health_metrics.discussion_source import HealthDiscussionSource
from src.domains.interests.discussion_source import InterestDiscussionSource
from src.domains.journals.discussion_source import JournalDiscussionSource, PortraitDiscussionSource
from src.domains.meetings.discussion_source import MeetingDiscussionSource
from src.domains.memories.discussion_source import MemoryDiscussionSource
from src.domains.open_loops.discussion_source import OpenLoopDiscussionSource
from src.domains.peers.discussion_source import PeerDiscussionSource, PeerMessageDiscussionSource
from src.domains.proactive_discussions.schemas import DiscussionPolicy
from src.domains.proactive_discussions.source_gateway import SourceGateway
from src.domains.relations.discussion_source import RelationDiscussionSource
from src.domains.reminders.discussion_source import ReminderDiscussionSource
from src.domains.scheduled_actions.discussion_source import ScheduledActionDiscussionSource
from src.domains.shared.discussion_sources import DiscussionSource, SourceKey
from src.domains.sms.discussion_source import SmsDiscussionSource
from src.domains.users.discussion_location import LocationDiscussionSource
from src.domains.users.models import User
from src.domains.workboard.discussion_source import WorkboardDiscussionSource
from src.infrastructure.proactive.conversation_source import ConversationDiscussionSource
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    read_request,
)

pytestmark = pytest.mark.integration

PORTS: dict[SourceKey, DiscussionSource] = {
    SourceKey.MEMORIES: MemoryDiscussionSource(),
    SourceKey.JOURNALS: JournalDiscussionSource(),
    SourceKey.PORTRAIT: PortraitDiscussionSource(),
    SourceKey.SMS: SmsDiscussionSource(),
    SourceKey.HABITS: HabitDiscussionSource(),
    SourceKey.INTERESTS: InterestDiscussionSource(),
    SourceKey.OPEN_LOOPS: OpenLoopDiscussionSource(),
    SourceKey.REMINDERS: ReminderDiscussionSource(),
    SourceKey.MEETINGS: MeetingDiscussionSource(),
    SourceKey.HEALTH: HealthDiscussionSource(),
    SourceKey.CONVERSATIONS: ConversationDiscussionSource(),
    SourceKey.PEERS: PeerDiscussionSource(),
    SourceKey.PEER_MESSAGES: PeerMessageDiscussionSource(),
    SourceKey.RELATIONS: RelationDiscussionSource(),
    SourceKey.SCHEDULED_ACTIONS: ScheduledActionDiscussionSource(),
    SourceKey.WORKBOARD: WorkboardDiscussionSource(),
    SourceKey.LOCATION: LocationDiscussionSource(),
}


@pytest.mark.parametrize("source", list(PORTS))
async def test_native_empty_read_is_recorded_once(
    source: SourceKey,
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for flag in (
        "memory_extraction_enabled",
        "journals_enabled",
        "habits_enabled",
        "interest_extraction_enabled",
        "open_loops_enabled",
        "meetings_enabled",
        "health_metrics_enabled",
        "peers_enabled",
        "workboard_enabled",
    ):
        monkeypatch.setattr(settings, flag, True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.memory_enabled, user.journals_enabled, user.habits_enabled = True, True, True
        user.sms_preferences = {"assistant_enabled": True}
        user.health_metrics_agents_enabled = True
        await db.commit()

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(
            enabled=True, sources=(source,), revision=0, sensitive_topics=("health",)
        )

    with treatment_collector(run_id="native-discussion-read") as rows:
        request = read_request(discussion_owner, source)
        if source == SourceKey.RELATIONS:
            request = request.model_copy(
                update={
                    "request": request.request.model_copy(
                        update={"operation": "search", "query": "Fictional"}
                    )
                }
            )
        result = await SourceGateway(dict.fromkeys(SourceKey, PORTS[source]), policy).read(request)
    assert result.status == "empty"
    assert len(rows) == 1 and rows[0].tool_name == f"discussion:{source.value}"
    assert rows[0].outcome == "ok" and rows[0].source == "proactive"
    assert result.physical_calls == 0


async def test_global_refusal_records_no_source_read(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "memory_extraction_enabled", True)
    async with AsyncSession(async_engine) as db:
        user = await db.get(User, discussion_owner)
        assert user is not None
        user.memory_enabled = False
        await db.commit()

    async def policy(owner: UUID) -> DiscussionPolicy:
        return DiscussionPolicy(enabled=True, sources=(SourceKey.MEMORIES,), revision=0)

    with treatment_collector(run_id="native-discussion-refusal") as rows:
        result = await SourceGateway(
            dict.fromkeys(SourceKey, MemoryDiscussionSource()), policy
        ).read(read_request(discussion_owner, SourceKey.MEMORIES))
    assert result.status == "disabled" and rows == []
