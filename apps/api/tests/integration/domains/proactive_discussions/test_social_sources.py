"""Personal dialogue context never crosses message, peer or source permissions."""

from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from src.core.config import settings
from src.core.field_names import FIELD_IS_AUTOMATED_SOURCE
from src.domains.conversations.models import Conversation, ConversationMessage
from src.domains.peers.discussion_source import PeerDiscussionSource, PeerMessageDiscussionSource
from src.domains.peers.models import PeerBlock, PeerConnection, PeerMessage, canonical_pair
from src.domains.relations.discussion_source import RelationDiscussionSource
from src.domains.relations.models import RelationAlias, RelationFavorite
from src.domains.shared.discussion_sources import ResearchRequest, SourceKey
from src.domains.users.models import User
from src.infrastructure.proactive.conversation_source import ConversationDiscussionSource
from tests.integration.domains.proactive_discussions.test_memory_portrait_sources import (
    NOW,
    read_request,
)

pytestmark = pytest.mark.integration


async def test_conversation_uses_visible_human_words_without_recycling_assistant_claims(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        conversation = Conversation(user_id=discussion_owner)
        db.add(conversation)
        await db.flush()
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content="My fictional piano recital is Friday",
                    created_at=NOW,
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content="Invented attendance",
                    created_at=NOW,
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content="Hidden ticket run",
                    hidden=True,
                    created_at=NOW,
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content="Automated input",
                    message_metadata={FIELD_IS_AUTOMATED_SOURCE: True},
                    created_at=NOW,
                ),
            ]
        )
        await db.commit()
    result = await ConversationDiscussionSource().read(
        read_request(discussion_owner, SourceKey.CONVERSATIONS)
    )
    assert result.total == 1 and result.items[0].excerpt == "My fictional piano recital is Friday"
    assert result.items[0].assertion == "reported"


async def test_a_blank_message_is_no_statement_and_never_voids_the_page(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    """One whitespace-only turn used to fail validation and close the whole source."""
    async with AsyncSession(async_engine) as db:
        conversation = Conversation(user_id=discussion_owner)
        db.add(conversation)
        await db.flush()
        db.add_all(
            [
                ConversationMessage(
                    conversation_id=conversation.id, role="user", content=" \n\t ", created_at=NOW
                ),
                ConversationMessage(
                    conversation_id=conversation.id,
                    role="user",
                    content="My fictional choir rehearses on Monday",
                    created_at=NOW,
                ),
            ]
        )
        await db.commit()
    result = await ConversationDiscussionSource().read(
        read_request(discussion_owner, SourceKey.CONVERSATIONS)
    )
    assert result.status == "ok" and result.total == 1
    assert [item.excerpt for item in result.items] == ["My fictional choir rehearses on Monday"]


async def test_relation_source_reads_explicit_links_without_hidden_memories_or_peer_reads(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
) -> None:
    async with AsyncSession(async_engine) as db:
        db.add_all(
            [
                RelationFavorite(
                    user_id=discussion_owner,
                    name_key="fictional alice",
                    display_name="Fictional Alice",
                ),
                RelationAlias(
                    user_id=discussion_owner,
                    alias_key="fictional mum",
                    canonical_key="fictional alice",
                    alias_display_name="Fictional Mum",
                ),
            ]
        )
        await db.commit()
    request = read_request(discussion_owner, SourceKey.RELATIONS).model_copy(
        update={
            "request": ResearchRequest(
                source=SourceKey.RELATIONS, operation="search", query="Fictional"
            )
        }
    )
    result = await RelationDiscussionSource().read(request)
    assert result.total == 2 and len(result.items) == 2
    assert all(item.required_sources == () for item in result.items)
    assert any("fictional alice" in item.excerpt for item in result.items)


async def test_peer_message_keeps_own_side_retention_and_live_connection_authority(
    async_engine: AsyncEngine,
    discussion_owner: UUID,
    committed_user_ids: list[UUID],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "peers_enabled", True)
    peer_id = uuid4()
    async with AsyncSession(async_engine) as db:
        db.add(
            User(
                id=peer_id,
                email=f"fictional-{peer_id}@example.test",
                full_name="Fictional peer",
                is_active=True,
            )
        )
        await db.flush()
        committed_user_ids.append(peer_id)
        a, b = canonical_pair(discussion_owner, peer_id)
        connection = PeerConnection(
            user_a_id=a,
            user_b_id=b,
            requested_by_id=discussion_owner,
            status="accepted",
            responded_at=NOW,
        )
        db.add(connection)
        await db.flush()
        db.add_all(
            [
                PeerMessage(
                    connection_id=connection.id,
                    sender_id=discussion_owner,
                    recipient_id=peer_id,
                    content="My own words",
                    delivered_text="Other assistant private tone",
                    status="delivered",
                    delivered_at=NOW,
                    expires_at=NOW + timedelta(days=2),
                ),
                PeerMessage(
                    connection_id=connection.id,
                    sender_id=peer_id,
                    recipient_id=discussion_owner,
                    content="Other raw directive",
                    delivered_text="Words actually received",
                    status="delivered",
                    delivered_at=NOW,
                    expires_at=NOW + timedelta(days=2),
                ),
                PeerMessage(
                    connection_id=connection.id,
                    sender_id=peer_id,
                    recipient_id=discussion_owner,
                    delivered_text="Expired secret",
                    status="delivered",
                    delivered_at=NOW,
                    expires_at=NOW - timedelta(seconds=1),
                ),
            ]
        )
        await db.commit()
    result = await PeerMessageDiscussionSource().read(
        read_request(discussion_owner, SourceKey.PEER_MESSAGES)
    )
    assert result.total == 2
    text = result.model_dump_json()
    assert "My own words" in text and "Words actually received" in text
    assert (
        "private tone" not in text and "raw directive" not in text and "Expired secret" not in text
    )
    assert all(item.expires_at == NOW + timedelta(days=2) for item in result.items)
    directory = await PeerDiscussionSource().read(read_request(discussion_owner, SourceKey.PEERS))
    assert directory.total == 1 and "example.test" not in directory.model_dump_json()
    async with AsyncSession(async_engine) as db:
        db.add(PeerBlock(blocker_id=peer_id, blocked_id=discussion_owner))
        await db.commit()
    assert (
        await PeerMessageDiscussionSource().read(
            read_request(discussion_owner, SourceKey.PEER_MESSAGES)
        )
    ).total == 0
    assert (
        await PeerDiscussionSource().read(read_request(discussion_owner, SourceKey.PEERS))
    ).total == 0
