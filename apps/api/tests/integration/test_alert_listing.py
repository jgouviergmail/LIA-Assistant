"""The alerts hub reads complete filtered sets through each owning domain."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.heartbeat.models import HeartbeatNotification
from src.domains.heartbeat.repository import HeartbeatNotificationRepository
from src.domains.interests.history_queries import InterestHistoryRepository
from src.domains.interests.models import InterestNotification, UserInterest
from src.domains.peers.history_queries import PeerHistoryRepository
from src.domains.peers.models import PeerBlock, PeerConnection, PeerMessage, canonical_pair
from src.domains.proactive_discussions.models import DiscussionOpeningRecord, DiscussionRun
from src.domains.proactive_discussions.openings import list_display_openings
from src.domains.reminders.models import Reminder
from src.domains.reminders.repository import ReminderRepository
from src.domains.shared.display_query import DisplayQuery
from src.domains.users.models import User
from src.domains.workboard.models import WorkboardTicket
from src.domains.workboard.repository import WorkboardRepository

pytestmark = pytest.mark.integration
NOW = datetime(2026, 11, 1, tzinfo=UTC)


async def test_discussion_search_only_reads_visible_archived_words(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    conversation = Conversation(user_id=test_user.id)
    async_session.add(conversation)
    await async_session.flush()
    for index, (content, hidden) in enumerate(
        [("Zèbre", False), ("Alpha", False), ("Hidden", True)]
    ):
        run = DiscussionRun(
            user_id=test_user.id,
            fence=index,
            policy_revision=0,
            context_epoch=0,
            state="completed",
            claimed_at=NOW,
        )
        message = ConversationMessage(
            conversation_id=conversation.id, role="assistant", content=content, hidden=hidden
        )
        async_session.add_all([run, message])
        await async_session.flush()
        async_session.add(
            DiscussionOpeningRecord(
                user_id=test_user.id,
                run_id=run.id,
                message_id=message.id,
                conversation_id=conversation.id,
                topic="Private topic",
                fingerprint=str(uuid4()),
                content_digest="x",
                references=[],
                state="expired",
                policy_revision=0,
                context_epoch=0,
                expires_at=NOW,
                created_at=NOW + timedelta(seconds=index),
            )
        )
    await async_session.flush()
    cut = NOW + timedelta(seconds=5)
    page = await list_display_openings(
        async_session,
        test_user.id,
        limit=1,
        offset=0,
        criteria=DisplayQuery(sort="name", as_of=cut),
    )
    assert page.total == 2 and page.items[0].content == "Alpha"
    page = await list_display_openings(
        async_session,
        test_user.id,
        limit=1,
        offset=1,
        criteria=DisplayQuery(q="e", sort="oldest", as_of=cut),
    )
    assert page.total == 1 and page.items == ()
    for query in ("Private", "Hidden"):
        page = await list_display_openings(
            async_session,
            test_user.id,
            limit=10,
            offset=0,
            criteria=DisplayQuery(q=query, as_of=cut),
        )
        assert page.total == 0 and page.items == ()


async def test_peer_search_never_reveals_the_other_side_of_the_relay(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    peer = User(id=uuid4(), email=f"peer-{uuid4()}@example.com", full_name="Élodie")
    async_session.add(peer)
    await async_session.flush()
    lo, hi = canonical_pair(test_user.id, peer.id)
    pair = PeerConnection(
        user_a_id=lo,
        user_b_id=hi,
        requested_by_id=test_user.id,
        status="accepted",
        requested_at=NOW,
    )
    async_session.add(pair)
    await async_session.flush()
    for sender, recipient, content, delivered in [
        (test_user.id, peer.id, "My directive", "Hidden foreign rendering"),
        (peer.id, test_user.id, "Hidden foreign directive", "My receipt"),
    ]:
        async_session.add(
            PeerMessage(
                connection_id=pair.id,
                sender_id=sender,
                recipient_id=recipient,
                content=content,
                delivered_text=delivered,
                status="delivered",
                delivered_at=NOW,
            )
        )
    await async_session.flush()
    repo = PeerHistoryRepository(async_session)
    assert await repo.page(
        test_user.id, limit=10, offset=0, criteria=DisplayQuery(q="Hidden", as_of=NOW)
    ) == ([], 0)
    page, total = await repo.page(
        test_user.id, limit=10, offset=0, criteria=DisplayQuery(q="elodie", sort="name", as_of=NOW)
    )
    assert total == 2 and {row.content for row in page} == {"My directive", "My receipt"}
    peer.full_name = "New name"
    await async_session.flush()
    assert await repo.page(
        test_user.id, limit=10, offset=0, criteria=DisplayQuery(q="elodie", as_of=NOW)
    ) == ([], 0)
    async_session.add(PeerBlock(blocker_id=test_user.id, blocked_id=peer.id))
    await async_session.flush()
    assert await repo.page(test_user.id, limit=10, offset=0, criteria=DisplayQuery(as_of=NOW)) == (
        [],
        0,
    )


def notification(owner: UUID, content: str, when: datetime) -> HeartbeatNotification:
    return HeartbeatNotification(
        id=uuid4(),
        user_id=owner,
        content=content,
        run_id=str(uuid4()),
        content_hash=str(uuid4()),
        sources_used="[]",
        created_at=when,
    )


async def test_heartbeat_display_search_order_and_empty_page_total(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    stranger = User(id=uuid4(), email=f"hub-{uuid4()}@example.com")
    async_session.add(stranger)
    await async_session.flush()
    zulu = notification(test_user.id, "Zèbre 100%_", NOW)
    alpha = notification(test_user.id, "Alpha 100%_", NOW - timedelta(days=1))
    older = notification(test_user.id, "Other", NOW - timedelta(days=2))
    async_session.add_all(
        [
            zulu,
            alpha,
            older,
            notification(stranger.id, "Secret 100%_", NOW),
            notification(test_user.id, "Future 100%_", NOW + timedelta(seconds=1)),
        ]
    )
    await async_session.flush()
    repo = HeartbeatNotificationRepository(async_session)
    rows, total = await repo.get_history(
        test_user.id, limit=1, criteria=DisplayQuery(q="100%_", sort="name", as_of=NOW)
    )
    assert [row.id for row in rows] == [alpha.id] and total == 2
    rows, total = await repo.get_history(
        test_user.id, limit=1, offset=1, criteria=DisplayQuery(q="100%_", sort="name", as_of=NOW)
    )
    assert [row.id for row in rows] == [zulu.id] and total == 2
    rows, total = await repo.get_history(
        test_user.id, limit=1, criteria=DisplayQuery(sort="oldest", as_of=NOW)
    )
    assert [row.id for row in rows] == [older.id] and total == 3
    assert await repo.get_history(
        test_user.id, limit=1, offset=100, criteria=DisplayQuery(as_of=NOW)
    ) == ([], 3)
    assert await repo.get_history(
        test_user.id, limit=1, criteria=DisplayQuery(q="absent", as_of=NOW)
    ) == ([], 0)


async def test_interest_name_and_body_share_one_owned_topic_join(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    stranger = User(id=uuid4(), email=f"foreign-{uuid4()}@example.com")
    async_session.add(stranger)
    await async_session.flush()
    topic = UserInterest(
        id=uuid4(),
        user_id=test_user.id,
        topic="Été cinéma",
        category="culture",
        last_mentioned_at=NOW,
    )
    foreign = UserInterest(
        id=uuid4(),
        user_id=stranger.id,
        topic="Hidden foreign topic",
        category="culture",
        last_mentioned_at=NOW,
    )
    async_session.add_all([topic, foreign])
    await async_session.flush()
    rows = [
        InterestNotification(
            id=uuid4(),
            user_id=test_user.id,
            interest_id=source,
            content=body,
            source="test",
            created_at=NOW,
            run_id=str(uuid4()),
            content_hash=str(uuid4()),
        )
        for source, body in [
            (topic.id, "Body"),
            (None, "Été in body"),
            (foreign.id, "Visible body"),
        ]
    ]
    async_session.add_all(rows)
    await async_session.flush()
    repo = InterestHistoryRepository(async_session)
    page, total = await repo.page(
        test_user.id, limit=1, offset=0, criteria=DisplayQuery(q="ete", sort="name", as_of=NOW)
    )
    assert total == 2 and len(page) == 1
    assert await repo.page(
        test_user.id, limit=10, offset=0, criteria=DisplayQuery(q="Hidden foreign", as_of=NOW)
    ) == ([], 0)
    page, total = await repo.page(
        test_user.id, limit=10, offset=0, criteria=DisplayQuery(q="Visible", as_of=NOW)
    )
    assert total == 1 and page[0].topic is None


async def test_reminders_sort_by_trigger_and_search_only_the_displayed_content(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    rows = [
        Reminder(
            id=uuid4(),
            user_id=test_user.id,
            content=title,
            original_message="Undisplayed secret",
            recurrence={},
            status=status,
            trigger_at=NOW + timedelta(days=days),
            created_at=NOW,
        )
        for title, days, status in [
            ("Zèbre", 1, "pending"),
            ("Alpha", 3, "pending"),
            ("Cancelled", 2, "cancelled"),
        ]
    ]
    async_session.add_all(rows)
    await async_session.flush()
    repo = ReminderRepository(async_session)
    for sort, expected in [
        (None, rows[0]),
        ("oldest", rows[0]),
        ("recent", rows[1]),
        ("name", rows[1]),
    ]:
        criteria = DisplayQuery.model_validate({"sort": sort, "as_of": NOW})
        page, total = await repo.pending_page(test_user.id, limit=1, offset=0, criteria=criteria)
        assert total == 2 and page[0].id == expected.id
    assert await repo.pending_page(
        test_user.id, limit=10, offset=0, criteria=DisplayQuery(q="secret", as_of=NOW)
    ) == ([], 0)


async def test_workboard_keeps_owner_holder_visibility_and_unknown_due_dates_last(
    async_session: AsyncSession,
    test_user: User,
) -> None:
    stranger = User(id=uuid4(), email=f"ticket-{uuid4()}@example.com")
    async_session.add(stranger)
    await async_session.flush()
    early = WorkboardTicket(
        id=uuid4(),
        owner_user_id=test_user.id,
        title="Zèbre",
        status="waiting",
        due_at=NOW - timedelta(days=2),
        created_at=NOW,
        status_changed_at=NOW,
    )
    late = WorkboardTicket(
        id=uuid4(),
        owner_user_id=stranger.id,
        assignee_user_id=test_user.id,
        title="Alpha",
        status="waiting",
        due_at=NOW - timedelta(days=1),
        created_at=NOW,
        status_changed_at=NOW,
    )
    unknown = WorkboardTicket(
        id=uuid4(),
        owner_user_id=test_user.id,
        title="Unknown",
        description="Hidden secret",
        status="waiting",
        due_at=None,
        created_at=NOW,
        status_changed_at=NOW,
    )
    hidden = WorkboardTicket(
        id=uuid4(),
        owner_user_id=stranger.id,
        title="Hidden secret",
        status="waiting",
        due_at=None,
        created_at=NOW,
        status_changed_at=NOW,
    )
    async_session.add_all([early, late, unknown, hidden])
    await async_session.flush()
    repo = WorkboardRepository(async_session)
    for sort, expected in [
        ("oldest", [early, late, unknown]),
        ("recent", [late, early, unknown]),
        ("name", [late, unknown, early]),
    ]:
        page, total = await repo.needs_me(
            test_user.id,
            NOW,
            limit=10,
            offset=0,
            criteria=DisplayQuery.model_validate({"sort": sort, "as_of": NOW}),
        )
        assert [row.id for row in page] == [row.id for row in expected] and total == 3
    assert await repo.needs_me(
        test_user.id, NOW, limit=10, offset=0, criteria=DisplayQuery(q="secret", as_of=NOW)
    ) == ([], 0)
